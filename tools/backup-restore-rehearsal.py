#!/usr/bin/env python3
"""Default plan; explicit approval required for local, network-none dump restoration.

No S3, external DSN, migration, production container, host data volume or apply
option. Restore only to a new owned container; emit no rows, DDL or credentials.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('copy_manifest', ROOT / 'tools/postgres-copy-validate.py')
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)
API_IMAGE = 'sha256:0a7050f73cab2b06b89b5b91fc0232c92fd0b41b029ac9710518d5255ca8a569'


def require(ok):
    if not ok:
        raise ValueError('isolated_restore_precondition_failed')


def file_hash(path):
    require(path.is_file() and not any(item.is_symlink() for item in (path, *path.parents)))
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def inputs(dump, manifest, approval):
    for path in (dump, manifest, approval):
        require(path is not None)
        file_hash(path)
    require(approval.stat().st_size < 32768 and manifest.stat().st_size < 64 * 1024**2)
    auth = json.loads(approval.read_text(encoding='utf-8-sig'))
    expected = json.loads(manifest.read_text(encoding='utf-8-sig'))
    require(auth.get('explicit_authorization') is True and auth.get('scope') == 'isolated_restore'
            and auth.get('production_mutation') is False
            and auth.get('dump_sha256') == file_hash(dump)
            and auth.get('manifest_sha256') == file_hash(manifest)
            and auth.get('profile') in ('038', '039', '040', '041')
            and auth.get('postgres_major') in (16, 17)
            and re.fullmatch(r'sha256:[0-9a-f]{64}', str(auth.get('postgres_image_id'))) is not None)
    with dump.open('rb') as stream:
        require(stream.read(5) == b'PGDMP')
    validator.compare(expected, expected)
    require(expected.get('valid') is True)
    versions = next((row['versions'] for row in expected['migration_ledger'] if row.get('schema') == 'socialmei'), [])
    require(len(versions) == int(auth['profile']) and [name[:3] for name in versions] ==
            [f'{index:03}' for index in range(1, int(auth['profile']) + 1)])
    require(auth.get('verification_mode', 'full_comparison') in ('full_comparison', 'archive_integrity'))
    require(auth.get('verification_mode') != 'archive_integrity' or auth['profile'] in ('040', '041'))
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', str(auth.get('validator_api_image_id', API_IMAGE))) is not None)
    if auth.get('external_receipt_file') is not None:
        external_path = Path(auth['external_receipt_file'])
        require(external_path.is_file() and external_path.stat().st_size <= 32768)
        require(file_hash(external_path) == auth.get('external_receipt_sha256'))
        external = json.loads(external_path.read_text(encoding='utf-8-sig'))
        version = external.get('external_version_id')
        require(external.get('external_uploaded') is True
                and external.get('sha256') == auth['dump_sha256']
                and external.get('external_object_sha256') == auth['dump_sha256']
                and external.get('bytes') == dump.stat().st_size
                and isinstance(version, str) and 0 < len(version) <= 1024 and version != 'null'
                and all(33 <= ord(char) <= 126 for char in version))
        auth['_verified_external_version_id'] = version
    return auth, expected


def verify_manifest(expected, restored, mode='full_comparison'):
    comparison = validator.compare(expected, restored)
    if mode == 'full_comparison':
        require(comparison['equal'])
    else:
        require(mode == 'archive_integrity' and expected['valid'] is True and restored['valid'] is True)
        # Production rows evolve. Verify the restored archive against the approved
        # immutable schema, not against historical customer contents/counts.
        require(validator.comparable_structure(expected['structure']) ==
                validator.comparable_structure(restored['structure']))
        require([(row['schema'], row['table']) for row in expected['tables']] ==
                [(row['schema'], row['table']) for row in restored['tables']])
        require(expected['migration_ledger'] == restored['migration_ledger'])
        require([{key: row[key] for key in ('schema', 'sequence', 'definition')} for row in expected['sequences']] ==
                [{key: row[key] for key in ('schema', 'sequence', 'definition')} for row in restored['sequences']])
        require(expected['foreign_keys'] == restored['foreign_keys'])
    return {'verification_mode': mode, 'source_contents_compared': mode == 'full_comparison',
            'sequence_state_compared_to_reference': mode == 'full_comparison',
            'sequence_max_value_safety_verified': False,
            'restored_rows': sum(row['rows'] for row in restored['tables']),
            'archive_integrity_verified': True}


def run(docker, *args, stdin=None, timeout=180):
    result = subprocess.run([docker, *args], stdin=stdin, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('isolated_restore_command_failed')
    return result.stdout


def cleanup(docker, name, token, network):
    owned = json.loads(run(docker, 'inspect', name))
    require(len(owned) == 1 and owned[0]['Config']['Labels'].get('socialmei.isolated-restore') == token
            and owned[0]['HostConfig']['NetworkMode'] == network)
    run(docker, 'rm', '-f', '-v', name)


def rehearse(dump, manifest, approval, docker='docker'):
    auth, expected = inputs(dump, manifest, approval)
    require(not os.environ.get('DOCKER_HOST') or os.environ['DOCKER_HOST'].startswith(('unix://', 'npipe://')))
    context = json.loads(run(docker, 'context', 'inspect'))
    require(len(context) == 1 and context[0]['Endpoints']['docker']['Host'].startswith(('unix://', 'npipe://')))
    image = auth['postgres_image_id']
    validator_image = auth.get('validator_api_image_id', API_IMAGE)
    for identity in (image, validator_image):
        info = json.loads(run(docker, 'image', 'inspect', identity))
        require(len(info) == 1 and info[0]['Id'] == identity)
    token = secrets.token_hex(12)
    name = 'socialmei-approved-restore-' + token
    label = 'socialmei.isolated-restore=' + token
    created = []
    try:
        # Create first: cleanup ownership is known even if startup later fails.
        created.append((name, 'none'))
        identity = run(docker, 'create', '--name', name, '--label', label, '--network', 'none',
            '--user', 'postgres', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--memory', '512m', '--cpus', '0.5', '--pids-limit', '128', '--restart', 'no',
            '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,noexec,size=512m,mode=1777',
            '--tmpfs', '/var/run/postgresql:rw,nosuid,noexec,size=16m,mode=1777',
            '--tmpfs', '/tmp:rw,nosuid,noexec,size=16m,mode=1777',
            '-e', 'PGDATA=/var/lib/postgresql/data/pgdata', '-e', 'POSTGRES_USER=restore',
            '-e', 'POSTGRES_DB=restore', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', image).decode().strip()
        require(re.fullmatch(r'[0-9a-f]{64}', identity) is not None)
        run(docker, 'start', identity)
        for attempt in range(60):
            try:
                # The image's temporary init server accepts Unix sockets only.
                # Wait for final TCP readiness before loading data/starting validation.
                run(docker, 'exec', identity, 'pg_isready', '-h', '127.0.0.1', '-U', 'restore', timeout=5)
                break
            except RuntimeError:
                if attempt == 59:
                    raise
                time.sleep(.5)
        actual_version = run(docker, 'exec', identity, 'postgres', '--version').decode()
        require(re.search(r'PostgreSQL\) ' + str(auth['postgres_major']) + r'\.', actual_version) is not None)
        for command in (('pg_restore', '--list'), ('pg_restore', '-U', 'restore', '-d', 'restore',
                         '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges')):
            with dump.open('rb') as stream:
                run(docker, 'exec', '-i', identity, *command, stdin=stream)
        code = ("import importlib.util,json; s=importlib.util.spec_from_file_location('v','/validator.py');"
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                "print(json.dumps(m.snapshot('postgresql://restore@127.0.0.1:5432/restore')))")
        check_name = name + '-check'
        created.append((check_name, 'container:' + identity))
        check_id = run(docker, 'create', '--name', check_name, '--label', label, '--network', 'container:' + identity,
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--memory', '256m', '--cpus', '0.5', '--pids-limit', '64',
            '--mount', 'type=bind,src=' + str(ROOT / 'tools/postgres-copy-validate.py') + ',dst=/validator.py,readonly',
            '--entrypoint', 'python', validator_image, '-B', '-c', code).decode().strip()
        require(re.fullmatch(r'[0-9a-f]{64}', check_id) is not None)
        result = json.loads(run(docker, 'start', '-a', check_id))
        verification = verify_manifest(expected, result, auth.get('verification_mode', 'full_comparison'))
        comparison = validator.compare(expected, result)
        require(file_hash(dump) == auth['dump_sha256'] and file_hash(manifest) == auth['manifest_sha256'])
        if '_verified_external_version_id' in auth:
            require(file_hash(Path(auth['external_receipt_file'])) == auth['external_receipt_sha256'])
        proof = {'profile': auth['profile'], 'dump_sha256': auth['dump_sha256'],
                 'manifest_sha256': auth['manifest_sha256'], 'restoration_verified': True,
                 'tables_verified': len(result['tables']), 'sequences_verified': len(result['sequences']),
                 'effective_permissions_equal': comparison['effective_permissions_equal'],
                 'effective_sequence_permissions_equal': comparison['effective_sequence_permissions_equal'],
                 'production_role_permissions_approved': False, 'migrations_executed': False,
                 'production_mutation': False, 'source_freshness_verified': False}
        proof.update(verification)
        if '_verified_external_version_id' in auth:
            proof.update(external_version_id=auth['_verified_external_version_id'],
                         external_object_sha256=auth['dump_sha256'],
                         external_receipt_sha256=auth['external_receipt_sha256'])
        proof['validator_api_image_id'] = validator_image
    finally:
        cleanup_errors = []
        for resource, network in reversed(created):
            try:
                cleanup(docker, resource, token, network)
            except Exception:
                cleanup_errors.append(resource)
        if cleanup_errors:
            raise RuntimeError('owned_restore_cleanup_unverified')
    proof['owned_cleanup_verified'] = True
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--dump', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--approval-receipt', type=Path)
    parser.add_argument('--docker', default='docker')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps({'mode': 'plan', 'explicit_authorization_required': True,
                          'profiles': ['038', '039', '040', '041'], 'external_connections_supported': False}))
        return
    try:
        print(json.dumps(rehearse(args.dump, args.manifest, args.approval_receipt, args.docker), indent=2))
    except Exception:
        raise SystemExit('isolated_restore_failed_private_details_suppressed') from None


if __name__ == '__main__':
    main()
