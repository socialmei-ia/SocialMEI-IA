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


    def test_apply_rejected_without_authorization_before_runtime_access(self):
        with patch.object(sys, "argv", [
            "tool", "--backup", "/no/secret/path", "--apply"
        ]), patch.object(gate, "prepare", side_effect=AssertionError("must not prepare")
        ), patch.object(gate, "with_lock", side_effect=AssertionError("no lock")
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(gate.main(), 2)
            self.assertEqual(json.loads(output.getvalue())["motivo"],
                             "explicit_apply_authorization_missing")

    def test_rollback_rejected_without_authorization(self):
        with patch.object(sys, "argv", [
            "tool", "--backup", "/no/secret/path", "--rollback"
        ]), patch.object(gate, "secure_folder",
                        side_effect=AssertionError("no access")
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(gate.main(), 2)
            self.assertEqual(json.loads(output.getvalue())["motivo"],
                             "explicit_rollback_authorization_missing")

    def test_revert_rejects_foreign_image_before_mutating_docker(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            name = gate.TARGETS["team-api"]["name"]
            source = {"Id": "old", "Image": gate.TARGETS["team-api"]["base_id"],
                      "Config": {"Image": "socialmei-v33/team-api:old"},
                      "State": {"Running": True, "StartedAt": "old"},
                      "RestartCount": 0}
            state = {"phase": "recovery_required",
                     "attempted": ["team-api"], "restored": []}
            with patch.object(gate, "write_journal"), patch.object(
                gate, "docker_inspect", return_value={
                    "Image": "sha256:unrecognized", "State": {"Running": True}
                }
            ), patch.object(gate, "call",
                            side_effect=AssertionError("no Docker mutation")):
                with self.assertRaises(gate.Blocked):
                    gate.revert_attempted(folder, {name: source}, state)

    def test_rollback_command_only_targets_one_service(self):
        cfg = gate.TARGETS["team-gateway"]
        data = {
            "Config": {"Labels": {"com.docker.compose.project": "socialmei-team",
                      "com.docker.compose.project.working_dir": str(gate.ROOT),
                      "com.docker.compose.project.config_files": "/dummy.yaml"}}
        }
        with patch.object(gate, "compose_files", return_value=[Path("/dummy.yaml")]):
            command = gate.service_command(
                data, "team-gateway", Path("/private"), candidate=False
            )
        self.assertEqual(command[-1], "team-gateway")
        self.assertIn("--no-deps", command)
        self.assertIn("--no-build", command)
        self.assertIn("never", command)
        self.assertNotIn("team-api", command)

    def test_revert_to_baseline_requires_protection_check(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            name = gate.TARGETS["team-api"]["name"]
            source = {"Id": "old", "Image": gate.TARGETS["team-api"]["base_id"],
                      "Config": {"Image": "socialmei-v33/team-api:old"},
                      "State": {"Running": True, "StartedAt": "old"},
                      "RestartCount": 0}
            state = {"phase": "recovery_required",
                     "attempted": ["team-api"], "restored": []}
            with patch.object(gate, "write_journal"), patch.object(
                gate, "docker_inspect", return_value=source
            ), patch.object(gate, "protected_same", return_value=True) as protected:
                gate.revert_attempted(folder, {name: source}, state)
            self.assertEqual(state["phase"], "restored_previous_images")
            self.assertEqual(state["restored"], ["team-api"])
            protected.assert_called_once()

    def test_revert_partial_same_image_must_force_recreation(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            name = gate.TARGETS["team-api"]["name"]
            source = {"Id": "old", "Image": gate.TARGETS["team-api"]["base_id"],
                      "Config": {"Image": "socialmei-v33/team-api:old"},
                      "State": {"Running": True, "StartedAt": "old"},
                      "RestartCount": 0}
            partial = json.loads(json.dumps(source))
            partial["Id"] = "recreated"
            state = {"phase": "recovery_required",
                     "attempted": ["team-api"], "restored": []}
            with patch.object(gate, "write_journal"), patch.object(
                gate, "docker_inspect", return_value=partial
            ), patch.object(gate, "service_command", return_value=[
                "docker", "compose", "up", "-d", "team-api"
            ]), patch.object(gate, "call") as cmd, patch.object(
                gate, "wait_service", return_value={
                    "Config": {"Image": source["Config"]["Image"]}
                }
            ), patch.object(gate, "protected_same", return_value=True):
                gate.revert_attempted(folder, {name: source}, state)
            self.assertIn("--force-recreate", cmd.call_args.args[0])
            self.assertEqual(state["restored"], ["team-api"])

    def test_private_journal_writes_without_disclosing_contents(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "journal.json"
            gate.write_journal(path, {"phase": "before_services", "secret": "fake"})
            self.assertEqual(json.loads(path.read_text())["secret"], "fake")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            gate.write_journal(path, {"phase": "published_api_gateway_only"})
            self.assertNotIn("secret", path.read_text())


if __name__ == "__main__":
    unittest.main()
