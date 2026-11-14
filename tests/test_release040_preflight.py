"""Artifact rejection tests. No daemon, database or provider calls."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load('preflight_test', 'tools/release040-preflight.py')
fixture = load('receipt_fixture', 'tests/test_team_release040_profile.py')


def inputs():
    receipt = fixture.proof()
    sha = receipt['source_sha']
    images = {role: {'Id': image, 'Architecture': 'amd64', 'Config': {'Labels': {
        'org.opencontainers.image.revision': sha, 'org.socialmei.release.profile': '040'}}}
              for role, image in [('api', receipt['api_image_id']), ('gateway', 'sha256:' + 'e' * 64)]}
    env = {'DATABASE_URL': 'postgresql://synthetic@private/test',
           'SOCIALMEI_AUTH_ORIGIN': 'https://example.test', 'SOCIALMEI_AUTH_ENABLED': 'true'}
    services = {'team-migrate': {'profiles': ['maintenance040']}, 'team-postgres': {}}
    for name in ('team-api', 'team-gateway', *gate.WORKERS):
        role = 'gateway' if name == 'team-gateway' else 'api'
        services[name] = {'image': images[role]['Id'], 'environment': dict(env),
                          'healthcheck': {'test': ['CMD', 'python', 'runtime_healthcheck.py']}}
        if name in gate.WORKERS:
            services[name].update(profiles=[name], restart='unless-stopped')
            services[name]['command'] = gate.COMMANDS[name]
    for name, (required, _) in gate.NETWORKS.items():
        services[name]['networks'] = dict.fromkeys(required, {})
    import json
    rollback = json.loads((ROOT / 'docs/evidence/20261113-schema040-rollback-rehearsal.json').read_text())
    rollback.update(candidate_source_sha=sha, candidate_image_id=images['api']['Id'])
    return {'services': services, 'networks': {name: {'internal': True}
            for name in ('database', 'api', 'automation')}}, images, sha, receipt, rollback


class Release040PreflightTests(unittest.TestCase):
    def test_whitespace_dsn_uses_real_fallback_and_default_port(self):
        env = {'DATABASE_URL': ' ', 'POSTGRES_HOST': 'private', 'POSTGRES_DB': 'a', 'POSTGRES_USER': 'u'}
        self.assertNotEqual(gate.database_identity(env), gate.database_identity({**env, 'POSTGRES_DB': 'b'}))
        self.assertEqual(gate.database_identity(env), gate.database_identity({**env, 'POSTGRES_PORT': ' 5432 '}))

    def test_approved_artifacts_never_approve_production(self):
        result = gate.validate(*inputs())
        self.assertTrue(result['artifact_checks_passed'])
        self.assertFalse(result['production_ready'])
        self.assertNotIn('DATABASE_URL', str(result))

    def test_effective_configuration_rejections(self):
        changes = [
            lambda s: s['team-api'].update(depends_on={'team-migrate': {}}),
            lambda s: s['team-migrate'].update(profiles=[]),
            lambda s: s['team-api'].update(ports=[{'published': '8000'}]),
            lambda s: s['team-postgres'].update(ports=[{'published': '5432'}]),
            lambda s: s['team-api'].update(build={'context': '.'}),
            lambda s: s['team-api'].update(image='mutable:latest'),
            lambda s: s['team-api']['environment'].update(SOCIALMEI_AUTH_ENABLED='false'),
            lambda s: s['team-api']['environment'].update(SOCIALMEI_IDENTITY_MODE='required'),
            lambda s: s['team-api']['environment'].update(SOCIALMEI_WHATSAPP_BOT_ENABLED='true'),
            lambda s: s['team-identity-worker']['environment'].update(DATABASE_URL='postgresql://other/test'),
            lambda s: s['team-identity-worker']['environment'].update(SOCIALMEI_AUTH_ORIGIN='https://other.test'),
            lambda s: s['team-identity-worker'].update(profiles=[]),
            lambda s: s['team-api'].update(networks={'web': {}}),
            lambda s: s['team-postgres'].update(network_mode='host'),
            lambda s: s['team-api'].update(command=['python', '/maintenance/team_migrate.py']),
            lambda s: s['team-gateway'].update(volumes=[{'type': 'volume', 'target': '/srv/frontend'}]),
            lambda s: s['team-instagram-menu-primary'].update(volumes=[{
                'type': 'bind', 'target': '/app/instagram-auto-menu-worker.py'}]),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                model, images, sha, receipt, rollback = inputs()
                change(model['services'])
                with self.assertRaises(RuntimeError):
                    gate.validate(model, images, sha, receipt, rollback)

    def test_private_network_and_source_image_receipt_mismatch(self):
        for part in ('network', 'revision', 'profile', 'receipt', 'architecture'):
            with self.subTest(part=part):
                model, images, sha, receipt, rollback = inputs()
                if part == 'network':
                    model['networks']['database']['internal'] = False
                elif part in ('revision', 'profile'):
                    key = 'org.opencontainers.image.revision' if part == 'revision' else 'org.socialmei.release.profile'
                    images['api']['Config']['Labels'][key] = 'old'
                elif part == 'architecture':
                    images['api']['Architecture'] = 'arm64'
                else:
                    receipt['api_image_id'] = 'sha256:' + 'f' * 64
                with self.assertRaises(RuntimeError):
                    gate.validate(model, images, sha, receipt, rollback)

    def test_wrong_or_incomplete_rollback_is_rejected(self):
        for key, value in [('candidate_source_sha', 'f' * 40),
                           ('pending_email_guard_verified', False),
                           ('provider_messages_sent', True),
                           ('fallback_api_image_id', 'sha256:' + 'f' * 64)]:
            with self.subTest(key=key):
                model, images, sha, receipt, rollback = inputs()
                rollback[key] = value
                with self.assertRaises(RuntimeError):
                    gate.validate(model, images, sha, receipt, rollback)


if __name__ == '__main__':
    unittest.main()
