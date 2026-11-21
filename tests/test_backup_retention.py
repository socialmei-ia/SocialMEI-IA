import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('retention', Path(__file__).resolve().parents[1] / 'tools/backup-retention.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RetentionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.now = datetime(2026, 11, 21, tzinfo=timezone.utc)
        self.paths = []
        for index in range(30):
            stamp = (self.now - timedelta(days=70 + index)).strftime('%Y%m%dT%H%M%SZ')
            dump = self.folder / ('destination-' + stamp + '.dump')
            dump.write_bytes(b'SYNTHETIC ARCHIVE')
            receipt = {'created_at_utc': stamp, 'database': 'socialmei_candidate040_20261114',
                       'schema': 40, 'current_production_backup': True,
                       'metadata_verified_before_export': True, 'archive_index_verified': True,
                       'bytes': dump.stat().st_size, 'sha256': hashlib.sha256(dump.read_bytes()).hexdigest(),
                       'external_uploaded': True, 'external_version_id': 'version-one'}
            path = dump.with_suffix('.json'); path.write_text(json.dumps(receipt))
            self.paths.append(path)

    def proof(self, path, **changes):
        receipt = json.loads(path.read_text())
        value = {'sha256': receipt['sha256'], 'independent_restore_equal': True,
                 'comparison': {'equal': True}, 'external_version_id': 'version-one'}
        path.with_suffix('.restore.private.json').write_text(json.dumps({**value, **changes}))

    def test_no_deletion_without_independent_version_bound_restore(self):
        result = m.retention(self.folder, self.now)
        self.assertEqual(result['files_deleted'], 0)
        self.assertEqual(sum(r['action'] == 'keep_retention' for r in result['records']), 24)
        self.assertEqual(sum(r['action'] == 'keep_external_restore_unproven' for r in result['records']), 6)
        self.assertEqual(len(list(self.folder.glob('*.dump'))), 30)

    def test_old_backup_requires_matching_external_restore_and_still_never_deletes(self):
        path = self.paths[-1]
        self.proof(path)
        result = m.retention(self.folder, self.now)
        row = next(r for r in result['records'] if r['receipt'] == path.name)
        self.assertEqual(result['blocked'], [])
        self.assertEqual(row['action'], 'eligible_after_approval')
        self.assertTrue(path.with_suffix('.dump').exists())
        for changes in ({'sha256': 'wrong'}, {'external_version_id': 'another-version'},
                        {'comparison': {'equal': False}}):
            self.proof(path, **changes)
            result = m.retention(self.folder, self.now)
            row = next(r for r in result['records'] if r['receipt'] == path.name)
            self.assertEqual(row['action'], 'keep_external_restore_unproven')

    def test_corruption_and_historical_receipts_are_preserved(self):
        self.paths[0].with_suffix('.dump').write_bytes(b'CORRUPTED')
        receipt = json.loads(self.paths[1].read_text()); receipt['database'] = 'historical'
        self.paths[1].write_text(json.dumps(receipt))
        result = m.retention(self.folder, self.now)
        self.assertEqual(len(result['blocked']), 2)
        self.assertEqual(result['files_deleted'], 0)

    def test_native_restore_receipt_requires_full_comparison_and_matching_external_version(self):
        path = self.paths[-1]; receipt = json.loads(path.read_text())
        proof = {'dump_sha256': receipt['sha256'], 'restoration_verified': True,
                 'profile': '040', 'verification_mode': 'full_comparison',
                 'source_contents_compared': True, 'archive_integrity_verified': True,
                 'owned_cleanup_verified': True, 'production_mutation': False,
                 'external_version_id': 'version-one', 'external_object_sha256': receipt['sha256'],
                 'external_receipt_sha256': 'a' * 64}
        def action(changes):
            path.with_suffix('.restore.private.json').write_text(json.dumps({**proof, **changes}))
            result = m.retention(self.folder, self.now)
            self.assertEqual(result['files_deleted'], 0)
            return next(row['action'] for row in result['records'] if row['receipt'] == path.name)
        self.assertEqual(action({}), 'eligible_after_approval')
        for changes in ({'profile': '041'}, {'verification_mode': 'archive_integrity'},
                        {'external_version_id': 'different'}, {'external_receipt_sha256': None},
                        {'owned_cleanup_verified': False}):
            self.assertEqual(action(changes), 'keep_external_restore_unproven')

    def test_private_report_is_replaced_atomically_without_deleting_archives(self):
        report = self.folder / 'retention-report.private.json'
        result = m.retention(self.folder, self.now)
        m.write_report(self.folder, report, result)
        m.write_report(self.folder, report, result)
        self.assertEqual(json.loads(report.read_text()), result)
        self.assertEqual(len(list(self.folder.glob('*.dump'))), 30)
        self.assertEqual(list(self.folder.glob('*.partial')), [])
        if os.name != 'nt':
            self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        for invalid in (self.folder / 'destination-fake.json', self.folder.parent / report.name):
            with self.assertRaisesRegex(ValueError, 'private_retention_report_required'):
                m.write_report(self.folder, invalid, result)

    def test_scheduled_report_exits_nonzero_on_corruption_to_trigger_service_alert(self):
        self.paths[0].with_suffix('.dump').write_bytes(b'CORRUPTED')
        report = self.folder / 'retention-report.private.json'
        result = subprocess.run([sys.executable, str(Path(m.__file__)),
                                 '--directory', str(self.folder), '--report', str(report)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['blocked_receipts'], 1)
        self.assertEqual(len(json.loads(report.read_text())['blocked']), 1)
        self.assertEqual(len(list(self.folder.glob('*.dump'))), 30)

    def test_latest_daily_and_weekly_copies_are_preserved(self):
        for index, path in enumerate(self.paths):
            receipt = json.loads(path.read_text())
            receipt['created_at_utc'] = (self.now - timedelta(days=index // 3)).strftime('%Y%m%dT%H%M%SZ')
            path.write_text(json.dumps(receipt)); self.proof(path)
        result = m.retention(self.folder, self.now)
        # 24 latest plus the first backup of each older day.
        self.assertGreater(sum(r['action'] == 'keep_retention' for r in result['records']), 24)


if __name__ == '__main__':
    unittest.main()
