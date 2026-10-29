"""Credential maintenance uses disposable PostgreSQL and an injected provider."""
import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from app import app
from instagram_meta_adapter import ProviderResponse
import test_instagram_persistent_oauth as oauth
from account_auth import digest

PATH = oauth.PREFIX + '/connection/refresh-token'


class RefreshTransport(oauth.FakeTransport):
    lifetime = 5184000

    def __init__(self):
        super().__init__()
        # Other legacy fixtures intentionally retain their fixed account ID.
        self.account = str(uuid4().int)

    def __call__(self, request):
        if request.url.endswith('/refresh_access_token'):
            self.calls.append(request)
            self.started.set()
            if self.block and not self.block.wait(10):
                raise RuntimeError('Synthetic refresh timeout')
            if self.fail:
                raise RuntimeError('private-provider-token-must-not-escape')
            return ProviderResponse(200, json.dumps({
                'access_token': 'synthetic-refreshed-token', 'token_type': 'bearer', 'expires_in': self.lifetime,
            }).encode())
        return super().__call__(request)


class RefreshClosedContracts(unittest.TestCase):
    def test_refresh_is_disabled_by_default_and_never_starts_oauth(self):
        transport = RefreshTransport()
        app.dependency_overrides[oauth.oauth_service] = lambda: oauth.service(transport)
        self.addCleanup(app.dependency_overrides.pop, oauth.oauth_service, None)
        with patch.dict(os.environ, {**oauth.ENV, **oauth.OAUTH_ENV, 'SOCIALMEI_INSTAGRAM_TOKEN_REFRESH_ENABLED': 'false'}), patch(
            'account_auth.session_identity', return_value={
                'id': 1, 'workspace_id': 1, 'role': 'owner', 'administrador_plataforma': False,
            }), patch('instagram_persistent_oauth.connect', side_effect=AssertionError('No database')):
            client = TestClient(app, base_url=oauth.ORIGIN)
            client.cookies.set(oauth.COOKIE, oauth.TOKEN)
            r = client.post(PATH, json={}, headers={'Origin': oauth.ORIGIN, 'X-SocialMEI-CSRF': oauth.csrf(oauth.TOKEN)})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.headers['cache-control'], 'no-store')
        self.assertEqual(transport.calls, [])


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Disposable PostgreSQL required')
class RefreshDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(oauth.PersistentTests.setUpClass.__func__)
    tearDown = oauth.PersistentTests.tearDown
    post = oauth.PersistentTests.post
    begin = oauth.PersistentTests.begin
    complete = oauth.PersistentTests.complete
    connection = oauth.PersistentTests.connection

    def setUp(self):
        oauth.PersistentTests.setUp(self)
        flag = patch.dict(os.environ, {'SOCIALMEI_INSTAGRAM_TOKEN_REFRESH_ENABLED': 'true'})
        flag.start()
        self.addCleanup(flag.stop)
        self.transport = RefreshTransport()
        self.service = oauth.service(self.transport)
        with self.database() as conn:
            conn.execute('DELETE FROM socialmei.auth_limites WHERE chave=%s', (digest('global:instagram-token-refresh'),))

    def database(self):
        return psycopg.connect(os.environ['TEST_DATABASE_URL'])

    def connected(self, *, old=True):
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        if old:
            with self.database() as conn:
                conn.execute("UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '2 days',"
                             "expires_at=NOW()+INTERVAL '58 days' WHERE workspace_id=%s", (self.identity['workspace_id'],))
        self.transport.calls.clear()
        self.transport.started.clear()

    def refresh(self):
        return self.post('/connection/refresh-token')

    def test_renews_ciphertext_and_expiration_without_exposing_token(self):
        self.connected()
        previous = self.connection()
        result = self.refresh()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['status'], 'refreshed')
        after = self.connection()
        self.assertEqual(after[:2], previous[:2])
        self.assertNotEqual(after[2], previous[2])
        self.assertEqual(after[3], previous[3] + 1)
        from instagram_token_vault import TokenBinding
        opened = self.service.vault.open(after[2], TokenBinding(self.identity['workspace_id'], after[0], after[1]))
        self.assertEqual(opened, 'synthetic-refreshed-token')
        self.assertNotIn('synthetic-', result.text)
        self.assertEqual(len(self.transport.calls), 2)
        with self.database() as conn:
            action = conn.execute("SELECT acao FROM socialmei.auth_auditoria WHERE user_id=%s ORDER BY id DESC LIMIT 1", (self.identity['id'],)).fetchone()[0]
        self.assertEqual(action, 'instagram_token_refreshed')

    def test_recent_expired_and_disconnected_connections_do_not_call_provider(self):
        self.connected(old=False)
        self.assertEqual(self.refresh().status_code, 409)
        with self.database() as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '60 days',expires_at=NOW()-INTERVAL '1 hour' WHERE workspace_id=%s", (self.identity['workspace_id'],))
        self.assertEqual(self.refresh().status_code, 409)
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.post('/connection/disconnect').status_code, 200)
        self.assertEqual(self.refresh().status_code, 409)

    def test_provider_failure_preserves_previous_connection_and_ciphertext(self):
        self.connected()
        previous = self.connection()
        self.transport.fail = True
        result = self.refresh()
        self.assertEqual(result.status_code, 503, result.text)
        self.assertNotIn('private-provider', result.text)
        self.assertEqual(self.connection(), previous)

    def test_wrong_identity_preserves_previous_connection(self):
        self.connected()
        previous = self.connection()
        self.transport.account = '000999'
        self.assertEqual(self.refresh().status_code, 503)
        self.assertEqual(self.connection(), previous)

    def test_concurrent_refresh_makes_one_provider_request(self):
        self.connected()
        self.transport.block = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(self.refresh)
            self.assertTrue(self.transport.started.wait(5))
            two = pool.submit(self.refresh)
            try:
                other = two.result(5)
                self.assertEqual(other.status_code, 409, other.text)
            finally:
                self.transport.block.set()
            self.assertEqual(one.result(5).status_code, 200)
        self.assertEqual(sum(r.url.endswith('/refresh_access_token') for r in self.transport.calls), 1)

    def test_disconnect_during_provider_call_cannot_be_resurrected(self):
        self.connected()
        self.transport.block = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.refresh)
            self.assertTrue(self.transport.started.wait(5))
            try:
                disconnected = pool.submit(self.post, '/connection/disconnect').result(5)
                self.assertEqual(disconnected.status_code, 200)
            finally:
                self.transport.block.set()
            self.assertEqual(future.result(5).status_code, 409)
        self.assertEqual(self.connection()[4], 'disconnected')
        self.assertIsNone(self.connection()[2])

    def test_revoked_session_during_refresh_cannot_save_new_token(self):
        self.connected()
        previous = self.connection()
        self.transport.block = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.refresh)
            self.assertTrue(self.transport.started.wait(5))
            try:
                with self.database() as conn:
                    conn.execute('UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE token_hash=%s', (digest(oauth.TOKEN),))
            finally:
                self.transport.block.set()
            self.assertEqual(future.result(5).status_code, 401)
        self.assertEqual(self.connection(), previous)

    def test_other_workspace_and_member_cannot_renew_owner_connection(self):
        self.connected()
        self.identity = self.identities[1]
        self.client.cookies.set(oauth.COOKIE, 'c' * 64)
        self.headers['X-SocialMEI-CSRF'] = oauth.csrf('c' * 64)
        self.assertEqual(self.refresh().status_code, 409)
        self.identity = self.identities[0]
        self.client.cookies.set(oauth.COOKIE, oauth.TOKEN)
        self.headers['X-SocialMEI-CSRF'] = oauth.csrf(oauth.TOKEN)
        with self.database() as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='member' WHERE workspace_id=%s AND user_id=%s",
                         (self.identity['workspace_id'], self.identity['id']))
        self.assertEqual(self.refresh().status_code, 403)
        self.assertEqual(self.transport.calls, [])

    def test_csrf_is_required_and_repeated_success_does_not_refresh_again(self):
        self.connected()
        r = self.client.post(PATH, json={}, headers={'Origin': oauth.ORIGIN})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.refresh().status_code, 200)
        self.assertEqual(self.refresh().status_code, 409)
        self.assertEqual(len(self.transport.calls), 2)

    def test_throttle_lock_is_bounded_and_does_not_retain_refresh_lease(self):
        self.connected()
        with self.database() as conn:
            conn.execute('INSERT INTO socialmei.auth_limites(chave) VALUES(%s)', (digest('global:instagram-token-refresh'),))
        with self.database() as blocker:
            blocker.execute('SELECT * FROM socialmei.auth_limites WHERE chave=%s FOR UPDATE', (digest('global:instagram-token-refresh'),))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.refresh)
                try:
                    result = future.result(5)
                except TimeoutError:
                    blocker.rollback()
                    future.result(5)
                    self.fail('Throttle aguardou mais de 5s mantendo a lease de renovação.')
                finally:
                    blocker.rollback()
        self.assertEqual(result.status_code, 503, result.text)
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.refresh().status_code, 200)

    def test_provider_must_extend_expiration_instead_of_shortening_it(self):
        self.connected()
        previous = self.connection()
        self.transport.lifetime = 1
        self.assertEqual(self.refresh().status_code, 503)
        self.assertEqual(self.connection(), previous)

    def test_role_demotion_during_provider_call_preserves_previous_token(self):
        self.connected()
        previous = self.connection()
        self.transport.block = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.refresh)
            self.assertTrue(self.transport.started.wait(5))
            try:
                with self.database() as conn:
                    conn.execute("UPDATE socialmei.workspace_members SET role='member' WHERE user_id=%s AND workspace_id=%s",
                                 (self.identity['id'], self.identity['workspace_id']))
            finally:
                self.transport.block.set()
            self.assertEqual(future.result(5).status_code, 403)
        self.assertEqual(self.connection(), previous)

    def test_key_rotation_during_http_cannot_be_overwritten(self):
        self.connected()
        self.transport.block = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.refresh)
            self.assertTrue(self.transport.started.wait(5))
            try:
                self.assertEqual(self.post('/connection/rotate-key').status_code, 200)
                rotated = self.connection()
            finally:
                self.transport.block.set()
            self.assertEqual(future.result(5).status_code, 409)
        self.assertEqual(self.connection(), rotated)

    def test_admin_can_refresh_and_failure_log_contains_no_token(self):
        self.connected()
        with self.database() as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='admin' WHERE user_id=%s AND workspace_id=%s",
                         (self.identity['id'], self.identity['workspace_id']))
        self.assertEqual(self.refresh().status_code, 200)
        with self.database() as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '2 days',expires_at=NOW()+INTERVAL '58 days' WHERE workspace_id=%s", (self.identity['workspace_id'],))
        self.transport.fail = True
        with self.assertLogs('socialmei.instagram', level='WARNING') as logs:
            self.assertEqual(self.refresh().status_code, 503)
        text = '\n'.join(logs.output)
        for private in ('synthetic-refreshed-token', 'synthetic-long-token', 'private-provider-token'):
            self.assertNotIn(private, text)
