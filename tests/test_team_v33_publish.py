"""Offline image-only Team033 publisher safety and rollback contracts."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SPEC = importlib.util.spec_from_file_location('team_v33_publish', Path(__file__).resolve().parents[1] / 'tools/team-v33-publish.py')
publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish)


def runtime():
    return {'Id': 'a' * 64, 'Config': {'Env': ['SOCIALMEI_AUTH_ENABLED=true', 'SECRET=one$two${OTHER}', 'PATH=/usr/bin'], 'Cmd': ['uvicorn', 'app:app']},
            'HostConfig': {'PortBindings': {}}, 'Mounts': [], 'NetworkSettings': {'Networks': {'socialmei_team_egress': {'Aliases': ['api', 'a' * 12]}}}}


class PublisherTests(unittest.TestCase):
    def test_only_known_services_can_be_recreated_without_dependencies_or_pull(self):
        for service in publish.SERVICES:
            self.assertEqual(publish.up(['docker', 'compose'], service)[-8:],
                             ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', service][-8:])
        with self.assertRaises(RuntimeError):
            publish.up([], 'team-postgres')

    def test_target_environment_preserves_secrets_and_explicitly_disables_providers(self):
        live = runtime()
        env = publish.target_environment(live)
        self.assertEqual(env['SECRET'], 'one$two${OTHER}')
        self.assertEqual(env['SOCIALMEI_RELEASE_SHA'], publish.SHA)
        self.assertEqual(env['SOCIALMEI_WAHA_INGRESS_MODE'], 'disabled')
        self.assertTrue(all(env[k] == 'false' for k in publish.audit.SENSITIVE_FLAGS))
        self.assertEqual(live['Config']['Env'][1], 'SECRET=one$two${OTHER}')

    def test_active_provider_or_weak_auth_refused(self):
        for change in ('SOCIALMEI_AUTH_ENABLED=false', 'SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED=true', 'SOCIALMEI_WAHA_INGRESS_MODE=waha'):
            live = runtime()
            live['Config']['Env'] = [v for v in live['Config']['Env'] if not v.startswith(change.split('=')[0] + '=')] + [change]
            with self.assertRaises(RuntimeError):
                publish.target_environment(live)

    def test_duplicate_environment_refused(self):
        live = runtime()
        live['Config']['Env'].append('SECRET=duplicate')
        with self.assertRaises(RuntimeError):
            publish.env_map(live)

    def test_literal_compose_environment_escapes_dollars_without_altering_source(self):
        env = {'SECRET': 'one$two${OTHER}'}
        self.assertEqual(publish.literal_environment(env), {'SECRET': 'one$$two$${OTHER}'})
        self.assertEqual(env['SECRET'], 'one$two${OTHER}')

    def test_only_target_image_environment_changes_in_compose(self):
        before = {'services': {'team-api': {'image': 'old', 'environment': {'A': 'B'}, 'networks': {'egress': {}}}, 'team-gateway': {'image': 'gw'}}, 'networks': {'egress': {'name': 'socialmei_team_egress'}}}
        after = publish.candidate_model(before, 'team-api', 'new', {'A': 'C'})
        self.assertEqual(after['services']['team-gateway'], before['services']['team-gateway'])
        self.assertEqual(after['networks'], before['networks'])
        self.assertEqual(before['services']['team-api']['image'], 'old')

    def test_invariant_detects_mount_network_alias_and_host_security_drift(self):
        old = runtime()
        for mutant in (dict(HostConfig={'Privileged': True}), dict(Mounts=[{'Destination': '/private', 'RW': True}]), dict(NetworkSettings={'Networks': {'socialmei_team_egress': {'Aliases': ['other']}}})):
            new = copy.deepcopy(old)
            new.update(mutant)
            self.assertNotEqual(publish.invariant(old), publish.invariant(new))
        new = copy.deepcopy(old)
        new['Id'] = 'b' * 64
        new['NetworkSettings']['Networks']['socialmei_team_egress']['Aliases'] = ['api', 'b' * 12]
        self.assertEqual(publish.invariant(old), publish.invariant(new))

    def test_prepare_never_has_build_pull_up_or_sql_mutation(self):
        import inspect
        source = inspect.getsource(publish.Publisher.prepare)
        self.assertNotIn("self.run(up(", source)
        self.assertNotIn("'build'", source)
        self.assertNotIn("'pull'", source)
        self.assertNotIn('INSERT ', source)
        self.assertIn('verify_image_archive', source)
        self.assertIn('read_bundle', source)
        self.assertIn('runtime-config.tar.gz', source)

    def test_run_is_fixed_to_original_checkout_and_sanitizes_errors(self):
        task = object.__new__(publish.Publisher)
        with patch.object(publish.subprocess, 'run', return_value=MagicMock(returncode=1, stdout='TOKEN=secret', stderr='privateDSN')) as run:
            with self.assertRaisesRegex(RuntimeError, '^comando_falhou$'):
                task.run(['python3', 'tools/team-maintenance.py', 'backup'])
            self.assertEqual(run.call_args.kwargs['cwd'], publish.ROOT)

    def test_rollback_restores_only_touched_service_and_never_restores_database(self):
        task = object.__new__(publish.Publisher)
        task.guard = MagicMock()
        task.run = MagicMock()
        task.verify = MagicMock()
        saved = {'services': {s: {'rollback_command': ['docker', 'compose', '-f', s]} for s in publish.SERVICES}}
        task.rollback(saved, ['team-api'])
        task.guard.assert_called_once_with(saved, rollback=True, missing=('team-api',))
        task.run.assert_called_once_with(publish.up(saved['services']['team-api']['rollback_command'], 'team-api'), timeout=180)
        task.verify.assert_called_once_with(saved, False)

    def test_rollback_drift_stops_before_any_recreation(self):
        task = object.__new__(publish.Publisher)
        task.guard = MagicMock(side_effect=RuntimeError('config_changed'))
        task.run = MagicMock()
        with self.assertRaises(RuntimeError):
            task.rollback({}, ['team-api'])
        task.run.assert_not_called()

    def test_prepared_artifacts_reject_symlinks_or_public_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            task = object.__new__(publish.Publisher)
            task.folder = Path(directory)
            data = task.folder / 'receipt.json'
            data.write_text('{}')
            data.chmod(0o644)
            with self.assertRaises(RuntimeError):
                task.read('receipt.json')
            data.chmod(0o600)
            self.assertEqual(task.read('receipt.json'), {})
            (task.folder / 'link.json').symlink_to(data)
            with self.assertRaises(RuntimeError):
                task.read('link.json')

    def test_fresh_backup_and_revalidation_precede_mutation(self):
        import inspect
        source = inspect.getsource(publish.Publisher.apply)
        self.assertLess(source.index("'backup'"), source.index('self.run(up('))
        self.assertIn("proof['sha256']", source)
        self.assertEqual(source.count('self.guard(saved)'), 2)
        self.assertIn('cutover-started.private.json', source)
        self.assertIn('reversed(touched)', source)


class HTTPVerificationTests(unittest.TestCase):
    def test_candidate_rejects_stale_script_or_basic_auth(self):
        import io
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'frontend/scripts').mkdir(parents=True)
            (source / 'frontend/socialmei-app.html').write_bytes(b'candidate-html')
            names = ('v22-bootstrap.js', 'v22-backend.js', 'v22-instagram.js', 'v22-instagram-publisher.js')
            for name in names:
                (source / 'frontend/scripts' / name).write_bytes(name.encode())
            task = object.__new__(publish.Publisher)
            called = []
            class Response(io.BytesIO):
                status = 200
                headers = {}
            def response(url, timeout):
                path = url.removeprefix(publish.ORIGIN)
                called.append(path)
                if path == '/api/v1/clientes':
                    raise publish.HTTPError(url, 401, 'unauthenticated', {}, None)
                if path == '/health/db':
                    raise publish.HTTPError(url, 404, 'not found', {}, None)
                return Response((source / ('frontend/socialmei-app.html' if path == '/' else 'frontend' + path)).read_bytes() if path == '/' or path.startswith('/scripts/') else b'{}')
            with patch.object(publish, 'SOURCE', source), patch.object(publish, 'urlopen', side_effect=response), patch.object(publish.time, 'sleep'):
                task.verify_http({}, True)
                self.assertTrue(all('/scripts/' + name in called for name in names))
                # Simulate a CDN/proxy serving an older script despite the new HTML.
                def stale(url, timeout):
                    result = response(url, timeout)
                    if url.endswith('/scripts/v22-instagram.js'):
                        return Response(b'old-script')
                    return result
                with patch.object(publish, 'urlopen', side_effect=stale):
                    with self.assertRaisesRegex(RuntimeError, 'frontend_https_divergente'):
                        task.verify_http({}, True)
                Response.headers = {'WWW-Authenticate': 'Basic realm=private'}
                with self.assertRaisesRegex(RuntimeError, 'http_basic_inesperado'):
                    task.verify_http({}, True)


class RollbackGuardTests(unittest.TestCase):
    def test_missing_touched_container_can_restore_but_missing_untouched_cannot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = object.__new__(publish.Publisher)
            task.folder = root
            task.privacy_snapshot = MagicMock(return_value={})
            task.others = MagicMock(return_value=[])
            bundle = root / 'images.zip'
            bundle.write_bytes(b'synthetic')
            saved = {'sha': publish.SHA, 'checkout': {}, 'privacy': {}, 'bundle': str(bundle), 'bundle_sha256': publish.digest(bundle),
                     'bind_directories': [], 'files': {}, 'artifacts': {}, 'others': [], 'archive_images': {}, 'services': {}}
            models = {}
            images = {}
            for service in publish.SERVICES:
                row = runtime()
                row['Image'] = 'old-' + service
                row['Config']['Env'] = ['SECRET=synthetic']
                tag, old = 'new-' + service, 'rollback-' + service
                before = {'services': {service: {'image': row['Image'], 'environment': {'SECRET': 'synthetic'}}}}
                cmd = ['docker', '--host=unix:///var/run/docker.sock', 'compose', '-f', service]
                candidate = cmd + ['-f', str(root / (service + '.override.private.json'))]
                rollback = cmd + ['-f', str(root / (service + '.rollback.private.json'))]
                env = {'SECRET': 'synthetic'}
                saved['services'][service] = {'container_id': row['Id'], 'old_image': row['Image'], 'new_image': tag, 'tag': tag, 'rollback_tag': old,
                                              'old_environment': env, 'environment': env, 'invariant': publish.invariant(row),
                                              'before_command': cmd, 'candidate_command': candidate, 'rollback_command': rollback}
                models[tuple(cmd)] = before
                models[tuple(candidate)] = publish.candidate_model(before, service, tag, env)
                models[tuple(rollback)] = publish.candidate_model(before, service, old, env)
                images[publish.NAMES[service]] = row
                images[tag] = {'Id': tag}
                images[old] = {'Id': row['Image']}
            task.inspect = MagicMock(side_effect=lambda name: images[name])
            task.docker = MagicMock(return_value=publish.NAMES['team-gateway'])
            task.model = MagicMock(side_effect=lambda cmd: models[tuple(cmd)])
            task.read = MagicMock(side_effect=lambda name: models[tuple(saved['services'][name.split('.before')[0]]['before_command'])])
            with patch.object(publish, 'checkout_snapshot', return_value={}), patch.object(publish.audit, 'prepared_source'), patch.object(publish.audit, 'ledger_current'), patch.object(publish.image_helper, 'read_bundle'), patch.object(publish.image_helper, 'local_image_status', return_value={'team-api': True, 'team-gateway': True}), patch.object(publish.archive_helper, 'verify_image_archive'):
                task.guard(saved, rollback=True, missing=('team-api',))
                with self.assertRaisesRegex(RuntimeError, 'servico_nao_tocado_ausente'):
                    task.guard(saved, rollback=True)
                self.assertNotIn(publish.NAMES['team-api'], [call.args[0] for call in task.inspect.call_args_list])
                task.docker.return_value = ''
                task.guard(saved, rollback=True, missing=publish.SERVICES)
                task.privacy_snapshot.assert_called_with(public_only=True)


class ApplyTests(unittest.TestCase):
    def setup_task(self, root):
        task = object.__new__(publish.Publisher)
        task.folder = root / 'publication'
        task.folder.mkdir()
        backup = root / 'team-auto-20261029-005509-abc123'
        backup.mkdir()
        (backup / 'equipe.dump').write_bytes(b'synthetic-only')
        (backup / 'concluido.json').write_text(json.dumps({'sha256': {'equipe.dump': publish.digest(backup / 'equipe.dump')}}))
        saved = {'services': {s: {'candidate_command': ['compose', s], 'rollback_command': ['rollback', s]} for s in publish.SERVICES}}
        task.read = MagicMock(return_value=saved)
        task.write = MagicMock()
        task.guard = MagicMock()
        task.verify = MagicMock()
        task.run = MagicMock(return_value='/home/ubuntu/socialmei-backups/team-auto-20261029-005509-abc123')
        task.rollback = MagicMock()
        return task

    def test_success_checks_both_services_and_records_manual_login(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(publish, 'BACKUPS', Path(directory)):
            task = self.setup_task(Path(directory))
            result = task.apply()
            self.assertEqual(result['status'], 'published')
            self.assertEqual(result['browser_login'], 'not_verified')
            self.assertFalse(result['providers_activated'])
            self.assertEqual(task.guard.call_count, 2)
            self.assertEqual(task.verify.call_count, 2)
            task.rollback.assert_not_called()

    def test_first_service_timeout_rolls_back_only_api(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(publish, 'BACKUPS', Path(directory)):
            task = self.setup_task(Path(directory))
            task.run.side_effect = ['/home/ubuntu/socialmei-backups/team-auto-20261029-005509-abc123', RuntimeError('timeout')]
            with self.assertRaisesRegex(RuntimeError, 'corte_falhou_rollback_verificado'):
                task.apply()
            touched = list(task.rollback.call_args.args[1])
            self.assertEqual(touched, ['team-api'])

    def test_second_service_failure_rolls_back_both_in_reverse_order(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(publish, 'BACKUPS', Path(directory)):
            task = self.setup_task(Path(directory))
            task.run.side_effect = ['/home/ubuntu/socialmei-backups/team-auto-20261029-005509-abc123', '', RuntimeError('timeout')]
            with self.assertRaisesRegex(RuntimeError, 'corte_falhou_rollback_verificado'):
                task.apply()
            self.assertEqual(list(task.rollback.call_args.args[1]), ['team-gateway', 'team-api'])

    def test_backup_corruption_stops_before_any_service_command(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(publish, 'BACKUPS', Path(directory)):
            root = Path(directory)
            task = self.setup_task(root)
            (root / 'team-auto-20261029-005509-abc123/equipe.dump').write_bytes(b'corrupted')
            with self.assertRaisesRegex(RuntimeError, 'backup_fresco_corrompido'):
                task.apply()
            self.assertEqual(task.run.call_count, 1)
            task.rollback.assert_not_called()

    def test_failed_rollback_preserves_manual_recovery_evidence(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(publish, 'BACKUPS', Path(directory)):
            task = self.setup_task(Path(directory))
            task.run.side_effect = ['/home/ubuntu/socialmei-backups/team-auto-20261029-005509-abc123', RuntimeError('timeout')]
            task.rollback.side_effect = RuntimeError('rollback_failed')
            with self.assertRaisesRegex(RuntimeError, 'rollback_exige_intervencao'):
                task.apply()
            self.assertEqual(task.write.call_args.args[0], 'rollback-failed.private.json')


if __name__ == '__main__':
    unittest.main()
