import os
import unittest
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
import test_account_auth as accounts


class AuditContracts(unittest.TestCase):
    def test_missing_session_does_not_read_history(self):
        with patch.dict(os.environ, accounts.ENV), patch('workspace_audit.connect', side_effect=AssertionError('database')):
            self.assertEqual(TestClient(accounts.app, base_url=accounts.ORIGIN).get('/api/v1/audit/workspace').status_code, 401)


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class AuditDatabase(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited

    def generate(self):
        self.other = self.register('audit-other@example.test')
        owner = self.admin_client
        value = owner.get('/api/v1/auth/me').json()
        owner.headers['X-SocialMEI-Identity'] = f"{value['usuario']['id']}:{value['negocio']['id']}"
        owner.headers['X-SocialMEI-CSRF'] = value['csrf_token']
        grant = owner.post('/api/v1/team/members', json={'email': 'audit-other@example.test', 'role': 'member'})
        self.assertEqual(grant.status_code, 200, grant.text)
        export = owner.post('/api/v1/exports/produtos', json={})
        self.assertEqual(export.status_code, 200, export.text)
        self.assertEqual(self.other.post('/api/v1/exports/clientes', json={}).status_code, 200)

    def test_committed_operations_are_visible_without_cross_workspace_or_account_events(self):
        self.generate()
        response = self.admin_client.get('/api/v1/audit/workspace')
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual([item['action'] for item in data['items']], ['CSV de produtos gerado', 'Acesso à equipe concedido'])
        self.assertTrue(all(item['actor'] for item in data['items']))
        self.assertNotIn('audit-other@example.test', response.text)
        self.assertNotIn('cadastro', response.text)
        self.assertNotIn('csrf', response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        other = self.other.get('/api/v1/audit/workspace').json()
        self.assertEqual([r['action'] for r in other['items']], ['CSV de clientes gerado'])

    def test_filters_keyset_limits_and_private_errors(self):
        self.generate()
        path = '/api/v1/audit/workspace'
        first = self.admin_client.get(path+'?limit=1').json()
        last = self.admin_client.get(path+f'?limit=1&before={first["next_before"]}').json()
        self.assertEqual(last['items'][0]['kind'], 'team')
        self.assertIsNone(last['next_before'])
        self.assertEqual(len(self.admin_client.get(path+'?kind=exports').json()['items']), 1)
        self.assertEqual(self.admin_client.get(path+'?start=2000-01-01&end=2000-01-01').json()['items'], [])
        for query in ['?limit=51', '?before=0', '?kind=login', '?start=2026-01-01']:
            self.assertEqual(self.admin_client.get(path+query).status_code, 422)
        with patch('workspace_audit.connect', side_effect=psycopg.OperationalError('secret detail')):
            response = self.admin_client.get(path)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret detail', response.text)

    def test_roles_and_revoked_session_are_enforced_in_backend(self):
        path = '/api/v1/audit/workspace'
        for role in ['member', 'viewer', 'report_viewer', 'admin']:
            with psycopg.connect(accounts.DB) as conn:
                conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s', (role, self.admin_id))
            self.assertEqual(self.admin_client.get(path).status_code, 200 if role == 'admin' else 403)
        self.admin_client.post('/api/v1/auth/logout', json={})
        self.assertEqual(self.admin_client.get(path).status_code, 401)

    def test_booking_policy_audit_is_bound_to_its_original_business(self):
        self.generate()
        result = self.admin_client.put('/api/v1/agenda/channel-booking',
            json={'expected_revision': 0, 'policy': {'enabled': False, 'timezone': 'America/Fortaleza'}})
        self.assertEqual(result.status_code, 200, result.text)
        # Old unscoped rows must never be attributed through the actor's current workspace.
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'channel_booking_configured')", (self.admin_id,))
        own = self.admin_client.get('/api/v1/audit/workspace?kind=settings').json()
        self.assertEqual([item['action'] for item in own['items']], ['Horários de agendamento configurados'])
        foreign = self.other.get('/api/v1/audit/workspace?kind=settings').json()
        self.assertEqual(foreign['items'], [])


if __name__ == '__main__':
    unittest.main()
