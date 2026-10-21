"""Preparation-only setup; no account credentials or transport activation."""
import copy
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from app import app
from integration_setup import InstagramSetup, SetupWrite, envelope
from test_account_auth import ENV, ORIGIN, HEADERS, DB, AccountDatabaseTests

PATH = '/api/v1/integrations/setup'
SETUP = {'username': '@Loja.teste', 'account_type': 'business',
         'meta_app_status': 'exists', 'test_participants': ['Equipe1', '@equipe1', 'equipe2'],
         'reply_mode': 'review'}


class SetupContracts(unittest.TestCase):
    def test_normalized_preparation_never_claims_connection(self):
        value = InstagramSetup(**SETUP).normalized()
        self.assertEqual(value['username'], 'loja.teste')
        self.assertEqual(value['test_participants'], ['equipe1', 'equipe2'])
        result = envelope(12, 1, value)
        self.assertFalse(result['connected'])
        self.assertEqual(result['transport'], 'none')
        self.assertFalse(result['readiness']['can_send'])
        self.assertFalse(result['readiness']['can_receive'])
        self.assertFalse(result['readiness']['can_publish'])
        self.assertTrue(result['readiness']['blockers'])

    def test_credentials_activation_and_invalid_inputs_are_rejected(self):
        invalid = [dict(SETUP, access_token='private-token'), dict(SETUP, password='private'),
                   dict(SETUP, connected=True), dict(SETUP, reply_mode='automatic'),
                   dict(SETUP, username='https://example.test'),
                   dict(SETUP, test_participants=['*']), dict(SETUP, test_participants=['a'] * 11)]
        for value in invalid:
            with self.subTest(fields=list(value)):
                with self.assertRaises(ValidationError):
                    InstagramSetup(**value)
        for revision in (True, -1, '0'):
            with self.assertRaises(ValidationError):
                SetupWrite(expected_revision=revision, instagram=SETUP)

    def test_disabled_auth_fails_before_database(self):
        client = TestClient(app, base_url=ORIGIN)
        with patch.dict(os.environ, {**ENV, 'SOCIALMEI_AUTH_ENABLED': 'false'}), patch('integration_setup.connect', side_effect=AssertionError('unexpected DB')):
            self.assertEqual(client.get(PATH).status_code, 503)


@unittest.skipUnless(DB, 'TEST_DATABASE_URL not configured')
class SetupDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(AccountDatabaseTests.setUpClass.__func__)
    setUp = AccountDatabaseTests.setUp
    login = AccountDatabaseTests.login
    invited = AccountDatabaseTests.invited
    register = AccountDatabaseTests.register

    def test_persistence_two_sessions_cas_and_other_workspace(self):
        first = self.admin_client.get(PATH)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['revision'], 0)
        body = {'expected_revision': 0, 'instagram': copy.deepcopy(SETUP)}
        saved = self.admin_client.put(PATH, json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        second = self.login('admin@example.com')
        self.assertEqual(second.get(PATH).json(), saved.json())
        self.assertEqual(second.put(PATH, json=body).status_code, 409)
        other = self.register('other-setup@example.test')
        self.assertEqual(other.get(PATH).json()['revision'], 0)
        self.assertEqual(other.get(PATH).json()['instagram']['username'], '')

    def test_roles_auth_csrf_query_and_secret_refusal(self):
        import psycopg
        body = {'expected_revision': 0, 'instagram': copy.deepcopy(SETUP)}
        anonymous = TestClient(app, base_url=ORIGIN, headers=HEADERS)
        self.assertEqual(anonymous.get(PATH).status_code, 401)
        self.assertEqual(anonymous.put(PATH, json=body).status_code, 401)
        no_csrf = TestClient(app, base_url=ORIGIN, headers=HEADERS)
        no_csrf.cookies.update(self.admin_client.cookies)
        self.assertEqual(no_csrf.put(PATH, json=body).status_code, 403)
        self.assertEqual(self.admin_client.put(PATH, json=body, headers={'Origin': 'https://wrong.test'}).status_code, 403)
        for role in ('member', 'viewer'):
            with psycopg.connect(DB) as conn:
                conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s', (role, self.admin_id))
            self.assertEqual(self.admin_client.get(PATH).status_code, 200)
            self.assertEqual(self.admin_client.put(PATH, json=body).status_code, 403)
        with psycopg.connect(DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='owner' WHERE user_id=%s", (self.admin_id,))
        self.assertEqual(self.admin_client.get(PATH + '?workspace_id=2').status_code, 422)
        body['instagram']['access_token'] = 'do-not-echo-this-secret'
        result = self.admin_client.put(PATH, json=body)
        self.assertEqual(result.status_code, 422)
        self.assertNotIn('do-not-echo-this-secret', result.text)


if __name__ == '__main__':
    unittest.main()
