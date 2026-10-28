"""Synthetic inspection fixtures; no server, provider or real Docker calls."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'tools/integration-readiness-inspect.py'
SECRET = 'private-token-do-not-print'


def fixture():
    return {
        'Id': 'a' * 64,
        'Image': 'sha256:' + 'b' * 64,
        'Config': {
            'Image': 'socialmei-v22/team-api:' + 'c' * 40,
            'Labels': {'private-label': SECRET},
            'Env': ['SOCIALMEI_AUTH_ENABLED=true', 'SOCIALMEI_INSTAGRAM_RUNTIME_MODE=connect',
                    'SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED=false', 'SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED=false',
                    'SOCIALMEI_WAHA_REGISTRY_FILE=/run/secrets/private.json', 'SOCIALMEI_INSTAGRAM_CLIENT_SECRET=' + SECRET,
                    'DB_POSTGRESDB_DATABASE=n8n', 'WHATSAPP_DEFAULT_ENGINE=WEBJS'],
        },
        'State': {'Status': 'running', 'Health': {'Status': 'healthy', 'Log': [SECRET]}},
        'NetworkSettings': {'Networks': {'socialmei_team_egress': {'private': SECRET}}},
    }


class IntegrationInspectionTests(unittest.TestCase):
    def module(self):
        self.assertTrue(PATH.is_file(), 'Read-only integration inspector is missing')
        spec = importlib.util.spec_from_file_location('integration_inspect', PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_missing_explicit_target_never_runs_commands(self):
        m = self.module()
        with patch.object(m, 'run', side_effect=AssertionError('command executed')):
            for target in ('', None, 'production', 'all'):
                with self.assertRaises(ValueError):
                    m.inspect(target)
        with patch.object(m, 'inspect', side_effect=AssertionError('inspection executed')):
            for args in ([], ['--target', 'production'], ['--target', 'team', '--apply']):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    m.main(args)

    def test_container_summary_never_includes_env_headers_or_private_labels(self):
        m = self.module()
        summary = m.container_summary(fixture())
        text = json.dumps(summary)
        self.assertNotIn(SECRET, text)
        self.assertNotIn('private.json', text)
        self.assertEqual(summary['health'], 'healthy')
        self.assertTrue(summary['egress_network_attached'])
        self.assertTrue(summary['flags']['authentication'])
        self.assertFalse(summary['flags']['instagram_ingress'])
        self.assertTrue(summary['registry_file_configured'])
        self.assertNotIn('Env', text)

    def test_unrecognized_env_values_are_not_echoed(self):
        m = self.module()
        value = fixture()
        value['Config']['Image'] = SECRET
        value['Config']['Env'] = ['SOCIALMEI_AUTH_ENABLED=' + SECRET, 'WHATSAPP_DEFAULT_ENGINE=' + SECRET]
        summary = m.container_summary(value)
        self.assertEqual(summary['flags']['authentication'], 'invalid')
        self.assertEqual(summary['engine'], 'not_verified')
        self.assertIsNone(summary['image'])
        self.assertNotIn(SECRET, json.dumps(summary))

    def test_database_output_is_allowlisted_and_migrations_are_known(self):
        m = self.module()
        summary = m.database_summary({
            'status': 'verified_read_only', 'migrations': ['001_initial_socialmei_schema.sql', SECRET],
            'instagram_active_valid': 1, 'waha_channels': {'total': 2, 'active': 1, 'provisioned': 1, 'token': SECRET},
            'encrypted_token': SECRET, 'email': 'private@example.test',
        })
        self.assertEqual(summary['migrations'], ['001_initial_socialmei_schema.sql'])
        self.assertTrue(summary['unrecognized_migrations'])
        self.assertEqual(summary['instagram_active_valid'], 1)
        self.assertNotIn(SECRET, json.dumps(summary))
        self.assertNotIn('private@example.test', json.dumps(summary))

    def test_every_command_is_inspect_or_readonly_exec(self):
        m = self.module()
        commands = []
        def command(args, **kwargs):
            commands.append((args, kwargs))
            if args[:2] == ['docker', 'inspect']:
                return json.dumps([fixture()])
            if 'python' in args:
                self.assertIn('SET TRANSACTION READ ONLY', kwargs['input'])
                self.assertIn('statement_timeout', kwargs['input'])
                return json.dumps({'status': 'verified_read_only', 'migrations': [], 'instagram_active_valid': 1})
            self.assertIn('PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=5s', args)
            self.assertIn('SELECT', kwargs['input'])
            return json.dumps({'workflow': 'LHlqroY2xzvpYAmD', 'saved_equals_active': True,
                               'webhook_count': 1, 'possible_sender_count': 2, 'token': SECRET}) + '\n'
        with patch.object(m, 'run', side_effect=command):
            report = m.inspect('team')
        self.assertEqual(report['mode'], 'read_only')
        self.assertEqual(report['waha']['session_status'], 'not_verified')
        self.assertNotIn(SECRET, json.dumps(report))
        for args, _ in commands:
            self.assertTrue(m.command_allowed(args, _.get('input')))
            self.assertEqual(args[0], 'docker')
            self.assertIn(args[1], {'inspect', 'exec'})
        self.assertEqual(report['n8n']['workflows'][0]['webhook_count'], 1)
        self.assertEqual(report['n8n']['workflows'][0]['published_contract'], 'not_verified')

    def test_subprocess_failure_is_bounded_and_sanitized(self):
        m = self.module()
        with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, SECRET, SECRET)) as call:
            with self.assertRaises(RuntimeError) as error:
                m.run(['docker', 'inspect', m.API])
        self.assertNotIn(SECRET, str(error.exception))
        self.assertEqual(call.call_args.kwargs['timeout'], 30)
        self.assertEqual(call.call_args.args[0][:2], ['docker', '--host=unix:///var/run/docker.sock'])
        self.assertNotIn('DOCKER_HOST', call.call_args.kwargs['env'])
        with patch.object(m, 'run', side_effect=RuntimeError(SECRET)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                m.main(['--target', 'team'])
        self.assertNotIn(SECRET, output.getvalue())
        self.assertIn('not_verified', output.getvalue())

    def test_boolean_counts_are_not_accepted_as_integer_evidence(self):
        m = self.module()
        result = m.database_summary({'status': 'verified_read_only', 'migrations': [], 'instagram_active_valid': True})
        self.assertIsNone(result['instagram_active_valid'])

    def test_mutating_commands_are_refused_before_subprocess(self):
        m = self.module()
        with patch.object(m.subprocess, 'run', side_effect=AssertionError('executed')):
            for args in (['docker','restart','service'], ['docker','compose','up'], ['ssh','server'], ['docker','exec',m.API,'sh','-c','touch /tmp/written']):
                with self.assertRaises(ValueError):
                    m.run(args)

    def test_n8n_metadata_does_not_echo_urls_bodies_or_unknown_ids(self):
        m = self.module()
        raw = '\n'.join(json.dumps(value) for value in [
            {'workflow':'LHlqroY2xzvpYAmD','active':True,'saved_equals_active':False,'webhook_count':1,
             'possible_sender_count':2,'url':SECRET,'body':SECRET,'credential':SECRET},
            {'workflow':SECRET,'webhook_count':100},
        ])
        result = m.n8n_summary(raw)
        self.assertEqual(len(result['workflows']),1)
        self.assertFalse(result['workflows'][0]['saved_equals_active'])
        self.assertEqual(result['workflows'][0]['published_contract'],'not_verified')
        self.assertNotIn(SECRET,json.dumps(result))
