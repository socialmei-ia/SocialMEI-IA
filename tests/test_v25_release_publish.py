"""Synthetic release fixtures only; never invokes Docker or live endpoints."""
import importlib.util
from pathlib import Path
import tempfile
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

PATH = Path(__file__).resolve().parents[1] / 'tools/v25-release-publish.py'

class PublisherTests(unittest.TestCase):
    def module(self):
        self.assertTrue(PATH.is_file(), 'Dedicated V25 publisher is missing')
        spec = importlib.util.spec_from_file_location('v25publisher', PATH)
        value = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(value)
        return value

    def test_provider_guard_preserves_oauth_connect(self):
        m = self.module()
        env = {'SOCIALMEI_AUTH_ENABLED':'true', 'SOCIALMEI_INSTAGRAM_RUNTIME_MODE':'oauth',
               'SOCIALMEI_INSTAGRAM_OAUTH_MODE':'connect'}
        m.validate_flags(env)
        for key in m.DISABLED_FLAGS:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                m.validate_flags(dict(env, **{key:'true'}))

    def test_service_commands_never_widen_scope(self):
        m = self.module()
        for service in ('team-postgres','n8n','waha','socialmei-caddy'):
            with self.assertRaises(RuntimeError): m.legacy.up_command([], service)
        command = m.legacy.up_command(['docker','compose'], 'team-api')
        self.assertEqual(command[-8:], ['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','team-api'])

    def test_failure_at_every_cutover_boundary_restores_only_attempted_services(self):
        m = self.module()
        for phase in ('preflight', 'fresh_backup', 'migrate', 'api', 'caddy', 'gateway', 'smoke', 'receipt'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                p = m.Publisher.__new__(m.Publisher)
                p.folder = Path(directory)
                p.preflight = Mock(); p.fresh_backup = Mock(); p.migrate = Mock()
                p.replace_caddy = Mock(); p.smoke = Mock(); p.record = Mock()
                p.rollback = Mock()
                p.switch = Mock()
                error = RuntimeError('synthetic phase failure')
                if phase in ('api','gateway'):
                    p.switch.side_effect = [error] if phase == 'api' else [None,error]
                elif phase == 'caddy': p.replace_caddy.side_effect = error
                elif phase == 'receipt': p.record.side_effect = error
                else: getattr(p, phase).side_effect = error
                with self.assertRaises(RuntimeError): p.publish()
                if phase in ('preflight','fresh_backup','migrate'):
                    p.rollback.assert_not_called()
                else:
                    self.assertEqual(p.rollback.call_args.args[0], ['team-api'] if phase == 'api' else ['team-api','team-gateway'])

    def test_pinned_build_image_identity_cannot_change(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            p = m.Publisher.__new__(m.Publisher)
            p.sha = 'a'*40
            p.load = Mock(return_value={'candidate_sha':p.sha,'images':{s:{'image':'socialmei-v22/'+s+':'+p.sha,'image_id':'sha256:expected'} for s in m.SERVICES}})
            p.inspect_image = Mock(return_value={'Id':'sha256:other','Config':{'Labels':{'org.opencontainers.image.revision':p.sha}}})
            with self.assertRaises(RuntimeError): p.build_images()

    def test_ledger_extra_or_reordered_versions_cannot_be_migrated(self):
        m = self.module()
        reviewed = list(m.prepare.REVIEWED_MIGRATIONS)
        for installed in (reviewed[:25],reviewed[:26]+['999_unreviewed.sql'],list(reversed(reviewed[:26]))):
            with self.subTest(installed=installed):
                p = m.Publisher.__new__(m.Publisher)
                p.fresh = Path('/synthetic')
                p.meta={'missing_migrations':reviewed[26:]}
                p.backup_checksums = Mock(); p.source = Mock(); p.build_images = Mock()
                p.ledger = Mock(return_value=installed); p.inspect = Mock()
                with self.assertRaises(RuntimeError): p.migrate()
                p.inspect.assert_not_called()

    def test_private_file_rejects_symlinks_and_public_modes(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'private'
            path.write_text('synthetic')
            path.chmod(0o644)
            with self.assertRaises(RuntimeError): m.private_file(path)
            path.chmod(0o600)
            self.assertEqual(m.private_file(path),path)
            alias = Path(directory)/'alias'; alias.symlink_to(path)
            with self.assertRaises(RuntimeError): m.private_file(alias)

    def test_rollback_gateway_validation_needs_no_candidate_image(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); livefile=folder/'live.Caddyfile';livefile.write_text('protected fixture');livefile.chmod(0o600)
            (folder/'gateway.before.Caddyfile').write_text('protected fixture')
            p=m.Publisher.__new__(m.Publisher);p.folder=folder;p.meta={'gateway_config_source':str(livefile)}
            p.inspect=Mock(return_value={'Mounts':[{'Type':'bind','Source':str(livefile),'Destination':'/etc/caddy/Caddyfile','RW':False}]})
            active={'logging':{'logs':{'default':{'encoder':m.prepare.privacy.ENCODER}}}}
            p.run=Mock(side_effect=lambda args,**kwargs: b'protected fixture' if 'cat' in args else json.dumps(active).encode())
            p.inspect_image=Mock(side_effect=AssertionError('Candidate image must not be used by rollback'))
            with patch.object(m,'BACKUPS',folder):p.gateway('before',check_candidate=False)
            p.inspect_image.assert_not_called()

    def test_unrelated_rollback_metadata_or_archived_image_is_rejected(self):
        import tarfile, io
        m=self.module()
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            config=json.dumps({'architecture':'amd64','os':'linux','rootfs':{'type':'layers','diff_ids':['sha256:'+hashlib.sha256(b'fixture').hexdigest()]}}).encode();good='sha256:'+hashlib.sha256(config).hexdigest()
            p=m.Publisher.__new__(m.Publisher);p.folder=folder;p.rollback_backup=folder
            p.meta={'installed_images':{s:{'image_id':good,'container_id':'old-'+s} for s in m.SERVICES},'gateway_config_source':str(folder/'live.Caddyfile')}
            p.model=Mock(side_effect=lambda s,mode:{'services':{s:{'image':'old-'+s}}})
            (folder/'containers.json').write_text(json.dumps([{'Name':'/socialmei-team-'+s+'-1','Id':'old-'+s,'Image':good,'Config':{'Image':'old-'+s}} for s in m.SERVICES]))
            (folder/'image-ids.txt').write_text(good+'\n')
            (folder/'gateway.before.Caddyfile').write_bytes(b'protected fixture')
            def archive(path,entries):
                with tarfile.open(path,'w:gz') as tar:
                    for name,data in entries.items():
                        info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
            config_name=good.removeprefix('sha256:')+'.json'
            manifest=[{'Config':config_name,'RepoTags':['old-team-api','old-team-gateway'],'Layers':['layer.tar']}]
            archive(folder/'images.tar.gz',{'manifest.json':json.dumps(manifest).encode(),config_name:config,'layer.tar':b'fixture'})
            archive(folder/'runtime-config.tar.gz',{str(folder/'live.Caddyfile').lstrip('/'):b'protected fixture'})
            for name in ('containers.json','image-ids.txt'):
                (folder/name).chmod(0o600)
            p.rollback_material()
            (folder/'image-ids.txt').write_text('sha256:'+'f'*64+'\n')
            with self.assertRaises(RuntimeError):p.rollback_material()
            (folder/'image-ids.txt').write_text(good+'\n')
            archive(folder/'images.tar.gz',{'manifest.json':json.dumps(manifest).encode(),config_name:b'wrong config','layer.tar':b'fixture'})
            with self.assertRaises(RuntimeError):p.rollback_material()

    def test_oci_archive_checks_index_manifest_config_chain(self):
        import io, tarfile
        m=self.module()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'images.tar.gz'
            blobs={}
            def blob(value):
                data=json.dumps(value).encode()
                key='sha256:'+hashlib.sha256(data).hexdigest()
                blobs['blobs/sha256/'+key[7:]]=data
                return {'digest':key,'size':len(data)}
            layer=blob({'synthetic':'layer'})
            config=blob({'architecture':'amd64','os':'linux','rootfs':{'type':'layers','diff_ids':[layer['digest']]}})
            manifest=blob({'schemaVersion':2,'config':config,'layers':[layer]})
            manifest['platform']={'os':'linux','architecture':'amd64'}
            root=blob({'schemaVersion':2,'manifests':[manifest]})
            tag='synthetic:old'
            def save(tamper=None):
                entries=dict(blobs)
                entries['index.json']=json.dumps({'manifests':[root]}).encode()
                entries['manifest.json']=json.dumps([{
                    'Config':'blobs/sha256/'+config['digest'][7:],
                    'RepoTags':[tag],
                    'Layers':['blobs/sha256/'+layer['digest'][7:]]
                }]).encode()
                if tamper: tamper(entries)
                with tarfile.open(path,'w:gz') as archive:
                    for name,data in entries.items():
                        info=tarfile.TarInfo(name);info.size=len(data)
                        archive.addfile(info,io.BytesIO(data))
            save()
            m.verify_image_archive(path,{tag:root['digest']})
            # Classic config-addressed saves remain supported.
            m.verify_image_archive(path,{tag:config['digest']})
            for change in (
                lambda e:e.pop('blobs/sha256/'+manifest['digest'][7:]),
                lambda e:e.update({'blobs/sha256/'+root['digest'][7:]:b'{}'}),
                lambda e:e.update({'blobs/sha256/'+manifest['digest'][7:]:b'{}'}),
                lambda e:e.update({'blobs/sha256/'+config['digest'][7:]:b'{}'}),
                lambda e:e.pop('blobs/sha256/'+layer['digest'][7:]),
                lambda e:e.update({'index.json':b'{"manifests":[]}'}),
            ):
                save(change)
                with self.assertRaises(RuntimeError):
                    m.verify_image_archive(path,{tag:root['digest']})
            save()
            with self.assertRaises(RuntimeError):
                m.verify_image_archive(path,{tag:'sha256:'+'f'*64})

    def test_dirty_checkout_is_rejected_without_mutation(self):
        m = self.module()
        p = m.Publisher.__new__(m.Publisher)
        p.meta = {'checkout_sha':'a'*40,'checkout_policy':{'mode':'clean'}}
        p.run = Mock(side_effect=[b'a'*40+b'\n',b' M unexpected.txt\n'])
        p.inspect = Mock()
        with self.assertRaises(RuntimeError): p.checkout()
        self.assertTrue(all(call.args[0][0] == 'git' for call in p.run.call_args_list))
        p.inspect.assert_not_called()

    def test_gateway_disk_drift_is_rejected_before_adaptation(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            m.BACKUPS = Path(directory)
            p = m.Publisher.__new__(m.Publisher); p.folder = Path(directory)
            raw = Path(directory)/'bound'; raw.write_text('changed'); raw.chmod(0o600)
            (p.folder/'gateway.before.Caddyfile').write_text('before')
            p.meta = {'gateway_config_source':str(raw)}
            p.inspect = Mock(return_value={'Mounts':[{'Destination':'/etc/caddy/Caddyfile','Type':'bind','Source':str(raw),'RW':False}]})
            p.run = Mock()
            with self.assertRaises(RuntimeError): p.gateway('before')
            p.run.assert_not_called()

    def test_gateway_active_config_drift_is_rejected(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            m.BACKUPS = Path(directory)
            p = m.Publisher.__new__(m.Publisher); p.folder = Path(directory)
            raw = Path(directory)/'bound'; raw.write_text('before'); raw.chmod(0o600)
            (p.folder/'gateway.before.Caddyfile').write_text('before')
            p.meta = {'gateway_config_source':str(raw)}
            p.inspect = Mock(return_value={'Mounts':[{'Destination':'/etc/caddy/Caddyfile','Type':'bind','Source':str(raw),'RW':False}],'Config':{'Env':[]}})
            p.run = Mock(side_effect=[b'before',b'{"changed":true}',b'{}'])
            with self.assertRaises(RuntimeError): p.gateway('before')
            self.assertEqual(len(p.run.call_args_list),3)

    def test_prepared_artifact_hash_drift_is_rejected(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            p = m.Publisher.__new__(m.Publisher); p.folder = Path(directory)
            names = {'compose-commands.private.json','gateway.before.Caddyfile','gateway.candidate.Caddyfile'}
            names |= {s+'.'+kind+'.private.json' for s in m.SERVICES for kind in ('installed','before','candidate','override')}
            hashes = {}
            for name in names:
                file = p.folder/name; file.write_bytes(b'prepared'); file.chmod(0o600)
                hashes[name] = m.digest(file)
            p.meta = {'hashes':hashes,'checkout_policy':{'mode':'clean'}}
            (p.folder/'gateway.candidate.Caddyfile').write_text('tampered')
            with self.assertRaises(RuntimeError): p.artifacts()

    def test_candidate_archive_tampering_and_extra_files_are_rejected(self):
        m = self.module()
        for extra in (False,True):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                p = m.Publisher.__new__(m.Publisher); p.folder = Path(directory); p.sha='a'*40
                source = p.folder/'source'; source.mkdir()
                (source/'reviewed.txt').write_bytes(b'changed' if not extra else b'reviewed')
                if extra: (source/'extra.txt').write_text('extra')
                data=b'reviewed'; oid=hashlib.sha1(b'blob 8\0'+data).hexdigest()
                p.run = Mock(return_value=('100644 blob '+oid+'\treviewed.txt\n').encode())
                with self.assertRaises(RuntimeError): p.source()

    def test_caddy_authentication_is_detected_in_nested_routes(self):
        m = self.module()
        self.assertFalse(m.has_http_auth({'apps':{'http':{}}}))
        self.assertTrue(m.has_http_auth({'apps':{'http':{'route':[{'handle':[{'handler':'authentication'}]}]}}}))

    def test_rollback_continues_other_service_after_one_restore_failure(self):
        m = self.module()
        p = m.Publisher.__new__(m.Publisher)
        p.artifacts=Mock();p.backup_checksums=Mock();p.models=Mock();p.checkout=Mock();p.rollback_material=Mock()
        p.rollback_backup=Path('/synthetic');p.replace_caddy=Mock()
        p.switch=Mock(side_effect=[RuntimeError('api failed'),None])
        with self.assertRaises(RuntimeError): p.rollback()
        self.assertEqual([c.args for c in p.switch.call_args_list],[('before',('team-api',)),('before',('team-gateway',))])
        p.models.assert_called_once_with(rollback=True)

    def test_migration_runs_pinned_api_on_only_database_network_and_removes_env(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            p=m.Publisher.__new__(m.Publisher);p.folder=Path(directory);p.fresh=Path('/synthetic');p.sha='a'*40
            p.backup_checksums=Mock();p.source=Mock();p.build_images=Mock()
            reviewed=list(m.prepare.REVIEWED_MIGRATIONS)
            p.meta={'missing_migrations':reviewed[26:]}
            p.ledger=Mock(side_effect=[reviewed[:26],reviewed])
            p.inspect=Mock(side_effect=[{'Config':{'Env':['DATABASE_URL=postgresql://fixture:synthetic-secret@team-postgres/fixture']},'NetworkSettings':{'Networks':{'database':{},'api':{}}}}, {'Config':{'Env':['POSTGRES_USER=fixture','POSTGRES_DB=fixture']},'NetworkSettings':{'Networks':{'database':{}}}}])
            p.inspect_image=Mock(return_value={'Id':'sha256:pinned'})
            p.run=Mock()
            p.migrate()
            command=p.run.call_args.args[0]
            self.assertEqual(command[command.index('--network')+1],'database')
            self.assertEqual(command[-2: ],['sha256:pinned','/maintenance/team_migrate.py'])
            self.assertIn('PYTHONPATH=/app',command)
            self.assertNotIn('DATABASE_URL=synthetic-secret',command)
            self.assertFalse((p.folder/'v25-migration.private.env').exists())
            self.assertNotIn('--privileged',command)

    def test_database_target_cannot_escape_to_another_database_or_host(self):
        m=self.module()
        pg={'Config':{'Env':['POSTGRES_USER=fixture','POSTGRES_DB=fixture']},'NetworkSettings':{'Networks':{'database':{'Aliases':['team-postgres']}}}}
        api={'Config':{'Env':['DATABASE_URL=postgresql://fixture:secret@team-postgres/fixture']},'NetworkSettings':{'Networks':{'database':{}}}}
        self.assertEqual(m.database_target(api,pg),'database')
        for url in ('postgresql://fixture:secret@other/fixture','postgresql://fixture:secret@team-postgres/other','postgresql://fixture:secret@team-postgres/fixture?host=other'):
            api['Config']['Env']=['DATABASE_URL='+url]
            with self.assertRaises(RuntimeError):m.database_target(api,pg)

    def test_additive_schema_after_rollback_requires_new_exact_preparation(self):
        m=self.module();p=m.Publisher.__new__(m.Publisher)
        reviewed=list(m.prepare.REVIEWED_MIGRATIONS)
        p.meta={'missing_migrations':reviewed[26:]}
        self.assertEqual(p.baseline_ledger(),reviewed[:26])
        p.meta={'missing_migrations':[]}
        self.assertEqual(p.baseline_ledger(),reviewed)
        p.meta={'missing_migrations':reviewed[27:29]}
        with self.assertRaises(RuntimeError):p.baseline_ledger()

    def test_unknown_private_caddy_change_is_never_overwritten(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);source=folder/'live';source.write_bytes(b'operator changed');source.chmod(0o600)
            (folder/'gateway.before.Caddyfile').write_bytes(b'before');(folder/'gateway.candidate.Caddyfile').write_bytes(b'candidate')
            p=m.Publisher.__new__(m.Publisher);p.folder=folder;p.meta={'gateway_config_source':str(source)}
            with patch.object(m,'BACKUPS',folder),self.assertRaises(RuntimeError):p.replace_caddy('before')
            self.assertEqual(source.read_bytes(),b'operator changed')

    def test_rollback_never_restarts_gateway_with_unverified_configuration(self):
        m=self.module();p=m.Publisher.__new__(m.Publisher)
        p.artifacts=Mock();p.backup_checksums=Mock();p.rollback_material=Mock();p.models=Mock();p.checkout=Mock()
        p.rollback_backup=Path('/synthetic');p.replace_caddy=Mock(side_effect=RuntimeError('unknown config'));p.switch=Mock()
        with self.assertRaises(RuntimeError):p.rollback()
        p.switch.assert_called_once_with('before',('team-api',))

if __name__ == '__main__': unittest.main()
