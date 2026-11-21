import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backup_consistent', Path(__file__).resolve().parents[1] / 'tools/aws-postgres-backup.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ConsistentExportTests(unittest.TestCase):
    def config(self):
        return {'database': 'synthetic', 'export_helper_image_id': 'sha256:' + 'a' * 64,
                'export_source_dsn': 'postgresql://fixture:private-sentinel@127.0.0.1:5432/synthetic?sslmode=disable'}

    def test_remote_host_other_database_extra_options_and_mutable_image_block_before_docker(self):
        for changes in ({'export_helper_image_id': 'postgres:latest'},
                        {'export_source_dsn': self.config()['export_source_dsn'].replace('127.0.0.1', 'remote.invalid')},
                        {'export_source_dsn': self.config()['export_source_dsn'] + '&host=remote.invalid'},
                        {'database': 'another'}):
            with self.subTest(changes=changes), patch.object(m.subprocess, 'run') as run:
                with self.assertRaises(RuntimeError):
                    m.consistent_export({**self.config(), **changes}, Path('unused'), 'unused')
                run.assert_not_called()

    def test_timeout_removes_only_owned_helper_and_never_retries_export(self):
        for owned in (True, False):
            with self.subTest(owned=owned), TemporaryDirectory() as temp:
                calls = []; created_name = None; token = None
                def docker(args, **options):
                    nonlocal created_name, token
                    calls.append(args)
                    if args[1:] == ['inspect', m.NAME]:
                        value = [{'Name': '/' + m.NAME, 'Id': 'source-id', 'State': {'Running': True}}]
                    elif args[1:3] == ['image', 'inspect']:
                        value = [{'Id': self.config()['export_helper_image_id']}]
                    elif args[1] == 'create':
                        created_name = args[args.index('--name') + 1]
                        token = args[args.index('--label') + 1].split('=', 1)[1]
                        self.assertNotIn('private-sentinel', ' '.join(args))
                        self.assertIn('private-sentinel', options['env']['SOCIALMEI_EXPORT_SOURCE_DSN'])
                        return SimpleNamespace(stdout='helper-id')
                    elif args[1] == 'start':
                        raise subprocess.TimeoutExpired(args, 180)
                    elif args[1:] == ['inspect', created_name]:
                        value = [{'Config': {'Labels': {'socialmei.backup040-export': token if owned else 'foreign'}},
                                  'HostConfig': {'NetworkMode': 'container:source-id'}}]
                    elif args[1] == 'rm':
                        self.assertEqual(args, ['docker', 'rm', '-f', created_name])
                        return SimpleNamespace(stdout='')
                    else:
                        raise AssertionError('Unexpected command')
                    return SimpleNamespace(stdout=json.dumps(value))
                with patch.object(m.subprocess, 'run', side_effect=docker):
                    with self.assertRaises((subprocess.TimeoutExpired, RuntimeError)):
                        m.consistent_export(self.config(), Path(temp), 'test')
                self.assertEqual(sum(c[1] == 'start' for c in calls), 1)
                self.assertEqual(sum(c[1] == 'rm' for c in calls), int(owned))


if __name__ == '__main__':
    unittest.main()
