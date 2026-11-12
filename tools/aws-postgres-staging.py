#!/usr/bin/env python3
"""Secure and validate the isolated restored target, with all external sends disabled."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import quote

ROOT = Path('/home/ubuntu/.socialmei-postgres-relocation-20261112')
DB = 'socialmei-postgres-relocation-20261112'
NETWORK = DB + '-isolated'
API = 'socialmei-team-team-api-1'


def run(args, data=None, timeout=60):
    value = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if value.returncode:
        (ROOT / 'staging-errors.private.log').write_bytes(value.stderr)
        os.chmod(ROOT / 'staging-errors.private.log', 0o600)
        raise RuntimeError('staging_command_failed')
    return value.stdout


def save(path, value):
    path.write_text(json.dumps(value, indent=2))
    os.chmod(path, 0o600)


def psql(command):
    return run(['docker', 'exec', '-i', DB, 'psql', '-XAt', '-v', 'ON_ERROR_STOP=1',
                '-U', 'relocation_admin', '-d', 'socialmei_relocation'], command.encode())


def secure():
    cfg = json.loads((ROOT / 'destination.private.json').read_text())
    marker = ROOT / 'security-receipt.json'
    if marker.exists():
        raise RuntimeError('security_already_prepared')
    certs = ROOT / 'certificates'
    certs.mkdir(mode=0o700)
    run(['openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-days', '365',
         '-keyout', str(certs / 'ca.key'), '-out', str(certs / 'ca.crt'),
         '-subj', '/CN=SocialMEI isolated PostgreSQL CA'])
    run(['openssl', 'req', '-newkey', 'rsa:3072', '-nodes', '-keyout', str(certs / 'server.key'),
         '-out', str(certs / 'server.csr'), '-subj', '/CN=' + DB])
    ext = certs / 'server.ext'
    ext.write_text('subjectAltName=DNS:' + DB + '\nextendedKeyUsage=serverAuth\n')
    run(['openssl', 'x509', '-req', '-in', str(certs / 'server.csr'), '-CA', str(certs / 'ca.crt'),
         '-CAkey', str(certs / 'ca.key'), '-CAcreateserial', '-days', '365',
         '-out', str(certs / 'server.crt'), '-extfile', str(ext)])
    for file in certs.iterdir():
        os.chmod(file, 0o600)
    import shutil
    for name in ('server.key', 'server.crt'):
        dest = ROOT / 'data' / name
        shutil.copyfile(certs / name, dest)
        os.chown(dest, 999, 999)
        os.chmod(dest, 0o600)
    psql("ALTER SYSTEM SET ssl TO on;\nALTER SYSTEM SET ssl_cert_file TO '/var/lib/postgresql/data/server.crt';\nALTER SYSTEM SET ssl_key_file TO '/var/lib/postgresql/data/server.key';\nALTER SYSTEM SET ssl_min_protocol_version TO 'TLSv1.2';\n")
    password = cfg['app_password']
    assert all(c.isalnum() or c in '_-' for c in password)
    psql("CREATE ROLE socialmei_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '" + password + "';\n"
         "REVOKE CREATE ON SCHEMA public FROM PUBLIC;\n"
         "GRANT CONNECT ON DATABASE socialmei_relocation TO socialmei_app;\n"
         "GRANT USAGE ON SCHEMA socialmei,public TO socialmei_app;\n"
         "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA socialmei TO socialmei_app;\n"
         "GRANT USAGE,SELECT,UPDATE ON ALL SEQUENCES IN SCHEMA socialmei TO socialmei_app;\n")
    subnet = json.loads(run(['docker', 'network', 'inspect', NETWORK]))[0]['IPAM']['Config'][0]['Subnet']
    hba = ROOT / 'data/pg_hba.conf'
    original = ROOT / 'pg_hba.before.private.conf'
    shutil.copyfile(hba, original)
    os.chmod(original, 0o600)
    hba.write_text('local all relocation_admin trust\nlocal all all scram-sha-256\n'
                   'hostssl all relocation_admin ' + subnet + ' scram-sha-256\n'
                   'hostssl socialmei_relocation socialmei_app ' + subnet + ' scram-sha-256\n'
                   'hostnossl all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n')
    os.chown(hba, 999, 999)
    os.chmod(hba, 0o600)
    psql('SELECT pg_reload_conf();\n')
    time.sleep(1)
    receipt = {'tls_enabled': psql('SHOW ssl;').strip() == b'on',
        'app_superuser': psql("SELECT rolsuper FROM pg_roles WHERE rolname='socialmei_app';").strip() == b't',
        'host_auth_requires_tls': True, 'ports_published': False,
        'application_schema_changed': False, 'cutover_executed': False}
    if not receipt['tls_enabled'] or receipt['app_superuser']:
        raise RuntimeError('target_security_gate_failed')
    save(marker, receipt)
    print(json.dumps(receipt))


def configure():
    cfg = json.loads((ROOT / 'destination.private.json').read_text())
    if not (ROOT / 'security-receipt.json').exists():
        raise RuntimeError('target_security_not_verified')
    security = json.loads((ROOT / 'security-receipt.json').read_text())
    if not security.get('tls_enabled') or security.get('app_superuser') is not False:
        raise RuntimeError('target_security_not_verified')
    sources = {'api': API, 'whatsapp-menu': 'socialmei-menu-public-api-v3',
               'instagram-worker': 'socialmei-instagram-menu-worker', 'recovery-worker': API}
    catalog = {}
    for kind, source in sources.items():
        obj = json.loads(run(['docker', 'inspect', source]))[0]
        save(ROOT / (kind + '-production-before.private.json'), obj)
        env = dict(s.split('=', 1) for s in obj['Config']['Env'] if '=' in s)
        env['DATABASE_URL'] = ('postgresql://' + cfg['app_user'] + ':' + quote(cfg['app_password'], safe='') +
            '@' + DB + ':5432/' + cfg['database'] + '?sslmode=verify-full&sslrootcert=/run/socialmei/database-ca.crt')
        env.update({'SOCIALMEI_INSTAGRAM_RUNTIME_MODE': 'disabled',
            'SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED': 'false', 'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED': 'false',
            'SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED': 'false', 'SOCIALMEI_INSTAGRAM_TOKEN_REFRESH_ENABLED': 'false',
            'SOCIALMEI_WHATSAPP_BOT_ENABLED': 'false', 'SOCIALMEI_WAHA_INGRESS_MODE': 'disabled',
            'SOCIALMEI_RECOVERY_MODE': 'disabled', 'SOCIALMEI_PROVIDER_SENTIMENT_ENABLED': 'false',
            'SOCIALMEI_AI_DRAFT_ENABLED': 'false', 'SOCIALMEI_AUTH_ORIGIN': 'https://staging-db.socialmei.invalid',
            'SOCIALMEI_MENU_SENDER_ACTIVE': 'NO', 'SOCIALMEI_PUBLIC_MENU_EXPLICIT_ENABLE': 'NO'})
        if any('\n' in value or '\r' in value for value in env.values()):
            raise RuntimeError('multiline_environment_requires_private_adapter')
        path = ROOT / (kind + '-staging.private.env')
        path.write_text(''.join(key + '=' + value + '\n' for key, value in env.items()))
        os.chmod(path, 0o600)
        catalog[kind] = {'image_id': obj['Image'], 'env_file': str(path),
            'database': cfg['database'], 'network': NETWORK, 'sends_enabled': False,
            'planned_command': ['python', 'recovery_worker.py', '--run', '--watch'] if kind == 'recovery-worker' else obj['Config']['Cmd'],
            'production_mounts_not_reused': True}
    save(ROOT / 'staging-manifest.private.json', catalog)
    print(json.dumps({'staging_consumers_configured': sorted(catalog), 'same_database_url': True,
                      'outbound_network': False, 'workers_started': False, 'cutover_executed': False}))


def base_args(kind, name=None):
    catalog = json.loads((ROOT / 'staging-manifest.private.json').read_text())
    args = ['docker', 'run', '--rm', '-i', '--network', NETWORK,
            '--memory', '160m', '--memory-swap', '224m', '--cpus', '0.35', '--pids-limit', '96',
            '--security-opt', 'no-new-privileges', '--cap-drop', 'ALL',
            '--env-file', catalog[kind]['env_file'],
            '--mount', 'type=bind,src=' + str(ROOT / 'certificates/ca.crt') + ',dst=/run/socialmei/database-ca.crt,readonly',
            '--mount', 'type=bind,src=' + str(ROOT / 'tools') + ',dst=/maintenance,readonly',
            '--mount', 'type=bind,src=' + str(ROOT / 'validation') + ',dst=/validation',
            '--entrypoint', 'python']
    if name:
        args += ['--name', name]
    return args + [catalog[kind]['image_id']]


def probe():
    (ROOT / 'validation').mkdir(mode=0o700, exist_ok=True)
    results = {}
    code = b"""import json
from database import connect
with connect() as conn:
    conn.execute('SET TRANSACTION READ ONLY')
    row=conn.execute("SELECT current_database(),inet_server_addr()::text,pg_is_in_recovery(),(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())").fetchone()
    conn.rollback()
print(json.dumps({'database':row[0],'server_ip':row[1],'in_recovery':row[2],'tls':row[3]}))
"""
    for kind in ('api', 'whatsapp-menu', 'instagram-worker', 'recovery-worker'):
        results[kind] = json.loads(run(base_args(kind) + ['-'], code))
    same = len({(value['database'], value['server_ip']) for value in results.values()}) == 1
    receipt = {'consumers': results, 'same_effective_database': same,
               'all_tls': all(value['tls'] for value in results.values()),
               'provider_sends': 0, 'cutover_executed': False}
    if not receipt['same_effective_database'] or not receipt['all_tls']:
        raise RuntimeError('consumer_database_gate_failed')
    save(ROOT / 'consumer-connection-receipt.json', receipt)
    print(json.dumps(receipt))


def snapshot():
    filename = 'target-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '.private.json'
    output = run(base_args('api') + ['/maintenance/postgres-copy-validate.py', '--output', '/validation/' + filename], timeout=120)
    save(ROOT / 'validation/latest-target.private.json', {'manifest': filename})
    print(output.decode().strip())


def restore_check():
    cfg = json.loads((ROOT / 'destination.private.json').read_text())
    stamp = time.strftime('%Y%m%d%H%M%S', time.gmtime())
    name = 'socialmei_restore_check_' + stamp
    if psql("SELECT 1 FROM pg_database WHERE datname='" + name + "';").strip():
        raise RuntimeError('restore_check_database_already_exists')
    psql('CREATE DATABASE ' + name + ' OWNER relocation_admin;')
    receipts = sorted((ROOT / 'backups').glob('destination-*.json'))
    if not receipts:
        raise RuntimeError('destination_backup_missing')
    metadata = json.loads(receipts[-1].read_text())
    backup = Path(metadata['dump_path'])
    import hashlib
    if (backup.is_symlink() or backup.parent.resolve() != (ROOT / 'backups').resolve()
            or hashlib.sha256(backup.read_bytes()).hexdigest() != metadata['sha256']):
        raise RuntimeError('destination_backup_integrity_invalid')
    with backup.open('rb') as stream:
        value = subprocess.run(['docker', 'exec', '-i', DB, 'pg_restore', '-U', 'relocation_admin',
            '-d', name, '--single-transaction', '--exit-on-error', '--no-owner', '--no-acl'],
            stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if value.returncode:
        raise RuntimeError('restore_check_failed')
    # A separate administrative probe validates the restored archive without changing rows.
    original = (ROOT / 'api-staging.private.env').read_text()
    lines = []
    for line in original.splitlines():
        if line.startswith('DATABASE_URL='):
            line = ('DATABASE_URL=postgresql://relocation_admin:' + quote(cfg['admin_password'], safe='') +
                    '@' + DB + ':5432/' + name + '?sslmode=verify-full&sslrootcert=/run/socialmei/database-ca.crt')
        lines.append(line)
    envfile = ROOT / 'restore-check.private.env'
    envfile.write_text('\n'.join(lines) + '\n')
    os.chmod(envfile, 0o600)
    args = base_args('api')
    args[args.index('--env-file') + 1] = str(envfile)
    restored_manifest = 'restore-check-' + stamp + '.private.json'
    run(args + ['/maintenance/postgres-copy-validate.py', '--output', '/validation/' + restored_manifest], timeout=120)
    import importlib.util
    spec = importlib.util.spec_from_file_location('copy_validator', ROOT / 'tools/postgres-copy-validate.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    latest = json.loads((ROOT / 'validation/latest-target.private.json').read_text())['manifest']
    if Path(latest).name != latest:
        raise RuntimeError('unsafe_manifest_path')
    first = json.loads((ROOT / 'validation' / latest).read_text())
    second = json.loads((ROOT / 'validation' / restored_manifest).read_text())
    comparison = validator.compare(first, second)
    receipt = {'comparison': comparison, 'tables': len(first['tables']),
               'total_rows': sum(table['rows'] for table in first['tables']),
               'foreign_keys_checked': len(first['foreign_keys']),
               'foreign_key_violations': sum(row['violations'] for row in first['foreign_keys']),
               'sequences_checked': len(first['sequences']),
               'large_objects': first['large_objects'],
               'historical_snapshot_only': True, 'production_freshness_verified': False}
    if not comparison['equal'] or receipt['foreign_key_violations']:
        save(ROOT / 'restore-validation-failed.private.json', receipt)
        raise RuntimeError('restore_integrity_gate_failed')
    save(ROOT / 'restore-validation-receipt.json', receipt)
    print(json.dumps(receipt))


def api_smoke():
    # Actual installed application against the destination; no providers or synthetic rows.
    code = b"""import json
from fastapi.testclient import TestClient
from app import app
with TestClient(app) as client:
    results={path: client.get(path).status_code for path in ('/health','/health/db','/api/v1/auth/session','/api/v1/clientes')}
print(json.dumps({'http_statuses':results,'provider_sends':0,'authenticated_write_tests_executed':False}))
"""
    result = json.loads(run(base_args('api') + ['-'], code, timeout=90))
    if result['http_statuses'] != {'/health': 200, '/health/db': 200,
                                  '/api/v1/auth/session': 200, '/api/v1/clientes': 401}:
        raise RuntimeError('api_smoke_gate_failed')
    save(ROOT / 'api-smoke-receipt.json', result)
    print(json.dumps(result))


def tls_negative():
    code = b"""import json
import psycopg
from settings import database_url
rejected=False
try:
    connection=psycopg.connect(database_url().replace('sslmode=verify-full','sslmode=disable'),connect_timeout=5)
    connection.close()
except psycopg.Error as error:
    rejected=('pg_hba.conf rejects connection' in str(error) and 'no encryption' in str(error))
print(json.dumps({'plaintext_connection_rejected':rejected}))
"""
    result = json.loads(run(base_args('api') + ['-'], code))
    if result.get('plaintext_connection_rejected') is not True:
        raise RuntimeError('plaintext_connection_rejection_not_verified')
    save(ROOT / 'tls-negative-receipt.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', required=True)
    parser.add_argument('stage', choices=['secure', 'configure', 'probe', 'snapshot', 'restore-check', 'api-smoke', 'tls-negative'])
    args = parser.parse_args()
    try:
        {'secure': secure, 'configure': configure, 'probe': probe, 'snapshot': snapshot,
         'restore-check': restore_check, 'api-smoke': api_smoke, 'tls-negative': tls_negative}[args.stage]()
    except Exception:
        raise SystemExit('Isolated staging step unavailable; inspect private receipt. No production change.') from None
