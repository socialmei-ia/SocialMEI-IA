"""Offline safety checks for the private Instagram #212 backup helper."""
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main, mock

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "instagram212-protected-backup.py"
spec = importlib.util.spec_from_file_location("backup212", SCRIPT)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupScriptTests(TestCase):
    def test_no_args_does_not_touch_docker_or_files(self):
        with mock.patch.object(sys, "argv", ["backup"]), mock.patch.object(
            backup, "backup", side_effect=AssertionError("must not run")
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(backup.main(), 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["resultado"], "PREPARE_ONLY")
            self.assertFalse(result["criou_backup"])

    def test_fingerprint_only_tracks_stable_identity(self):
        raw = {"Id": "container", "Image": "sha256:abc",
               "State": {"Running": True, "StartedAt": "start",
                         "Health": {"Log": ["sensitive"]}},
               "RestartCount": 0}
        expected = backup.fingerprint(raw)
        raw["State"]["Health"]["Log"] = ["secret"]
        self.assertEqual(backup.fingerprint(raw), expected)
        raw["Image"] = "sha256:changed"
        self.assertNotEqual(backup.fingerprint(raw), expected)

    def test_docker_path_must_match_project(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "compose.yaml"
            file.write_text("services: {}")
            data = {"Config": {"Labels": {
                "com.docker.compose.project": "other",
                "com.docker.compose.project.working_dir": str(backup.ROOT),
                "com.docker.compose.project.config_files": str(file),
            }}}
            with self.assertRaises(backup.GateError):
                backup.files_for(data)

    def test_missing_compose_files_fail_closed(self):
        data = {"Config": {"Labels": {
            "com.docker.compose.project": "socialmei-team",
            "com.docker.compose.project.working_dir": str(backup.ROOT),
            "com.docker.compose.project.config_files": "/no/such/compose.yaml",
        }}}
        with self.assertRaises(backup.GateError):
            backup.files_for(data)

    def test_private_tar_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            a = folder / "private.env"
            a.write_text("secret=never-printed")
            link = folder / "private-link"
            link.symlink_to(a)
            with self.assertRaises(backup.GateError):
                backup.regular(link, "no_link")

    def test_sensitive_error_never_echoed(self):
        with mock.patch.object(sys, "argv", ["backup", "--create-backup"]), mock.patch.object(
            backup, "backup", side_effect=RuntimeError("secret-private-value")
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(backup.main(), 2)
            self.assertNotIn("secret-private-value", stdout.getvalue())
            data = json.loads(stdout.getvalue())
            self.assertEqual(data["resultado"], "BLOQUEADO")
            self.assertEqual(data["producao_alterada"], "nao_comprovada_em_falha")

    def test_known_error_code_only(self):
        with mock.patch.object(sys, "argv", ["backup", "--create-backup"]), mock.patch.object(
            backup, "backup", side_effect=backup.GateError("insufficient_disk_space")
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(backup.main(), 2)
            data = json.loads(stdout.getvalue())
            self.assertEqual(data["motivo"], "insufficient_disk_space")

    def test_no_production_mutating_actions_in_tool(self):
        script = SCRIPT.read_text()
        for forbidden in ("docker compose up", "docker compose down",
                          "docker image load", "docker pull", "n8n import",
                          "docker restart", "docker stop"):
            self.assertNotIn(forbidden, script)
        self.assertIn('"--network", "none"', script)
        self.assertIn('"postgres.dump"', script)
        self.assertIn('"pg_restore"', script)
        self.assertIn('"images-before.tar"', script)


if __name__ == "__main__":
    main()
