"""Safety tests for low-memory, one-off Team 032/033 schema migration."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "tools/team-v33-lowmem-cutover.py"
SPEC = importlib.util.spec_from_file_location("team_lowmem_cutover", PATH)
cutover = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cutover)

FINGERPRINT = cutover.RESTORE_FINGERPRINT
NAMES = [f"{i:03}_fixture.sql" for i in range(1, 32)] + list(cutover.MIGRATIONS)
BLANK_TABLES = {
    "wa_bot_access": False,
    "wa_bot_conversations": False,
    "wa_bot_decisions": False,
    "me_provider_sentiment_jobs": False,
}


class OneOffMigrationTests(unittest.TestCase):
    def prepare_migrator(self):
        fake = SimpleNamespace()
        fake.backup = Path("/private/old-backup")
        fake.source = Path("/private/stage")
        fake.check_inputs = lambda b, s: (
            SimpleNamespace(), fake.backup, fake.source, NAMES,
            cutover.STAGED_SHA, NAMES[:31], NAMES[31:],
        )
        fake.runtime_safety = lambda: True
        fake.live_new_tables = lambda: BLANK_TABLES
        fake.live_ledger = lambda: NAMES[:31]
        fake.guarded_sql = lambda source, names: "SELECT 'guarded transaction'"
        fake.pgsql = lambda *a, **kw: None
        return fake

    def test_inspect_does_not_backup_or_write(self):
        m = self.prepare_migrator()
        with patch.object(cutover, "load_guard", return_value=m):
            with patch.object(cutover, "checkout_guard"):
                with patch.object(cutover, "memory_for_ddl"):
                    with patch.object(cutover, "fresh_backup",
                                      side_effect=AssertionError("backup")):
                        with patch.object(m, "pgsql",
                                          side_effect=AssertionError("write")):
                            report, status = cutover.apply_with_prior_restore(
                                FINGERPRINT, apply=False
                            )
        self.assertEqual(status, 0)
        self.assertEqual(report["action"], "read_only_preflight_success")
        self.assertFalse(report["production_changed"])
        self.assertFalse(report["provider_messages_sent"])
        self.assertNotIn("fresh_backup_name", report)

    def test_apply_requires_fresh_backup_and_transaction(self):
        m = self.prepare_migrator()
        written = []
        ledger = iter([NAMES[:31], NAMES])
        tables = iter([BLANK_TABLES, BLANK_TABLES,
                       {key: True for key in BLANK_TABLES}])
        m.live_ledger = lambda: next(ledger)
        m.live_new_tables = lambda: next(tables)
        m.pgsql = lambda sql, **kw: written.append((sql, kw))
        with patch.object(cutover, "load_guard", return_value=m):
            with patch.object(cutover, "checkout_guard") as checkout:
                with patch.object(cutover, "memory_for_ddl"):
                    with patch.object(cutover, "fresh_backup",
                                      return_value="team-auto-20261029-003900-abc123") as backup:
                        report, status = cutover.apply_with_prior_restore(
                            FINGERPRINT, apply=True
                        )
        self.assertEqual(status, 0)
        self.assertEqual(report["action"], "migrations_032_033_applied")
        self.assertTrue(report["production_changed"])
        self.assertEqual(report["production_migrations_after"], 33)
        self.assertTrue(report["fresh_backup_integrity_verified"])
        self.assertEqual(backup.call_count, 1)
        self.assertEqual(checkout.call_count, 2)
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0][1]["write"])
        self.assertEqual(written[0][1]["timeout"], 180)
        self.assertFalse(report["api_restarted"])
        self.assertFalse(report["provider_messages_sent"])

    def test_wrong_restore_fingerprint_blocks_before_write(self):
        m = self.prepare_migrator()
        with patch.object(cutover, "load_guard", return_value=m):
            with patch.object(m, "pgsql", side_effect=AssertionError("unsafe")):
                report, status = cutover.apply_with_prior_restore("0" * 64, apply=True)
        self.assertEqual(status, 1)
        self.assertEqual(report["phase"], "preflight")
        self.assertFalse(report["production_change_possible"])
        self.assertFalse(report["production_changed"])

    def test_backup_failure_never_attempts_migration(self):
        m = self.prepare_migrator()
        with patch.object(cutover, "load_guard", return_value=m):
            with patch.object(cutover, "checkout_guard"):
                with patch.object(cutover, "memory_for_ddl"):
                    with patch.object(cutover, "fresh_backup",
                                      side_effect=RuntimeError("backup failed")):
                        with patch.object(m, "pgsql",
                                          side_effect=AssertionError("unsafe write")):
                            report, code = cutover.apply_with_prior_restore(
                                FINGERPRINT, apply=True
                            )
        self.assertEqual(code, 1)
        self.assertEqual(report["phase"], "fresh_backup")
        self.assertFalse(report["production_change_possible"])
        self.assertNotIn("backup failed", json.dumps(report))

    def test_transaction_failure_flags_possible_change_and_blocks_retry(self):
        m = self.prepare_migrator()
        m.pgsql = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("sql command failed; private message")
        )
        with patch.object(cutover, "load_guard", return_value=m):
            with patch.object(cutover, "checkout_guard"):
                with patch.object(cutover, "memory_for_ddl"):
                    with patch.object(cutover, "fresh_backup", return_value="safe-backup"):
                        report, status = cutover.apply_with_prior_restore(
                            FINGERPRINT, apply=True
                        )
        self.assertEqual(status, 1)
        self.assertEqual(report["phase"], "transaction")
        self.assertTrue(report["production_change_possible"])
        self.assertNotIn("private message", json.dumps(report))

    def test_checkout_only_known_caddy_hotfix(self):
        command_output = iter([
            cutover.LIVE_BASE_SHA + "\n", " M deploy/team/Caddyfile\n"
        ])
        with patch.object(cutover.ROOT, "is_dir", return_value=True):
            with patch.object(cutover.ROOT, "is_symlink", return_value=False):
                with patch.object(cutover, "local",
                                  side_effect=lambda *a, **k: next(command_output)):
                    with patch.object(cutover.Path, "is_file", return_value=True):
                        cutover.checkout_guard()

    def test_available_ram_limit_is_lower_because_no_trial(self):
        mem = "MemTotal: 1980000 kB\nMemAvailable: 139000 kB\n"
        with patch.object(cutover.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=16 * 1024**3)):
            with patch.object(cutover.Path, "read_text", return_value=mem):
                cutover.memory_for_ddl()
        mem = "MemTotal: 1980000 kB\nMemAvailable: 100000 kB\n"
        with patch.object(cutover.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=16 * 1024**3)):
            with patch.object(cutover.Path, "read_text", return_value=mem):
                with self.assertRaisesRegex(RuntimeError, "memoria_insuficiente"):
                    cutover.memory_for_ddl()


if __name__ == "__main__":
    unittest.main()
