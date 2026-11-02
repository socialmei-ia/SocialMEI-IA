"""266/035 release gates; fake runtime, no SSH, provider calls or live Docker."""
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


class V01ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('v01_release_test', Path(__file__).resolve().parents[1] / 'tools/team-v01-release.py')
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
        with patch.object(m, 'preflight', return_value=({}, {})), patch.object(m.legacy, 'run') as run:
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
                       'isolated': True, 'migrations_executed': False, 'production_runtime_changed': False}
            receipt = {'source_sha': m.CANDIDATE_SHA, 'baseline_sha': m.BASE_SHA, 'release_profile': '035',
                       'captured_unix': time.time(), 'runtime_fingerprints': {'team-api': m.runtime_fingerprint(plans['team-api']['container'])},
                       'mount_fingerprints': {'team-api': {}}}
            def save():
                (folder / 'restore035.json').write_text(json.dumps(restore))
                receipt['sha256'] = {n: m.legacy.digest_file(folder / n) for n in
                                    ['postgres.dump', 'images-before.tar', 'private-config.tar', 'restore035.json']}
                (folder / 'v01-backup-receipt.json').write_text(json.dumps(receipt))
                for p in folder.iterdir(): p.chmod(0o600)
            save()
            with patch.object(m.legacy, 'PRIVATE', parent), patch.object(m, 'sibling', return_value=SimpleNamespace(verify_archive_config_digests=MagicMock())):
                self.assertEqual(m.backup_gate(folder, plans)['source_sha'], m.CANDIDATE_SHA)
                restore['migrations_executed'] = True; save()
                with self.assertRaises(m.legacy.Blocked): m.backup_gate(folder, plans)
                restore['migrations_executed'] = False; receipt['captured_unix'] -= 1000; save()
                with self.assertRaises(m.legacy.Blocked): m.backup_gate(folder, plans)
                receipt['captured_unix'] = time.time(); save()
                (folder / 'postgres.dump').chmod(0o644)
                with self.assertRaises(m.legacy.Blocked): m.backup_gate(folder, plans)

    def failure_scenario(self, rollback_failure=False, protected_drift=False):
        m = self.m
        plans, current = {}, {}
        for service, name in m.NAMES.items():
            before, c, _ = self.fixture(service)
            plans[service] = {'wd': Path('.'), 'command': ['docker', service], 'files': {},
                              'before': before, 'after': copy.deepcopy(before), 'container': c,
                              'mount_fingerprints': {}, 'candidate_image_id': 'new-image-' + service}
            current[name] = copy.deepcopy(c)
        calls = []
        drifted = False
        def execute(command, **kwargs):
            nonlocal drifted
            if 'up' in command:
                service = command[-1]
                candidate = any(str(v).endswith('.candidate.compose.json') for v in command)
                calls.append((service, candidate))
                self.assertIn('--no-deps', command); self.assertIn('--no-build', command)
                self.assertEqual(command[command.index('--pull') + 1], 'never')
                if service == 'team-gateway' and (candidate or rollback_failure):
                    raise m.legacy.Blocked('synthetic_failure')
                current[m.NAMES[service]] = copy.deepcopy(plans[service]['container'])
                if candidate: current[m.NAMES[service]]['Image'] = plans[service]['candidate_image_id']
                if candidate and protected_drift: drifted = True
            return b''
        def check_inputs(*args, check_protected=True):
            if drifted and check_protected:
                raise m.legacy.Blocked('servico_protegido_alterado_ou_reiniciado')
        with tempfile.TemporaryDirectory() as temp, patch.object(m, 'preflight', return_value=(plans, {})), \
             patch.object(m, 'backup_gate', return_value={'sha256': {}}), patch.object(m, 'inputs_unchanged', side_effect=check_inputs), \
             patch.object(m, 'fresh_backup'), \
             patch.object(m.os, 'geteuid', return_value=0, create=True), patch.object(m, 'open', mock_open(), create=True), \
             patch.object(m.legacy.fcntl, 'flock'), patch.object(m.legacy, 'run', side_effect=execute), \
             patch.object(m.legacy, 'inspect', side_effect=lambda name: current[name]), \
             patch.object(m.legacy, 'render', side_effect=lambda cmd, wd: plans[cmd[1]]['after']), \
             patch.object(m, 'allowed_model'), patch.object(m, 'runtime_matches'), patch.object(m, 'image_for', return_value={}), \
             patch.object(m.legacy, 'docker', side_effect=lambda *args, **kwargs: json.dumps([{'Id': 'new-image-' + ('team-api' if 'team-api:' in args[-1] else 'team-gateway')}]).encode()), \
             patch.object(m.legacy, 'wait_service', side_effect=lambda service: current[m.NAMES[service]]), \
             patch.object(m, 'ledger035'), patch.object(m.legacy, 'https', return_value=b'old fixture'), \
             patch.object(m.legacy, 'public_smoke'):
            with self.assertRaises(m.legacy.Blocked) as error:
                m.operate(Path(temp), Path('bundle'), Path(temp), apply=True)
            expected = 'servico_protegido_alterado_ou_reiniciado' if protected_drift else ('rollback_incompleto' if rollback_failure else 'synthetic_failure')
            self.assertEqual(str(error.exception), expected)
        expected_calls = [('team-api', True), ('team-api', False)] if protected_drift else [('team-api', True), ('team-gateway', True), ('team-gateway', False), ('team-api', False)]
        self.assertEqual(calls, expected_calls)

    def test_gateway_failure_rolls_back_both_attempted_services(self):
        self.failure_scenario()

    def test_rollback_failure_still_attempts_other_service_and_never_claims_success(self):
        self.failure_scenario(rollback_failure=True)

    def test_protected_service_drift_does_not_prevent_api_rollback(self):
        self.failure_scenario(protected_drift=True)

    def test_backup_expiring_during_preflight_is_rejected_before_first_up(self):
        with tempfile.NamedTemporaryFile() as dump:
            with patch.object(Path, 'stat', return_value=SimpleNamespace(st_mtime=time.time())):
                with self.assertRaises(self.m.legacy.Blocked):
                    self.m.fresh_backup({'captured_unix': time.time() - 901}, Path(dump.name))


if __name__ == '__main__':
    unittest.main()
