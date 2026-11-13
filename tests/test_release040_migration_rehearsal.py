"""Offline guard coverage for the isolated PostgreSQL 040 rehearsal."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('rehearsal040_tests', ROOT / 'tools/release040-migration-rehearsal.py')
rehearsal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rehearsal)


class Rehearsal040Tests(unittest.TestCase):
    def test_default_is_read_only_plan_with_explicit_039_baseline(self):
        with patch.object(rehearsal, 'run', side_effect=AssertionError('no command in plan')):
            plan = rehearsal.rehearse(rehearsal.options([]))
        self.assertEqual(plan['mode'], 'plan')
        self.assertEqual(plan['profile'], '040')
        self.assertEqual(plan['baseline'], '039')
        self.assertEqual(len(plan['source_migrations']), 40)
        self.assertEqual(len(plan['baseline_migrations']), 39)
        self.assertFalse(plan['production_data_used'])
        self.assertFalse(plan['production_runtime_changed'])
        self.assertFalse(plan['provider_messages_sent'])
        with self.assertRaises(RuntimeError):
            rehearsal.profile.rehearsal040(plan, 'a'*40)

    def test_only_exact_image_and_source_can_run(self):
        for argv in (['--run'], ['--run', '--source-sha', 'a'*40, '--api-image', 'latest'],
                     ['--run', '--source-sha', 'a'*39, '--api-image', 'sha256:'+'b'*64]):
            with self.subTest(argv=argv), self.assertRaises(RuntimeError):
                rehearsal.options(argv)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            rehearsal.options(['--database-url', 'postgresql://live'])
        self.assertTrue(rehearsal.options(['--run', '--source-sha', 'a'*40,
                                         '--api-image', 'sha256:'+'b'*64]).run)

    def test_remote_endpoints_and_artifact_escape_rejected(self):
        for endpoint in ('unix:///var/run/docker.sock', 'npipe:////./pipe/docker_engine',
                         'npipe:////./pipe/dockerDesktopLinuxEngine'):
            self.assertTrue(rehearsal.local_docker(endpoint))
        for endpoint in ('ssh://live', 'tcp://127.0.0.1:2375', 'tcp://live:2375', None):
            self.assertFalse(rehearsal.local_docker(endpoint))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            self.assertEqual(rehearsal.workspace_path(root, 'receipt.json'), root / 'receipt.json')
            for target in ('.', '../receipt.json', str(root.parent / 'receipt.json')):
                with self.subTest(target=target), self.assertRaises(RuntimeError):
                    rehearsal.workspace_path(root, target)

    def test_remote_daemon_never_reaches_docker(self):
        args = rehearsal.options(['--run', '--source-sha', 'a'*40, '--api-image', 'sha256:'+'b'*64])
        with patch.dict(rehearsal.os.environ, {'DOCKER_HOST': 'ssh://live'}), \
                patch.object(rehearsal, 'run', side_effect=AssertionError('remote daemon contacted')):
            with self.assertRaisesRegex(RuntimeError, 'local_docker_required'):
                rehearsal.rehearse(args)

    def test_dirty_source_never_creates_disposable_resources(self):
        args = rehearsal.options(['--run', '--source-sha', 'a'*40, '--api-image', 'sha256:'+'b'*64])
        replies = [json.dumps([{'Endpoints': {'docker': {'Host': 'unix:///var/run/docker.sock'}}}]).encode(),
                   json.dumps([{'Id': args.api_image, 'Config': {'Labels': {'org.opencontainers.image.revision': args.source_sha}}}]).encode(),
                   (args.source_sha+'\n').encode(), b' M frontend/config.js\n']
        with patch.dict(rehearsal.os.environ, {'DOCKER_HOST': ''}), patch.object(rehearsal, 'run', side_effect=replies) as command:
            with self.assertRaisesRegex(RuntimeError, 'clean_source_required'):
                rehearsal.rehearse(args)
            self.assertEqual(command.call_count, 4)
            self.assertTrue(all('run' not in call.args[1:] for call in command.call_args_list))

    def test_restore_normalization_keeps_meaningful_constraint_changes_visible(self):
        before = "CHECK (status = ANY ((ARRAY['pending'::character varying, 'sent'::character varying])::text[]))"
        after = "CHECK (status = ANY (ARRAY[('pending'::character varying)::text, ('sent'::character varying)::text]))"
        self.assertEqual(rehearsal.canonical_expression(before), after)
        changed = before.replace("'sent'", "'revoked'")
        self.assertNotEqual(rehearsal.canonical_expression(changed), after)


if __name__ == '__main__':
    unittest.main()
