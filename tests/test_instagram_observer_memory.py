"""Opt-in local TLS benchmark; synthetic data, owned resources and no external network."""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import unittest
from urllib.parse import urlencode


def docker(*args, data=None, timeout=30):
    result = subprocess.run(['docker', *args], input=data, capture_output=True, timeout=timeout)
    if result.returncode: raise RuntimeError('isolated_observer_benchmark_failed:' + args[0])
    return result.stdout


def inspect(name): return json.loads(docker('inspect', name))[0]


def until(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(.5)
    raise AssertionError('isolated_observer_condition_timeout')


@unittest.skipUnless(os.getenv('SOCIALMEI_IG_MEMORY_TESTS') == '1', 'Explicit local TLS benchmark required')
class ObserverMemoryTests(unittest.TestCase):
    def test_two_workspaces_tls_memory_isolation_and_restart(self):
        self.assertTrue(json.loads(docker('context', 'inspect'))[0]['Endpoints']['docker']['Host'].startswith(('unix://', 'npipe://')))
        self.assertFalse(os.getenv('DOCKER_HOST', '').startswith(('tcp:', 'ssh:')))
        images = {phase: os.environ['SOCIALMEI_IG_MEMORY_' + phase.upper() + '_IMAGE'] for phase in ('baseline', 'optimized')}
        for image in images.values():
            self.assertRegex(image, r'^sha256:[0-9a-f]{64}$'); self.assertEqual(inspect(image)['Id'], image)
        postgres = inspect('postgres:17-alpine')['Id']
        token = secrets.token_hex(8); db = 'socialmei-ig-memory-db-' + token
        created = []; volumes = []; measurements = {}
        def sql(query):
            return docker('exec', '-i', db, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'observer_memory_test', data=query.encode()).decode().strip()
        def own(name): self.assertEqual(inspect(name)['Config']['Labels'].get('socialmei.observer-memory'), token)
        def state(name): return json.loads(docker('exec', name, 'cat', '/run/socialmei/instagram-menu-state/state.json'))
        def healthy(name): return inspect(name)['State'].get('Health', {}).get('Status') == 'healthy'
        with tempfile.TemporaryDirectory(prefix='socialmei-observer-memory-') as tmp:
            try:
                docker('create', '--name', db, '--label', 'socialmei.observer-memory=' + token, '--network', 'none', '--user', 'postgres', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '512m', '--cpus', '0.5', '--restart', 'no', '--tmpfs', '/var/lib/postgresql/data:rw,size=256m,mode=1777', '--tmpfs', '/var/run/postgresql:rw,size=16m,mode=1777', '--tmpfs', '/tmp:rw,size=16m,mode=1777', '-e', 'PGDATA=/var/lib/postgresql/data/pgdata', '-e', 'POSTGRES_USER=postgres', '-e', 'POSTGRES_DB=observer_memory_test', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', postgres)
                created.append(db); docker('start', db)
                until(lambda: subprocess.run(['docker', 'exec', db, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], capture_output=True).returncode == 0)
                key, cert = Path(tmp) / 'server.key', Path(tmp) / 'server.crt'
                openssl = shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
                subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1', '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True, env=dict(os.environ, MSYS_NO_PATHCONV='1'), timeout=30)
                for filename, data in [('server.key', key.read_bytes()), ('server.crt', cert.read_bytes()), ('pg_hba.conf', b'local all all trust\nhostssl all all 127.0.0.1/32 trust\nhostnossl all all 0.0.0.0/0 reject\n')]:
                    docker('exec', '-i', db, 'sh', '-c', 'umask 077; cat > "$PGDATA/' + filename + '"', data=data)
                for query in ["ALTER SYSTEM SET ssl='on'", "ALTER SYSTEM SET ssl_cert_file='/var/lib/postgresql/data/pgdata/server.crt'", "ALTER SYSTEM SET ssl_key_file='/var/lib/postgresql/data/pgdata/server.key'", "ALTER SYSTEM SET log_connections='on'", 'SELECT pg_reload_conf()']:
                    sql(query)
                sql("""CREATE SCHEMA socialmei;
CREATE TABLE socialmei.me_messages(workspace_id bigint,id bigint,origin text,occurred_at timestamptz);
CREATE TABLE socialmei.ig_meta_connections(workspace_id bigint,id uuid,external_account_id text);
CREATE TABLE socialmei.ig_meta_ingress_events(workspace_id bigint,message_id bigint,connection_id uuid,external_account_id text,kind text,status text,received_at timestamptz);
CREATE TABLE socialmei.ig_menu_replies(workspace_id bigint,source_message_id bigint);
INSERT INTO socialmei.ig_meta_connections VALUES(60,'00000000-0000-0000-0000-000000000060','606060'),(61,'00000000-0000-0000-0000-000000000061','616161');
INSERT INTO socialmei.me_messages SELECT w,id,'instagram',NOW() FROM (VALUES(60,1000),(61,2000)) s(w,n),LATERAL generate_series(1,n) g(id);
INSERT INTO socialmei.ig_meta_ingress_events SELECT m.workspace_id,m.id,c.id,c.external_account_id,'message','processed',NOW() FROM socialmei.me_messages m JOIN socialmei.ig_meta_connections c USING(workspace_id);
CREATE INDEX ON socialmei.me_messages(workspace_id,id); CREATE INDEX ON socialmei.ig_meta_ingress_events(workspace_id,message_id);
""")
                for phase, image in images.items():
                    names = []; stats = {}; limit = 128 if phase == 'baseline' else 72
                    def sample(name):
                        status = docker('exec', name, 'cat', '/proc/1/status').decode()
                        values = {'rss_peak_bytes': int(re.search(r'^VmRSS:\s+(\d+)', status, re.M)[1]) * 1024, 'process_hwm_bytes': int(re.search(r'^VmHWM:\s+(\d+)', status, re.M)[1]) * 1024, 'cgroup_peak_bytes': int(docker('exec', name, 'cat', '/sys/fs/cgroup/memory.peak'))}
                        entry = stats.setdefault(name, dict.fromkeys(values, 0))
                        for key, value in values.items(): entry[key] = max(entry[key], value)
                    for workspace in (60, 61):
                        name = 'socialmei-ig-memory-' + token + '-' + phase + '-' + str(workspace)
                        volume = name + '-state'; docker('volume', 'create', '--label', 'socialmei.observer-memory=' + token, volume); volumes.append(volume)
                        query = urlencode({'sslmode':'verify-full', 'sslrootcert':'/run/database-ca.crt', 'application_name':'observer-memory-' + phase + '-' + str(workspace)})
                        env = Path(tmp) / (phase + str(workspace) + '.env')
                        env.write_text('\n'.join(['DATABASE_URL=postgresql://postgres@127.0.0.1:5432/observer_memory_test?' + query, 'SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME=observer_memory_test', 'SOCIALMEI_INSTAGRAM_WORKER_MODE=observe', 'SOCIALMEI_QUEUE_WAKEUP_MODE=poll', 'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED=false', 'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false', 'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID=' + str(workspace), 'SOCIALMEI_INSTAGRAM_AUTO_MENU_START_UTC=2026-01-01T00:00:00+00:00']), encoding='utf-8')
                        docker('create', '--name', name, '--label', 'socialmei.observer-memory=' + token, '--network', 'container:' + db, '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', str(limit) + 'm', '--memory-swap', str(limit) + 'm', '--cpus', '0.25', '--pids-limit', '64', '--restart', 'unless-stopped', '--tmpfs', '/tmp:size=8m', '--env-file', str(env), '--mount', 'type=volume,src=' + volume + ',dst=/run/socialmei/instagram-menu-state', '--mount', 'type=bind,src=' + str(cert) + ',dst=/run/database-ca.crt,readonly', '--health-cmd', 'python -m instagram_worker_health', '--health-interval', '1s', '--health-start-period', '5s', image, 'python', '-u', '/app/instagram-auto-menu-worker.py')
                        created.append(name); names.append(name); docker('start', name); until(lambda: healthy(name))
                        self.assertEqual(state(name)['pending_count'], 1000 if workspace == 60 else 2000)
                        self.assertFalse(state(name)['send_enabled']); sample(name)
                    self.assertTrue(sql("SELECT count(*),bool_and(ssl) FROM pg_stat_activity a JOIN pg_stat_ssl s USING(pid) WHERE application_name LIKE 'observer-memory-" + phase + "-%'").endswith('|t'))
                    sql("INSERT INTO socialmei.me_messages VALUES(60,1001,'instagram',NOW()); INSERT INTO socialmei.ig_meta_ingress_events SELECT 60,1001,id,external_account_id,'message','processed',NOW() FROM socialmei.ig_meta_connections WHERE workspace_id=60")
                    until(lambda: state(names[0])['pending_count'] == 1001, timeout=25)
                    self.assertEqual(state(names[1])['pending_count'], 2000)
                    for name in names:
                        sample(name)
                        self.assertEqual(inspect(name)['RestartCount'], 0)
                        self.assertEqual(inspect(name)['HostConfig']['MemorySwap'], inspect(name)['HostConfig']['Memory'])
                    old = [inspect(n)['State']['StartedAt'] for n in names]
                    docker('restart', '--time', '2', names[0]); until(lambda: healthy(names[0]))
                    self.assertNotEqual(inspect(names[0])['State']['StartedAt'], old[0]); self.assertEqual(inspect(names[1])['State']['StartedAt'], old[1])
                    self.assertEqual(state(names[0])['pending_count'], 1001)
                    old = [inspect(n)['State']['StartedAt'] for n in names]
                    sql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name LIKE 'observer-memory-" + phase + "-%'")
                    until(lambda: all(inspect(n)['State']['StartedAt'] != stamp and healthy(n) for n, stamp in zip(names, old)), timeout=40)
                    for name in names:
                        self.assertFalse(inspect(name)['State']['OOMKilled']); sample(name); self.assertFalse(state(name)['send_enabled'])
                    logs = subprocess.run(['docker','logs',db], capture_output=True, text=True, check=True).stderr
                    opened = sum('connection authorized:' in line and 'application_name=observer-memory-' + phase + '-' in line for line in logs.splitlines())
                    measurements[phase] = {'image_id':image, 'limit_per_worker_mib':limit, 'workers':list(stats.values()), 'tls_verified':True, 'backend_connections_opened':opened, 'independent_restart':True, 'database_disconnect_recovered':True, 'provider_requests':0, 'swap_disabled':True}
                    for name in reversed(names): own(name); docker('rm','-f','-v',name); created.remove(name)
                    sql('DELETE FROM socialmei.ig_meta_ingress_events WHERE workspace_id=60 AND message_id=1001; DELETE FROM socialmei.me_messages WHERE workspace_id=60 AND id=1001')
                self.assertLess(measurements['optimized']['backend_connections_opened'], measurements['baseline']['backend_connections_opened'])
                self.assertTrue(all(row['cgroup_peak_bytes'] < 64 * 1024**2 for row in measurements['optimized']['workers']), '72MiB cap requires at least8MiB measured headroom')
            finally:
                for name in reversed(created): own(name); docker('rm','-f','-v',name)
                for volume in reversed(volumes):
                    self.assertEqual(json.loads(docker('volume','inspect',volume))[0]['Labels']['socialmei.observer-memory'], token)
                    docker('volume','rm',volume)
        measurements.update(owned_cleanup_verified=True, production_modified=False, network='none', synthetic_messages=3000)
        evidence = os.getenv('SOCIALMEI_IG_MEMORY_EVIDENCE')
        if evidence: Path(evidence).write_text(json.dumps(measurements, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(measurements))


if __name__ == '__main__': unittest.main()