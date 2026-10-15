import importlib.util
from pathlib import Path
import json
import subprocess
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "runtime_inventory", Path(__file__).parents[1] / "tools/runtime-inventory.py"
)
inventory_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory_module)


class RuntimeInventoryTests(unittest.TestCase):
    def test_allowlist_excludes_secrets_and_private_configuration(self):
        container = {
            "Config": {
                "Image": "service:approved",
                "Env": ["TOKEN=do-not-print"],
                "Labels": {"private": "do-not-print"},
            },
            "Image": "sha256:public-image-id",
            "State": {"Running": True, "Health": {"Status": "healthy"}},
            "Mounts": [
                {"Type": "bind", "Source": "do-not-print"},
                {"Type": "volume", "Name": "n8n_data"},
            ],
            "NetworkSettings": {"Networks": {"internal": {"secret": "do-not-print"}}},
        }
        with patch.object(
            inventory_module, "read_command", return_value=json.dumps([container])
        ):
            result = inventory_module.inspect_service("fixture")
        self.assertNotIn("do-not-print", json.dumps(result))
        self.assertEqual(result["volumes"], ["n8n_data"])
        self.assertEqual(result["networks"], ["internal"])
        self.assertEqual(result["connected"], "NÃO CONFIRMADO")

    def test_dirty_checkout_stops_before_contacting_docker(self):
        with patch.object(
            inventory_module, "read_command", side_effect=["approved-sha", " M file"]
        ) as command:
            report = inventory_module.inventory(Path("/fixture"))
        self.assertIn("blocked", report)
        self.assertEqual(command.call_count, 2)
        self.assertEqual(report["services"], {})

    def test_unavailable_services_are_not_reported_as_ready(self):
        def command(*args):
            if args[0] == "git":
                return "approved-sha" if args[-1] == "HEAD" else ""
            raise RuntimeError("private diagnostic that must not escape")

        with patch.object(inventory_module, "read_command", side_effect=command):
            report = inventory_module.inventory(Path("/fixture"))
        self.assertNotIn("private diagnostic", json.dumps(report))
        for service in report["services"].values():
            self.assertEqual(service["status"], "NÃO CONFIRMADO")

    def test_subprocess_has_no_inherited_stdin_and_does_not_echo_errors(self):
        with patch.object(inventory_module.subprocess, "run") as command:
            command.return_value = subprocess.CompletedProcess(
                [], 1, "secret", "secret"
            )
            with self.assertRaisesRegex(RuntimeError, "^Read command failed$"):
                inventory_module.read_command("docker", "inspect", "fixture")
            self.assertEqual(command.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_non_version_output_is_not_forwarded(self):
        def command(*args):
            if args[0] == "git":
                return "approved-sha" if args[-1] == "HEAD" else ""
            if args[-1] == "--version":
                return "private diagnostic instead of a version"
            return json.dumps({"/health": True, "/mensagem": False})

        with patch.object(
            inventory_module, "read_command", side_effect=command
        ), patch.object(
            inventory_module, "inspect_service", return_value={"running": True}
        ):
            report = inventory_module.inventory(Path("/fixture"))
        self.assertEqual(report["services"]["n8n"]["version"], "NÃO CONFIRMADO")
        self.assertNotIn("private diagnostic", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
