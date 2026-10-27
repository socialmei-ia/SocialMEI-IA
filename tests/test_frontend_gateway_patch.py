import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class GatewayPatchTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('patcher',ROOT/'tools/frontend-gateway-patch.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_only_gateway_image_can_change(self):
        m=self.module()
        before={'services':{'team-gateway':{'image':'old','environment':{'SAFE':'yes'},'volumes':['private']},'team-api':{'image':'api'}},'networks':{'private':{}}}
        after=m.candidate_model(before,'new')
        self.assertEqual(after['services']['team-gateway']['image'],'new')
        self.assertEqual(before['services']['team-gateway']['image'],'old')
        after['services']['team-gateway']['image']='old'
        self.assertEqual(after,before)

    def test_patch_has_exact_reviewed_static_files(self):
        m=self.module()
        self.assertEqual(set(m.FILES),{'frontend/scripts/entrada.js','frontend/scripts/v22-instagram.js','frontend/scripts/v22-knowledge-reporting.js'})

    def test_gateway_command_never_recreates_dependencies(self):
        m=self.module()
        self.assertEqual(m.switch_command(['docker','compose'])[-8:],['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','team-gateway'])

    def test_guard_failure_never_switches_gateway(self):
        from unittest.mock import Mock
        m=self.module();p=m.Patch.__new__(m.Patch)
        p.read=Mock(return_value={});p.guard=Mock(side_effect=RuntimeError('drift'));p.run=Mock()
        with self.assertRaises(RuntimeError):p.apply()
        p.run.assert_not_called()

    def test_failed_cutover_rolls_back_gateway_and_verifies_baseline(self):
        from unittest.mock import Mock
        m=self.module();p=m.Patch.__new__(m.Patch)
        receipt={'candidate_command':['new'],'before_command':['old'],'image_id':'new-id','old_image_id':'old-id'}
        p.read=Mock(return_value=receipt);p.guard=Mock();p.run=Mock(return_value=b'synthetic')
        p.inspect=Mock(side_effect=[{'Image':'new-id'},{'Image':'old-id'}])
        p.smoke=Mock(side_effect=[RuntimeError('HTTPS failure'),None]);p.write=Mock()
        with self.assertRaises(RuntimeError):p.apply()
        self.assertEqual(p.run.call_args_list[0].args[0],m.switch_command(['new']))
        self.assertEqual(p.run.call_args_list[1].args[0],m.switch_command(['old']))
        self.assertEqual(p.smoke.call_count,2)
        p.write.assert_not_called()
