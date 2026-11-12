#!/usr/bin/env python3
"""Sanitized postflight of the isolated relocation and unchanged production."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/ubuntu/.socialmei-postgres-relocation-20261112')
DB = 'socialmei-postgres-relocation-20261112'


def run(args):
    value = subprocess.run(args, capture_output=True, timeout=25)
    return value.stdout if value.returncode == 0 else None


def collect():
    result = {'collected_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'production_cutover_executed': False, 'production_connections_changed': False,
              'new_migrations_executed': False}
    unchanged = {}
    for kind, container in (('api', 'socialmei-team-team-api-1'),
                            ('whatsapp-menu', 'socialmei-menu-public-api-v3'),
                            ('instagram-worker', 'socialmei-instagram-menu-worker')):
        before = json.loads((ROOT / (kind + '-production-before.private.json')).read_text())
        after = json.loads(run(['docker', 'inspect', container]))[0]
        unchanged[kind] = all(before.get(key) == after.get(key) for key in
            ('Image', 'Config', 'HostConfig', 'Mounts'))
    result['production_configuration_unchanged'] = unchanged
    obj = json.loads(run(['docker', 'inspect', DB]))[0]
    network = json.loads(run(['docker', 'network', 'inspect', DB + '-isolated']))[0]
    result['destination'] = {'running': obj['State']['Running'],
        'image_id': obj['Image'], 'public_ports': bool(obj['HostConfig'].get('PortBindings')),
        'only_isolated_network': sorted(obj['NetworkSettings']['Networks']) == [DB + '-isolated'],
        'internal_network': network['Internal'], 'memory_limit_bytes': obj['HostConfig']['Memory'],
        'no_new_privileges': 'no-new-privileges' in obj['HostConfig'].get('SecurityOpt', [])}
    database_info = run(['docker', 'exec', DB, 'psql', '-XAt', '-U', 'relocation_admin',
        '-d', 'socialmei_relocation', '-c', "SELECT json_build_object('server_version_num',current_setting('server_version_num'),'database_bytes',pg_database_size(current_database()),'data_checksums',current_setting('data_checksums'))::text"])
    result['destination']['database_info'] = json.loads(database_info)
    for name in ('security-receipt', 'source-export-receipt', 'restore-portable-receipt',
                 'restore-validation-receipt', 'consumer-connection-receipt', 'api-smoke-receipt', 'tls-negative-receipt'):
        result[name] = json.loads((ROOT / (name + '.json')).read_text())
    timer = 'socialmei-postgres-relocation-backup.timer'
    result['backup_timer_active'] = (run(['systemctl', 'is-active', timer]) or b'').strip() == b'active'
    result['backup_service_result'] = (run(['systemctl', 'show', 'socialmei-postgres-relocation-backup.service',
                                         '--property=Result', '--value']) or b'unknown').decode().strip()
    mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    result['host_memory_available_kib'] = int(mem['MemAvailable'].split()[0])
    result['s3_configured'] = (ROOT / 's3-backup.private.json').is_file()
    return result


if __name__ == '__main__':
    try:
        report = collect()
        print(json.dumps(report, indent=2))
        if (not all(report['production_configuration_unchanged'].values())
                or report['destination']['public_ports']
                or not report['destination']['internal_network']):
            raise SystemExit(2)
    except Exception:
        raise SystemExit('Postflight unavailable; inspect private receipts without printing secrets.') from None
