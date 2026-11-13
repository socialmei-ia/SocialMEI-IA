"""Explicit onboarding catalog; synthetic records in a disposable database only."""
from concurrent.futures import ThreadPoolExecutor
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from business_start import CatalogConfirm, catalog_state
import test_account_auth as accounts

PATH = '/api/v1/onboarding/catalog'


class SetupContracts(unittest.TestCase):
    def test_services_require_confirmed_price_duration_and_unique_names(self):
        base = {'operation_id': str(uuid4()), 'expected_revision': 0, 'confirmed': True}
        for items in ([{'nome': 'Teste', 'tipo': 'Serviço', 'preco': 20}],
                      [{'nome': 'Teste', 'tipo': 'Produto'}],
                      [{'nome': 'Teste', 'tipo': 'Produto', 'preco': 1}] * 2):
            with self.assertRaises(ValueError):
                CatalogConfirm.model_validate({**base, 'items': items})
        with self.assertRaises(ValueError):
            CatalogConfirm.model_validate({**base, 'confirmed': False,
                'items': [{'nome': 'Teste', 'tipo': 'Produto', 'preco': 1}]})

    def test_anonymous_setup_does_not_open_database(self):
        with patch.dict(os.environ, accounts.ENV), patch('business_start.connect', side_effect=AssertionError('database')):
            client = TestClient(accounts.app, base_url=accounts.ORIGIN)
            self.assertEqual(client.get(PATH).status_code, 401)

    def test_malformed_saved_configuration_fails_closed(self):
        for value in ({'revision': True, 'items': []}, {'revision': 0, 'items': [{'nome': ''}]},
                      {'revision': 1, 'items': [], 'receipt': {'operation_id': 'invalid'}}):
            with self.assertRaises(Exception) as caught:
                catalog_state({'configuracao': {'onboarding_catalog': value}})
            self.assertEqual(caught.exception.status_code, 503)


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class SetupDatabase(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited

    def packet(self, **changes):
        return {'operation_id': str(uuid4()), 'expected_revision': 0, 'confirmed': True,
                'items': [{'nome': 'Serviço escolhido', 'tipo': 'Serviço', 'preco': '79.90', 'duracao_minutos': 45},
                          {'nome': 'Produto escolhido', 'tipo': 'Produto', 'preco': 12}], **changes}

    def test_draft_resume_creates_nothing_until_explicit_confirmation_and_receipt_is_durable(self):
        draft = {'expected_revision': 0, 'items': [{'nome': 'Serviço escolhido', 'tipo': 'Serviço', 'preco': None}]}
        result = self.admin_client.put(PATH, json=draft)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.admin_client.get('/api/v1/produtos').json(), [])
        resumed = self.admin_client.get(PATH).json()
        self.assertEqual(resumed['items'][0]['nome'], 'Serviço escolhido')
        self.assertIsNone(resumed['items'][0]['preco'])
        packet = self.packet(expected_revision=1)
        response = self.admin_client.post(PATH, json=packet)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['registered'])
        self.assertEqual(len(self.admin_client.get('/api/v1/produtos').json()), 2)
        self.assertEqual(self.admin_client.post(PATH, json=packet).json(), response.json())
        self.assertEqual(self.admin_client.post(PATH, json={**packet, 'operation_id': str(uuid4())}).status_code, 409)
        self.assertEqual(self.admin_client.post(PATH, json={**packet, 'items': packet['items'][:1]}).status_code, 409)
        status = self.admin_client.get('/api/v1/onboarding/status').json()
        self.assertTrue(status['setup']['catalog_confirmed'])
        self.assertFalse(status['setup']['hours_configured'])
        self.assertEqual(status['counts']['services'], 1)
        self.assertEqual(status['counts']['products'], 1)

    def test_two_businesses_and_roles_cannot_share_or_modify_setup(self):
        packet = self.packet()
        first = self.admin_client.post(PATH, json=packet)
        self.assertEqual(first.status_code, 200, first.text)
        other = self.register('other-setup@example.test')
        self.assertIsNone(other.get(PATH).json()['receipt'])
        self.assertEqual(other.post(PATH, json=packet).status_code, 200)
        first_ids = {p['id'] for p in self.admin_client.get('/api/v1/produtos').json()}
        other_ids = {p['id'] for p in other.get('/api/v1/produtos').json()}
        self.assertFalse(first_ids & other_ids)
        for role in ('member', 'viewer', 'report_viewer'):
            with psycopg.connect(accounts.DB) as conn:
                conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s', (role, self.admin_id))
            self.assertEqual(self.admin_client.get(PATH).status_code, 403)

    def test_concurrent_confirmation_creates_only_one_catalog(self):
        packet = self.packet()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.admin_client.post(PATH, json=packet), range(2)))
        self.assertEqual([r.status_code for r in responses], [200, 200], [r.text for r in responses])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(len(self.admin_client.get('/api/v1/produtos').json()), 2)

    def test_partial_persistence_rolls_back_and_private_errors_are_sanitized(self):
        import business_start
        real = business_start.insert_product
        calls = []
        def failing(cur, workspace, item):
            calls.append(item.nome)
            if len(calls) > 1:
                raise psycopg.OperationalError('private database password')
            return real(cur, workspace, item)
        packet = self.packet()
        with patch('business_start.insert_product', side_effect=failing):
            response = self.admin_client.post(PATH, json=packet)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private database', response.text)
        self.assertEqual(self.admin_client.get('/api/v1/produtos').json(), [])
        self.assertIsNone(self.admin_client.get(PATH).json()['receipt'])
        self.assertEqual(self.admin_client.post(PATH, json=packet).status_code, 200)

    def test_stale_draft_duplicate_existing_offer_and_origin_are_rejected(self):
        draft = {'expected_revision': 0, 'items': []}
        self.assertEqual(self.admin_client.put(PATH, json=draft).status_code, 200)
        self.assertEqual(self.admin_client.put(PATH, json=draft).status_code, 409)
        self.assertEqual(self.admin_client.post(PATH, json=self.packet()).status_code, 409)
        created = self.admin_client.post('/api/v1/produtos', json=self.packet()['items'][0])
        self.assertEqual(created.status_code, 201, created.text)
        result = self.admin_client.post(PATH, json=self.packet(expected_revision=1))
        self.assertEqual(result.status_code, 409)
        self.assertEqual(len(self.admin_client.get('/api/v1/produtos').json()), 1)
        result = self.admin_client.put(PATH, json={'expected_revision': 1, 'items': []}, headers={'Origin': 'https://evil.example.test'})
        self.assertEqual(result.status_code, 403)


if __name__ == '__main__':
    unittest.main()
