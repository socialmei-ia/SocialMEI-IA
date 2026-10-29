"""Read-only diagnostic after a stopped production migration."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "team_v33_diagnostic", ROOT / "tools/team-v33-diagnose-stopped.py"
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
NAMES = [f"{i:03}_example.sql" for i in range(1, 32)] + [
    diagnostic.VERSION_032, diagnostic.VERSION_033
]
SHA = "c19d44b6ef6b8f125e6cafe60a7adfc0477cf454"
EMPTY = {
    "wa_bot_access": False,
    "wa_bot_conversations": False,
    "wa_bot_decisions": False,
    "me_provider_sentiment_jobs": False,
}


class DiagnoseStoppedTests(unittest.TestCase):
    def fake(self, *, ledger=None, tables=None):
        helper = SimpleNamespace(
            backup_receipt=lambda name: Path("/secret-backup"),
            stage_receipt=lambda name: (Path("/secret-source"), NAMES, SHA),
            disk_memory_preflight=lambda size: True,
        )
        migrator = SimpleNamespace(
            restore_module=lambda: helper,
            live_ledger=lambda: NAMES[:31] if ledger is None else ledger,
            live_new_tables=lambda: EMPTY if tables is None else tables,
            runtime_safety=lambda: True,
        )
        return migrator

    def run_checked(self, migrator):
        with patch.object(diagnostic, "load_migrator", return_value=migrator):
            with patch.object(diagnostic, "orphan_counts",
                              return_value={"available": True,
                                            "owned_temporary_containers": 0,
                                            "owned_temporary_volumes": 0}):
                with patch.object(diagnostic.Path, "stat") as stat:
                    stat.return_value.st_size = 12345
                    return diagnostic.inspect("backup", "stage")

    def test_031_failsafe_diagnostic_and_no_secret_paths(self):
        data = self.run_checked(self.fake())
        self.assertEqual(
            data["decision"],
            "schema_031_confirmado_diagnosticar_falha_durante_apply",
        )
        self.assertFalse(data["production_write_attempted_by_diagnostic"])
        self.assertFalse(data["provider_messages_sent_by_diagnostic"])
        self.assertEqual(data["production_migration_count"], 31)
        self.assertTrue(data["no_033_tables_present"])
        self.assertTrue(data["production_ledger_matches_stage_prefix"])
        self.assertNotIn("secret-source", json.dumps(data))
        self.assertNotIn("secret-backup", json.dumps(data))

    def test_completed_033_never_recommends_reapply(self):
        data = self.run_checked(self.fake(
            ledger=NAMES, tables={name: True for name in EMPTY}
        ))
        self.assertEqual(data["decision"], "schema_033_confirmado_nao_reaplicar")
        self.assertTrue(data["all_033_tables_present"])
        self.assertEqual(data["production_migration_count"], 33)

    def test_drift_returns_warning_without_write(self):
        data = self.run_checked(self.fake(
            ledger=NAMES[:31], tables={**EMPTY, "wa_bot_access": True}
        ))
        self.assertEqual(data["decision"], "drift_exige_revisao_sem_reaplicar")

    def test_blocked_runtime_redacts_exception_body(self):
        unsafe = self.fake()
        def blocked():
            raise RuntimeError("private app token=abc123")
        unsafe.runtime_safety = blocked
        data = self.run_checked(unsafe)
        self.assertEqual(data["checks"]["runtime_health_and_disabled_providers"],
                         "erro_interno_sanitizado")
        self.assertIn("runtime_health_and_disabled_providers",
                      data["failing_phases"])
        self.assertNotIn("private app token", json.dumps(data))
        self.assertEqual(data["decision"], "corrigir_bloqueio_sem_repetir_apply")

    def test_known_code_can_be_safely_reported(self):
        unsafe = self.fake()
        def blocked():
            raise RuntimeError("api_nao_saudavel")
        unsafe.runtime_safety = blocked
        data = self.run_checked(unsafe)
        self.assertEqual(data["checks"]["runtime_health_and_disabled_providers"],
                         "api_nao_saudavel")

    def test_no_docker_mutating_commands_in_orphan_count(self):
        commands = []
        fake = SimpleNamespace(returncode=0, stdout="owned-1\nowned-2\n")
        with patch.object(diagnostic.subprocess, "run",
                          side_effect=lambda args, **kw:
                          commands.append((args,kw)) or fake):
            status = diagnostic.orphan_counts()
        self.assertEqual(status["owned_temporary_containers"], 2)
        self.assertEqual(status["owned_temporary_volumes"], 2)
        self.assertTrue(all("ps" in args or "ls" in args for args, _ in commands))
        self.assertFalse(any("rm" in args or "run" in args for args, _ in commands))

    def test_missing_docker_is_inconclusive(self):
        with patch.object(diagnostic.subprocess, "run",
                          side_effect=OSError("socket unavailable")):
            self.assertEqual(diagnostic.orphan_counts(), {"available": False})


if __name__ == "__main__":
    unittest.main()
