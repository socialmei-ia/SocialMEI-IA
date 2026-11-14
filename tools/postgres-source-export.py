#!/usr/bin/env python3
"""Opt-in current-source export; never activates provider access or switches databases."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def validator():
    spec = importlib.util.spec_from_file_location(
        'copy_validator', Path(__file__).with_name('postgres-copy-validate.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_environment(dsn):
    from psycopg.conninfo import conninfo_to_dict
    values = conninfo_to_dict(dsn)
    mappings = {'host': 'PGHOST', 'port': 'PGPORT', 'dbname': 'PGDATABASE',
                'user': 'PGUSER', 'password': 'PGPASSWORD', 'sslmode': 'PGSSLMODE',
                'sslrootcert': 'PGSSLROOTCERT', 'sslcert': 'PGSSLCERT',
                'sslkey': 'PGSSLKEY', 'channel_binding': 'PGCHANNELBINDING',
                'connect_timeout': 'PGCONNECT_TIMEOUT', 'application_name': 'PGAPPNAME'}
    if (not all(values.get(key) for key in ('host', 'dbname', 'user', 'password', 'sslrootcert'))
            or values.get('sslmode') != 'verify-full'
            or '/' in values.get('host', '')
            or set(values) - mappings.keys()):
        raise ValueError('Explicit TLS-verified source required')
    # Do not inherit another PG service, password, host or connection from the operator.
    env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    env.update({mappings[key]: value for key, value in values.items()})
    env.update(PGCONNECT_TIMEOUT='8', PGOPTIONS='-c default_transaction_read_only=on')
    return env


def private_directory(path):
    if os.name != 'posix':
        raise ValueError('Execute only on a private POSIX operational host')
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink() or (parent / '.git').exists():
            raise ValueError('Private output must be outside Git and symlinks')
    path.mkdir(mode=0o700)  # A new directory is required; never reuse an old dump.
    if path.stat().st_mode & 0o077:
        raise ValueError('Private output permissions required')
    return path


def source_identity(env):
    identity = [env['PGHOST'], int(env.get('PGPORT', '5432')), env['PGDATABASE']]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def export(dsn, directory, *, expected_identity, pg_dump='pg_dump', pg_restore='pg_restore', timeout=1800):
    """Caller must have explicit permission to export real data before calling."""
    import psycopg
    env = source_environment(dsn)
    identity = source_identity(env)
    if identity != expected_identity:
        raise ValueError('Source does not match the inventoried application database')
    for binary in (pg_dump, pg_restore):
        result = subprocess.run([binary, '--version'], capture_output=True, timeout=10, check=True)
        if not re.search(r'\(PostgreSQL\) 17\.\d+\b', result.stdout.decode()):
            raise ValueError('PostgreSQL 17 client required')
    directory = private_directory(directory)
    check = validator()
    partial = directory / 'source.dump.partial'
    with psycopg.connect(dsn, connect_timeout=8, application_name='socialmei-source-export') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout = '120s'")
        if conn.info.server_version // 10000 != 17:
            raise ValueError('Source server version requires review')
        snapshot_id = conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
        manifest = check.snapshot(dsn, exported_snapshot=snapshot_id)
        if manifest.get('valid') is not True:
            raise ValueError('Source integrity validation failed')
        with partial.open('xb') as stream:
            os.chmod(partial, 0o600)
            subprocess.run([pg_dump, '--format=custom', '--no-owner', '--no-acl',
                            '--no-password', '--lock-wait-timeout=5s',
                            '--snapshot=' + snapshot_id], env=env, stdout=stream,
                           stderr=subprocess.PIPE, timeout=timeout, check=True)
            stream.flush()
            os.fsync(stream.fileno())
        with partial.open('rb') as stream:
            if stream.read(5) != b'PGDMP':
                raise ValueError('Invalid archive')
        subprocess.run([pg_restore, '--list', str(partial)], capture_output=True,
                       timeout=60, check=True)
        conn.rollback()
    dump = directory / 'source.dump'
    partial.rename(dump)
    manifest_path = directory / 'source-manifest.private.json'
    check.private_json(manifest_path, manifest)
    receipt = {'source_export_succeeded': True, 'dump_sha256': sha256(dump),
               'manifest_sha256': sha256(manifest_path), 'shared_snapshot': True,
               'source_database_fingerprint': identity,
               'writers_quiescence_verified': False, 'restoration_verified': False,
               'external_backup_verified': False, 'cutover_authorized': False}
    check.private_json(directory / 'export-receipt.json', receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--approved-data-export', action='store_true')
    parser.add_argument('--output-directory')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps({'mode': 'plan', 'connections': 0,
                          'requires': ['explicit export approval', 'current source DSN in private environment',
                                       'inventoried source fingerprint in private environment',
                                       'PostgreSQL 17 clients', 'new private directory outside Git'],
                          'activates_recovery_window': False, 'cutover_authorized': False}))
        return 0
    if not args.approved_data_export or not args.output_directory:
        parser.error('--run requires --approved-data-export and --output-directory')
    try:
        # No DATABASE_URL fallback: an operator must identify the real source deliberately.
        print(json.dumps(export(os.environ['SOCIALMEI_EXPORT_SOURCE_DSN'], args.output_directory,
                                expected_identity=os.environ['SOCIALMEI_EXPORT_SOURCE_FINGERPRINT'])))
        return 0
    except Exception:
        # Never print driver errors, command environments, DSNs or archive contents.
        print('Export unavailable. Preserve partial files; review source access and private prerequisites. No automatic retry.',
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
