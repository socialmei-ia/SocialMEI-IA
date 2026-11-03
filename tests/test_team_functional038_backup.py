"""Private backup035/restore gates, with no Docker or production access."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
from types import ModuleType
import unittest
from unittest.mock import MagicMock, patch


class Functional038BackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'tools/team-functional038-backup.py'
        spec = importlib.util.spec_from_file_location('functional038_backup_tests', path)
        cls.m = importlib.util.module_from_spec(spec)
        fake = ModuleType('fcntl')
        fake.flock = MagicMock()
        fake.LOCK_EX, fake.LOCK_NB = 2, 4
        with patch.dict(sys.modules, {'fcntl': fake}) if sys.platform == 'win32' else contextlib.nullcontext():
            spec.loader.exec_module(cls.m)

    def snapshot(self):
        m = self.m
        tables = [f'table_{index:02d}' for index in range(71)]
        return {'snapshot': '00000001-00000002-1',
                'ledger': sorted(m.operator.profile.MIGRATIONS), 'tables': tables,
                'fingerprints': {table: [0, 'a' * 32] for table in tables},
                'schema': {group: [] for group in m.schema.METADATA_GROUPS}}

    def test_inspect_cannot_create_paths_dump_or_restore(self):
        m = self.m
        with patch.object(m.operator, 'preflight', return_value=({}, {})), \
                patch.object(m.operator, 'no_external_senders'), \
                patch.object(Path, 'mkdir') as mkdir, \
                patch.object(m.subprocess, 'Popen') as popen, \
                patch.object(m.subprocess, 'run') as run:
            result = m.create_backup(Path('/source'), Path('/bundle'))
        mkdir.assert_not_called()
        popen.assert_not_called()
        run.assert_not_called()
        self.assertFalse(result['backup_created'])
        self.assertFalse(result['restore_verified'])

    def test_create_requires_authorization_before_any_probe_or_write(self):
        m = self.m
        with patch.object(m.operator, 'preflight') as preflight, patch.object(Path, 'mkdir') as mkdir:
            with self.assertRaisesRegex(m.operator.legacy.Blocked, 'autorizacao_backup'):
                m.create_backup(Path('/source'), Path('/bundle'), create=True)
        preflight.assert_not_called()
        mkdir.assert_not_called()

    def test_create_requires_root_linux(self):
        m = self.m
        with patch.object(m.os, 'name', 'nt'), patch.object(m.operator, 'preflight') as preflight:
            with self.assertRaisesRegex(m.operator.legacy.Blocked, 'root_linux'):
                m.create_backup(Path('/source'), Path('/bundle'), create=True,
                                authorization=m.operator.AUTHORIZATION)
        preflight.assert_not_called()

    def test_snapshot_requires_exact035_71tables_and_11groups(self):
        m = self.m
        snapshot = self.snapshot()
        m.validate_snapshot(snapshot)
        variants = []
        missing = copy.deepcopy(snapshot); missing['ledger'].pop(); variants.append(missing)
        extra = copy.deepcopy(snapshot); extra['tables'].append('unexpected'); variants.append(extra)
        group = copy.deepcopy(snapshot); del group['schema']['constraints']; variants.append(group)
        data = copy.deepcopy(snapshot); data['fingerprints'].pop('table_00'); variants.append(data)
        identity = copy.deepcopy(snapshot); identity['snapshot'] = "x';DROP SCHEMA"; variants.append(identity)
        for value in variants:
            with self.subTest(value=value.keys()), self.assertRaises(m.operator.legacy.Blocked):
                m.validate_snapshot(value)

    def test_snapshot_program_is_readonly_and_keeps_same_export_alive(self):
        program = self.m.snapshot_program()
        compile(program, '<snapshot-reader>', 'exec')
        self.assertIn('REPEATABLE READ READ ONLY', program)
        self.assertIn('pg_export_snapshot()', program)
        self.assertIn('sys.stdin.read(1)', program)
        self.assertIn('conn.rollback()', program)
        self.assertNotIn('conn.commit()', program)
        self.assertIn('SET LOCAL search_path=pg_catalog', program)
        self.assertEqual(program.count('psycopg.connect('), 1)

    def test_restore_cleanup_refuses_foreign_label_or_network(self):
        m = self.m
        expected = {'Config': {'Labels': {m.RESTORE_LABEL: 'own'}},
                    'HostConfig': {'NetworkMode': 'none'}}
        with patch.object(m.operator.legacy, 'inspect', return_value=expected):
            self.assertEqual(m.restore_container_owned('own-container', 'own'), expected)
            with self.assertRaises(m.operator.legacy.Blocked):
                m.restore_container_owned('own-container', 'other')
        expected['HostConfig']['NetworkMode'] = 'bridge'
        with patch.object(m.operator.legacy, 'inspect', return_value=expected):
            with self.assertRaises(m.operator.legacy.Blocked):
                m.restore_container_owned('own-container', 'own')

    def test_invalid_table_cannot_enter_psql_query(self):
        m = self.m
        with patch.object(m, 'sql') as sql:
            with self.assertRaises(m.operator.legacy.Blocked):
                m.row_fingerprints('fixture', 'restorecheck', ['table"; DROP SCHEMA socialmei;--'])
        sql.assert_not_called()

    def test_private_configuration_archive_binds_exact_bytes(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / 'fictional.env'
            config.write_text('fictional only')
            plans = {'team-api': {'files': {str(config): m.operator.legacy.digest_file(config)},
                                  'mount_fingerprints': {}}}
            m.archive_private_configuration(folder, plans)
            with tarfile.open(folder / 'private-config.tar') as archive:
                self.assertEqual(len(archive.getmembers()), 1)
            config.write_text('changed after capture')
            with self.assertRaises(m.operator.legacy.Blocked):
                m.operator.verify_private_archive(folder / 'private-config.tar', plans)

    def test_cli_suppresses_raw_exceptions_and_secrets(self):
        m = self.m
        output = io.StringIO()
        with patch.object(sys, 'argv', ['backup', '--source', '/source', '--bundle', '/bundle']), \
                patch.object(m, 'create_backup', side_effect=ValueError('private-password-example')), \
                contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit):
                m.main()
        self.assertNotIn('private-password-example', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['code'], 'backup_gate_failed_details_redacted')

    def test_only_reviewed_schema_rewrites_compare_equal(self):
        m = self.m
        old = "CHECK (((status)::text = ANY ((ARRAY['pending'::character varying])::text[])))"
        new = "CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text])))"
        before = {'columns': [{'table_name': 'jobs', 'column_name': 'status', 'default': None}],
                  'constraints': [{'relname': 'jobs', 'conname': 'check', 'definition': old}]}
        after = copy.deepcopy(before)
        after['constraints'][0]['definition'] = new
        self.assertTrue(m.schema.compare(before, after))
        after['constraints'][0]['definition'] = new.replace('pending', 'other')
        self.assertFalse(m.schema.compare(before, after))
        after = copy.deepcopy(before); after['columns'][0]['default'] = 'changed'
        self.assertFalse(m.schema.compare(before, after))
        after = copy.deepcopy(before); after['constraints'] = []
        self.assertFalse(m.schema.compare(before, after))

    def test_schema_flags_missing_indexes_and_duplicate_objects_cannot_disappear(self):
        m = self.m
        value = {'tables': [{'table_name': 'a', 'rls': True}],
                 'indexes': [{'table_name': 'a', 'index_name': 'idx', 'valid': True}]}
        changed = copy.deepcopy(value); changed['indexes'][0]['valid'] = False
        self.assertFalse(m.schema.compare(value, changed))
        changed = copy.deepcopy(value); changed['indexes'] = []
        self.assertFalse(m.schema.compare(value, changed))
        value['tables'].append(value['tables'][0])
        with self.assertRaises(ValueError):
            m.schema.compare(value, value)


if __name__ == '__main__':
    unittest.main()
