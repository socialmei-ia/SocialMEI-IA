import copy
import importlib.util
from pathlib import Path
import unittest
import json
import os
import subprocess
from tempfile import TemporaryDirectory

spec = importlib.util.spec_from_file_location('worker_db', Path(__file__).resolve().parents[1] / 'tools/instagram-worker-database.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class WorkerDatabaseTests(unittest.TestCase):
    def test_raw_environment_preserves_dollar_signs_and_rejects_injected_lines(self):
        self.assertEqual(m.environment_bytes({'PRIVATE': 'p$a#"quoted"'}), b'PRIVATE=p$a#"quoted"\n')
        for values in ({'INVALID-KEY': 'x'}, {'PRIVATE': 'a\nINJECT=true'}, {'PRIVATE': 'a\r'}, {'PRIVATE': 'a\0'}):
            with self.assertRaises(RuntimeError): m.environment_bytes(values)

    def test_actual_compose_model_keeps_two_private_scopes_and_literal_credentials(self):
        with TemporaryDirectory() as tmp:
            files = []
            for workspace in (60, 61):
                path = Path(tmp) / (str(workspace) + '.env')
                path.write_bytes(m.environment_bytes({'PRIVATE_SENTINEL': 'p$a#"quoted"',
                    'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED': 'true'}))
                files.append(str(path))
            env = dict(os.environ, INSTAGRAM_REVIEWED_WORKER_IMAGE='synthetic@sha256:' + 'a' * 64,
                       INSTAGRAM_BRILHO_ENV_FILE=files[0], INSTAGRAM_BELLA_ENV_FILE=files[1],
                       INSTAGRAM_REVIEWED_DATABASE_NETWORK='synthetic-private-network')
            model = json.loads(subprocess.run(['docker', 'compose', '-f', str(Path(__file__).resolve().parents[1] /
                'deploy/team/compose.instagram-observers.yaml'), '--profile', 'instagram-observers', 'config', '--format', 'json'],
                env=env, capture_output=True, text=True, check=True, timeout=15).stdout)
        services = model['services']
        self.assertEqual(len(services), 2)
        volumes = []
        for name, workspace in [('brilho-observer', '60'), ('bella-observer', '61')]:
            service = services[name]
            # `compose config` escapes dollars for a subsequent Compose parse.
            self.assertEqual(service['environment']['PRIVATE_SENTINEL'].replace('$$', '$'), 'p$a#"quoted"')
            self.assertEqual(service['environment']['SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED'], 'false')
            self.assertEqual(service['environment']['SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID'], workspace)
            self.assertEqual(service['restart'], 'unless-stopped')
            self.assertFalse(service.get('ports'))
            volumes.append(service['volumes'][0]['source'])
        self.assertNotEqual(*volumes)

    def setUp(self):
        self.api = {'Name': '/' + m.API, 'Config': {'Env': [
            'POSTGRES_HOST=' + m.HOST, 'POSTGRES_DB=' + m.DATABASE,
            'POSTGRES_USER=synthetic', 'POSTGRES_PASSWORD=private-sentinel']}}
        self.worker = {'Name': '/' + m.WORKER, 'Config': {'Env': [
            'DATABASE_URL=postgresql://synthetic@db.prisma.io/postgres',
            'POSTGRES_DB=historical', 'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED=true',
            'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=true', 'PRIVATE_OAUTH=preserved']}}

    def test_old_prisma_override_is_removed_and_sender_remains_disabled(self):
        before = copy.deepcopy((self.api, self.worker))
        result = m.candidate(self.api, self.worker, 60)
        self.assertNotIn('DATABASE_URL', result)
        self.assertEqual(result['POSTGRES_DB'], m.DATABASE)
        self.assertEqual(result['POSTGRES_PASSWORD'], 'private-sentinel')
        self.assertEqual(result['PRIVATE_OAUTH'], 'preserved')
        self.assertEqual(result['SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED'], 'false')
        self.assertEqual(result['SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED'], 'false')
        self.assertEqual((self.api, self.worker), before)

    def test_explicit_api_url_is_preserved_exactly_with_encoded_credentials(self):
        url = 'postgresql://synthetic:p%40ss@' + m.HOST + '/' + m.DATABASE
        self.api['Config']['Env'] = ['DATABASE_URL=' + url]
        self.assertEqual(m.candidate(self.api, self.worker, 61)['DATABASE_URL'], url)

    def test_each_workspace_has_independent_worker_scope(self):
        for workspace in (60, 61):
            result = m.candidate(self.api, self.worker, workspace)
            self.assertEqual(result['SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES'], str(workspace))
            self.assertEqual(result['SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID'], str(workspace))
        for invalid in (1, True, '60'):
            with self.assertRaises(RuntimeError):
                m.candidate(self.api, self.worker, invalid)

    def test_unknown_api_database_or_duplicate_key_fails_closed(self):
        for value in ('postgresql://synthetic@db.prisma.io/postgres',
                      'postgresql://synthetic@' + m.HOST + '/historical'):
            self.api['Config']['Env'] = ['DATABASE_URL=' + value]
            with self.assertRaises(RuntimeError):
                m.candidate(self.api, self.worker, 60)
        self.api['Config']['Env'] = ['DATABASE_URL=a', 'DATABASE_URL=b']
        with self.assertRaises(RuntimeError):
            m.candidate(self.api, self.worker, 60)


if __name__ == '__main__':
    unittest.main()
