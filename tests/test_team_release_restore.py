"""Only synthetic backups/mocked Docker; production dumps never enter automated tests."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('release_restore', Path(__file__).resolve().parents[1] / 'tools/team-release-restore.py')
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class ReleaseRestoreTests(unittest.TestCase):
    def test_sha_and_stage_are_bound_before_private_backup_access(self):
        for name, sha in [('team-v33-' + 'a' * 12, 'b' * 40), ('../../live', 'a' * 40), ('team-v33-abc', 'abc')]:
            with self.subTest(name=name), patch.object(restore.legacy, 'private_dir') as access:
                with self.assertRaises(RuntimeError):
                    restore.stage_source(name, sha)
                access.assert_not_called()

    def test_default_inspection_never_creates_a_container(self):
        args = ['tool', '--target', 'team', '--backup', 'synthetic', '--stage', 'synthetic', '--expected-sha', 'a' * 40]
        with patch('sys.argv', args), patch.object(restore, 'stage_source', return_value=(Path('synthetic'), [])), \
             patch.object(restore.legacy, 'backup_receipt', return_value=Path('synthetic')), \
             patch.object(restore.legacy, 'checksum', return_value='b' * 64), \
             patch.object(restore, 'ReleaseRestore') as trial, contextlib.redirect_stdout(io.StringIO()) as output:
            restore.main()
        trial.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['mode'], 'inspection_only')
        self.assertFalse(json.loads(output.getvalue())['production_modified'])

    def test_incompatible_backup_is_blocked_before_migration_sql(self):
        trial = restore.ReleaseRestore()
        with patch.object(trial, 'start'), patch.object(restore.legacy, 'docker') as docker, \
             patch.object(restore.legacy, 'json_query', return_value=list(restore.profile.MIGRATIONS)[:31]):
            with self.assertRaisesRegex(RuntimeError, 'ledger_033_exato'):
                trial.execute(Path('synthetic'), Path('synthetic'), list(restore.profile.MIGRATIONS))
        self.assertEqual(docker.call_count, 1)
        self.assertIn('pg_restore', docker.call_args.args)

    def run_trial(self, *, corrupt_counts=False, schema_drift=False):
        versions = list(restore.profile.MIGRATIONS)
        before = {'schema_migrations': 33, **{'synthetic_' + str(i): i for i in range(12)}}
        if schema_drift:
            before['agenda_reminders'] = 0
        after = {**before, 'schema_migrations': 35, 'agenda_reminders': 0, 'wa_human_replies': 0}
        if corrupt_counts:
            after['synthetic_1'] = 2
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            migrations = source / 'database/migrations'
            migrations.mkdir(parents=True)
            for name in versions[33:]:
                (migrations / name).write_text('SELECT 1;\n')
            trial = restore.ReleaseRestore()
            with patch.object(trial, 'start'), patch.object(restore.legacy, 'docker') as docker, \
                 patch.object(restore.legacy, 'json_query', side_effect=[versions[:33], before, versions, after]):
                result = trial.execute(Path('synthetic'), source, versions)
                sql = docker.call_args.kwargs['input_text']
                self.assertIn('BEGIN;', sql)
                self.assertIn('COMMIT;', sql)
                self.assertIn(versions[33], sql)
                self.assertIn(versions[34], sql)
                self.assertNotIn(versions[32], sql)
                return result

    def test_only_reviewed_additions_apply_and_original_counts_must_survive(self):
        result = self.run_trial()
        self.assertTrue(result['restore_verified'])
        self.assertEqual(result['migration_ledger'], 35)
        with self.assertRaisesRegex(RuntimeError, 'contagens_originais_alteradas'):
            self.run_trial(corrupt_counts=True)
        with self.assertRaisesRegex(RuntimeError, 'schema_divergente'):
            self.run_trial(schema_drift=True)


if __name__ == '__main__':
    unittest.main()
