"""Contract tests for guarded, production Team 032/033 migration cutover."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / "tools/team-v33-migrate-guarded.py"
spec = importlib.util.spec_from_file_location("guarded_team_migrate", TOOL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SHA = "c19d44b6ef6b8f125e6cafe60a7adfc0477cf454"
NAMES = [f"{i:03}_fixture.sql" for i in range(1, 32)] + [
    "032_whatsapp_bot_conversations.sql",
    "033_provider_sentiment_jobs.sql",
]


class GuardedMigrationTests(unittest.TestCase):
    def source_fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        source = Path(tmp.name)
        migrations = source / "database/migrations"
        migrations.mkdir(parents=True)
        for name in NAMES[-2:]:
            (migrations / name).write_text(
                "-- reviewed additive migration\n"
                "CREATE TABLE IF NOT EXISTS socialmei.fake(x bigint);\n"
            )
        return source

    def helper(self, source):
        return SimpleNamespace(
            backup_receipt=lambda name: Path("/private/team-backup"),
            stage_receipt=lambda name: (source, NAMES, SHA),
        )

    def test_read_only_mode_never_starts_restore_or_sql_write(self):
        source = self.source_fixture()
        with patch.object(module, "restore_module", return_value=self.helper(source)):
            with patch.object(module, "live_ledger", return_value=NAMES[:31]):
                with patch.object(module, "runtime_safety", return_value=True):
                    with patch.object(module, "restore_trial", side_effect=AssertionError("restore called")):
                        with patch.object(module, "pgsql", side_effect=AssertionError("write SQL called")):
                            result = module.run("team-auto-stub", "team-v33-stub", apply=False)
        self.assertEqual(result["action"], "read_only_inspection")
        self.assertEqual(result["pending_migrations"], NAMES[-2:])
        self.assertFalse(result["production_changed"])
        self.assertFalse(result["provider_messages_sent"])

    def test_apply_reruns_restore_and_commits_032_033_atomically(self):
        source = self.source_fixture()
        calls = []
        ledger = iter([NAMES[:31], NAMES[:31], NAMES])
        with patch.object(module, "restore_module", return_value=self.helper(source)):
            with patch.object(module, "live_ledger", side_effect=lambda: next(ledger)):
                with patch.object(module, "runtime_safety", return_value=True):
                    with patch.object(module, "restore_trial", side_effect=lambda *a: calls.append("restore")):
                        with patch.object(module, "pgsql", side_effect=lambda sql, **kw: calls.append((sql, kw))):
                            result = module.run("team-auto-stub", "team-v33-stub", apply=True)
        self.assertTrue(result["production_changed"])
        self.assertEqual(result["migration_count_after"], 33)
        self.assertFalse(result["api_restarted"])
        self.assertFalse(result["provider_messages_sent"])
        self.assertEqual(calls[0], "restore")
        sql, kw = calls[1]
        self.assertTrue(kw["write"])
        self.assertEqual(len([x for x in calls if isinstance(x, tuple)]), 1)
        self.assertIn("SET LOCAL lock_timeout", sql)
        self.assertIn("pg_advisory_xact_lock(72426001)", sql)
        self.assertIn("jsonb_agg(version ORDER BY version)", sql)
        self.assertIn("032_whatsapp_bot_conversations.sql", sql)
        self.assertIn("033_provider_sentiment_jobs.sql", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS", sql)
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("Docker Compose", sql)

    def test_failed_restore_never_touches_real_db(self):
        source = self.source_fixture()
        with patch.object(module, "restore_module", return_value=self.helper(source)):
            with patch.object(module, "live_ledger", return_value=NAMES[:31]):
                with patch.object(module, "runtime_safety", return_value=True):
                    with patch.object(module, "restore_trial", side_effect=RuntimeError("trial failed")):
                        with patch.object(module, "pgsql", side_effect=AssertionError("unsafe write")):
                            with self.assertRaisesRegex(RuntimeError, "trial failed"):
                                module.run("team-auto-stub", "team-v33-stub", apply=True)

    def test_already_at_033_never_reapplies_schema(self):
        source = self.source_fixture()
        with patch.object(module, "restore_module", return_value=self.helper(source)):
            with patch.object(module, "live_ledger", return_value=NAMES):
                with patch.object(module, "runtime_safety", return_value=True):
                    with patch.object(module, "restore_trial", side_effect=AssertionError("no need")):
                        result = module.run("backup-stub", "stage-stub", apply=True)
        self.assertEqual(result["action"], "already_at_033")
        self.assertFalse(result["production_changed"])

    def test_unexpected_ledger_version_fails_closed(self):
        source = self.source_fixture()
        with patch.object(module, "restore_module", return_value=self.helper(source)):
            with patch.object(module, "live_ledger", return_value=NAMES[:31] + ["032_unreviewed.sql"]):
                with self.assertRaisesRegex(RuntimeError, "ledger_nao_e_prefixo"):
                    module.check_inputs("backup-stub", "stage-stub")

    def test_runtime_cannot_migrate_when_provider_send_is_active(self):
        api = {
            "Name": "/" + module.API_CONTAINER,
            "State": {"Running": True, "Health": {"Status": "healthy"}},
            "HostConfig": {"PortBindings": None},
            "NetworkSettings": {"Networks": {"api_db": {}}},
            "Config": {"Env": ["SOCIALMEI_AUTH_ENABLED=true",
                              "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=true"]},
        }
        database = {
            "Name": "/" + module.DB_CONTAINER,
            "State": {"Running": True, "Health": {"Status": "healthy"}},
            "HostConfig": {"PortBindings": None},
            "NetworkSettings": {"Networks": {"api_db": {}}},
            "Config": {"Env": []},
        }
        replies = iter([api, database])
        with patch.object(module.Path, "is_socket", return_value=True):
            with patch.object(module, "docker",
                              side_effect=lambda *a, **kw: json.dumps([next(replies)])):
                with self.assertRaisesRegex(RuntimeError, "provedor_ativo_bloqueia_migracao"):
                    module.runtime_safety()

    def test_psql_write_mode_requires_single_transaction_and_stdin(self):
        calls = []
        with patch.object(module.Path, "is_socket", return_value=True):
            with patch.object(module, "command",
                              side_effect=lambda argv, **kw: calls.append((argv, kw)) or ""):
                module.pgsql("SELECT 1;", write=True)
        self.assertEqual(len(calls), 1)
        argv, kw = calls[0]
        self.assertEqual(argv[:3], ["docker", "--host=unix:///var/run/docker.sock", "exec"])
        self.assertEqual(argv[-1], 'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q -1 -f -')
        self.assertEqual(kw["input_text"], "SELECT 1;")


if __name__ == "__main__":
    unittest.main()
