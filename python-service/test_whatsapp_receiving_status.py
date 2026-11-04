"""Receipt evidence uses real isolated persistence, never provider or production I/O."""
import json
import os
import unittest
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from app import app
import test_account_auth as accounts
import test_waha_ingress as fixtures
from waha_ingress import WahaBinding, WahaIngressService

PATH = '/api/v1/whatsapp/receiving-status'


class ReceivingStatusGuards(unittest.TestCase):
    def test_no_session_cannot_open_evidence_database(self):
        with patch.dict(os.environ, accounts.ENV), patch(
                'whatsapp_receiving_status.connect', side_effect=AssertionError('database')) as db:
            self.assertEqual(TestClient(app, base_url=accounts.ORIGIN).get(PATH).status_code, 401)
            db.assert_not_called()


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL not configured')
class ReceivingStatusDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        flags = patch.dict(os.environ, fixtures.FLAGS)
        flags.start()
        self.addCleanup(flags.stop)
        workspace = self.admin_client.identity['negocio']['id']
        with psycopg.connect(accounts.DB) as conn:
            channel = conn.execute(
                "INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,"
                "ingress_provisioned,ativo) VALUES(%s,'status-test','default','111@c.us',true,true) RETURNING id",
                (workspace,),
            ).fetchone()[0]
        self.binding = WahaBinding(instance='status-test', session='default', account_id='111@c.us',
                                   workspace_id=workspace, channel_id=channel, hmac_key=fixtures.KEY)
        self.service = WahaIngressService({'status-test': self.binding})

    def receive(self, marker='test-one'):
        body = fixtures.raw(fixtures.payload(marker))
        return self.service.receive('status-test', body, fixtures.sign(body), 'sha512')

    def evidence(self, client=None):
        response = (client or self.admin_client).get(PATH)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        return response.json()

    def test_empty_history_is_not_connection_or_session_evidence(self):
        value = self.evidence()
        self.assertEqual(value['message_count'], 0)
        self.assertEqual(value['conversation_count'], 0)
        self.assertIsNone(value['last_persisted_at'])
        self.assertFalse(value['historical_receiving_confirmed'])
        self.assertFalse(value['session_live_verified'])
        self.assertFalse(value['sending_available'])

    def test_signed_persisted_receipts_are_deduplicated_and_scoped(self):
        foreign = self.register('other-business@example.test')
        self.assertEqual(self.receive()['processed'], 1)
        self.assertEqual(self.receive()['duplicates'], 1)
        self.assertEqual(self.receive('test-two')['processed'], 1)
        value = self.evidence()
        self.assertEqual(value['message_count'], 2)
        self.assertEqual(value['conversation_count'], 1)
        self.assertTrue(value['historical_receiving_confirmed'])
        self.assertIsNotNone(value['last_persisted_at'])
        self.assertFalse(value['session_live_verified'])
        self.assertFalse(value['sending_available'])
        raw = json.dumps(value)
        for private in (fixtures.KEY, '111@c.us', '222@c.us', 'Original', 'test-one'):
            self.assertNotIn(private, raw)
        self.assertEqual(self.evidence(foreign)['message_count'], 0)
        self.assertNotEqual(self.evidence(foreign)['workspace_id'], value['workspace_id'])
        with patch.dict(os.environ, {'SOCIALMEI_WAHA_INGRESS_MODE': 'disabled'}):
            self.assertEqual(self.evidence()['message_count'], 2)

    def test_synthetic_messages_do_not_become_receiving_evidence(self):
        workspace = self.binding.workspace_id
        with psycopg.connect(accounts.DB) as conn:
            conversation = conn.execute(
                'INSERT INTO socialmei.me_conversations(workspace_id,channel,account_ref,contact_ref,contact_name) '
                "VALUES(%s,'whatsapp','synthetic:test','synthetic:contact','Synthetic') RETURNING id",
                (workspace,),
            ).fetchone()[0]
            conn.execute(
                'INSERT INTO socialmei.me_messages(workspace_id,conversation_id,external_message_id,'
                'fingerprint,conversation_revision,text) VALUES(%s,%s,%s,%s,1,%s)',
                (workspace, conversation, 'synthetic-only', 'a'*64, 'Fictitious isolated text'),
            )
        self.assertEqual(self.evidence()['message_count'], 0)

    def test_foreign_query_roles_revocation_and_database_failure_fail_closed(self):
        with patch('whatsapp_receiving_status.connect') as db:
            self.assertEqual(self.admin_client.get(PATH+'?workspace_id=9999').status_code, 422)
            db.assert_not_called()
        for role in ('owner', 'admin', 'member', 'viewer'):
            with psycopg.connect(accounts.DB) as conn:
                conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s',
                             (role, self.admin_id))
            self.assertEqual(self.admin_client.get(PATH).status_code, 200)
        with patch('whatsapp_receiving_status.connect', side_effect=psycopg.OperationalError('private-detail')):
            response = self.admin_client.get(PATH)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private-detail', response.text)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='report_viewer' WHERE user_id=%s",
                         (self.admin_id,))
        self.assertEqual(self.admin_client.get(PATH).status_code, 403)
        self.assertEqual(self.admin_client.post('/api/v1/auth/logout', json={}).status_code, 204)
        self.assertEqual(self.admin_client.get(PATH).status_code, 401)


if __name__ == '__main__':
    unittest.main()
