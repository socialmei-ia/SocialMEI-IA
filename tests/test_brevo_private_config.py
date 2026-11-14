"""Synthetic credentials only; no SMTP, AWS, SQL or service activation."""
import contextlib
import getpass
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('brevo_private', ROOT / 'tools/brevo-private-config.py')
brevo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(brevo)


class BrevoPrivateTests(unittest.TestCase):
    def test_default_plan_does_not_request_credentials_or_run_commands(self):
        with patch.object(brevo, 'prepare') as prepare, patch.object(brevo.subprocess, 'run') as run, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            brevo.main([])
        prepare.assert_not_called()
        run.assert_not_called()
        self.assertFalse(json.loads(output.getvalue())['workers_enabled'])

    def test_dotenv_format_preserves_special_characters_and_disables_delivery(self):
        key = "synthetic-$#'\"=\\value"
        data = brevo.parse_content(brevo.content('smtp-login', key))
        self.assertEqual(data['SOCIALMEI_BREVO_PASSWORD'], key)
        self.assertEqual(data['SOCIALMEI_BREVO_PORT'], '587')
        self.assertEqual(data['SOCIALMEI_IDENTITY_MODE'], 'disabled')
        self.assertEqual(data['SOCIALMEI_RECOVERY_MODE'], 'disabled')

    def test_rejects_controls_empty_values_and_argument_secrets(self):
        for value in ('', 'key\nINJECT=true', 'key\r', 'key\x00', ' value', 'value '):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                brevo.content('login', value)
        with contextlib.redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit):
            brevo.main(['prepare', '--password', 'synthetic-must-not-leak'])
        self.assertNotIn('synthetic-must-not-leak', error.getvalue())

    def test_junction_or_reparse_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(Path, 'is_junction', return_value=True, create=True):
            with self.assertRaises(ValueError):
                brevo.target(Path(folder) / 'private/brevo.env')

    def test_same_database_audit_uses_runtime_whitespace_fallback(self):
        data = brevo.parse_content(brevo.content('synthetic', 'synthetic'))
        values = {'SOCIALMEI_SMTP_' + key: data['SOCIALMEI_BREVO_' + key]
                  for key in ('HOST', 'PORT', 'USER', 'PASSWORD', 'FROM')}
        values.update(SOCIALMEI_AUTH_ENABLED='true', SOCIALMEI_IDENTITY_MODE='disabled',
                      SOCIALMEI_AUTH_ORIGIN='https://example.test',
                      SOCIALMEI_RECOVERY_MODE='disabled', SOCIALMEI_PUBLIC_BOOKING_ENABLED='false',
                      DATABASE_URL=' ', POSTGRES_HOST='private', POSTGRES_DB='one',
                      POSTGRES_USER='synthetic', POSTGRES_PASSWORD='synthetic')
        model = {'services': {name: {'environment': dict(values), 'profiles': ['optional']}
                 for name in ('team-api', 'team-recovery-worker', 'team-identity-worker')}}
        model['services']['team-gateway'] = {'environment': {'SOCIALMEI_TEAM_HOST': 'example.test'}}
        self.assertTrue(brevo.audit_model(data, model)['same_database_configuration'])
        model['services']['team-api']['environment']['SOCIALMEI_AUTH_ORIGIN'] = 'https://old.example.test'
        with self.assertRaises(ValueError):
            brevo.audit_model(data, model)
        model['services']['team-api']['environment']['SOCIALMEI_AUTH_ORIGIN'] = 'https://example.test'
        model['services']['team-identity-worker']['environment']['POSTGRES_DB'] = 'other'
        with self.assertRaises(ValueError):
            brevo.audit_model(data, model)

    @unittest.skipUnless(os.name == 'nt', 'Native Windows junction test')
    def test_native_junction_cannot_redirect_credentials_into_a_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            checkout = base / 'checkout'
            checkout.mkdir()
            (checkout / '.git').mkdir()
            alias = base / 'alias'
            brevo.subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(checkout)],
                                 capture_output=True, check=True, timeout=10)
            try:
                with self.assertRaises(ValueError):
                    brevo.target(alias / 'brevo.env')
                self.assertFalse((checkout / 'brevo.env').exists())
            finally:
                require_junction = getattr(alias, 'is_junction', lambda: False)()
                self.assertTrue(require_junction)
                os.rmdir(alias)

    def test_no_terminal_fails_before_asking_for_key(self):
        with patch.object(brevo.sys.stdin, 'isatty', return_value=False), patch.object(brevo.getpass, 'getpass') as hidden:
            with self.assertRaises(ValueError):
                brevo.prepare(Path(tempfile.gettempdir()) / 'not-created.env')
        hidden.assert_not_called()

    def test_no_overwrite_no_git_path_and_no_echo_fallback(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(brevo.sys.stdin, 'isatty', return_value=True), \
                patch.object(brevo.sys.stderr, 'isatty', return_value=True):
            existing = Path(folder) / 'existing.env'
            existing.write_text('preserve')
            with self.assertRaises(ValueError):
                brevo.prepare(existing, hidden=lambda _: self.fail('No prompt for existing file'))
            self.assertEqual(existing.read_text(), 'preserve')
            with self.assertRaises(ValueError):
                brevo.target(ROOT / 'test-results/forbidden.env')
            def fallback(_):
                warnings.warn('synthetic warning', getpass.GetPassWarning)
            with self.assertRaises(getpass.GetPassWarning):
                brevo.prepare(Path(folder) / 'private/new.env', hidden=fallback)

    def test_native_private_creation_inspection_and_literal_key_without_output(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(brevo.sys.stdin, 'isatty', return_value=True), \
                patch.object(brevo.sys.stderr, 'isatty', return_value=True), contextlib.redirect_stdout(io.StringIO()) as output:
            key = "synthetic-$#'\"=\\value"
            values = iter(['smtp-login', key, key])
            path = Path(folder) / 'private/brevo.env'
            result = brevo.prepare(path, hidden=lambda _: next(values))
            self.assertTrue(result['private_config_created'])
            self.assertTrue(brevo.inspect(path)['private_config_valid'])
            self.assertEqual(brevo.parse_content(path.read_text())['SOCIALMEI_BREVO_PASSWORD'], key)
            self.assertEqual(output.getvalue(), '')
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(list(path.parent.glob('*.partial')))


if __name__ == '__main__':
    unittest.main()
