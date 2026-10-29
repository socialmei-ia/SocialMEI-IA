"""Reference Compose must pass opt-in capabilities without activating defaults."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ('SOCIALMEI_KNOWLEDGE_PDF_ENABLED','SOCIALMEI_WA_CATALOG_ENABLED')


class FunctionalConfigurationTests(unittest.TestCase):
    def test_reference_compose_keeps_features_off_and_forwards_explicit_activation(self):
        for selected in ({},dict.fromkeys(FLAGS,'true')):
            with self.subTest(selected=bool(selected)), tempfile.TemporaryDirectory() as directory:
                env = {'PATH':os.environ['PATH'],'TEAM_POSTGRES_PASSWORD':'disposable-config-only',
                       'SOCIALMEI_TEAM_HOST':'app.example.test',**selected}
                result = subprocess.run(['docker','compose','--project-directory',directory,
                    '--env-file','/dev/null','-f',str(ROOT/'compose.team.yaml'),'config','--format','json'],
                    env=env,capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,'Reference Compose validation failed')
                settings = json.loads(result.stdout)['services']['team-api']['environment']
                for key in FLAGS:
                    self.assertEqual(settings.get(key),selected.get(key,'false'),key)
