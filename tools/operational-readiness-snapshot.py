#!/usr/bin/env python3
"""Bounded read-only Linux/Docker inventory; never queries SQL or providers.

Private inspect/log output is parsed locally and discarded. Only allowlisted
metadata, categories and hashes leave the host. No configuration is written.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import unquote, urlsplit

API = 'socialmei-team-team-api-1'
BACKUP = Path('/home/ubuntu/.socialmei-postgres-relocation-20261112')
FLAGS = ('SOCIALMEI_AUTH_ENABLED', 'SOCIALMEI_IDENTITY_MODE', 'SOCIALMEI_RECOVERY_MODE',
         'SOCIALMEI_INSTAGRAM_RUNTIME_MODE', 'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED',
         'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED', 'SOCIALMEI_WHATSAPP_BOT_ENABLED',
         'SOCIALMEI_WAHA_INGRESS_MODE', 'SOCIALMEI_QUEUE_WAKEUP_MODE')


def run(*args, timeout=20):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('read_command_failed')
    return result.stdout


def text(path):
    try:
        return Path(path).read_text()
    except (OSError, ValueError):
        return ''


def numbers(path):
    return {parts[0].rstrip(':'): int(parts[1]) for line in text(path).splitlines()
            if len(parts := line.split()) >= 2 and parts[1].isdigit()}


def category(output):
    # Never return raw logs, URLs, exceptions, tokens or message bodies.
    return {'plan_limit_seen': bool(re.search(r'planLimitReached|provider_account_limit', output, re.I)),
            'health_db_503_seen': bool(re.search(r'/health/db[^\n]{0,100}\b503\b', output)),
            'health_db_200_seen': bool(re.search(r'/health/db[^\n]{0,100}\b200\b', output)),
            'readiness_unavailable_seen': 'periodic database readiness: unavailable' in output}


def db_identity(env):
    explicit = env.get('DATABASE_URL', '').strip()
    if explicit:
        parsed = urlsplit(explicit)
        if parsed.scheme in ('postgres', 'postgresql') and parsed.hostname:
            return (parsed.hostname, str(parsed.port or 5432), unquote(parsed.path.lstrip('/')),
                    unquote(parsed.username or ''), unquote(parsed.password or ''))
        return ('opaque', explicit)
    if env.get('POSTGRES_HOST') and env.get('POSTGRES_DB') and env.get('POSTGRES_USER'):
        return (env['POSTGRES_HOST'].strip(), env.get('POSTGRES_PORT', '').strip() or '5432',
                env['POSTGRES_DB'].strip(), env['POSTGRES_USER'].strip(), env.get('POSTGRES_PASSWORD', ''))
    return None


def provider(env):
    host = urlsplit(env.get('DATABASE_URL', '').strip()).hostname or env.get('POSTGRES_HOST', '')
    return 'prisma' if host.endswith(('.prisma.io', '.prisma-data.net')) else 'other'


def cgroup_memory(pid):
    if not isinstance(pid, int) or pid <= 0:
        return None
    unified = next((line[3:] for line in text(f'/proc/{pid}/cgroup').splitlines()
                    if line.startswith('0::')), None)
    if unified is None:
        return {'available': False, 'reason': 'cgroup_v2_not_available'}
    base = Path('/sys/fs/cgroup') / unified.lstrip('/')
    if not base.resolve().is_relative_to(Path('/sys/fs/cgroup')):
        return None
    def integer(name):
        value = text(base / name).strip()
        return int(value) if value.isdigit() else None
    stat = numbers(base / 'memory.stat')
    return {'available': True, 'current_bytes': integer('memory.current'),
            'swap_current_bytes': integer('memory.swap.current'),
            'anon_bytes': stat.get('anon'), 'file_bytes': stat.get('file'),
            'inactive_file_bytes': stat.get('inactive_file'),
            'kernel_bytes': stat.get('kernel'), 'events': numbers(base / 'memory.events')}


def project(obj, groups):
    env = dict(item.split('=', 1) for item in obj.get('Config', {}).get('Env', []) if '=' in item)
    identity = db_identity(env)
    group = None
    if identity is not None:
        if identity not in groups:
            groups.append(identity)
        group = groups.index(identity) + 1
    host = obj.get('HostConfig', {})
    state = obj.get('State', {})
    health = state.get('Health') or {}
    config = obj.get('Config', {})
    health_config = config.get('Healthcheck') or {}
    test = health_config.get('Test', [])
    labels = config.get('Labels') or {}
    return {'name': obj['Name'].lstrip('/'), 'image_id': obj.get('Image'),
            'revision': value if re.fullmatch(r'[0-9a-f]{40}', value := labels.get('org.opencontainers.image.revision') or '') else None,
            'compose_service': labels.get('com.docker.compose.service'),
            'compose_migrator_dependency': 'team-migrate:' in labels.get('com.docker.compose.depends_on', ''),
            'state': state.get('Status'), 'health': health.get('Status'),
            'health_exit_codes': [entry.get('ExitCode') for entry in health.get('Log', [])],
            'health_output_categories': category('\n'.join(entry.get('Output', '') for entry in health.get('Log', []))),
            'periodic_healthcheck_installed': any('runtime_healthcheck.py' in str(part) for part in test),
            'health_interval_seconds': health_config.get('Interval', 0) / 1e9,
            'restart_count': obj.get('RestartCount'), 'oom_killed': state.get('OOMKilled'),
            'memory_limit_bytes': host.get('Memory'), 'memory_reservation_bytes': host.get('MemoryReservation'),
            'memory_swap_limit_bytes': host.get('MemorySwap'), 'nano_cpus': host.get('NanoCpus'),
            'cgroup_memory': cgroup_memory(state.get('Pid')) if state.get('Running') else None,
            'networks': sorted(obj.get('NetworkSettings', {}).get('Networks', {})),
            'mounts': [{'type': mount.get('Type'), 'target': mount.get('Destination'),
                        'writable': mount.get('RW'),
                        'source_sha256': hashlib.sha256(mount.get('Source', '').encode()).hexdigest()}
                       for mount in obj.get('Mounts', [])],
            'published_port_count': sum(bool(value) for value in (host.get('PortBindings') or {}).values()),
            'database_group': group, 'database_provider': provider(env) if identity is not None else None,
            'database_group_scope': 'normalized configured endpoint/database/credentials; not live identity or connection options',
            'optional_modes': {key: (env[key] if env[key] in ('true', 'false', 'disabled', 'enabled', 'required', 'poll', 'notify')
                                     else 'configured_other') for key in FLAGS if key in env}}


def backups():
    if BACKUP.is_symlink():
        return {'inspection_available': False, 'reason': 'unexpected_symlink'}
    if not BACKUP.exists() or not os.access(BACKUP, os.R_OK | os.X_OK):
        return {'inspection_available': False, 'reason': 'backup_directory_missing_or_inaccessible',
                's3_configuration_present': None, 'local_receipt_count': None}
    if (BACKUP / 'backups').is_symlink():
        return {'inspection_available': False, 'reason': 'unexpected_symlink'}
    result = {'scope': 'isolated historical destination; not current production',
              's3_configuration_present': (BACKUP / 's3-backup.private.json').is_file()}
    for unit in ('socialmei-postgres-relocation-backup.timer', 'socialmei-postgres-relocation-backup.service'):
        try:
            output = run('systemctl', 'show', unit, '--property=LoadState,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,LastTriggerUSec,NextElapseUSecRealtime')
            result[unit] = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
        except Exception:
            result[unit] = {'inspection_available': False}
    receipts = sorted((path for path in (BACKUP / 'backups').glob('destination-*.json')
                       if path.is_file() and not path.is_symlink() and path.stat().st_size < 16384),
                      key=lambda path: path.stat().st_mtime, reverse=True)
    result['local_receipt_count'] = len(receipts)
    if receipts:
        record = json.loads(receipts[0].read_text())
        dump = receipts[0].with_suffix('.dump')
        entry = {'created_at_utc': record.get('created_at_utc') if re.fullmatch(
                     r'\d{8}T\d{6}Z-[0-9a-f]{8}', str(record.get('created_at_utc'))) else None,
                 'bytes': record.get('bytes') if type(record.get('bytes')) is int and record['bytes'] >= 0 else None,
                 'sha256': record.get('sha256') if re.fullmatch(r'[0-9a-f]{64}', str(record.get('sha256'))) else None,
                 'source': 'isolated_historical_destination' if record.get('source') == 'isolated_historical_destination' else 'unrecognized'}
        entry.update({key: record.get(key) if type(record.get(key)) is bool else None
                      for key in ('current_production_backup', 'external_uploaded', 'archive_index_verified')})
        digest = hashlib.sha256()
        if dump.is_file() and not dump.is_symlink():
            with dump.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            entry['local_hash_and_size_verified'] = digest.hexdigest() == record.get('sha256') and dump.stat().st_size == record.get('bytes')
        else:
            entry['local_hash_and_size_verified'] = False
        result['latest_local_backup'] = entry
    export = BACKUP / 'source-export-receipt.json'
    if export.is_file() and not export.is_symlink() and export.stat().st_size < 16384:
        record = json.loads(export.read_text())
        result['previous_source_export'] = {
            'source_export_succeeded': record.get('source_export_succeeded') if type(record.get('source_export_succeeded')) is bool else None,
            'reason': record.get('reason') if record.get('reason') in ('exported', 'provider_account_limit', 'export_unavailable') else 'unrecognized',
            'bytes': record.get('bytes') if type(record.get('bytes')) is int and record['bytes'] >= 0 else None}
    return result


def collect():
    before = numbers('/proc/vmstat')
    cpu_before = [int(value) for value in text('/proc/stat').splitlines()[0].split()[1:9]]
    time.sleep(3)
    after = numbers('/proc/vmstat')
    cpu_after = [int(value) for value in text('/proc/stat').splitlines()[0].split()[1:9]]
    cpu_total = sum(cpu_after) - sum(cpu_before)
    cpu_idle = sum(cpu_after[3:5]) - sum(cpu_before[3:5])
    allowed = ('MemTotal', 'MemAvailable', 'MemFree', 'Buffers', 'Cached', 'AnonPages', 'SwapCached', 'SwapTotal', 'SwapFree')
    memory = numbers('/proc/meminfo')
    report = {'mode': 'read_only_no_database_or_provider_requests',
              'collected_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'host_memory_bytes': {key: memory[key] * 1024 for key in allowed if key in memory},
              'swap_activity': {'sample_seconds': 3, 'page_bytes': os.sysconf('SC_PAGE_SIZE'),
                  **{key + '_delta': after.get(key, 0) - before.get(key, 0) for key in ('pswpin', 'pswpout', 'pgmajfault')}},
              'memory_pressure': text('/proc/pressure/memory').splitlines(),
              'load_average': list(os.getloadavg()), 'containers': []}
    report['cpu'] = {'logical_count': os.cpu_count(), 'sample_seconds': 3,
                     'busy_percent': round(100 * (1 - cpu_idle / cpu_total), 2) if cpu_total else None}
    groups = []
    # Raw config remains in this process; no raw JSON/log exception is printed.
    ids = run('docker', 'ps', '-aq').split()
    for identity in ids:
        obj = json.loads(run('docker', 'inspect', identity))[0]
        report['containers'].append(project(obj, groups))
    report['container_stats'] = [
        {key: item.get(key) for key in ('Name', 'MemUsage', 'MemPerc', 'CPUPerc', 'PIDs')}
        for line in run('docker', 'stats', '--no-stream', '--format', '{{json .}}').splitlines()
        if (item := json.loads(line))]
    report['networks'] = []
    for name in sorted({name for row in report['containers'] for name in row['networks']}):
        info = json.loads(run('docker', 'network', 'inspect', name))[0]
        report['networks'].append({key: info.get(key) for key in ('Name', 'Driver', 'Internal')})
    logs = subprocess.run(['docker', 'logs', '--tail', '160', API], capture_output=True,
                          text=True, timeout=20, check=True)
    report['api_existing_log_categories'] = category(logs.stdout + logs.stderr)
    # /health is liveness only in the installed and candidate source. Never /health/db.
    code = "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3); p=json.load(r); print(json.dumps({'http_status':r.status,'healthy':p.get('status')=='healthy'}))"
    try:
        report['api_liveness'] = json.loads(run('docker', 'exec', API, 'python', '-B', '-c', code))
    except Exception:
        report['api_liveness'] = {'healthy': False, 'read_failed': True}
    report['backup'] = backups()
    report['limitations'] = ['Low-load sample is not a load/capacity approval.',
        'Memory limits/reservations are configuration, not allocated RAM.',
        'Cgroup current includes cache/kernel; Docker usage generally excludes inactive file cache.',
        'Swap occupancy does not establish active swapping; see sampled page deltas/PSI.',
        'No SQL/export/IAM retry, provider request, restart or configuration change.',
        'No external backup upload/readback or fresh production restore is certified.']
    return report


if __name__ == '__main__':
    try:
        print(json.dumps(collect(), indent=2))
    except Exception as error:
        print(json.dumps({'complete': False, 'error_type': type(error).__name__}))
        raise SystemExit(1)
