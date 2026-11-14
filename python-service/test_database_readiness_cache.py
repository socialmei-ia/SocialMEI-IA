import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from threading import Barrier
from unittest.mock import patch

import database
from settings import database_readiness_cache_seconds


class ReadinessCacheTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://test@localhost/isolated",
            "SOCIALMEI_DB_READINESS_CACHE_SECONDS": "300",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        database._readiness_cache = None
        self.addCleanup(setattr, database, "_readiness_cache", None)
        self.now = 100.0
        self.clock = patch("database.monotonic", side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.schema = patch("database.check_database", return_value="prepared")
        self.deep = self.schema.start()
        self.addCleanup(self.schema.stop)
        self.availability = patch("database._check_database_availability")
        self.ping = self.availability.start()
        self.addCleanup(self.availability.stop)

    def test_repeated_readiness_requests_do_not_query_database(self):
        for _ in range(100):
            self.assertEqual(database.check_database_readiness(include_auth=True), "prepared")
        self.deep.assert_called_once_with(include_auth=True)
        self.ping.assert_called_once_with()

    def test_expiration_checks_only_availability_without_schema_scan(self):
        database.check_database_readiness()
        self.now += 300
        database.check_database_readiness()
        self.now += 299
        database.check_database_readiness()
        self.deep.assert_called_once_with(include_auth=False)
        self.assertEqual(self.ping.call_count, 2)

    def test_database_outage_is_cached_and_recovers_without_schema_rescan(self):
        database.check_database_readiness()
        self.now += 300
        self.ping.side_effect = ConnectionError("private-marker")
        for _ in range(10):
            with self.assertRaisesRegex(RuntimeError, "^Database readiness unavailable\\.$") as failure:
                database.check_database_readiness()
            self.assertNotIn("private-marker", str(failure.exception))
        self.assertEqual(self.ping.call_count, 2)
        self.now += 300
        self.ping.side_effect = None
        self.assertEqual(database.check_database_readiness(), "prepared")
        self.assertEqual(self.ping.call_count, 3)
        self.deep.assert_called_once_with(include_auth=False)

    def test_cold_database_connection_failure_recovers_automatically(self):
        self.ping.side_effect = database.psycopg.OperationalError("private-marker")
        for _ in range(5):
            with self.assertRaisesRegex(RuntimeError, "^Database readiness unavailable\\.$"):
                database.check_database_readiness()
        self.deep.assert_not_called()
        self.ping.assert_called_once_with()
        self.now += 300
        self.ping.side_effect = None
        self.assertEqual(database.check_database_readiness(), "prepared")
        self.deep.assert_called_once_with(include_auth=False)

    def test_structural_failures_do_not_repeat_full_schema_queries(self):
        for error in (
            database.psycopg.errors.UndefinedTable("private-marker"),
            database.psycopg.errors.UndefinedColumn("private-marker"),
            database.psycopg.errors.InsufficientPrivilege("private-marker"),
            RuntimeError("Migrations do CRM incompletas."),
            RuntimeError("Migration de contas ausente."),
        ):
            with self.subTest(error=type(error).__name__):
                database._readiness_cache = None
                self.deep.reset_mock()
                self.deep.side_effect = error
                with self.assertRaises(RuntimeError):
                    database.check_database_readiness()
                self.now += 300
                with self.assertRaises(RuntimeError):
                    database.check_database_readiness()
                self.deep.assert_called_once_with(include_auth=False)
        self.assertEqual(self.ping.call_count, 10)

    def test_partial_deep_failure_has_bounded_schema_retry_and_remains_unready(self):
        partial_queries = []

        def partial_failure(**_):
            partial_queries.extend(range(25))
            raise database.psycopg.OperationalError("temporary failure after SQL")

        self.deep.side_effect = partial_failure
        with self.assertRaises(RuntimeError):
            database.check_database_readiness()
        for _ in range(71):
            self.now += 300
            with self.assertRaises(RuntimeError):
                database.check_database_readiness()
        self.assertEqual(len(partial_queries), 25)
        self.deep.assert_called_once_with(include_auth=False)
        self.now += 300
        self.deep.side_effect = None
        self.assertEqual(database.check_database_readiness(), "prepared")
        self.assertEqual(self.deep.call_count, 2)

    def test_database_authentication_and_ttl_changes_invalidate_cache(self):
        database.check_database_readiness()
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test@localhost/other"}):
            database.check_database_readiness()
        database.check_database_readiness(include_auth=True)
        with patch.dict(os.environ, {"SOCIALMEI_DB_READINESS_CACHE_SECONDS": "60"}):
            database.check_database_readiness(include_auth=True)
        self.assertEqual(self.deep.call_count, 4)
        self.assertEqual(self.ping.call_count, 4)

    def test_process_restart_does_full_schema_validation(self):
        database.check_database_readiness()
        database._readiness_cache = None
        database.check_database_readiness()
        self.assertEqual(self.deep.call_count, 2)
        self.assertEqual(self.ping.call_count, 2)

    def test_disabled_or_invalid_cache_performs_full_checks(self):
        for value in ("0", "-1", "invalid"):
            with self.subTest(value=value), patch.dict(os.environ, {
                "SOCIALMEI_DB_READINESS_CACHE_SECONDS": value,
            }):
                database.check_database_readiness()
                database.check_database_readiness()
        self.assertEqual(self.deep.call_count, 6)
        self.ping.assert_not_called()

    def test_optional_channel_unavailable_result_does_not_repeat_schema_checks(self):
        self.deep.return_value = "unavailable"
        self.assertEqual(database.check_database_readiness(), "unavailable")
        self.now += 300
        self.assertEqual(database.check_database_readiness(), "unavailable")
        self.deep.assert_called_once_with(include_auth=False)
        self.assertEqual(self.ping.call_count, 2)

    def test_concurrent_health_requests_coalesce_deep_validation_and_pings(self):
        start = Barrier(8)

        def check(_):
            start.wait(timeout=5)
            return database.check_database_readiness(include_auth=True)

        for cycle in range(2):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(check, range(8)))
            self.assertEqual(results, ["prepared"] * 8)
            self.now += 300
        self.assertEqual(self.deep.call_count, 1)
        self.assertEqual(self.ping.call_count, 2)


class ReadinessQueryTests(unittest.TestCase):
    def setUp(self):
        database._readiness_cache = None
        self.addCleanup(setattr, database, "_readiness_cache", None)

    def test_periodic_probe_is_one_autocommit_query_with_bounded_read_only_options(self):
        queries = []
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://test@localhost/isolated?options=-c%20search_path%3Dsocialmei",
        }), patch("database.psycopg.connect") as connect:
            connect.return_value.__enter__.return_value.execute.side_effect = queries.append
            database._check_database_availability()
        self.assertEqual(queries, ["SELECT 1"])
        self.assertEqual(connect.call_args.kwargs, {
            "autocommit": True, "connect_timeout": 5,
            "options": "-c search_path=socialmei -c default_transaction_read_only=on -c statement_timeout=5000",
        })

    def test_direct_operational_check_is_not_cached(self):
        queries = []

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def cursor(self):
                return self

            def transaction(self):
                return nullcontext()

            def execute(self, query):
                queries.append(query)

            def fetchall(self):
                return [(name,) for name in database.CRM_MIGRATIONS | {
                    database.AUTH_MIGRATION, database.CHANNEL_MIGRATION,
                    database.IDENTITY_MIGRATION,
                }]

        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://test@localhost/isolated",
            "SOCIALMEI_DB_READINESS_CACHE_SECONDS": "300",
        }), patch("database.connect", side_effect=Connection), patch("database._check_database_availability"), patch("database.monotonic", return_value=100):
            database.check_database_readiness(include_auth=True)
            deep_count = len(queries)
            queries.clear()
            database.check_database_readiness(include_auth=True)
            self.assertEqual(queries, [])
            database.check_database(include_auth=True)
            self.assertEqual(len(queries), deep_count)
        self.assertEqual(deep_count, 3 + len(database.CRM_SCHEMA_QUERIES)
                         + len(database.AUTH_SCHEMA_QUERIES) + len(database.CHANNEL_SCHEMA_QUERIES))

    def test_default_and_maximum_cache_duration(self):
        with patch.dict(os.environ):
            os.environ.pop("SOCIALMEI_DB_READINESS_CACHE_SECONDS", None)
            self.assertEqual(database_readiness_cache_seconds(), 300)
        with patch.dict(os.environ, {"SOCIALMEI_DB_READINESS_CACHE_SECONDS": "999999"}):
            self.assertEqual(database_readiness_cache_seconds(), 900)

    def test_monthly_monitor_budget_with_four_workers_and_daily_restarts(self):
        # Upper bound includes 25 SELECT, 2 SET and 4 transaction/savepoint statements per start.
        month = 31 * 24 * 3600
        workers = 4
        pings = workers * month // 300
        startup = workers * 31 * 31
        self.assertEqual(pings + startup, 39556)
        self.assertLess(pings + startup, 40000)

    def test_monthly_monitor_budget_even_with_partial_deep_failures(self):
        # Four retries/day plus a possible daily process restart, including protocol statements.
        operations = 4 * 31 * (24 * 3600 // 300 + 5 * 31)
        self.assertEqual(operations, 54932)
        self.assertLess(operations, 55000)


if __name__ == "__main__":
    unittest.main()
