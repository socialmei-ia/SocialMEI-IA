import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

class APIPatchTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('api_patch',Path(__file__).resolve().parents[1]/'tools/api-diagnostics-release.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def test_delta_preserves_egress_and_all_other_fields(self):
        m=self.module();before={'services':{'team-api':{'image':'old','environment':{'SOCIALMEI_RELEASE_SHA':'old','SECRET':'synthetic'},'networks':{'api':None,'database':None,'egress':None}}},'networks':{'egress':{'name':'socialmei_team_egress'}}}
        after=copy.deepcopy(before);after['services']['team-api']['image']=m.TAG;after['services']['team-api']['environment']['SOCIALMEI_RELEASE_SHA']=m.TARGET
        m.validate(before,after)
        for mutation in ('network','secret','ports'):
            changed=copy.deepcopy(after)
            if mutation=='network':del changed['services']['team-api']['networks']['egress']
            if mutation=='secret':changed['services']['team-api']['environment']['SECRET']='other'
            if mutation=='ports':changed['services']['team-api']['ports']=[8000]
            with self.assertRaises(RuntimeError):m.validate(before,changed)
    def test_failed_smoke_rolls_back_api_only(self):
        m=self.module();task=m.Update.__new__(m.Update)
        task.load=Mock(return_value={'before_command':['before'],'candidate_command':['after']})
        task.guard=Mock();task.run=Mock();task.verify=Mock(side_effect=[RuntimeError('probe'),None]);task.write=Mock()
        with self.assertRaises(RuntimeError):task.apply()
        self.assertEqual([call.args[0] for call in task.run.call_args_list],[m.common.up(['after']),m.common.up(['before'])])
        task.write.assert_not_called()
