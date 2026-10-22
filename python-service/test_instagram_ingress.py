"""Instagram-shaped lab preparation is not a Meta webhook or real transport."""
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import app
import test_account_auth as accounts
from channel_ingress import sign_fixture, verify_instagram_fixture

PATH = '/internal/channel-ingress/instagram-fixture'
STATUS = '/api/v1/channel-lab/instagram/status'
MODE = {'SOCIALMEI_CHANNEL_INGRESS_MODE': 'fixture',
        'SOCIALMEI_CHANNEL_INGRESS_TEST_KEY': 'isolated-instagram-fixture-key-123456789',
        'SOCIALMEI_MESSAGE_ENRICHMENT_MODE': 'stub',
        'SOCIALMEI_MESSAGE_ENRICHMENT_TEST_KEY': 'isolated-enrichment-fixture-key-123456789',
        'SOCIALMEI_INSTAGRAM_MODE': 'simulation'}


def event(account_id=None, **changes):
    value = {'schema_version': 1, 'event_id': str(uuid4()), 'timestamp': int(time.time()),
             'account_id': account_id or str(uuid4()), 'kind': 'incoming_text',
             'sender_ref': 'fixture-participant', 'sender_name': 'Pessoa fictícia',
             'message_id': 'fixture-message-1', 'text': 'O produto fictício está disponível?'}
    return {**value, **changes}


class InstagramIngressContracts(unittest.TestCase):
    def test_signed_strict_event_and_protocol_separation(self):
        with patch.dict(os.environ, {**accounts.ENV, **MODE}):
            value = event()
            self.assertEqual(str(verify_instagram_fixture(sign_fixture(value)).account_id), value['account_id'])
            for changes in ({'workspace_id': 9}, {'kind': 'outgoing_text'}, {'kind': 'image'},
                            {'sender_ref': 'real-account'}, {'text': ''}, {'schema_version': True},
                            {'timestamp': str(value['timestamp'])}, {'account_id': 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'},
                            {'text': 'é' * 4097}):
                with self.subTest(changes=changes), self.assertRaises(HTTPException):
                    verify_instagram_fixture(sign_fixture({**value, **changes}))
            wrong = sign_fixture(value)
            wrong['text'] = 'Conteúdo alterado'
            with self.assertRaises(HTTPException) as error:
                verify_instagram_fixture(wrong)
            self.assertEqual(error.exception.status_code, 403)
            with self.assertRaises(HTTPException) as error:
                verify_instagram_fixture(sign_fixture({**value, 'timestamp': value['timestamp'] - 121}))
            self.assertEqual(error.exception.status_code, 409)
            from test_channel_ingress import event as waha_event
            with self.assertRaises(HTTPException):
                verify_instagram_fixture(sign_fixture(waha_event()))

    def test_disabled_or_non_simulation_fails_before_database(self):
        for options in ({'SOCIALMEI_INSTAGRAM_MODE': 'disabled'},
                        {'SOCIALMEI_INSTAGRAM_MODE': 'live'},
                        {'SOCIALMEI_CHANNEL_INGRESS_MODE': 'disabled'},
                        {'SOCIALMEI_AUTH_ENABLED': 'false'},
                        {'SOCIALMEI_SHARED_DATA_ENABLED': 'false'}):
            with self.subTest(options=options), patch.dict(os.environ, {**accounts.ENV, **MODE, **options}), patch('message_enrichment.connect', side_effect=AssertionError('DB accessed')):
                response = TestClient(app, base_url=accounts.ORIGIN).post(PATH, json=sign_fixture(event()))
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_json_limits_duplicates_queries_and_signature_before_storage(self):
        with patch.dict(os.environ, {**accounts.ENV, **MODE}), patch('message_enrichment.connect', side_effect=AssertionError('DB accessed')):
            client = TestClient(app, base_url=accounts.ORIGIN)
            for body, content_type in [('{}', 'text/plain'), ('{"kind":1,"kind":2}', 'application/json'), ('a' * 16385, 'application/json')]:
                response = client.post(PATH, content=body, headers={'Content-Type': content_type})
                self.assertEqual(response.status_code, 422)
            self.assertEqual(client.post(PATH + '?workspace_id=9', json=sign_fixture(event())).status_code, 422)
            value = sign_fixture(event()); value['signature'] = '0' * 64
            self.assertEqual(client.post(PATH, json=value).status_code, 403)


@unittest.skipUnless(accounts.DB, 'TEST_DATABASE_URL not configured')
class InstagramIngressDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        mode = patch.dict(os.environ, MODE); mode.start(); self.addCleanup(mode.stop)
        self.internal = TestClient(app, base_url=accounts.ORIGIN)

    def account(self, client=None):
        response = (client or self.admin_client).post('/api/v1/instagram/simulation/accounts', json={'label': 'Instagram fictício'})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def deliver(self, value):
        return self.internal.post(PATH, json=sign_fixture(value))

    def test_two_accounts_and_businesses_no_contact_merge_and_no_crm_creation(self):
        first_id = self.account(); other = self.register('instagram-other@example.test')
        second_id = self.account(other)
        a = self.deliver(event(first_id)); b = self.deliver(event(second_id))
        self.assertEqual(a.status_code, 200, a.text); self.assertEqual(b.status_code, 200, b.text)
        self.assertNotEqual(a.json()['conversation_id'], b.json()['conversation_id'])
        second_session = self.login('admin@example.com')
        rows = second_session.get('/api/v1/message-enrichment/conversations').json()['items']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['channel'], 'instagram')
        self.assertEqual(rows[0]['messages'][0]['text'], 'O produto fictício está disponível?')
        self.assertEqual(other.get('/api/v1/message-enrichment/conversations/%s/enrichments' % a.json()['conversation_id']).status_code, 404)
        self.assertEqual(second_session.get('/api/v1/clientes').json(), [])
        for result in (a.json(), b.json()):
            self.assertEqual(result['transport'], 'none'); self.assertFalse(result['sent'])
        same_business_id = self.account()
        c = self.deliver(event(same_business_id))
        self.assertNotEqual(c.json()['conversation_id'], a.json()['conversation_id'])
        d = self.deliver(event(first_id, sender_ref='fixture-another-person', message_id='fixture-message-2'))
        self.assertNotEqual(d.json()['conversation_id'], a.json()['conversation_id'])

    def test_replay_concurrency_alias_conflict_and_single_revision(self):
        value = event(self.account())
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.deliver(value), range(2)))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(responses[0].json()['message_id'], responses[1].json()['message_id'])
        alias = {**value, 'event_id': str(uuid4())}
        self.assertEqual(self.deliver(alias).json()['message_id'], responses[0].json()['message_id'])
        self.assertEqual(self.deliver({**alias, 'text': 'Outro conteúdo'}).status_code, 409)
        rows = self.admin_client.get('/api/v1/message-enrichment/conversations').json()['items']
        self.assertEqual(rows[0]['revision'], 1); self.assertEqual(len(rows[0]['messages']), 1)

    def test_unknown_or_ambiguous_account_refuses_instead_of_guessing_owner(self):
        self.assertEqual(self.deliver(event()).status_code, 404)
        account_id = self.account(); other = self.register('ambiguous-instagram@example.test')
        with psycopg.connect(accounts.DB) as conn:
            conn.execute('INSERT INTO socialmei.instagram_sim_accounts(workspace_id,id,label) VALUES(%s,%s,%s)', (other.identity['negocio']['id'], account_id, 'Colisão fictícia'))
        self.assertEqual(self.deliver(event(account_id)).status_code, 409)
        self.assertEqual(self.admin_client.get('/api/v1/message-enrichment/conversations').json()['items'], [])
        self.assertEqual(other.get('/api/v1/message-enrichment/conversations').json()['items'], [])

    def test_status_auth_roles_and_review_never_report_real_connection(self):
        self.assertEqual(self.internal.get(STATUS).status_code, 401)
        account_id = self.account()
        response = self.admin_client.get(STATUS)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        status = response.json()
        self.assertEqual(status['workspace_id'], self.admin_client.identity['negocio']['id'])
        self.assertEqual(status['account_source'], 'instagram_simulation')
        self.assertTrue(status['fixture_ingress_available'])
        for key in ('connected', 'can_receive_real', 'can_send', 'can_publish'):
            self.assertFalse(status[key])
        self.assertNotIn('key', str(status).lower())
        for options in ({'SOCIALMEI_CHANNEL_INGRESS_MODE': 'disabled'},
                        {'SOCIALMEI_INSTAGRAM_MODE': 'disabled'},
                        {'SOCIALMEI_CHANNEL_INGRESS_TEST_KEY': ''}):
            with patch.dict(os.environ, options):
                unavailable = self.admin_client.get(STATUS)
                self.assertEqual(unavailable.status_code, 200)
                self.assertEqual(unavailable.json()['mode'], 'disabled')
                self.assertFalse(unavailable.json()['fixture_ingress_available'])
                self.assertFalse(unavailable.json()['connected'])
        self.assertEqual(self.admin_client.get(STATUS + '?workspace_id=999').status_code, 422)
        for role in ('member', 'viewer'):
            with psycopg.connect(accounts.DB) as conn:
                conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s', (role, self.admin_id))
            self.assertEqual(self.admin_client.get(STATUS).status_code, 200)
            self.assertEqual(self.admin_client.post('/api/v1/instagram/simulation/accounts', json={'label': 'Bloqueado'}).status_code, 403)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='owner' WHERE user_id=%s", (self.admin_id,))
        incoming = self.deliver(event(account_id)).json()
        result = self.admin_client.post('/api/v1/message-enrichment/messages/%s/enrich' % incoming['message_id'], json={'schema_version': 1, 'operation_id': str(uuid4()), 'expected_revision': 1})
        self.assertEqual(result.status_code, 200, result.text)
        job = result.json()
        reviewed = self.admin_client.patch('/api/v1/message-enrichment/jobs/' + job['id'] + '/review', json={'schema_version': 1, 'expected_revision': job['revision'], 'decision': 'approved', 'suggested_reply': 'Rascunho revisado, sem envio.'})
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()['transport'], 'none')


if __name__ == '__main__':
    unittest.main()
