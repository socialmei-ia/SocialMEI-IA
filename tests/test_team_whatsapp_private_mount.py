"""Offline guards for restoring the Team API's missing private WhatsApp mount."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "team_whatsapp_private_mount", ROOT / "tools" / "team-whatsapp-private-mount.py"
)
mount = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mount)


def fixture():
    model = {
        "name": "socialmei-team",
        "networks": {"api": {"name": "socialmei-team_api"}},
        "services": {
            "team-api": {
                "image": "socialmei/team-api:pin",
                "environment": {"SOCIALMEI_AUTH_ENABLED": "true"},
                "networks": {"api": None},
                "volumes": [],
            },
            "team-gateway": {"image": "socialmei/gateway:pin"}
        }
    }
    api = {
        "Config": {
            "Image": "socialmei/team-api:pin",
            "Env": ["SOCIALMEI_AUTH_ENABLED=true"],
        },
        "HostConfig": {"PortBindings": {}},
        "NetworkSettings": {"Networks": {"socialmei-team_api": {}}},
        "Mounts": [],
        "State": {"Health": {"Status": "healthy"}},
    }
    return model, api


class PilotPrivateMountTests(unittest.TestCase):
    def test_baseline_runtime_must_match_model(self):
        model, api = fixture()
        mount.assert_current(api, model)
        api["Config"]["Image"] = "socialmei/team-api:other"
        with self.assertRaises(mount.Blocked):
            mount.assert_current(api, model)

    def test_only_one_private_readonly_bind_is_allowed(self):
        old, _ = fixture()
        new = copy.deepcopy(old)
        source = Path("/opt/socialmei/private/whatsapp-pilot")
        new["services"]["team-api"]["volumes"] = [{
            "type": "bind", "source": str(source),
            "target": mount.TARGET, "read_only": True,
        }]
        mount.check_candidate(old, new, source)
        new["services"]["team-gateway"]["image"] = "changed"
        with self.assertRaises(mount.Blocked):
            mount.check_candidate(old, new, source)

    def test_readwrite_or_duplicate_bind_is_blocked(self):
        old, _ = fixture()
        source = Path("/opt/socialmei/private/whatsapp-pilot")
        new = copy.deepcopy(old)
        volume = {"type": "bind", "source": str(source), "target": mount.TARGET,
                  "read_only": False}
        new["services"]["team-api"]["volumes"] = [volume]
        with self.assertRaises(mount.Blocked):
            mount.check_candidate(old, new, source)
        new["services"]["team-api"]["volumes"] = [{**volume, "read_only": True},
                                                    {**volume, "read_only": True}]
        with self.assertRaises(mount.Blocked):
            mount.check_candidate(old, new, source)

class SecretSeparationTests(unittest.TestCase):
    def test_registry_is_outside_gateway_private_mount(self):
        gateway = {'Mounts': [{'Type': 'bind', 'Source': '/home/ubuntu/socialmei-team/deploy/team/private'}]}
        source = mount.private_source(gateway)
        self.assertEqual(source, mount.BACKUPS / 'registry')
        with self.assertRaises(mount.Blocked):
            mount.private_source({'Mounts': [{'Type': 'bind', 'Source': '/var/lib'}]})


class RuntimeSafetyTests(unittest.TestCase):
    def test_invocation_selects_last_private_api_overlay_in_compose_order(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / "older"
            current = root / "current"
            old.mkdir()
            current.mkdir()
            compose = root / "compose.team.yaml"
            (root / ".env.team").write_text("", encoding="utf-8")
            old_override = old / mount.OVERRIDE
            current_override = current / mount.OVERRIDE
            for path in (compose, old_override, current_override):
                path.write_text("{}", encoding="utf-8")
            api = {"Config": {"Labels": {
                "com.docker.compose.project.working_dir": str(root),
                "com.docker.compose.project.config_files": ",".join(map(str, (
                    compose, old_override, current_override
                ))),
            }}}

            _, files, selected, command = mount.invocation(api)

            self.assertEqual(files, [compose, old_override, current_override])
            self.assertEqual(selected, current_override.resolve())
            self.assertIn(str(current_override.resolve()), command)

    def test_docker_commands_always_select_local_daemon(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with patch.object(mount.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout='safe')) as run:
            self.assertEqual(mount.call(['docker', 'inspect', mount.API]), 'safe')
        self.assertEqual(run.call_args.args[0], [
            'docker', '--host=unix:///var/run/docker.sock', 'inspect', mount.API])

    def test_network_environment_health_and_mount_drift_are_refused(self):
        mutations = (
            lambda row: row['NetworkSettings']['Networks'].update({'unexpected': {}}),
            lambda row: row['Config']['Env'].append('SOCIALMEI_AUTH_ENABLED=false'),
            lambda row: row['State']['Health'].update({'Status': 'unhealthy'}),
            lambda row: row['Mounts'].append({'Type': 'bind', 'Source': '/tmp',
                        'Destination': '/unexpected', 'RW': True}),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                model, api = fixture()
                mutate(api)
                with self.assertRaises(mount.Blocked):
                    mount.assert_current(api, model)

    def test_rollback_is_checked_for_health_after_failed_cutover(self):
        import io
        import json
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backup = root / 'backups'
            backup.mkdir(mode=0o700)
            original = root / mount.OVERRIDE
            previous = json.dumps({'services': {'team-api': {'image': 'pin'}}}).encode()
            original.write_bytes(previous)
            model, api = fixture()
            api['Image'] = 'sha256:' + 'a' * 64
            def render(command, wd):
                result = copy.deepcopy(model)
                if any('.wa-candidate-' in part for part in command):
                    result['services']['team-api']['volumes'] = [{
                        'type': 'bind', 'source': str(backup / 'registry'),
                        'target': mount.TARGET, 'read_only': True,
                        'bind': {'create_host_path': False}}]
                return result
            original_stat = Path.stat
            def stat_as_root(path, **kwargs):
                result = original_stat(path, **kwargs)
                if path == backup:
                    import os
                    fields = list(result)
                    fields[4] = 0
                    return os.stat_result(fields)
                return result
            def call(command, **kwargs):
                if command[1:3] == ['image', 'inspect']:
                    return json.dumps([{'Id': api['Image']}])
                if command[1] == 'inspect':
                    return '[{"Mounts": []}]'
                return ''
            with patch.object(mount, 'BACKUPS', backup), \
                 patch.object(Path, 'stat', stat_as_root), \
                 patch.object(mount.os, 'geteuid', return_value=0), \
                 patch.object(mount, 'get_api', return_value=api), \
                 patch.object(mount, 'invocation', return_value=(root, [original], original, ['docker', 'compose', '-f', str(original)])), \
                 patch.object(mount, 'render', side_effect=render), \
                 patch.object(mount, 'call', side_effect=call) as invoke, \
                 patch.object(mount, 'healthy', side_effect=[False, True]) as healthy, \
                 patch.object(mount, 'open', return_value=io.StringIO(), create=True), \
                 patch.object(mount.fcntl, 'flock'), \
                 patch.object(mount.sys, 'argv', ['mount.py', '--apply']), \
                 patch('sys.stdout', new_callable=io.StringIO) as output:
                with self.assertRaises(mount.Blocked) as failure:
                    mount.main()
            self.assertEqual(str(failure.exception), 'API nao ficou saudavel apos ajuste do volume')
            self.assertEqual(original.read_bytes(), previous)
            self.assertEqual(healthy.call_count, 2)
            self.assertEqual(sum('up' in c.args[0] for c in invoke.call_args_list), 2)
            self.assertIn('ROLLBACK_COMPOSE: APLICADO_E_SAUDE_CONFERIDA', output.getvalue())


if __name__ == "__main__":
    unittest.main()
