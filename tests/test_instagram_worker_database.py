import copy
import importlib.util
from pathlib import Path
import unittest
import json
import os
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

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
                       INSTAGRAM_REVIEWED_DATABASE_CA_FILE=str(Path(tmp) / 'database-ca.crt'),
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
            ca = next(v for v in service['volumes'] if v['target'] == '/run/database-ca.crt')
            self.assertTrue(ca['read_only'])
            self.assertFalse(ca['bind']['create_host_path'])
        self.assertNotEqual(*volumes)

    def setUp(self):
        self.api = {'Name': '/' + m.API, 'Config': {'Env': [
            'POSTGRES_HOST=' + m.HOST, 'POSTGRES_DB=' + m.DATABASE,
            'POSTGRES_USER=synthetic', 'POSTGRES_PASSWORD=private-sentinel']}}
        self.worker = {'Name': '/' + m.WORKER, 'Config': {'Env': [
            'DATABASE_URL=postgresql://synthetic@db.prisma.io/postgres',
            'PGSSLROOTCERT=/old-ca', 'PGSERVICE=old-service', 'PGPASSWORD=old-password',
            'POSTGRES_DB=historical', 'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED=true',
            'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=true', 'PRIVATE_OAUTH=preserved']}}

    def test_tls_ca_is_copied_from_existing_api_without_client_key_or_flag_changes(self):
        self.api['Id'] = 'frozen-api'
        url = 'DATABASE_URL=postgresql://synthetic@' + m.HOST + '/' + m.DATABASE
        self.api['Config']['Env'] = [url + '?sslmode=verify-full&sslrootcert=/run/database-ca.crt']
        cert = b'-----BEGIN CERTIFICATE-----\nSYNTHETIC PUBLIC CA\n-----END CERTIFICATE-----'
        with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(stdout=cert)) as run:
            self.assertEqual(m.database_ca(self.api), cert)
        self.assertEqual(run.call_args.args[0], ['docker', 'exec', 'frozen-api', 'cat', '/run/database-ca.crt'])
        with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(stdout=b'PRIVATE KEY')):
            with self.assertRaises(RuntimeError): m.database_ca(self.api)
        for suffix in ('&sslkey=/private/key', '&sslrootcert=/another/path'):
            self.api['Config']['Env'] = [url + '?sslmode=verify-full&sslrootcert=/run/database-ca.crt' + suffix]
            with patch.object(m.subprocess, 'run') as run:
                with self.assertRaises(RuntimeError): m.database_ca(self.api)
                run.assert_not_called()

    def test_old_prisma_override_is_removed_and_sender_remains_disabled(self):
        before = copy.deepcopy((self.api, self.worker))
        result = m.candidate(self.api, self.worker, 60)
        self.assertNotIn('DATABASE_URL', result)
        for key in ('PGSSLROOTCERT', 'PGSERVICE', 'PGPASSWORD'):
            self.assertNotIn(key, result)
        self.assertEqual(result['POSTGRES_DB'], m.DATABASE)
        self.assertEqual(result['POSTGRES_PASSWORD'], 'private-sentinel')
        self.assertNotIn('PRIVATE_OAUTH', result)
        self.assertEqual(result['SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED'], 'false')
        self.assertEqual(result['SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED'], 'false')
        self.assertEqual((self.api, self.worker), before)

    def test_observers_never_inherit_provider_credentials_or_the_old_workspace_cutoff(self):
        self.worker['Config']['Env'].extend([
            'SOCIALMEI_INSTAGRAM_CLIENT_SECRET=synthetic-secret', 'SOCIALMEI_SMTP_PASSWORD=synthetic-mail',
            'N8N_API_KEY=synthetic-n8n', 'SOCIALMEI_INSTAGRAM_TOKEN_VAULT_KEY=synthetic-vault',
            'SOCIALMEI_INSTAGRAM_AUTO_MENU_START_UTC=2025-01-01T00:00:00+00:00'])
        result = m.candidate(self.api, self.worker, 60)
        for key in ('PRIVATE_OAUTH', 'SOCIALMEI_INSTAGRAM_CLIENT_SECRET', 'SOCIALMEI_SMTP_PASSWORD',
                    'N8N_API_KEY', 'SOCIALMEI_INSTAGRAM_TOKEN_VAULT_KEY', 'SOCIALMEI_INSTAGRAM_AUTO_MENU_START_UTC'):
            self.assertNotIn(key, result)
        self.assertEqual(result['SOCIALMEI_QUEUE_WAKEUP_MODE'], 'poll')
        self.assertEqual(result['POSTGRES_PASSWORD'], 'private-sentinel')

    def test_start_cutoff_requires_explicit_timezone_and_is_bound_to_each_workspace(self):
        for workspace in (60, 61):
            result = m.candidate(self.api, self.worker, workspace, start_utc='2026-11-21T09:00:00-03:00')
            self.assertEqual(result['SOCIALMEI_INSTAGRAM_AUTO_MENU_START_UTC'], '2026-11-21T12:00:00+00:00')
            self.assertEqual(result['SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID'], str(workspace))
        for value in ('2026-11-21T09:00:00', 'invalid', 123):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                m.candidate(self.api, self.worker, 60, start_utc=value)

    def test_capacity_preserves_automatic_backup_and_never_counts_swap_as_ram(self):
        limited = m.observer_capacity(605)
        self.assertEqual(limited['safe_observer_count'], 1)
        self.assertFalse(limited['two_observers_fit'])
        self.assertEqual(limited['required_for_two_mib'], 704)
        self.assertEqual(m.observer_capacity(704)['safe_observer_count'], 2)
        self.assertEqual(m.observer_capacity(447)['safe_observer_count'], 0)
        for value in (-1, True, '605'):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                m.observer_capacity(value)

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
