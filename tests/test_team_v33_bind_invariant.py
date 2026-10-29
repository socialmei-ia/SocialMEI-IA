"""Synthetic Docker bind-order regressions; never touches production."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    'team_v33_bind_invariant', Path(__file__).resolve().parents[1] / 'tools/team-v33-publish.py')
publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish)


def gateway():
    return {
        'Id': 'a' * 64,
        'Config': {'Cmd': ['caddy', 'run'], 'User': '', 'Env': ['SYNTHETIC=true']},
        'HostConfig': {
            'Binds': ['/synthetic/Caddyfile:/etc/caddy/Caddyfile:ro',
                      '/synthetic/private:/etc/caddy/private:ro',
                      '/synthetic/config.js:/srv/frontend/config.js:ro'],
            'Privileged': False,
            'ReadonlyRootfs': False,
            'SecurityOpt': ['no-new-privileges:true'],
        },
        'Mounts': [
            {'Type': 'bind', 'Source': '/synthetic/Caddyfile',
             'Destination': '/etc/caddy/Caddyfile', 'RW': False},
            {'Type': 'bind', 'Source': '/synthetic/private',
             'Destination': '/etc/caddy/private', 'RW': False},
            {'Type': 'bind', 'Source': '/synthetic/config.js',
             'Destination': '/srv/frontend/config.js', 'RW': False},
        ],
        'NetworkSettings': {'Networks': {'synthetic-api': {'Aliases': ['gateway']}}},
    }


class BindInvariantTests(unittest.TestCase):
    def test_bind_permutation_matches_without_mutating_docker_inspect(self):
        before = gateway()
        after = copy.deepcopy(before)
        after['HostConfig']['Binds'] = [before['HostConfig']['Binds'][2],
                                      before['HostConfig']['Binds'][0],
                                      before['HostConfig']['Binds'][1]]
        original_before = copy.deepcopy(before)
        original_after = copy.deepcopy(after)
        self.assertEqual(publish.invariant(before), publish.invariant(after))
        self.assertEqual(before, original_before)
        self.assertEqual(after, original_after)

    def test_bind_source_destination_mode_and_multiplicity_still_matter(self):
        before = gateway()
        for bind in (
            '/synthetic/other:/etc/caddy/Caddyfile:ro',
            '/synthetic/Caddyfile:/etc/caddy/other:ro',
            '/synthetic/Caddyfile:/etc/caddy/Caddyfile:rw',
            '/synthetic/Caddyfile:/etc/caddy/Caddyfile:ro,z',
        ):
            with self.subTest(bind=bind):
                after = copy.deepcopy(before)
                after['HostConfig']['Binds'][0] = bind
                self.assertNotEqual(publish.invariant(before), publish.invariant(after))
        after = copy.deepcopy(before)
        after['HostConfig']['Binds'].append(after['HostConfig']['Binds'][0])
        self.assertNotEqual(publish.invariant(before), publish.invariant(after))
        after['HostConfig']['Binds'] = before['HostConfig']['Binds'][:-1]
        self.assertNotEqual(publish.invariant(before), publish.invariant(after))

    def test_mount_details_and_other_host_security_are_not_normalized_away(self):
        before = gateway()
        for field, value in (('Source', '/synthetic/other'),
                             ('Destination', '/etc/caddy/other'), ('RW', True)):
            with self.subTest(field=field):
                after = copy.deepcopy(before)
                after['Mounts'][0][field] = value
                self.assertNotEqual(publish.invariant(before), publish.invariant(after))
        for field, value in (('Privileged', True), ('ReadonlyRootfs', True),
                             ('SecurityOpt', [])):
            with self.subTest(field=field):
                after = copy.deepcopy(before)
                after['HostConfig'][field] = value
                self.assertNotEqual(publish.invariant(before), publish.invariant(after))

    def test_absent_and_null_binds_are_preserved(self):
        row = gateway()
        del row['HostConfig']['Binds']
        self.assertNotIn('Binds', publish.invariant(row)['host'])
        row['HostConfig']['Binds'] = None
        self.assertIsNone(publish.invariant(row)['host']['Binds'])


if __name__ == '__main__':
    unittest.main()
