"""Safety regression tests for the isolated Team release 033 Git stage."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "tools" / "team-v33-stage.py"
SPEC = importlib.util.spec_from_file_location("team_v33_stage", PATH)
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)


def call(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, check=True, timeout=20)
    return result.stdout.strip()


class ReleaseStageTests(unittest.TestCase):
    def test_status_paths_are_never_exposed(self):
        s = stage.dirty_summary(
            b" M deploy/team/Caddyfile\x00?? .env.team.private\x00"
        )
        self.assertEqual(s["tracked_changes"], 1)
        self.assertEqual(s["untracked_files"], 1)
        self.assertFalse(s["only_caddy_hotfix"])
        self.assertNotIn(".env.team.private", json.dumps(s))
        self.assertTrue(stage.dirty_summary(b" M deploy/team/Caddyfile\x00")["only_caddy_hotfix"])
        self.assertFalse(stage.dirty_summary(b"R  renamed\x00oldname\x00")["only_caddy_hotfix"])

    def test_migrations_are_exact_prefix_and_do_not_write_db(self):
        names = [f"{i:03}_fixture.sql" for i in range(1, 32)] + [
            stage.MIGRATION_032, stage.MIGRATION_033,
        ]
        self.assertEqual(stage.reviewed_source(names), names)
        p = stage.plan(names[:31], names)
        self.assertEqual(p["pending"], [stage.MIGRATION_032, stage.MIGRATION_033])
        self.assertFalse(p["migration_apply_executed"])
        self.assertFalse(p["backup_created"])
        for bad in (names[:-1], names[:-2] + [stage.MIGRATION_032, "033_other.sql"],
                    names[:29] + ["030_duplicate.sql"] + names[30:]):
            with self.assertRaises(RuntimeError):
                stage.reviewed_source(bad)
        with self.assertRaises(RuntimeError):
            stage.plan(names[:30], names)
        with self.assertRaises(RuntimeError):
            stage.plan(names[:31] + ["032_fake.sql"], names)

    def test_stage_preserves_dirty_checkout_and_creates_private_clean_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            backup = Path(tmp) / "backups"
            backup.mkdir(mode=0o700)
            call("git", "init", "-q", str(root))
            call("git", "config", "user.email", "test@example.invalid", cwd=root)
            call("git", "config", "user.name", "Test", cwd=root)
            migrations = root / "database/migrations"
            migrations.mkdir(parents=True)
            names = [f"{i:03}_fixture.sql" for i in range(1, 32)] + [
                stage.MIGRATION_032, stage.MIGRATION_033,
            ]
            for name in names:
                (migrations / name).write_text("SELECT 1;\n")
            caddy = root / "deploy/team/Caddyfile"
            caddy.parent.mkdir(parents=True)
            caddy.write_text("example.com { respond ok }\n")
            (root / "README.md").write_text("STAGE FIXTURE\n")
            call("git", "add", ".", cwd=root)
            call("git", "commit", "-qm", "candidate", cwd=root)
            sha = call("git", "rev-parse", "HEAD", cwd=root)
            caddy.write_text("hotfix.example.com { respond ok }\n")
            (root / ".env.team.private").write_text("SENSITIVE_DO_NOT_PRINT=secret\n")
            prior = stage.git_audit(root)
            with patch.object(stage, "ROOT", root), patch.object(stage, "ensure_git_object"):
                with patch.object(stage, "read_ledger", return_value=names[:31]):
                    result = stage.stage(root, backup, sha)
            self.assertTrue(result["checkout_original_preservado"])
            self.assertEqual(stage.git_audit(root), prior)
            self.assertEqual(caddy.read_text(), "hotfix.example.com { respond ok }\n")
            self.assertEqual((root / ".env.team.private").read_text(),
                             "SENSITIVE_DO_NOT_PRINT=secret\n")
            output = Path(result["stage_source"])
            self.assertEqual(call("git", "rev-parse", "HEAD", cwd=output), sha)
            self.assertFalse(call("git", "status", "--porcelain", cwd=output))
            self.assertFalse((output / ".env.team.private").exists())
            self.assertEqual((output / "deploy/team/Caddyfile").read_text(),
                             "example.com { respond ok }\n")
            receipt = output.parent / "stage-receipt.json"
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
            self.assertNotIn("SENSITIVE_DO_NOT_PRINT", json.dumps(result))
            self.assertEqual(result["migration_plan"]["pending"], names[-2:])
            self.assertFalse(result["deployment_executed"])
            self.assertFalse(result["provider_messages_sent"])
            with patch.object(stage, "ROOT", root), patch.object(stage, "ensure_git_object"):
                with patch.object(stage, "read_ledger", return_value=names[:31]):
                    with self.assertRaises(RuntimeError):
                        stage.stage(root, backup, sha)

    def test_trusted_remote_is_strict_and_errors_are_sanitized(self):
        with self.assertRaises(RuntimeError):
            stage.candidate("abc")
        with self.assertRaises(RuntimeError):
            stage.dirty_summary(b"bad_entry_without_status\x00")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "private"
            folder.mkdir(mode=0o755)
            with self.assertRaises(RuntimeError):
                stage.private_root(folder)
            folder.chmod(0o700)
            self.assertEqual(stage.private_root(folder), folder)


if __name__ == "__main__":
    unittest.main()
