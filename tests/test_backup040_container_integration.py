"""Opt-in, real PostgreSQL040 export/restore; synthetic data in owned local containers."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('restore040', ROOT / 'tools/backup-restore-rehearsal.py')
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


@unittest.skipUnless(os.getenv('SOCIALMEI_BACKUP040_CONTAINER_TESTS') == '1', 'Explicit local container test opt-in required')
class Backup040Integration(unittest.TestCase):
    def test_real040_shared_snapshot_export_and_full_isolated_restore(self):
        context = json.loads(restore.run('docker', 'context', 'inspect'))
        self.assertTrue(context[0]['Endpoints']['docker']['Host'].startswith(('unix://', 'npipe://')))
        self.assertFalse(os.getenv('DOCKER_HOST', '').startswith(('tcp:', 'ssh:')))
        postgres = json.loads(restore.run('docker', 'image', 'inspect', 'postgres:17-alpine'))[0]['Id']
        exporter = os.environ.get('SOCIALMEI_BACKUP040_TEST_IMAGE', 'socialmei-backup040:test-20261121')
        validator = json.loads(restore.run('docker', 'image', 'inspect',
                              os.environ.get('SOCIALMEI_BACKUP040_VALIDATOR_IMAGE', exporter)))[0]['Id']
        token = secrets.token_hex(12); name = 'socialmei-export040-test-' + token
        created = False
        with tempfile.TemporaryDirectory(prefix='socialmei-export040-') as temp:
            try:
                restore.run('docker', 'create', '--name', name, '--label', 'socialmei.isolated-restore=' + token,
                    '--network', 'none', '--user', 'postgres', '--read-only', '--cap-drop', 'ALL',
                    '--security-opt', 'no-new-privileges', '--memory', '512m', '--cpus', '0.5',
                    '--restart', 'no', '--tmpfs', '/var/lib/postgresql/data:rw,size=512m,mode=1777',
                    '--tmpfs', '/var/run/postgresql:rw,size=16m,mode=1777', '--tmpfs', '/tmp:rw,size=16m,mode=1777',
                    '-e', 'PGDATA=/var/lib/postgresql/data/pgdata', '-e', 'POSTGRES_USER=postgres',
                    '-e', 'POSTGRES_DB=source040', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', postgres)
                created = True
                restore.run('docker', 'start', name)
                for attempt in range(60):
                    try:
                        restore.run('docker', 'exec', name, 'pg_isready', '-U', 'postgres', timeout=5)
                        break
                    except RuntimeError:
                        if attempt == 59: raise
                        time.sleep(.5)
                sql = 'CREATE SCHEMA socialmei; CREATE TABLE socialmei.schema_migrations(version text PRIMARY KEY);\n'
                migrations = sorted(p for p in (ROOT / 'database/migrations').glob('*.sql')
                                    if p.name[:3].isdigit() and 1 <= int(p.name[:3]) <= 40)
                self.assertEqual(len(migrations), 40)
                for path in migrations:
                    sql += path.read_text(encoding='utf-8') + "\nINSERT INTO socialmei.schema_migrations(version) VALUES ('" + path.name + "');\n"
                sql += "CREATE TABLE public.backup_probe(id bigserial PRIMARY KEY,label text); INSERT INTO public.backup_probe(label) VALUES ('SYNTHETIC BACKUP TEST');"
                loaded = subprocess.run(['docker', 'exec', '-i', name, 'psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1',
                            '-U', 'postgres', '-d', 'source040'], input=sql.encode(), capture_output=True, timeout=180)
                self.assertEqual(loaded.returncode, 0, loaded.stderr.decode(errors='replace')[-1500:])
                identity = __import__('hashlib').sha256(json.dumps(['127.0.0.1', 5432, 'source040']).encode()).hexdigest()
                output = restore.run('docker', 'run', '--rm', '--network', 'container:' + name,
                    '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                    '--memory', '256m', '--cpus', '0.5',
                    '--mount', 'type=bind,src=' + temp + ',dst=/artifacts',
                    '-e', 'SOCIALMEI_EXPORT_SOURCE_DSN=host=127.0.0.1 dbname=source040 user=postgres password=synthetic-only sslmode=disable',
                    '-e', 'SOCIALMEI_EXPORT_SOURCE_FINGERPRINT=' + identity,
                    exporter, '--run', '--approved-data-export', '--isolated-loopback', '--profile', '040',
                    '--output-directory', '/artifacts/export', timeout=180)
                exported = json.loads(output)
                self.assertTrue(exported['shared_snapshot'])
                self.assertTrue(exported['sequence_state_unchanged_during_export'])
                folder = Path(temp) / 'export'
                approval = folder / 'restore-approval.private.json'
                approval.write_text(json.dumps({'explicit_authorization': True, 'scope': 'isolated_restore',
                    'production_mutation': False, 'dump_sha256': exported['dump_sha256'],
                    'manifest_sha256': exported['manifest_sha256'], 'profile': '040', 'postgres_major': 17,
                    'postgres_image_id': postgres, 'validator_api_image_id': validator}), encoding='utf-8')
                proof = restore.rehearse(folder / 'source.dump', folder / 'source-manifest.private.json', approval)
                self.assertTrue(proof['restoration_verified'])
                self.assertTrue(proof['source_contents_compared'])
                self.assertTrue(proof['owned_cleanup_verified'])
                self.assertGreater(proof['tables_verified'], 50)
                self.assertFalse(proof['production_mutation'])
            finally:
                if created: restore.cleanup('docker', name, token, 'none')


if __name__ == '__main__':
    unittest.main()
