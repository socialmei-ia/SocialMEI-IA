import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "accounts", Path(__file__).resolve().parents[1] / "tools/team-accounts.py"
)
accounts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accounts)


class AccountActivationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.private = self.root / "deploy/team/private"
        self.private.mkdir(parents=True)
        for name, value in [("ROOT", self.root), ("PRIVATE", self.private)]:
            mock = patch.object(accounts, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        self.env = self.root / ".env.team"
        self.env.write_text(
            "TEAM_POSTGRES_PASSWORD=private-fixture-password\nSOCIALMEI_TEAM_HOST=app.example.com\n"
        )
        module = {"mode": "remote", "apiBaseUrl": "/api/v1", "workspaceKey": "team"}
        self.config = self.private / "config.js"
        self.config.write_text(
            "const SOCIALMEI_CONFIG = Object.freeze("
            + json.dumps(
                {
                    key: module
                    for key in ["clientes", "produtos", "vendas", "financeiro"]
                }
            )
            + ");\n"
        )
        self.basic = self.private / "users.Caddyfile"
        self.basic.write_text("individual $2a$14$private-hash-fixture\n")

    def result(self, count="1", code=0):
        return SimpleNamespace(returncode=code, stdout=count, stderr="private-error")

    def test_enable_requires_database_admin_and_never_restarts_or_removes_basic(self):
        output = io.StringIO()
        with (
            patch.object(accounts.subprocess, "run", return_value=self.result()) as run,
            contextlib.redirect_stdout(output),
        ):
            accounts.enable()
        self.assertIn("TEAM_AUTH_ENABLED=true", self.env.read_text())
        self.assertIn('"auth"', self.config.read_text())
        self.assertIn("$2a$14$private-hash-fixture", self.basic.read_text())
        self.assertEqual(run.call_count, 1)
        self.assertIn("exec", run.call_args.args[0])
        self.assertNotIn("up", run.call_args.args[0])
        for secret in [
            "private-fixture-password",
            "private-hash-fixture",
            "private-error",
        ]:
            self.assertNotIn(secret, output.getvalue())
        snapshot = next(self.private.glob("accounts-before-*"))
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o700)
        for file in [
            self.env,
            self.config,
            snapshot / "env.team",
            snapshot / "config.js",
        ]:
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_unprepared_admin_or_failed_database_does_not_change_config(self):
        before = (self.env.read_text(), self.config.read_text())
        for response in [self.result("0"), self.result("private-data", 1)]:
            with (
                patch.object(accounts.subprocess, "run", return_value=response),
                self.assertRaises(RuntimeError),
            ):
                accounts.enable()
            self.assertEqual((self.env.read_text(), self.config.read_text()), before)
            self.assertEqual(list(self.private.glob("accounts-before-*")), [])

    def test_local_module_or_missing_basic_is_rejected_before_database(self):
        self.basic.write_text("")
        with (
            patch.object(
                accounts.subprocess, "run", side_effect=AssertionError("must not run")
            ),
            self.assertRaises(RuntimeError),
        ):
            accounts.enable()
        self.basic.write_text("individual hash")
        self.config.write_text(
            'const SOCIALMEI_CONFIG = Object.freeze({"clientes":{"mode":"local"}});'
        )
        with (
            patch.object(
                accounts.subprocess, "run", side_effect=AssertionError("must not run")
            ),
            self.assertRaises(RuntimeError),
        ):
            accounts.enable()

    def test_second_write_failure_restores_prior_configuration(self):
        before = (self.env.read_text(), self.config.read_text())
        original = accounts.private_write
        failed = False

        def write(path, contents):
            nonlocal failed
            if path == self.config and not failed:
                failed = True
                raise OSError("private fixture error")
            original(path, contents)

        with (
            patch.object(accounts.subprocess, "run", return_value=self.result()),
            patch.object(accounts, "private_write", side_effect=write),
            self.assertRaises(OSError),
        ):
            accounts.enable()
        self.assertEqual((self.env.read_text(), self.config.read_text()), before)
