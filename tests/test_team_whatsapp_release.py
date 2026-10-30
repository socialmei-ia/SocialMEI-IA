"""Pilot release gates and exact rollback smoke use synthetic fixtures only."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'tools/team-whatsapp-release.py'


class PilotReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('pilot_release', PATH)
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'fcntl': ModuleType('fcntl')}) if sys.platform == 'win32' else patch.dict(sys.modules, {}):
            spec.loader.exec_module(cls.module)

    def test_source_requires_exact_clean_git_commit(self):
        m = self.module
        sha = 'a' * 40
        source = m.BACKUPS / 'synthetic' / 'source'
        with patch.object(m, 'SOURCE', source), patch.object(m, 'run', side_effect=[(sha+'\n').encode(), b'']):
            m.validate_source(sha)
        for responses in ([b'wrong\n', b''], [(sha+'\n').encode(), b' M private-file']):
            with patch.object(m, 'SOURCE', source), patch.object(m, 'run', side_effect=responses), self.assertRaises(m.Blocked):
                m.validate_source(sha)

    def test_rollback_checks_saved_bytes_instead_of_new_candidate_source(self):
        m = self.module
        old = b'synthetic old frontend'
        expected = {'scripts/v22-bootstrap.js': hashlib.sha256(old).hexdigest()}
        def https(path, status):
            return old if path.endswith('v22-bootstrap.js') else b'home'
        with patch.object(m, 'https', side_effect=https):
            m.public_smoke(expected_files=expected)
        with patch.object(m, 'https', return_value=b'wrong'), self.assertRaises(m.Blocked):
            m.public_smoke(expected_files=expected)

    def test_candidate_changes_only_two_images_release_and_existing_pilot_flags(self):
        m = self.module
        sha = 'a' * 40
        before = {'services': {'team-api': {'image': 'old-api', 'environment': {'KEEP': 'private', **{k: 'old' for k in m.FLAGS}}},
                               'team-gateway': {'image': 'old-gateway', 'volumes': ['private:ro']},
                               'team-postgres': {'image': 'untouched'}}, 'networks': {'egress': {'name': 'socialmei_team_egress'}}}
        import copy, json
        expected = copy.deepcopy(before)
        expected['services']['team-api']['image'] = m.image_tags(sha)['team-api']
        expected['services']['team-gateway']['image'] = m.image_tags(sha)['team-gateway']
        expected['services']['team-api']['environment'].update({k: sha if k == 'SOCIALMEI_RELEASE_SHA' else v for k,v in m.FLAGS.items()})
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / 'override.json'
            with patch.object(m, 'render', return_value=expected):
                value = m.candidate_model(before, {'services': {}}, original, ['docker', str(original)], folder, sha)
                self.assertEqual(json.loads(value)['services']['team-api']['image'], m.image_tags(sha)['team-api'])
            altered = copy.deepcopy(expected)
            altered['services']['team-postgres']['image'] = 'forbidden'
            with patch.object(m, 'render', return_value=altered), self.assertRaises(m.Blocked):
                m.candidate_model(before, {'services': {}}, original, ['docker', str(original)], folder, sha)

    def test_runtime_security_requires_compose_privilege_capabilities_and_read_only_flags(self):
        m = self.module
        config = {'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true']}
        host = {'ReadonlyRootfs': True, 'Privileged': False, 'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges:true']}
        container = {'HostConfig': host}
        self.assertTrue(m.security_matches(config, container))
        for key, value in [('Privileged', True), ('ReadonlyRootfs', False), ('CapDrop', []), ('SecurityOpt', [])]:
            self.assertFalse(m.security_matches(config, {'HostConfig': {**host, key: value}}))

    def test_retargeted_baseline_tag_is_rejected_before_backup(self):
        import json
        m = self.module
        api = {'Config': {'Image': m.image_tags(m.BASE_SHA)['team-api']}, 'Image': 'sha256:running'}
        gateway = {'Config': {'Image': m.image_tags(m.BASE_SHA)['team-gateway']}, 'Image': 'sha256:running'}
        with patch.object(m, 'docker', return_value=json.dumps([{'Id': 'sha256:running'}]).encode()):
            m.baseline_image_identity(api, gateway)
        with patch.object(m, 'docker', return_value=json.dumps([{'Id': 'sha256:retargeted'}]).encode()), self.assertRaises(m.Blocked):
            m.baseline_image_identity(api, gateway)

    def test_gateway_rollback_is_attempted_even_when_api_restore_fails(self):
        m = self.module
        with patch.object(m, 'run', side_effect=[m.Blocked('failed'), b'']) as run, \
             patch.object(m, 'wait_service') as wait, self.assertRaises(m.Blocked):
            m.restore_services(['docker', 'compose'], Path('synthetic'), list(m.SERVICES))
        self.assertEqual([call.args[0][-1] for call in run.call_args_list], ['team-api', 'team-gateway'])
        wait.assert_called_once_with('team-gateway')

    def test_backup_runs_in_original_operator_home_and_rejects_other_locations(self):
        m = self.module
        name = 'team-auto-20261030-120000-synthetic'
        with patch.object(m, 'run', return_value=('Backup: '+(m.BACKUPS / name).as_posix()).encode()) as run:
            self.assertEqual(m.fresh_database_backup(), m.BACKUPS / name)
        self.assertEqual(run.call_args.args[0][:5], ['sudo', '-u', 'ubuntu', '-H', 'python3'])
        for output in (b'Backup: /root/socialmei-backups/' + name.encode(), b'no receipt'):
            with patch.object(m, 'run', return_value=output), self.assertRaises(m.Blocked):
                m.fresh_database_backup()
