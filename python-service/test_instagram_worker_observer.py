from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

import instagram_worker_observer as observer


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 21, tzinfo=timezone.utc)
        self.counts = {'pending_count': 2, 'latest_pending_message_id': 99}

    def test_checkpoint_survives_restart_without_advancing_or_dispatching_jobs(self):
        state = observer.checkpoint(None, 60, self.start, self.counts)
        self.assertEqual(observer.checkpoint(state, 60, self.start, self.counts), state)
        self.assertFalse(state['send_enabled'])
        self.assertFalse(state['in_flight'])
        with self.assertRaises(RuntimeError):
            observer.checkpoint(state, 61, self.start, self.counts)

    def test_pending_scan_is_read_only_and_scope_is_bound_on_both_joins(self):
        conn = MagicMock(); conn.execute.return_value.fetchone.return_value = self.counts
        @contextmanager
        def connect(): yield conn
        with patch.object(observer, 'connect', connect):
            self.assertEqual(observer.pending(60, self.start), self.counts)
        calls = conn.execute.call_args_list
        self.assertEqual(calls[0].args[0], 'SET TRANSACTION READ ONLY')
        query, params = calls[-1].args
        self.assertIn('e.workspace_id=m.workspace_id', query)
        self.assertIn('c.workspace_id=e.workspace_id', query)
        self.assertEqual(params, (60, self.start, self.start))

    def test_scan_reuses_lease_connection_without_closing_or_releasing_its_session(self):
        conn = MagicMock(); conn.execute.return_value.fetchone.return_value = self.counts
        factory = conn.row_factory
        with patch.object(observer, 'connect') as connect:
            self.assertEqual(observer.pending(60, self.start, connection=conn), self.counts)
            connect.assert_not_called()
        conn.transaction.assert_called_once_with()
        conn.close.assert_not_called()
        self.assertIs(conn.row_factory, factory)
        self.assertEqual(conn.execute.call_args_list[0].args[0], 'SET TRANSACTION READ ONLY')
        conn.execute.side_effect = OSError('synthetic SQL interruption')
        with self.assertRaises(OSError): observer.pending(60, self.start, connection=conn)
        conn.close.assert_not_called()
        self.assertIs(conn.row_factory, factory)

    def test_startup_gates_block_before_database_lease_even_with_optimized_python(self):
        lock_api = SimpleNamespace(flock=Mock(), LOCK_EX=1, LOCK_NB=2)
        enable = Mock(return_value=False)
        with patch.dict(sys.modules, {'fcntl': lock_api,
                                     'instagram_auto_menu': SimpleNamespace(enabled=enable)}):
            spec = importlib.util.spec_from_file_location('gated_instagram_worker',
                Path(__file__).resolve().parents[1] / 'tools/instagram-auto-menu-worker.py')
            worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
            scenarios = [
                ('60', 'send', '2026-11-21T00:00:00+00:00', 'sending is disabled'),
                ('60', 'observe', '2026-11-21T00:00:00', 'explicit timezone'),
                ('0', 'observe', '2026-11-21T00:00:00+00:00', 'Invalid Instagram workspace'),
            ]
            for workspace, mode, start, reason in scenarios:
                with self.subTest(workspace=workspace, mode=mode, start=start):
                    env = {'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID': workspace,
                           'SOCIALMEI_INSTAGRAM_WORKER_MODE': mode,
                           'SOCIALMEI_INSTAGRAM_AUTO_MENU_START_UTC': start,
                           'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED': 'false',
                           'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED': 'false'}
                    with patch.dict(os.environ, env, clear=True), \
                            patch.object(worker, 'Path', return_value=MagicMock()), \
                            patch.object(worker, 'heartbeat'), \
                            patch.object(worker, 'worker_lease') as lease, \
                            patch.object(worker, 'run_sender') as sender:
                        with self.assertRaisesRegex(RuntimeError, reason):
                            worker.main()
                        lease.assert_not_called()
                        sender.assert_not_called()

    def test_unconfigured_runtime_cannot_save_or_dispatch(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        database = MagicMock()
        database.return_value.__enter__.return_value = conn
        runtime = SimpleNamespace(status='blocked', send=Mock())
        reply = Mock()
        modules = {'fcntl': SimpleNamespace(),
                   'instagram_auto_menu': SimpleNamespace(next_source=Mock(), reply=reply, db=database),
                   'instagram_contact_identity': SimpleNamespace(refresh_contacts=Mock()),
                   'instagram_runtime': SimpleNamespace(build_runtime=Mock(return_value=runtime))}
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('blocked_runtime_worker',
                Path(__file__).resolve().parents[1] / 'tools/instagram-auto-menu-worker.py')
            worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
            with TemporaryDirectory() as tmp, patch.object(worker, 'save') as save:
                with self.assertRaisesRegex(RuntimeError, 'runtime is unavailable'):
                    worker.run_sender(60, self.start, Path(tmp), Mock())
                save.assert_not_called()
                reply.assert_not_called()
                runtime.send.assert_not_called()

    def test_real_worker_loop_does_not_build_runtime_or_call_sender_in_observe_mode(self):
        # fcntl is Linux-only; the worker loop itself can be exercised on Windows.
        with patch.dict(sys.modules, {'fcntl': SimpleNamespace(), 'instagram_auto_menu': None,
                                     'instagram_runtime': None, 'instagram_contact_identity': None}):
            spec = importlib.util.spec_from_file_location('observer_worker',
                Path(__file__).resolve().parents[1] / 'tools/instagram-auto-menu-worker.py')
            worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
        wakeup = MagicMock(); wakeup.__enter__.return_value = wakeup
        wakeup.wait.side_effect = InterruptedError('synthetic stop after first persisted scan')
        with TemporaryDirectory() as tmp, patch.object(worker, 'QueueWakeup', return_value=wakeup), \
                patch.object(worker, 'heartbeat'), patch.object(worker, 'run_sender') as sender, \
                patch.object(observer, 'pending', return_value=self.counts):
            for workspace in (60, 61):
                folder = Path(tmp) / str(workspace); folder.mkdir()
                lease = Mock()
                for _ in range(2):
                    with self.assertRaises(InterruptedError):
                        worker.run_observer(workspace, self.start, folder, lease)
                    state = json.loads((folder / 'state.json').read_text())
                    self.assertEqual(state['workspace_id'], workspace)
                    self.assertFalse(state['send_enabled'])
                self.assertEqual(lease.call_count, 2)
            sender.assert_not_called()


if __name__ == '__main__':
    unittest.main()
