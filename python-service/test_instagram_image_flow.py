"""Real sessions/PostgreSQL, synthetic provider, zero Meta network requests."""
import base64
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from app import app
from account_auth import digest, COOKIE
from instagram_meta_adapter import InstagramAdapter, ProviderResponse, ProviderError
from instagram_publishing import InstagramPublishingService, service
from instagram_token_vault import TokenVault, TokenBinding
import test_account_auth as accounts
from test_instagram_media import picture

PREFIX = '/api/v1/instagram/publishing'


class Meta:
    def __init__(self):
        self.calls = []
        self.state = 'FINISHED'
        self.fail = None

    def __call__(self, req):
        self.calls.append(req)
        if self.fail and req.url.endswith(self.fail):
            raise ProviderError(outcome_unknown=True)
        if req.url.endswith('/me'):
            value = {'id':'123456','username':'synthetic_profile','account_type':'BUSINESS'}
        elif req.method == 'GET':
            value = {'status_code': self.state}
        else:
            value = {'id': '10001' if req.url.endswith('/media') else '10002'}
        return ProviderResponse(200, json.dumps(value).encode())


@unittest.skipUnless(accounts.DB, 'TEST_DATABASE_URL not configured')
class ImageFlowTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        self.client = self.admin_client
        self.identity = self.client.identity
        self.uid = self.identity['usuario']['id']
        self.wid = self.identity['negocio']['id']
        self.meta = Meta()
        self.vault = TokenVault(keys={'test': b't' * 32}, active_key_id='test')
        self.connection = uuid4()
        sealed = self.vault.seal('synthetic-access-token', TokenBinding(self.wid, self.connection, '123456'))
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("INSERT INTO socialmei.ig_meta_connections "
                         "(id,workspace_id,external_account_id,account_type,status,scopes,encrypted_token,token_kind,issued_at,expires_at,created_by) "
                         "VALUES(%s,%s,'123456','BUSINESS','connected',%s,%s,'long',NOW(),NOW()+INTERVAL '1 day',%s)",
                         (self.connection, self.wid, ['instagram_business_basic', 'instagram_business_content_publish'], sealed, self.uid))
        adapter = InstagramAdapter(client_id='123', client_secret='synthetic-secret',
                                   callback_uri=accounts.ORIGIN+'/return', graph_version='v22.0', transport=self.meta)
        self.publisher = InstagramPublishingService(adapter, self.vault)
        app.dependency_overrides[service] = lambda: self.publisher
        self.addCleanup(app.dependency_overrides.clear)

    def image_payload(self):
        return {'request_id': str(uuid4()), 'image_url': 'https://cdn.example.org/photo.jpg', 'caption': 'Foto de teste'}

    def test_finished_verified_before_publish_and_replay_no_send(self):
        payload = self.image_payload()
        result = self.client.post(PREFIX+'/image', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['status'], 'published')
        self.assertEqual(result.json()['media_id'], '10002')
        self.assertEqual([r.method for r in self.meta.calls], ['POST', 'GET', 'POST'])
        self.assertEqual(self.meta.calls[1].params['fields'], 'status_code')
        self.assertEqual(self.client.post(PREFIX+'/image', json=payload).json(), result.json())
        self.assertEqual(len(self.meta.calls), 3)

    def test_processing_resume_then_single_publish(self):
        self.meta.state = 'IN_PROGRESS'
        result = self.client.post(PREFIX+'/image', json=self.image_payload()).json()
        self.assertEqual(result['status'], 'created')
        self.assertEqual(len(self.meta.calls), 2)
        self.meta.state = 'FINISHED'
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.ig_meta_publications SET checked_at=NOW()-INTERVAL '61 seconds'")
        result = self.client.post(PREFIX+'/'+result['id']+'/continue', json={})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['status'], 'published')
        self.assertEqual(len([r for r in self.meta.calls if r.url.endswith('/media_publish')]), 1)

    def test_timeout_unknown_never_resends(self):
        self.meta.fail = '/media_publish'
        payload = self.image_payload()
        result = self.client.post(PREFIX+'/image', json=payload).json()
        self.assertEqual(result['status'], 'uncertain')
        for _ in range(2):
            self.client.post(PREFIX+'/image', json=payload)
            self.client.post(PREFIX+'/'+result['id']+'/continue', json={})
        self.assertEqual(len([r for r in self.meta.calls if r.url.endswith('/media_publish')]), 1)

    def test_failed_container_never_publishes(self):
        self.meta.state = 'ERROR'
        result = self.client.post(PREFIX+'/image', json=self.image_payload()).json()
        self.assertEqual(result['error_code'], 'media_processing_failed')
        self.assertFalse(any(r.url.endswith('/media_publish') for r in self.meta.calls))

    def test_concurrent_same_operation_claim(self):
        payload = self.image_payload()
        token = self.client.cookies.get(COOKIE)
        headers = dict(self.client.headers)
        def call(_):
            client = TestClient(app, base_url=accounts.ORIGIN, headers=headers)
            client.cookies.set(COOKIE, token)
            return client.post(PREFIX+'/image', json=payload)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(call, range(2)))
        self.assertTrue(all(r.status_code == 200 for r in results), [r.text for r in results])
        self.assertEqual(len([r for r in self.meta.calls if r.url.endswith('/media')]), 1)
        self.assertEqual(len([r for r in self.meta.calls if r.url.endswith('/media_publish')]), 1)

    def test_upload_delivery_expiry_and_workspace_guard(self):
        upload = {'request_id': str(uuid4()), 'image_base64': base64.b64encode(picture('PNG')).decode()}
        result = self.client.post(PREFIX+'/upload', json=upload)
        self.assertEqual(result.status_code, 200, result.text)
        asset = result.json()['media_id']
        with psycopg.connect(accounts.DB) as conn:
            key = conn.execute('SELECT public_key FROM socialmei.ig_meta_media WHERE id=%s', (asset,)).fetchone()[0]
        anon = TestClient(app, base_url=accounts.ORIGIN)
        delivered = anon.get('/media/instagram/'+key+'.jpg')
        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(delivered.headers['content-type'], 'image/jpeg')
        self.assertEqual(delivered.headers['cache-control'], 'no-store')
        self.assertEqual(anon.post(PREFIX+'/upload', json=upload).status_code, 403)
        payload = {'request_id': str(uuid4()), 'media_id': asset, 'caption': 'Foto local'}
        sent = self.client.post(PREFIX+'/image', json=payload)
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(sent.json()['status'], 'published')
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.ig_meta_media SET expires_at=NOW()-INTERVAL '1 second'")
        self.assertEqual(anon.get('/media/instagram/'+key+'.jpg').status_code, 404)
        self.assertEqual(self.client.post(PREFIX+'/image', json=payload).json()['status'], 'published')

    def test_forbidden_member_no_provider_call(self):
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='member' WHERE user_id=%s", (self.uid,))
        result = self.client.post(PREFIX+'/image', json=self.image_payload())
        self.assertEqual(result.status_code, 403, result.text)
        self.assertEqual(self.meta.calls, [])

    def test_profile_is_verified_and_connection_change_rejected(self):
        profile = self.client.get(PREFIX+'/account')
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()['username'], 'synthetic_profile')
        result = self.client.post(PREFIX+'/image', json={**self.image_payload(), 'connection_id':str(uuid4())})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(len(self.meta.calls), 1)

    def test_disconnected_missing_permission_and_changed_content(self):
        payload = self.image_payload()
        first = self.client.post(PREFIX+'/image', json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.client.post(PREFIX+'/image', json={**payload,'caption':'Outra foto'}).status_code, 409)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET scopes=ARRAY['instagram_business_basic']")
        self.assertEqual(self.client.post(PREFIX+'/image', json=self.image_payload()).status_code, 409)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET status='disconnected',encrypted_token=NULL,disconnected_at=NOW()")
        self.assertEqual(self.client.post(PREFIX+'/image', json=self.image_payload()).status_code, 409)
        self.assertEqual(len(self.meta.calls), 3)

    def test_other_workspace_cannot_continue_read_or_use_media(self):
        result = self.client.post(PREFIX+'/image', json=self.image_payload()).json()
        asset = self.client.post(PREFIX+'/upload', json={'request_id':str(uuid4()),'image_base64':base64.b64encode(picture()).decode()}).json()['media_id']
        with psycopg.connect(accounts.DB) as conn:
            other = conn.execute("INSERT INTO socialmei.workspaces(slug,nome) VALUES('other-tenant','Other') RETURNING id").fetchone()[0]
            conn.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')", (other,self.uid))
            conn.execute("UPDATE socialmei.auth_sessoes SET workspace_id=%s WHERE token_hash=%s", (other,digest(self.client.cookies.get(COOKIE))))
        self.assertEqual(self.client.get(PREFIX+'/recent').json()['items'], [])
        self.assertEqual(self.client.post(PREFIX+'/'+result['id']+'/continue',json={}).status_code,404)
        # Direct asset lookup enforces identity even when an attacker knows the UUID.
        from instagram_media import resolve_media
        from psycopg.rows import dict_row
        with psycopg.connect(accounts.DB, row_factory=dict_row) as conn:
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as error:
                resolve_media(conn, {'id':self.uid,'workspace_id':other}, asset)
            self.assertEqual(error.exception.status_code,404)

    def test_csrf_and_invalid_upload_no_provider_calls(self):
        bad = self.client.post(PREFIX+'/upload', json={'request_id':str(uuid4()),'image_base64':'YmFk'})
        self.assertEqual(bad.status_code,422)
        bad = self.client.post(PREFIX+'/image', json=self.image_payload(), headers={'X-SocialMEI-CSRF':'wrong'})
        self.assertEqual(bad.status_code,403)
        self.assertEqual(self.meta.calls,[])
