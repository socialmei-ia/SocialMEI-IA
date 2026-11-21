"""Synthetic metadata only; never connects to PostgreSQL or Docker."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'current_backup', Path(__file__).resolve().parents[1] / 'tools/aws-postgres-backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class CurrentBackupTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            'backup_target_approved': True, 'container': backup.NAME,
            'database': 'socialmei_candidate040_20261114', 'admin_user': 'relocation_admin',
            'schema': '040', 'source': 'approved_schema040_destination',
            'current_production_backup': True}
        self.metadata = {'database': self.config['database'], 'server_version_num': 170006,
                         'versions': list(range(1, 41))}

    def test_historical_timer_never_queries_or_claims_current_database(self):
        with patch.object(backup.subprocess, 'run') as run:
            self.assertEqual(backup.current_database_provenance({}), {})
        run.assert_not_called()

    def test_current_metadata_is_read_only_bounded_and_not_restore_evidence(self):
        with patch.object(backup.subprocess, 'run', return_value=SimpleNamespace(
                stdout=json.dumps(self.metadata))) as run:
            receipt = backup.current_database_provenance(self.config)
        args, options = run.call_args
        query = args[0][-1]
        self.assertTrue(query.startswith('BEGIN READ ONLY;'))
        self.assertTrue(query.endswith('ROLLBACK;'))
        self.assertIn("statement_timeout = '3s'", query)
        self.assertEqual(options['timeout'], 15)
        self.assertTrue(options['check'])
        self.assertEqual(receipt['schema'], 40)
        self.assertTrue(receipt['metadata_verified_before_export'])
        self.assertFalse(receipt['restore_verified'])

    def test_target_drift_stops_before_any_docker_command(self):
        for key, value in [('database', 'historical'), ('container', 'other'),
                           ('backup_target_approved', False), ('schema', '041'),
                           ('source', 'historical'), ('admin_user', 'other')]:
            with self.subTest(key=key), patch.object(backup.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'target_not_approved'):
                    backup.current_database_provenance({**self.config, key: value})
                run.assert_not_called()

    def test_ledger_database_and_server_drift_reject_current_backup(self):
        for field, value in [('database', 'historical'), ('versions', list(range(1, 40))),
                             ('versions', list(range(1, 42))),
                             ('versions', [1] * 40), ('server_version_num', 160006)]:
            with self.subTest(field=field), patch.object(backup.subprocess, 'run',
                    return_value=SimpleNamespace(stdout=json.dumps({**self.metadata, field: value}))):
                with self.assertRaisesRegex(RuntimeError, 'metadata_not_verified'):
                    backup.current_database_provenance(self.config)

    def test_failure_never_leaks_stderr_and_never_starts_dump(self):
        errors = [subprocess.TimeoutExpired('psql', 15, stderr='private-sentinel'),
                  subprocess.CalledProcessError(1, 'psql', stderr='private-sentinel')]
        for error in errors:
            with self.subTest(error=type(error).__name__), TemporaryDirectory() as tmp, \
                    patch.object(backup, 'ROOT', Path(tmp)), \
                    patch.object(backup.subprocess, 'run', side_effect=error) as run:
                with self.assertRaisesRegex(RuntimeError, '^current_backup_metadata_not_verified$'):
                    backup.backup(config=self.config)
                self.assertEqual(run.call_count, 1)
                self.assertFalse((Path(tmp) / 'backups').exists())

    def test_export_receipt_carries_verified_identity_without_reopening_config(self):
        def docker(args, **options):
            if 'psql' in args:
                return SimpleNamespace(stdout=json.dumps(self.metadata))
            if 'pg_dump' in args:
                options['stdout'].write(b'SYNTHETIC ARCHIVE')
            return SimpleNamespace(returncode=0)
        with TemporaryDirectory() as tmp, patch.object(backup, 'ROOT', Path(tmp)), \
                patch.object(backup.subprocess, 'run', side_effect=docker), \
                patch.object(backup.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), \
                patch('sys.stdout'):
            backup.backup(config=self.config)
            receipt = json.loads(next((Path(tmp) / 'backups').glob('*.json')).read_text())
        self.assertEqual(receipt['database'], self.config['database'])
        self.assertEqual(receipt['schema'], 40)
        self.assertTrue(receipt['current_production_backup'])
        self.assertFalse(receipt['restore_verified'])
        self.assertFalse(receipt['external_uploaded'])


if __name__ == '__main__':
    unittest.main()
