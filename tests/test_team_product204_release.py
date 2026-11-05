"""App-only038 release safety; no SSH, production or database writes."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch, mock_open

from test_team_functional038_release import Functional038ReleaseTests


class Product204ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'tools/team-product204-release.py'
        spec = importlib.util.spec_from_file_location('product204_release_test', path)
        cls.m = importlib.util.module_from_spec(spec)
        fake = ModuleType('fcntl')
        fake.flock = MagicMock()
        fake.LOCK_EX, fake.LOCK_NB = 2, 4
        with patch.dict(sys.modules, {'fcntl': fake}) if sys.platform == 'win32' else patch.dict(sys.modules, {}):
            spec.loader.exec_module(cls.m)

    fixture = Functional038ReleaseTests.fixture
    test_only_two_images_and_api_release_can_change = Functional038ReleaseTests.test_only_two_images_and_api_release_can_change
    test_runtime_env_aliases_and_restart_must_match = Functional038ReleaseTests.test_runtime_env_aliases_and_restart_must_match
    test_compose_null_command_inherits_image_defaults = Functional038ReleaseTests.test_compose_null_command_inherits_image_defaults
    test_health_heartbeat_is_not_drift_but_protected_restart_is = Functional038ReleaseTests.test_health_heartbeat_is_not_drift_but_protected_restart_is
    test_exact038_ledger_rejects_missing_extra_and035 = Functional038ReleaseTests.test_exact038_ledger_rejects_missing_extra_and035
    test_sender_flags_must_stay_off = Functional038ReleaseTests.test_sender_flags_must_stay_off
    test_revision_label_alone_does_not_allow_retargeted_image = Functional038ReleaseTests.test_revision_label_alone_does_not_allow_retargeted_image
    test_private_archive_requires_exact_files_and_bytes = Functional038ReleaseTests.test_private_archive_requires_exact_files_and_bytes

    def test_pins_are_app_only_and_old_operator_remains_unchanged(self):
        m = self.m
        self.assertEqual(m.BASE_SHA, 'a4720f8b7ea98a67cb40b7b3208acdd7e8bcd510')
        self.assertEqual(m.CANDIDATE_SHA, 'f2805c8a1549071010850090606c6a92f9d6ba7a')
        self.assertEqual(m.BUNDLE_SHA256, '5b682c41d76a002a574522d10405232eb4673216e0b8245e49274e84ab01ff34')
        self.assertEqual(m.runtime.ledger035, m.runtime.ledger038)
        self.assertFalse(hasattr(m, 'migrate038'))
        self.assertFalse(hasattr(m, 'resume'))
        self.assertEqual(set(m.NAMES), {'team-api', 'team-gateway'})
        self.assertIn('scripts/v22-businesses.js', m.CANDIDATE_STATIC_FILES)
        self.assertIn('styles/v22-businesses.css', m.CANDIDATE_STATIC_FILES)

    def test_inspect_is_read_only_and_apply_requires_new_authorization(self):
        m = self.m
        with patch.object(m, 'source_gate'), patch.object(m, 'preflight', return_value=({}, {})), \
             patch.object(m, 'publish_services') as publish, patch.object(m, 'backup_gate') as backup, \
             patch.object(m.runtime, 'migrate038') as forbidden:
            result = m.operate(Path('/source'), Path('/bundle'))
            self.assertFalse(result['production_changed'])
            self.assertFalse(result['migrations_executed'])
            for authorization in (None, '266-035-to-a472-038', 'a472-038-to-754a-038-app-only'):
                with self.assertRaises(m.legacy.Blocked):
                    m.operate(Path('/source'), Path('/bundle'), Path('/backup'), True, authorization)
            publish.assert_not_called()
            backup.assert_not_called()
            forbidden.assert_not_called()

    def test_candidate_assets_include_new_panels_but_baseline_only_contains_existing_files(self):
        m = self.m
        self.assertEqual(len(m.CANDIDATE_STATIC_FILES), len(set(m.CANDIDATE_STATIC_FILES)))
        self.assertTrue(set(m.BASELINE_STATIC_FILES) <= set(m.CANDIDATE_STATIC_FILES))
        for name in ('scripts/report-viewer-details.js', 'scripts/v22-customer-reporting.js',
                     'scripts/v22-finance-reporting.js', 'scripts/v22-product-reporting.js',
                     'scripts/v22-workspace-audit.js', 'scripts/v22-businesses.js'):
            self.assertIn(name, m.CANDIDATE_STATIC_FILES)
            self.assertNotIn(name, m.BASELINE_STATIC_FILES)
        self.assertIn('scripts/auth-store.js', m.BASELINE_STATIC_FILES)
        self.assertIn('scripts/v22-bootstrap.js', m.BASELINE_STATIC_FILES)

    @unittest.skipUnless(os.name == 'posix', 'Unix ownership checked in Linux')
    def test_private_baseline_after_own_verified_rollback_uses_linked_cas_without_rewriting_old_journal(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            root = parent/'checkout'; root.mkdir()
            backups = parent/'backups'; backups.mkdir()
            private = parent/'private'; private.mkdir(mode=0o700)
            baseline = private/m.BASELINE_WINDOW; baseline.mkdir(mode=0o700)
            env = root/'.env.team'; env.write_text('fictional'); env.chmod(0o600)
            compose = root/'compose.json'; compose.write_text('{}')
            path = baseline/'team-api.candidate.compose.json'
            path.write_text(json.dumps({'services':{'team-api':{'image':m.legacy.image_tags(m.BASE_SHA)['team-api'],'environment':{'SOCIALMEI_RELEASE_SHA':m.BASE_SHA}}}})); path.chmod(0o600)
            old = baseline/'functional038-state.json'
            old.write_text(json.dumps({'source_sha':m.BASE_SHA,'baseline_sha':'266e59b6a766c07f60c83b7b3053b33fc91cc135','bundle_sha256':'43f5df836e3b49e4e99a5a01f0d243108f5310be4cd8e2d7d68a59d28afcac2a','phase':'published038','candidate_runtime':{'team-api':'original-container-cas'}})); old.chmod(0o600)
            original = old.read_bytes()
            _, container, _ = self.fixture()
            container['Config']['Labels']={'com.docker.compose.service':'team-api','com.docker.compose.project.working_dir':str(root),'com.docker.compose.project.environment_file':str(env),'com.docker.compose.project.config_files':str(compose)+','+str(path)}
            command=['docker','--host=unix:///var/run/docker.sock','compose','-p','socialmei-team','--env-file',str(env),'-f',str(compose),'-f',str(path)]
            hashes={str(p):m.legacy.digest_file(p) for p in [env,compose,path]}
            recovery=private/'product204-window-20261105T000000Z-fixture'; recovery.mkdir(mode=0o700)
            receipt=recovery/m.BACKUP_RECEIPT
            receipt.write_text(json.dumps({'source_sha':m.CANDIDATE_SHA,'baseline_sha':m.BASE_SHA,'release_profile':'038'})); receipt.chmod(0o600)
            state={'source_sha':m.CANDIDATE_SHA,'baseline_sha':m.BASE_SHA,'bundle_sha256':m.BUNDLE_SHA256,'phase':'rolled_back_schema038_retained','migrations_executed':False,'rolled_back_services':['team-api'],'rolled_back_runtime':{'team-api':'restored-container-cas'},'backup_receipt_sha256':m.legacy.digest_file(receipt),'protected':{n:'protected-cas' for n in m.PROTECTED},'backup_plans':{'team-api':{'wd':str(root),'command':command,'files':hashes,'mount_fingerprints':{'private':'hash'}}}}
            journal=recovery/m.JOURNAL
            journal.write_text(json.dumps(state)); journal.chmod(0o600)
            with patch.object(m,'approved_context',side_effect=m.legacy.Blocked('compose_fora_do_escopo')), patch.object(m.legacy,'ROOT',root), patch.object(m.legacy,'BACKUPS',backups), patch.object(m.legacy,'PRIVATE',private), patch.object(m,'runtime_fingerprint',return_value='restored-container-cas'), patch.object(m,'mount_fingerprints',return_value={'private':'hash'}), patch.object(m,'protected_fingerprint',return_value='protected-cas'), patch.object(m.legacy,'inspect',return_value=container):
                self.assertEqual(m.context(container),(root,command,hashes))
                self.assertEqual(old.read_bytes(),original)
                for key,value in [('source_sha','unexpected'),('backup_receipt_sha256','changed'),('protected',{}),('rolled_back_runtime',{'team-api':'unexpected'})]:
                    changed=copy.deepcopy(state); changed[key]=value; journal.write_text(json.dumps(changed))
                    with self.subTest(key=key), self.assertRaises(m.legacy.Blocked): m.context(container)
                for key,value in [('files',{}),('mount_fingerprints',{}),('command',['unexpected'])]:
                    changed=copy.deepcopy(state); changed['backup_plans']['team-api'][key]=value
                    journal.write_text(json.dumps(changed))
                    with self.subTest(plan_key=key), self.assertRaises(m.legacy.Blocked): m.context(container)
                journal.write_text(json.dumps(state))
                duplicate=private/'product204-window-duplicate'; duplicate.mkdir(mode=0o700)
                for filename in (m.JOURNAL,m.BACKUP_RECEIPT):
                    copied=duplicate/filename; copied.write_bytes((recovery/filename).read_bytes()); copied.chmod(0o600)
                with self.assertRaises(m.legacy.Blocked): m.context(container)
                for filename in (m.JOURNAL,m.BACKUP_RECEIPT): (duplicate/filename).unlink()
                duplicate.rmdir()
                journal.write_text(json.dumps(state)); recovery.chmod(0o755)
                with self.assertRaises(m.legacy.Blocked): m.context(container)

    def test_rollback_canary_capture_never_requests_assets_absent_in_a472(self):
        m = self.m
        def existing_asset(url, status):
            self.assertEqual(status, 200)
            self.assertIn(url.removeprefix('/frontend/'), m.BASELINE_STATIC_FILES)
            return b'baseline-only'
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(m, 'source_gate'), patch.object(m, 'preflight', return_value=({}, {})), \
             patch.object(m, 'backup_gate', return_value={}), patch.object(m, 'inputs_unchanged'), \
             patch.object(m, 'publish_services') as publish, patch.object(m, 'write_journal') as journal, \
             patch.object(m.legacy, 'digest_file', return_value='backup-digest'), \
             patch.object(m.legacy, 'https', side_effect=existing_asset), \
             patch.object(m.legacy.fcntl, 'flock'), patch.object(os, 'geteuid', return_value=0, create=True), \
             patch('builtins.open', mock_open()):
            result = m.operate(Path('/source'), Path('/bundle'), Path(temp), True, m.AUTHORIZATION)
            self.assertFalse(result['migrations_executed'])
            self.assertEqual(set(journal.call_args.args[1]['old_files']), set(m.BASELINE_STATIC_FILES))
            publish.assert_called_once()

    def test_preflight_inherits038_baseline_and_sender_guards(self):
        m = self.m
        with patch.object(m.runtime, 'preflight', return_value=({'test': 'plan'}, {'protected': 'hash'})), \
             patch.object(m, 'no_external_senders') as send:
            self.assertEqual(m.preflight(Path('/source'), Path('/bundle')),
                             ({'test': 'plan'}, {'protected': 'hash'}))
            send.assert_called_once_with({'test': 'plan'})

    @unittest.skipUnless(os.name == 'posix', 'Unix ownership gate runs in Linux CI/container')
    def test_only_exact_published_baseline_private_overlay_is_accepted(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            root = parent / 'checkout'; root.mkdir()
            backups = parent / 'backups'; backups.mkdir()
            private = parent / 'private'; private.mkdir()
            folder = private / m.BASELINE_WINDOW; folder.mkdir(mode=0o700)
            env = root / '.env.team'; env.write_text('fictional only')
            compose = root / 'compose.yaml'; compose.write_text('services: {}')
            path = folder / 'team-api.candidate.compose.json'
            expected = {'services': {'team-api': {'image': m.legacy.image_tags(m.BASE_SHA)['team-api'],
                        'environment': {'SOCIALMEI_RELEASE_SHA': m.BASE_SHA}}}}
            path.write_text(json.dumps(expected)); path.chmod(0o600)
            container = self.fixture()[1]
            container['Config']['Labels'] = {
                'com.docker.compose.project': 'socialmei-team',
                'com.docker.compose.service': 'team-api',
                'com.docker.compose.project.working_dir': str(root),
                'com.docker.compose.project.environment_file': str(env),
                'com.docker.compose.project.config_files': str(compose) + ',' + str(path),
            }
            journal = {'source_sha':m.BASE_SHA,
                       'baseline_sha':'266e59b6a766c07f60c83b7b3053b33fc91cc135',
                       'bundle_sha256':'43f5df836e3b49e4e99a5a01f0d243108f5310be4cd8e2d7d68a59d28afcac2a',
                       'phase':'published038', 'candidate_runtime':{'team-api':m.runtime_fingerprint(container)}}
            journal_file = folder / 'functional038-state.json'
            journal_file.write_text(json.dumps(journal)); journal_file.chmod(0o600)
            original_stat = Path.stat
            def root_owned_fixture(path, *args, **kwargs):
                result = original_stat(path, *args, **kwargs)
                if path.is_relative_to(folder):
                    fields = list(result); fields[4] = 0
                    return os.stat_result(fields)
                return result
            with patch.object(Path, 'stat', root_owned_fixture), \
                 patch.object(m.legacy, 'ROOT', root), patch.object(m.legacy, 'BACKUPS', backups), \
                 patch.object(m.legacy, 'PRIVATE', private):
                wd, command, hashes = m.context(container)
                self.assertEqual(wd, root)
                self.assertEqual(command[-2:], ['-f', str(path)])
                self.assertEqual(set(hashes), {str(env), str(compose), str(path)})
                path.write_text('{"services":{}}')
                with self.assertRaisesRegex(m.legacy.Blocked, 'overlay_baseline_conteudo_diverge'):
                    m.context(container)
                path.write_text(json.dumps(expected))
                journal['phase'] = 'rolled_back_schema038_retained'
                journal_file.write_text(json.dumps(journal))
                with self.assertRaisesRegex(m.legacy.Blocked, 'overlay_baseline_journal_diverge'):
                    m.context(container)
                journal['phase'] = 'published038'
                journal['candidate_runtime']['team-api'] = 'changed'
                journal_file.write_text(json.dumps(journal))
                with self.assertRaisesRegex(m.legacy.Blocked, 'overlay_baseline_journal_diverge'):
                    m.context(container)
                foreign = private / 'arbitrary.compose.json'; foreign.write_text('{}')
                container['Config']['Labels']['com.docker.compose.project.config_files'] += ',' + str(foreign)
                with self.assertRaisesRegex(m.legacy.Blocked, 'overlay_baseline_fora_do_escopo'):
                    m.context(container)

    def test_publisher_updates_only_two_services_and_never_calls_migrator(self):
        m = self.m
        plans = {}
        current = {}
        for service, name in m.NAMES.items():
            model, container, _ = self.fixture(service)
            plans[service] = {'wd': Path('/fixture'), 'command': ['docker', 'compose'],
                              'container': container, 'before': model,
                              'candidate_image_id': 'candidate-' + service}
            current[name] = container
        state = {'attempted': [], 'candidate_runtime': {}}
        def docker(*args, **kwargs):
            service = next(s for s in m.NAMES if s in args[-1])
            return json.dumps([{'Id': plans[service]['candidate_image_id']}]).encode()
        with patch.object(m, 'ledger038') as ledger, patch.object(m, 'fresh_backup'), \
             patch.object(m, 'write_journal'), patch.object(m, 'inputs_unchanged'), \
             patch.object(m, 'image_for'), patch.object(m, 'allowed_model'), \
             patch.object(m, 'overlay_file', side_effect=lambda folder, service: folder / service), \
             patch.object(m, 'capture_candidate'), patch.object(m.legacy, 'inspect', side_effect=lambda name: current[name]), \
             patch.object(m.legacy, 'docker', side_effect=docker), patch.object(m.legacy, 'render'), \
             patch.object(m.legacy, 'run') as run, patch.object(m.legacy, 'wait_service'), \
             patch.object(m.legacy, 'public_smoke') as smoke, \
             patch.object(m.legacy, 'digest_file', return_value='expected-file'), \
             patch.object(m.runtime, 'migrate038') as forbidden:
            m.publish_services(Path('/source'), plans, {}, Path('/backup'), {}, state)
            self.assertEqual(state['attempted'], list(m.NAMES))
            self.assertEqual(state['phase'], 'published_app_only038')
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                command = call.args[0]
                self.assertEqual(command[-7:], ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', command[-1]])
                self.assertIn(command[-1], m.NAMES)
            self.assertGreaterEqual(ledger.call_count, 5)
            self.assertEqual(set(smoke.call_args.kwargs['expected_files']), set(m.CANDIDATE_STATIC_FILES))
            forbidden.assert_not_called()

    def test_publication_failure_requires_exact038_then_image_only_recovery(self):
        m = self.m
        state = {'attempted': []}
        with patch.object(m, 'ledger038'), patch.object(m, 'fresh_backup'), \
             patch.object(m, 'write_journal'), patch.object(m.legacy, 'public_smoke', side_effect=RuntimeError('fixture_failure')), \
             patch.object(m.legacy, 'digest_file', return_value='fixture'), \
             patch.object(m, 'rollback_services') as recover, patch.object(m.runtime, 'migrate038') as forbidden:
            with self.assertRaisesRegex(RuntimeError, 'fixture_failure'):
                m.publish_services(Path('/source'), {}, {}, Path('/backup'), {}, state)
            self.assertEqual(state['phase'], 'app_only_recovery_required')
            recover.assert_called_once()
            forbidden.assert_not_called()

    def test_unknown_ledger_prevents_unsafe_recovery(self):
        m = self.m
        with patch.object(m, 'ledger038', side_effect=m.legacy.Blocked('ledger_divergente')), \
             patch.object(m, 'rollback_services') as recover:
            with self.assertRaisesRegex(m.legacy.Blocked, 'ledger_divergente'):
                m.publish_services(Path('/source'), {}, {}, Path('/backup'), {}, {})
            recover.assert_not_called()

    @unittest.skipUnless(os.name == 'posix', 'Unix ownership gate runs in Linux CI/container')
    def test_backup038_requires_data_schema_sequences_accounts_and_private_images(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            folder = parent / 'product204'; folder.mkdir(mode=0o700)
            config = parent / 'fixture.env'; config.write_text('fictional fixture')
            plans = {'team-api': {'container': self.fixture()[1], 'files': {str(config): m.legacy.digest_file(config)}, 'mount_fingerprints': {}}}
            (folder / 'postgres.dump').write_bytes(b'isolated dummy; real PG restore tested separately')
            (folder / 'images-before.tar').write_bytes(b'image content checked independently')
            with tarfile.open(folder / 'private-config.tar', 'w') as archive:
                archive.add(config, arcname='config/' + hashlib.sha256(str(config).encode()).hexdigest())
            restore = {'backup_sha256': m.legacy.digest_file(folder / 'postgres.dump'),
                       'ledger': sorted(m.profile.MIGRATIONS038), 'restore_verified': True,
                       'isolated': True, 'migrations_executed': False, 'production_runtime_changed': False,
                       'fingerprints_match': True, 'schema_and_constraints_match': True, 'table_count': 74,
                       'sequence_states_match': True, 'accounts_memberships_match': True,
                       'metadata_groups': ['columns', 'constraint_properties', 'constraints', 'environment',
                                           'functions', 'indexes', 'schemas', 'sequences', 'tables', 'triggers', 'views']}
            receipt = {'source_sha': m.CANDIDATE_SHA, 'baseline_sha': m.BASE_SHA, 'release_profile': '038',
                       'captured_unix': time.time(), 'runtime_fingerprints': {'team-api': m.runtime_fingerprint(plans['team-api']['container'])},
                       'mount_fingerprints': {'team-api': {}}}
            def save():
                (folder / 'restore038.json').write_text(json.dumps(restore))
                receipt['sha256'] = {n: m.legacy.digest_file(folder / n) for n in
                                    ['postgres.dump', 'images-before.tar', 'private-config.tar', 'restore038.json']}
                (folder / m.BACKUP_RECEIPT).write_text(json.dumps(receipt))
                for path in folder.iterdir(): path.chmod(0o600)
            save()
            original_stat = Path.stat
            def root_owned_fixture(path, *args, **kwargs):
                result = original_stat(path, *args, **kwargs)
                if path.is_relative_to(folder):
                    fields = list(result); fields[4] = 0
                    return os.stat_result(fields)
                return result
            with patch.object(Path, 'stat', root_owned_fixture), patch.object(m.legacy, 'PRIVATE', parent), \
                 patch.object(m, 'sibling', return_value=SimpleNamespace(verify_archive_config_digests=MagicMock())):
                self.assertEqual(m.backup_gate(folder, plans)['source_sha'], m.CANDIDATE_SHA)
                for key, bad in [('sequence_states_match', False), ('accounts_memberships_match', False),
                                 ('table_count', 71), ('ledger', sorted(m.profile.MIGRATIONS)),
                                 ('metadata_groups', ['columns']), ('migrations_executed', True)]:
                    previous = restore[key]; restore[key] = bad; save()
                    with self.assertRaises(m.legacy.Blocked): m.backup_gate(folder, plans)
                    restore[key] = previous; save()
                receipt['captured_unix'] -= 1000; save()
                with self.assertRaises(m.legacy.Blocked): m.backup_gate(folder, plans)
                self.assertEqual(m.backup_gate(folder, plans, fresh=False)['source_sha'], m.CANDIDATE_SHA)


del Functional038ReleaseTests

if __name__ == '__main__':
    unittest.main()
