"""Offline guard tests. Combined runtime evidence comes only from --run in CI."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('channel_e2e_lab', ROOT / 'tools/channel-e2e-lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class PlanTests(unittest.TestCase):
    def test_fixture_import_tail_redacts_before_filtering_and_is_bounded(self):
        secret = 'private-fixture-value-123456789'
        result = subprocess.CompletedProcess([], 1, stdout='\x1b[31mImport workflow failed ' + secret + '\x1b[0m\n' + 'error ' * 500,
                                              stderr='credentials ' + secret)
        with patch.object(lab, '_REDACTIONS', (secret,)):
            diagnostic = lab.classify_command_error(result, include_fixture_tail=True)
        raw = json.dumps(diagnostic)
        self.assertNotIn(secret, raw)
        self.assertNotIn('\\u001b', raw)
        self.assertLessEqual(len(diagnostic['fixture_import_tail']), 1000)
        self.assertNotIn('fixture_import_tail', lab.classify_command_error(result))

    def test_cli_diagnostics_classify_without_printing_private_output(self):
        result = subprocess.CompletedProcess([], 1, stdout='generated-secret-token',
                    stderr="TypeError: Cannot read properties of undefined (reading 'tags')\nSQLITE_CONSTRAINT: NOT NULL constraint failed: workflow_entity.versionId")
        diagnostic = lab.classify_command_error(result)
        self.assertEqual(diagnostic['missing_property'], 'tags')
        self.assertEqual(diagnostic['constraint_column'], 'workflow_entity.versionId')
        self.assertIn('type_error', diagnostic['categories'])
        self.assertNotIn('generated-secret-token', json.dumps(diagnostic))

    def test_default_plan_never_invokes_docker(self):
        with patch.object(lab, 'docker', side_effect=AssertionError('Docker called')):
            report = lab.plan()
        self.assertFalse(report['docker_executed'])
        self.assertEqual(report['candidate_sha'], '345a074310673640084c7634e3da75dd72491813')
        self.assertEqual(report['artifact_id'], 13414736091)
        self.assertIn('no_live_homologation', report['limitations'])

    def test_cli_default_is_offline_and_sanitized(self):
        result = subprocess.run(['python3', str(ROOT / 'tools/channel-e2e-lab.py')],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['mode'], 'plan')
        self.assertNotIn('DATABASE_URL', result.stdout)

    def test_unpinned_bundle_rejected_before_importer_or_docker(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / 'wrong.zip'
            bundle.write_bytes(b'not the reviewed artifact')
            with patch.object(lab, 'docker', side_effect=AssertionError('Docker called')):
                with self.assertRaisesRegex(RuntimeError, 'candidate_external_digest_mismatch'):
                    lab.verify_bundle(bundle)

    def test_symlink_bundle_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'target'
            target.write_bytes(b'fixture')
            linked = Path(temp) / 'bundle.zip'
            linked.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, 'candidate_bundle_required'):
                lab.verify_bundle(linked)


class SourceTests(unittest.TestCase):
    def test_wrong_commit_and_dirty_checkout_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            for outputs, code in ((['a' * 40], 'candidate_source_sha_mismatch'),
                                  ([lab.SOURCE_SHA, ' M python-service/app.py'], 'candidate_source_dirty')):
                with self.subTest(code=code), patch.object(lab, 'command', side_effect=outputs):
                    with self.assertRaisesRegex(RuntimeError, code):
                        lab.validate_source(Path(temp))

    def test_clean_checkout_requires_complete_migration_sequence(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            migrations = source / 'database/migrations'
            migrations.mkdir(parents=True)
            for version in range(1, 38):
                (migrations / f'{version:03}_fixture.sql').touch()
            with patch.object(lab, 'command', side_effect=[lab.SOURCE_SHA, '']):
                with self.assertRaisesRegex(RuntimeError, 'candidate_migrations_incomplete'):
                    lab.validate_source(source)


class CleanupTests(unittest.TestCase):
    def test_partial_startup_removes_only_matching_labels_and_checks_again(self):
        fixture = lab.Lab()
        with patch.object(lab, 'docker', side_effect=['container-id\n', '', '', 'network-id\n', '', '']) as docker:
            fixture.cleanup()
        calls = [call.args for call in docker.call_args_list]
        self.assertIn(('rm', '-fv', 'container-id'), calls)
        self.assertIn(('network', 'rm', 'network-id'), calls)
        for args in calls:
            if 'ls' in args or 'ps' in args:
                self.assertIn('label=' + fixture.filter, args)
        self.assertNotIn('prune', str(calls))

    def test_cleanup_failure_is_fatal_and_still_checks_network(self):
        fixture = lab.Lab()
        with patch.object(lab, 'docker', side_effect=[RuntimeError('failed'), '', '']) as docker:
            with self.assertRaisesRegex(RuntimeError, 'lab_cleanup_failed'):
                fixture.cleanup()
        self.assertEqual(docker.call_count, 3)

    def test_remaining_resources_are_fatal(self):
        fixture = lab.Lab()
        with patch.object(lab, 'docker', side_effect=['id', '', 'id', '', '']):
            with self.assertRaisesRegex(RuntimeError, 'lab_cleanup_failed'):
                fixture.cleanup()

    def test_container_has_no_pull_local_internal_network_and_unique_label(self):
        fixture = lab.Lab()
        with patch.object(lab, 'docker', return_value='id') as docker:
            fixture.container('api', 'candidate-image')
        args = docker.call_args.args
        self.assertIn('--pull=never', args)
        self.assertIn(fixture.filter, args)
        self.assertIn(fixture.network, args)
        self.assertNotIn('-p', args)


class WorkflowTests(unittest.TestCase):
    def test_ephemeral_workflows_preserve_original_files_and_signed_binary_graph(self):
        source = ROOT
        before = (source / 'n8n-workflows/experimental/whatsapp-bot-planner.json').read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            lab.workflows(source, folder, {'bot': 'fake-bot', 'waha': 'fake-waha', 'bridge': 'fake-bridge'})
            whatsapp = json.loads((folder / 'whatsapp.json').read_text())
            instagram = json.loads((folder / 'instagram.json').read_text())
            self.assertFalse(whatsapp['active'])
            self.assertFalse(instagram['active'])
            # n8n 2.40.5 validates these mandatory tuples before importing.
            for workflow in (whatsapp, instagram):
                for node in workflow['nodes']:
                    self.assertEqual(len(node['position']), 2)
                    self.assertTrue(all(type(value) in (int, float) for value in node['position']))
            persist = next(node for node in instagram['nodes'] if node['name'] == 'SocialMEI persistir antes da IA')
            self.assertEqual(persist['parameters']['url'], 'http://team-api:8000/webhooks/instagram/n8n')
            self.assertEqual(persist['parameters']['contentType'], 'binaryData')
            self.assertEqual(persist['parameters']['inputDataFieldName'], 'data')
            self.assertEqual(instagram['connections']['SocialMEI confirmar persistencia']['main'], [[]])
            self.assertEqual(instagram['connections']['SocialMEI retomar fluxo existente']['main'], [[]])
            self.assertEqual((folder / 'credentials.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((source / 'n8n-workflows/experimental/whatsapp-bot-planner.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
