import copy
import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('premium_release',Path(__file__).with_name('prepare-premium-v69-release.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PremiumReleaseTests(unittest.TestCase):
    def setUp(self):
        self.files=[{'path':'frontend/scripts/example.js','sha256':'a'*64}]
        self.root=Path('/private/candidate')
        self.before={'services':{'team-gateway':{'image':m.base.PREMIUM,'environment':{'PRIVATE':'preserved'},'volumes':[
            {'target':'/srv/frontend/config.js','source':'/private/config.js','type':'bind','read_only':True},
            {'target':'/srv/frontend/scripts/v22-inbox-customer.js','source':'/private/crm233.js','type':'bind','read_only':True}]},
            'team-api':{'image':'unchanged-api'}},'networks':{'edge':{'name':'existing-edge'}}}
        self.after=copy.deepcopy(self.before)
        self.after['services']['team-gateway']['volumes'].append({'type':'bind','source':str(self.root/self.files[0]['path']),
          'target':'/srv/frontend/scripts/example.js','read_only':True,'bind':{'create_host_path':False}})

    def test_exact_files_are_only_permitted_compose_delta(self):
        m.validate_delta(self.before,self.after,self.files,self.root)
        for change in ['api','image','environment','config','writable','network']:
            after=copy.deepcopy(self.after)
            if change=='api':after['services']['team-api']['image']='different'
            if change=='image':after['services']['team-gateway']['image']='generic'
            if change=='environment':after['services']['team-gateway']['environment']['PRIVATE']='changed'
            if change=='config':after['services']['team-gateway']['volumes'][0]['source']='/demo/config.js'
            if change=='writable':after['services']['team-gateway']['volumes'][-1]['read_only']=False
            if change=='network':after['networks']['edge']['name']='other'
            with self.subTest(change=change),self.assertRaises(RuntimeError):m.validate_delta(self.before,after,self.files,self.root)

    def test_reserved_paths_duplicates_and_shell_paths_are_rejected(self):
        for path in ['frontend/config.js','frontend/scripts/auth-store.js','frontend/scripts/v22-inbox-customer.js',
                     '../outside.js','frontend/../outside.js','frontend/a;touch.js','frontend//config.js','/frontend/a.js','frontend/a\\b.js']:
            with self.subTest(path=path),self.assertRaises(RuntimeError):m.candidate_files({'candidate_files':[{'path':path,'sha256':'a'*64}]})
        with self.assertRaises(RuntimeError):m.candidate_files({'candidate_files':self.files*2})

    def test_existing_visual_bind_can_change_without_touching_other_mounts(self):
        before=copy.deepcopy(self.before)
        before['services']['team-gateway']['volumes'].append({'type':'bind','source':'/old/example.js','target':'/srv/frontend/scripts/example.js','read_only':True})
        m.validate_delta(before,self.after,self.files,self.root)

    def test_changed_frozen_plan_is_rejected_before_docker(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m.base,'inspect') as inspect:
            stage=Path(tmp)/'frozen-plan';stage.mkdir()
            (stage/'approval-plan.json').write_text(json.dumps({'plan_sha256':'0'*64}))
            with self.assertRaisesRegex(RuntimeError,'APPROVAL_PLAN_CHANGED'):m.verify(tmp)
            inspect.assert_not_called()

    def test_changed_rollback_document_is_rejected_before_docker(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m.base,'inspect') as inspect:
            stage=Path(tmp)/'frozen-plan';stage.mkdir()
            value={'baseline_sha256':m.base.digest({}),'candidate_sha256':m.base.digest({}),'rollback_sha256':m.base.digest({'image':'frozen'})}
            value['plan_sha256']=m.base.digest(value)
            (stage/'approval-plan.json').write_text(json.dumps(value))
            for name in ['baseline-compose.json','candidate-compose.json','rollback-compose.json']:(stage/name).write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'FROZEN_COMPOSE_CHANGED'):m.verify(tmp)
            inspect.assert_not_called()

if __name__=='__main__':unittest.main()
