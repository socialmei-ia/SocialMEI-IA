"""Compose-only synthetic configuration. Does not create networks or containers."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class EgressTests(unittest.TestCase):
    def test_optional_egress_changes_only_api_networks(self):
        def model(overlay=False):
            args=['docker','compose','--env-file','/dev/null','-f','compose.team.yaml']
            if overlay:args+=['-f','compose.team.egress.yaml']
            env=dict(os.environ,TEAM_POSTGRES_PASSWORD='synthetic-test-only',SOCIALMEI_TEAM_HOST='app.example.test')
            return json.loads(subprocess.check_output(args+['config','--format','json'],cwd=ROOT,env=env,stderr=subprocess.PIPE))
        before=model()
        after=model(True)
        self.assertEqual(set(after['services']['team-api']['networks']),{'database','api','automation','egress'})
        self.assertEqual(after['networks']['egress']['name'],'socialmei_team_egress')
        self.assertFalse(after['networks']['egress'].get('internal',False))
        self.assertTrue(after['networks']['database']['internal'])
        self.assertTrue(after['networks']['api']['internal'])
        self.assertTrue(after['networks']['automation']['internal'])
        self.assertNotIn('ports',after['services']['team-api'])
        del after['services']['team-api']['networks']['egress']
        del after['networks']['egress']
        self.assertEqual(after,before)
