import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('bella_plan', Path(__file__).resolve().parents[1] /
                                              'tools/instagram-bella-observer-plan.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class BellaPlanTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {'available_mib': 574, 'preserved_brilho_id': 'preserved',
            'brilho': {'id': 'preserved', 'image': m.IMAGE, 'running': True, 'health': 'healthy',
                'restarts': 0, 'oom': False, 'workspace': '60', 'mode': 'observe',
                'send': 'false', 'auto_menu': 'false', 'memory_limit': 72 * 1024**2,
                'memswap_limit': 72 * 1024**2, 'state_volume': 'socialmei-instagram-observers_brilho-state'},
            'exact_image_present': True, 'bella_volume_exists': False,
            'duplicate_workspace61': False, 'runtime_fingerprints': {'preserved': 'frozen'},
            'compose_sha256': 'a' * 64}

    def test_budget_never_spends_existing_brilho_cap_or_backup_reserve(self):
        value = m.build(self.snapshot)
        self.assertFalse(value['ready_for_approval'])
        self.assertEqual(value['required_before_start_mib'], 592)
        self.assertEqual(value['required_while_running_mib'], 520)
        self.snapshot['available_mib'] = 592
        value = m.build(self.snapshot)
        self.assertTrue(value['ready_for_approval'])
        self.assertFalse(value['activation_authorized'])
        self.assertFalse(value['external_send'])
        self.assertFalse(value['queue_consumption'])
        expected = value.pop('plan_sha256')
        self.assertEqual(expected, m.digest(value))

    def test_conflicts_missing_image_and_existing_volume_each_block(self):
        self.snapshot['available_mib'] = 700
        for key, value in [('exact_image_present', False), ('bella_volume_exists', True),
                            ('duplicate_workspace61', True)]:
            snapshot = {**self.snapshot, key: value}
            self.assertFalse(m.build(snapshot)['ready_for_approval'])

    def test_wrong_brilho_scope_health_limits_or_identity_fail_closed(self):
        for key, value in [('id', 'replacement'), ('health', 'unhealthy'), ('workspace', '61'),
                           ('send', 'true'), ('memswap_limit', -1), ('restarts', 1)]:
            snapshot = copy.deepcopy(self.snapshot); snapshot['brilho'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.build(snapshot)
        for value in (True, -1, '574'):
            with self.assertRaises(ValueError): m.build({**self.snapshot, 'available_mib': value})


if __name__ == '__main__':
    unittest.main()
