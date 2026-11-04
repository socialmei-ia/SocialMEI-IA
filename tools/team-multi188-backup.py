"""Read-only inspection or explicitly authorized private038 backup/restore for multi188.

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


operator = sibling('multi188_backup_operator', 'team-multi188-release.py')
schema = sibling('multi188_restore_schema', 'team-restore-schema.py')
require = operator.require
RESTORE_LABEL = 'socialmei.multi188.backup.restore'
WINDOW_LOCK = '/run/lock/socialmei-wa-pilot-release.lock'


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


def sequence_toc(folder, content, expected_names):
    # Sequence values are not MVCC: validate the values stored in this exact dump.
    names = set(expected_names)
    require(names and all(re.fullmatch(r'[a-z_][a-z0-9_]*', name) for name in names),
            'sequence_names_invalid')
    rows = []
    seen = set()
    for line in content.decode().splitlines():
        if ' SEQUENCE SET ' not in line or line.startswith(';'):
            continue
        match = re.fullmatch(r'\d+; \d+ \d+ SEQUENCE SET socialmei ([a-z_][a-z0-9_]*) \S+', line)
        require(match is not None and match[1] in names and match[1] not in seen,
                'dump_sequence_toc_invalid')
        seen.add(match[1])
        rows.append(line)
    require(seen == names, 'dump_sequence_toc_incomplete')
    path = folder / 'sequence-toc.private.txt'
    with path.open('x', encoding='utf-8') as output:
        os.chmod(path, 0o600)
        output.write('\n'.join(rows) + '\n')


def verify_sequence_states(target, expected_names):
    output = operator.legacy.docker(
        'exec', target, 'pg_restore', '--use-list=/backup/sequence-toc.private.txt',
        '--file=-', '/backup/postgres.dump').decode()
    dumped = {}
    for name, value, called in re.findall(
            r"SELECT pg_catalog\.setval\('socialmei\.([a-z_][a-z0-9_]*)', (-?\d+), (true|false)\);",
            output):
        require(name not in dumped, 'dump_sequence_state_duplicated')
        dumped[name] = [int(value), called == 'true']
    require(set(dumped) == set(expected_names), 'dump_sequence_states_incomplete')
    for name, expected in dumped.items():
        require(re.fullmatch(r'[a-z_][a-z0-9_]*', name) is not None, 'sequence_name_invalid')
        row = sql(target, 'restorecheck',
                  'SELECT last_value,is_called FROM socialmei."' + name + '"').split('|')
        require(len(row) == 2 and [int(row[0]), row[1] == 't'] == expected,
                'restored_sequence_state_diverges')
    return True


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
    require(snapshot.get('ledger') == sorted(operator.profile.MIGRATIONS038),
            'snapshot_ledger038_diverge')
    tables = snapshot.get('tables')
    require(isinstance(tables, list) and len(tables) == 74
            and tables == sorted(set(tables))
            and all(re.fullmatch(r'[a-z_][a-z0-9_]*', t) for t in tables),
            'snapshot_tabelas_divergem')
    require({'users', 'workspaces', 'workspace_members', 'auth_credenciais', 'auth_sessoes'} <= set(tables),
            'snapshot_accounts_memberships_missing')
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
    if not create:
        return _create_backup_locked(source, bundle, create=False, authorization=authorization)
    require(authorization == operator.AUTHORIZATION,
            'autorizacao_backup_explicita_obrigatoria')
    require(os.name == 'posix' and os.geteuid() == 0, 'backup_exige_root_linux')
    with open(WINDOW_LOCK, 'a') as lock:
        try:
            operator.legacy.fcntl.flock(
                lock, operator.legacy.fcntl.LOCK_EX | operator.legacy.fcntl.LOCK_NB)
        except BlockingIOError:
            require(False, 'outra_janela_operacional_em_execucao')
        try:
            return _create_backup_locked(source, bundle, create=True, authorization=authorization)
        finally:
            operator.legacy.fcntl.flock(lock, operator.legacy.fcntl.LOCK_UN)


def _create_backup_locked(source, bundle, *, create=False, authorization=None):
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
    folder = private / ('multi188-window-' + token)
    folder.mkdir(mode=0o700)
    snapshot_process = None
    target = None
    captured_unix = time.time()
    phase = 'snapshot038'
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
        phase = 'consistent038_dump'
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
        sequence_names = [entry['name'] for entry in snapshot['schema']['sequences']]
        sequence_toc(folder, toc.stdout, sequence_names)
        phase = 'isolated038_restore'
        pg_image = operator.legacy.inspect(operator.legacy.POSTGRES)['Image']
        target = 'socialmei-multi188-restore-' + token.lower()
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
        require(sql(target, 'restorecheck', "SELECT current_setting('server_version_num')::int/10000") == '16',
                'restore_requires_postgres16')
        verify_sequence_states(target, sequence_names)
        save_private(folder, 'restore038.json', {
            'backup_sha256': operator.legacy.digest_file(folder / 'postgres.dump'),
            'ledger': ledger, 'restore_verified': True, 'isolated': True,
            'migrations_executed': False, 'production_runtime_changed': False,
            'table_count': len(snapshot['tables']), 'fingerprints_match': True,
            'schema_and_constraints_match': True, 'metadata_groups': sorted(snapshot['schema']),
            'sequence_states_match': True, 'accounts_memberships_match': True,
            'sequence_state_scope': 'exact_dump_sequence_set_not_mvcc_snapshot',
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
        save_private(folder, 'multi188-backup-receipt.json', receipt)
        operator.backup_gate(folder, plans)
        return {'action': 'backup038_restore_verified', 'source_sha': operator.CANDIDATE_SHA,
                'backup': str(folder), 'backup_created': True,
                'dump_sha256': receipt['sha256']['postgres.dump'], 'restore_verified': True,
                'table_count': 74, 'ledger_count': 38, 'consistent_exported_snapshot': True,
                'schema_and_constraints_match': True, 'rollback_archives_verified': True,
                'sequence_states_match': True, 'accounts_memberships_match': True,
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
