import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "tools/n8n-python-runner.py"
SOURCE = SCRIPT.read_text()


class ApplyTests(unittest.TestCase):
    def scenario(self, fault=None):
        import os

        previous_umask = os.umask(0o077)
        self.addCleanup(os.umask, previous_umask)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "project"
        backup = Path(temp.name) / "backup"
        private = Path(temp.name) / "private"
        root.mkdir()
        backup.mkdir()
        for name in ("compose.yaml", "compose.override.yaml", "Caddyfile", ".env"):
            (root / name).write_text("private-marker")
        with tarfile.open(backup / "configuracao.tar.gz", "w:gz") as archive:
            for file in root.iterdir():
                archive.add(file, arcname=file.name)
        env = {
            "DB_TYPE": "postgresdb",
            "N8N_ENCRYPTION_KEY": "private-marker",
            "PATH": "/bin",
        }
        n8n = {
            "Name": "/socialmei-n8n",
            "Id": "original",
            "Image": "same-image",
            "State": {"Running": True, "StartedAt": "original-time"},
            "Config": {
                "Env": [key + "=" + value for key, value in env.items()],
                "Labels": {
                    "com.docker.compose.project.config_files": str(
                        root / "compose.yaml"
                    )
                },
            },
            "Mounts": [{"Name": "socialmei_n8n_data"}],
            "NetworkSettings": {"Networks": {"socialmei_default": {}}},
        }
        state = {
            "socialmei-n8n": n8n,
            "socialmei-postgres": {
                "Name": "/socialmei-postgres",
                "Id": "database",
                "Image": "postgres",
                "State": {"StartedAt": "old"},
            },
        }
        (backup / "runtime-n8n.json").write_text(json.dumps([n8n]))

        def containers():
            return {
                c["Name"]: (c["Id"], c["Image"], c["State"]["StartedAt"])
                for c in state.values()
            }

        (backup / "containers-before.txt").write_text(
            "\n".join(
                name + "|" + "|".join(values) for name, values in containers().items()
            )
        )
        base = {
            "services": {
                "n8n": {
                    "image": "latest",
                    "environment": {
                        "DB_TYPE": "postgresdb",
                        "N8N_ENCRYPTION_KEY": "private-marker",
                    },
                    "networks": {"default": None},
                    "ports": [],
                }
            }
        }
        if fault == "image":
            n8n["Image"] = "changed"
        if fault == "file":
            (root / "Caddyfile").write_text("changed")
        if fault == "environment":
            base["services"]["n8n"]["environment"]["N8N_ENCRYPTION_KEY"] = "changed"
        operations = []

        def run(*args):
            if args[0] == "sha256sum":
                return b"checked"
            if "--format" in args:
                if str(private / "compose.python-runners.json") in args:
                    new = copy.deepcopy(base)
                    override = json.loads(
                        (private / "compose.python-runners.json").read_text()
                    )
                    for key, value in override["services"]["n8n"].items():
                        if key == "environment":
                            new["services"]["n8n"][key].update(value)
                        else:
                            new["services"]["n8n"][key] = value
                    new["services"]["python-runners"] = override["services"][
                        "python-runners"
                    ]
                    if fault == "options":
                        new["services"]["n8n"]["ports"] = ["9999:5678"]
                    return json.dumps(new).encode()
                return json.dumps(base).encode()
            if "up" in args:
                operations.append(args[-1])
                if args[-1] == "n8n":
                    n8n["Id"] = "updated"
                    overrides = json.loads(
                        (private / "compose.python-runners.json").read_text()
                    )
                    final = {**env, **overrides["services"]["n8n"]["environment"]}
                    n8n["Config"]["Env"] = [k + "=" + v for k, v in final.items()]
                else:
                    state["socialmei-python-runners"] = {
                        "Name": "/socialmei-python-runners",
                        "Id": "new-runner",
                        "Image": "runner-image",
                        "State": {"Running": True, "StartedAt": "now"},
                    }
                    if fault == "other":
                        state["socialmei-postgres"]["State"]["StartedAt"] = "changed"
            if args[-1] == "--version":
                return b"2.40.5\n"
            return b""

        namespace = {"__name__": "runner_test_module"}
        exec(compile(SOURCE, "apply.py", "exec"), namespace)
        namespace.update(
            ROOT=root,
            BACKUP=backup,
            PRIVATE=private,
            run=run,
            inspect=lambda name: state.get(name, {"Image": "runner-image"}),
            containers=containers,
        )
        output = io.StringIO()
        with patch(
            "subprocess.run", return_value=subprocess.CompletedProcess([], 0)
        ), contextlib.redirect_stdout(output):
            if fault:
                with self.assertRaises(AssertionError):
                    namespace["main"]()
            else:
                namespace["main"]()
        self.assertNotIn("private-marker", output.getvalue())
        self.assertEqual(
            operations, ["n8n", "python-runners"] if fault in (None, "other") else []
        )
        if fault is None:
            self.assertTrue((backup / "aplicado.json").exists())
            config = json.loads((private / "compose.python-runners.json").read_text())
            self.assertNotIn(
                config["services"]["n8n"]["environment"]["N8N_RUNNERS_AUTH_TOKEN"],
                output.getvalue(),
            )
            self.assertEqual(
                (private / "compose.python-runners.json").stat().st_mode & 0o777, 0o600
            )
            self.assertTrue(
                json.loads((private / "compose.python-runners.json").read_text())[
                    "networks"
                ]["python_runners"]["internal"]
            )

    def test_success_preserves_other_services_and_keeps_token_private(self):
        self.scenario()

    def test_help_requires_no_server_or_docker(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--apply", result.stdout)

    def test_missing_apply_flag_stops_before_reading_backup(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--backup", "/does-not-exist"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Informe --apply", result.stderr)

    def test_changed_image_blocks_restart(self):
        self.scenario("image")

    def test_changed_local_file_blocks_restart(self):
        self.scenario("file")

    def test_changed_environment_blocks_restart(self):
        self.scenario("environment")

    def test_changed_ports_block_restart(self):
        self.scenario("options")

    def test_other_service_restart_is_detected(self):
        self.scenario("other")


if __name__ == "__main__":
    unittest.main()
