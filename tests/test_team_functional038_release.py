"""Pinned 266/035 to 038 release gates; fake runtime, no SSH or live Docker."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tarfile
import hashlib
from types import SimpleNamespace
from types import ModuleType
import unittest
from unittest.mock import MagicMock, mock_open, patch


class Functional038ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('functional038_release_test', Path(__file__).resolve().parents[1] / 'tools/team-functional038-release.py')
        cls.m = importlib.util.module_from_spec(spec)
        fake = ModuleType('fcntl')
        fake.flock = MagicMock()
        fake.LOCK_EX, fake.LOCK_NB = 2, 4
        with patch.dict(sys.modules, {'fcntl': fake}) if sys.platform == 'win32' else patch.dict(sys.modules, {}):
            spec.loader.exec_module(cls.m)

    def fixture(self, service='team-api'):
        m = self.m
        config = {'image': 'baseline', 'environment': {'FLAG': 'off'}, 'networks': {'api': {'aliases': ['private-api']}}}
        model = {'services': {service: config}, 'networks': {'api': {'name': 'team_api'}}}
        image = {'Config': {'Env': ['PATH=/bin'], 'User': '', 'Cmd': ['serve']}}
        container = {'Id': 'old-' + service, 'Name': '/container-' + service, 'Image': 'old-image',
                     'Config': {'Image': 'baseline', 'Env': ['PATH=/bin', 'FLAG=off'], 'User': '', 'Cmd': ['serve']},
                     'HostConfig': {'RestartPolicy': {'Name': 'no'}}, 'Mounts': [],
                     'NetworkSettings': {'Networks': {'team_api': {'Aliases': [service, 'container-' + service, 'private-api']}}},
                     'State': {'Running': True, 'StartedAt': 'same', 'Health': {'Log': [1]}}}
        return model, container, image

    def test_only_two_images_and_api_release_can_change(self):
        m = self.m
        for service in m.NAMES:
            before, _, _ = self.fixture(service)
            after = copy.deepcopy(before)
            after['services'][service]['image'] = m.legacy.image_tags(m.CANDIDATE_SHA)[service]
            if service == 'team-api':
                after['services'][service]['environment']['SOCIALMEI_RELEASE_SHA'] = m.CANDIDATE_SHA
            m.allowed_model(before, after, service)
            for field, value in [('privileged', True), ('environment', {'FLAG': 'on'}), ('networks', {}), ('volumes', ['other'])]:
                altered = copy.deepcopy(after)
                altered['services'][service][field] = value
                with self.assertRaises(m.legacy.Blocked):
                    m.allowed_model(before, altered, service)

    def test_runtime_env_aliases_and_restart_must_match(self):
        m = self.m
        model, container, image = self.fixture()
        m.runtime_matches(model, container, 'team-api', image)
        variants = []
        env = copy.deepcopy(container); env['Config']['Env'].append('EXTRA=unexpected'); variants.append(env)
        alias = copy.deepcopy(container); alias['NetworkSettings']['Networks']['team_api']['Aliases'].remove('private-api'); variants.append(alias)
        restart = copy.deepcopy(container); restart['HostConfig']['RestartPolicy']['Name'] = 'always'; variants.append(restart)
        command = copy.deepcopy(container); command['Config']['Cmd'] = ['other']; variants.append(command)
        for changed in variants:
            with self.assertRaises(m.legacy.Blocked):
                m.runtime_matches(model, changed, 'team-api', image)

    def test_compose_null_command_inherits_image_defaults(self):
        model, container, image = self.fixture()
        model['services']['team-api'].update(command=None, entrypoint=None, working_dir=None, user=None)
        self.m.runtime_matches(model, container, 'team-api', image)
        model['services']['team-api']['command'] = []
        with self.assertRaises(self.m.legacy.Blocked):
            self.m.runtime_matches(model, container, 'team-api', image)

    def test_health_heartbeat_is_not_drift_but_protected_restart_is(self):
        m = self.m
        _, c, _ = self.fixture()
        heartbeat = copy.deepcopy(c); heartbeat['State']['Health']['Log'] = [2, 3]
        self.assertEqual(m.runtime_fingerprint(c), m.runtime_fingerprint(heartbeat))
        restarted = copy.deepcopy(c); restarted['State']['StartedAt'] = 'later'
        self.assertNotEqual(m.protected_fingerprint(c), m.protected_fingerprint(restarted))
        stopped = copy.deepcopy(c); stopped['State']['Running'] = False; stopped['State']['Status'] = 'exited'
        self.assertNotEqual(m.protected_fingerprint(c), m.protected_fingerprint(stopped))
        changed = copy.deepcopy(c); changed['Config']['Env'].append('UNEXPECTED=1')
        self.assertNotEqual(m.runtime_fingerprint(c), m.runtime_fingerprint(changed))

    def test_exact_035_ledger_in_read_only_transaction(self):
        m = self.m
        for count in [35, 33]:
            output = ('BEGIN\n' + json.dumps(sorted(m.profile.MIGRATIONS)[:count]) + '\nCOMMIT\n').encode()
            with patch.object(m.legacy, 'docker', return_value=output) as docker:
                if count == 35:
                    m.ledger035()
                else:
                    with self.assertRaises(m.legacy.Blocked): m.ledger035()
                self.assertIn('BEGIN READ ONLY', docker.call_args.args[-1])

    def test_mount_contents_and_permissions_are_part_of_snapshot(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            private = root / 'config.js'; private.write_text('fixture configuration')
            container = {'Mounts': [{'Type': 'bind', 'Source': str(root), 'RW': False}]}
            before = m.mount_fingerprints(container)
            private.write_text('changed fixture')
            self.assertNotEqual(before, m.mount_fingerprints(container))
            container['Mounts'][0]['RW'] = True
            with self.assertRaises(m.legacy.Blocked): m.mount_fingerprints(container)

    def test_individual_compose_contexts_are_preserved(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); env = root / '.env.team'; env.touch()
            base = root / 'compose.yaml'; base.touch()
            api = root / 'api-only.json'; api.touch()
            with patch.object(m.legacy, 'ROOT', root), patch.object(m.legacy, 'BACKUPS', root):
                for files in [[base], [base, api]]:
                    c = {'Config': {'Labels': {'com.docker.compose.project': 'socialmei-team',
                         'com.docker.compose.project.working_dir': str(root),
                         'com.docker.compose.project.environment_file': str(env),
                         'com.docker.compose.project.config_files': ','.join(map(str, files))}}}
                    _, cmd, hashes = m.context(c)
                    self.assertEqual([cmd[i + 1] for i, value in enumerate(cmd) if value == '-f'], list(map(str, files)))
                    self.assertEqual(set(hashes), set(map(str, [env, *files])))

    def test_inspect_never_applies_or_claims_backup(self):
        m = self.m
        with patch.object(m, 'source_gate'), patch.object(m, 'no_external_senders'), patch.object(m, 'preflight', return_value=({}, {})), patch.object(m.legacy, 'run') as run:
            result = m.operate(Path('source'), Path('bundle'))
            run.assert_not_called()
            self.assertFalse(result['production_changed'])
            self.assertFalse(result['backup_verified'])
            self.assertFalse(result['deployment_ready'])

    def test_config_change_and_protected_restart_block_before_up(self):
        m = self.m
        _, c, _ = self.fixture()
        plan = {'files': {'fixture': 'expected'}, 'container': c, 'mount_fingerprints': {}}
        with patch.object(m.legacy, 'digest_file', return_value='changed'):
            with self.assertRaises(m.legacy.Blocked): m.inputs_unchanged({'team-api': plan}, {})
        with patch.object(m.legacy, 'digest_file', return_value='expected'), patch.object(m, 'mount_fingerprints', return_value={}), patch.object(m.legacy, 'inspect', return_value=c):
            with self.assertRaises(m.legacy.Blocked): m.inputs_unchanged({'team-api': plan}, {'postgres': 'old'})

    def test_private_archive_requires_exact_files_and_bytes(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'fixture.env'; config.write_text('only a fictional fixture')
            key = 'config/' + hashlib.sha256(str(config).encode()).hexdigest()
            archive = root / 'config.tar'
            plans = {'team-api': {'files': {str(config): m.legacy.digest_file(config)}, 'mount_fingerprints': {}}}
            with tarfile.open(archive, 'w') as output:
                output.add(config, arcname=key)
            m.verify_private_archive(archive, plans)
            config.write_text('modified fictional fixture')
            with self.assertRaises(m.legacy.Blocked): m.verify_private_archive(archive, plans)
            with tarfile.open(archive, 'w') as output:
                output.add(config, arcname='../unexpected')
            with self.assertRaises(m.legacy.Blocked): m.verify_private_archive(archive, plans)

    def test_capacity_gate_precedes_expensive_exports(self):
        m = self.m
        with tempfile.NamedTemporaryFile() as bundle:
            with patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
                with self.assertRaises(m.legacy.Blocked): m.capacity_gate(Path(bundle.name))
            with patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), \
                 patch.object(Path, 'read_text', return_value='MemAvailable: 1024 kB\n'):
                with self.assertRaises(m.legacy.Blocked): m.capacity_gate(Path(bundle.name))
            with patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), \
                 patch.object(Path, 'read_text', return_value='MemAvailable: 524288 kB\n'):
                m.capacity_gate(Path(bundle.name))

    def test_revision_label_alone_does_not_allow_retargeted_image(self):
        m = self.m
        _, container, _ = self.fixture()
        image = {'Id': 'different-id', 'Config': {'Labels': {'org.opencontainers.image.revision': m.BASE_SHA}}}
        with patch.object(m.legacy, 'docker', return_value=json.dumps([image]).encode()):
            with self.assertRaises(m.legacy.Blocked): m.image_for(container, m.BASE_SHA)

    @unittest.skipUnless(os.name == 'posix', 'Unix ownership gate runs in Linux CI/container')
    def test_backup_gate_binds_fresh_dump_restore_runtime_private_config_and_permissions(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            folder = parent / 'v01-backup'; folder.mkdir(mode=0o700)
            config = parent / 'fictional.env'; config.write_text('fixture only')
            plans = {'team-api': {'container': self.fixture()[1], 'files': {str(config): m.legacy.digest_file(config)}, 'mount_fingerprints': {}}}
            (folder / 'postgres.dump').write_bytes(b'fictional dump; PostgreSQL tested separately')
            (folder / 'images-before.tar').write_bytes(b'archive identity checked by importer independently')
            with tarfile.open(folder / 'private-config.tar', 'w') as archive:
                archive.add(config, arcname='config/' + hashlib.sha256(str(config).encode()).hexdigest())
            restore = {'backup_sha256': m.legacy.digest_file(folder / 'postgres.dump'),
                       'ledger': sorted(m.profile.MIGRATIONS), 'restore_verified': True,
                       'isolated': True, 'migrations_executed': False, 'production_runtime_changed': False,
                       'fingerprints_match': True, 'schema_and_constraints_match': True, 'table_count': 71,
                       'metadata_groups': ['columns', 'constraint_properties', 'constraints', 'environment',
                                           'functions', 'indexes', 'schemas', 'sequences', 'tables', 'triggers', 'views']}
            receipt = {'source_sha': m.CANDIDATE_SHA, 'baseline_sha': m.BASE_SHA, 'release_profile': '038',
                       'captured_unix': time.time(), 'runtime_fingerprints': {'team-api': m.runtime_fingerprint(plans['team-api']['container'])},
                       'mount_fingerprints': {'team-api': {}}}
            def save():
                (folder / 'restore035.json').write_text(json.dumps(restore))
                receipt['sha256'] = {n: m.legacy.digest_file(folder / n) for n in
                                    ['postgres.dump', 'images-before.tar', 'private-config.tar', 'restore035.json']}
                (folder / 'v01-backup-receipt.json').write_text(json.dumps(receipt))
                for p in folder.iterdir(): p.chmod(0o600)
            save()
            actual_stat = Path.stat
            def root_owned_fixture(path, *args, **kwargs):
                result = actual_stat(path, *args, **kwargs)
                if path.is_relative_to(folder):
                    fields = list(result)
                    fields[4] = 0
                    return os.stat_result(fields)
                return result
            # The runner may be unprivileged; virtualize only fixture ownership, not production gates.
            with patch.object(Path, 'stat', root_owned_fixture), \
                 patch.object(m.legacy, 'PRIVATE', parent), patch.object(m, 'sibling', return_value=SimpleNamespace(verify_archive_config_digests=MagicMock())):
                self.assertEqual(m.backup_gate(folder, plans)['source_sha'], m.CANDIDATE_SHA)
                for key, bad in [('fingerprints_match', False), ('schema_and_constraints_match', False),
                                 ('table_count', 70), ('metadata_groups', ['columns'])]:
                    previous = restore[key]; restore[key] = bad; save()
                    with self.assertRaises(m.legacy.Blocked): m.backup_gate(folder, plans)
                    restore[key] = previous; save()
                restore['migrations_executed'] = True; save()
                with self.assertRaises(m.legacy.Blocked): m.backup_gate(folder, plans)
                restore['migrations_executed'] = False; receipt['captured_unix'] -= 1000; save()
                with self.assertRaises(m.legacy.Blocked): m.backup_gate(folder, plans)
                receipt['captured_unix'] = time.time(); save()
                (folder / 'postgres.dump').chmod(0o644)
                with self.assertRaises(m.legacy.Blocked): m.backup_gate(folder, plans)

    def test_exact038_ledger_rejects_missing_extra_and035(self):
        m = self.m
        for names in (sorted(m.profile.MIGRATIONS038), sorted(m.profile.MIGRATIONS),
                      sorted(m.profile.MIGRATIONS038) + ['039_unreviewed.sql']):
            with patch.object(m.legacy, 'docker', return_value=json.dumps(names).encode()) as docker:
                if len(names) == 38:
                    self.assertEqual(m.ledger038(), names)
                else:
                    with self.assertRaises(m.legacy.Blocked): m.ledger038()
                self.assertIn('BEGIN READ ONLY', docker.call_args.args[-1])

    def test_apply_requires_explicit_authorization_before_write(self):
        m = self.m
        with patch.object(m, 'source_gate'), patch.object(m, 'preflight', return_value=({}, {})), \
             patch.object(m, 'no_external_senders'), patch.object(m, 'migrate038') as migrate:
            with self.assertRaisesRegex(m.legacy.Blocked, 'autorizacao_operacional'):
                m.operate(Path('/source'), Path('/bundle'), Path('/backup'), apply=True)
            migrate.assert_not_called()

    def test_bundle_digest_is_pinned_before_archive_import(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / 'candidate.zip'
            bundle.write_bytes(b'not the approved artifact')
            with patch.object(m.legacy, 'BACKUPS', Path(temporary)), patch.object(m, 'sibling') as importer:
                with self.assertRaisesRegex(m.legacy.Blocked, 'bundle_digest_diverge'):
                    m.read_bundle038(bundle)
                importer.assert_not_called()

    def test_sender_flags_must_stay_off(self):
        m = self.m
        plans = {'team-api': {'container': {}}}
        for key in ('SOCIALMEI_WHATSAPP_BOT_ENABLED', 'SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED'):
            with patch.object(m.legacy, 'env_map', return_value={key: 'true'}):
                with self.assertRaises(m.legacy.Blocked): m.no_external_senders(plans)
        with patch.object(m.legacy, 'env_map', return_value={}): m.no_external_senders(plans)

    def test_migration_uses_only_ephemeral_database_network_and_readonly_source(self):
        m = self.m
        env = {'POSTGRES_HOST': 'database', 'POSTGRES_PORT': '5432', 'POSTGRES_USER': 'fixture',
               'POSTGRES_DB': 'fixture', 'POSTGRES_PASSWORD': 'fictional-only'}
        api = {'NetworkSettings': {'Networks': {'private-database': {}, 'egress': {}}}}
        pg = {'Name': '/postgres', 'NetworkSettings': {'Networks': {
            'private-database': {'Aliases': ['database']}}}}
        plans = {'team-api': {'container': api, 'candidate_image_id': 'sha256:' + 'c' * 64}}
        with tempfile.TemporaryDirectory() as temporary:
            backup = Path(temporary)
            label = m.fingerprint([str(backup), m.CANDIDATE_SHA])
            created = {'Id': 'a' * 64, 'Image': plans['team-api']['candidate_image_id'],
                       'Config': {'Labels': {'socialmei.functional038.migration': label}},
                       'State': {'ExitCode': 0}}
            calls = []
            def docker(*args, **kwargs):
                calls.append(args)
                if args[:2] == ('network', 'inspect'): return b'[{"Internal":true}]'
                if args[:2] == ('image', 'inspect'): return json.dumps([{'Id': created['Image']}]).encode()
                if args[0] == 'create':
                    content = (backup / 'functional038-migration.env').read_text()
                    self.assertIn('POSTGRES_DB=fixture', content)
                    self.assertIn('lock_timeout=5s', content)
                    self.assertEqual(len(content.splitlines()), 8)
                    self.assertEqual(content.splitlines()[0], 'POSTGRES_HOST=database')
                    return ('a' * 64).encode()
                return b''
            with patch.object(m, 'source_gate'), patch.object(m, 'ledger035'), \
                 patch.object(m, 'migration_snapshot', return_value=(Path('/snapshot/migrations'), Path('/snapshot/team_migrate.py'))), \
                 patch.object(m, 'write_private_json'), \
                 patch.object(m.legacy, 'digest_file', return_value='a' * 64), \
                 patch.object(m, 'ledger038') as after, patch.object(m.legacy, 'env_map', return_value=env), \
                 patch.object(m.legacy, 'docker', side_effect=docker), \
                 patch.object(m.legacy, 'inspect', side_effect=lambda name: pg if name == m.legacy.POSTGRES else created):
                m.migrate038(Path('/source'), plans, backup)
            create = next(call for call in calls if call[0] == 'create')
            self.assertIn('--read-only', create)
            self.assertEqual(create[create.index('--network') + 1], 'private-database')
            self.assertNotIn('--privileged', create)
            self.assertNotIn('-v', create)
            self.assertEqual(sum(str(arg).endswith(',readonly') for arg in create), 2)
            self.assertIn(('rm', '-f', 'a' * 64), calls)
            self.assertFalse((backup / 'functional038-migration.env').exists())
            after.assert_called_once()

    def test_migration_rejects_public_network_before_container_creation(self):
        m = self.m
        api = {'NetworkSettings': {'Networks': {'public': {}}}}
        pg = {'NetworkSettings': {'Networks': {'public': {}}}}
        with patch.object(m, 'source_gate'), patch.object(m, 'ledger035'), \
             patch.object(m.legacy, 'inspect', return_value=pg), \
             patch.object(m.legacy, 'docker', return_value=b'[{"Internal":false}]') as docker:
            with self.assertRaisesRegex(m.legacy.Blocked, 'rede_database_nao_privada'):
                m.migrate038(Path('/source'), {'team-api': {'container': api}}, Path('/backup'))
            self.assertEqual(docker.call_count, 1)

    def test_rollback_refuses_runtime_drift_and_never_executes_sql_restore(self):
        m = self.m
        before, container, _ = self.fixture()
        plan = {'container': container, 'before': before, 'files': {}, 'mount_fingerprints': {}}
        state = {'attempted': ['team-api'], 'rolled_back_services': [], 'rolled_back_runtime': {},
                 'candidate_runtime': {'team-api': 'not-the-current-runtime'}}
        with patch.object(m, 'ledger038'), patch.object(m, 'inputs_unchanged'), \
             patch.object(m.legacy, 'inspect', return_value=container), \
             patch.object(m.legacy, 'run') as run, patch.object(m.legacy, 'docker') as docker:
            with self.assertRaisesRegex(m.legacy.Blocked, 'rollback_incompleto'):
                m.rollback_services({'team-api': plan, 'team-gateway': plan}, {}, Path('/backup'), {}, state)
            run.assert_not_called()
            docker.assert_not_called()

    def test_migration_failure_checks_actual_ledger_before_claiming035_preserved(self):
        m = self.m
        state = {'phase': 'before_migration035', 'attempted': []}
        with patch.object(m, 'fresh_backup'), patch.object(m, 'migrate038', side_effect=m.legacy.Blocked('fixture_failure')), \
             patch.object(m, 'ledger', return_value=['unexpected']), patch.object(m, 'rollback_services') as recover:
            with self.assertRaisesRegex(m.legacy.Blocked, 'migration_estado_desconhecido'):
                m.publish_services(Path('/source'), {}, {}, Path('/backup'), {}, state, run_migration=True)
            recover.assert_not_called()

    def test_atomic_failed_upgrade_retains035_without_image_up(self):
        m = self.m
        state = {'phase': 'before_migration035', 'attempted': []}
        with patch.object(m, 'fresh_backup'), patch.object(m, 'migrate038', side_effect=m.legacy.Blocked('fixture_failure')), \
             patch.object(m, 'ledger', return_value=sorted(m.profile.MIGRATIONS)), \
             patch.object(m, 'inputs_unchanged'), patch.object(m, 'write_journal'), \
             patch.object(m.legacy, 'run') as run, patch.object(m, 'rollback_services') as recover:
            with self.assertRaisesRegex(m.legacy.Blocked, 'fixture_failure'):
                m.publish_services(Path('/source'), {}, {}, Path('/backup'), {}, state, run_migration=True)
            self.assertEqual(state['phase'], 'migration_failed035_retained')
            recover.assert_not_called()
            run.assert_not_called()

    def test_overlay_reuse_is_exact_and_never_overwrites_drift(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temporary, patch.object(m, 'private_file', side_effect=lambda p: p):
            folder = Path(temporary)
            path = m.overlay_file(folder, 'team-api')
            original = path.read_bytes()
            self.assertEqual(m.overlay_file(folder, 'team-api'), path)
            self.assertEqual(path.read_bytes(), original)
            path.write_text('{"services":{}}')
            with self.assertRaisesRegex(m.legacy.Blocked, 'overlay_da_janela_diverge'):
                m.overlay_file(folder, 'team-api')
            self.assertEqual(path.read_text(), '{"services":{}}')

    def test_forward_smoke_checks_new_assets_without_changing_rollback_set(self):
        m = self.m
        old_files = {'socialmei-app.html': 'baseline-hash'}
        state = {'old_files': copy.deepcopy(old_files)}
        with patch.object(m, 'write_journal'), patch.object(m.legacy, 'digest_file', return_value='candidate-hash'), \
             patch.object(m.legacy, 'public_smoke') as smoke:
            m.publish_services(Path('/source'), {}, {}, Path('/backup'), {}, state, run_migration=False)
        expected = smoke.call_args.kwargs['expected_files']
        self.assertEqual(set(expected), set(m.legacy.STATIC_FILES) | {
            'scripts/v22-appointments.js', 'scripts/v22-inbox-customer.js',
            'scripts/v22-whatsapp-replies.js', 'scripts/product-store.js'})
        self.assertEqual(state['old_files'], old_files)

    def test_snapshot_uses_pinned_blobs_and_rejects_changed_sql(self):
        m = self.m
        root = Path(__file__).resolve().parents[1]
        def git_blob(arguments, **kwargs):
            self.assertEqual(arguments[:4], ['git', '-C', str(root), 'show'])
            revision, filename = arguments[4].split(':', 1)
            self.assertEqual(revision, m.CANDIDATE_SHA)
            return (root / filename).read_bytes()
        with tempfile.TemporaryDirectory() as temporary, patch.object(m.legacy, 'run', side_effect=git_blob):
            migrations, script = m.migration_snapshot(root, Path(temporary))
            self.assertEqual(len(list(migrations.iterdir())), 38)
            self.assertEqual(script.read_bytes(), (root / 'tools/team_migrate.py').read_bytes())
        def corrupted(arguments, **kwargs):
            original = git_blob(arguments, **kwargs)
            return original + b'-- unexpected modification' if arguments[-1].endswith('038_inbox_customer_link.sql') else original
        with tempfile.TemporaryDirectory() as temporary, patch.object(m.legacy, 'run', side_effect=corrupted):
            with self.assertRaises(RuntimeError): m.migration_snapshot(root, Path(temporary))

    def test_running_migration_blocks_recovery_without_killing_it(self):
        m = self.m
        backup = Path('/private/backup')
        label = m.fingerprint([str(backup), m.CANDIDATE_SHA])
        current = {'Id': 'a' * 64, 'Config': {'Labels': {'socialmei.functional038.migration': label}},
                   'State': {'Running': True}}
        with patch.object(m.legacy, 'docker', return_value=('a' * 64 + '\n').encode()) as docker, \
             patch.object(m.legacy, 'inspect', return_value=current):
            with self.assertRaisesRegex(m.legacy.Blocked, 'migrador_ainda_em_execucao'):
                m.migration_inactive(backup)
            self.assertEqual(docker.call_count, 1)

    def test_commit_before_journal_update_is_recoverable_only_with_baseline_cas(self):
        m = self.m
        plans = {}
        current = {}
        for service, name in m.NAMES.items():
            before, container, _ = self.fixture(service)
            plans[service] = {'wd': Path('/fixture'), 'before': before, 'container': container,
                              'files': {}, 'mount_fingerprints': {}}
            current[name] = container
        with tempfile.TemporaryDirectory() as temporary:
            backup = Path(temporary)
            receipt_file = backup / 'v01-backup-receipt.json'
            receipt_file.write_text('fictional window receipt')
            state = {'source_sha': m.CANDIDATE_SHA, 'baseline_sha': m.BASE_SHA,
                     'bundle_sha256': m.BUNDLE_SHA256,
                     'backup_receipt_sha256': m.legacy.digest_file(receipt_file),
                     'phase': 'before_migration035', 'plans': plans, 'backup_plans': plans,
                     'protected': {}, 'attempted': [], 'rolled_back_services': [],
                     'rolled_back_runtime': {}, 'candidate_runtime': {}, 'old_files': {}}
            (backup / m.JOURNAL).write_text(json.dumps(state, default=str))
            with patch.object(m, 'source_gate'), patch.object(m, 'read_bundle038'), \
                 patch.object(m, 'private_file', side_effect=lambda p: p), patch.object(m, 'backup_gate', return_value={}), \
                 patch.object(m, 'ledger038'), patch.object(m, 'migration_inactive'), \
                 patch.object(m, 'no_external_senders'), patch.object(m, 'inputs_unchanged'), \
                 patch.object(m.os, 'geteuid', return_value=0, create=True), patch.object(m, 'open', mock_open(), create=True), \
                 patch.object(m.legacy.fcntl, 'flock'), patch.object(m.legacy, 'inspect', side_effect=lambda n: current[n]), \
                 patch.object(m.legacy, 'public_smoke'), patch.object(m.legacy, 'run') as run:
                result = m.rollback(Path('/source'), Path('/bundle'), backup, m.AUTHORIZATION)
                self.assertEqual(result['action'], 'rolled_back_schema038_retained')
                run.assert_not_called()
                state['phase'] = 'before_migration035'
                (backup / m.JOURNAL).write_text(json.dumps(state, default=str))
                current[m.legacy.API] = {**current[m.legacy.API], 'Id': 'changed-outside-window'}
                with self.assertRaisesRegex(m.legacy.Blocked, 'rollback_baseline_cas_diverge'):
                    m.rollback(Path('/source'), Path('/bundle'), backup, m.AUTHORIZATION)


if __name__ == '__main__':
    unittest.main()

