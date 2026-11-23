"""Opt-in local observer restart test against the guarded disposable database."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import unittest
from urllib.parse import quote


def run(*args):
    result = subprocess.run(['docker', *args], capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('local_observer_container_operation_failed')
    return result.stdout


@unittest.skipUnless(os.getenv('SOCIALMEI_IG_OBSERVER_CONTAINER_TESTS') == '1', 'Explicit local observer container test required')
class ObserverContainerTests(unittest.TestCase):
    def test_two_workspace_volumes_and_health_survive_restart_without_sender(self):
        context = json.loads(run('context', 'inspect'))[0]
        self.assertTrue(context['Endpoints']['docker']['Host'].startswith(('unix://', 'npipe://')))
        self.assertFalse(os.getenv('DOCKER_HOST', '').startswith(('ssh:', 'tcp:')))
        source = json.loads(run('inspect', os.getenv('SOCIALMEI_IG_OBSERVER_TEST_SOURCE',
                                                    'socialmei-mei-demo-tests-20261119')))[0]
        env = dict(line.split('=', 1) for line in source['Config']['Env'] if '=' in line)
        self.assertEqual(env['POSTGRES_DB'], 'socialmei_demo_test')
        dsn = ('postgresql://' + quote(env.get('POSTGRES_USER', 'postgres'), safe='') + ':' +
               quote(env['POSTGRES_PASSWORD'], safe='') + '@127.0.0.1:5432/socialmei_demo_test')
        token = secrets.token_hex(8); created = []; volumes = []
        image = os.getenv('SOCIALMEI_IG_OBSERVER_TEST_IMAGE', 'socialmei-instagram-workers:test-20261121')
        def healthy(name):
            for _ in range(30):
                row = json.loads(run('inspect', name))[0]
                if row['State'].get('Health', {}).get('Status') == 'healthy': return
                time.sleep(.5)
            raise AssertionError('observer_never_became_healthy')
        with tempfile.TemporaryDirectory(prefix='socialmei-observer-env-') as temp:
            try:
                for workspace in (60, 61):
                    name = 'socialmei-observer-test-' + token + '-' + str(workspace)
                    volume = name + '-state'
                    run('volume', 'create', '--label', 'socialmei.observer-test=' + token, volume)
                    volumes.append(volume)
                    private = Path(temp) / (str(workspace) + '.env')
                    private.write_text('\n'.join([
                        'DATABASE_URL=' + dsn, 'SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME=socialmei_demo_test',
                        'SOCIALMEI_INSTAGRAM_WORKER_MODE=observe',
                        'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED=false',
                        'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false',
                        'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID=' + str(workspace),
                        'SOCIALMEI_INSTAGRAM_AUTO_MENU_START_UTC=2026-11-21T00:00:00+00:00']), encoding='utf-8')
                    run('create', '--name', name, '--label', 'socialmei.observer-test=' + token,
                        '--network', 'container:' + source['Id'], '--read-only', '--cap-drop', 'ALL',
                        '--security-opt', 'no-new-privileges', '--memory', '128m', '--cpus', '0.25',
                        '--pids-limit', '64', '--tmpfs', '/tmp:size=8m', '--env-file', str(private),
                        '--mount', 'type=volume,src=' + volume + ',dst=/run/socialmei/instagram-menu-state',
                        '--health-cmd', 'python -m instagram_worker_health', '--health-interval', '1s',
                        '--health-start-period', '10s', '--health-retries', '3', image,
                        'python', '-u', '/app/instagram-auto-menu-worker.py')
                    created.append(name)
                    run('start', name); healthy(name)
                    def state(): return json.loads(run('exec', name, 'cat', '/run/socialmei/instagram-menu-state/state.json'))
                    before = state()
                    self.assertEqual(before['workspace_id'], workspace)
                    self.assertFalse(before['send_enabled'])
                    run('restart', '--time', '2', name); healthy(name)
                    self.assertEqual(state(), before)
            finally:
                for name in reversed(created):
                    row = json.loads(run('inspect', name))[0]
                    self.assertEqual(row['Config']['Labels'].get('socialmei.observer-test'), token)
                    run('rm', '-f', name)
                for volume in volumes:
                    row = json.loads(run('volume', 'inspect', volume))[0]
                    self.assertEqual(row['Labels'].get('socialmei.observer-test'), token)
                    run('volume', 'rm', volume)


if __name__ == '__main__':
    unittest.main()
