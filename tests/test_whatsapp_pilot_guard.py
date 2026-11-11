import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_worker', ROOT / 'tools/whatsapp-menu-worker.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
spec = importlib.util.spec_from_file_location('pilot_guard', ROOT / 'tools/whatsapp-pilot-guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class PilotLimitsTests(unittest.TestCase):
    def run_pilot(self, allowed_count=1, error=False, expire_before_post=False, foreign=False, source_failures=0, fail_after_send=False, transport_error_stage=None):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            contacts = ['waha:22' + str(i) + '@c.us' for i in range(allowed_count)]
            (folder / 'allowed.json').write_text(json.dumps(contacts))
            clock = [1000.0]
            posts = []
            failed_reads = [0]
            def handler(request):
                posts.append(request)
                return httpx.Response(200, json={'id': 'synthetic-provider-receipt'})
            def poll(cfg, client_factory):
                if transport_error_stage:
                    url = (guard.API_URL + guard.SOURCE_URL if transport_error_stage == 'source_read'
                           else guard.WAHA_URL + '/api/sessions/fixture')
                    def fail_transport(request):
                        raise httpx.ConnectError('synthetic connection failure', request=request)
                    with client_factory(transport=httpx.MockTransport(fail_transport)) as client:
                        client.request('GET', url)
                if fail_after_send and len(posts) == 1 and not failed_reads[0]:
                    failed_reads[0] += 1
                    raise module.SourceUnavailable('read failure after previous send')
                if failed_reads[0] < source_failures:
                    failed_reads[0] += 1
                    raise module.SourceUnavailable('source read only')
                if error:
                    raise RuntimeError('source unavailable')
                if expire_before_post:
                    clock[0] = 1601
                contact = '999@c.us' if foreign else contacts[len(posts) % len(contacts)].removeprefix('waha:')
                with client_factory(transport=httpx.MockTransport(handler)) as client:
                    client.request('POST', guard.WAHA_URL + '/api/sendText', content=json.dumps({'chatId': contact}).encode())
                return 'ENVIO_CONFIRMADO'
            def path(value):
                return folder / ('allowed.json' if value.endswith('allowed-contacts.json') else 'state.json')
            with patch.object(guard, 'Path', side_effect=path), patch.object(guard.Config, 'from_env'), patch.object(guard, 'run_once', side_effect=poll), patch.object(guard, 'pause'), patch.object(guard.time, 'time', side_effect=lambda: clock[0]), patch.object(guard.time, 'monotonic', return_value=0), patch.object(guard.time, 'sleep', side_effect=lambda value: clock.__setitem__(0, clock[0] + value)), patch.dict(os.environ, {'SOCIALMEI_PILOT_START_UTC': '1970-01-01T00:16:40+00:00'}), patch('builtins.print'):
                guard.main()
            return json.loads((folder / 'state.json').read_text()), len(posts)

    def test_fifth_contact_response_closes_pilot_before_another_poll(self):
        state, posts = self.run_pilot()
        self.assertEqual((state['confirmed'], posts, state['reason']), (5, 5, 'send_limit_reached'))

    def test_fortieth_total_response_closes_pilot_without_exceeding_contact_cap(self):
        state, posts = self.run_pilot(allowed_count=10)
        self.assertEqual((state['confirmed'], posts), (40, 40))
        self.assertEqual(max(state['contacts'].values()), 4)

    def test_any_source_error_closes_without_retry_or_send(self):
        state, posts = self.run_pilot(error=True)
        self.assertEqual((state['attempted'], posts), (0, 0))
        self.assertEqual(state['reason'], 'error_RuntimeError')

    def test_source_read_recovers_within_window_before_any_send(self):
        state, posts = self.run_pilot(source_failures=2)
        self.assertEqual((state['confirmed'], posts, state['reason']), (5, 5, 'send_limit_reached'))
        self.assertEqual(state['source_read_failures'], 2)

    def test_source_read_failure_budget_closes_without_sending(self):
        state, posts = self.run_pilot(source_failures=3)
        self.assertEqual((state['attempted'], posts, state['reason']), (0, 0, 'source_read_unavailable'))
        self.assertEqual(state['source_read_failures'], 3)

    def test_source_read_failure_after_attempt_stops_without_resend(self):
        state, posts = self.run_pilot(fail_after_send=True)
        self.assertEqual((state['attempted'], state['confirmed'], posts), (1, 1, 1))
        self.assertEqual(state['reason'], 'source_read_unavailable')

    def test_transport_error_records_stage_without_sensitive_details(self):
        for stage in ('source_read', 'waha_session_read'):
            with self.subTest(stage=stage):
                state, posts = self.run_pilot(transport_error_stage=stage)
                self.assertEqual((state['attempted'], posts), (0, 0))
                self.assertEqual(state['last_transport_stage'], stage)
                self.assertEqual(state['reason'], 'error_ConnectError')

    def test_expiration_before_provider_post_blocks_send(self):
        state, posts = self.run_pilot(expire_before_post=True)
        self.assertEqual((state['attempted'], posts), (0, 0))
        self.assertEqual(state['status'], 'paused')

    def test_contact_outside_existing_authorization_cannot_receive(self):
        state, posts = self.run_pilot(foreign=True)
        self.assertEqual((state['attempted'], posts), (0, 0))

    def test_resumed_window_cannot_exceed_the_remaining_time(self):
        with patch.dict(os.environ, {'SOCIALMEI_PILOT_SECONDS': '1'}):
            state, posts = self.run_pilot(allowed_count=10)
        self.assertEqual(posts, 1)
        self.assertEqual(state['reason'], 'window_expired')
