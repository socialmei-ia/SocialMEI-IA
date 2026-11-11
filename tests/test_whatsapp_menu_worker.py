import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import httpx

spec = importlib.util.spec_from_file_location('menu_worker', Path(__file__).resolve().parents[1] / 'tools/whatsapp-menu-worker.py')
worker = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = worker
spec.loader.exec_module(worker)


class ContinuousWorkerTests(unittest.TestCase):
    def test_only_source_transport_or_server_failure_is_retry_safe(self):
        config = worker.Config('isolated-instance', 'fixture', '111@c.us',
                               'isolated-token-for-test', 'isolated-key-for-test')
        for status, error in ((503, worker.SourceUnavailable), (403, worker.Blocked)):
            with self.subTest(status=status):
                api, provider = Mock(), Mock()
                api.__enter__ = Mock(return_value=api)
                api.__exit__ = Mock(return_value=False)
                provider.__enter__ = Mock(return_value=provider)
                provider.__exit__ = Mock(return_value=False)
                api.request.return_value = httpx.Response(status, json={'detail': 'unavailable'})
                factory = Mock(side_effect=[api, provider])
                with self.assertRaises(error) as raised:
                    worker.run_once(config, client_factory=factory)
                if status == 403:
                    self.assertNotIsInstance(raised.exception, worker.SourceUnavailable)
                self.assertEqual(api.request.call_count, 1)
                self.assertEqual(api.request.call_args.args[0], 'GET')
                provider.request.assert_not_called()

    def test_source_failure_backs_off_and_recovers_before_any_dispatch(self):
        poll = Mock(side_effect=[worker.SourceUnavailable(), worker.SourceUnavailable(),
                                 'SEM_MENSAGENS_NOVAS', 'RESULTADO_INCERTO_NAO_REENVIAR'])
        sleep = Mock()
        with patch('builtins.print'):
            self.assertEqual(worker.run_continuously(object(), poll=poll, sleep=sleep), 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [15, 30, 3])

    def test_unknown_failure_after_source_does_not_retry(self):
        poll = Mock(side_effect=worker.Blocked('Receipt unavailable'))
        sleep = Mock()
        with patch('builtins.print'):
            self.assertEqual(worker.run_continuously(object(), poll=poll, sleep=sleep), 3)
        self.assertEqual(poll.call_count, 1)
        sleep.assert_not_called()

    def test_default_entrypoint_never_sends(self):
        with patch.object(worker.Config, 'from_env') as config, patch('builtins.print'):
            self.assertEqual(worker.main([]), 0)
        config.assert_not_called()

    def test_continuous_uncertainty_stays_paused_instead_of_triggering_restart(self):
        with patch.object(worker.Config, 'from_env'), patch.object(worker, 'run_continuously', return_value=2) as run, patch.object(worker.time, 'sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                worker.main(['--continuous'])
        run.assert_called_once()
