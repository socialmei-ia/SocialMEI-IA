"""Authenticated bridge fixtures only; PostgreSQL tests require a disposable DB."""
import hashlib
import hmac
import json
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import app
from instagram_n8n_ingress import PATH, InstagramN8NIngressService, bound_event, ingress_service
from instagram_meta_ingress import InstagramIngressService, parse_message_events
import settings
import test_instagram_persistent_oauth as oauth
from test_instagram_meta_ingress import encoded, payload, signature as meta_signature, KEY as META_KEY, VERIFY
from test_instagram_simulation import DB, ENV, COOKIE, TOKEN

KEY = "synthetic-n8n-signing-key-never-production-123"
NOW = int(time.time())
CONFIG = {
    **ENV,
    "SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED": "true",
    "SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY": KEY,
    "SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET": META_KEY,
    "SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS": '{"987654321":1}',
}


def signed(raw, timestamp=NOW, key=KEY):
    timestamp = str(timestamp)
    return {"Content-Type": "application/json", "X-Hub-Signature-256": meta_signature(raw), "X-SocialMEI-Timestamp": timestamp,
            "X-SocialMEI-Signature": "sha256=" + hmac.new(
                key.encode(), timestamp.encode() + b"\n" + raw, hashlib.sha256,
            ).hexdigest()}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.service = InstagramN8NIngressService(key=KEY, meta_app_secret=META_KEY, bindings={"987654321": 1}, clock=lambda: NOW)

    def test_invalid_auth_and_stale_requests_never_parse_or_reach_database(self):
        raw = encoded(payload())
        for timestamp, signature in ((str(NOW), "bad"), (str(NOW-301), signed(raw, NOW-301)["X-SocialMEI-Signature"]),
                                     (str(NOW+301), signed(raw, NOW+301)["X-SocialMEI-Signature"]),
                                     ("0"+str(NOW), "bad"), (str(NOW), meta_signature(raw))):
            with self.subTest(timestamp=timestamp), patch("instagram_n8n_ingress.parse_message_events", side_effect=AssertionError("Parser accessed")):
                with self.assertRaises(HTTPException) as caught:
                    self.service.receive(raw, timestamp, signature, meta_signature(raw))
                self.assertEqual(caught.exception.status_code, 403)

    def test_mutated_body_and_different_key_are_refused(self):
        raw = encoded(payload())
        for candidate, key in ((raw+b" ", KEY), (raw, "other-synthetic-key")):
            with patch("instagram_n8n_ingress.persist_authenticated_events", side_effect=AssertionError("DB accessed")):
                with self.assertRaises(HTTPException) as caught:
                    self.service.receive(candidate, str(NOW), signed(raw, key=key)["X-SocialMEI-Signature"], meta_signature(raw))
                self.assertEqual(caught.exception.status_code, 403)

    def test_relay_signature_alone_cannot_authenticate_an_internet_payload(self):
        raw=encoded(payload())
        for source_signature in ('', 'sha256='+'0'*64, signed(raw)['X-SocialMEI-Signature']):
            with patch('instagram_n8n_ingress.persist_authenticated_events',side_effect=AssertionError('DB accessed')):
                with self.assertRaises(HTTPException) as caught:
                    self.service.receive(raw,str(NOW),signed(raw)['X-SocialMEI-Signature'],source_signature)
                self.assertEqual(caught.exception.status_code,403)
        serialized=json.dumps(payload(),sort_keys=True).encode()
        with self.assertRaises(HTTPException) as caught:
            self.service.receive(serialized,str(NOW),signed(serialized)['X-SocialMEI-Signature'],meta_signature(raw))
        self.assertEqual(caught.exception.status_code,403)

    def test_original_meta_secret_must_be_explicit_and_distinct(self):
        for secret in ('', 'short', KEY):
            with self.assertRaises(ValueError):
                InstagramN8NIngressService(key=KEY,meta_app_secret=secret,bindings={'987654321':1})

    def test_alias_mapping_is_strict_and_not_supplied_by_the_payload(self):
        invalid = [
            {'111': {'workspace_id': True, 'connection_account_id': '987654321'}},
            {'111': {'workspace_id': 1, 'connection_account_id': 987654321}},
            {'111': {'workspace_id': 1, 'connection_account_id': '987654321', 'extra': 1}},
            {'111': {'workspace_id': 1}},
            {'111': {'workspace_id': 1, 'connection_account_id': '987654321'}, '987654321': 1},
        ]
        for bindings in invalid:
            with self.subTest(bindings=bindings), self.assertRaises(ValueError):
                InstagramN8NIngressService(key=KEY,meta_app_secret=META_KEY,bindings=bindings)
        raw=encoded(payload(account='111'))
        original=parse_message_events(raw,meta_signature(raw),META_KEY)[0]
        canonical=bound_event(original,'987654321')
        self.assertEqual(canonical.account_ref,'instagram:987654321')
        self.assertEqual(canonical.contact_ref,original.contact_ref)
        self.assertEqual(canonical.event_key,original.event_key)
        self.assertEqual(canonical.canonical_fingerprint,original.canonical_fingerprint)

    def test_authenticated_bad_envelope_and_workspace_injection_are_refused(self):
        spoofed=payload()
        spoofed['entry'][0]['workspace_id']=99
        for raw in (b'{"object":"instagram","object":"instagram","entry":[]}', b'[]', b'{}', encoded(spoofed)):
            with self.subTest(raw=raw[:20]), patch("instagram_n8n_ingress.persist_authenticated_events", side_effect=AssertionError("DB accessed")):
                with self.assertRaises(HTTPException) as caught:
                    self.service.receive(raw,str(NOW),signed(raw)["X-SocialMEI-Signature"], meta_signature(raw))
                self.assertEqual(caught.exception.status_code,403)

    def test_unknown_account_is_refused_before_database(self):
        raw=encoded(payload(account="111"))
        with patch("instagram_n8n_ingress.persist_authenticated_events", side_effect=AssertionError("DB accessed")):
            with self.assertRaises(HTTPException) as caught:
                self.service.receive(raw,str(NOW),signed(raw)["X-SocialMEI-Signature"], meta_signature(raw))
        self.assertEqual(caught.exception.status_code,403)

    def test_retries_and_mixed_batches_never_continue_automation(self):
        raw=encoded(payload())
        for processed,ignored,duplicates,allowed in ((1,0,0,True),(0,0,1,False),(1,0,1,False),(0,1,0,False),(1,1,0,False)):
            with patch("instagram_n8n_ingress.persist_authenticated_events", return_value=dict(received=True,processed=processed,ignored=ignored,duplicates=duplicates)):
                result=self.service.receive(raw,str(NOW),signed(raw)["X-SocialMEI-Signature"], meta_signature(raw))
                self.assertEqual(result['continue_automation'],allowed)

    def test_invalid_private_configuration_and_default_disabled(self):
        bad_configs=[{"SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED":"false"},
                     {"SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY":"short"},
                     {"SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET":""},
                     {"SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS":'{"987654321":true}'},
                     {"SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS":'{"987654321":1,"987654321":2}'},
                     {"SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS":'{"987654321":-1}'},
                     {"SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS":'{}'}]
        for config in bad_configs:
            with patch.dict(os.environ,{**CONFIG,**config}),patch("instagram_n8n_ingress.persist_authenticated_events",side_effect=AssertionError("DB accessed")):
                response=TestClient(app).post(PATH,content=b"{}",headers=signed(b"{}"))
                self.assertEqual(response.status_code,503)
                self.assertNotIn(KEY,response.text)

    def test_http_bounds_duplicate_headers_queries_and_privacy(self):
        raw=encoded(payload())
        with patch.dict(os.environ,CONFIG),patch("instagram_n8n_ingress.persist_authenticated_events",side_effect=AssertionError("DB accessed")):
            client=TestClient(app)
            for headers,status in (({},415),({**signed(raw),"Content-Type":"text/plain"},415),({**signed(raw),"Origin":"https://example.com"},403)):
                response=client.post(PATH,content=raw,headers=headers)
                self.assertEqual(response.status_code,status)
            response=client.post(PATH,content=b'x'*65537,headers=signed(b'x'*65537))
            self.assertEqual(response.status_code,413)
            headers=list(signed(raw).items())+[("X-SocialMEI-Signature","bad")]
            self.assertEqual(client.post(PATH,content=raw,headers=headers).status_code,403)
            headers=list(signed(raw).items())+[("X-Hub-Signature-256","bad")]
            self.assertEqual(client.post(PATH,content=raw,headers=headers).status_code,403)
            response=client.post(PATH+'?secret=never-echo',content=raw,headers=signed(raw))
            self.assertEqual(response.status_code,403)
            self.assertNotIn('never-echo',response.text)
            self.assertEqual(response.headers['cache-control'],'no-store')


@unittest.skipUnless(DB,"Disposable PostgreSQL not configured")
class DatabaseTests(unittest.TestCase):
    setUpClass=classmethod(oauth.PersistentTests.setUpClass.__func__)
    tearDown=oauth.PersistentTests.tearDown
    begin=oauth.PersistentTests.begin
    complete=oauth.PersistentTests.complete
    post=oauth.PersistentTests.post

    def setUp(self):
        oauth.PersistentTests.setUp(self)
        self.flags=patch.dict(os.environ,CONFIG)
        self.flags.start()
        self.addCleanup(self.flags.stop)
        self.assertEqual(self.complete(self.begin()).status_code,200)
        self.bridge=InstagramN8NIngressService(key=KEY,meta_app_secret=META_KEY,bindings={'987654321':self.identity['workspace_id']},clock=lambda:NOW)
        app.dependency_overrides[ingress_service]=lambda:self.bridge
        self.addCleanup(app.dependency_overrides.pop,ingress_service,None)

    def receive(self,value=None):
        raw=encoded(payload() if value is None else value)
        return self.client.post(PATH,content=raw,headers=signed(raw))

    def counts(self):
        with psycopg.connect(DB) as conn:
            return tuple(conn.execute('SELECT (SELECT count(*) FROM socialmei.ig_meta_ingress_events WHERE workspace_id=%s),(SELECT count(*) FROM socialmei.me_messages WHERE workspace_id=%s)',(self.identity['workspace_id'],)*2).fetchone())

    def alias_bridge(self,workspace=None):
        self.bridge=InstagramN8NIngressService(
            key=KEY,meta_app_secret=META_KEY,clock=lambda:NOW,
            bindings={'555444333':{'workspace_id':self.identity['workspace_id'] if workspace is None else workspace,
                                    'connection_account_id':'987654321'}},
        )

    def test_verified_source_alias_persists_canonical_account_and_original_fingerprint(self):
        self.alias_bridge()
        value=payload(account='555444333')
        raw=encoded(value)
        original=parse_message_events(raw,meta_signature(raw),META_KEY)[0]
        response=self.receive(value)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['processed'],1)
        self.assertTrue(response.json()['continue_automation'])
        self.assertEqual(self.receive(value).json()['duplicates'],1)
        with psycopg.connect(DB) as conn:
            row=conn.execute('SELECT external_account_id,event_key,fingerprint FROM socialmei.ig_meta_ingress_events WHERE workspace_id=%s',(self.identity['workspace_id'],)).fetchone()
        self.assertEqual(row,('987654321',original.event_key,original.canonical_fingerprint))
        rows=self.client.get('/api/v1/message-enrichment/conversations').json()['items']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['account_ref'],'instagram:987654321')
        self.assertEqual(rows[0]['messages'][0]['text'],value['entry'][0]['messaging'][0]['message']['text'])
        self.assertEqual(self.counts(),(1,1))

    def test_alias_unknown_source_and_wrong_workspace_are_refused(self):
        self.alias_bridge()
        self.assertEqual(self.receive(payload(account='111')).status_code,403)
        # Canonical OAuth ID is not automatically a permitted webhook alias.
        self.assertEqual(self.receive(payload(account='987654321')).status_code,403)
        self.alias_bridge(self.identities[1]['workspace_id'])
        self.assertEqual(self.receive(payload(account='555444333')).status_code,403)
        self.assertEqual(self.counts(),(0,0))

    def test_alias_concurrent_replay_and_canonical_source_conflict_do_not_duplicate(self):
        self.alias_bridge()
        raw=encoded(payload(account='555444333'))
        relay=signed(raw)['X-SocialMEI-Signature']
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.bridge.receive(raw,str(NOW),relay,meta_signature(raw)),range(3)))
        self.assertEqual(sum(row['processed'] for row in results),1)
        self.assertEqual(sum(row['duplicates'] for row in results),2)
        canonical_raw=encoded(payload())
        meta=InstagramIngressService(app_secret=META_KEY,verify_token=VERIFY)
        with self.assertRaises(HTTPException) as caught:
            meta.receive(canonical_raw,meta_signature(canonical_raw))
        self.assertEqual(caught.exception.status_code,409)
        self.assertEqual(self.counts(),(1,1))

    def test_message_is_durable_and_visible_without_ai_or_provider_calls(self):
        self.transport.fail=True
        response=self.receive()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['processed'],1)
        self.assertTrue(response.json()['continue_automation'])
        self.assertEqual(self.counts(),(1,1))
        rows=self.client.get('/api/v1/message-enrichment/conversations').json()['items']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['origin'],'instagram')
        self.assertEqual(rows[0]['messages'][0]['text'],'  Mensagem original\n')
        self.assertIsNone(rows[0]['messages'][0]['enrichment'])
        self.identity=self.identities[1]
        self.client.cookies.set(COOKIE,'c'*64)
        self.assertEqual(self.client.get('/api/v1/message-enrichment/conversations').json()['items'],[])

    def test_duplicate_and_concurrent_retries_persist_once(self):
        raw=encoded(payload())
        signature=signed(raw)['X-SocialMEI-Signature']
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.bridge.receive(raw,str(NOW),signature,meta_signature(raw)),range(4)))
        self.assertEqual(sum(r['processed'] for r in results),1)
        self.assertEqual(sum(r['duplicates'] for r in results),3)
        self.assertEqual(sum(r['continue_automation'] for r in results),1)
        self.assertEqual(self.counts(),(1,1))

    def test_conflicting_replay_returns_409_without_mutating_message(self):
        self.assertEqual(self.receive().status_code,200)
        response=self.receive(payload(text='Different synthetic text'))
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.counts(),(1,1))

    def test_replay_between_meta_and_n8n_shares_same_durable_ledger(self):
        raw=encoded(payload())
        meta=InstagramIngressService(app_secret=META_KEY,verify_token=VERIFY)
        self.assertEqual(meta.receive(raw,meta_signature(raw))['processed'],1)
        response=self.receive()
        self.assertEqual(response.json()['duplicates'],1)
        self.assertFalse(response.json()['continue_automation'])
        self.assertEqual(self.counts(),(1,1))

    def test_wrong_workspace_expired_or_disconnected_connection_never_persist(self):
        self.bridge=InstagramN8NIngressService(key=KEY,meta_app_secret=META_KEY,bindings={'987654321':self.identities[1]['workspace_id']},clock=lambda:NOW)
        self.assertEqual(self.receive().status_code,403)
        self.bridge=InstagramN8NIngressService(key=KEY,meta_app_secret=META_KEY,bindings={'987654321':self.identity['workspace_id']},clock=lambda:NOW)
        with psycopg.connect(DB) as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '2 days',expires_at=NOW()-INTERVAL '1 day' WHERE workspace_id=%s",(self.identity['workspace_id'],))
        self.assertEqual(self.receive().status_code,404)
        self.assertEqual(self.counts(),(0,0))

    def test_database_failure_rolls_back_batch_and_retry_recovers(self):
        value=payload(mid='first')
        second=payload(mid='second')['entry'][0]['messaging'][0]
        value['entry'][0]['messaging'].append(second)
        from instagram_meta_ingress import _append_inbox_message
        calls=[]
        def fail_second(*args,**kwargs):
            calls.append(1)
            if len(calls)==2: raise RuntimeError('private failure must never escape')
            return _append_inbox_message(*args,**kwargs)
        with patch('instagram_meta_ingress._append_inbox_message',side_effect=fail_second):
            response=self.receive(value)
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private failure',response.text)
        self.assertEqual(self.counts(),(0,0))
        self.assertEqual(self.receive(value).json()['processed'],2)
        self.assertEqual(self.counts(),(2,2))

    def test_mixed_batch_persists_new_but_does_not_repeat_ai(self):
        self.assertEqual(self.receive().status_code,200)
        value=payload()
        value['entry'][0]['messaging'].append(payload(mid='new-mid')['entry'][0]['messaging'][0])
        response=self.receive(value)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['processed'],1)
        self.assertEqual(response.json()['duplicates'],1)
        self.assertFalse(response.json()['continue_automation'])
        self.assertEqual(self.counts(),(2,2))
