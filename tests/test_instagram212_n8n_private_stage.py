"""Offline safety tests for IG212 n8n-private staging."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "instagram212-n8n-private-stage.py"
SPEC = importlib.util.spec_from_file_location("ig212_n8n_stage", SCRIPT)
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)


class StageTests(unittest.TestCase):
    def test_stage_data_atomic_new_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "private.env"
            stage.create_bytes(path, b"SAFE=example\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            # GitHub Actions does not run as root, while the AWS operator does.
            # Keep production root ownership checks, mock only this positive path.
            with patch.object(stage, "private", side_effect=lambda p: p):
                stage.create_bytes(path, b"SAFE=example\n")
                with self.assertRaises(stage.Refuse):
                    stage.create_bytes(path, b"SAFE=changed\n")

    def test_private_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            actual = root / "a"
            actual.write_text("test")
            actual.chmod(0o600)
            link = root / "b"
            link.symlink_to(actual)
            with self.assertRaises(stage.Refuse):
                stage.private(link)

    def test_failure_output_sanitized(self):
        with patch.object(stage, "prepare",
                          side_effect=RuntimeError("SECRET=not-for-chat")), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as out:
            self.assertEqual(stage.main(), 2)
            self.assertNotIn("not-for-chat", out.getvalue())
            self.assertEqual(json.loads(out.getvalue())["resultado"], "BLOQUEADO")

    def test_does_not_contain_live_mutations(self):
        source = SCRIPT.read_text()
        for banned in ("docker compose up", "docker restart", "docker rm -f",
                       "import:workflow", "import:credentials",
                       "activate:workflow", "pg_restore", "pg_dump",
                       "UPDATE socialmei", "INSERT INTO socialmei"):
            self.assertNotIn(banned, source)

    def test_stage_declares_no_live_publishing(self):
        source = SCRIPT.read_text()
        self.assertIn('"recepcao_instagram_ativada": False', source)
        self.assertIn('"n8n_workflow_modificado": False', source)
        self.assertIn('"api_reiniciada": False', source)

    def test_export_uses_random_temporary_and_private_location(self):
        source = SCRIPT.read_text()
        self.assertIn('uuid.uuid4().hex', source)
        self.assertIn('"--output=" + tmp_path', source)
        self.assertIn('str(tmp_host)', source)
        self.assertIn("create_bytes(SRC, tmp_host.read_bytes())", source)

    def test_connected_accounts_only_and_read_only_pg(self):
        source = SCRIPT.read_text()
        self.assertIn("BEGIN READ ONLY;", source)
        self.assertIn("status='connected' AND expires_at>NOW()", source)
        self.assertIn('"connection_account_id"', source)

    def test_secret_not_in_stdout_report(self):
        source = SCRIPT.read_text()
        self.assertIn('"credencial_relay_preparada": True', source)
        self.assertNotIn('"key": key', source)
        self.assertNotIn('"meta_app_secret": meta', source)


if __name__ == "__main__":
    unittest.main()
