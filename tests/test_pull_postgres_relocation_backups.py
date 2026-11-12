"""Offline validation of off-host backup paths, bytes and task security."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

TARGET = Path(__file__).resolve().parents[1] / 'tools/pull-postgres-relocation-backups.py'
spec = importlib.util.spec_from_file_location('pull_relocation_backup', TARGET)
pull = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pull)


def manifest():
    return {'historical_snapshot_only': True, 'current_production_freshness_verified': False,
            'files': [{'kind': 'original-prisma', 'path': pull.ORIGINAL, 'bytes': 3, 'sha256': 'a' * 64},
                      {'kind': 'isolated-destination', 'path': pull.REMOTE_ROOT + '/backups/destination-20261112T190000Z.dump', 'bytes': 3, 'sha256': 'b' * 64},
                      {'kind': 'private-configuration', 'path': pull.REMOTE_ROOT + '/external-packages/configuration-20261112T190000Z-a123.tar.gz', 'bytes': 3, 'sha256': 'c' * 64}]}


class ExternalBackupTests(unittest.TestCase):
    def test_manifest_requires_exact_snapshot_set_and_provenance(self):
        self.assertEqual(len(pull.checked_items(manifest())), 3)
        bad = manifest()
        bad['current_production_freshness_verified'] = True
        with self.assertRaises(ValueError):
            pull.checked_items(bad)
        bad = manifest()
        bad['files'] = bad['files'][:2]
        with self.assertRaises(ValueError):
            pull.checked_items(bad)

    def test_manifest_rejects_traversal_unrelated_paths_and_shell_fragments(self):
        for value in (pull.REMOTE_ROOT + '/backups/../destination-test.dump',
                      '/etc/passwd', pull.REMOTE_ROOT + '/backups/destination-x.dump;id',
                      pull.REMOTE_ROOT + '/data/destination-x.dump'):
            bad = manifest()
            bad['files'][1]['path'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                pull.checked_items(bad)

    def test_manifest_rejects_invalid_hash_size_and_duplicate_kind(self):
        for field, value in (('sha256', 'not-a-digest'), ('bytes', 0), ('bytes', True),
                             ('kind', 'original-prisma')):
            bad = manifest()
            bad['files'][1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                pull.checked_items(bad)

    def test_verified_copy_streams_bytes_without_returning_contents(self):
        payload = b'private-backup-bytes'
        item = {'kind': 'original-prisma', 'path': pull.ORIGINAL,
                'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
        def transport(args, **kwargs):
            self.assertEqual(args[-5:], ['sudo', '-n', 'cat', '--', pull.ORIGINAL])
            kwargs['stdout'].write(payload)
            return subprocess.CompletedProcess(args, 0, stderr=b'')
        with tempfile.TemporaryDirectory() as directory, patch.object(pull.subprocess, 'run', side_effect=transport):
            result = pull.copy_file(['ssh', 'fixed-host'], item, Path(directory))
            self.assertTrue(result['verified'])
            self.assertNotIn('private-backup-bytes', json.dumps(result))
            self.assertEqual((Path(directory) / 'original-prisma.dump').read_bytes(), payload)
            with self.assertRaises(ValueError):
                pull.copy_file(['ssh'], item, Path(directory))

    def test_truncated_or_corrupted_copy_never_becomes_a_completed_dump(self):
        item = {'kind': 'original-prisma', 'path': pull.ORIGINAL,
                'bytes': 3, 'sha256': hashlib.sha256(b'abc').hexdigest()}
        for payload, code in ((b'ab', 0), (b'xyz', 0), (b'abc', 1)):
            def transport(args, **kwargs):
                kwargs['stdout'].write(payload)
                return subprocess.CompletedProcess(args, code, stderr=b'private-error')
            with self.subTest(payload=payload, code=code), tempfile.TemporaryDirectory() as directory, \
                    patch.object(pull.subprocess, 'run', side_effect=transport):
                with self.assertRaises(ValueError):
                    pull.copy_file(['ssh'], item, Path(directory))
                self.assertFalse((Path(directory) / 'original-prisma.dump').exists())
                self.assertTrue((Path(directory) / 'original-prisma.dump.partial').exists())

    def test_task_is_interactive_least_privilege_and_contains_no_password(self):
        data = pull.task_xml('C:/Python/python.exe', 'C:/Private/pull.py', 'S-1-5-21-1000', 'C:/Private')
        root = ET.fromstring(data)
        ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
        self.assertEqual(root.findtext('.//t:Principal/t:LogonType', namespaces=ns), 'InteractiveToken')
        self.assertEqual(root.findtext('.//t:Principal/t:RunLevel', namespaces=ns), 'LeastPrivilege')
        self.assertEqual(root.findtext('.//t:Exec/t:Arguments', namespaces=ns), '"C:/Private/pull.py"')
        self.assertIsNotNone(root.find('.//t:CalendarTrigger', ns))
        self.assertIsNotNone(root.find('.//t:LogonTrigger', ns))
        self.assertNotIn('Password', data.decode('utf-16'))

    def test_registered_task_xml_handles_windows_redirected_encodings(self):
        data = pull.task_xml('C:/Python/python.exe', 'C:/Private/pull.py', 'S-1-5-21-1000', 'C:/Private')
        for raw in (data, data.decode('utf-16').encode('utf-8')):
            self.assertTrue(pull.parse_task_xml(raw).tag.endswith('Task'))


if __name__ == '__main__':
    unittest.main()
