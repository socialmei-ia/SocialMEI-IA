"""Freeze a disabled Bella-only approval plan from a private read-only snapshot."""
import argparse
import hashlib
import json
import os
from pathlib import Path

IMAGE = 'sha256:fad45c4a9f644f51b694dd9799cea857bcb1eb77caf1bee02554a530a0d48636'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build(snapshot):
    memory = snapshot['available_mib']
    if type(memory) is not int or memory < 0:
        raise ValueError('memory_measurement_invalid')
    brilho = snapshot['brilho']
    if (brilho['id'] != snapshot['preserved_brilho_id'] or brilho['image'] != IMAGE
            or not brilho['running'] or brilho['health'] != 'healthy' or brilho['restarts'] != 0
            or brilho['oom'] or brilho['workspace'] != '60' or brilho['mode'] != 'observe'
            or brilho['send'] != 'false' or brilho['auto_menu'] != 'false'
            or brilho['memory_limit'] != 72 * 1024**2 or brilho['memswap_limit'] != brilho['memory_limit']
            or brilho['state_volume'] != 'socialmei-instagram-observers_brilho-state'):
        raise ValueError('preserved_brilho_identity_or_health_changed')
    blockers = []
    # Deliberately grant no residency credit for the running Brilho process.
    # Keep its entire cap available in addition to backup, reserve and Bella.
    required = 352 + 96 + 72 + 72
    if memory < required:
        blockers.append('memory_below_592_mib_conservative_budget')
    if not snapshot['exact_image_present']:
        blockers.append('reviewed_image_missing')
    if snapshot['bella_volume_exists']:
        blockers.append('bella_volume_requires_reconciliation')
    if snapshot['duplicate_workspace61']:
        blockers.append('workspace61_worker_already_exists')
    result = {'format': 'socialmei-bella-observer-pilot-v1', 'workspace_id': 61,
        'service': 'bella-observer', 'image_id': IMAGE, 'available_mib': memory,
        'required_before_start_mib': required, 'required_while_running_mib': 520,
        'observer_limit_mib': 72, 'memswap_limit_mib': 72,
        'budget': {'backup_mib': 352, 'reserve_mib': 96, 'full_brilho_cap_mib': 72,
                   'bella_cap_mib': 72, 'existing_residency_credit_mib': 0},
        'preserved_brilho_id': brilho['id'],
        'runtime_fingerprints': snapshot['runtime_fingerprints'],
        'compose_sha256': snapshot['compose_sha256'], 'snapshot_sha256': digest(snapshot),
        'activation_authorized': False, 'ready_for_approval': not blockers, 'blockers': blockers,
        'external_send': False, 'queue_consumption': False, 'meta_changes': False,
        'start_arguments': ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'bella-observer'],
        'pre_start': ['specific_owner_approval', 'same_runtime_compose_and_exact_image',
                      'fresh_memory_at_least_592_mib', 'api_database_verify_full_ca',
                      'workspace61_exclusive_lease', 'new_empty_bella_volume',
                      'independent_utc_cutoff_and_env_without_provider_secrets',
                      'read_only_root_no_ports_no_swap_poll_mode',
                      'do_not_recreate_or_reconfigure_brilho'],
        'monitor': 'Health within90s, sample every15s for5min then every60s through30min; '
                   'stop only new Bella on OOM/restarts, MemAvailable<520MiB or existing service instability.',
        'rollback': 'Stop only the newly recorded Bella container ID; preserve its volume, '
                    'Brilho container and all existing services. Never compose down.'}
    result['plan_sha256'] = digest(result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(json.loads(args.snapshot.read_text()))
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('plan_sha256', 'ready_for_approval', 'blockers')}))
