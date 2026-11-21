"""Prepare a disabled worker environment from API Docker metadata; never deploy.

Output contains secrets and must stay in the server-private directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import re
from urllib.parse import unquote, urlsplit

API = 'socialmei-team-team-api-1'
WORKER = 'socialmei-instagram-menu-worker'
DATABASE = 'socialmei_candidate040_20261114'
HOST = 'socialmei-postgres-relocation-20261112'
KEYS = {'DATABASE_URL', 'POSTGRES_HOST', 'POSTGRES_USER', 'POSTGRES_PASSWORD',
        'POSTGRES_DB', 'POSTGRES_PORT'}


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def environment(row):
    pairs = [line.split('=', 1) for line in row['Config'].get('Env', [])]
    require(all(len(pair) == 2 for pair in pairs), 'invalid_environment')
    require(len({key for key, _ in pairs}) == len(pairs), 'duplicate_environment')
    return dict(pairs)


def candidate(api, worker, workspace):
    require(api['Name'] == '/' + API and worker['Name'] == '/' + WORKER, 'source_identity_mismatch')
    require(type(workspace) is int and workspace in {60, 61}, 'workspace_not_reviewed')
    source = environment(api)
    explicit = source.get('DATABASE_URL', '').strip()
    if explicit:
        url = urlsplit(explicit)
        require(url.scheme in {'postgres', 'postgresql'} and not url.fragment, 'api_database_url_invalid')
        host, database = url.hostname, unquote(url.path[1:])
    else:
        host, database = source.get('POSTGRES_HOST', '').strip(), source.get('POSTGRES_DB', '').strip()
        require(bool(source.get('POSTGRES_USER', '').strip()), 'api_database_user_missing')
    require((host, database) == (HOST, DATABASE), 'api_database_not_reviewed')
    result = environment(worker)
    # An old explicit Prisma URL otherwise overrides all POSTGRES_* values.
    for key in KEYS:
        result.pop(key, None)
    result.update({key: value for key, value in source.items() if key in KEYS})
    result.update(SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME=database,
                  SOCIALMEI_INSTAGRAM_WORKER_MODE='observe',
                  SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID=str(workspace),
                  SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES=str(workspace),
                  SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED='false',
                  SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED='false')
    return result


def environment_bytes(values):
    require(all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key)
                and isinstance(value, str) and not any(c in value for c in '\r\n\0')
                for key, value in values.items()), 'unsafe_environment_file')
    return ''.join(key + '=' + value + '\n' for key, value in sorted(values.items())).encode()


def prepare(directory):
    require(not directory.exists() and not directory.is_symlink(), 'new_private_directory_required')
    try:
        rows = json.loads(subprocess.run(['docker', 'inspect', API, WORKER],
                          text=True, capture_output=True, check=True, timeout=20).stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise RuntimeError('private_metadata_unavailable') from None
    require(len(rows) == 2, 'exact_sources_required')
    api, worker = rows
    require(api['State']['Running'] and api['State'].get('Health', {}).get('Status') == 'healthy',
            'api_not_healthy')
    candidates = {str(workspace): candidate(api, worker, workspace) for workspace in (60, 61)}
    directory.mkdir(mode=0o700)
    contents = {'api.private.json': api, 'worker.private.json': worker,
                'candidates.private.json': candidates}
    # Compose must read these with format: raw, not interpolate private values.
    for workspace, values in candidates.items():
        contents['workspace' + workspace + '.env'] = environment_bytes(values)
    hashes = {}
    for name, value in contents.items():
        data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        hashes[name] = hashlib.sha256(data).hexdigest()
    return {'mode': 'prepared_disabled_not_deployed', 'files_sha256': hashes,
            'database': DATABASE, 'workspaces': [60, 61],
            'api_container_id': api['Id'], 'worker_container_id': worker['Id'],
            'new_worker_image_required': True, 'separate_state_volumes_required': True,
            'n8n_exclusivity_review_required': True, 'runtime_and_vault_review_required': True,
            'send_enabled': False,
            'services_modified': False, 'tokens_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.directory)))
    except Exception as error:
        print(json.dumps({'complete': False, 'services_modified': False,
                          'reason': str(error) if isinstance(error, RuntimeError) else type(error).__name__}))
        raise SystemExit(1)
