"""Safety gates for the disposable compatible-image rollback rehearsal."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('rollback040', ROOT / 'tools/schema040-rollback-rehearsal.py')
rollback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rollback)


class Rollback040Tests(unittest.TestCase):
    def image(self, image=None, revision=None):
        return [{'Id': image or rollback.IMAGE, 'Config': {'Labels': {
            'org.opencontainers.image.revision': revision or rollback.SOURCE}}}]

    def test_plan_does_not_contact_docker(self):
        with patch.object(rollback.migration, 'run', side_effect=AssertionError('unexpected Docker')):
            plan = rollback.rehearse(rollback.options([]))
        self.assertEqual(plan['mode'], 'plan')
        self.assertEqual(plan['profile'], '040')
        self.assertEqual(len(plan['source_migrations']), 40)
        self.assertFalse(plan['schema_downgraded'])
        self.assertFalse(plan['production_database_changed'])

    def test_no_external_target_or_deployment_flags(self):
        for flag in ('--database-url', '--apply', '--deploy', '--api-image', '--source-sha'):
            with self.subTest(flag=flag), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                rollback.options([flag, 'unapproved'])

    def test_exact_image_and_revision_required(self):
        rollback.approved_image(self.image())
        for value in ([], self.image(image='sha256:' + 'a' * 64), self.image(revision='a' * 40)):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'approved_image_revision_mismatch'):
                rollback.approved_image(value)

    def test_remote_daemon_stops_before_contact(self):
        with patch.dict(rollback.os.environ, {'DOCKER_HOST': 'ssh://live'}), \
                patch.object(rollback.migration, 'run', side_effect=AssertionError('remote contact')):
            with self.assertRaisesRegex(RuntimeError, 'local_docker_required'):
                rollback.rehearse(rollback.options(['--run']))

    def test_wrong_active_context_stops_before_inspecting_images(self):
        reply = json.dumps([{'Endpoints': {'docker': {'Host': 'tcp://live:2375'}}}]).encode()
        with patch.dict(rollback.os.environ, {'DOCKER_HOST': ''}), \
                patch.object(rollback.migration, 'run', return_value=reply) as command:
            with self.assertRaisesRegex(RuntimeError, 'local_docker_required'):
                rollback.rehearse(rollback.options(['--run']))
        self.assertEqual(command.call_count, 1)

    def test_image_mismatch_creates_no_resources(self):
        replies = [json.dumps([{'Endpoints': {'docker': {'Host': 'unix:///var/run/docker.sock'}}}]).encode(),
                   json.dumps(self.image(revision='a' * 40)).encode()]
        with patch.dict(rollback.os.environ, {'DOCKER_HOST': ''}), \
                patch.object(rollback.migration, 'run', side_effect=replies) as command:
            with self.assertRaisesRegex(RuntimeError, 'approved_image_revision_mismatch'):
                rollback.rehearse(rollback.options(['--run']))
        self.assertEqual(command.call_count, 2)

    def test_cleanup_requires_matching_label_and_network(self):
        def container(token='owned', network='none'):
            return [{'Config': {'Labels': {rollback.LABEL: token}}, 'HostConfig': {'NetworkMode': network}}]
        rollback.owned_container(container(), 'owned', 'none')
        for value in ([], container(token='foreign'), container(network='bridge')):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'cleanup_target_not_owned'):
                rollback.owned_container(value, 'owned', 'none')

    def test_failed_start_removes_only_its_owned_container(self):
        container_id = 'c' * 64
        context = [{'Endpoints': {'docker': {'Host': 'unix:///var/run/docker.sock'}}}]
        def command(binary, *args, **kwargs):
            if args == ('context', 'inspect'):
                return json.dumps(context).encode()
            if args == ('image', 'inspect', rollback.IMAGE):
                return json.dumps(self.image()).encode()
            if args == ('image', 'inspect', 'postgres:16-alpine'):
                return json.dumps([{'Id': 'sha256:' + 'd' * 64}]).encode()
            if args[0] == 'create':
                self.assertIn('--pull=never', args)
                self.assertIn('none', args)
                return container_id.encode()
            if args == ('start', container_id):
                raise RuntimeError('synthetic_start_failure')
            if args == ('inspect', container_id):
                return json.dumps([{'Config': {'Labels': {rollback.LABEL: 'owned'}},
                                    'HostConfig': {'NetworkMode': 'none'}}]).encode()
            if args == ('rm', '-f', '-v', container_id) or args[0] == 'ps':
                return b''
            raise AssertionError(args)
        with patch.dict(rollback.os.environ, {'DOCKER_HOST': ''}), \
                patch.object(rollback.secrets, 'token_hex', return_value='owned'), \
                patch.object(rollback.migration, 'run', side_effect=command) as calls:
            with self.assertRaisesRegex(RuntimeError, 'synthetic_start_failure'):
                rollback.rehearse(rollback.options(['--run', '--receipt', '.preview/rollback040-unit-only.json']))
        removals = [call.args[1:] for call in calls.call_args_list if call.args[1] == 'rm']
        self.assertEqual(removals, [('rm', '-f', '-v', container_id)])


if __name__ == '__main__':
    unittest.main()
