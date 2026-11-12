"""Offline failure gates for isolated database preparation; never starts Docker."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def load(name):
    path = Path(__file__).resolve().parents[1] / 'tools' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load('aws-postgres-backup')
staging = load('aws-postgres-staging')


class PreparationFailureTests(unittest.TestCase):
    def test_failed_dump_is_only_partial_and_never_receives_a_verified_receipt(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'destination.private.json').write_text(json.dumps({
                'admin_user': 'test_admin', 'database': 'disposable_test'}))
            def fail(args, **kwargs):
                kwargs['stdout'].write(b'incomplete synthetic archive')
                return SimpleNamespace(returncode=1, stderr=b'private transport failure')
            with patch.object(backup, 'ROOT', root), \
                    patch.object(backup.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), \
                    patch.object(backup.subprocess, 'run', side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, '^destination_backup_failed$'):
                    backup.backup()
            self.assertEqual(len(list((root / 'backups').glob('*.partial'))), 1)
            self.assertEqual(list((root / 'backups').glob('*.dump')), [])
            self.assertEqual(list((root / 'backups').glob('*.json')), [])

    def test_invalid_archive_index_is_not_promoted_to_backup(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'destination.private.json').write_text(json.dumps({
                'admin_user': 'test_admin', 'database': 'disposable_test'}))
            def fake(args, **kwargs):
                if 'pg_dump' in args:
                    kwargs['stdout'].write(b'not a valid archive')
                    return SimpleNamespace(returncode=0)
                return SimpleNamespace(returncode=1)
            with patch.object(backup, 'ROOT', root), \
                    patch.object(backup.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), \
                    patch.object(backup.subprocess, 'run', side_effect=fake):
                with self.assertRaisesRegex(RuntimeError, 'backup_index_invalid'):
                    backup.backup()
            self.assertFalse(list((root / 'backups').glob('*.dump')))

    def test_scheduler_refuses_negative_restore_receipt_before_systemd_calls(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'tools').mkdir()
            (root / 'tools/aws-postgres-backup.py').write_text('test only')
            for comparison, violations in ((False, 0), (True, 1)):
                (root / 'restore-validation-receipt.json').write_text(json.dumps({
                    'comparison': {'equal': comparison}, 'foreign_key_violations': violations}))
                with patch.object(backup, 'ROOT', root), patch.object(backup.subprocess, 'run') as calls:
                    with self.assertRaisesRegex(RuntimeError, 'destination_validation_failed'):
                        backup.install_schedule()
                    calls.assert_not_called()

    def test_staging_refuses_insecure_destination_before_copying_live_configuration(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'destination.private.json').write_text('{}')
            for tls, privileged in ((False, False), (True, True)):
                (root / 'security-receipt.json').write_text(json.dumps({
                    'tls_enabled': tls, 'app_superuser': privileged}))
                with patch.object(staging, 'ROOT', root), patch.object(staging, 'run') as calls:
                    with self.assertRaisesRegex(RuntimeError, 'target_security_not_verified'):
                        staging.configure()
                    calls.assert_not_called()


if __name__ == '__main__':
    unittest.main()
