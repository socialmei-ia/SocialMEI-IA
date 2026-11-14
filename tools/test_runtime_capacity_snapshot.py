"""Offline privacy and Docker projection regression checks."""
import importlib.util
import json
from pathlib import Path
import re
import unittest


spec = importlib.util.spec_from_file_location(
    'snapshot', Path(__file__).with_name('runtime-capacity-snapshot.py'))
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class SnapshotTests(unittest.TestCase):
    def test_network_projection_produces_complete_json(self):
        rendered = snapshot.NETWORK_TEMPLATE.replace('{{json .Name}}', '"isolated"')
        rendered = rendered.replace('{{.Internal}}', 'true')
        rendered = rendered.replace('{{json .Driver}}', '"bridge"')
        self.assertEqual(json.loads(rendered), {
            'name': 'isolated', 'internal': True, 'driver': 'bridge'})

    def test_container_projection_produces_complete_json(self):
        rendered = snapshot.CONTAINER_TEMPLATE
        health = '{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}'
        rendered = rendered.replace(health, 'null')
        networks = '{{range $i, $v := .NetworkSettings.Networks}}{{json $i}},{{end}}'
        rendered = rendered.replace(networks, '"isolated",')
        rendered = re.sub(r'\{\{.*?\}\}', 'null', rendered)
        value = json.loads(rendered)
        self.assertEqual(value['networks'], ['isolated', None])
        self.assertIsNone(value['health'])

    def test_projection_excludes_private_config(self):
        combined = snapshot.NETWORK_TEMPLATE + snapshot.CONTAINER_TEMPLATE
        for private in ('.Config.Env', '.Mounts', '.Config.Cmd', '.Config.Entrypoint',
                        '.State.Health.Log', '.IPAddress'):
            self.assertNotIn(private, combined)

    def test_identifiers_reject_urls_and_untrusted_revision(self):
        self.assertIsNone(snapshot.safe_name('https://private.invalid/token'))
        self.assertIsNone(snapshot.safe_revision('release\nsecret'))
        self.assertEqual(snapshot.safe_revision('a' * 40), 'a' * 40)


if __name__ == '__main__':
    unittest.main()
