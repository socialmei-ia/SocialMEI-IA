"""Read-only inspection or explicitly authorized private035 backup/restore for038.

No migration or runtime recreation. The only new containers are isolated restore
targets on network none, removed only after ownership verification.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tarfile
import time


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


operator = sibling('functional038_backup_operator', 'team-functional038-release.py')
schema = sibling('functional038_restore_schema', 'team-restore-schema.py')
require = operator.require
RESTORE_LABEL = 'socialmei.functional038.backup.restore'


def save_private(folder, name, value):
    require(Path(name).name == name, 'nome_privado_invalido')
    with (folder / name).open('x', encoding='utf-8') as stream:
        os.chmod(folder / name, 0o600)
        json.dump(value, stream, sort_keys=True, default=str)


def sql(container, database, query):
    result = operator.legacy.docker(
        'exec', container, 'psql', '-X', '-A', '-t', '-U', 'socialmei_team',
        '-d', database, '-v', 'ON_ERROR_STOP=1', '-c', query)
    return result.decode().strip()


def row_fingerprints(container, database, tables):
    result = {}
    for table in tables:
        require(re.fullmatch(r'[a-z_][a-z0-9_]*', table) is not None, 'tabela_invalida')
        value = sql(container, database,
                    "SELECT count(*),md5(COALESCE(string_agg(md5(to_jsonb(t)::text),"
                    "'' ORDER BY md5(to_jsonb(t)::text)),'')) "
                    'FROM socialmei."' + table + '" t')
        count, checksum = value.split('|')
        result[table] = [int(count), checksum]
    return result


def snapshot_program():
    # Executed inside the baseline API, using its configured DB access.
    return r'''
import json,re,signal,sys,psycopg
from settings import database_url
signal.alarm(300)
SCHEMA_QUERY = __SCHEMA_QUERY__
with psycopg.connect(database_url()) as conn:
    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    conn.execute("SET LOCAL statement_timeout='60s'")
    conn.execute('SET LOCAL search_path=pg_catalog')
    snapshot = conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
    tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='socialmei' ORDER BY tablename")]
    fingerprints = {}
    for table in tables:
        assert re.fullmatch(r'[a-z_][a-z0-9_]*',table)
        query = "SELECT count(*),md5(COALESCE(string_agg(md5(to_jsonb(t)::text),'' ORDER BY md5(to_jsonb(t)::text)),'')) FROM socialmei." + '"' + table + '" t'
        fingerprints[table] = list(conn.execute(query).fetchone())
    ledger = [r[0] for r in conn.execute('SELECT version FROM socialmei.schema_migrations ORDER BY version')]
    metadata = conn.execute(SCHEMA_QUERY).fetchone()[0]
    print(json.dumps({'snapshot':snapshot,'tables':tables,'fingerprints':fingerprints,'ledger':ledger,'schema':metadata}),flush=True)
    sys.stdin.read(1)
    conn.rollback()
'''.replace('__SCHEMA_QUERY__', repr(schema.SCHEMA_QUERY))


def validate_snapshot(snapshot):
    require(isinstance(snapshot, dict), 'snapshot_invalido')
    require(snapshot.get('ledger') == sorted(operator.profile.MIGRATIONS),
            'snapshot_ledger035_diverge')
    tables = snapshot.get('tables')
    require(isinstance(tables, list) and len(tables) == 71
            and tables == sorted(set(tables))
            and all(re.fullmatch(r'[a-z_][a-z0-9_]*', t) for t in tables),
            'snapshot_tabelas_divergem')
    require(isinstance(snapshot.get('schema'), dict)
            and sorted(snapshot['schema']) == schema.METADATA_GROUPS,
            'snapshot_metadata_incompleto')
    require(isinstance(snapshot.get('fingerprints'), dict)
            and set(snapshot['fingerprints']) == set(tables),
            'snapshot_fingerprints_incompletos')
    require(re.fullmatch(r'[0-9A-Fa-f]+-[0-9A-Fa-f]+-[0-9A-Fa-f]+',
                        str(snapshot.get('snapshot'))) is not None,
            'snapshot_identidade_invalida')


def restore_container_owned(name, token):
    container = operator.legacy.inspect(name)
    require(container['Config']['Labels'].get(RESTORE_LABEL) == token,
            'restore_container_nao_pertence_a_janela')
    require(container['HostConfig'].get('NetworkMode') == 'none',
            'restore_container_rede_divergente')
    return container


def release_snapshot(process):
    if process is None:
        return
    with contextlib.suppress(Exception):
        process.stdin.close()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)


def archive_private_configuration(folder, plans):
    expected = {}
    for plan in plans.values():
        for filename in plan['files']:
            expected['config/' + hashlib.sha256(filename.encode()).hexdigest()] = Path(filename)
        for filename in plan['mount_fingerprints']:
            root = Path(filename)
            prefix = 'mounts/' + hashlib.sha256(filename.encode()).hexdigest() + '/'
            if root.is_file():
                expected[prefix + '__file__'] = root
            else:
                for path in root.rglob('*'):
                    require(not path.is_symlink(), 'backup_mount_link_proibido')
                    if path.is_file():
                        expected[prefix + path.relative_to(root).as_posix()] = path
    with tarfile.open(folder / 'private-config.tar', 'x') as archive:
        for name, path in expected.items():
            archive.add(path, arcname=name, recursive=False)
    os.chmod(folder / 'private-config.tar', 0o600)
    operator.verify_private_archive(folder / 'private-config.tar', plans)


def create_backup(source, bundle, *, create=False, authorization=None):
    if create:
        require(authorization == operator.AUTHORIZATION,
                'autorizacao_backup_explicita_obrigatoria')
        require(os.name == 'posix' and os.geteuid() == 0, 'backup_exige_root_linux')
    plans, protected = operator.preflight(source, bundle)
    operator.no_external_senders(plans)
    if not create:
        return {'action': 'backup_inspect_passed', 'source_sha': operator.CANDIDATE_SHA,
                'backup_created': False, 'restore_verified': False,
                'production_runtime_changed': False, 'migrations_executed': False}
    private = operator.legacy.PRIVATE
    require(private.is_dir() and not private.is_symlink() and private.stat().st_uid == 0
            and stat.S_IMODE(private.stat().st_mode) & 0o022 == 0,
            'diretorio_privado_invalido')
    memory = re.search(r'^MemAvailable:\s+(\d+) kB$', Path('/proc/meminfo').read_text(), re.M)
    require(memory is not None and int(memory[1]) >= 384 * 1024,
            'memoria_insuficiente_para_restore')
    token = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + secrets.token_hex(6)
    folder = private / ('functional038-window-' + token)
    folder.mkdir(mode=0o700)
    snapshot_process = None
    target = None
    captured_unix = time.time()
    phase = 'snapshot035'
    try:
        save_private(folder, 'rollback-recipe.private.json', {'plans': plans, 'protected': protected})
        save_private(folder, 'rollback.public-files.json', {
            p: hashlib.sha256(operator.legacy.https('/frontend/' + p, 200)).hexdigest()
            for p in operator.legacy.STATIC_FILES})
        snapshot_process = subprocess.Popen(
            ['docker', '--host=unix:///var/run/docker.sock', 'exec', '-i',
             operator.legacy.API, 'python', '-u', '-c', snapshot_program()],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        line = snapshot_process.stdout.readline(16 * 1024**2)
        require(bool(line) and line.endswith(b'\n'), 'snapshot_export_failed')
        snapshot = json.loads(line)
        validate_snapshot(snapshot)
        save_private(folder, 'source-snapshot.private.json',
                     {key: value for key, value in snapshot.items() if key != 'snapshot'})
        phase = 'consistent035_dump'
        with (folder / 'postgres.dump').open('xb') as output:
            os.chmod(folder / 'postgres.dump', 0o600)
            dump = subprocess.run(
                ['docker', '--host=unix:///var/run/docker.sock', 'exec',
                 operator.legacy.POSTGRES, 'pg_dump', '-U', 'socialmei_team',
                 '-d', 'socialmei_team', '-Fc', '--snapshot=' + snapshot['snapshot']],
                stdout=output, stderr=subprocess.PIPE, timeout=180)
        require(dump.returncode == 0 and (folder / 'postgres.dump').stat().st_size > 0,
                'consistent_dump_failed')
        snapshot_process.stdin.close()
        snapshot_process.wait(timeout=15)
        require(snapshot_process.returncode == 0, 'snapshot_keeper_failed')
        snapshot_process = None
        with (folder / 'postgres.dump').open('rb') as stream:
            toc = subprocess.run(
                ['docker', '--host=unix:///var/run/docker.sock', 'exec', '-i',
                 operator.legacy.POSTGRES, 'pg_restore', '--list'],
                stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        require(toc.returncode == 0, 'dump_toc_invalid')
        with (folder / 'database-toc.private.txt').open('xb') as output:
            os.chmod(folder / 'database-toc.private.txt', 0o600)
            output.write(toc.stdout)
        phase = 'isolated035_restore'
        pg_image = operator.legacy.inspect(operator.legacy.POSTGRES)['Image']
        target = 'socialmei-functional038-restore-' + token.lower()
        operator.legacy.docker(
            'run', '-d', '--name', target, '--network', 'none', '--pull', 'never',
            '--memory', '256m', '--cpus', '0.5', '--pids-limit', '128',
            '--label', RESTORE_LABEL + '=' + token,
            '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_USER=socialmei_team',
            '-e', 'POSTGRES_DB=restorecheck', '-v', str(folder) + ':/backup:ro',
            pg_image, 'postgres', '-c', 'shared_buffers=16MB', '-c', 'max_connections=10',
            '-c', 'work_mem=1MB', '-c', 'maintenance_work_mem=16MB', timeout=60)
        restore_container_owned(target, token)
        for _ in range(60):
            try:
                if sql(target, 'restorecheck', 'SELECT 1') == '1':
                    break
            except operator.legacy.Blocked:
                pass
            time.sleep(1)
        else:
            require(False, 'isolated_postgres_not_ready')
        operator.legacy.docker('exec', target, 'pg_restore', '-U', 'socialmei_team',
                               '-d', 'restorecheck', '--exit-on-error', '--single-transaction',
                               '/backup/postgres.dump', timeout=180)
        require(row_fingerprints(target, 'restorecheck', snapshot['tables'])
                == snapshot['fingerprints'], 'restored_data_diverges')
        ledger = sql(target, 'restorecheck',
                     'SELECT version FROM socialmei.schema_migrations ORDER BY version').splitlines()
        require(ledger == snapshot['ledger'], 'restored_ledger_diverges')
        raw = sql(target, 'restorecheck', 'SET search_path=pg_catalog;' + schema.SCHEMA_QUERY)
        restored_schema = json.loads(next(value for value in raw.splitlines() if value.startswith('{')))
        require(schema.compare(snapshot['schema'], restored_schema),
                'restored_schema_or_constraints_diverge')
        save_private(folder, 'restore035.json', {
            'backup_sha256': operator.legacy.digest_file(folder / 'postgres.dump'),
            'ledger': ledger, 'restore_verified': True, 'isolated': True,
            'migrations_executed': False, 'production_runtime_changed': False,
            'table_count': len(snapshot['tables']), 'fingerprints_match': True,
            'schema_and_constraints_match': True, 'metadata_groups': sorted(snapshot['schema']),
            'validator': 'strict-two-reviewed-postgres-rewrites-v1',
            'consistent_exported_snapshot': True})
        restore_container_owned(target, token)
        operator.legacy.docker('rm', '-f', '-v', target)
        target = None
        phase = 'rollback_archives'
        with (folder / 'images-before.tar').open('xb') as output:
            os.chmod(folder / 'images-before.tar', 0o600)
            exported = subprocess.run(
                ['docker', '--host=unix:///var/run/docker.sock', 'save',
                 *[plan['container']['Config']['Image'] for plan in plans.values()]],
                stdout=output, stderr=subprocess.PIPE, timeout=300)
        require(exported.returncode == 0, 'rollback_image_export_failed')
        archive_private_configuration(folder, plans)
        operator.inputs_unchanged(plans, protected)
        receipt = {
            'source_sha': operator.CANDIDATE_SHA, 'baseline_sha': operator.BASE_SHA,
            'release_profile': '038', 'captured_unix': captured_unix,
            'sha256': {path.name: operator.legacy.digest_file(path)
                       for path in folder.iterdir() if path.is_file()},
            'runtime_fingerprints': {service: operator.runtime_fingerprint(plan['container'])
                                     for service, plan in plans.items()},
            'mount_fingerprints': {service: plan['mount_fingerprints']
                                   for service, plan in plans.items()}}
        save_private(folder, 'v01-backup-receipt.json', receipt)
        operator.backup_gate(folder, plans)
        return {'action': 'backup035_restore_verified', 'source_sha': operator.CANDIDATE_SHA,
                'backup': str(folder), 'backup_created': True,
                'dump_sha256': receipt['sha256']['postgres.dump'], 'restore_verified': True,
                'table_count': 71, 'ledger_count': 35, 'consistent_exported_snapshot': True,
                'schema_and_constraints_match': True, 'rollback_archives_verified': True,
                'production_runtime_changed': False, 'migrations_executed': False}
    except Exception:
        save_private(folder, 'backup-failed.json', {'phase': phase, 'passed': False,
                                                   'production_runtime_changed': False})
        raise
    finally:
        release_snapshot(snapshot_process)
        if target is not None:
            with contextlib.suppress(Exception):
                restore_container_owned(target, token)
                operator.legacy.docker('rm', '-f', '-v', target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--create-backup', action='store_true')
    parser.add_argument('--authorization')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = create_backup(args.source, args.bundle, create=args.create_backup,
                               authorization=args.authorization)
        print(json.dumps(result))
    except Exception as error:
        code = str(error) if isinstance(error, operator.legacy.Blocked) and re.fullmatch(r'[a-z0-9_]+', str(error)) else 'backup_gate_failed_details_redacted'
        print(json.dumps({'action': 'blocked', 'code': code,
                          'production_runtime_changed': False, 'migrations_executed': False}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
