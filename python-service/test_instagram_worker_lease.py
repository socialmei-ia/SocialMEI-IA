"""No Meta requests; optional locks use only the handover disposable database."""
from contextlib import contextmanager
import os
import unittest
from unittest.mock import Mock, patch

import instagram_worker_lease as lease
from test_whatsapp_channel_handover import DISPOSABLE
import test_account_auth as accounts


class WorkerLeaseTests(unittest.TestCase):
    def test_missing_review_or_invalid_workspace_never_opens_database(self):
        with patch.dict(os.environ,{'SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME':''}),patch.object(lease,'connect') as connect:
            for workspace in [60,True,0,-1,'60']:
                with self.assertRaises(RuntimeError),lease.worker_lease(workspace):pass
            connect.assert_not_called()

    def test_wrong_database_or_existing_sender_fails_without_provider_io(self):
        for database,locked in [('old-prisma-database',True),('reviewed',False)]:
            conn=Mock();conn.execute.return_value.fetchone.side_effect=[(database,),(locked,)]
            @contextmanager
            def connection(**options):
                self.assertEqual(options, {'worker': True})
                yield conn
            with patch.dict(os.environ,{'SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME':'reviewed'}),patch.object(lease,'connect',connection):
                with self.assertRaises(RuntimeError),lease.worker_lease(60):pass

    def test_connection_failure_stops_the_guard_and_unlocks(self):
        conn=Mock();conn.closed=False
        conn.execute.return_value.fetchone.side_effect=[('reviewed',),(True,),OSError('synthetic lost connection'),(True,)]
        @contextmanager
        def connection(**options):
            self.assertEqual(options, {'worker': True})
            yield conn
        with patch.dict(os.environ,{'SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME':'reviewed'}),patch.object(lease,'connect',connection):
            with self.assertRaises(OSError),lease.worker_lease(60) as check:check()
        self.assertIn('pg_advisory_unlock',conn.execute.call_args.args[0])


@unittest.skipUnless(DISPOSABLE,'Explicit disposable PostgreSQL required')
class WorkerLeaseDatabaseTests(unittest.TestCase):
    def test_reused_read_only_scans_keep_the_same_backend_and_exclusive_workspace_lease(self):
        from datetime import datetime, timezone
        from urllib.parse import urlsplit
        from psycopg.pq import TransactionStatus
        from instagram_worker_observer import pending
        with patch.dict(os.environ, {'DATABASE_URL': accounts.DB,
                    'SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME': urlsplit(accounts.DB).path[1:]}):
            with lease.worker_lease(60) as check:
                conn = check(); backend = conn.info.backend_pid; factory = conn.row_factory
                for _ in range(2):
                    self.assertIn('pending_count', pending(60, datetime.now(timezone.utc), connection=conn))
                    self.assertIs(check(), conn)
                    self.assertEqual(conn.info.backend_pid, backend)
                    self.assertEqual(conn.info.transaction_status, TransactionStatus.IDLE)
                    self.assertIs(conn.row_factory, factory)
                with self.assertRaises(RuntimeError), lease.worker_lease(60): pass
                with lease.worker_lease(61) as other: self.assertIsNot(other(), conn)
            self.assertTrue(conn.closed)

    def test_one_sender_per_workspace_and_release_after_shutdown(self):
        from urllib.parse import urlsplit
        with patch.dict(os.environ,{'DATABASE_URL':accounts.DB,
                    'SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME':urlsplit(accounts.DB).path[1:]}):
            with lease.worker_lease(60) as check:
                check()
                with self.assertRaises(RuntimeError),lease.worker_lease(60):pass
                with lease.worker_lease(61) as other:other()
            with lease.worker_lease(60) as resumed:resumed()


if __name__=='__main__':unittest.main()
