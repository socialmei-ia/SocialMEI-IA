"""Execute only the explicitly approved immutable Brilho observer pilot."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time

APPROVED = '30ab1ec0c97d34c651102daf9a74e3597c1ac09c3cdfa6d3e9ea748e9a6957c8'
PROJECT = 'socialmei-instagram-observers'
VOLUME = PROJECT + '_brilho-state'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def call(args, *, timeout=30, env=None):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
    require(result.returncode == 0, 'command_failed_' + args[0])
    return result.stdout


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace('-', '_'), path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def private(path, value):
    data = json.dumps(value, sort_keys=True, indent=2).encode() + b'\n'
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def memory():
    values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(values['MemAvailable'].split()[0]) // 1024


def validate_container(row, image, network):
    labels = row['Config'].get('Labels') or {}
    config = row['HostConfig']
    env = dict(item.split('=', 1) for item in row['Config']['Env'])
    require(labels.get('com.docker.compose.project') == PROJECT
            and labels.get('com.docker.compose.service') == 'brilho-observer'
            and row['Image'] == image, 'container_scope_mismatch')
    require(config['Memory'] == 72 * 1024**2 and config['MemorySwap'] == config['Memory']
            and config['ReadonlyRootfs'] and config['PidsLimit'] == 64
            and config['NanoCpus'] == 250000000 and config['CapDrop'] == ['ALL']
            and not config.get('PortBindings') and not config.get('Privileged'), 'container_limits_mismatch')
    require(set(row['NetworkSettings']['Networks']) == {network}, 'container_network_mismatch')
    require(env.get('SOCIALMEI_INSTAGRAM_WORKER_MODE') == 'observe'
            and env.get('SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID') == '60'
            and env.get('SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES') == '60'
            and env.get('SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED') == 'false'
            and env.get('SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED') == 'false'
            and env.get('SOCIALMEI_QUEUE_WAKEUP_MODE') == 'poll', 'observer_mode_mismatch')
    state = [v for v in row['Mounts'] if v['Destination'] == '/run/socialmei/instagram-menu-state']
    require(len(state) == 1 and state[0]['Type'] == 'volume' and state[0]['Name'] == VOLUME,
            'state_volume_mismatch')
    require(not any(key for key in env if any(word in key.upper() for word in
                ('SMTP', 'WAHA', 'N8N', 'META_', 'CLIENT_SECRET', 'TOKEN_VAULT'))), 'provider_secret_present')


class Pilot:
    def __init__(self, root):
        self.root = root
        self.plan = json.loads((root / 'approved-plan.json').read_text())
        frozen = dict(self.plan)
        require(frozen.pop('plan_sha256') == APPROVED and digest(frozen) == APPROVED, 'plan_hash_mismatch')
        for name, expected in self.plan['reviewed_tools_sha256'].items():
            require(hashlib.sha256((root / name.replace('\\', '/')).read_bytes()).hexdigest() == expected,
                    'reviewed_source_mismatch')
        self.compose = root / 'deploy/team/compose.instagram-observers.yaml'
        require(hashlib.sha256(self.compose.read_bytes()).hexdigest() == self.plan['compose_sha256'], 'compose_mismatch')
        self.gate = module(root / 'tools/instagram-observer-pilot.py')
        self.db = module(root / 'tools/instagram-worker-database.py')
        self.container = None
        self.environment = None

    def rows(self):
        ids = call(['docker', 'ps', '-aq']).split()
        return json.loads(call(['docker', 'inspect', *ids]))

    def baseline(self):
        rows = self.rows()
        fresh = self.gate.plan(rows, memory(), False, self.plan['compose_sha256'])
        require(fresh['runtime_fingerprints'] == self.plan['runtime_fingerprints'], 'runtime_changed')
        require(fresh['blockers'] == ['exact_image_not_loaded'], 'capacity_or_duplicate_worker')
        require(shutil.disk_usage(self.root).free >= 512 * 1024**2, 'disk_margin_insufficient')
        units = call(['systemctl', 'list-units', '--type=service', '--state=running', '--no-legend'])
        require(not any('040' in row and 'backup' in row for row in units.splitlines()), 'backup_cycle_running')
        info = json.loads(call(['docker', 'info', '--format', '{{json .}}']))
        require(info.get('MemoryLimit') and info.get('SwapLimit'), 'docker_limits_unavailable')
        return rows

    def compose_call(self, *arguments):
        return call(['docker', 'compose', '-f', str(self.compose), '--profile', 'instagram-observers',
                     *arguments], env=self.environment, timeout=60)

    def start(self):
        require(not (self.root / 'activation.private.json').exists(), 'reconcile_existing_activation')
        rows = self.baseline()
        private(self.root / 'runtime-before.private.json', rows)
        before = {r['Id']: {'running': r['State']['Running'], 'restarts': r['RestartCount'],
                           'health': r['State'].get('Health', {}).get('Status')} for r in rows}
        require(VOLUME not in call(['docker', 'volume', 'ls', '--format', '{{.Name}}']).splitlines(),
                'state_volume_already_exists')
        archive = self.root / 'original-image.tar'
        require(archive.stat().st_size == self.plan['archive_bytes'], 'archive_size_mismatch')
        with archive.open('rb') as stream:
            require(hashlib.file_digest(stream, 'sha256').hexdigest() == self.plan['archive_sha256'], 'archive_mismatch')
        oci = module(self.root / 'tools/team-oci-image-identity.py')
        tag = 'socialmei/instagram-observer:' + self.plan['image_source_commit']
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            require(len({v.name for v in members}) == len(members), 'duplicate_archive_members')
            oci.verify_oci_archive_identity(tar, {v.name: v for v in members},
                json.load(tar.extractfile('manifest.json')), {tag: {'image_id': self.plan['image_id']}},
                self.plan['image_source_commit'])
        start = datetime.now(timezone.utc).isoformat()
        preparation = self.db.prepare(self.root / 'prepared', start_utc=start)
        require(preparation['database_ca_copied'], 'verify_full_ca_required')
        api = next(r for r in rows if r['Name'] == '/' + self.gate.API)
        db = json.loads(call(['docker', 'inspect', self.db.HOST]))[0]
        networks = set(api['NetworkSettings']['Networks']) & set(db['NetworkSettings']['Networks'])
        require(len(networks) == 1, 'database_network_ambiguous')
        self.network = networks.pop()
        probe = """import json
from database import connect
with connect() as c:
 c.execute('SET TRANSACTION READ ONLY')
 c.execute("SET LOCAL statement_timeout='5s'")
 row=c.execute("SELECT current_database(),to_regclass('socialmei.ig_meta_ingress_events') IS NOT NULL,to_regclass('socialmei.ig_menu_replies') IS NOT NULL,pg_try_advisory_lock(hashtextextended('instagram-menu-worker:60',0))").fetchone()
 print(json.dumps(list(row)))
"""
        identity = json.loads(call(['docker', 'exec', self.gate.API, 'python', '-c', probe]))
        require(identity == [self.db.DATABASE, True, True, True], 'database_or_lease_mismatch')
        self.baseline()
        call(['docker', 'load', '-i', str(archive)], timeout=180)
        loaded = json.loads(call(['docker', 'image', 'inspect', self.plan['image_id']]))[0]
        require(loaded['Id'] == self.plan['image_id'] and loaded['Config']['Labels'].get(
            'org.opencontainers.image.revision') == self.plan['image_source_commit'], 'loaded_image_mismatch')
        self.environment = dict(os.environ, INSTAGRAM_REVIEWED_WORKER_IMAGE=self.plan['image_id'],
            INSTAGRAM_BRILHO_ENV_FILE=str(self.root / 'prepared/workspace60.env'),
            INSTAGRAM_BELLA_ENV_FILE=str(self.root / 'prepared/workspace61.env'),
            INSTAGRAM_REVIEWED_DATABASE_CA_FILE=str(self.root / 'prepared/database-ca.crt'),
            INSTAGRAM_REVIEWED_DATABASE_NETWORK=self.network)
        model = json.loads(self.compose_call('config', '--format', 'json', 'brilho-observer'))
        require(set(model['services']) == {'brilho-observer'}, 'compose_scope_mismatch')
        private(self.root / 'rendered-compose.private.json', model)
        self.baseline()
        self.compose_call('create', '--no-build', '--pull', 'never', 'brilho-observer')
        self.container = self.compose_call('ps', '-aq', 'brilho-observer').strip()
        require(len(self.container) == 64, 'exact_new_container_required')
        row = json.loads(call(['docker', 'inspect', self.container]))[0]
        validate_container(row, self.plan['image_id'], self.network)
        volume = next(v for v in row['Mounts'] if v['Destination'] == '/run/socialmei/instagram-menu-state')
        require(not list(Path(volume['Source']).iterdir()), 'state_volume_not_empty')
        require(memory() >= 520, 'pre_start_memory_insufficient')
        private(self.root / 'activation.private.json', {'container_id': self.container, 'plan_sha256': APPROVED,
            'start_utc': start, 'state_volume': VOLUME, 'before': before, 'network': self.network})
        self.compose_call('up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'brilho-observer')
        return self.container

    def sample(self, *, warming=False):
        activation = json.loads((self.root / 'activation.private.json').read_text())
        rows = self.rows()
        by_id = {r['Id']: r for r in rows}
        for identifier, baseline in activation['before'].items():
            row = by_id[identifier]
            require(row['State']['Running'] == baseline['running'] and row['RestartCount'] == baseline['restarts'],
                    'existing_service_changed')
            require(baseline['health'] != 'healthy' or row['State'].get('Health', {}).get('Status') == 'healthy',
                    'existing_service_unhealthy')
        row = by_id[self.container]
        validate_container(row, self.plan['image_id'], activation['network'])
        require(row['State']['Running'] and not row['State'].get('OOMKilled') and row['RestartCount'] == 0,
                'observer_unstable')
        available = memory()
        require(available >= 448, 'runtime_memory_below_backup_plus_reserve')
        status = row['State'].get('Health', {}).get('Status')
        require(status == 'healthy' or (warming and status == 'starting'), 'observer_not_healthy')
        stats = json.loads(call(['docker', 'stats', '--no-stream', '--format', '{{json .}}', self.container]))
        return {'at': datetime.now(timezone.utc).isoformat(), 'available_mib': available,
                'health': status, 'restarts': row['RestartCount'], 'memory_usage': stats['MemUsage']}

    def rollback(self, reason):
        if self.container:
            row = json.loads(call(['docker', 'inspect', self.container]))[0]
            labels = row['Config'].get('Labels') or {}
            require(labels.get('com.docker.compose.project') == PROJECT
                    and labels.get('com.docker.compose.service') == 'brilho-observer', 'rollback_scope_mismatch')
            call(['docker', 'stop', '--time', '15', self.container])
        private(self.root / 'result.private.json', {'complete': False, 'reason': reason,
            'observer_stopped': bool(self.container), 'volumes_preserved': True, 'other_services_modified': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--approved-plan', required=True)
    args = parser.parse_args()
    require(args.approved_plan == APPROVED, 'explicit_approved_plan_required')
    pilot = Pilot(args.directory.resolve())
    try:
        identifier = pilot.start()
        samples = []
        for index in range(21):
            samples.append(pilot.sample(warming=index < 6))
            private(pilot.root / 'monitor.private.json', samples)
            if index < 20:
                time.sleep(15)
        private(pilot.root / 'result.private.json', {'complete': True, 'phase': 'five_minute_monitor_passed',
            'container_id': identifier, 'plan_sha256': APPROVED, 'samples': samples,
            'send_enabled': False, 'bella_started': False, 'other_services_modified': False,
            'thirty_minute_check_pending': True})
        print('BRILHO_OBSERVER_FIVE_MINUTE_MONITOR_PASSED', flush=True)
        # Runs on EC2 after SSH disconnect; no notebook or timer dependency.
        for _ in range(25):
            time.sleep(60)
            samples.append(pilot.sample())
            private(pilot.root / 'monitor.private.json', samples)
        private(pilot.root / 'result.private.json', {'complete': True, 'phase': 'thirty_minute_monitor_passed',
            'container_id': identifier, 'plan_sha256': APPROVED, 'samples': samples,
            'send_enabled': False, 'bella_started': False, 'other_services_modified': False,
            'thirty_minute_check_pending': False})
        print('BRILHO_OBSERVER_THIRTY_MINUTE_MONITOR_PASSED', flush=True)
    except Exception as error:
        reason = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        pilot.rollback(reason)
        print('BRILHO_OBSERVER_BLOCKED_OR_STOPPED ' + reason, flush=True)
        raise SystemExit(1)
