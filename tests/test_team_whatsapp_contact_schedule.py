import importlib.util
from pathlib import Path, PurePosixPath
import unittest
import tempfile
import json
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock, patch


class ContactScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('schedule', Path(__file__).resolve().parents[1] / 'tools/team-whatsapp-contact-schedule.py')
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_schedule_is_pinned_bounded_and_has_no_external_sender(self):
        path = PurePosixPath('/home/ubuntu/socialmei-backups/team-wa-refresh-0123456789ab/source')
        body = self.m.schedule(path, 'a' * 40)
        self.assertIn('--limit 3 --apply --confirm TEAM-1', body)
        self.assertIn('--source-sha ' + 'a' * 40, body)
        self.assertIn('* * * * * root /usr/bin/python3 ', body)
        self.assertNotIn('curl', body)

    def test_shell_metacharacters_and_non_staged_source_are_rejected(self):
        for source, sha in [(Path('/tmp/source'), 'a' * 40),
                            (Path('/home/ubuntu/socialmei-backups/bad;job/source'), 'a' * 40),
                            (Path('/home/ubuntu/socialmei-backups/safe/source'), 'a' * 40 + ';id')]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.m.schedule(source, sha)

    def test_install_and_remove_refuse_unrecognized_existing_job(self):
        for action, current, expected in [('install', b'foreign', b'ours'), ('remove', b'foreign', b'ours')]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.m.change_required(action, current, expected)
        self.assertTrue(self.m.change_required('install', None, b'ours'))
        self.assertFalse(self.m.change_required('install', b'ours', b'ours'))
        self.assertTrue(self.m.change_required('remove', b'ours', b'ours'))
        self.assertFalse(self.m.change_required('remove', None, b'ours'))

    def test_real_file_install_idempotency_and_emergency_remove_preserve_other_jobs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job, log = root / 'job', root / 'log'
            unrelated = root / 'unrelated'; unrelated.write_bytes(b'unchanged')
            def require(ok, code):
                if not ok: raise ValueError(code)
            h = SimpleNamespace(ROOT=root, require=require, private=Mock(),
                                validate_source=Mock(), validate_source_runtime=Mock())
            args = SimpleNamespace(source_sha='a' * 40, install=True, remove=False, confirm='TEAM-1')
            with patch.dict('sys.modules', {'fcntl': SimpleNamespace(flock=Mock(), LOCK_EX=2, LOCK_NB=4)}), patch.object(self.m, 'JOB', job), patch.object(self.m, 'LOG', log), \
                    patch.object(self.m, 'schedule', return_value='safe job\n'), patch.object(self.m.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                result = self.m.run(args, h)
                self.assertEqual(result['action'], 'installed')
                self.assertEqual(job.read_bytes(), b'safe job\n')
                folder = root / result['backup']
                snapshot = (folder / 'snapshot.json').read_bytes()
                self.assertEqual(hashlib.sha256(snapshot).hexdigest(), (folder / 'snapshot.sha256').read_text())
                self.assertIsNone(json.loads(snapshot)['before'])
                self.assertEqual(self.m.run(args, h)['action'], 'already_installed')
                args.install = False; args.remove = True
                h.validate_source_runtime.side_effect = RuntimeError('API unavailable')
                self.assertEqual(self.m.run(args, h)['action'], 'removed')
                self.assertFalse(job.exists())
                self.assertEqual(self.m.run(args, h)['action'], 'already_removed')
            self.assertEqual(unrelated.read_bytes(), b'unchanged')
