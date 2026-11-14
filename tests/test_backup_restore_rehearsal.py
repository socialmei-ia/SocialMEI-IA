"""Synthetic inputs and Docker fakes only; no database/archive/provider access."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('restore_runner', ROOT / 'tools/backup-restore-rehearsal.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def manifest(profile=40):
    return {'manifest_version': 1, 'large_objects': 0, 'structure': {}, 'tables': [],
            'sequences': [], 'foreign_keys': [], 'effective_permissions': [],
            'migration_ledger': [{'schema': 'socialmei', 'versions': [f'{index:03}_synthetic.sql'
                                 for index in range(1, profile + 1)]}], 'valid': True}


def fixture(folder, profile=40):
    dump, expected, approval = [Path(folder) / name for name in ('synthetic.dump', 'manifest.json', 'approval.json')]
    dump.write_bytes(b'PGDMPsynthetic-only-not-an-archive')
    expected.write_text(json.dumps(manifest(profile)))
    data = {'explicit_authorization': True, 'scope': 'isolated_restore', 'production_mutation': False,
            'dump_sha256': runner.file_hash(dump), 'manifest_sha256': runner.file_hash(expected),
            'profile': f'{profile:03}', 'postgres_major': 17, 'postgres_image_id': 'sha256:' + 'a' * 64}
    approval.write_text(json.dumps(data))
    return dump, expected, approval


class RestoreRehearsalTests(unittest.TestCase):
    def test_default_plan_and_rejection_of_remote_or_apply_flags(self):
        with patch.object(runner, 'run') as calls, contextlib.redirect_stdout(io.StringIO()):
            runner.main([])
        calls.assert_not_called()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            runner.main(['--dsn', 'postgresql://production/db'])

    def test_approval_hash_profile_and_scope_are_required_before_docker(self):
        with tempfile.TemporaryDirectory() as folder:
            dump, expected, approval = fixture(folder)
            original = json.loads(approval.read_text())
            for key, value in [('explicit_authorization', False), ('scope', 'production'),
                               ('dump_sha256', 'bad'), ('manifest_sha256', 'bad'),
                               ('profile', '041'), ('postgres_image_id', 'postgres:latest')]:
                with self.subTest(key=key), patch.object(runner, 'run') as calls:
                    approval.write_text(json.dumps({**original, key: value}))
                    with self.assertRaises(ValueError):
                        runner.rehearse(dump, expected, approval)
                    calls.assert_not_called()

    def test_038_039_040_inputs_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            for profile in (38, 39, 40):
                files = fixture(folder, profile)
                self.assertEqual(runner.inputs(*files)[0]['profile'], f'{profile:03}')
            files[0].write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                runner.inputs(*files)

    def test_cleanup_never_removes_an_unowned_container(self):
        obj = [{'Config': {'Labels': {'socialmei.isolated-restore': 'somebody-else'}},
                'HostConfig': {'NetworkMode': 'none'}}]
        with patch.object(runner, 'run', return_value=json.dumps(obj).encode()) as calls:
            with self.assertRaises(ValueError):
                runner.cleanup('docker', 'somebody-else', 'owned', 'none')
        self.assertEqual(calls.call_count, 1)

    def test_isolated_restore_and_mismatch_always_cleanup_both_owned_containers(self):
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as folder:
                files = fixture(folder)
                commands = []
                networks = {}
                labels = {}
                def command(docker, *args, **kwargs):
                    commands.append(args)
                    if args == ('context', 'inspect'):
                        return b'[{"Endpoints":{"docker":{"Host":"unix:///local.sock"}}}]'
                    if args[:2] == ('image', 'inspect'):
                        return json.dumps([{'Id': args[2]}]).encode()
                    if args[0] == 'create':
                        name = args[args.index('--name') + 1]
                        networks[name] = args[args.index('--network') + 1]
                        labels[name] = args[args.index('--label') + 1].split('=', 1)[1]
                        self.assertNotIn('--publish', args)
                        self.assertIn('--read-only', args)
                        return (('c' if name.endswith('-check') else 'b') * 64).encode()
                    if args[:2] == ('start', '-a'):
                        value = manifest()
                        if corrupt:
                            value['sequences'] = [{'last_value': 999}]
                        return json.dumps(value).encode()
                    if args[0] == 'inspect':
                        return json.dumps([{'Config': {'Labels': {'socialmei.isolated-restore': labels[args[1]]}},
                                            'HostConfig': {'NetworkMode': networks[args[1]]}}]).encode()
                    if args[0] == 'exec' and args[-2:] == ('postgres', '--version'):
                        return b'postgres (PostgreSQL) 17.11'
                    return b''
                with patch.dict(runner.os.environ, {'DOCKER_HOST': ''}), patch.object(runner, 'run', side_effect=command):
                    if corrupt:
                        with self.assertRaises(ValueError):
                            runner.rehearse(*files)
                    else:
                        result = runner.rehearse(*files)
                        self.assertTrue(result['restoration_verified'])
                        self.assertTrue(result['owned_cleanup_verified'])
                        self.assertFalse(result['production_mutation'])
                self.assertEqual(sum(args[0] == 'rm' for args in commands), 2)


if __name__ == '__main__':
    unittest.main()
