"""Private backup038/restore gates, with no Docker or production access."""
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
from unittest.mock import MagicMock, mock_open, patch


class Multi188BackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'tools/team-multi188-backup.py'
        spec = importlib.util.spec_from_file_location('multi188_backup_tests', path)
        cls.m = importlib.util.module_from_spec(spec)
        fake = ModuleType('fcntl')
        fake.flock = MagicMock()
        fake.LOCK_EX, fake.LOCK_NB, fake.LOCK_UN = 2, 4, 8
        with patch.dict(sys.modules, {'fcntl': fake}) if sys.platform == 'win32' else contextlib.nullcontext():
            spec.loader.exec_module(cls.m)

    def snapshot(self):
        m = self.m
        tables = sorted([f'table_{index:02d}' for index in range(69)] +
                        ['users', 'workspaces', 'workspace_members', 'auth_credenciais', 'auth_sessoes'])
        return {'snapshot': '00000001-00000002-1',
                'ledger': sorted(m.operator.profile.MIGRATIONS038), 'tables': tables,
                'fingerprints': {table: [0, 'a' * 32] for table in tables},
                'schema': {group: [] for group in m.schema.METADATA_GROUPS}}

    def test_inspect_cannot_create_paths_dump_or_restore(self):
        m = self.m
        with patch.object(m.operator, 'preflight', return_value=({}, {})), \
                patch.object(m.operator, 'no_external_senders'), \
                patch.object(Path, 'mkdir') as mkdir, \
                patch.object(m, 'open', create=True) as opened, \
                patch.object(m.operator.legacy.fcntl, 'flock') as flock, \
                patch.object(m.subprocess, 'Popen') as popen, \
                patch.object(m.subprocess, 'run') as run:
            result = m.create_backup(Path('/source'), Path('/bundle'))
        mkdir.assert_not_called()
        popen.assert_not_called()
        run.assert_not_called()
        opened.assert_not_called()
        flock.assert_not_called()
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

    def test_busy_window_blocks_before_preflight_or_backup_work(self):
        m = self.m
        opened = mock_open()
        with patch.object(m.os, 'name', 'posix'), \
                patch.object(m.os, 'geteuid', return_value=0, create=True), \
                patch.object(m, 'open', opened, create=True), \
                patch.object(m.operator.legacy.fcntl, 'flock', side_effect=BlockingIOError), \
                patch.object(m, '_create_backup_locked') as work, \
                patch.object(m.operator, 'preflight') as preflight, \
                patch.object(m, 'save_private') as save, \
                patch.object(m.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(m.operator.legacy.Blocked, 'outra_janela'):
                m.create_backup(Path('/source'), Path('/bundle'), create=True,
                                authorization=m.operator.AUTHORIZATION)
        opened.assert_called_once_with('/run/lock/socialmei-wa-pilot-release.lock', 'a')
        work.assert_not_called()
        preflight.assert_not_called()
        save.assert_not_called()
        popen.assert_not_called()
        opened().__exit__.assert_called_once()

    def test_window_lock_is_released_after_success_or_failure(self):
        m = self.m
        for failure in (False, True):
            opened = mock_open()
            lock = opened()
            with patch.object(m.os, 'name', 'posix'), \
                    patch.object(m.os, 'geteuid', return_value=0, create=True), \
                    patch.object(m, 'open', opened, create=True), \
                    patch.object(m.operator.legacy.fcntl, 'flock') as flock, \
                    patch.object(m, '_create_backup_locked', return_value={'passed': True},
                                 side_effect=ValueError('fixture failure') if failure else None) as work:
                if failure:
                    with self.assertRaises(ValueError):
                        m.create_backup(Path('/source'), Path('/bundle'), create=True,
                                        authorization=m.operator.AUTHORIZATION)
                else:
                    self.assertEqual(m.create_backup(Path('/source'), Path('/bundle'), create=True,
                                                     authorization=m.operator.AUTHORIZATION),
                                     {'passed': True})
            self.assertEqual(flock.call_args_list[0].args,
                             (lock, m.operator.legacy.fcntl.LOCK_EX | m.operator.legacy.fcntl.LOCK_NB))
            self.assertEqual(flock.call_args_list[-1].args,
                             (lock, m.operator.legacy.fcntl.LOCK_UN))
            work.assert_called_once()
            lock.__exit__.assert_called_once()

    @unittest.skipUnless(os.name == 'posix', 'Real flock is verified on the Linux operator host')
    def test_real_flock_blocks_competing_window_then_allows_backup(self):
        m = self.m
        fcntl = m.operator.legacy.fcntl
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'window.lock'
            with path.open('a') as competing:
                fcntl.flock(competing, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(m, 'WINDOW_LOCK', str(path)), \
                        patch.object(m.os, 'geteuid', return_value=0), \
                        patch.object(m, '_create_backup_locked', return_value={'passed': True}) as work:
                    with self.assertRaisesRegex(m.operator.legacy.Blocked, 'outra_janela'):
                        m.create_backup(Path('/source'), Path('/bundle'), create=True,
                                        authorization=m.operator.AUTHORIZATION)
                    work.assert_not_called()
                    fcntl.flock(competing, fcntl.LOCK_UN)
                    self.assertEqual(m.create_backup(Path('/source'), Path('/bundle'), create=True,
                                                     authorization=m.operator.AUTHORIZATION),
                                     {'passed': True})
                    work.assert_called_once()

    def test_snapshot_requires_exact038_74tables_and_11groups(self):
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

    def test_sequence_toc_requires_every_named_sequence_and_excludes_data(self):
        m = self.m
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            toc = (b'; Header\n1; 0 0 TABLE DATA socialmei users owner\n'
                   b'2; 0 0 SEQUENCE SET socialmei users_id_seq owner\n')
            m.sequence_toc(folder, toc, ['users_id_seq'])
            saved = (folder / 'sequence-toc.private.txt').read_text()
            self.assertIn('SEQUENCE SET', saved)
            self.assertNotIn('TABLE DATA', saved)
        for content, names in ((b'', ['users_id_seq']),
                               (toc, ['other_seq']),
                               (toc + b'3; 0 0 SEQUENCE SET socialmei users_id_seq owner\n', ['users_id_seq'])):
            with tempfile.TemporaryDirectory() as temp, self.assertRaises(m.operator.legacy.Blocked):
                m.sequence_toc(Path(temp), content, names)

    def test_sequence_states_compare_exact_dump_value_and_called_bit(self):
        m = self.m
        dump = b"SELECT pg_catalog.setval('socialmei.users_id_seq', 8, true);\n"
        with patch.object(m.operator.legacy, 'docker', return_value=dump), \
                patch.object(m, 'sql', return_value='8|t'):
            self.assertTrue(m.verify_sequence_states('isolated', ['users_id_seq']))
        for restored in ('7|t', '8|f'):
            with patch.object(m.operator.legacy, 'docker', return_value=dump), \
                    patch.object(m, 'sql', return_value=restored), \
                    self.assertRaisesRegex(m.operator.legacy.Blocked, 'restored_sequence_state_diverges'):
                m.verify_sequence_states('isolated', ['users_id_seq'])
        with patch.object(m.operator.legacy, 'docker', return_value=b'-- no sequence'), \
                self.assertRaisesRegex(m.operator.legacy.Blocked, 'dump_sequence_states_incomplete'):
            m.verify_sequence_states('isolated', ['users_id_seq'])

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
