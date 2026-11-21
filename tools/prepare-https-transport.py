"""Prepare by default; live reload requires an explicitly approved frozen plan."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import os
import urllib.request

spec = importlib.util.spec_from_file_location('privacy', Path(__file__).with_name('instagram-proxy-privacy.py'))
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)
CONTAINER = 'socialmei-caddy'
BLOCK = '    servers {\n        protocols h1 h2\n    }\n'


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def candidate_text(source):
    require(bool(source.strip()), 'EMPTY_CADDYFILE')
    bounds = privacy._global_block(source)
    if bounds is None:
        return '{\n' + BLOCK + '}\n' + source
    start, end = bounds
    require(not re.search(r'^\s*servers\b', source[start + 1:end], re.M), 'EXISTING_SERVER_OPTIONS_REQUIRE_REVIEW')
    return source[:start + 1] + '\n' + BLOCK + source[start + 1:]


def validate_delta(before, after):
    expected = copy.deepcopy(before)
    servers = expected.get('apps', {}).get('http', {}).get('servers', {})
    require(bool(servers), 'HTTP_SERVERS_MISSING')
    for server in servers.values():
        require(server.get('protocols') in (None, ['h1', 'h2', 'h3']), 'EXISTING_PROTOCOL_OPTIONS_REQUIRE_REVIEW')
        server['protocols'] = ['h1', 'h2']
    require(expected == after, 'CHANGE_EXCEEDS_HTTP_PROTOCOLS')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def prepare(directory):
    directory = Path(directory).absolute()
    require(not directory.exists(), 'PLAN_DIRECTORY_ALREADY_EXISTS')
    rows = json.loads(privacy._call(['docker', 'inspect', CONTAINER]))
    require(isinstance(rows, list) and len(rows) == 1 and rows[0].get('Name') == '/' + CONTAINER,
            'EXACT_PUBLIC_CADDY_REQUIRED')
    installed = rows[0]
    require(installed['State']['Running'], 'PUBLIC_CADDY_NOT_RUNNING')
    mounts = [m for m in installed['Mounts'] if m['Type'] == 'bind' and m['Destination'] == '/etc/caddy/Caddyfile']
    require(len(mounts) == 1, 'EXACT_CADDYFILE_BIND_REQUIRED')
    source = Path(mounts[0]['Source'])
    require(source.is_file() and not source.is_symlink(), 'SOURCE_FILE_UNAVAILABLE')
    raw = source.read_text()
    require(raw == privacy._call(['docker', 'exec', CONTAINER, 'cat', '/etc/caddy/Caddyfile']), 'MOUNT_SOURCE_CHANGED')
    active = privacy._json(privacy._call(['docker', 'exec', CONTAINER, 'wget', '-qO-', 'http://127.0.0.1:2019/config/']))
    before = privacy._normalized_auto_hidden_config(privacy._adapt(CONTAINER, raw))
    require(before == active, 'ACTIVE_CONFIG_DIFFERS_FROM_SOURCE')
    require(privacy.protected(active), 'EXISTING_LOG_PRIVACY_NOT_VERIFIED')
    changed = candidate_text(raw)
    after = privacy._normalized_auto_hidden_config(privacy._adapt(CONTAINER, changed))
    validate_delta(active, after)
    directory.mkdir(mode=0o700)
    for name, value in [('before.Caddyfile', raw), ('candidate.Caddyfile', changed),
                        ('before.private.json', active), ('candidate.private.json', after),
                        ('container.private.json', installed)]:
        privacy._write_private(directory / name, value if isinstance(value, str) else json.dumps(value))
    plan = {'mode': 'prepared_not_applied', 'service': CONTAINER, 'container_id': installed['Id'],
            'image_id': installed['Image'], 'source_file': str(source), 'source_inode': source.stat().st_ino,
            'before_sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'candidate_sha256': hashlib.sha256(changed.encode()).hexdigest(),
            'before_json_sha256': digest(active), 'candidate_json_sha256': digest(after),
            'allowed_change': 'http_servers_protocols_h1_h2_only', 'routes_changed': False,
            'credentials_changed': False, 'ports_changed': False, 'services_modified': False,
            'execution': 'approved_in_place_config_write_and_local_admin_reload_only',
            'rollback': 'frozen_before_Caddyfile_and_before_private_json', 'approval_required': True}
    plan['plan_sha256'] = digest(plan)
    privacy._write_private(directory / 'plan.private.json', json.dumps(plan))
    return {k: plan[k] for k in ['mode', 'service', 'plan_sha256', 'services_modified', 'approval_required']}


def load_plan(directory, approved=None):
    requested = Path(directory).absolute()
    require(not requested.is_symlink(), 'PRIVATE_PLAN_REQUIRED')
    directory = requested.resolve(strict=True)
    for name in ['plan.private.json', 'before.Caddyfile', 'candidate.Caddyfile', 'before.private.json', 'candidate.private.json', 'container.private.json']:
        require((directory / name).is_file() and not (directory / name).is_symlink(), 'FROZEN_FILE_REQUIRED')
    plan = json.loads((directory / 'plan.private.json').read_text())
    unsigned = dict(plan); sha = unsigned.pop('plan_sha256')
    require(digest(unsigned) == sha and (approved is None or sha == approved), 'APPROVED_PLAN_MISMATCH')
    for filename, key in [('before.Caddyfile', 'before_sha256'), ('candidate.Caddyfile', 'candidate_sha256')]:
        path = directory / filename
        require(not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == plan[key], 'FROZEN_TEXT_CHANGED')
    for filename, key in [('before.private.json', 'before_json_sha256'), ('candidate.private.json', 'candidate_json_sha256')]:
        require(digest(json.loads((directory / filename).read_text())) == plan[key], 'FROZEN_JSON_CHANGED')
    return directory, plan


def active_json():
    return privacy._json(privacy._call(['docker', 'exec', CONTAINER, 'wget', '-qO-', 'http://127.0.0.1:2019/config/']))


def same_container(directory, plan):
    current = json.loads(privacy._call(['docker', 'inspect', CONTAINER]))[0]
    previous = json.loads((directory / 'container.private.json').read_text())
    require(current['State']['Running'] and current['Id'] == plan['container_id'] and current['Image'] == plan['image_id'], 'CADDY_IDENTITY_CHANGED')
    require(all(current[k] == previous[k] for k in ['Id', 'Image', 'Config', 'HostConfig', 'Mounts']), 'CADDY_RUNTIME_CHANGED')
    source = Path(plan['source_file'])
    require(source.is_file() and not source.is_symlink() and source.stat().st_ino == plan['source_inode'], 'SOURCE_INODE_CHANGED')
    return source


def verify(directory, approved=None):
    directory, plan = load_plan(directory, approved)
    source = same_container(directory, plan)
    require(hashlib.sha256(source.read_bytes()).hexdigest() == plan['before_sha256'], 'SOURCE_CHANGED')
    require(digest(active_json()) == plan['before_json_sha256'], 'ACTIVE_CONFIG_CHANGED')
    return {'mode': 'verified_not_applied', 'plan_sha256': plan['plan_sha256'], 'services_modified': False}


def web_state():
    with urllib.request.urlopen('https://socialmei-ia.54-94-213-7.sslip.io/frontend/entrada.html', timeout=15) as response:
        require(response.status == 200, 'HTTPS_NOT_HEALTHY')
        return {'entry_sha256': hashlib.sha256(response.read()).hexdigest(),
                'advertises_h3': 'h3=' in response.headers.get('Alt-Svc', '')}


def other_services():
    ids = privacy._call(['docker', 'ps', '-q']).split()
    rows = json.loads(privacy._call(['docker', 'inspect', *ids]))
    require(any(r['Name'] == '/socialmei-team-team-api-1' and r['State'].get('Health', {}).get('Status') == 'healthy'
                for r in rows), 'TEAM_API_NOT_HEALTHY')
    return {r['Name']: [r['Id'], r['Image'], r['State']['StartedAt']]
            for r in rows if r['Name'] != '/' + CONTAINER}


def write_and_reload(source, data):
    # Preserve the inode: an atomic replacement would leave a file bind on old bytes.
    with source.open('wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    privacy._call(['docker', 'exec', CONTAINER, 'caddy', 'reload', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'])


def rollback(directory, approved):
    directory, plan = load_plan(directory, approved)
    receipt = json.loads((directory / 'execution.private.json').read_text())
    require(receipt['status'] in {'started', 'applied'} and receipt['plan_sha256'] == approved, 'REVERSIBLE_RECEIPT_REQUIRED')
    source = same_container(directory, plan)
    require(hashlib.sha256(source.read_bytes()).hexdigest() in {plan['before_sha256'], plan['candidate_sha256']}, 'ROLLBACK_SOURCE_DIVERGED')
    require(digest(active_json()) in {plan['before_json_sha256'], plan['candidate_json_sha256']}, 'ROLLBACK_RUNTIME_DIVERGED')
    write_and_reload(source, (directory / 'before.Caddyfile').read_bytes())
    require(digest(active_json()) == plan['before_json_sha256'], 'ROLLBACK_NOT_VERIFIED')
    require(web_state() == receipt['before_web'], 'ROLLBACK_HTTPS_CHANGED')
    receipt.update(status='rolled_back', other_services_unchanged=other_services() == receipt['other_services'])
    privacy._write_private(directory / 'execution.private.json', json.dumps(receipt))
    return {'status': 'rolled_back', 'plan_sha256': approved, 'other_services_unchanged': receipt['other_services_unchanged']}


def apply(directory, approved):
    require(bool(approved), 'EXPLICIT_APPROVED_PLAN_REQUIRED')
    verify(directory, approved)
    directory, plan = load_plan(directory, approved)
    require(not (directory / 'execution.private.json').exists(), 'EXECUTION_RECEIPT_EXISTS_RECONCILE_FIRST')
    receipt = {'status': 'started', 'plan_sha256': approved, 'before_web': web_state(), 'other_services': other_services()}
    privacy._write_private(directory / 'execution.private.json', json.dumps(receipt))
    try:
        source = same_container(directory, plan)
        write_and_reload(source, (directory / 'candidate.Caddyfile').read_bytes())
        require(digest(active_json()) == plan['candidate_json_sha256'], 'CANDIDATE_NOT_ACTIVE')
        web = web_state()
        require(not web['advertises_h3'] and web['entry_sha256'] == receipt['before_web']['entry_sha256'], 'HTTPS_TRANSPORT_NOT_VERIFIED')
        require(other_services() == receipt['other_services'], 'OTHER_SERVICE_CHANGED')
        receipt.update(status='applied', other_services_unchanged=True)
        privacy._write_private(directory / 'execution.private.json', json.dumps(receipt))
        return {'status': 'applied', 'plan_sha256': approved, 'other_services_unchanged': True, 'routes_changed': False}
    except Exception:
        rollback(directory, approved)
        raise RuntimeError('TRANSPORT_APPLY_FAILED_ROLLBACK_VERIFIED') from None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--verify', action='store_true')
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--rollback', action='store_true')
    parser.add_argument('--approved-plan')
    args = parser.parse_args()
    try:
        if args.apply or args.rollback:
            require(bool(args.approved_plan), 'EXPLICIT_APPROVED_PLAN_REQUIRED')
            result = (apply if args.apply else rollback)(args.directory, args.approved_plan)
        else:
            result = verify(args.directory, args.approved_plan) if args.verify else prepare(args.directory)
        print(json.dumps(result))
    except Exception as error:
        print(json.dumps({'complete': False, 'services_modified': 'reconcile_private_receipt' if args.apply or args.rollback else False,
                          'reason': str(error) if isinstance(error, RuntimeError) else type(error).__name__}))
        raise SystemExit(1)
