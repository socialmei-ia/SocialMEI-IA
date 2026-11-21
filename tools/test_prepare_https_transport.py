import copy
import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('transport', Path(__file__).with_name('prepare-https-transport.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TransportTests(unittest.TestCase):
    def test_only_protocols_can_change(self):
        before = {'apps': {'http': {'servers': {'srv0': {'listen': [':443'], 'routes': [{'handle': 'preserved'}]}}}}, 'logging': {'protected': True}}
        after = copy.deepcopy(before)
        after['apps']['http']['servers']['srv0']['protocols'] = ['h1', 'h2']
        m.validate_delta(before, after)
        for field in ['routes', 'logging', 'listen', 'protocols']:
            candidate = copy.deepcopy(after)
            if field == 'logging': candidate['logging'] = {'protected': False}
            elif field == 'protocols': candidate['apps']['http']['servers']['srv0'][field] = ['h1', 'h2', 'h3']
            else: candidate['apps']['http']['servers']['srv0'][field] = ['changed']
            with self.subTest(field=field), self.assertRaises(RuntimeError): m.validate_delta(before, candidate)

    def test_private_original_content_and_global_logging_are_preserved(self):
        source = '# private\n{\n    log default {\n        format json\n    }\n}\nexample.test {\n    respond "never-log"\n}\n'
        candidate = m.candidate_text(source)
        self.assertEqual(candidate.replace('\n' + m.BLOCK, '', 1), source)
        self.assertEqual(candidate.count('protocols h1 h2'), 1)

    def test_existing_server_options_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'REQUIRE_REVIEW'):
            m.candidate_text('{\n    servers {\n        protocols h1 h2c\n    }\n}\n:80 {}')

    def test_site_environment_placeholder_is_not_global_block(self):
        source = '{$HOSTNAME} {\n    respond "ok"\n}'
        self.assertEqual(m.candidate_text(source), '{\n' + m.BLOCK + '}\n' + source)

    def test_custom_protocols_are_never_overwritten(self):
        before = {'apps': {'http': {'servers': {'srv0': {'protocols': ['h1', 'h2c']}}}}}
        with self.assertRaisesRegex(RuntimeError, 'REQUIRE_REVIEW'): m.validate_delta(before, before)

    def test_prepare_accepts_docker_inspect_array_and_never_changes_runtime(self):
        before = {'apps': {'http': {'servers': {'srv0': {'listen': [':443']}}}}}
        after = copy.deepcopy(before);after['apps']['http']['servers']['srv0']['protocols'] = ['h1', 'h2']
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'Caddyfile';raw = ':443 {\n    respond "ok"\n}\n';source.write_text(raw)
            installed = {'Name': '/socialmei-caddy', 'Id': 'frozen-container', 'Image': 'frozen-image',
                         'State': {'Running': True}, 'Mounts': [{'Type': 'bind', 'Destination': '/etc/caddy/Caddyfile', 'Source': str(source)}]}
            calls = []
            def call(args, **options):
                calls.append(args)
                if args[1] == 'inspect': return json.dumps([installed])
                if args[3] == 'cat': return raw
                if args[3] == 'wget': return json.dumps(before)
                raise AssertionError('Unexpected runtime operation')
            with patch.object(m.privacy, '_call', side_effect=call),patch.object(m.privacy, 'protected', return_value=True), \
                 patch.object(m.privacy, '_adapt', side_effect=lambda container,text: before if text == raw else after), \
                 patch.object(m.privacy, '_write_private'):
                plan = m.prepare(Path(tmp) / 'plan')
            self.assertEqual(plan['mode'], 'prepared_not_applied')
            self.assertFalse(plan['services_modified'])
            self.assertNotIn('reload', str(calls))
            self.assertNotIn('restart', str(calls))


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name);self.directory = root / 'plan';self.directory.mkdir()
        self.source = root / 'Caddyfile';self.before = ':443 {\n    respond "ok"\n}\n'
        self.candidate = m.candidate_text(self.before);self.source.write_bytes(self.before.encode())
        self.before_json = {'apps': {'http': {'servers': {'s': {'listen': [':443']}}}}}
        self.after_json = copy.deepcopy(self.before_json);self.after_json['apps']['http']['servers']['s']['protocols'] = ['h1','h2']
        self.installed = {'Name':'/socialmei-caddy','Id':'fixed-id','Image':'fixed-image','Config':{},'HostConfig':{},'Mounts':[], 'State':{'Running':True}}
        import hashlib
        self.plan = {'container_id':'fixed-id','image_id':'fixed-image','source_file':str(self.source),'source_inode':self.source.stat().st_ino,
            'before_sha256':hashlib.sha256(self.before.encode()).hexdigest(),'candidate_sha256':hashlib.sha256(self.candidate.encode()).hexdigest(),
            'before_json_sha256':m.digest(self.before_json),'candidate_json_sha256':m.digest(self.after_json)}
        self.plan['plan_sha256'] = m.digest(self.plan)
        for name,value in [('before.Caddyfile',self.before),('candidate.Caddyfile',self.candidate),('before.private.json',json.dumps(self.before_json)),
                           ('candidate.private.json',json.dumps(self.after_json)),('container.private.json',json.dumps(self.installed)),('plan.private.json',json.dumps(self.plan))]:
            (self.directory/name).write_bytes(value.encode())
        self.active = self.before_json;self.reloads = 0;self.fail_reload = False
        def call(args, **kwargs):
            if args == ['docker','inspect',m.CONTAINER]:return json.dumps([self.installed])
            if args[:5] == ['docker','exec',m.CONTAINER,'caddy','reload']:
                self.reloads += 1
                if self.fail_reload and self.reloads == 1:raise RuntimeError('Synthetic reload failure')
                self.active = self.after_json if self.source.read_text() == self.candidate else self.before_json
                return ''
            raise AssertionError('Unexpected runtime command')
        self.overrides = [patch.object(m.privacy,'_call',side_effect=call),patch.object(m,'active_json',side_effect=lambda:self.active),
            patch.object(m,'other_services',return_value={'api':'unchanged'}),
            patch.object(m,'web_state',side_effect=lambda:{'entry_sha256':'same-entry','advertises_h3':self.active==self.before_json}),
            patch.object(m.privacy,'_write_private',side_effect=lambda path,value:path.write_text(value))]
        for override in self.overrides:override.start();self.addCleanup(override.stop)

    def test_apply_and_manual_rollback_preserve_inode_and_other_services(self):
        result = m.apply(self.directory,self.plan['plan_sha256'])
        self.assertEqual(result['status'],'applied');self.assertEqual(self.source.read_text(),self.candidate)
        self.assertEqual(self.source.stat().st_ino,self.plan['source_inode'])
        result = m.rollback(self.directory,self.plan['plan_sha256'])
        self.assertEqual(result['status'],'rolled_back');self.assertTrue(result['other_services_unchanged'])
        self.assertEqual(self.source.read_text(),self.before)

    def test_reload_failure_restores_frozen_configuration_without_retrying_candidate(self):
        self.fail_reload = True
        with self.assertRaisesRegex(RuntimeError,'ROLLBACK_VERIFIED'):m.apply(self.directory,self.plan['plan_sha256'])
        self.assertEqual(self.reloads,2);self.assertEqual(self.source.read_text(),self.before)
        self.assertEqual(json.loads((self.directory/'execution.private.json').read_text())['status'],'rolled_back')

    def test_missing_or_wrong_approval_never_writes_active_source(self):
        for approval in ['', 'wrong-plan']:
            with self.assertRaises(RuntimeError):m.apply(self.directory,approval)
        self.assertEqual(self.reloads,0);self.assertFalse((self.directory/'execution.private.json').exists())


if __name__ == '__main__': unittest.main()
