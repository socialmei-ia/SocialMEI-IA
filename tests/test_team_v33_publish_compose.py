"""Real Compose parsing only: no container, network or volume is created."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'v33_compose_roundtrip', Path(__file__).resolve().parents[1] / 'tools/team-v33-publish.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class ComposeRoundtripTests(unittest.TestCase):
    def test_literal_environment_and_runtime_shape_survive_config(self):
        if not shutil.which('docker'):
            self.skipTest('Docker Compose CLI unavailable')
        version = subprocess.run(['docker', 'compose', 'version'], capture_output=True)
        if version.returncode:
            self.skipTest('Docker Compose CLI unavailable')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            environment = {'SECRET': 'synthetic$VALUE${UNDEFINED}$$tail',
                           'EMPTY': '', 'NORMAL': 'literal'}
            base = {'services': {'team-api': {'image': 'old:test',
                    'environment': {'NORMAL': 'literal'},
                    'networks': {'api': {'aliases': ['team-api']}},
                    'volumes': ['fixture:/data', '/tmp:/private:ro']}},
                    'networks': {'api': {'external': True, 'name': 'synthetic_api'}},
                    'volumes': {'fixture': {'external': True, 'name': 'synthetic_volume'}}}
            (root / 'base.json').write_text(json.dumps(base))
            overlay = {'services': {'team-api': {'image': 'candidate:test',
                       'environment': publisher.literal_environment(environment)}}}
            (root / 'overlay.json').write_text(json.dumps(overlay))
            instance = publisher.Publisher.__new__(publisher.Publisher)
            def run(args):
                return subprocess.run(args, capture_output=True, text=True, check=True).stdout
            instance.run = run
            command = ['docker', 'compose', '--project-name', 'synthetic-v33',
                       '-f', str(root / 'base.json')]
            before = instance.model(command)
            after = instance.model(command + ['-f', str(root / 'overlay.json')])
            self.assertEqual(after, publisher.candidate_model(
                before, 'team-api', 'candidate:test', environment))
            self.assertEqual(after['services']['team-api']['environment'], environment)
            self.assertEqual(after['services']['team-api']['volumes'], before['services']['team-api']['volumes'])
            self.assertEqual(after['services']['team-api']['networks'], before['services']['team-api']['networks'])


class CaddyPrivacyTests(unittest.TestCase):
    def fixture(self, *, drift=False, unprotected=False, basic=False):
        from unittest.mock import Mock
        instance = publisher.Publisher.__new__(publisher.Publisher)
        config = {'logging': {'logs': {'default': {'encoder': publisher.privacy_helper.ENCODER}}}}
        if unprotected:
            config['logging'] = {}
        if basic:
            config['apps'] = {'http': {'servers': {'s': {'routes': [{'handle': [{'handler': 'authentication', 'providers': {'http_basic': {}}}]}]}}}}
        def docker(*args):
            import copy
            value = copy.deepcopy(config)
            if drift and 'adapt' in args:
                value['admin'] = {'disabled': True}
            return json.dumps(value)
        instance.docker = Mock(side_effect=docker)
        return instance

    def test_both_active_proxies_are_protected_and_return_only_hashes(self):
        result = self.fixture().privacy_snapshot()
        self.assertEqual(set(result), {'socialmei-caddy', publisher.NAMES['team-gateway']})
        self.assertTrue(all(len(value) == 64 for value in result.values()))

    def test_active_file_drift_unprotected_logs_or_gateway_basic_are_blocked(self):
        for options in ({'drift': True}, {'unprotected': True}, {'basic': True}):
            with self.subTest(options=options), self.assertRaises(RuntimeError):
                self.fixture(**options).privacy_snapshot()
