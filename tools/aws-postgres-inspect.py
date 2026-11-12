#!/usr/bin/env python3
"""Read-only inventory for database relocation; never print connection secrets."""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


def run(args, timeout=20):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def source_identity(env):
    explicit = env.get('DATABASE_URL', '').strip()
    host = urlsplit(explicit).hostname if explicit else env.get('POSTGRES_HOST', '')
    return {'explicit_url': bool(explicit),
            'provider': 'prisma' if host and host.endswith('.prisma.io') else 'other',
            'host_fingerprint': hashlib.sha256((host or '').encode()).hexdigest(),
            'connection_fingerprint': hashlib.sha256(json.dumps(
                {'url': explicit} if explicit else {k: env.get(k) for k in
                 ('POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD')},
                sort_keys=True).encode()).hexdigest()}


def inventory():
    report = {'mode': 'read_only', 'collected_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    report['capacity'] = {'cpu_count': os.cpu_count(), 'load_average': os.getloadavg(),
                          'memory_kib': {key: int(mem[key].split()[0]) for key in
                                         ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')},
                          'disk_bytes': dict(zip(('total', 'used', 'free'), shutil.disk_usage('/')))}
    report['tools'] = {name: bool(shutil.which(name)) for name in ('aws', 'pg_dump', 'pg_restore', 'docker', 'restic')}
    report['python_modules'] = {name: importlib.util.find_spec(name) is not None for name in ('boto3', 'psycopg')}
    report['containers'] = []
    names = (run(['docker', 'ps', '-a', '--format', '{{.Names}}']) or '').splitlines()
    for name in names:
        raw = run(['docker', 'inspect', name])
        if not raw:
            continue
        obj = json.loads(raw)[0]
        env = dict(item.split('=', 1) for item in obj.get('Config', {}).get('Env', []) if '=' in item)
        host = obj.get('HostConfig', {})
        entry = {'name': name, 'image_id': obj.get('Image'), 'running': obj['State']['Running'],
                 'memory_limit_bytes': host.get('Memory'),
                 'networks': sorted(obj.get('NetworkSettings', {}).get('Networks', {})),
                 'port_bindings': host.get('PortBindings'),
                 'database': source_identity(env) if any(k in env for k in ('DATABASE_URL', 'POSTGRES_HOST')) else None}
        report['containers'].append(entry)
    report['backups'] = []
    for base, dirs, files in os.walk('/home/ubuntu'):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '.npm', '.cache', '.local', '.rustup', '.cargo')]
        for name in files:
            if name.endswith(('.dump', '.dump.gz', '.sql.gz', '.backup', '.pgdump', '.bak')):
                path = Path(base) / name
                try:
                    stat = path.stat()
                    report['backups'].append({'path': str(path), 'size': stat.st_size,
                                              'mtime_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(stat.st_mtime))})
                except OSError:
                    pass
    report['backups'].sort(key=lambda row: row['mtime_utc'], reverse=True)
    report['recovery_artifacts'] = {}
    for folder in ('/home/ubuntu/.socialmei-instagram-86cdd5b', '/home/ubuntu/socialmei-prisma-migration-20261109'):
        report['recovery_artifacts'][folder] = [str(p.relative_to(folder)) for p in Path(folder).rglob('*')
            if p.is_file() and p.suffix in ('.json', '.py', '.sql', '.env', '.dump')][:100]
    report['metadata'] = {'available': False}
    try:
        request = urllib.request.Request('http://169.254.169.254/latest/api/token', method='PUT',
                    headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'})
        token = urllib.request.urlopen(request, timeout=2).read().decode()
        def meta(path):
            req = urllib.request.Request('http://169.254.169.254/latest/' + path,
                                         headers={'X-aws-ec2-metadata-token': token})
            return urllib.request.urlopen(req, timeout=2).read().decode()
        doc = json.loads(meta('dynamic/instance-identity/document'))
        report['metadata'] = {key: doc.get(key) for key in ('instanceType', 'region', 'availabilityZone')}
        report['metadata']['available'] = True
        report['metadata']['iam_role_available'] = bool(meta('meta-data/iam/security-credentials/'))
    except Exception:
        pass
    return report


if __name__ == '__main__':
    print(json.dumps(inventory(), indent=2))
