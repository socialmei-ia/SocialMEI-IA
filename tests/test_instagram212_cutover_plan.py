"""Offline tests: the #212 cutover plan is never itself a deployment."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "tools/instagram212-cutover-plan.py"
SPEC = importlib.util.spec_from_file_location("instagram212_cutover_plan", FILE)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class CutoverPlanTests(unittest.TestCase):
    def test_default_does_not_call_prepare(self):
        with patch.object(sys, "argv", ["tool", "--backup", "/not/a/real/backup"]), patch.object(
            gate, "prepare", side_effect=AssertionError("prepare should not run")
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(gate.main(), 0)
            self.assertEqual(json.loads(output.getvalue())["resultado"], "PREPARE_ONLY")

    def test_candidate_overlay_pins_only_image_and_release(self):
        api = gate.candidate_overlay("team-api")
        gw = gate.candidate_overlay("team-gateway")
        self.assertEqual(set(api["services"]["team-api"]), {"image", "environment"})
        self.assertEqual(set(gw["services"]["team-gateway"]), {"image"})
        self.assertEqual(api["services"]["team-api"]["environment"],
                         {"SOCIALMEI_RELEASE_SHA": gate.CANDIDATE})
        self.assertIn(gate.CANDIDATE, gw["services"]["team-gateway"]["image"])

    def test_model_diff_allows_only_candidate_target(self):
        base = {"services": {
            "team-api": {"image": "baseline", "environment": {
                "SOCIALMEI_RELEASE_SHA": gate.BASELINE,
                "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED": "false"
            }},
            "team-gateway": {"image": "baseline_gw"}
        }, "networks": {"default": {"external": False}}}
        proposed = json.loads(json.dumps(base))
        proposed["services"]["team-api"]["image"] = gate.candidate_overlay(
            "team-api")["services"]["team-api"]["image"]
        proposed["services"]["team-api"]["environment"][
            "SOCIALMEI_RELEASE_SHA"] = gate.CANDIDATE
        self.assertTrue(gate.safe_diff(base, proposed, "team-api"))
        proposed["services"]["team-api"]["environment"][
            "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED"] = "true"
        self.assertFalse(gate.safe_diff(base, proposed, "team-api"))

    def test_wrong_service_rejected(self):
        with self.assertRaises(gate.Blocked):
            gate.candidate_overlay("socialmei-waha")

    def test_snapshot_rejects_stopped_or_recreated(self):
        obj = {"Id": "a", "Image": "sha256:old", "RestartCount": 0,
               "State": {"Running": True, "StartedAt": "t"}}
        same = json.loads(json.dumps(obj))
        self.assertTrue(gate.same_runtime(obj, same))
        same["State"]["StartedAt"] = "new"
        self.assertFalse(gate.same_runtime(obj, same))
        same = json.loads(json.dumps(obj))
        same["State"]["Running"] = False
        self.assertFalse(gate.same_runtime(obj, same))

    def test_backup_folder_must_be_root_private(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            with self.assertRaises(gate.Blocked):
                gate.secure_folder(path)

    def test_private_tar_checks_original_bytes_and_rejects_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "secret.env"
            private.write_text("PRIVATE=synthetic\n")
            key = hashlib.sha256(str(private).encode()).hexdigest()
            archive = root / "private.tar"
            with tarfile.open(archive, "w") as tar:
                tar.add(private, arcname=f"config/{key}/.", recursive=False)
                body = json.dumps({key: str(private)}).encode()
                info = tarfile.TarInfo("config/path-map.private.json")
                info.size = len(body)
                tar.addfile(info, io.BytesIO(body))
            gate.verify_config_archive(archive)
            private.write_text("PRIVATE=changed\n")
            with self.assertRaises(gate.Blocked):
                gate.verify_config_archive(archive)

    def test_failures_have_no_private_details(self):
        with patch.object(sys, "argv", ["tool", "--backup", "/secret/path", "--prepare"]), patch.object(
            gate, "prepare", side_effect=RuntimeError("SECRET_PASSWORD_PRIVATE")
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(gate.main(), 2)
            self.assertNotIn("SECRET_PASSWORD_PRIVATE", output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["resultado"], "BLOQUEADO")

    def test_plan_has_no_release_or_migration_command(self):
        source = FILE.read_text()
        for forbidden in ("docker compose up", "docker compose down",
                          "docker restart", "docker rm", "docker run",
                          "docker image load", "docker image prune",
                          "pg_restore", "pg_dump", "git pull", "n8n import"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
