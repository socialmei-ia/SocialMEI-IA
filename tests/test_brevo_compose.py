"""Opt-in offline Compose rendering only; never starts Docker services."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('brevo_fixture', ROOT / 'tools/brevo-private-config.py')
brevo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(brevo)
DOCKER = shutil.which('docker') or str(Path(os.environ.get('LOCALAPPDATA', '')) /
    'Programs/DockerDesktop/resources/bin/docker.exe')


@unittest.skipUnless(os.getenv('SOCIALMEI_BREVO_COMPOSE_TEST') == 'true', 'Requires explicit offline Compose rendering')
class BrevoComposeTests(unittest.TestCase):
    def render(self, folder, *, brevo_enabled, ambient=True):
        empty = folder / 'empty.env'
        empty.write_text('')
        raw = folder / 'brevo.env'
        raw.write_text(brevo.content('synthetic-login', self.key))
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('SOCIALMEI_', 'TEAM_', 'COMPOSE_', 'POSTGRES_'))
               and key != 'DATABASE_URL'}
        env.update(TEAM_POSTGRES_PASSWORD='synthetic', SOCIALMEI_TEAM_HOST='example.test',
                   TEAM_AUTH_ENABLED='true', TEAM_APPLICATION_DATABASE_URL='postgresql://synthetic@private/test',
                   SOCIALMEI_API_IMAGE='sha256:' + 'a' * 64,
                   SOCIALMEI_GATEWAY_IMAGE='sha256:' + 'b' * 64,
                   SOCIALMEI_BREVO_ENV_FILE=str(raw), SOCIALMEI_SMTP_HOST='ambient.invalid',
                   SOCIALMEI_SMTP_PASSWORD='ambient-synthetic', SOCIALMEI_SMTP_PORT='465',
                   SOCIALMEI_IDENTITY_MODE='enforced', SOCIALMEI_RECOVERY_MODE='smtp')
        if not ambient:
            for key in ('SOCIALMEI_SMTP_HOST', 'SOCIALMEI_SMTP_PASSWORD', 'SOCIALMEI_SMTP_PORT'):
                env.pop(key, None)
        args = [DOCKER, 'compose', '--env-file', str(empty)]
        files = ['compose.team.yaml', 'compose.team-recovery.yaml', 'compose.team-identity.yaml',
                 'compose.team-instagram-auto.yaml', 'compose.team-public-booking.yaml', 'compose.team-release040.yaml']
        if brevo_enabled:
            args.extend(['--env-file', str(raw)])
            files.append('compose.team-brevo.yaml')
        for file in files:
            args.extend(['-f', str(ROOT / file)])
        result = subprocess.run(args + ['--profile', '*', 'config', '--format', 'json'],
                                env=env, capture_output=True, text=True, timeout=30, cwd=ROOT)
        self.assertEqual(result.returncode, 0, 'Offline Compose render failed; requires reviewed Compose version')
        inputs = subprocess.run(args + ['--profile', '*', 'config', '--environment'],
                                env=env, capture_output=True, text=True, timeout=30, cwd=ROOT)
        self.assertEqual(inputs.returncode, 0)
        self.interpolation_inputs = dict(line.split('=', 1) for line in inputs.stdout.splitlines() if '=' in line)
        model = json.loads(result.stdout)
        if brevo_enabled:
            audit = brevo.audit_model(brevo.parse_content(raw.read_text()), model)
            self.assertTrue(audit['three_consumers_match_private_config'])
        return model

    def test_three_consumers_receive_literal_credentials_while_delivery_is_disabled(self):
        self.key = "synthetic-$#'\"=\\value"
        with tempfile.TemporaryDirectory() as temp:
            before = self.render(Path(temp), brevo_enabled=False)
            after = self.render(Path(temp), brevo_enabled=True)
            self.assertEqual(self.interpolation_inputs['SOCIALMEI_BREVO_PASSWORD'], self.key)
        self.assertEqual(before['networks'], after['networks'])
        for name in ('team-api', 'team-recovery-worker', 'team-identity-worker'):
            one, two = before['services'][name], after['services'][name]
            config = two['environment']
            # Compose serializes literal dollars as $$ to make its config reusable.
            self.assertEqual(config['SOCIALMEI_SMTP_PASSWORD'], self.key.replace('$', '$$'))
            self.assertEqual(config['SOCIALMEI_SMTP_HOST'], 'smtp-relay.brevo.com')
            self.assertEqual(config['SOCIALMEI_SMTP_PORT'], '587')
            self.assertEqual(config['SOCIALMEI_SMTP_FROM'], 'servermeiiafacepe@gmail.com')
            self.assertEqual(config['SOCIALMEI_IDENTITY_MODE'], 'disabled')
            self.assertEqual(config['SOCIALMEI_RECOVERY_MODE'], 'disabled')
            self.assertEqual(config['DATABASE_URL'], 'postgresql://synthetic@private/test')
            for key in ('image', 'networks', 'volumes', 'profiles', 'command', 'depends_on'):
                self.assertEqual(one.get(key), two.get(key), key)
        self.assertEqual(after['services']['team-api']['environment']['SOCIALMEI_PUBLIC_BOOKING_ENABLED'], 'false')

    def test_dotenv_roundtrip_variable_syntax_backslashes_and_quotes(self):
        cases = ['synthetic-$SHOULD_NOT_EXIST-${OTHER}$$end', 'trailing\\',
                 "slash\\'quote\"", 'inside # with spaces']
        with tempfile.TemporaryDirectory() as temp:
            for value in cases:
                with self.subTest(value=value):
                    self.key = value
                    data = self.render(Path(temp), brevo_enabled=True)
                    self.assertEqual(self.interpolation_inputs['SOCIALMEI_BREVO_PASSWORD'], value)
                    self.assertEqual(data['services']['team-api']['environment']['SOCIALMEI_SMTP_PASSWORD'], value.replace('$', '$$'))


if __name__ == '__main__':
    unittest.main()
