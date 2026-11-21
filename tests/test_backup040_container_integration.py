"""Opt-in, real PostgreSQL040 export/restore; synthetic data in owned local containers."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('restore040', ROOT / 'tools/backup-restore-rehearsal.py')
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)
spec_backup = importlib.util.spec_from_file_location('periodic040', ROOT / 'tools/aws-postgres-backup.py')
backup = importlib.util.module_from_spec(spec_backup)
spec_backup.loader.exec_module(backup)


@unittest.skipUnless(os.getenv('SOCIALMEI_BACKUP040_CONTAINER_TESTS') == '1', 'Explicit local container test opt-in required')
class Backup040Integration(unittest.TestCase):
    def test_real040_shared_snapshot_export_and_full_isolated_restore(self):
        self.roundtrip('040')

    def test_schema041_handover_remains_exportable_and_restorable(self):
        self.roundtrip('041')

    def test_tls_required_source_exports_with_pinned_ca_and_full_restore(self):
        self.roundtrip('040', tls=True)

    def roundtrip(self, profile, tls=False):
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
                        restore.run('docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres', timeout=5)
                        break
                    except RuntimeError:
                        if attempt == 59: raise
                        time.sleep(.5)
                sql = 'CREATE SCHEMA socialmei; CREATE TABLE socialmei.schema_migrations(version text PRIMARY KEY);\n'
                migrations = sorted(p for p in (ROOT / 'database/migrations').glob('*.sql')
                                    if p.name[:3].isdigit() and 1 <= int(p.name[:3]) <= int(profile))
                self.assertEqual(len(migrations), int(profile))
                for path in migrations:
                    sql += path.read_text(encoding='utf-8') + "\nINSERT INTO socialmei.schema_migrations(version) VALUES ('" + path.name + "');\n"
                sql += "CREATE TABLE public.backup_probe(id bigserial PRIMARY KEY,label text); INSERT INTO public.backup_probe(label) VALUES ('SYNTHETIC BACKUP TEST');"
                loaded = subprocess.run(['docker', 'exec', '-i', name, 'psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1',
                            '-U', 'postgres', '-d', 'source040'], input=sql.encode(), capture_output=True, timeout=180)
                self.assertEqual(loaded.returncode, 0, loaded.stderr.decode(errors='replace')[-1500:])
                helper = json.loads(restore.run('docker', 'image', 'inspect', exporter))[0]['Id']
                config = {'database': 'source040', 'schema': profile, 'export_helper_image_id': helper,
                          'export_source_dsn': 'postgresql://postgres:synthetic-only@127.0.0.1:5432/source040?sslmode=disable'}
                if tls:
                    openssl = shutil.which('openssl')
                    if not openssl:
                        candidate = Path('C:/Program Files/Git/usr/bin/openssl.exe')
                        self.assertTrue(candidate.is_file(), 'OpenSSL required for synthetic TLS fixture')
                        openssl = str(candidate)
                    key = Path(temp) / 'server.key'; cert = Path(temp) / 'server.crt'
                    subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, capture_output=True,
                        env=dict(os.environ, MSYS_NO_PATHCONV='1'), timeout=30)
                    os.chmod(cert, 0o600)
                    for filename, content in [('server.key', key.read_bytes()), ('server.crt', cert.read_bytes()),
                        ('pg_hba.conf', b'local all all trust\nhostssl all all 127.0.0.1/32 trust\nhostnossl all all 0.0.0.0/0 reject\n')]:
                        written = subprocess.run(['docker', 'exec', '-i', name, 'sh', '-c',
                            'umask 077; cat > "$PGDATA/' + filename + '"'], input=content, capture_output=True, timeout=15)
                        self.assertEqual(written.returncode, 0)
                    restore.run('docker', 'exec', name, 'psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1',
                        '-U', 'postgres', '-d', 'source040', '-c', "ALTER SYSTEM SET ssl='on'",
                        '-c', "ALTER SYSTEM SET ssl_cert_file='/var/lib/postgresql/data/pgdata/server.crt'",
                        '-c', "ALTER SYSTEM SET ssl_key_file='/var/lib/postgresql/data/pgdata/server.key'",
                        '-c', 'SELECT pg_reload_conf()')
                    for attempt in range(30):
                        try:
                            restore.run('docker', 'exec', '-e', 'PGSSLMODE=require', name,
                                'psql', '-X', '-qAt', '-U', 'postgres', '-h', '127.0.0.1', '-d', 'source040', '-c', 'SELECT 1')
                            break
                        except RuntimeError:
                            if attempt == 29: raise
                            time.sleep(.5)
                    config.update(export_transport='tls_verify_full', export_tls_ca_file=str(cert),
                        export_tls_ca_sha256=backup.file_sha256(cert),
                        export_source_dsn='postgresql://postgres:synthetic-only@127.0.0.1:5432/source040?sslmode=verify-full&sslrootcert=/certs/source-ca.crt')
                with patch.object(backup, 'NAME', name):
                    dump, manifest = backup.consistent_export(config, Path(temp), 'synthetic-test')
                exported = json.loads((Path(temp) / 'export-synthetic-test/export/export-receipt.json').read_text())
                self.assertTrue(exported['shared_snapshot'])
                self.assertTrue(exported['sequence_state_unchanged_during_export'])
                self.assertEqual(exported['transport'], 'tls_verify_full' if tls else 'isolated_loopback')
                folder = Path(temp)
                approval = folder / 'restore-approval.private.json'
                approval.write_text(json.dumps({'explicit_authorization': True, 'scope': 'isolated_restore',
                    'production_mutation': False, 'dump_sha256': exported['dump_sha256'],
                    'manifest_sha256': exported['manifest_sha256'], 'profile': profile, 'postgres_major': 17,
                    'postgres_image_id': postgres, 'validator_api_image_id': validator}), encoding='utf-8')
                proof = restore.rehearse(dump, manifest, approval)
                self.assertTrue(proof['restoration_verified'])
                self.assertTrue(proof['source_contents_compared'])
                self.assertTrue(proof['owned_cleanup_verified'])
                self.assertGreater(proof['tables_verified'], 50)
                self.assertFalse(proof['production_mutation'])
            finally:
                if created: restore.cleanup('docker', name, token, 'none')


if __name__ == '__main__':
    unittest.main()
