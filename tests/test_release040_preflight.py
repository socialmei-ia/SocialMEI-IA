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
    def external_inputs(self):
        model, images, sha, receipt, rollback = inputs()
        model['networks']['database'] = {'external': True, 'name': 'isolated-db-network'}
        url = ('postgresql://synthetic@isolated-pg/test?sslmode=verify-full'
               '&sslrootcert=/run/socialmei/database-ca.crt')
        for name in ('team-api', *gate.WORKERS):
            model['services'][name]['environment']['DATABASE_URL'] = url
            model['services'][name]['volumes'] = [{'type': 'bind', 'source': '/private/ca.crt',
                'target': '/run/socialmei/database-ca.crt', 'read_only': True}]
        runtime = {'network': {'Name': 'isolated-db-network', 'Internal': True},
                   'postgres': {'Name': '/isolated-pg', 'State': {'Running': True},
                                'HostConfig': {'PortBindings': {}},
                                'NetworkSettings': {'Networks': {'isolated-db-network': {}}}}}
        return model, images, sha, receipt, rollback, runtime

    def test_external_private_postgres_requires_runtime_proof_and_ca_for_all_consumers(self):
        args = self.external_inputs()
        result = gate.validate(*args)
        self.assertTrue(result['artifact_checks_passed'])
        self.assertFalse(result['production_ready'])
        with self.assertRaises(RuntimeError):
            gate.validate(*args[:-1])

    def test_external_database_rejects_public_network_wrong_identity_and_missing_tls(self):
        changes = [
            lambda m, r: r['network'].update(Internal=False),
            lambda m, r: r['network'].update(Name='other-network'),
            lambda m, r: r['postgres']['State'].update(Running=False),
            lambda m, r: r['postgres']['HostConfig'].update(PortBindings={'5432/tcp': [{}]}),
            lambda m, r: r['postgres'].pop('HostConfig'),
            lambda m, r: r['postgres']['NetworkSettings']['Networks'].update(public={}),
            lambda m, r: m['services']['team-api']['environment'].update(DATABASE_URL='postgresql://other/test'),
            lambda m, r: m['services']['team-api']['environment'].update(DATABASE_URL='postgresql://synthetic@isolated-pg/test?sslmode=require'),
            lambda m, r: m['services']['team-identity-worker'].update(volumes=[]),
            lambda m, r: m['services']['team-api']['volumes'][0].update(read_only=False),
            lambda m, r: m['services']['team-identity-worker']['volumes'][0].update(source='/other/ca.crt'),
        ]
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                model, images, sha, receipt, rollback, runtime = self.external_inputs()
                change(model, runtime)
                with self.assertRaises(RuntimeError):
                    gate.validate(model, images, sha, receipt, rollback, runtime)

    def test_whitespace_dsn_uses_real_fallback_and_default_port(self):
        env = {'DATABASE_URL': ' ', 'POSTGRES_HOST': 'private', 'POSTGRES_DB': 'a', 'POSTGRES_USER': 'u'}
        self.assertNotEqual(gate.database_identity(env), gate.database_identity({**env, 'POSTGRES_DB': 'b'}))
        self.assertEqual(gate.database_identity(env), gate.database_identity({**env, 'POSTGRES_PORT': ' 5432 '}))

    def test_external_database_uri_query_cannot_override_effective_libpq_identity(self):
        for override in ('host=other', 'host=', 'hostaddr=127.0.0.1', 'dbname=other',
                         'user=other', 'port=5433', 'service=other', 'options=other'):
            with self.subTest(override=override):
                model, images, sha, receipt, rollback, runtime = self.external_inputs()
                model['services']['team-api']['environment']['DATABASE_URL'] += '&' + override
                with self.assertRaises(RuntimeError):
                    gate.validate(model, images, sha, receipt, rollback, runtime)

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
