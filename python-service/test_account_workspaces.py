"""Account-owned workspace creation using real disposable PostgreSQL only."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from app import app
from account_auth import COOKIE, WorkspaceCreate
import test_account_auth as accounts
from test_account_auth import DB, ENV, HEADERS, ORIGIN

PATH = '/api/v1/auth/workspaces'


def body(name='SorriaOdonto', segment='Serviços odontológicos', key=None):
    return {'nome': name, 'segmento': segment, 'idempotency_key': str(key or uuid4())}


class WorkspaceContractTests(unittest.TestCase):
    def test_names_and_segment_are_required_and_owner_fields_forbidden(self):
        valid = body()
        for change in ({'nome': ' '}, {'segmento': '\x00'}, {'nome': 123},
                       {'segmento': 'x'*121}, {'user_id': 5}, {'role': 'owner'},
                       {'idempotency_key': 'not-uuid'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                WorkspaceCreate(**{**valid, **change})
        normalized = WorkspaceCreate(**body('  Minha   empresa  '))
        self.assertEqual(normalized.nome, 'Minha empresa')

    def test_unauthenticated_creation_cannot_reach_database(self):
        with patch.dict(os.environ, ENV), patch('account_auth.connect', side_effect=AssertionError('database')):
            client = TestClient(app, base_url=ORIGIN, headers=HEADERS)
            self.assertEqual(client.post(PATH, json=body()).status_code, 401)


@unittest.skipUnless(DB, 'TEST_DATABASE_URL not configured')
class WorkspaceCreationTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login

    def scoped(self, client):
        identity = client.get('/api/v1/auth/me').json()
        client.headers['X-SocialMEI-Identity'] = f"{identity['usuario']['id']}:{identity['negocio']['id']}"
        return client

    def create(self, client, data=None):
        return client.post(PATH, json=data or body())

    def test_one_user_creates_two_businesses_and_switches_without_login(self):
        client = self.scoped(self.admin_client)
        first = self.create(client)
        second = self.create(client, body('She Style', 'Moda feminina'))
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        ids = {first.json()['negocio']['id'], second.json()['negocio']['id']}
        self.assertEqual(len(ids), 2)
        self.assertEqual(first.json()['papel'], 'owner')
        listed = client.get(PATH).json()
        self.assertTrue(ids.issubset({item['id'] for item in listed['items']}))
        self.assertEqual(listed['active_workspace_id'], client.identity['negocio']['id'])
        switched = client.post(PATH+'/switch', json={'workspace_id': second.json()['negocio']['id']})
        self.assertEqual(switched.status_code, 200, switched.text)
        self.assertEqual(switched.json()['usuario']['id'], self.admin_id)
        self.assertEqual(switched.json()['negocio']['id'], second.json()['negocio']['id'])
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.users').fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM socialmei.workspace_members WHERE role='owner' AND user_id=%s", (self.admin_id,)).fetchone()[0], 3)
            self.assertEqual(conn.execute("SELECT count(*) FROM socialmei.auth_auditoria WHERE acao='negocio_criado'").fetchone()[0], 2)

    def test_retry_is_durable_and_payload_change_rejected(self):
        client = self.scoped(self.admin_client)
        data = body()
        first = self.create(client, data)
        self.assertEqual(first.status_code, 201, first.text)
        second = self.create(self.scoped(self.login('admin@example.com')), data)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertFalse(second.json()['created'])
        self.assertEqual(first.json()['negocio']['id'], second.json()['negocio']['id'])
        self.assertEqual(self.create(client, {**data, 'nome': 'Different'}).status_code, 409)
        self.assertEqual(self.create(client, body('  sorriaodonto ')).status_code, 409)

    def test_concurrent_same_key_and_different_key_duplicate_name(self):
        clients = [self.scoped(self.login('admin@example.com')) for _ in range(2)]
        data = body()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda client: self.create(client, data), clients))
        self.assertEqual(sorted(item.status_code for item in responses), [200, 201])
        self.assertEqual(len({item.json()['negocio']['id'] for item in responses}), 1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda client: self.create(client, body('She Style')), clients))
        self.assertEqual(sorted(item.status_code for item in responses), [201, 409])

    def test_roles_csrf_origin_identity_revocation_and_third_party(self):
        client = self.scoped(self.admin_client)
        self.assertEqual(self.create(client, {**body(), 'user_id': 3}).status_code, 422)
        self.assertEqual(client.post(PATH, json=body(), headers={'X-SocialMEI-CSRF': ''}).status_code, 403)
        self.assertEqual(client.post(PATH, json=body(), headers={'Origin': 'https://foreign.example'}).status_code, 403)
        self.assertEqual(client.post(PATH, json=body(), headers={'X-SocialMEI-Identity': ''}).status_code, 409)
        self.assertEqual(client.post(PATH+'/switch', json={'workspace_id': 999999}).status_code, 403)
        for role in ('member', 'viewer', 'report_viewer'):
            with psycopg.connect(DB) as conn:
                conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s', (role, self.admin_id))
            self.assertEqual(self.create(client).status_code, 403)
        with psycopg.connect(DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='owner' WHERE user_id=%s", (self.admin_id,))
        self.assertEqual(client.post('/api/v1/auth/logout').status_code, 204)
        self.assertEqual(self.create(client).status_code, 401)

    def test_cap_and_failed_transaction_leave_no_orphan_workspace(self):
        client = self.scoped(self.admin_client)
        with patch('account_auth.throttle', side_effect=RuntimeError('isolated injected failure')):
            with self.assertRaises(RuntimeError):
                self.create(client)
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.workspaces').fetchone()[0], 1)
            for index in range(19):
                workspace = conn.execute('INSERT INTO socialmei.workspaces(slug,nome) VALUES(%s,%s) RETURNING id', (f'limit-{index}', f'Business {index}')).fetchone()[0]
                conn.execute("INSERT INTO socialmei.workspace_members VALUES(%s,%s,'owner',NOW())", (workspace, self.admin_id))
        self.assertEqual(self.create(client).status_code, 429)

    def test_throttle_limits_new_businesses_without_breaking_safe_retries(self):
        client = self.scoped(self.admin_client)
        first = body('Business 0')
        self.assertEqual(self.create(client, first).status_code, 201)
        for index in range(1, 10):
            result = self.create(client, body(f'Business {index}'))
            self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(self.create(client, body('Rate limited')).status_code, 429)
        self.assertEqual(self.create(client, first).status_code, 200)

    def test_audit_failure_rolls_back_workspace_and_membership(self):
        client = self.scoped(self.admin_client)
        with psycopg.connect(DB) as conn:
            conn.execute("""CREATE FUNCTION socialmei.reject_workspace_test_audit() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                IF NEW.acao='negocio_criado' THEN RAISE EXCEPTION 'isolated test'; END IF;
                RETURN NEW; END $$""")
            conn.execute("""CREATE TRIGGER reject_workspace_test_audit BEFORE INSERT
                ON socialmei.auth_auditoria FOR EACH ROW
                EXECUTE FUNCTION socialmei.reject_workspace_test_audit()""")
        try:
            result = self.create(client)
            self.assertEqual(result.status_code, 503, result.text)
            with psycopg.connect(DB) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.workspaces').fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.workspace_members').fetchone()[0], 1)
        finally:
            with psycopg.connect(DB) as conn:
                conn.execute('DROP TRIGGER reject_workspace_test_audit ON socialmei.auth_auditoria')
                conn.execute('DROP FUNCTION socialmei.reject_workspace_test_audit()')


if __name__ == '__main__':
    unittest.main()
