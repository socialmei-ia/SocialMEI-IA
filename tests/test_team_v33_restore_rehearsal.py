"""Offline regression tests for restoring the real Team dump into owned resources."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "team_restore", ROOT / "tools/team-v33-restore-rehearsal.py"
)
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class RestoreTrialTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.backups = self.root / "backups"
        self.backups.mkdir(mode=0o700)
        patcher = patch.object(restore, "BACKUPS", self.backups)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, path, value):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(value)
        path.chmod(0o600)

    def fixtures(self):
        name = "team-auto-20261028-234141-5dc482"
        backup = self.backups / name
        backup.mkdir(mode=0o700)
        values = {
            "equipe.dump": b"synthetic private dump" * 12,
            "configuracao.tar.gz": b"only fixture; never extract\n",
            "conteudo.txt": b"only fixture\n",
        }
        for filename, raw in values.items():
            self.write(backup / filename, raw)
        receipt = {
            "formato": "socialmei-team-backup", "workspace": "team",
            "sha256": {
                k: hashlib.sha256(v).hexdigest() for k, v in values.items()
            },
        }
        self.write(backup / "concluido.json", json.dumps(receipt).encode())
        stage = self.backups / "team-v33-c19d44b6ef6b"
        stage.mkdir(mode=0o700)
        source = stage / "source" / "database" / "migrations"
        source.mkdir(mode=0o700, parents=True)
        for i in range(1, 32):
            self.write(source / f"{i:03}_fixture.sql", b"SELECT 1;\n")
        m32 = b"CREATE TABLE IF NOT EXISTS socialmei.wa_bot_access(id int);\n"
        m33 = b"CREATE TABLE IF NOT EXISTS socialmei.me_provider_sentiment_jobs(id int);\n"
        self.write(source / restore.VERSION_032, m32)
        self.write(source / restore.VERSION_033, m33)
        sr = {
            "candidate_sha": "c19d44b6ef6b8f125e6cafe60a7adfc0477cf454",
            "stage_clean": True, "checkout_original_preservado": True,
            "deployment_executed": False,
            "new_migration_sha256": {
                restore.VERSION_032: hashlib.sha256(m32).hexdigest(),
                restore.VERSION_033: hashlib.sha256(m33).hexdigest(),
            },
        }
        self.write(stage / "stage-receipt.json", json.dumps(sr).encode())
        return name, stage.name

    def test_exact_backup_receipt_and_no_config_extraction(self):
        name, _ = self.fixtures()
        self.assertEqual(restore.backup_receipt(name), self.backups / name)
        with self.assertRaises(RuntimeError):
            restore.backup_receipt("../team-auto-20261028-234141-5dc482")
        dump = self.backups / name / "equipe.dump"
        dump.write_bytes(b"tampered" * 40)
        with self.assertRaises(RuntimeError):
            restore.backup_receipt(name)

    def test_restore_requires_clean_reviewed_stage_and_exact_hash(self):
        _, name = self.fixtures()
        source, names, sha = restore.stage_receipt(name)
        self.assertEqual(len(names), 33)
        self.assertTrue(sha.startswith("c19d44b6ef6b"))
        self.assertTrue(source.is_dir())
        target = source / "database/migrations" / restore.VERSION_033
        target.write_text("DROP DATABASE live;")
        with self.assertRaises(RuntimeError):
            restore.stage_receipt(name)

    def test_unsafe_temporary_container_is_rejected(self):
        name, volume, token = "socialmei-restore-a", "socialmei-restore-data-a", "a"
        base = {
            "Name": "/" + name,
            "Config": {"Labels": {restore.LABEL: token}},
            "HostConfig": {"NetworkMode": "none", "PortBindings": None, "Privileged": False},
            "NetworkSettings": {"Ports": {"5432/tcp": None}},
            "Mounts": [
                {"Type": "volume", "Name": volume,
                 "Destination": "/var/lib/postgresql/data"}
            ],
        }
        restore.validate_trial([base], name, volume, token)
        for change in [
            {"HostConfig": {"NetworkMode": "bridge", "PortBindings": None}},
            {"HostConfig": {"NetworkMode": "none",
                            "PortBindings": {"5432/tcp": [{"HostPort": "15432"}]}}},
            {"Config": {"Labels": {restore.LABEL: "wrong"}}},
        ]:
            bad = {**base, **change}
            with self.assertRaises(RuntimeError):
                restore.validate_trial([bad], name, volume, token)

    def test_original_counts_are_nonnegative_and_never_disclosed(self):
        self.assertEqual(restore.restore_sql({"crm_clientes": 3}), {"crm_clientes": 3})
        for invalid in ({"table": -1}, {"table": "3"}, {"PII@name": 1}):
            with self.assertRaises(RuntimeError):
                restore.restore_sql(invalid)

    def test_rehearsal_validates_ledger_and_counts_without_production_calls(self):
        trial = restore.Rehearsal()
        commands = []
        query_outputs = iter([
            [f"{i:03}_fixture.sql" for i in range(1, 32)],
            {"crm_clientes": 3, "schema_migrations": 31,
             **{f"t{i}": 0 for i in range(10)}},
            [f"{i:03}_fixture.sql" for i in range(1, 32)] +
            [restore.VERSION_032, restore.VERSION_033],
            {"crm_clientes": 3, "schema_migrations": 33,
             **{f"t{i}": 0 for i in range(10)},
             "wa_bot_access": 0, "wa_bot_conversations": 0,
             "me_provider_sentiment_jobs": 0},
        ])
        # The ledger is intentionally expected to grow, unlike the user-data tables.
        # A separate check below proves no mutation reaches the live database.
        with tempfile.TemporaryDirectory() as t:
            source = Path(t)
            backup = source / "backup"
            backup.mkdir()
            (backup / "equipe.dump").write_bytes(b"fixture")
            migrations = source / "database/migrations"
            migrations.mkdir(parents=True)
            names = [f"{i:03}_fixture.sql" for i in range(1, 32)] + [
                restore.VERSION_032, restore.VERSION_033
            ]
            for i in names[-2:]:
                (migrations / i).write_text("SELECT 1;\n")
            with patch.object(trial, "start", lambda *args: None):
                with patch.object(restore, "docker", side_effect=lambda *args, **kw: commands.append((args, kw)) or ""):
                    with patch.object(restore, "json_query", side_effect=lambda *args: next(query_outputs)):
                        with self.assertRaisesRegex(RuntimeError, "dados_originais_alterados"):
                            trial.execute(backup, source, names)
            self.assertTrue(commands)
            self.assertTrue(all("socialmei-team-team-postgres-1" not in str(x) for x in commands))
            self.assertTrue(any("pg_restore" in str(x) for x in commands))
            self.assertTrue(any("032_whatsapp_bot_conversations" in str(x) for x in commands))

    def test_cleanup_only_operates_on_owned_resources(self):
        trial = restore.Rehearsal()
        trial.created_container = True
        trial.created_volume = True
        invocations = []
        with patch.object(trial, "assert_owned_container", return_value=None):
            with patch.object(trial, "assert_owned_volume", return_value=None):
                with patch.object(restore, "docker", side_effect=lambda *x, **kw: invocations.append(x) or ""):
                    self.assertEqual(trial.cleanup(), [])
        self.assertTrue(trial.cleaned)
        self.assertEqual(invocations, [("rm", "-f", "-v", trial.name),
                                       ("volume", "rm", trial.volume)])


if __name__ == "__main__":
    unittest.main()
