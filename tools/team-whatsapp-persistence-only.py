#!/usr/bin/env python3
"""Detach the legacy WAHA hook for a receive-only pilot; never change n8n or send.

Read-only by default. Apply requires a configuration digest from inspection.
Session configuration updates may reconnect WEBJS; the container and history
volume are preserved. A failed health/config check restores the exact snapshot.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path('/var/lib/socialmei-wa-pilot')
REGISTRY = ROOT / 'registry/waha-registry.json'
WAHA = 'socialmei-waha'
API = 'socialmei-team-team-api-1'


class Blocked(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Blocked(code)


def config_digest(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def persistence_config(config, binding, legacy_hooks=None):
    """Validate both destinations and return only the already configured signed hook."""
    require(isinstance(config, dict), 'session_config_invalid')
    hooks = config.get('webhooks')
    require(isinstance(hooks, list) and 1 <= len(hooks) <= 2, 'unexpected_hook_count')
    url = 'http://team-api:8000/internal/waha/' + binding['instance'] + '/webhook'
    direct = [h for h in hooks if isinstance(h, dict) and h.get('url') == url]
    require(len(direct) == 1, 'direct_hook_missing_or_duplicated')
    require(direct[0].get('events') == ['message']
            and (direct[0].get('hmac') or {}).get('key') == binding['hmac_key'], 'signed_hook_diverged')
    legacy = [h for h in hooks if h is not direct[0]]
    if legacy:
        require(isinstance(legacy_hooks, list) and len(legacy_hooks) == 1
                and legacy == legacy_hooks, 'legacy_hook_differs_from_verified_backup')
    for hook in legacy:
        require(isinstance(hook, dict), 'legacy_hook_invalid')
        path = urlsplit(str(hook.get('url', ''))).path
        require(path.startswith(('/webhook-test/', '/webhook/'))
                and 'message' in (hook.get('events') or []), 'unknown_legacy_hook')
    result = copy.deepcopy(config)
    result['webhooks'] = copy.deepcopy(direct)
    return result


def docker(*args):
    result = subprocess.run(['docker', '--host=unix:///var/run/docker.sock', *args],
                            capture_output=True, timeout=40)
    require(result.returncode == 0, 'docker_operation_failed')
    return result.stdout


def inspect(name):
    rows = json.loads(docker('inspect', name))
    require(len(rows) == 1 and rows[0]['State'].get('Running'), 'container_not_running')
    return rows[0]


def private(path, mode, *, directory=False):
    require(not path.is_symlink() and (path.is_dir() if directory else path.is_file()), 'private_path_invalid')
    info = path.stat()
    require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == mode, 'private_path_permissions_invalid')


def write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def backup(session):
    path = ROOT / ('persistence-only-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    path.mkdir(mode=0o700)
    data = json.dumps(session, sort_keys=True).encode()
    write(path / 'session.json', data)
    write(path / 'session.sha256', (hashlib.sha256(data).hexdigest() + '\n').encode())
    require((path / 'session.json').read_bytes() == data, 'backup_verification_failed')
    return path


def load_snapshot(folder):
    require(folder.parent == ROOT and folder.name.startswith('persistence-only-'), 'snapshot_outside_private_root')
    private(folder, 0o700, directory=True)
    for name in ('session.json', 'session.sha256'):
        private(folder / name, 0o600)
    data = (folder / 'session.json').read_bytes()
    require(hashlib.sha256(data).hexdigest() == (folder / 'session.sha256').read_text().strip(), 'snapshot_digest_mismatch')
    return json.loads(data)


def load_legacy(folder):
    require(folder.parent == ROOT, 'legacy_backup_outside_private_root')
    private(folder, 0o700, directory=True)
    name = 'waha-session.before.json'
    private(folder / name, 0o600)
    private(folder / 'SHA256SUMS.private.json', 0o600)
    sums = json.loads((folder / 'SHA256SUMS.private.json').read_text())
    data = (folder / name).read_bytes()
    require(hashlib.sha256(data).hexdigest() == sums.get(name), 'legacy_backup_digest_mismatch')
    before = json.loads(data)
    hooks = (before.get('config') or {}).get('webhooks')
    require(isinstance(hooks, list) and len(hooks) == 1, 'legacy_backup_ambiguous')
    return before


def operate(args):
    require(os.geteuid() == 0, 'root_required_for_private_inspection')
    private(ROOT, 0o700, directory=True)
    private(REGISTRY.parent, 0o700, directory=True)
    private(REGISTRY, 0o600)
    registry = json.loads(REGISTRY.read_text())
    bindings = registry.get('bindings') or []
    require(registry.get('version') == 1 and len(bindings) == 1, 'registry_ambiguous')
    binding = bindings[0]
    require(binding.get('workspace_id') == 1 and binding.get('instance') == 'socialmei-equipe-piloto'
            and binding.get('account_id', '').split('@')[0].endswith('5976'), 'pilot_binding_diverged')
    api, waha = inspect(API), inspect(WAHA)
    require(api['State'].get('Health', {}).get('Status') == 'healthy', 'api_not_healthy')
    api_env = dict(x.split('=', 1) for x in api['Config'].get('Env', []) if '=' in x)
    require(api_env.get('SOCIALMEI_WAHA_INGRESS_MODE', '').strip().lower() == 'team-pilot'
            and api_env.get('SOCIALMEI_WAHA_LAB_ENVIRONMENT', '').strip().lower() == 'team-pilot'
            and api_env.get('SOCIALMEI_WAHA_REGISTRY_FILE') == '/run/socialmei/private/waha-registry.json'
            and api_env.get('SOCIALMEI_SHARED_DATA_ENABLED', '').lower() in {'1', 'true', 'yes', 'on'}
            and api_env.get('SOCIALMEI_AUTH_ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}
            and api_env.get('SOCIALMEI_WHATSAPP_BOT_ENABLED', 'false').strip().lower() != 'true', 'receive_only_flags_required')
    mounts = [m for m in api.get('Mounts', []) if m.get('Destination') == '/run/socialmei/private']
    require(len(mounts) == 1 and mounts[0].get('RW') is False
            and mounts[0].get('Source') == str(REGISTRY.parent), 'registry_mount_diverged')
    require(bool(set(api['NetworkSettings']['Networks']) & set(waha['NetworkSettings']['Networks'])), 'private_network_missing')
    env = dict(x.split('=', 1) for x in waha['Config'].get('Env', []) if '=' in x)
    key = env.get('WAHA_API_KEY') or env.get('WAHA_API_KEY_PLAIN')
    require(bool(key) and not key.startswith('sha512:'), 'waha_api_key_unavailable')
    require(env.get('WHATSAPP_DEFAULT_ENGINE', 'WEBJS') == 'WEBJS', 'engine_not_webjs')
    ports = (waha['NetworkSettings'].get('Ports') or {}).get('3000/tcp') or []
    require(len(ports) == 1, 'waha_local_port_ambiguous')
    base = 'http://127.0.0.1:' + ports[0]['HostPort'] + '/api/sessions/' + quote(binding['session'], safe='')

    def request(method='GET', config=None):
        data = None if config is None else json.dumps({'name': binding['session'], 'config': config}).encode()
        req = Request(base, method=method, data=data, headers={'X-Api-Key': key, 'Content-Type': 'application/json'})
        with urlopen(req, timeout=20) as response:
            return json.load(response)

    def validate(session):
        require(session.get('name') == binding['session'] and session.get('status') == 'WORKING', 'session_not_working')
        require((session.get('me') or {}).get('id') == binding['account_id'], 'session_account_changed')
        engine = session.get('engine')
        engine = engine.get('engine') if isinstance(engine, dict) else engine
        require(str(engine).upper() == 'WEBJS', 'session_engine_changed')
        return session['config']

    def wait_for(expected):
        for _ in range(40):
            session = request()
            if session.get('status') == 'WORKING':
                require(validate(session) == expected, 'session_config_changed')
                require(inspect(WAHA)['Id'] == waha['Id'], 'waha_container_changed')
                updated_api = inspect(API)
                require(updated_api['Id'] == api['Id'], 'api_container_changed')
                require(updated_api['State'].get('Health', {}).get('Status') == 'healthy', 'api_health_changed')
                return
            time.sleep(3)
        raise Blocked('session_recovery_timeout')

    current = request()
    config = validate(current)
    original = load_legacy(args.legacy_backup)
    validate(original)
    original_shape = copy.deepcopy(config)
    original_shape['webhooks'] = original['config']['webhooks']
    require(original_shape == original['config'], 'non_webhook_session_config_drift')
    legacy_hooks = original['config']['webhooks']
    target = persistence_config(config, binding, legacy_hooks)
    if args.restore:
        before = load_snapshot(Path(args.restore))
        require(validate(before) is not None, 'snapshot_session_invalid')
        target = before['config']
        require(config == persistence_config(target, binding, legacy_hooks), 'restore_current_config_drifted')
    elif not args.apply:
        return {'action': 'read_only', 'already_persistence_only': target == config,
                'legacy_hook_count': len(config['webhooks']) - 1,
                'config_sha256': config_digest(config), 'api_healthy': True,
                'session_working': True, 'authorized_suffix_verified': True}
    require(args.confirm == 'TEAM-1' and args.expected_config_sha256 == config_digest(config), 'confirmation_or_config_digest_missing')
    if target == config:
        return {'action': 'already_persistence_only', 'session_working': True}
    saved = backup(current)
    require(validate(request()) == config, 'config_changed_before_update')
    try:
        request('PUT', target)
        wait_for(target)
    except Exception:
        try:
            request('PUT', config)
            wait_for(config)
        except Exception:
            raise Blocked('update_failed_rollback_failed') from None
        raise Blocked('update_failed_rollback_verified') from None
    return {'action': 'restored' if args.restore else 'persistence_only_configured',
            'backup': saved.name, 'session_working': True, 'authorized_suffix_verified': True,
            'n8n_workflow_changed': False, 'container_recreated': False, 'provider_messages_sent': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--restore', metavar='PRIVATE_SNAPSHOT_DIRECTORY')
    parser.add_argument('--expected-config-sha256')
    parser.add_argument('--confirm')
    parser.add_argument('--legacy-backup', type=Path, required=True,
                        help='Verified root-only backup directory containing the original WAHA hook and checksum manifest')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        import fcntl
        require(os.geteuid() == 0, 'root_required_for_private_inspection')
        private(ROOT, 0o700, directory=True)
        lock = ROOT / 'persistence-only.lock'
        fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = operate(args)
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({'action': 'stopped', 'error_code': str(exc) if isinstance(exc, Blocked) else 'operation_failed_details_suppressed'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
