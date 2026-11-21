"""Offline pilot activation guards; never starts Docker or contacts providers."""
import copy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pilot_activation', Path(__file__).resolve().parents[1] /
                                              'tools/activate-brilho-observer-pilot.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.row = {'Id': 'new', 'Image': 'frozen', 'RestartCount': 0,
            'State': {'Running': True, 'Health': {'Status': 'healthy'}, 'OOMKilled': False},
            'Config': {'Labels': {'com.docker.compose.project': m.PROJECT,
                                 'com.docker.compose.service': 'brilho-observer'},
                       'Env': ['SOCIALMEI_INSTAGRAM_WORKER_MODE=observe',
                               'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID=60',
                               'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES=60',
                               'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false',
                               'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED=false',
                               'SOCIALMEI_QUEUE_WAKEUP_MODE=poll']},
            'HostConfig': {'Memory': 72*1024**2, 'MemorySwap': 72*1024**2, 'ReadonlyRootfs': True,
                           'PidsLimit': 64, 'NanoCpus': 250000000, 'CapDrop': ['ALL']},
            'NetworkSettings': {'Networks': {'private-db': {}}},
            'Mounts': [{'Destination': '/run/socialmei/instagram-menu-state',
                        'Type': 'volume', 'Name': m.VOLUME}]}

    def test_scope_limits_isolation_and_no_provider_secrets(self):
        m.validate_container(self.row, 'frozen', 'private-db')
        for change in ('send', 'scope', 'swap', 'ports', 'network', 'volume', 'provider'):
            row = copy.deepcopy(self.row)
            if change == 'send': row['Config']['Env'][3] = 'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=true'
            if change == 'scope': row['Config']['Env'][1] = 'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID=61'
            if change == 'swap': row['HostConfig']['MemorySwap'] = -1
            if change == 'ports': row['HostConfig']['PortBindings'] = {'80/tcp': [{}]}
            if change == 'network': row['NetworkSettings']['Networks']['another'] = {}
            if change == 'volume': row['Mounts'][0]['Name'] = 'other-workspace'
            if change == 'provider': row['Config']['Env'].append('N8N_API_KEY=synthetic')
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                m.validate_container(row, 'frozen', 'private-db')

    def pilot(self, folder):
        pilot = object.__new__(m.Pilot)
        pilot.root = Path(folder); pilot.container = 'new'; pilot.plan = {'image_id': 'frozen'}
        (pilot.root/'activation.private.json').write_text(json.dumps({'network': 'private-db',
            'before': {'existing-api': {'running': True, 'restarts': 0, 'health': 'healthy'}}}))
        return pilot

    def test_monitor_checks_existing_services_and_preserves_full_backup_reserve(self):
        existing = {'Id': 'existing-api', 'RestartCount': 0,
                    'State': {'Running': True, 'Health': {'Status': 'healthy'}}}
        with TemporaryDirectory() as folder:
            pilot = self.pilot(folder)
            with patch.object(pilot, 'rows', return_value=[existing, self.row]), \
                    patch.object(m, 'memory', return_value=448), \
                    patch.object(m, 'call', return_value='{"MemUsage":"42MiB / 72MiB"}'):
                self.assertEqual(pilot.sample()['available_mib'], 448)
                existing['RestartCount'] = 1
                with self.assertRaisesRegex(RuntimeError, 'existing_service_changed'): pilot.sample()
                existing['RestartCount'] = 0
                with patch.object(m, 'memory', return_value=447):
                    with self.assertRaisesRegex(RuntimeError, 'runtime_memory'): pilot.sample()

    def test_rollback_stops_only_recorded_new_scope_and_keeps_volumes(self):
        with TemporaryDirectory() as folder:
            pilot = self.pilot(folder)
            with patch.object(m, 'call', side_effect=[json.dumps([self.row]), '']) as call:
                pilot.rollback('synthetic_failure')
            self.assertEqual(call.call_args.args[0], ['docker', 'stop', '--time', '15', 'new'])
            result = json.loads((pilot.root/'result.private.json').read_text())
            self.assertTrue(result['volumes_preserved'])
            row = copy.deepcopy(self.row)
            row['Config']['Labels']['com.docker.compose.service'] = 'bella-observer'
            with patch.object(m, 'call', return_value=json.dumps([row])) as call:
                with self.assertRaisesRegex(RuntimeError, 'rollback_scope'): pilot.rollback('synthetic')
            self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
