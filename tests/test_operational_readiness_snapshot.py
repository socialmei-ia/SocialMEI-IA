"""Only synthetic inspect/log/cgroup fixtures; no SSH, Docker or SQL."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ops_snapshot', ROOT / 'tools/operational-readiness-snapshot.py')
ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ops)


class OperationalSnapshotTests(unittest.TestCase):
    def test_projection_never_emits_credentials_logs_commands_or_mount_sources(self):
        secret = 'synthetic-private-value'
        fixture = {'Name': '/synthetic-api', 'Image': 'sha256:' + 'a' * 64,
                   'State': {'Status': 'running', 'Running': True, 'Pid': 42, 'Health': {
                       'Status': 'unhealthy', 'Log': [{'ExitCode': 1, 'Output': secret + ' planLimitReached'}]}},
                   'Config': {'Env': ['DATABASE_URL=postgresql://user:' + secret + '@db.prisma.io/test',
                                      'SOCIALMEI_IDENTITY_MODE=' + secret],
                              'Healthcheck': {'Test': ['CMD', secret]}, 'Labels': None},
                   'HostConfig': {'PortBindings': None},
                   'Mounts': [{'Source': '/private/' + secret, 'Destination': '/run/private', 'RW': False}]}
        with patch.object(ops, 'cgroup_memory', return_value={'current_bytes': 100}):
            row = ops.project(fixture, [])
        self.assertNotIn(secret, json.dumps(row))
        self.assertTrue(row['health_output_categories']['plan_limit_seen'])
        self.assertEqual(row['database_provider'], 'prisma')
        self.assertEqual(row['optional_modes']['SOCIALMEI_IDENTITY_MODE'], 'configured_other')

    def test_same_effective_database_is_grouped_without_exporting_dsn(self):
        groups = []
        def obj(url):
            return {'Name': '/synthetic', 'Config': {'Env': ['DATABASE_URL=' + url]}, 'State': {}}
        one = ops.project(obj(' postgresql://synthetic@private/a '), groups)
        two = ops.project(obj('postgresql://synthetic@private/a'), groups)
        other = ops.project(obj('postgresql://synthetic@private/b'), groups)
        self.assertEqual(one['database_group'], two['database_group'])
        self.assertNotEqual(one['database_group'], other['database_group'])
        self.assertNotIn('private', json.dumps(one))

    def test_encoding_and_query_options_do_not_invent_different_database_targets(self):
        self.assertEqual(ops.db_identity({'DATABASE_URL': 'postgresql://u:p%40ss@private/a?sslmode=require'}),
                         ops.db_identity({'DATABASE_URL': 'postgres://u:p%40ss@private:5432/a?connect_timeout=5'}))
        self.assertEqual(ops.db_identity({'DATABASE_URL': 'postgresql://u:p%40ss@private/a'}),
                         ops.db_identity({'POSTGRES_HOST': 'private', 'POSTGRES_DB': 'a',
                                          'POSTGRES_USER': 'u', 'POSTGRES_PASSWORD': 'p@ss'}))

    def test_log_classification_is_only_categories(self):
        result = ops.category('GET /health/db HTTP/1.1 503 private@example.test planLimitReached')
        self.assertEqual(set(result), {'plan_limit_seen', 'health_db_503_seen',
                                     'health_db_200_seen', 'readiness_unavailable_seen'})
        self.assertTrue(result['health_db_503_seen'])
        self.assertNotIn('private', str(result))

    def test_latest_backup_hash_verified_without_returning_dump_content(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / 'backups').mkdir()
            dump = base / 'backups/destination-synthetic.dump'
            data = b'PGDMPsynthetic-private-content'
            dump.write_bytes(data)
            receipt = {'sha256': ops.hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                       'source': 'isolated_historical_destination', 'current_production_backup': False}
            dump.with_suffix('.json').write_text(json.dumps(receipt))
            (base / 'backups/destination-new.external.private.json').write_text('{"phase":"verified"}')
            with patch.object(ops, 'BACKUP', base), patch.object(ops, 'run', return_value='ActiveState=active'):
                result = ops.backups()
                self.assertEqual(result['local_receipt_count'], 1)
                self.assertTrue(result['latest_local_backup']['local_hash_and_size_verified'])
                self.assertFalse(result['latest_local_backup']['current_production_backup'])
                self.assertNotIn('synthetic-private-content', json.dumps(result))
                dump.write_bytes(b'changed')
                self.assertFalse(ops.backups()['latest_local_backup']['local_hash_and_size_verified'])

    def test_legacy_receipt_free_text_is_not_exported(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / 'backups').mkdir()
            secret = 'synthetic-private-error'
            (base / 'source-export-receipt.json').write_text(json.dumps({
                'reason': secret, 'source_export_succeeded': secret, 'bytes': secret}))
            (base / 'backups/destination-synthetic.json').write_text(json.dumps({
                key: secret for key in ('created_at_utc', 'bytes', 'sha256', 'source', 'external_uploaded')}))
            with patch.object(ops, 'BACKUP', base), patch.object(ops, 'run', return_value='ActiveState=active'):
                self.assertNotIn(secret, json.dumps(ops.backups()))

    def test_inaccessible_directory_is_unknown_not_missing_backups(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(ops, 'BACKUP', Path(folder)), \
                patch.object(ops.os, 'access', return_value=False):
            result = ops.backups()
            self.assertFalse(result['inspection_available'])
            self.assertIsNone(result['s3_configuration_present'])
            self.assertIsNone(result['local_receipt_count'])


if __name__ == '__main__':
    unittest.main()
