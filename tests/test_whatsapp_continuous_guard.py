import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch, MagicMock

import httpx

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


worker = load('public_worker', 'whatsapp-menu-worker.py')
guard = load('continuous_guard', 'whatsapp-continuous-guard.py')


class ContinuousTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.journal = guard.Journal(self.folder, 1000, ['waha:222@c.us'])
        self.addCleanup(lambda: self.journal.lock.close())

    def test_single_sender_lock(self):
        with self.assertRaises(BlockingIOError):
            guard.Journal(self.folder, 1000, ['waha:222@c.us'])

    def test_no_foreign_contact_and_persistent_budget(self):
        with self.assertRaises(RuntimeError):
            self.journal.before_send({'chatId': '333@c.us'}, 1001)
        for _ in range(5):
            self.journal.before_send({'chatId': '222@c.us'}, 1001)
        with self.assertRaises(RuntimeError):
            self.journal.before_send({'chatId': '222@c.us'}, 1002)
        self.assertTrue(self.journal.available(3701))
        self.assertEqual(json.loads(self.journal.path.read_text())['attempted'], 5)

    def test_crash_after_claim_blocks_restart(self):
        self.journal.state['in_flight'] = True
        self.journal.save()
        self.journal.lock.close()
        with self.assertRaises(RuntimeError):
            guard.Journal(self.folder, 1000, ['waha:222@c.us'])

    def test_closed_state_never_reopens(self):
        self.journal.state['status'] = 'paused'
        self.journal.save()
        self.journal.lock.close()
        with self.assertRaises(RuntimeError):
            guard.Journal(self.folder, 1000, ['waha:222@c.us'])

    def test_source_failure_after_previous_confirmed_is_read_only_retry(self):
        self.journal.state['confirmed'] = 3
        poll = Mock(side_effect=[worker.SourceUnavailable(), 'SEM_MENSAGENS_NOVAS', RuntimeError()])
        sleeps = []
        guard.serve(self.journal, None, poll=poll, sleep=sleeps.append, clock=lambda: 1001)
        self.assertEqual(sleeps, [15, 15])
        self.assertEqual(self.journal.state['confirmed'], 3)
        self.assertEqual(self.journal.state['attempted'], 0)

    def test_uncertain_result_stops_without_retry(self):
        poll = Mock(return_value='RESULTADO_INCERTO_NAO_REENVIAR')
        guard.serve(self.journal, None, poll=poll, sleep=Mock(), clock=lambda: 1001)
        self.assertEqual(poll.call_count, 1)
        self.assertTrue(self.journal.state['in_flight'])
        self.assertEqual(self.journal.state['status'], 'paused')

    def test_actual_provider_post_is_guarded_before_transport(self):
        sent = []
        def poll(config, client_factory):
            with client_factory(transport=httpx.MockTransport(lambda req: sent.append(req) or httpx.Response(200))) as client:
                client.request('POST', guard.WAHA_URL + '/api/sendText', content=json.dumps({'chatId': '333@c.us'}))
            return 'ENVIO_CONFIRMADO'
        guard.serve(self.journal, None, poll=poll, sleep=Mock(), clock=lambda: 1001)
        self.assertEqual(sent, [])
        self.assertEqual(self.journal.state['status'], 'paused')

    def test_clock_cannot_precede_activation(self):
        with self.assertRaises(RuntimeError):
            self.journal.available(999)


class SourceGateTests(unittest.TestCase):
    def test_source_requires_same_contact_fresh_receipt_and_timestamp(self):
        from fastapi import FastAPI
        settings = types.SimpleNamespace(whatsapp_bot_allowed_contacts=lambda: frozenset({'waha:222@c.us'}))
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            {'external_message_id': 'synthetic-human', 'text': 'fixture', 'state': 'human'},
            {'external_message_id': 'synthetic-menu', 'text': 'fixture', 'state': 'menu'},
        ]
        context = MagicMock()
        context.__enter__.return_value = conn
        original = types.SimpleNamespace(app=FastAPI(), require_bot=Mock(),
            operation_database=lambda: context,
            authorize=lambda c, r: dict(workspace_id=1, channel_id=1,
                instancia='socialmei-equipe-piloto', sessao='01', identificador_conta='111@c.us'),
            permitted_text=lambda text, state: state != 'human')
        with patch.dict(sys.modules, {'settings': settings, 'public_app': original}), \
             patch.dict('os.environ', {'SOCIALMEI_CONTINUOUS_START_UTC': '2026-01-01T00:00:00+00:00'}), \
             patch.object(Path, 'read_text', return_value='["waha:222@c.us"]'):
            source = load('continuous_source', 'whatsapp-public-continuous.py')
        result = source.sources(None)
        self.assertEqual(result['sources'][0]['external_message_id'], 'synthetic-menu')
        sql, params = conn.execute.call_args.args
        self.assertIn('e.recebido_em>=%s AND m.occurred_at>=%s', sql)
        self.assertIn('d.id IS NULL', sql)
        self.assertIn("INTERVAL '2 minutes'", sql)
        self.assertEqual(params[2], ['waha:222@c.us'])
        self.assertEqual(params[3:], (source.START, source.START))

    def test_source_refuses_contact_not_in_existing_authorization(self):
        from fastapi import FastAPI
        settings = types.SimpleNamespace(whatsapp_bot_allowed_contacts=lambda: frozenset({'waha:333@c.us'}))
        with patch.dict(sys.modules, {'settings': settings, 'public_app': types.SimpleNamespace(app=FastAPI())}), \
             patch.dict('os.environ', {'SOCIALMEI_CONTINUOUS_START_UTC': '2026-01-01T00:00:00+00:00'}), \
             patch.object(Path, 'read_text', return_value='["waha:222@c.us"]'):
            with self.assertRaises(RuntimeError):
                load('continuous_source_invalid', 'whatsapp-public-continuous.py')


if __name__ == '__main__':
    unittest.main()
