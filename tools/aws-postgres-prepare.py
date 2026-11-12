#!/usr/bin/env python3
"""Explicit isolated PostgreSQL preparation. Never changes the live application or source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import urlsplit, parse_qs, quote

ROOT = Path('/home/ubuntu/.socialmei-postgres-relocation-20261112')
NAME = 'socialmei-postgres-relocation-20261112'
NETWORK = NAME + '-isolated'
API = 'socialmei-team-team-api-1'
BACKUP = Path('/home/ubuntu/.socialmei-instagram-86cdd5b/backup/prisma.dump')


def run(args, *, input_data=None, timeout=60, check=True):
    result = subprocess.run(args, input=input_data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('subprocess_failed_' + args[0])
    return result


def private_json(path, value):
    with path.open('w', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, indent=2)


def setup_root():
    if ROOT.is_symlink():
        raise RuntimeError('unsafe_workspace')
    ROOT.mkdir(mode=0o700, exist_ok=True)
    os.chmod(ROOT, 0o700)


def source_environment():
    obj = json.loads(run(['docker', 'inspect', API]).stdout)[0]
    values = dict(s.split('=', 1) for s in obj['Config']['Env'] if '=' in s)
    raw = values.get('DATABASE_URL')
    if raw:
        from urllib.parse import unquote
        url = urlsplit(raw)
        if not url.hostname or not url.hostname.endswith('.prisma.io'):
            raise RuntimeError('unexpected_source')
        env = {'PGHOST': url.hostname, 'PGPORT': str(url.port or 5432),
               'PGUSER': unquote(url.username or ''), 'PGPASSWORD': unquote(url.password or ''),
               'PGDATABASE': url.path.lstrip('/') or 'postgres',
               'PGSSLMODE': parse_qs(url.query).get('sslmode', ['require'])[0]}
    else:
        if not values.get('POSTGRES_HOST', '').endswith('.prisma.io'):
            raise RuntimeError('unexpected_source')
        env = {'PGHOST': values['POSTGRES_HOST'], 'PGPORT': values.get('POSTGRES_PORT', '5432'),
               'PGUSER': values['POSTGRES_USER'], 'PGPASSWORD': values['POSTGRES_PASSWORD'],
               'PGDATABASE': values['POSTGRES_DB'], 'PGSSLMODE': 'require'}
    env['PGCONNECT_TIMEOUT'] = '8'
    # Carry the live API's trusted CA bundle into the PostgreSQL client image.
    # Never weaken verify-full to work around certificate or provider failures.
    ca = ROOT / 'source-trusted-ca.crt'
    if not ca.exists():
        source_ca = values.get('SSL_CERT_FILE', '/etc/ssl/certs/ca-certificates.crt')
        run(['docker', 'cp', API + ':' + source_ca, str(ca)])
        os.chmod(ca, 0o600)
    env['PGSSLROOTCERT'] = '/run/socialmei-source-ca.crt'
    env['PGSSLMODE'] = 'verify-full'
    if any('\n' in v or '\r' in v for v in env.values()):
        raise RuntimeError('invalid_source_environment')
    path = ROOT / 'source.private.env'
    path.write_text(''.join(k + '=' + v + '\n' for k, v in env.items()))
    os.chmod(path, 0o600)
    return path


def export_source():
    setup_root()
    envfile = source_environment()
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    output = ROOT / ('source-' + stamp + '.dump')
    with output.open('xb') as stream:
        os.chmod(output, 0o600)
        result = subprocess.run(['docker', 'run', '--rm', '--network', 'container:' + API,
            '--memory', '128m', '--cpus', '0.25', '--env-file', str(envfile),
            '--mount', 'type=bind,src=' + str(ROOT / 'source-trusted-ca.crt') + ',dst=/run/socialmei-source-ca.crt,readonly', 'postgres:17',
            'pg_dump', '--format=custom', '--no-owner', '--no-acl'], stdout=stream,
            stderr=subprocess.PIPE, timeout=120)
    success = result.returncode == 0 and output.stat().st_size > 5
    (ROOT / 'export-errors.private.log').write_bytes(result.stderr)
    os.chmod(ROOT / 'export-errors.private.log', 0o600)
    reason = 'exported' if success else ('provider_account_limit' if b'planLimitReached' in result.stderr else 'export_unavailable')
    receipt = {'source_export_succeeded': success, 'reason': reason,
               'source_unchanged': True, 'cutover_executed': False,
               'dump_path': str(output), 'bytes': output.stat().st_size}
    if success:
        receipt['sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    private_json(ROOT / 'source-export-receipt.json', receipt)
    print(json.dumps(receipt))
    if not success:
        raise SystemExit(2)


def provision():
    setup_root()
    marker = ROOT / 'destination.private.json'
    if marker.exists():
        raise RuntimeError('destination_already_prepared_inspect_before_retry')
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
    if available < 320 * 1024 * 1024:
        raise RuntimeError('insufficient_memory_headroom')
    for command in (['docker', 'container', 'inspect', NAME], ['docker', 'network', 'inspect', NETWORK]):
        if run(command, check=False).returncode == 0:
            raise RuntimeError('resource_already_exists')
    image = json.loads(run(['docker', 'image', 'inspect', 'postgres:17']).stdout)[0]['Id']
    password = secrets.token_urlsafe(48)
    app_password = secrets.token_urlsafe(48)
    data = ROOT / 'data'
    if data.exists():
        raise RuntimeError('data_path_already_exists')
    data.mkdir(mode=0o700)
    os.chown(data, 999, 999)
    envfile = ROOT / 'destination.private.env'
    envfile.write_text('POSTGRES_USER=relocation_admin\nPOSTGRES_DB=socialmei_relocation\nPOSTGRES_PASSWORD=' + password + '\nPOSTGRES_INITDB_ARGS=--data-checksums --auth-host=scram-sha-256\n')
    os.chmod(envfile, 0o600)
    private_json(marker, {'container': NAME, 'network': NETWORK, 'image_id': image,
        'database': 'socialmei_relocation', 'admin_user': 'relocation_admin', 'admin_password': password,
        'app_user': 'socialmei_app', 'app_password': app_password})
    run(['docker', 'network', 'create', '--internal', '--label', 'socialmei.scope=database-relocation', NETWORK])
    run(['docker', 'run', '-d', '--name', NAME, '--label', 'socialmei.scope=database-relocation',
         '--restart', 'unless-stopped', '--network', NETWORK, '--memory', '192m', '--memory-swap', '256m',
         '--cpus', '0.35', '--pids-limit', '128', '--user', '999:999', '--read-only',
         '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
         '--tmpfs', '/tmp:rw,noexec,nosuid,size=32m',
         '--tmpfs', '/var/run/postgresql:rw,nosuid,size=8m,uid=999,gid=999,mode=3775',
         '--mount', 'type=bind,src=' + str(data) + ',dst=/var/lib/postgresql/data',
         '--env-file', str(envfile), image, 'postgres',
         '-c', 'shared_buffers=32MB', '-c', 'work_mem=1MB', '-c', 'maintenance_work_mem=32MB',
         '-c', 'max_connections=25', '-c', 'password_encryption=scram-sha-256',
         '-c', 'log_statement=none', '-c', 'log_min_error_statement=panic'])
    print(json.dumps({'destination_created': NAME, 'ports_published': False,
                      'network_internal': True, 'memory_limit_mib': 192, 'image_id': image,
                      'cutover_executed': False}))


def restore(portable=False):
    setup_root()
    config = json.loads((ROOT / 'destination.private.json').read_text())
    status = json.loads(run(['docker', 'inspect', NAME]).stdout)[0]
    if status['HostConfig'].get('PortBindings') or sorted(status['NetworkSettings']['Networks']) != [NETWORK]:
        raise RuntimeError('destination_isolation_invalid')
    receipt_path = ROOT / ('restore-portable-receipt.json' if portable else 'restore-receipt.json')
    if receipt_path.exists():
        raise RuntimeError('restore_already_recorded')
    # This fallback is deliberately an older snapshot, never called a live copy.
    receipt = json.loads((BACKUP.parent / 'backup-receipt.json').read_text())
    digest = hashlib.sha256(BACKUP.read_bytes()).hexdigest()
    if digest != receipt['backup_sha256'] or BACKUP.read_bytes()[:5] != b'PGDMP':
        raise RuntimeError('backup_integrity_invalid')
    args = ['docker', 'exec', '-i', NAME, 'pg_restore', '--username', config['admin_user'],
            '--dbname', config['database'], '--single-transaction', '--exit-on-error', '--no-owner', '--no-acl']
    omitted = []
    if portable:
        empty = run(['docker', 'exec', NAME, 'psql', '-XAt', '-U', config['admin_user'],
                     '-d', config['database'], '-c', "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')"]).stdout.strip()
        if empty != b'0':
            raise RuntimeError('destination_not_empty')
        with BACKUP.open('rb') as stream:
            listing = subprocess.run(['docker', 'exec', '-i', NAME, 'pg_restore', '--list'],
                stdin=stream, capture_output=True, timeout=30)
        if listing.returncode:
            raise RuntimeError('backup_toc_unavailable')
        lines = listing.stdout.decode().splitlines()
        for line in lines:
            if not line.startswith(';') and (' EXTENSION - prisma_postgres ' in line or
                                            ' COMMENT - EXTENSION prisma_postgres ' in line):
                omitted.append(line)
        if len(omitted) != 2:
            raise RuntimeError('unexpected_provider_extension_toc')
        filtered = '\n'.join(line for line in lines if line not in omitted) + '\n'
        run(['docker', 'exec', '-i', NAME, 'tee', '/tmp/relocation-restore.toc'], input_data=filtered.encode())
        args += ['--use-list', '/tmp/relocation-restore.toc']
    with BACKUP.open('rb') as stream:
        result = subprocess.run(args, stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    (ROOT / 'restore-errors.private.log').write_bytes(result.stderr)
    os.chmod(ROOT / 'restore-errors.private.log', 0o600)
    success = result.returncode == 0
    record = {'restore_succeeded': success, 'source': 'historical_prisma_snapshot',
              'source_snapshot_mtime_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(BACKUP.stat().st_mtime)),
              'dump_sha256': digest, 'schema_at_backup': receipt['schema'],
              'cutover_allowed': False, 'source_is_current': False,
              'provider_only_entries_omitted': len(omitted),
              'application_schema_migrations_executed': False}
    if not success:
        # No automatic SQL filtering, schema substitutions or partial retry.
        record['reason'] = 'restore_failed_review_private_log'
    private_json(receipt_path, record)
    print(json.dumps(record))
    if not success:
        raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', required=True)
    parser.add_argument('stage', choices=['export-source', 'provision', 'restore-historical', 'restore-portable'])
    args = parser.parse_args()
    try:
        {'export-source': export_source, 'provision': provision, 'restore-historical': restore,
         'restore-portable': lambda: restore(portable=True)}[args.stage]()
    except Exception as error:
        # Fixed errors only; subprocess stderr and connection strings stay private.
        allowed = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(json.dumps({'stage': args.stage, 'succeeded': False, 'reason': allowed,
                          'cutover_executed': False}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
