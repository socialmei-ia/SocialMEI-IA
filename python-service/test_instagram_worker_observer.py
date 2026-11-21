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

    def test_real_worker_loop_does_not_build_runtime_or_call_sender_in_observe_mode(self):
        # fcntl is Linux-only; the worker loop itself can be exercised on Windows.
        with patch.dict(sys.modules, {'fcntl': SimpleNamespace()}):
            spec = importlib.util.spec_from_file_location('observer_worker',
                Path(__file__).resolve().parents[1] / 'tools/instagram-auto-menu-worker.py')
            worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
        wakeup = MagicMock(); wakeup.__enter__.return_value = wakeup
        wakeup.wait.side_effect = InterruptedError('synthetic stop after first persisted scan')
        with TemporaryDirectory() as tmp, patch.object(worker, 'QueueWakeup', return_value=wakeup), \
                patch.object(worker, 'heartbeat'), patch.object(worker, 'build_runtime') as runtime, \
                patch.object(worker, 'reply') as reply, patch.object(observer, 'pending', return_value=self.counts):
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
            runtime.assert_not_called(); reply.assert_not_called()


if __name__ == '__main__':
    unittest.main()
