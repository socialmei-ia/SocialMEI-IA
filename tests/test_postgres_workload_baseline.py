"""Offline tests: no database connection, table changes or network required."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "postgres-workload-baseline.py"
spec = importlib.util.spec_from_file_location("workload_baseline", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def state(value=0, reset="2026-11-11 00:00:00+00"):
    return {"reset": reset, "connections": 2,
            "counters": {name: value for name in module.COUNTERS}}


class WorkloadBaselineTests(unittest.TestCase):
    def test_query_is_cumulative_read_only_single_statement(self):
        self.assertTrue(module.SQL.startswith("SELECT "))
        self.assertIn("pg_catalog.pg_stat_database", module.SQL)
        self.assertEqual(module.SQL.count("SELECT "), 1)
        self.assertNotIn("pg_stat_statements", module.SQL)

    def test_decode_rejects_missing_or_invalid_statistics(self):
        with self.assertRaisesRegex(ValueError, "invalid_statistics"):
            module.decode(None)
        with self.assertRaisesRegex(ValueError, "invalid_statistics"):
            module.decode(("reset", 1, *([-1] * len(module.COUNTERS))))
        decoded = module.decode(("reset", 2, *([3] * len(module.COUNTERS))))
        self.assertEqual(decoded["connections"], 2)
        self.assertEqual(decoded["counters"]["xact_commit"], 3)

    def test_comparison_rates_and_cache_ratio(self):
        first, second = state(10), state(20)
        result = module.compare(first, second, 60)
        self.assertEqual(result["delta"]["xact_commit"], 10)
        self.assertEqual(result["per_minute"]["xact_commit"], 10)
        self.assertEqual(result["block_cache_hit_percent"], 50)
        self.assertEqual(result["connections_last"], 2)

    def test_statistics_reset_or_negative_counters_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "reset"):
            module.compare(state(10), state(20, "different"), 60)
        with self.assertRaisesRegex(ValueError, "reset"):
            module.compare(state(20), state(10), 60)
        with self.assertRaises(ValueError):
            module.compare(state(), state(), 0)

    def test_missing_explicit_metrics_dsn_does_not_connect(self):
        with patch.dict(os.environ, {"SOCIALMEI_PG_METRICS_DSN": ""}), \
                patch.object(module, "snapshot") as sample, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.run(["--interval", "10"]), 2)
            sample.assert_not_called()

    def test_cli_bounded_interval_and_sampling(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                module.run(["--interval", "0"])
            with self.assertRaises(SystemExit):
                module.run(["--samples", "13"])

    def test_cli_sanitizes_connection_failures(self):
        errors = io.StringIO()
        with patch.dict(os.environ, {"SOCIALMEI_PG_METRICS_DSN": "PRIVATE-PASSWORD"}), \
                patch.object(module, "snapshot", side_effect=RuntimeError("PRIVATE-PASSWORD")), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(module.run(["--interval", "10"]), 1)
        self.assertNotIn("PRIVATE-PASSWORD", errors.getvalue())

    def test_cli_uses_exactly_two_samples_without_looping(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"SOCIALMEI_PG_METRICS_DSN": "private-dsn"}), \
                patch.object(module, "snapshot", side_effect=[state(10), state(11)]) as snap, \
                patch.object(module.time, "sleep") as sleep, \
                contextlib.redirect_stdout(output):
            self.assertEqual(module.run(["--interval", "10"]), 0)
        self.assertEqual(snap.call_count, 2)
        sleep.assert_called_once_with(10)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["statement_count"], 2)
        self.assertNotIn("private-dsn", output.getvalue())

    def test_snapshot_enforces_read_only_and_timeouts(self):
        fake = MagicMock()
        fake.connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            "reset", 1, *([0] * len(module.COUNTERS)))
        with patch.dict(sys.modules, {"psycopg": fake}):
            result = module.snapshot("private-dsn")
        options = fake.connect.call_args.kwargs
        self.assertIn("default_transaction_read_only=on", options["options"])
        self.assertIn("statement_timeout=3000", options["options"])
        self.assertEqual(options["connect_timeout"], 5)
        self.assertTrue(options["autocommit"])
        self.assertEqual(result["connections"], 1)


if __name__ == "__main__":
    unittest.main()
