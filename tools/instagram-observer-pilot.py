"""Read-only Brilho observer approval plan. Never starts or changes containers."""
import hashlib
import json
from pathlib import Path
import subprocess


IMAGE = 'sha256:fad45c4a9f644f51b694dd9799cea857bcb1eb77caf1bee02554a530a0d48636'
ARCHIVE_SHA256 = 'ce4a9d96d4f55d74dd94f92a3bb503771f39d4e2426a46ba1a7eda19b7c7676f'
ARCHIVE_BYTES = 81447936
API = 'socialmei-team-team-api-1'
LEGACY = 'socialmei-instagram-menu-worker'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def plan(rows, available_mib, image_present, compose_sha256):
    if type(available_mib) is not int or available_mib < 0:
        raise ValueError('memory_measurement_invalid')
    by_name = {row['Name'].lstrip('/'): row for row in rows}
    if len(by_name) != len(rows) or API not in by_name or LEGACY not in by_name:
        raise ValueError('runtime_identity_incomplete')
    api = by_name[API]
    if not api['State']['Running'] or api['State'].get('Health', {}).get('Status') != 'healthy':
        raise ValueError('api_not_healthy')
    blockers = []
    if available_mib < 520:
        blockers.append('memory_below_520_mib')
    if not image_present:
        blockers.append('exact_image_not_loaded')
    fingerprints = {}
    for name, row in by_name.items():
        pairs = [value.split('=', 1) for value in row['Config'].get('Env', [])]
        if any(len(pair) != 2 for pair in pairs) or len(dict(pairs)) != len(pairs):
            raise ValueError('ambiguous_environment')
        env = dict(pairs)
        scope = {env.get('SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID', '').strip()}
        scope.update(env.get('SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES', '').replace(',', ' ').split())
        if row['State']['Running'] and '60' in scope and name != API:
            blockers.append('existing_workspace60_worker')
        fingerprints[name] = digest({'id': row['Id'], 'image': row['Image'],
                                     'running': row['State']['Running'], 'config': row['Config'],
                                     'mounts': row.get('Mounts'), 'networks': row.get('NetworkSettings')})
    result = {
        'format': 'socialmei-brilho-observer-pilot-v1', 'workspace_id': 60,
        'image_id': IMAGE, 'compose_sha256': compose_sha256,
        'archive_sha256': ARCHIVE_SHA256, 'archive_bytes': ARCHIVE_BYTES,
        'image_source_commit': '331cc1fce37133587235ff3672c6f5b8119e241b',
        'runtime_fingerprints': fingerprints, 'available_mib': available_mib,
        'required_mib': 520, 'observer_limit_mib': 72, 'swap_limit_mib': 72,
        'backup_envelope_mib': 352, 'reserve_mib': 96,
        'external_send': False, 'provider_credentials': False,
        'service': 'brilho-observer', 'excluded_service': 'bella-observer',
        'scope': 'Load only the verified original image, then start only Brilho observation after all gates pass.',
        'start_arguments': ['--profile', 'instagram-observers', 'up', '-d', '--no-deps',
                            '--no-build', '--pull', 'never', 'brilho-observer'],
        'activation_authorized': False, 'blockers': sorted(set(blockers)),
        'pre_start_requirements': [
            'specific_owner_approval_of_this_plan', 'fresh_memory_at_least_520_mib',
            'at_least_512_mib_free_disk_and_no_backup_cycle_running_during_load',
            'verify_archive_full_oci_chain_and_sha256_before_loading',
            'same_runtime_and_compose_fingerprints', 'exact_image_id_present',
            'private_api_database_config_and_verify_full_ca_match',
            'explicit_utc_cutoff_and_empty_dedicated_state_volume',
            'compose_render_only_brilho_service_with_no_dependencies',
            'no_provider_secrets_no_ports_send_flags_false_poll_mode',
            'database_workspace60_advisory_lease_exclusive'],
        'monitor': ['health_ready_within_90_seconds', 'no_oom_or_restart_loop',
                    'sample_every_15_seconds_for_5_minutes_then_check_health_after_30_minutes',
                    'memory_limit_72_mib_no_swap', 'preserve_96_mib_runtime_headroom',
                    'existing_services_healthy_and_container_ids_unchanged',
                    'workspace60_checkpoint_only_no_queue_claims_or_provider_calls'],
        'rollback': 'Stop only the newly recorded Brilho container ID; preserve its state volume and all existing containers. Never compose down.',
    }
    result['plan_sha256'] = digest(result)
    return result


def run(args):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=20).stdout


def inspect():
    ids = run(['docker', 'ps', '-aq']).split()
    if not ids:
        raise ValueError('runtime_unavailable')
    rows = json.loads(run(['docker', 'inspect', *ids]))
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0]) // 1024
    image = subprocess.run(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'],
                           capture_output=True, text=True, timeout=20)
    compose = Path(__file__).resolve().parents[1] / 'deploy/team/compose.instagram-observers.yaml'
    return plan(rows, available, image.returncode == 0 and image.stdout.strip() == IMAGE,
                hashlib.sha256(compose.read_bytes()).hexdigest())


if __name__ == '__main__':
    try:
        print(json.dumps(inspect(), sort_keys=True))
    except Exception as error:
        print(json.dumps({'complete': False, 'activation_authorized': False,
                          'reason': str(error) if isinstance(error, ValueError) else type(error).__name__}))
        raise SystemExit(1)
