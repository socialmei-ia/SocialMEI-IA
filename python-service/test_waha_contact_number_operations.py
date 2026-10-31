"""Metadata changes preserve real-ingress invariants using disposable PostgreSQL fixtures."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
import test_account_auth as fixtures
from test_waha_ingress import KEY, payload, raw, sign
from waha_ingress import WahaBinding, WahaIngressService

spec = importlib.util.spec_from_file_location('contact_number_ops', Path(__file__).resolve().parents[1] / 'tools/team-whatsapp-contact-number.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
namespace = {'__name__': 'contact_number_fixture'}
exec(tool.DB_CODE, namespace)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Disposable PostgreSQL required')
class ContactNumberDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.AccountDatabaseTests.setUpClass.__func__)
    login = fixtures.AccountDatabaseTests.login

    def setUp(self):
        fixtures.AccountDatabaseTests.setUp(self)
        flags = patch.dict(os.environ, {'SOCIALMEI_WAHA_INGRESS_MODE': 'isolated', 'SOCIALMEI_WAHA_LAB_ENVIRONMENT': 'isolated'})
        flags.start(); self.addCleanup(flags.stop)
        with self.db() as c:
            channel = c.execute("INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ativo,ingress_provisioned) VALUES(1,'socialmei-equipe-piloto','01','9915976@c.us',true,true) RETURNING id").fetchone()[0]
        self.binding = WahaBinding('socialmei-equipe-piloto', '01', '9915976@c.us', 1, channel, KEY)
        self.service = WahaIngressService({self.binding.instance: self.binding})
        self.incoming()
        with self.db() as c:
            self.cid = c.execute("SELECT id FROM socialmei.me_conversations WHERE workspace_id=1 AND origin='waha'").fetchone()[0]
        self.before = self.operation('inspect')

    def db(self):
        return psycopg.connect(os.environ['TEST_DATABASE_URL'])

    def incoming(self):
        event = payload('false_opaque-test@lid_' + uuid4().hex)
        event.update(session='01', me={'id': self.binding.account_id})
        event['payload'].update({'from': 'opaque-test@lid', 'to': self.binding.account_id, 'body': 'Synthetic fixture'})
        body = raw(event)
        self.service.receive(self.binding.instance, body, sign(body), 'sha512')

    def operation(self, operation, **fields):
        return namespace['operate']({'operation': operation, 'conversation_id': self.cid, **fields})

    def test_verified_label_changes_revision_without_altering_messages_references_or_channel(self):
        result = self.operation('apply', expected=self.before, desired_name='+5511990001234')
        after = self.operation('inspect')
        self.assertEqual(after['contact_name'], '+5511990001234')
        self.assertEqual(result['revision'], self.before['revision'] + 1)
        for key in ('account_ref', 'contact_ref', 'channel_id', 'channel_revision', 'id'):
            self.assertEqual(after[key], self.before[key])
        with self.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM socialmei.me_messages WHERE workspace_id=1').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT count(*) FROM socialmei.crm_eventos_canal WHERE workspace_id=1').fetchone()[0], 1)

    def test_candidates_exclude_identified_human_labels_and_inactive_channels(self):
        self.assertEqual(self.operation('candidates'), [self.cid])
        with self.db() as c:
            c.execute('UPDATE socialmei.me_conversations SET contact_name=%s WHERE id=%s', ('Human label', self.cid))
        self.assertEqual(self.operation('candidates'), [])
        with self.db() as c:
            c.execute('UPDATE socialmei.me_conversations SET contact_name=%s WHERE id=%s', (tool.GENERIC, self.cid))
            c.execute('UPDATE socialmei.crm_canais SET ativo=false WHERE id=%s', (self.binding.channel_id,))
        self.assertEqual(self.operation('candidates'), [])

    def test_concurrent_message_and_wrong_workspace_expectations_refuse_the_update(self):
        self.incoming()
        with self.assertRaises(ValueError):
            self.operation('apply', expected=self.before, desired_name='+5511990001234')
        current = self.operation('inspect')
        with self.assertRaises(ValueError):
            self.operation('apply', expected={**current, 'workspace_id': 2}, desired_name='+5511990001234')
        self.assertEqual(self.operation('inspect')['contact_name'], tool.GENERIC)

    def test_rollback_preserves_messages_received_after_the_metadata_change(self):
        self.operation('apply', expected=self.before, desired_name='+5511990001234')
        self.incoming()
        after = self.operation('inspect')
        self.operation('rollback', expected=self.before, desired_name=tool.GENERIC, expected_current_name='+5511990001234')
        restored = self.operation('inspect')
        self.assertEqual(restored['contact_name'], tool.GENERIC)
        self.assertEqual(restored['revision'], after['revision'] + 1)
        with self.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM socialmei.me_messages WHERE workspace_id=1').fetchone()[0], 2)
