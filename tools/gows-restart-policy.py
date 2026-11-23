"""Freeze and verify the existing GOWS container; update only an approved policy.

No container creation, session API, restart, message send or Compose up.
Future Compose deployments must pass --check-compose with rendered JSON.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

NAME = 'socialmei-waha-gows-piloto'
TARGET = {'Name': 'unless-stopped', 'MaximumRetryCount': 0}


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def call(args):
    try:
        return subprocess.run(args, check=True, text=True, capture_output=True, timeout=20).stdout
    except (subprocess.SubprocessError, OSError):
        raise RuntimeError('gows_docker_operation_failed') from None


def inspect():
    rows = json.loads(call(['docker', 'inspect', NAME]))
    require(len(rows) == 1 and rows[0]['Name'] == '/' + NAME, 'gows_identity_mismatch')
    return rows[0]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def invariant(row):
    host = copy.deepcopy(row['HostConfig'])
    host.pop('RestartPolicy', None)
    return {'Id': row['Id'], 'Image': row['Image'], 'Config': row['Config'],
            'HostConfig': host, 'Mounts': row['Mounts'],
            'Networks': row['NetworkSettings']['Networks'], 'StartedAt': row['State']['StartedAt']}


def private(path, value):
    require(not path.exists(), 'private_artifact_already_exists')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def prepare(directory):
    row = inspect()
    require(row['State']['Running'], 'gows_not_running')
    require(row['HostConfig']['RestartPolicy'] == {'Name': 'no', 'MaximumRetryCount': 0},
            'restart_policy_not_expected')
    require(not directory.exists() and not directory.is_symlink(), 'new_private_directory_required')
    directory.mkdir(mode=0o700, parents=False)
    private(directory / 'before.private.json', row)
    plan = {'container': NAME, 'container_id': row['Id'], 'image_id': row['Image'],
            'invariant_sha256': fingerprint(invariant(row)),
            'before': row['HostConfig']['RestartPolicy'], 'after': TARGET,
            'compose_managed': bool((row['Config'].get('Labels') or {}).get('com.docker.compose.service')),
            'allowed_operation': 'docker_update_restart_only', 'recreate': False}
    plan['plan_sha256'] = fingerprint(plan)
    private(directory / 'plan.private.json', plan)
    return {'mode': 'prepared_not_applied', 'plan_sha256': plan['plan_sha256'],
            'compose_managed': plan['compose_managed'], 'container_restarted': False}


def verify(directory, approved=None, policy=None):
    require(not directory.is_symlink(), 'private_plan_required')
    for name in ('plan.private.json', 'before.private.json'):
        require((directory / name).is_file() and not (directory / name).is_symlink(), 'frozen_file_required')
    plan = json.loads((directory / 'plan.private.json').read_text())
    unsigned = dict(plan); digest = unsigned.pop('plan_sha256')
    require(fingerprint(unsigned) == digest and (approved is None or approved == digest), 'plan_mismatch')
    before = json.loads((directory / 'before.private.json').read_text())
    require(fingerprint(invariant(before)) == plan['invariant_sha256'], 'frozen_container_changed')
    row = inspect()
    require(row['State']['Running'] and fingerprint(invariant(row)) == plan['invariant_sha256'],
            'runtime_changed')
    require(row['HostConfig']['RestartPolicy'] == (policy or plan['before']), 'restart_policy_changed')
    require(plan['after'] == TARGET and plan['before'] == {'Name': 'no', 'MaximumRetryCount': 0},
            'unexpected_policy_plan')
    return plan


def update(directory, approved, rollback=False):
    require(bool(approved), 'explicit_approval_required')
    receipt_path = directory / 'execution.private.json'
    if rollback:
        require(receipt_path.is_file() and not receipt_path.is_symlink(), 'execution_receipt_required')
        receipt = json.loads(receipt_path.read_text())
        require(receipt.get('plan_sha256') == approved and receipt.get('status') == 'started',
                'reconcile_execution_receipt')
        plan = verify(directory, approved, TARGET)
        destination = plan['before']
    else:
        plan = verify(directory, approved)
        require(not receipt_path.exists(), 'reconcile_execution_receipt')
        private(receipt_path, {'plan_sha256': approved, 'status': 'started'})
        destination = TARGET
    # An uncertain Docker result is inspected, never retried blindly.
    try:
        call(['docker', 'update', '--restart', destination['Name'], plan['container_id']])
    except RuntimeError:
        verify(directory, approved, destination)
    verify(directory, approved, destination)
    private(directory / ('rollback.private.json' if rollback else 'verified.private.json'),
            {'plan_sha256': approved, 'policy': destination, 'container_restarted': False})
    return {'status': 'rolled_back' if rollback else 'applied', 'container_restarted': False,
            'plan_sha256': approved}


def check_compose(value):
    """Gate rendered Compose JSON, not a template with unresolved variables."""
    services = [s for s in value.get('services', {}).values() if s.get('container_name') == NAME]
    require(len(services) == 1, 'exact_gows_service_required')
    require(services[0].get('restart') == TARGET['Name'], 'gows_restart_policy_missing')
    return {'compose_restart_policy_verified': True, 'services_modified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--check-compose', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--verify', action='store_true')
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--rollback', action='store_true')
    parser.add_argument('--approved-plan')
    args = parser.parse_args()
    try:
        if args.check_compose:
            require(not (args.apply or args.rollback or args.verify or args.directory), 'compose_check_only')
            result = check_compose(json.loads(args.check_compose.read_text()))
        else:
            require(args.directory is not None, 'private_directory_required')
            if args.apply or args.rollback:
                result = update(args.directory, args.approved_plan, args.rollback)
            elif args.verify:
                plan = verify(args.directory)
                result = {'mode': 'verified_not_applied', 'plan_sha256': plan['plan_sha256']}
            else:
                result = prepare(args.directory)
        print(json.dumps(result))
    except Exception:
        print(json.dumps({'complete': False, 'action': 'reconcile_private_plan_and_runtime'}))
        raise SystemExit(1)
