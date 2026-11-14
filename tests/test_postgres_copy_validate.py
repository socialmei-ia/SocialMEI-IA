"""Offline contracts for the read-only database copy validator."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


TARGET = Path(__file__).resolve().parents[1] / 'tools/postgres-copy-validate.py'
spec = importlib.util.spec_from_file_location('postgres_copy_validate', TARGET)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def manifest():
    return {'manifest_version': 1, 'created_at_utc': 'before',
            'large_objects': 0,
            'structure': {'tables': ['fixture']},
            'tables': [{'schema': 'socialmei', 'table': 'fixture', 'rows': 1, 'sha256': 'a' * 64}],
            'sequences': [{'last_value': 1, 'is_called': True}],
            'foreign_keys': [{'violations': 0}], 'migration_ledger': [{'versions': ['039_fixture.sql']}],
            'effective_permissions': [['socialmei', 'fixture', 'r', True, True, True, True]], 'valid': True}


class CopyValidatorTests(unittest.TestCase):
    def test_postgres_constant_array_cast_rewrite_preserves_values_and_real_differences(self):
        source = manifest()
        source['structure'] = {
            'constraints': [['socialmei', 'auth_identity_mail', 'role_check', 'c', True, False, False,
                             "CHECK (role::text = ANY (ARRAY['admin'::character varying, 'member'::character varying]::text[]))"]],
            'indexes': [['socialmei', 'auth_identity_mail', 'active', True, True, True,
                         "CREATE UNIQUE INDEX active ON socialmei.auth_identity_mail (id) WHERE status::text = ANY ((ARRAY['pending'::character varying, 'sent'::character varying])::text[])"]],
        }
        target = copy.deepcopy(source)
        target['structure']['constraints'][0][-1] = (
            "CHECK (role::text = ANY (ARRAY['admin'::character varying::text, 'member'::character varying::text]))")
        target['structure']['indexes'][0][-1] = (
            "CREATE UNIQUE INDEX active ON socialmei.auth_identity_mail (id) WHERE status::text = ANY (ARRAY[('pending'::character varying)::text, ('sent'::character varying)::text])")
        result = validator.compare(source, target)
        self.assertTrue(result['equal'])
        self.assertTrue(result['constant_array_cast_representation_only'])
        self.assertIn('::text[]', source['structure']['constraints'][0][-1])
        for field in ('constraints', 'indexes'):
            changed = copy.deepcopy(target)
            changed['structure'][field][0][-1] = changed['structure'][field][0][-1].replace(
                "'admin'", "'owner'").replace("'sent'", "'uncertain'")
            self.assertFalse(validator.compare(source, changed)['equal'])
        changed = copy.deepcopy(target)
        changed['structure']['constraints'][0][4] = False
        self.assertFalse(validator.compare(source, changed)['equal'])

    def test_digest_preserves_duplicates_and_unambiguous_boundaries(self):
        first = validator.digest_rows(iter([('ab',), ('c',)]))
        second = validator.digest_rows(iter([('a',), ('bc',)]))
        duplicate = validator.digest_rows(iter([('ab',), ('ab',)]))
        self.assertEqual(first['rows'], 2)
        self.assertNotEqual(first['sha256'], second['sha256'])
        self.assertNotEqual(first['sha256'], duplicate['sha256'])
        self.assertEqual(first, validator.digest_rows(iter([('ab',), ('c',)])))
        self.assertEqual(len(validator.digest_rows([])['sha256']), 64)

    def test_array_cast_normalization_never_rewrites_quoted_names_or_literal_contents(self):
        first_name = "ARRAY['x'::character varying]::text[]"
        second_name = "ARRAY[('x'::character varying)::text]"
        source = manifest()
        source['structure'] = {'constraints': [['schema', 'table', 'check', 'CHECK ("' + first_name + '" IS NOT NULL)']]}
        target = copy.deepcopy(source)
        target['structure']['constraints'][0][-1] = 'CHECK ("' + second_name + '" IS NOT NULL)'
        self.assertFalse(validator.compare(source, target)['equal'])
        for value in ("CHECK (note = 'ARRAY[''x''::character varying]::text[]')",
                      "CHECK (note = E'escaped\\string ARRAY[''x''::character varying]::text[]')",
                      "CHECK (note = $$ARRAY['x'::character varying]::text[]$$)"):
            structure = {'constraints': [['schema', 'table', 'check', value]]}
            self.assertEqual(validator.comparable_structure(structure), structure)

    def test_comparison_checks_content_sequences_schema_and_ledger_not_timestamp(self):
        source = manifest()
        target = copy.deepcopy(source)
        target['created_at_utc'] = 'after'
        self.assertTrue(validator.compare(source, target)['equal'])
        for section in ('structure', 'tables', 'sequences', 'foreign_keys', 'migration_ledger'):
            target = copy.deepcopy(source)
            target[section] = {} if section == 'structure' else []
            result = validator.compare(source, target)
            self.assertFalse(result['equal'])
            self.assertIn(section, result['different_sections'])
            self.assertFalse(result['cutover_authorized'])
            self.assertFalse(result['freshness_verified'])

    def test_invalid_fk_never_passes_even_when_manifests_match(self):
        source = manifest()
        source['valid'] = False
        self.assertFalse(validator.compare(source, source)['equal'])
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            validator.compare({'manifest_version': 1}, {'manifest_version': 1})

    def test_permissions_are_reported_separately_for_different_application_roles(self):
        source = manifest()
        target = copy.deepcopy(source)
        target['effective_permissions'] = []
        result = validator.compare(source, target)
        self.assertTrue(result['equal'])
        self.assertFalse(result['effective_permissions_equal'])

    def test_private_output_is_new_and_never_overwrites_or_follows_links(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.private.json'
            validator.private_json(path, {'valid': True})
            self.assertEqual(json.loads(path.read_text()), {'valid': True})
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                validator.private_json(path, {'replacement': True})
            self.assertEqual(json.loads(path.read_text()), {'valid': True})

    def test_cli_uses_environment_and_sanitizes_all_failures(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://PRIVATE_SECRET'}), \
                patch.object(validator, 'snapshot', side_effect=RuntimeError('PRIVATE_SECRET')) as snapshot:
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                result = validator.main(['--output', 'unused.private.json'])
            self.assertEqual(result, 1)
            snapshot.assert_called_once_with('postgresql://PRIVATE_SECRET')
            self.assertNotIn('PRIVATE_SECRET', output.getvalue())

    def test_cli_compare_writes_private_full_evidence_and_prints_only_comparison(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {'SOURCE_DATABASE_URL': 'private-source', 'TARGET_DATABASE_URL': 'private-target'}), \
                patch.object(validator, 'snapshot', side_effect=[manifest(), manifest()]) as snapshot:
            output = io.StringIO()
            path = Path(folder) / 'comparison.private.json'
            with contextlib.redirect_stdout(output):
                status = validator.main(['--compare', '--output', str(path)])
            self.assertEqual(status, 0)
            self.assertEqual(snapshot.call_args_list[0].args, ('private-source',))
            self.assertEqual(snapshot.call_args_list[1].args, ('private-target',))
            self.assertTrue(json.loads(output.getvalue())['equal'])
            self.assertNotIn('private-source', output.getvalue())
            self.assertNotIn('fixture', output.getvalue())
            self.assertIn('source', json.loads(path.read_text()))

    def test_snapshot_sets_read_only_before_catalog_and_rolls_back(self):
        import psycopg
        conn = MagicMock()
        conn.execute.return_value.__iter__.return_value = iter([])
        conn.execute.return_value.fetchone.return_value = (170006, 'on', 'repeatable read')
        conn.execute.side_effect = lambda query: (
            MagicMock(fetchone=MagicMock(return_value=(0,)))
            if query == 'SELECT count(*) FROM pg_catalog.pg_largeobject_metadata'
            else conn.execute.return_value)
        empty = {'relations': []}
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch.object(psycopg, 'connect', return_value=context), \
                patch.object(validator, 'catalog', return_value=empty), \
                patch.object(validator, 'foreign_keys', return_value=[]):
            result = validator.snapshot('PRIVATE_SOURCE')
        self.assertEqual(conn.execute.call_args_list[0].args,
                         ('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY',))
        self.assertIn('SET LOCAL row_security = off', [call.args[0] for call in conn.execute.call_args_list])
        conn.rollback.assert_called_once()
        self.assertTrue(result['snapshot']['sequence_comparison_requires_quiescent_writers'])
        self.assertTrue(result['valid'])
        self.assertEqual(result['large_objects'], 0)

    def test_fk_validation_quotes_identifiers_and_respects_match_null_rules(self):
        from psycopg import sql
        conn = MagicMock()
        constraints = [
            ('socialmei', 'child', 'tenant_fk', 'socialmei', 'parent', 's',
             ['workspace_id', 'odd"column'], ['workspace_id', 'id']),
            ('socialmei', 'child', 'full_fk', 'socialmei', 'parent', 'f',
             ['workspace_id', 'parent_id'], ['workspace_id', 'id']),
        ]
        conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=constraints)),
            MagicMock(fetchone=MagicMock(return_value=(0,))),
            MagicMock(fetchone=MagicMock(return_value=(2,))),
        ]
        result = validator.foreign_keys(conn, sql)
        self.assertEqual([row['violations'] for row in result], [0, 2])
        self.assertTrue(all(row['workspace_key'] for row in result))
        simple = conn.execute.call_args_list[1].args[0].as_string()
        full = conn.execute.call_args_list[2].args[0].as_string()
        self.assertIn('c."odd""column" IS NOT NULL', simple)
        self.assertIn('NOT EXISTS', simple)
        self.assertIn('IS NULL', full)
        self.assertIn(' OR ', full)
        self.assertTrue(simple.startswith('SELECT count(*)'))

    def test_exported_snapshot_is_imported_before_any_catalog_read(self):
        import psycopg
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.__iter__.return_value = iter([])
        conn.execute.return_value.fetchone.return_value = (170011, 'on', 'repeatable read')
        conn.execute.side_effect = lambda query: (
            MagicMock(fetchone=MagicMock(return_value=(0,)))
            if query == 'SELECT count(*) FROM pg_catalog.pg_largeobject_metadata'
            else conn.execute.return_value)
        with patch.object(psycopg, 'connect', return_value=conn), \
                patch.object(validator, 'catalog', return_value={'relations': []}), \
                patch.object(validator, 'foreign_keys', return_value=[]):
            validator.snapshot('private-source', exported_snapshot="00000003-00000010-1'")
        statements = conn.execute.call_args_list
        self.assertEqual(statements[0].args[0],
                         'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        self.assertEqual(statements[1].args[0].as_string(),
                         "SET TRANSACTION SNAPSHOT '00000003-00000010-1'''" )
        conn.rollback.assert_called_once()

    def test_foreign_tables_fail_closed_before_data_read(self):
        import psycopg
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (0,)
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch.object(psycopg, 'connect', return_value=context), \
                patch.object(validator, 'catalog', return_value={'relations': [['public', 'remote', 'f']]}):
            with self.assertRaisesRegex(ValueError, 'Foreign tables'):
                validator.snapshot('private-source')
        conn.cursor.assert_not_called()

    def test_large_objects_fail_closed_before_catalog_or_data_read(self):
        import psycopg
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (2,)
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch.object(psycopg, 'connect', return_value=context), \
                patch.object(validator, 'catalog') as catalog:
            with self.assertRaises(validator.LargeObjectsUnsupported):
                validator.snapshot('private-source')
        catalog.assert_not_called()
        conn.cursor.assert_not_called()

    def test_large_object_block_is_explicit_and_old_manifests_are_not_accepted(self):
        source = manifest()
        del source['large_objects']
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            validator.compare(source, manifest())
        with patch.dict(os.environ, {'DATABASE_URL': 'private-source'}), \
                patch.object(validator, 'snapshot', side_effect=validator.LargeObjectsUnsupported('PRIVATE_SECRET')):
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                status = validator.main(['--output', 'unused.private.json'])
        self.assertEqual(status, 1)
        self.assertIn('large objects', output.getvalue())
        self.assertNotIn('PRIVATE_SECRET', output.getvalue())


if __name__ == '__main__':
    unittest.main()
