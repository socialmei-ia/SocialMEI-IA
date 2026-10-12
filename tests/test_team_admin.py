import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "tools/team-admin.py"
spec = importlib.util.spec_from_file_location("team_admin", SCRIPT)
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)


class TeamAdminTests(unittest.TestCase):
    def test_hostname_rejects_injection_and_non_host_inputs(self):
        for host in [
            "https://app.example.com",
            "app.example.com:80",
            "app.example.com/path",
            "bad.example\nrespond 200",
            "*.example.com",
            "127.0.0.1",
            "a..com",
            "-app.example.com",
        ]:
            with self.assertRaises(ValueError):
                admin.validate_host(host)
        self.assertEqual(admin.validate_host("APP.EXAMPLE.COM"), "app.example.com")

    def test_prepare_is_private_and_never_overwrites_existing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "deploy/team/private"
            with (
                patch.object(admin, "ROOT", root),
                patch.object(admin, "PRIVATE", private),
                patch.object(admin, "ENV", root / ".env.team"),
                patch.object(
                    admin, "ask_user", return_value=("mike", "$2a$14$fixture")
                ),
            ):
                admin.init("app.example.com")
                env = (root / ".env.team").read_text()
                self.assertNotIn("socialmei_dev_local", env)
                self.assertEqual((root / ".env.team").stat().st_mode & 0o777, 0o600)
                self.assertEqual(
                    (private / "users.Caddyfile").stat().st_mode & 0o777, 0o600
                )
                config = (private / "config.js").read_text()
                self.assertNotIn("$2a$", config)
                self.assertNotIn("PASSWORD", config)
                self.assertIn('"apiBaseUrl": "/api/v1"', config)
                with self.assertRaises(RuntimeError):
                    admin.init("other.example.com")
                self.assertEqual((root / ".env.team").read_text(), env)

    def test_init_rejects_a_hostname_already_used_by_n8n(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text('N8N_HOST="social.example.com"\n')
            with (
                patch.object(admin, "ROOT", root),
                patch.object(admin, "PRIVATE", root / "private"),
                patch.object(admin, "ENV", root / ".env.team"),
                self.assertRaises(ValueError),
            ):
                admin.init("social.example.com")

    def test_password_does_not_enter_command_arguments_or_error_output(self):
        password = "individual-test-password"
        result = type("Result", (), {"returncode": 0, "stdout": "$2a$14$" + "a" * 53})()
        with patch.object(admin.subprocess, "run", return_value=result) as run:
            admin.hash_password(password)
            self.assertNotIn(password, " ".join(run.call_args.args[0]))
            self.assertEqual(run.call_args.kwargs["input"], password + "\n")
        for password in ["short", "x" * 73, "a" * 12 + "\n"]:
            with self.assertRaises(ValueError):
                admin.hash_password(password)
