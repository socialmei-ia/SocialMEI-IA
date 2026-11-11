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
            "SOCIALMEI_DB_READINESS_CACHE_SECONDS": "60",
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

    def test_cache_always_checks_database_availability(self):
        self.assertEqual(database.check_database_readiness(include_auth=True), "prepared")
        self.assertEqual(database.check_database_readiness(include_auth=True), "prepared")
        self.deep.assert_called_once_with(include_auth=True)
        self.ping.assert_called_once_with()

    def test_expiration_rechecks_schema_and_does_not_cache_schema_failures(self):
        database.check_database_readiness()
        self.now += 60
        self.deep.side_effect = RuntimeError("schema unavailable")
        with self.assertRaises(RuntimeError):
            database.check_database_readiness()
        self.deep.side_effect = None
        database.check_database_readiness()
        self.assertEqual(self.deep.call_count, 3)
        self.ping.assert_not_called()

    def test_unreachable_database_never_uses_cached_healthy_result(self):
        database.check_database_readiness()
        self.ping.side_effect = ConnectionError("offline")
        with self.assertRaises(ConnectionError):
            database.check_database_readiness()
        self.assertIsNone(database._readiness_cache)
        self.deep.side_effect = ConnectionError("offline")
        with self.assertRaises(ConnectionError):
            database.check_database_readiness()

    def test_recovery_after_failed_ping_requires_deep_validation(self):
        database.check_database_readiness()
        self.ping.side_effect = ConnectionError("offline")
        with self.assertRaises(ConnectionError):
            database.check_database_readiness()
        self.ping.side_effect = None
        database.check_database_readiness()
        self.assertEqual(self.deep.call_count, 2)

    def test_database_authentication_and_ttl_changes_invalidate_cache(self):
        database.check_database_readiness()
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test@localhost/other"}):
            database.check_database_readiness()
        database.check_database_readiness(include_auth=True)
        with patch.dict(os.environ, {"SOCIALMEI_DB_READINESS_CACHE_SECONDS": "30"}):
            database.check_database_readiness(include_auth=True)
        self.assertEqual(self.deep.call_count, 4)
        self.ping.assert_not_called()

    def test_disabled_or_invalid_cache_performs_full_checks(self):
        for value in ("0", "-1", "invalid"):
            with self.subTest(value=value), patch.dict(os.environ, {
                "SOCIALMEI_DB_READINESS_CACHE_SECONDS": value,
            }):
                database.check_database_readiness()
                database.check_database_readiness()
        self.assertEqual(self.deep.call_count, 6)
        self.ping.assert_not_called()

    def test_unavailable_channel_schema_is_not_cached(self):
        self.deep.return_value = "unavailable"
        self.assertEqual(database.check_database_readiness(), "unavailable")
        self.assertEqual(database.check_database_readiness(), "unavailable")
        self.assertEqual(self.deep.call_count, 2)
        self.ping.assert_not_called()

    def test_concurrent_health_requests_coalesce_deep_validation(self):
        start = Barrier(8)

        def check(_):
            start.wait(timeout=5)
            return database.check_database_readiness(include_auth=True)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(check, range(8)))
        self.assertEqual(results, ["prepared"] * 8)
        self.assertEqual(self.deep.call_count, 1)
        self.assertEqual(self.ping.call_count, 7)


class ReadinessQueryTests(unittest.TestCase):
    def setUp(self):
        database._readiness_cache = None
        self.addCleanup(setattr, database, "_readiness_cache", None)

    def test_cache_hit_runs_only_read_only_availability_query(self):
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
                }]

        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://test@localhost/isolated",
            "SOCIALMEI_DB_READINESS_CACHE_SECONDS": "60",
        }), patch("database.connect", side_effect=Connection), patch("database.monotonic", return_value=100):
            database.check_database_readiness(include_auth=True)
            deep_count = len(queries)
            queries.clear()
            database.check_database_readiness(include_auth=True)
            availability_queries = list(queries)
            queries.clear()
            database.check_database(include_auth=True)
            self.assertEqual(len(queries), deep_count)
        self.assertEqual(deep_count, 3 + len(database.CRM_SCHEMA_QUERIES)
                         + len(database.AUTH_SCHEMA_QUERIES) + len(database.CHANNEL_SCHEMA_QUERIES))
        self.assertEqual(availability_queries, ["SET TRANSACTION READ ONLY",
                                               "SET LOCAL statement_timeout = '5s'", "SELECT 1"])

    def test_default_and_maximum_cache_duration(self):
        with patch.dict(os.environ):
            os.environ.pop("SOCIALMEI_DB_READINESS_CACHE_SECONDS", None)
            self.assertEqual(database_readiness_cache_seconds(), 60)
        with patch.dict(os.environ, {"SOCIALMEI_DB_READINESS_CACHE_SECONDS": "999999"}):
            self.assertEqual(database_readiness_cache_seconds(), 300)


if __name__ == "__main__":
    unittest.main()
