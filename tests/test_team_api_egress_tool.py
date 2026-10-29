import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

class EgressToolTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('egress_tool',Path(__file__).resolve().parents[1]/'tools/team-api-egress.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def models(self):
        before={'services':{'team-api':{'image':'unchanged','environment':{'TOKEN':'synthetic'},'networks':{'api':None,'database':None}},'team-postgres':{'image':'postgres'}},'networks':{'api':{'internal':True},'database':{'internal':True}}}
        after=copy.deepcopy(before)
        after['services']['team-api']['networks']['egress']=None
        after['networks']['egress']={'name':'socialmei_team_egress','driver':'bridge'}
        return before,after
    def test_exact_network_delta_only(self):
        m=self.module();before,after=self.models();m.validate_delta(before,after)
        for mutation in ('image','ports','env','database','external','driver'):
            changed=copy.deepcopy(after)
            if mutation=='image':changed['services']['team-api']['image']='other'
            if mutation=='ports':changed['services']['team-api']['ports']=[8000]
            if mutation=='env':changed['services']['team-api']['environment']['TOKEN']='changed'
            if mutation=='database':changed['networks']['database']['internal']=False
            if mutation=='external':changed['networks']['egress']['external']=True
            if mutation=='driver':changed['networks']['egress']['driver']='host'
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):m.validate_delta(before,changed)
    def test_switch_is_api_only(self):
        m=self.module();self.assertEqual(m.up(['docker','compose'])[-8:],['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','team-api'])
    def test_preflight_failure_cannot_switch(self):
        m=self.module();p=m.Egress.__new__(m.Egress);p.load=Mock(return_value={});p.guard=Mock(side_effect=RuntimeError('drift'));p.run=Mock()
        with self.assertRaises(RuntimeError):p.apply()
        p.run.assert_not_called()
    def test_failed_probe_rolls_back_only_api(self):
        m=self.module();p=m.Egress.__new__(m.Egress)
        p.load=Mock(return_value={'before_command':['before'],'candidate_command':['after']})
        p.guard=Mock();p.run=Mock();p.verify=Mock(side_effect=[RuntimeError('TLS unavailable'),None]);p.write=Mock()
        with self.assertRaises(RuntimeError):p.apply()
        self.assertEqual([c.args[0] for c in p.run.call_args_list],[m.up(['after']),m.up(['before'])])
        self.assertEqual(p.verify.call_args.args[1],False)
        p.write.assert_not_called()
