"""Synthetic files and fake S3 only; no SDK credentials, SQL or transport."""
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('backup', Path(__file__).resolve().parents[1] / 'tools/aws-postgres-backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class S3Error(Exception):
    def __init__(self, code):
        self.response = {'Error': {'Code': code}}


class Body:
    def __init__(self, data):
        self.data = data
        self.closed = False

    def iter_chunks(self, chunk_size):
        for offset in range(0, len(self.data), 3):
            yield self.data[offset:offset + 3]

    def close(self):
        self.closed = True


class FakeS3:
    def __init__(self):
        self.meta = SimpleNamespace(endpoint_url='https://s3.example.invalid')
        self.versioning = 'Enabled'
        self.encryption = 'AES256'
        self.block = dict.fromkeys(('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets'), True)
        self.ownership = 'BucketOwnerEnforced'
        self.objects = {}
        self.current = None
        self.put_calls = []
        self.get_calls = []
        self.head_calls = []
        self.uncertain_put = False
        self.no_version = False
        self.head_denied = False
        self.change_version = False
        self.corrupt = False
        self.wrong_get_version = False

    def get_bucket_versioning(self, **kw):
        return {'Status': self.versioning}

    def get_bucket_encryption(self, **kw):
        return {'ServerSideEncryptionConfiguration': {'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': self.encryption}}]}}

    def get_public_access_block(self, **kw):
        return {'PublicAccessBlockConfiguration': self.block}

    def get_bucket_ownership_controls(self, **kw):
        return {'OwnershipControls': {'Rules': [{'ObjectOwnership': self.ownership}]}}

    def head_object(self, **kw):
        self.head_calls.append(kw)
        if self.head_denied:
            raise S3Error('403')
        version = kw.get('VersionId') or self.current
        if version not in self.objects:
            raise S3Error('404')
        data = self.objects[version]
        return {'VersionId': 'changed' if self.change_version and 'VersionId' not in kw else version,
                'ContentLength': len(data), 'ServerSideEncryption': 'AES256',
                'Metadata': {'sha256': hashlib.sha256(data).hexdigest()}}

    def put_object(self, **kw):
        self.put_calls.append({k: v for k, v in kw.items() if k != 'Body'})
        self.current = 'version-1'
        self.objects[self.current] = kw['Body'].read()
        if self.uncertain_put:
            raise TimeoutError('private provider details suppressed')
        return {} if self.no_version else {'VersionId': self.current}

    def get_object(self, **kw):
        self.get_calls.append(kw)
        data = self.objects[kw['VersionId']]
        self.last_body = Body(data + b'corrupt' if self.corrupt else data)
        return {'Body': self.last_body, 'VersionId': 'different' if self.wrong_get_version else kw['VersionId'],
                'ContentLength': len(data), 'ServerSideEncryption': 'AES256'}


class ExternalUploadTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'synthetic.dump'
        self.path.write_bytes(b'SYNTHETIC CUSTOM ARCHIVE ONLY')
        self.receipt = {'sha256': hashlib.sha256(self.path.read_bytes()).hexdigest(),
                        'bytes': self.path.stat().st_size, 'archive_index_verified': True,
                        'source': 'isolated_historical_destination', 'current_production_backup': False,
                        'external_uploaded': False}
        self.config = {'bucket': 'synthetic-private-backup', 'expected_bucket_owner': '123456789012'}
        self.client = FakeS3()

    def upload(self):
        return backup.upload_external_versioned(self.path, self.receipt, self.config, self.client)

    def checkpoint(self):
        return json.loads(self.path.with_suffix('.external.private.json').read_text())

    def test_upload_pins_version_reads_every_byte_and_keeps_historical_flag(self):
        result = self.upload()
        self.assertTrue(result['external_uploaded'])
        self.assertFalse(result['current_production_backup'])
        self.assertFalse(self.receipt['external_uploaded'])
        self.assertEqual(result['external_version_id'], 'version-1')
        self.assertEqual(self.client.get_calls[0]['VersionId'], 'version-1')
        self.assertEqual(self.client.put_calls[0]['IfNoneMatch'], '*')
        self.assertEqual(self.client.put_calls[0]['ServerSideEncryption'], 'AES256')
        self.assertEqual(self.client.get_calls[0]['ExpectedBucketOwner'], '123456789012')
        self.assertTrue(self.client.last_body.closed)
        self.assertEqual(self.checkpoint()['phase'], 'verified')

    def test_uncertain_put_restart_reconciles_without_second_upload(self):
        self.client.uncertain_put = True
        with self.assertRaisesRegex(RuntimeError, 'put_uncertain'):
            self.upload()
        self.assertEqual(self.checkpoint()['phase'], 'put_uncertain')
        self.client.uncertain_put = False
        self.assertTrue(self.upload()['external_uploaded'])
        self.assertEqual(len(self.client.put_calls), 1)

    def test_uncertain_missing_object_does_not_retry_put(self):
        self.client.uncertain_put = True
        with self.assertRaises(RuntimeError):
            self.upload()
        self.client.objects.clear()
        with self.assertRaisesRegex(RuntimeError, 'uncertain_object_missing'):
            self.upload()
        self.assertEqual(len(self.client.put_calls), 1)

    def test_verified_restart_is_idempotent_and_uses_pinned_head(self):
        self.upload()
        self.client.current = 'new-unrelated-version'
        self.client.objects[self.client.current] = b'unrelated'
        self.assertTrue(self.upload()['external_uploaded'])
        self.assertEqual(len(self.client.put_calls), 1)
        self.assertEqual(self.client.head_calls[-1]['VersionId'], 'version-1')

    def test_head_403_is_not_interpreted_as_absence(self):
        self.client.head_denied = True
        with self.assertRaisesRegex(RuntimeError, 'head_unavailable'):
            self.upload()
        self.assertEqual(self.client.put_calls, [])

    def test_existing_key_mismatch_is_not_overwritten(self):
        self.client.current = 'existing'
        self.client.objects['existing'] = b'unrelated'
        with self.assertRaisesRegex(RuntimeError, 'existing_object_mismatch'):
            self.upload()
        self.assertEqual(self.client.put_calls, [])

    def test_returned_put_version_must_match_head(self):
        self.client.change_version = True
        with self.assertRaisesRegex(RuntimeError, 'version_changed'):
            self.upload()
        self.assertEqual(self.checkpoint()['phase'], 'uploaded')
        self.assertEqual(self.client.get_calls, [])

    def test_missing_put_version_can_only_reconcile_not_put_again(self):
        self.client.no_version = True
        with self.assertRaisesRegex(RuntimeError, 'version_missing'):
            self.upload()
        self.assertTrue(self.upload()['external_uploaded'])
        self.assertEqual(len(self.client.put_calls), 1)

    def test_corruption_or_wrong_get_version_keeps_pending_receipt(self):
        for attribute in ('corrupt', 'wrong_get_version'):
            with self.subTest(attribute=attribute):
                setattr(self.client, attribute, True)
                with self.assertRaisesRegex(RuntimeError, 'readback_invalid'):
                    self.upload()
                self.assertEqual(self.checkpoint()['phase'], 'readback_pending')
                self.assertTrue(self.client.last_body.closed)
                setattr(self.client, attribute, False)
        self.assertTrue(self.upload()['external_uploaded'])
        self.assertEqual(len(self.client.put_calls), 1)

    def test_http_fails_before_storage_calls(self):
        self.client.meta.endpoint_url = 'http://s3.example.invalid'
        with self.assertRaisesRegex(RuntimeError, 'https_required'):
            self.upload()
        self.assertEqual(self.client.head_calls, [])

    def test_expected_bucket_owner_is_required(self):
        self.config.pop('expected_bucket_owner')
        with self.assertRaisesRegex(RuntimeError, 'expected_owner_required'):
            self.upload()
        self.assertEqual(self.client.put_calls, [])

    def test_existing_object_without_version_cannot_be_certified(self):
        metadata = {'VersionId': 'null', 'ContentLength': self.receipt['bytes'],
                    'ServerSideEncryption': 'AES256', 'Metadata': {'sha256': self.receipt['sha256']}}
        with patch.object(self.client, 'head_object', return_value=metadata):
            with self.assertRaisesRegex(RuntimeError, 'version_missing'):
                self.upload()
        self.assertEqual(self.client.put_calls, [])
        self.assertEqual(self.client.get_calls, [])

    def test_unversioned_unencrypted_public_or_wrong_ownership_never_writes(self):
        for attribute, value in (('versioning', 'Suspended'), ('encryption', 'aws:kms'),
                                 ('ownership', 'ObjectWriter'), ('block', {})):
            with self.subTest(attribute=attribute):
                self.client = FakeS3()
                setattr(self.client, attribute, value)
                with self.assertRaisesRegex(RuntimeError, 'security_invalid'):
                    self.upload()
                self.assertEqual(self.client.put_calls, [])

    def test_changed_checkpoint_identity_is_rejected(self):
        self.upload()
        self.config['bucket'] = 'different-bucket'
        with self.assertRaisesRegex(RuntimeError, 'checkpoint_identity_mismatch'):
            self.upload()

    def test_current_production_receipt_is_refused(self):
        self.receipt['current_production_backup'] = True
        with self.assertRaisesRegex(RuntimeError, 'artifact_receipt_invalid'):
            self.upload()
        self.assertEqual(self.client.put_calls, [])

    def test_each_public_access_block_flag_is_required(self):
        for flag in self.client.block:
            with self.subTest(flag=flag):
                self.client = FakeS3()
                self.client.block[flag] = False
                with self.assertRaisesRegex(RuntimeError, 'security_invalid'):
                    self.upload()
                self.assertEqual(self.client.put_calls, [])

    def test_bucket_security_read_denial_does_not_write(self):
        with patch.object(self.client, 'get_bucket_encryption', side_effect=S3Error('403')):
            with self.assertRaisesRegex(RuntimeError, 'security_unavailable'):
                self.upload()
        self.assertEqual(self.client.put_calls, [])

    def test_backup_resumes_only_explicit_pending_receipts_before_new_dump(self):
        root = self.path.parent
        folder = root / 'backups'
        folder.mkdir()
        (root / 'destination.private.json').write_text('{}')
        (root / 's3-backup.private.json').write_text(json.dumps(self.config))
        pending = folder / 'destination-synthetic.json'
        previous = dict(self.receipt, external_upload_requested=True)
        pending.write_text(json.dumps(previous))
        (folder / 'destination-old.json').write_text(json.dumps(self.receipt))
        module = SimpleNamespace(client=lambda *a, **kw: self.client)
        with patch.object(backup, 'ROOT', root), \
                patch.object(backup.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), \
                patch.dict('sys.modules', {'boto3': module}), \
                patch.object(backup, 'upload_external_versioned', side_effect=RuntimeError('stop_after_resume')) as upload, \
                patch.object(backup.subprocess, 'run') as docker:
            with self.assertRaisesRegex(RuntimeError, 'stop_after_resume'):
                backup.backup()
        upload.assert_called_once()
        self.assertEqual(upload.call_args.args[0], pending.with_suffix('.dump'))
        docker.assert_not_called()

    def test_local_valid_receipt_survives_external_failure(self):
        root = self.path.parent
        (root / 'destination.private.json').write_text(json.dumps({'admin_user': 'synthetic', 'database': 'synthetic'}))
        (root / 's3-backup.private.json').write_text(json.dumps(self.config))
        module = SimpleNamespace(client=lambda *a, **kw: self.client)
        def docker(args, **kwargs):
            if 'pg_dump' in args:
                kwargs['stdout'].write(b'SYNTHETIC ARCHIVE')
            return SimpleNamespace(returncode=0)
        with patch.object(backup, 'ROOT', root), \
                patch.object(backup.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), \
                patch.dict('sys.modules', {'boto3': module}), \
                patch.object(backup.subprocess, 'run', side_effect=docker), \
                patch.object(backup, 'upload_external_versioned', side_effect=RuntimeError('external_unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'external_unavailable'):
                backup.backup()
        receipts = list((root / 'backups').glob('destination-*.json'))
        self.assertEqual(len(receipts), 1)
        record = json.loads(receipts[0].read_text())
        self.assertTrue(record['archive_index_verified'])
        self.assertTrue(record['external_upload_requested'])
        self.assertFalse(record['external_uploaded'])
        self.assertTrue(receipts[0].with_suffix('.dump').is_file())


if __name__ == '__main__':
    unittest.main()
