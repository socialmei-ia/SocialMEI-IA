"""Workspace profile audit commits atomically without retaining profile contents."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg
import test_account_auth as accounts
from test_workspace_profile import PROFILE_PATH, PREF_PATH, payload
from workspace_profile import default_preferences


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class ProfileAuditDatabase(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited

    def events(self, client=None):
        response = (client or self.admin_client).get('/api/v1/audit/workspace?kind=settings')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['items']

    def test_creation_edit_and_conflict_have_only_committed_events_without_profile_values(self):
        self.assertEqual(self.admin_client.patch(PROFILE_PATH, json=payload()).status_code, 200)
        self.assertEqual(self.admin_client.patch(PROFILE_PATH, json=payload()).status_code, 409)
        self.assertEqual(self.admin_client.patch(PROFILE_PATH, json=payload(revision=1)).status_code, 200)
        rows = self.events()
        self.assertEqual([row['action'] for row in rows], ['Perfil do negócio atualizado', 'Perfil do negócio configurado'])
        self.assertTrue(all(row['actor'] and row['target'] is None for row in rows))
        self.assertNotIn('Analysis', str(rows))
        self.assertNotIn('example.com', str(rows))
        self.assertNotIn('Technical services', str(rows))
        with psycopg.connect(accounts.DB) as conn:
            actions = conn.execute("SELECT acao FROM socialmei.auth_auditoria WHERE acao LIKE 'perfil:%'").fetchall()
        self.assertEqual(len(actions), 2)

    def test_failed_audit_rolls_back_both_initial_profile_and_revision_update(self):
        for revision in (0, 1):
            with patch('workspace_profile.audit_profile', side_effect=psycopg.OperationalError('private database detail')):
                response = self.admin_client.patch(PROFILE_PATH, json=payload(revision=revision))
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private database detail', response.text)
            self.assertEqual(self.admin_client.get(PROFILE_PATH).json()['revision'], revision)
            self.assertEqual(len(self.events()), revision)
            self.assertEqual(self.admin_client.patch(PROFILE_PATH, json=payload(revision=revision)).status_code, 200)
        self.assertEqual(len(self.events()), 2)

    def test_concurrent_writers_only_audit_the_winner(self):
        clients = [self.login('admin@example.com') for _ in range(2)]
        for revision in (0, 1):
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda client: client.patch(PROFILE_PATH, json=payload(revision=revision)), clients))
            self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
            self.assertEqual(len(self.events()), revision + 1)

    def test_other_business_preferences_and_rejected_writes_do_not_pollute_history(self):
        other = self.register('other-profile@example.test')
        self.assertEqual(other.patch(PROFILE_PATH, json=payload()).status_code, 200)
        self.assertEqual(self.events(), [])
        self.assertEqual(len(self.events(other)), 1)
        self.assertEqual(self.admin_client.patch(PREF_PATH, json=payload(default_preferences(), field='preferences')).status_code, 200)
        self.assertEqual(self.events(), [])
        self.assertEqual(self.admin_client.patch(PROFILE_PATH, json=payload(), headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.events(), [])
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='member' WHERE user_id=%s", (self.admin_id,))
        self.assertEqual(self.admin_client.patch(PROFILE_PATH, json=payload()).status_code, 403)
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM socialmei.auth_auditoria WHERE user_id=%s AND acao LIKE 'perfil:%%'", (self.admin_id,)).fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
