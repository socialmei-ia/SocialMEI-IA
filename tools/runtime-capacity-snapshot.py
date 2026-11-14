#!/usr/bin/env python3
"""Run on the Linux host over SSH; emit only allowlisted runtime metadata.

No AWS API, SQL, provider request, configuration dump or runtime mutation.
Docker inspect is projected by Go templates before any output is captured.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import time


NETWORK_TEMPLATE = ('{"name":{{json .Name}},"internal":{{.Internal}},'
                    '"driver":{{json .Driver}}}')
CONTAINER_TEMPLATE = (
    '{"name":{{json .Name}},"image_id":{{json .Image}},'
    '"state":{{json .State.Status}},'
    '"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}},'
    '"restart_count":{{.RestartCount}},"memory_limit_bytes":{{.HostConfig.Memory}},'
    '"revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}},'
    '"networks":[{{range $i, $v := .NetworkSettings.Networks}}{{json $i}},{{end}}null]}')


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          timeout=20).stdout.strip()


def safe_name(value):
    return value if re.fullmatch(r"[a-zA-Z0-9_.-]{1,160}", value) else None


def safe_revision(value):
    return value if re.fullmatch(r"[0-9a-f]{40}", value or "") else None


def cpu_sample():
    values = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
    # guest fields are already included in user/nice.
    return sum(values[:8]), values[3] + values[4]


def collect():
    first = cpu_sample()
    time.sleep(1)
    second = cpu_sample()
    total = second[0] - first[0]
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
            memory[key] = int(value.split()[0]) * 1024
    disk = os.statvfs('/')
    result = {
        'collected_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'scope': 'read-only host and Docker metadata; no database or provider requests',
        'cpu': {'logical_count': os.cpu_count(), 'sample_seconds': 1,
                'busy_percent': round(100 * (1 - (second[1] - first[1]) / total), 2) if total else None,
                'load_average': list(os.getloadavg())},
        'memory_bytes': memory,
        'root_filesystem_bytes': {'total': disk.f_blocks * disk.f_frsize,
                                  'available': disk.f_bavail * disk.f_frsize},
        'containers': [],
    }
    ids = run('docker', 'ps', '-aq').splitlines()
    for identity in ids:
        row = json.loads(run('docker', 'inspect', '--format', CONTAINER_TEMPLATE, identity))
        row['name'] = safe_name(row['name'].lstrip('/'))
        row['revision'] = safe_revision(row['revision'])
        row['networks'] = [safe_name(n) for n in row['networks'] if n]
        result['containers'].append(row)
    result['container_counts'] = {
        'total': len(ids), 'running': sum(r['state'] == 'running' for r in result['containers'])}
    stats = []
    for line in run('docker', 'stats', '--no-stream', '--format', '{{json .}}').splitlines():
        entry = json.loads(line)
        stats.append({key: entry.get(key) for key in ('CPUPerc', 'MemUsage', 'MemPerc')}
                     | {'name': safe_name(entry.get('Name', ''))})
    result['container_stats'] = stats
    networks = sorted({n for row in result['containers'] for n in row['networks'] if n})
    result['networks'] = [json.loads(run('docker', 'network', 'inspect', '--format',
        NETWORK_TEMPLATE, n))
        for n in networks]
    # Hash only tracked application code, never configuration or environment.
    code = ("import hashlib,json,pathlib; "
            "files=['app.py','account_auth.py','database.py']; "
            "print(json.dumps({n:hashlib.sha256(pathlib.Path('/app',n).read_bytes()).hexdigest() "
            "for n in files if pathlib.Path('/app',n).is_file()}))")
    result['api_source_sha256'] = json.loads(run('docker', 'exec',
        'socialmei-team-team-api-1', 'python', '-B', '-c', code))
    result['limitations'] = [
        'Single low-load sample; no sustained-load capacity certification.',
        'Revision label is image metadata; code hashes identify selected effective files only.',
        'No IAM retry; known EC2/S3 access and external-backup gates remain unresolved.',
        'No database health query, credentials, logs, customer data or configuration collected.',
    ]
    return result


if __name__ == '__main__':
    try:
        print(json.dumps(collect(), indent=2))
    except Exception as error:
        # Command output can contain private material; keep errors structural.
        print(json.dumps({'complete': False, 'error_type': type(error).__name__}))
        raise SystemExit(1)
