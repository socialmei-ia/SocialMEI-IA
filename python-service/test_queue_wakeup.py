"""Offline wakeup, reconciliation and sender liveness contracts."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import psycopg

import queue_wakeup as queue
import instagram_worker_health as health


class QueueWakeupTests(unittest.TestCase):
    def test_default_poll_never_opens_a_listener_and_preserves_interval(self):
        delays = []
        with patch.dict(os.environ, {'SOCIALMEI_QUEUE_WAKEUP_MODE': 'poll'}), \
                patch.object(queue.psycopg, 'connect') as connect:
            with queue.QueueWakeup(queue.RECOVERY_CHANNEL, interval=5, sleeper=delays.append) as wakeup:
                self.assertFalse(wakeup.wait())
            connect.assert_not_called()
        self.assertEqual(delays, [5])

    def test_listen_subscribes_before_read_and_wakes_without_sleeping(self):
        conn = MagicMock()
        # Generator close is also supported by psycopg's notification iterator.
        conn.notifies.side_effect = [(value for value in [object()]), (value for value in [object(), object()])]
        with patch.dict(os.environ, {'SOCIALMEI_QUEUE_WAKEUP_MODE': 'listen'}), \
                patch.object(queue, 'database_url', return_value='synthetic-dsn'), \
                patch.object(queue.psycopg, 'connect', return_value=conn) as connect:
            delay = MagicMock()
            with queue.QueueWakeup(queue.instagram_channel(9), sleeper=delay) as wakeup:
                conn.execute.assert_called_once()
                self.assertTrue(wakeup.wait())
            connect.assert_called_once()
            self.assertTrue(connect.call_args.kwargs['autocommit'])
            delay.assert_not_called()
            conn.close.assert_called_once()

    def test_lost_notifications_reconcile_and_keep_file_heartbeat_fresh(self):
        conn = MagicMock()
        conn.notifies.side_effect = lambda **kwargs: (value for value in [])
        heartbeat = MagicMock()
        with patch.dict(os.environ, {'SOCIALMEI_QUEUE_WAKEUP_MODE': 'listen'}), \
                patch.object(queue, 'database_url', return_value='synthetic-dsn'), \
                patch.object(queue.psycopg, 'connect', return_value=conn):
            with queue.QueueWakeup(queue.RECOVERY_CHANNEL, reconcile=300, heartbeat=heartbeat) as wakeup:
                self.assertFalse(wakeup.wait())
        self.assertEqual(conn.notifies.call_count, 10)
        self.assertTrue(all(call.kwargs['timeout'] == 30 for call in conn.notifies.call_args_list))
        self.assertGreaterEqual(heartbeat.call_count, 10)

    def test_broken_listener_falls_back_to_poll_without_busy_reconnect(self):
        delays = []
        with patch.dict(os.environ, {'SOCIALMEI_QUEUE_WAKEUP_MODE': 'listen'}), \
                patch.object(queue, 'database_url', return_value='synthetic-dsn'), \
                patch.object(queue.time, 'monotonic', return_value=100), \
                patch.object(queue.psycopg, 'connect', side_effect=psycopg.OperationalError('private')) as connect:
            with queue.QueueWakeup(queue.RECOVERY_CHANNEL, sleeper=delays.append) as wakeup:
                wakeup.prepare()
                wakeup.wait()
                wakeup.prepare()
                self.assertEqual(wakeup.connection_failures, 1)
                self.assertEqual(wakeup.retry_at, 115)
            connect.assert_called_once()
        self.assertEqual(delays, [15])

    def test_notify_has_empty_payload_and_failure_rolls_back_only_savepoint(self):
        conn = MagicMock()
        with patch.dict(os.environ, {'SOCIALMEI_QUEUE_WAKEUP_MODE': 'listen'}):
            self.assertTrue(queue.notify_queue(conn, queue.instagram_channel(12)))
            conn.execute.assert_called_once_with("SELECT pg_notify(%s, '')", ('socialmei_instagram_12',))
            conn.commit.assert_not_called()
            conn.execute.side_effect = psycopg.OperationalError('private')
            self.assertFalse(queue.notify_queue(conn, queue.RECOVERY_CHANNEL))
            conn.rollback.assert_not_called()

    def test_poll_producers_add_no_sql(self):
        conn = MagicMock()
        with patch.dict(os.environ, {'SOCIALMEI_QUEUE_WAKEUP_MODE': 'poll'}):
            self.assertFalse(queue.notify_queue(conn, queue.RECOVERY_CHANNEL))
        conn.execute.assert_not_called()

    def test_queue_names_and_configuration_reject_untrusted_input(self):
        for workspace in (True, 0, -1, '1', 2**64):
            with self.subTest(workspace=workspace), self.assertRaises(ValueError):
                queue.instagram_channel(workspace)
        with patch.dict(os.environ, {'SOCIALMEI_QUEUE_WAKEUP_MODE': 'invalid'}):
            with self.assertRaises(ValueError):
                queue.QueueWakeup(queue.RECOVERY_CHANNEL)
        with self.assertRaises(ValueError):
            queue.notify_queue(MagicMock(), 'channel; DROP TABLE source')

    def test_virtual_idle_window_reduces_durable_scans_without_extra_listen_queries(self):
        # Each iteration is a durable queue scan; PostgreSQL notification waits emit no SQL.
        for reconcile, expected in ((60, 15), (300, 3)):
            conn = MagicMock()
            conn.notifies.side_effect = lambda **kwargs: (value for value in [])
            with patch.dict(os.environ, {'SOCIALMEI_QUEUE_WAKEUP_MODE': 'listen'}), \
                    patch.object(queue, 'database_url', return_value='synthetic-dsn'), \
                    patch.object(queue.psycopg, 'connect', return_value=conn):
                with queue.QueueWakeup(queue.RECOVERY_CHANNEL, reconcile=reconcile) as wakeup:
                    scans = 0
                    for _ in range(0, 900, reconcile):
                        wakeup.prepare()
                        scans += 1
                        wakeup.wait()
                self.assertEqual(scans, expected)
                conn.execute.assert_called_once()
                self.assertLess(scans, 900 // 15)


class InstagramHealthTests(unittest.TestCase):
    def test_stale_foreign_blocked_or_read_failure_never_looks_running(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'state.json').write_text(json.dumps({'status': 'running', 'in_flight': True}))
            now = datetime.now(timezone.utc)
            health.heartbeat('running', 'ready', folder=path)
            self.assertTrue(health.healthy(folder=path, now=now))
            self.assertFalse(health.healthy(folder=path, now=now + timedelta(seconds=121)))
            for status, read in (('blocked', 'unavailable'), ('starting', 'initializing'), ('running', 'unavailable')):
                health.heartbeat(status, read, folder=path)
                self.assertFalse(health.healthy(folder=path))
            health.heartbeat('running', 'ready', folder=path)
            with patch.object(health.socket, 'gethostname', return_value='other-container'):
                self.assertFalse(health.healthy(folder=path))
            # Liveness must never clear the sender's uncertain/in-flight latch.
            self.assertTrue(json.loads((path / 'state.json').read_text())['in_flight'])


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Disposable PostgreSQL not configured')
class PostgreSQLWakeupTests(unittest.TestCase):
    def test_committed_signal_wakes_immediately_and_rollback_has_no_signal(self):
        dsn = os.environ['TEST_DATABASE_URL']
        channel = queue.instagram_channel(int(uuid4().hex[:12], 16))
        with patch.dict(os.environ, {'DATABASE_URL': dsn, 'SOCIALMEI_QUEUE_WAKEUP_MODE': 'listen'}):
            with queue.QueueWakeup(channel, interval=1, reconcile=1) as wakeup, psycopg.connect(dsn) as producer:
                producer.execute('SELECT 1')
                self.assertTrue(queue.notify_queue(producer, channel))
                self.assertEqual(list(wakeup.connection.notifies(timeout=0.05, stop_after=1)), [])
                producer.commit()
                self.assertTrue(wakeup.wait())
                producer.execute('SELECT 1')
                self.assertTrue(queue.notify_queue(producer, channel))
                producer.rollback()
                self.assertEqual(list(wakeup.connection.notifies(timeout=0.05, stop_after=1)), [])
                # Timeout does not claim that a signal or durable job existed.
                self.assertFalse(wakeup.wait())

    def test_listener_disconnect_falls_back_and_reconnects_without_queue_mutations(self):
        dsn = os.environ['TEST_DATABASE_URL']
        channel = queue.instagram_channel(int(uuid4().hex[:12], 16))
        delays = []
        with patch.dict(os.environ, {'DATABASE_URL': dsn, 'SOCIALMEI_QUEUE_WAKEUP_MODE': 'listen'}):
            with queue.QueueWakeup(channel, interval=1, reconcile=1, sleeper=delays.append) as wakeup:
                wakeup.connection.close()
                self.assertFalse(wakeup.wait())
                self.assertEqual(delays, [1])
                self.assertEqual(wakeup.connection_failures, 1)
                wakeup.retry_at = 0
                wakeup.prepare()
                with psycopg.connect(dsn) as producer:
                    self.assertTrue(queue.notify_queue(producer, channel))
                self.assertTrue(wakeup.wait())


if __name__ == '__main__':
    unittest.main()
