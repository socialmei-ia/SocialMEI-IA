"""No real database, dump, SMTP or AWS calls in these export contracts."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

TARGET = Path(__file__).resolve().parents[1] / 'tools/postgres-source-export.py'
spec = importlib.util.spec_from_file_location('source_export', TARGET)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
DSN = ('host=source.invalid dbname=fixture user=fixture password=synthetic '
       'sslmode=verify-full sslrootcert=/synthetic/ca.crt')


def identity():
    return exporter.source_identity(exporter.source_environment(DSN))


class ExportTests(unittest.TestCase):
    def test_loopback_transport_is_explicit_and_never_allows_plain_remote_postgres(self):
        dsn = 'host=127.0.0.1 dbname=fixture user=fixture password=synthetic sslmode=disable'
        with self.assertRaises(ValueError):
            exporter.source_environment(dsn)
        self.assertEqual(exporter.source_environment(dsn, isolated_loopback=True)['PGHOST'], '127.0.0.1')
        for other in (dsn.replace('127.0.0.1', 'remote.invalid'), dsn + ' service=other',
                      dsn.replace('127.0.0.1', 'localhost'), dsn + ' sslrootcert=/unused'):
            with self.subTest(dsn=other), self.assertRaises(ValueError):
                exporter.source_environment(other, isolated_loopback=True)

    def test_sequence_change_prevents_publication_of_full_comparison_artifact(self):
        conn = MagicMock()
        manifest = {'sequences': [{'schema': 'socialmei', 'sequence': 'synthetic_seq',
                                   'last_value': 42, 'is_called': True}]}
        conn.execute.return_value.fetchone.return_value = (42, True)
        exporter.verify_sequence_state(conn, manifest)
        for value in ((43, True), (42, False)):
            conn.execute.return_value.fetchone.return_value = value
            with self.assertRaises(ValueError):
                exporter.verify_sequence_state(conn, manifest)

    def test_reviewed040_ledger_rejects_incomplete_historical_and_future_migrations(self):
        versions = sorted(p.name for p in (TARGET.parents[1] / 'database/migrations').glob('*.sql')
                          if p.name[:3].isdigit() and 1 <= int(p.name[:3]) <= 40)
        exporter.verify_profile040({'migration_ledger': [{'schema': 'socialmei', 'versions': versions}]})
        for installed in ([], versions[:-1], versions + ['041_future.sql'], versions[::-1]):
            with self.assertRaises(ValueError):
                exporter.verify_profile040({'migration_ledger': [{'schema': 'socialmei', 'versions': installed}]})

    def test_plan_never_connects_or_runs_processes(self):
        with patch.object(exporter, 'export') as run, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(exporter.main([]), 0)
        run.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['connections'], 0)

    def test_run_requires_explicit_approval(self):
        with patch.object(exporter, 'export') as run, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                exporter.main(['--run', '--output-directory', 'unused'])
        run.assert_not_called()

    def test_explicit_source_does_not_fall_back_to_application_database(self):
        with patch.dict(os.environ, {'DATABASE_URL': DSN}, clear=True), \
                patch.object(exporter, 'export') as run, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(exporter.main(['--run', '--approved-data-export',
                                            '--output-directory', 'unused']), 1)
        run.assert_not_called()

    def test_tls_identity_and_service_aliases_fail_closed(self):
        for dsn in ('host=source.invalid sslmode=require',
                    DSN + ' hostaddr=127.0.0.1', DSN + ' service=other',
                    DSN.replace('source.invalid', '/tmp/postgres-socket'),
                    'dbname=fixture user=fixture sslmode=verify-full'):
            with self.subTest(dsn=dsn), self.assertRaises(ValueError):
                exporter.source_environment(dsn)
        with patch.dict(os.environ, {'PGHOST': 'wrong', 'PGSERVICE': 'wrong', 'PGPASSWORD': 'wrong'}):
            env = exporter.source_environment(DSN)
        self.assertEqual(env['PGDATABASE'], 'fixture')
        self.assertEqual(env['PGHOST'], 'source.invalid')
        self.assertNotIn('PGSERVICE', env)
        self.assertEqual(env['PGPASSWORD'], 'synthetic')

    def exercise(self, folder, failure=None):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.info.server_version = 170011
        conn.execute.return_value.fetchone.return_value = ('00000003-00000010-1',)
        check = exporter.validator()
        check.snapshot = MagicMock(return_value={'valid': True, 'synthetic': True})
        calls = []

        def process(args, **kwargs):
            calls.append((args, kwargs))
            if '--version' in args:
                return subprocess.CompletedProcess(args, 0, stdout=b'pg_dump (PostgreSQL) 17.11 (Debian)')
            if '--format=custom' in args:
                self.assertFalse(conn.rollback.called)
                kwargs['stdout'].write(b'PGDMP synthetic archive')
                if failure:
                    raise failure
            return subprocess.CompletedProcess(args, 0, stdout=b'')

        with patch('psycopg.connect', return_value=conn), \
                patch.object(exporter, 'validator', return_value=check), \
                patch.object(exporter, 'private_directory', return_value=Path(folder)), \
                patch.object(exporter.subprocess, 'run', side_effect=process):
            result = exporter.export(DSN, folder, expected_identity=identity())
        return result, calls, check, conn

    def test_dump_and_manifest_share_snapshot_and_secrets_never_enter_arguments(self):
        with TemporaryDirectory() as folder:
            result, calls, check, conn = self.exercise(folder)
            self.assertTrue((Path(folder) / 'source.dump').exists())
            self.assertFalse((Path(folder) / 'source.dump.partial').exists())
            self.assertEqual(result['dump_sha256'], exporter.sha256(Path(folder) / 'source.dump'))
            self.assertEqual(result['manifest_sha256'], exporter.sha256(Path(folder) / 'source-manifest.private.json'))
        check.snapshot.assert_called_once_with(DSN, exported_snapshot='00000003-00000010-1')
        self.assertTrue(conn.rollback.called)
        for args, kwargs in calls:
            self.assertNotIn('synthetic', ' '.join(args))
        dump_args, dump_options = next(call for call in calls if '--format=custom' in call[0])
        self.assertIn('--snapshot=00000003-00000010-1', dump_args)
        self.assertEqual(dump_options['env']['PGDATABASE'], 'fixture')
        self.assertEqual(dump_options['env']['PGPASSWORD'], 'synthetic')
        self.assertFalse(result['cutover_authorized'])
        self.assertFalse(result['writers_quiescence_verified'])
        self.assertFalse(result['restoration_verified'])

    def test_failed_or_timed_out_dump_remains_partial_and_never_gets_success_receipt(self):
        for failure in (subprocess.CalledProcessError(1, ['pg_dump'], stderr=b'private'),
                        subprocess.TimeoutExpired(['pg_dump'], 1800)):
            with TemporaryDirectory() as folder, self.assertRaises(type(failure)):
                try:
                    self.exercise(folder, failure=failure)
                finally:
                    self.assertTrue((Path(folder) / 'source.dump.partial').exists())
                    self.assertFalse((Path(folder) / 'export-receipt.json').exists())
                    self.assertFalse((Path(folder) / 'source.dump').exists())

    def test_errors_never_echo_dsn_or_driver_details(self):
        with patch.dict(os.environ, {'SOCIALMEI_EXPORT_SOURCE_DSN': DSN,
                                    'SOCIALMEI_EXPORT_SOURCE_FINGERPRINT': identity()}), \
                patch.object(exporter, 'export', side_effect=RuntimeError(DSN)), \
                contextlib.redirect_stderr(io.StringIO()) as out:
            self.assertEqual(exporter.main(['--run', '--approved-data-export',
                                            '--output-directory', 'unused']), 1)
        self.assertNotIn('synthetic', out.getvalue())

    def test_wrong_client_version_blocks_before_connection_or_directory_creation(self):
        with patch.object(exporter.subprocess, 'run', return_value=subprocess.CompletedProcess(
                ['pg_dump', '--version'], 0, stdout=b'pg_dump (PostgreSQL) 18.1')), \
                patch('psycopg.connect') as connect, \
                patch.object(exporter, 'private_directory') as directory:
            with self.assertRaises(ValueError):
                exporter.export(DSN, 'unused', expected_identity=identity())
        connect.assert_not_called()
        directory.assert_not_called()

    def test_historical_or_other_source_identity_blocks_before_any_process_or_connection(self):
        with patch.object(exporter.subprocess, 'run') as process, patch('psycopg.connect') as connect:
            with self.assertRaises(ValueError):
                exporter.export(DSN, 'unused', expected_identity='historical')
        process.assert_not_called()
        connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
