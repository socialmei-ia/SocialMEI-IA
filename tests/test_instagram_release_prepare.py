"""Release preparation must preserve private runtime configuration, without deployment."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_prepare',ROOT/'tools/instagram-release-prepare.py')
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
SHA = 'a' * 40
# This publisher is deliberately pinned to the approved V25 chain, not new bot SQL.
MIGRATIONS = sorted(p.name for p in (ROOT/'database/migrations').glob('*.sql') if int(p.name[:3]) <= 31)


def model():
    return {'name':'socialmei-team','services':{
        'team-api':{'image':'installed-api','environment':{'SECRET':'synthetic-private','SOCIALMEI_INSTAGRAM_RUNTIME_MODE':'connect','SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED':'false'},'networks':{'api':{}},'volumes':[]},
        'team-gateway':{'image':'installed-gateway','environment':{'HOST':'app.example.test'},'networks':{'api':{}},'volumes':[{'type':'bind','source':'/private/Caddyfile','target':'/etc/caddy/Caddyfile','read_only':True}]},
        'team-postgres':{'image':'postgres:16-alpine'}},'networks':{'api':{'name':'socialmei-team_api'}}}


class ReleasePrepareTests(unittest.TestCase):
    def test_v25_publisher_refuses_new_bot_migration(self):
        current = sorted(p.name for p in (ROOT/'database/migrations').glob('*.sql'))
        self.assertIn('032_whatsapp_bot_conversations.sql', current)
        with self.assertRaises(RuntimeError):
            prep.missing_migrations(MIGRATIONS, current, stage='functional')

    def test_models_change_only_target_image_and_api_release(self):
        original = model()
        for service in ('team-api','team-gateway'):
            candidate,override = prep.candidate_model(original,service,SHA)
            wanted = copy.deepcopy(original)
            wanted['services'][service]['image'] = f'socialmei-v22/{service}:{SHA}'
            if service == 'team-api': wanted['services'][service]['environment']['SOCIALMEI_RELEASE_SHA']=SHA
            self.assertEqual(candidate,wanted)
            self.assertEqual(set(override['services']),{service})
        self.assertNotIn('SOCIALMEI_RELEASE_SHA',original['services']['team-api']['environment'])

    def test_only_absent_reviewed_migrations_are_planned(self):
        files = MIGRATIONS
        self.assertEqual(prep.missing_migrations(files[:26],files),files[26:28])
        self.assertEqual(prep.missing_migrations(files[:26],files,stage='oauth'),[])
        self.assertEqual(prep.missing_migrations(files[:26],files,stage='functional'),files[26:])
        self.assertEqual(prep.missing_migrations(files[:29],files),[])
        self.assertEqual(prep.missing_migrations(files,files),[])
        for installed in (files[1:26],files[:26]+[files[27]],files+['032_unreviewed.sql'],files[:25]):
            with self.assertRaises(RuntimeError):prep.missing_migrations(installed,files)

    def test_unreviewed_source_or_stage_is_rejected_without_planning(self):
        for files in (MIGRATIONS[:-1],MIGRATIONS+['032_extra.sql'],
                      MIGRATIONS[:29]+['030_another_change.sql']+MIGRATIONS[30:]):
            with self.assertRaises(RuntimeError):prep.missing_migrations(MIGRATIONS[:26],files)
        with self.assertRaises(RuntimeError):
            prep.missing_migrations(MIGRATIONS[:26],MIGRATIONS,stage='all')

    def test_gateway_patch_preserves_logging_and_existing_routes(self):
        source = '{\n log default {\n format json\n }\n}\n:80 {\n route {\n handle /api/v1/* {\n reverse_proxy team-api:8000\n }\n handle / { respond landing }\n }\n}\n'
        result = prep.patch_caddy(source)
        self.assertIn(source.split(':80')[0],result)
        self.assertIn('handle / { respond landing }',result)
        self.assertIn('handle /webhooks/instagram',result)
        self.assertIn('handle /media/instagram/*',result)
        self.assertIn('header_up -Cookie',result)
        self.assertIn('route {\n',result)

    def test_existing_route_needs_semantic_review_not_duplicate(self):
        for path in ('/media/instagram/*','/webhooks/instagram'):
            source = ':80 {\n route {\n handle '+path+' {\n respond existing\n }\n handle /api/v1/* { reverse_proxy team-api:8000 }\n }\n}\n'
            result=prep.patch_caddy(source)
            self.assertEqual(result.count('handle '+path+' '),1)
        with self.assertRaises(RuntimeError):prep.patch_caddy(':80 { respond unexpected }')

    def test_route_delta_rejects_auth_network_and_logger_changes(self):
        old={'apps':{'http':{'servers':{'srv0':{'routes':[{'match':[{'path':['/api/v1/*']}],'handle':[{'handler':'reverse_proxy','upstreams':[{'dial':'team-api:8000'}]}]}]}}}},'logging':{'logs':{'default':{'encoder':{'format':'filter'}}}}}
        added={'match':[{'path':['/media/instagram/*']}],'handle':[{'handler':'subroute','routes':[]}]}
        new=copy.deepcopy(old);new['apps']['http']['servers']['srv0']['routes'].insert(0,added)
        self.assertTrue(prep.routes_only(old,new,['/media/instagram/*']))
        for changed in ('logging','admin'):
            bad=copy.deepcopy(new);bad[changed]={'changed':True}
            self.assertFalse(prep.routes_only(old,bad,['/media/instagram/*']))
        bad=copy.deepcopy(new);bad['apps']['http']['servers']['srv0']['routes'][1]['handle'][0]['upstreams'][0]['dial']='other:8000'
        self.assertFalse(prep.routes_only(old,bad,['/media/instagram/*']))

    def test_caddy_generated_groups_may_rename_but_never_merge_or_split(self):
        before={'apps':{'http':{'routes':[{'group':'group2','handle':[{'handler':'a'}]}, {'group':'group2','handle':[{'handler':'b'}]}]}}}
        after=copy.deepcopy(before)
        for row in after['apps']['http']['routes']:row['group']='group5'
        self.assertTrue(prep.routes_only(before,after,[]))
        after['apps']['http']['routes'][1]['group']='group6'
        self.assertFalse(prep.routes_only(before,after,[]))
        before['apps']['http']['routes'][1]['group']='group3'
        after['apps']['http']['routes'][1]['group']='group5'
        self.assertFalse(prep.routes_only(before,after,[]))

    def test_bad_targets_and_ambiguous_flags_refused(self):
        for service in ('team-postgres','caddy','n8n'):
            with self.assertRaises(RuntimeError):prep.candidate_model(model(),service,SHA)
        for sha in ('main','../source','b'*39):
            with self.assertRaises(RuntimeError):prep.candidate_model(model(),'team-api',sha)
        for key in ('SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED','SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED','SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED'):
            for value in ('true','True','unexpected'):
                candidate=model();candidate['services']['team-api']['environment'][key]=value
                with self.assertRaises(RuntimeError):prep.candidate_model(candidate,'team-api',SHA)

    def test_default_cli_never_inspects_runtime(self):
        from unittest.mock import patch
        with patch('sys.argv',['prepare','--target','team']), patch.object(prep,'call',side_effect=AssertionError('Runtime queried')):
            prep.main()

    def test_unsafe_output_or_dirty_checkout_blocks_before_docker(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'candidate'
            with patch.object(prep,'call',side_effect=AssertionError('Command executed')):
                with self.assertRaises(RuntimeError):prep.prepare(SHA,target,'old-api','old-gateway')
            with patch.object(prep,'BACKUPS',Path(folder)), patch.object(prep,'call',return_value=' M unexpected') as call:
                with self.assertRaises(RuntimeError):prep.prepare(SHA,target,'old-api','old-gateway')
                self.assertEqual(call.call_args.args[0],['git','status','--porcelain'])
                self.assertEqual(call.call_count,1)
                self.assertFalse(target.exists())

    def test_reviewed_unmounted_caddy_exception_is_exact_and_opt_in(self):
        import hashlib, tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=root/'deploy/team/Caddyfile';path.parent.mkdir(parents=True);path.write_text('synthetic hotfix')
            checksum=hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(prep,'ROOT',root), patch.object(prep,'call',return_value=' M deploy/team/Caddyfile\n'):
                with self.assertRaises(RuntimeError): prep.checkout_policy()
                self.assertEqual(prep.checkout_policy(checksum)['sha256'],checksum)
                with self.assertRaises(RuntimeError): prep.checkout_policy('0'*64)
            for status in ('M  deploy/team/Caddyfile\n',' M other\n',' M deploy/team/Caddyfile\n?? other\n',''):
                with patch.object(prep,'ROOT',root), patch.object(prep,'call',return_value=status):
                    with self.assertRaises(RuntimeError):prep.checkout_policy(checksum)
            path.unlink();path.symlink_to(root/'elsewhere')
            with patch.object(prep,'ROOT',root), patch.object(prep,'call',return_value=' M deploy/team/Caddyfile\n'):
                with self.assertRaises(RuntimeError):prep.checkout_policy(checksum)

    def test_preserved_file_cannot_be_part_of_any_active_mount(self):
        path=str(prep.ROOT/'deploy/team/Caddyfile')
        for source in (path,str(prep.ROOT),str(prep.ROOT/'deploy/team')):
            with self.assertRaises(RuntimeError):prep.require_unmounted_hotfix({'mode':'preserved_caddy'}, [{'Mounts':[{'Type':'bind','Source':source}]}])
        prep.require_unmounted_hotfix({'mode':'preserved_caddy'},[{'Mounts':[{'Type':'bind','Source':str(prep.ROOT/'deploy/team/private')}]}])

    def test_runtime_environment_drift_is_refused(self):
        from unittest.mock import patch
        current=model(); container={'Config':{'Image':'installed-api','Env':['SECRET=synthetic-private','SOCIALMEI_INSTAGRAM_RUNTIME_MODE=connect','SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false']}}
        with patch.object(prep.publisher,'runtime_shape_matches',return_value=True):
            prep.validate_runtime(current,container,'team-api')
            container['Config']['Env'].append('SOCIALMEI_INSTAGRAM_TOKEN_KEYRING=synthetic-private-must-not-lose')
            with self.assertRaises(RuntimeError):prep.validate_runtime(current,container,'team-api')
            container['Config']['Env'][0]='SECRET=changed'
            with self.assertRaises(RuntimeError):prep.validate_runtime(current,container,'team-api')

    def test_existing_handler_cannot_bypass_structural_checks(self):
        from unittest.mock import patch
        source=':80 {\n route {\n handle /api/v1/* { reverse_proxy team-api:8000 }\n }\n}\n'
        active={'logging':{'logs':{'default':{'encoder':prep.privacy.ENCODER}}}}
        with patch.object(prep.privacy,'_adapt',return_value=active):
            with self.assertRaises(RuntimeError):prep.validate_gateway('fixture',source,active)

    def test_preparation_writes_only_private_artifacts_and_preserves_runtime(self):
        self.preparation_fixture(False)

    def test_preserved_hotfix_preparation_retains_bytes_and_private_receipt(self):
        self.preparation_fixture(True)

    def preparation_fixture(self, preserve_hotfix):
        import contextlib, io, json, tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'team';root.mkdir()
            backups=Path(directory)/'backups';backups.mkdir()
            private=root/'deploy/team/private';private.mkdir(parents=True)
            raw='synthetic protected gateway source'
            (private/'Caddyfile').write_text(raw)
            (root/'compose.team.yaml').write_text('synthetic source')
            hotfix=root/'deploy/team/Caddyfile';hotfix.write_text('synthetic unmounted hotfix')
            checksum=prep.hashlib.sha256(hotfix.read_bytes()).hexdigest()
            baseline=model()
            baseline['services']['team-gateway']['volumes'][0]['source']=str(private/'Caddyfile')
            containers={}
            for service in prep.SERVICES:
                config=baseline['services'][service]
                containers[service]={'Id':'container-'+service,'Image':'sha256:'+'b'*64,
                    'Config':{'Image':config['image'],'Env':[k+'='+v for k,v in config['environment'].items()],
                    'Labels':{'com.docker.compose.project':'socialmei-team',
                              'com.docker.compose.project.working_dir':str(root),
                              'com.docker.compose.project.config_files':str(root/'compose.team.yaml')}},
                    'State':{'Running':True,'Health':{'Status':'healthy'}},
                    'NetworkSettings':{'Networks':{'socialmei-team_api':{}}},
                    'HostConfig':{'PortBindings':{}},
                    'Mounts':[{'Type':'bind','Source':str(private/'Caddyfile'),'Destination':'/etc/caddy/Caddyfile','RW':False}] if service=='team-gateway' else []}
            names=MIGRATIONS
            active={'logging':{'logs':{'default':{'encoder':prep.privacy.ENCODER}}}}
            commands=[]
            def call(args, input=None):
                commands.append(args)
                if args[:2]==['git','status']:return ' M deploy/team/Caddyfile\n' if preserve_hotfix else ''
                if args[:2]==['git','rev-parse']:return SHA if args[2]!='HEAD' else 'b'*40
                if args[:2]==['git','ls-tree']:return '\n'.join('database/migrations/'+p for p in names)
                if args[:2]==['git','show']:return 'synthetic migration'
                if args[:2]==['docker','inspect']:
                    if args[2]=='socialmei-caddy':return json.dumps([{'Mounts':[{'Type':'bind','Source':str(backups/'public.Caddyfile')}]}])
                    service=next(s for s in prep.SERVICES if args[2]=='socialmei-team-'+s+'-1')
                    return json.dumps([containers[service]])
                if args[:2]==['docker','compose']:
                    overlay=next((Path(v) for v in args if v.endswith('.override.private.json')),None)
                    after=copy.deepcopy(baseline)
                    if overlay:
                        obj=json.loads(overlay.read_text())
                        for service,value in obj['services'].items():
                            after['services'][service]['image']=value['image']
                            after['services'][service]['environment'].update(value.get('environment',{}))
                    return json.dumps(after)
                if args[:2]==['docker','exec']:
                    if 'cat' in args:return raw
                    if 'wget' in args:return json.dumps(active)
                    if 'validate' in args:return 'valid configuration'
                raise AssertionError('Unexpected operation')
            output=backups/'prepared'
            with patch.object(prep,'ROOT',root), patch.object(prep,'BACKUPS',backups), patch.object(prep,'call',side_effect=call), \
                 patch.object(prep.preflight,'sql_read',return_value=[names[:26]]), \
                 patch.object(prep.preflight,'inspect_proxy',return_value={'source':'active'}), \
                 patch.object(prep,'validate_gateway',return_value=(raw+' candidate',active)), \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                prep.prepare(SHA,output,'installed-api','installed-gateway',preserved_caddy_sha256=checksum if preserve_hotfix else None)
            receipt=json.loads((output/'preparation.private.json').read_text())
            self.assertFalse(receipt['deployment_executed'])
            if preserve_hotfix:
                self.assertEqual(receipt['checkout_policy']['sha256'],checksum)
                self.assertEqual((output/'checkout-hotfix.preserved.Caddyfile').read_bytes(),hotfix.read_bytes())
            self.assertEqual(hotfix.read_text(),'synthetic unmounted hotfix')
            self.assertEqual(receipt['missing_migrations'],names[26:28])
            self.assertEqual(receipt['unapplied_source_migrations'],names[26:])
            self.assertEqual(receipt['deferred_migrations'],names[28:])
            self.assertEqual(receipt['migration_stage'],'publishing')
            self.assertNotIn('synthetic-private',stdout.getvalue())
            self.assertEqual(output.stat().st_mode & 0o777,0o700)
            for artifact in output.iterdir():self.assertEqual(artifact.stat().st_mode & 0o777,0o600)
            self.assertEqual((private/'Caddyfile').read_text(),raw)
            self.assertEqual(json.loads((output/'team-api.candidate.private.json').read_text())['services']['team-api']['environment']['SECRET'],'synthetic-private')
            self.assertFalse(any('up' in command or 'reload' in command or 'build' in command for command in commands))


import os
@unittest.skipUnless(os.getenv('SOCIALMEI_INSTAGRAM_RELEASE_TEST') == 'true','Disposable Caddy opt-in')
class RealGatewayPreparationTests(unittest.TestCase):
    def test_only_provider_routes_added_to_protected_real_caddy(self):
        import json
        import subprocess
        import tempfile
        import time
        from uuid import uuid4
        source=prep.privacy.with_logging(':8080 {\n route {\n handle /api/v1/* {\n reverse_proxy team-api:8000\n }\n handle / {\n respond landing 200\n }\n }\n}\n')
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'Caddyfile';config.write_text(source)
            name='socialmei-ig-release-'+uuid4().hex[:10]
            local=[item for key in ('http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','all_proxy','ALL_PROXY') for item in ('--env',key+'=')]
            def run(*args,input=None):
                return subprocess.run(['docker',*args],input=input,text=True,capture_output=True,check=True,timeout=30).stdout
            try:
                run('run','-d','--name',name,'--network','none',*local,
                    '--mount',f'type=bind,src={config},dst=/etc/caddy/Caddyfile,readonly','caddy:2-alpine')
                for _ in range(100):
                    try:
                        active=json.loads(run('exec',name,'wget','-qO-','http://127.0.0.1:2019/config/'));break
                    except subprocess.CalledProcessError:time.sleep(.05)
                else:self.fail('Owned Caddy did not become ready')
                changed,adapted=prep.validate_gateway(name,source,active)
                self.assertTrue(prep.privacy.protected(adapted))
                self.assertTrue(all(prep.preflight.proxy_routes(adapted).values()))
                self.assertEqual(run('exec',name,'cat','/etc/caddy/Caddyfile'),source)
                still_active=json.loads(run('exec',name,'wget','-qO-','http://127.0.0.1:2019/config/'))
                self.assertEqual(still_active,active,'Preparation must never reload Caddy')
                run('exec','-i',name,'caddy','validate','--config','/dev/stdin','--adapter','caddyfile',input=changed)
                # A previously protected gateway must stop for review; preparation
                # cannot remove Basic Auth or claim that Meta can reach its routes.
                basic=source.replace(' route {', ' route {\n basic_auth {\n tester $2a$14$OvF3gOBUchjj49Ws.qBH.O6n7NN8xPRWxOZuF0lYxH4hNIsSzbcQm\n }',1)
                auth_active=prep.privacy._normalized_auto_hidden_config(prep.privacy._adapt(name,basic))
                with self.assertRaises(RuntimeError):prep.validate_gateway(name,basic,auth_active)
            finally:
                subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)
