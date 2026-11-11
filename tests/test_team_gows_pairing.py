import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('gows_pairing', Path(__file__).resolve().parents[1]/'tools/team_gows_pairing.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PairingScopeTests(unittest.TestCase):
    def test_only_unauthenticated_isolated_gows_can_start_or_restart(self):
        self.assertEqual(module.pairing_action('GOWS','FAILED',False,0),'restart')
        self.assertEqual(module.pairing_action('GOWS','STOPPED',False,0),'start')

    def test_main_engine_and_connected_webhooks_are_blocked(self):
        for engine, hooks in [('WEBJS',0),('GOWS',1)]:
            with self.assertRaises(ValueError): module.pairing_action(engine,'FAILED',False,hooks)

    def test_authenticated_and_active_pairing_are_not_restarted(self):
        for state, authenticated in [('WORKING',True),('FAILED',True),('SCAN_QR_CODE',False),('STARTING',False)]:
            self.assertIsNone(module.pairing_action('GOWS',state,authenticated,0))

    def test_unknown_states_need_human_attention(self):
        with self.assertRaises(ValueError): module.pairing_action('GOWS','PASSKEY_REQUIRED',False,0)


if __name__ == '__main__': unittest.main()
