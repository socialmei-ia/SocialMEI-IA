import contextlib
import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "maintenance", ROOT / "tools/team-maintenance.py"
)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "socialmei-team"
        self.private = self.root / "deploy/team/private"
        self.private.mkdir(parents=True)
        (self.private / "users.Caddyfile").write_text("fixture-hash")
        (self.root / ".env.team").write_text(
            "SOCIALMEI_TEAM_HOST=app.example.com\nTEAM_POSTGRES_PASSWORD=private-fixture\n"
        )
        workflow_dir = self.root / "n8n-workflows/equipe"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "01-conferir-conexao.json").write_bytes(
            (ROOT / "n8n-workflows/equipe/01-conferir-conexao.json").read_bytes()
        )
        old = self.base / "socialmei"
        old.mkdir()
        (old / ".env").write_text("N8N_ENCRYPTION_KEY=private-fixture-key\n")
        self.backups = self.base / "backups"
        for key, value in [
            ("ROOT", self.root),
            ("PRIVATE", self.private),
            ("BACKUPS", self.backups),
        ]:
            patcher = patch.object(maintenance, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.calls = []
        self.fail = ""
        self.cron = "0 1 * * * existing-job\n"
        patcher = patch.object(maintenance.subprocess, "run", side_effect=self.engine)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.output = io.StringIO()

    def engine(self, args, **kwargs):
        self.calls.append(args)
        if args[:2] == ["crontab", "-l"]:
            return SimpleNamespace(returncode=0, stdout=self.cron, stderr="")
        if args[:2] == ["crontab", "-"]:
            self.cron = kwargs["input"].decode()
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if "inspect" in args:
            if "{{json .Config.Env}}" in args:
                data = [
                    "DB_TYPE=postgresdb",
                    "DB_POSTGRESDB_HOST=postgres",
                    "DB_POSTGRESDB_DATABASE=n8n_actual_db",
                    "N8N_ENCRYPTION_KEY=private-fixture-key",
                ]
                return SimpleNamespace(
                    returncode=0, stdout=json.dumps(data).encode(), stderr=b""
                )
            service = "postgres" if "socialmei-postgres" in args else "n8n"
            data = {
                "com.docker.compose.project": "socialmei",
                "com.docker.compose.service": service,
            }
            return SimpleNamespace(
                returncode=0, stdout=json.dumps(data).encode(), stderr=b""
            )
        if "stdout" in kwargs:
            kwargs["stdout"].write(b"mock postgres dump")
            return SimpleNamespace(
                returncode=4 if self.fail == "dump" else 0,
                stdout=None,
                stderr=b"private error must not leak",
            )
        return SimpleNamespace(
            returncode=4 if self.fail and self.fail in args else 0,
            stdout=b"checked index",
            stderr=b"",
        )

    def test_complete_backup_has_verified_dump_configuration_and_hashes(self):
        with contextlib.redirect_stdout(self.output):
            folder = maintenance.backup()
        receipt = json.loads((folder / "concluido.json").read_text())
        for name, digest in receipt["sha256"].items():
            self.assertEqual(
                hashlib.sha256((folder / name).read_bytes()).hexdigest(), digest
            )
        with tarfile.open(folder / "configuracao.tar.gz") as archive:
            self.assertIn(".env.team", archive.getnames())
            self.assertIn("deploy/team/private/users.Caddyfile", archive.getnames())
        self.assertFalse(list(folder.glob("*.partial")))
        self.assertFalse(any("stop" in call or "down" in call for call in self.calls))
        self.assertNotIn("private-fixture", self.output.getvalue())

    def test_failed_dump_or_validation_never_creates_completion_receipt(self):
        for failure in ["dump", "pg_restore"]:
            self.fail = failure
            with self.assertRaises(RuntimeError):
                maintenance.backup()
        self.assertFalse(list(self.backups.glob("*/concluido.json")))
        self.assertFalse(list(self.backups.glob("*/*.partial")))

    def test_schedule_preserves_unrelated_jobs_and_is_idempotent(self):
        with contextlib.redirect_stdout(self.output):
            maintenance.schedule()
            maintenance.schedule()
        self.assertEqual(self.cron.count(maintenance.MARKER), 1)
        self.assertIn("existing-job", self.cron)
        self.assertIn("30 2 * * *", self.cron)
        with contextlib.redirect_stdout(self.output):
            maintenance.schedule(False)
        self.assertNotIn(maintenance.MARKER, self.cron)
        self.assertIn("existing-job", self.cron)

    def test_prepare_reuses_private_identity_and_never_embeds_token_in_workflow(self):
        with contextlib.redirect_stdout(self.output):
            first = maintenance.prepare_n8n()
            second = maintenance.prepare_n8n()
        self.assertEqual(first, second)
        token = maintenance.environment()["TEAM_N8N_READ_TOKEN"]
        self.assertNotIn(token, (self.private / "n8n-workflow.json").read_text())
        self.assertNotIn(token, self.output.getvalue())
        credential = json.loads((self.private / "n8n-credentials.json").read_text())[0]
        self.assertEqual(credential["data"]["value"], "Bearer " + token)
        self.assertEqual(
            (self.private / "n8n-credentials.json").stat().st_mode & 0o077, 0
        )

    def test_import_only_new_inactive_workflow_and_replay_does_not_overwrite_it(self):
        with (
            patch.object(maintenance, "connection", return_value={"workspace": "team"}),
            contextlib.redirect_stdout(self.output),
        ):
            maintenance.import_n8n()
            count = sum("import:workflow" in call for call in self.calls)
            maintenance.import_n8n()
        self.assertEqual(sum("import:workflow" in call for call in self.calls), count)
        self.assertEqual(count, 1)
        self.assertTrue(any("n8n_actual_db" in call for call in self.calls))
        workflow = json.loads((self.private / "n8n-workflow.json").read_text())
        self.assertFalse(workflow["active"])
        self.assertFalse((self.private / "n8n-credentials.json").exists())
        self.assertTrue(
            list(self.backups.glob("n8n-antes-importacao-*/configuracao.tar.gz"))
        )
        self.assertFalse(
            any("restart" in call or "stop" in call for call in self.calls)
        )

    def test_failed_n8n_backup_never_imports_credentials(self):
        self.fail = "dump"
        with (
            patch.object(maintenance, "connection", return_value={}),
            contextlib.redirect_stdout(self.output),
            self.assertRaises(RuntimeError),
        ):
            maintenance.import_n8n()
        self.assertFalse(any("import:credentials" in call for call in self.calls))
        self.assertFalse(
            json.loads((self.private / "n8n-installation.json").read_text())[
                "instalado"
            ]
        )
