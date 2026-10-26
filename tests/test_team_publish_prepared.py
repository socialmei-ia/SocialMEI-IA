"""Deployment guards with synthetic manifests; no Docker or remote access."""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("publisher", Path(__file__).resolve().parents[1] / "tools/team-publish-prepared.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SHA = "a" * 40


class PreparedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.model = {"services": {"team-api": {"image": "old", "environment": {"SECRET": "synthetic-only"}, "networks": {"api": {}}}}, "networks": {"api": {"name": "owned_api"}}}
        self.live = {"NetworkSettings": {"Networks": {"owned_api": {}}}, "Mounts": [], "HostConfig": {"PortBindings": {}}}

    def test_only_image_and_declared_release_are_allowed(self):
        after = copy.deepcopy(self.model)
        after["services"]["team-api"]["image"] = "socialmei-v22/team-api:" + SHA
        after["services"]["team-api"]["environment"]["SOCIALMEI_RELEASE_SHA"] = SHA
        self.assertTrue(module.allowed_change(self.model, after, "team-api", SHA))
        after["services"]["team-api"]["environment"]["SECRET"] = "changed"
        self.assertFalse(module.allowed_change(self.model, after, "team-api", SHA))
        self.assertNotIn("SOCIALMEI_RELEASE_SHA", self.model["services"]["team-api"]["environment"])

    def test_extra_service_change_is_rejected(self):
        after = copy.deepcopy(self.model)
        after["services"]["team-postgres"] = {"image": "new"}
        self.assertFalse(module.allowed_change(self.model, after, "team-api", SHA))

    def test_runtime_network_mismatch_is_rejected(self):
        self.assertTrue(module.runtime_shape_matches(self.model, self.live, "team-api"))
        self.live["NetworkSettings"]["Networks"] = {"other": {}}
        self.assertFalse(module.runtime_shape_matches(self.model, self.live, "team-api"))

    def test_runtime_private_mounts_must_match(self):
        self.model["services"]["team-api"]["volumes"] = [{"type": "bind", "source": "/private", "target": "/config", "read_only": True}]
        self.assertFalse(module.runtime_shape_matches(self.model, self.live, "team-api"))
        self.live["Mounts"] = [{"Type": "bind", "Source": "/private", "Destination": "/config", "RW": False}]
        self.assertTrue(module.runtime_shape_matches(self.model, self.live, "team-api"))
        self.live["Mounts"][0]["RW"] = True
        self.assertFalse(module.runtime_shape_matches(self.model, self.live, "team-api"))

    def test_published_ports_are_out_of_scope(self):
        self.live["HostConfig"]["PortBindings"] = {"8000/tcp": [{"HostPort": "8000"}]}
        self.assertFalse(module.runtime_shape_matches(self.model, self.live, "team-api"))

    def test_recreate_never_builds_pulls_or_starts_dependencies(self):
        command = module.up_command(["docker", "compose", "-f", "private.json"], "team-api")
        for flag in ("--no-deps", "--no-build", "--force-recreate"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--pull") + 1], "never")
        self.assertEqual(command[-1], "team-api")
        with self.assertRaises(RuntimeError):
            module.up_command([], "team-postgres")

    def publisher(self, directory):
        value = module.Publisher.__new__(module.Publisher)
        value.folder = Path(directory)
        value.sha = SHA
        value.preflight = Mock()
        value.migrate = Mock()
        value.switch = Mock()
        value.smoke = Mock()
        return value

    def test_failed_migration_does_not_recreate_any_service(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.publisher(directory)
            value.migrate.side_effect = RuntimeError("migration rejected")
            with self.assertRaises(RuntimeError):
                value.publish()
            value.switch.assert_not_called()
            self.assertFalse((Path(directory) / "installed.json").exists())

    def test_failed_gateway_restores_both_attempted_services(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.publisher(directory)
            value.switch.side_effect = [None, RuntimeError("gateway rejected"), None]
            with self.assertRaises(RuntimeError):
                value.publish()
            self.assertEqual(value.switch.call_args_list[-1].args, ("previous", ("team-api", "team-gateway")))
            self.assertFalse((Path(directory) / "installed.json").exists())

    def test_failed_api_restores_only_api(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.publisher(directory)
            value.switch.side_effect = [RuntimeError("api rejected"), None]
            with self.assertRaises(RuntimeError):
                value.publish()
            self.assertEqual(value.switch.call_args_list[-1].args, ("previous", ("team-api",)))

    def test_failed_https_validation_does_not_mark_release_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.publisher(directory)
            value.smoke.side_effect = RuntimeError("HTTP 500")
            with self.assertRaises(RuntimeError):
                value.publish()
            self.assertEqual(value.switch.call_args_list[-1].args, ("previous", ("team-api", "team-gateway")))
            self.assertFalse((Path(directory) / "installed.json").exists())

    def test_success_records_manual_login_validation_as_pending(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            value = self.publisher(directory)
            value.publish()
            receipt = json.loads((Path(directory) / "installed.json").read_text())
            self.assertEqual(receipt["sha"], SHA)
            self.assertEqual(receipt["browser_login"], "pending_manual_validation")
            self.assertEqual([call.args[0] for call in value.switch.call_args_list], ["candidate", "candidate"])
