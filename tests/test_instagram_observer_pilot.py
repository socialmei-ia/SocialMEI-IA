import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('pilot', Path(__file__).resolve().parents[1] / 'tools/instagram-observer-pilot.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ObserverPilotTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'Name': '/' + name, 'Id': name, 'Image': 'frozen',
                      'State': {'Running': True, 'Health': {'Status': 'healthy'}},
                      'Config': {'Env': ['PRIVATE_SECRET=never-print',
                          'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID=1']}}
                     for name in (m.API, m.LEGACY)]

    def build(self, available=557, image=True):
        return m.plan(self.rows, available, image, 'a' * 64)

    def test_one_scope_fits_without_authorizing_activation_or_exposing_secrets(self):
        value = self.build()
        self.assertEqual(value['blockers'], [])
        self.assertEqual(value['workspace_id'], 60)
        self.assertEqual(value['required_mib'], 520)
        self.assertFalse(value['activation_authorized'])
        self.assertFalse(value['external_send'])
        self.assertNotIn('never-print', str(value))
        digest = value.pop('plan_sha256')
        self.assertEqual(digest, m.digest(value))

    def test_memory_and_missing_image_block_independently(self):
        self.assertEqual(len(self.build(519, False)['blockers']), 2)
        self.assertEqual(self.build(520)['blockers'], [])
        for invalid in (True, -1, '557'):
            with self.assertRaises(ValueError): self.build(invalid)

    def test_running_scope_lease_conflicts_even_if_sender_disabled(self):
        row = copy.deepcopy(self.rows[-1])
        row['Name'] = '/another-observer'
        row['Config']['Env'] = ['SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES=61,60',
                                'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false']
        self.rows.append(row)
        self.assertIn('existing_workspace60_worker', self.build()['blockers'])
        row['State']['Running'] = False
        self.assertEqual(self.build()['blockers'], [])

    def test_mutated_runtime_changes_plan_hash(self):
        before = self.build()['plan_sha256']
        self.rows[-1]['Config']['Env'].append('NEW_CONFIG=value')
        self.assertNotEqual(before, self.build()['plan_sha256'])

    def test_unhealthy_api_missing_source_or_duplicate_environment_fail_closed(self):
        self.rows[0]['State']['Health']['Status'] = 'unhealthy'
        with self.assertRaises(ValueError): self.build()
        self.rows[0]['State']['Health']['Status'] = 'healthy'
        self.rows[-1]['Config']['Env'].append('PRIVATE_SECRET=second')
        with self.assertRaises(ValueError): self.build()
        self.rows.pop()
        with self.assertRaises(ValueError): self.build()


if __name__ == '__main__':
    unittest.main()
