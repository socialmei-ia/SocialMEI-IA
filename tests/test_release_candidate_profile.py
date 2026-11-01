"""The current CI rehearsal rejects schema drift before creating Docker resources."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('current_release_rehearsal', ROOT/'tests/release-candidate-db.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class CurrentReleaseProfileTests(unittest.TestCase):
    def test_current_rehearsal_accepts_only_reviewed035_bytes(self):
        files, identity = release.reviewed_migrations()
        self.assertEqual(identity['profile'], '035')
        self.assertEqual(len(files), 35)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            shutil.copytree(ROOT/'database/migrations', source/'database/migrations')
            (source/'tools').mkdir()
            shutil.copyfile(ROOT/'tools/team-release-profile.py', source/'tools/team-release-profile.py')
            with patch.object(release, 'ROOT', source):
                for name in ('001_initial_socialmei_schema.sql', '034_workspace_agenda.sql', '035_whatsapp_human_outbox.sql'):
                    path = source/'database/migrations'/name
                    previous = path.read_bytes()
                    path.write_bytes(previous + b'\n')
                    with self.subTest(mutation=name), self.assertRaisesRegex(RuntimeError, 'conteudo_de_migration_divergente'):
                        release.reviewed_migrations()
                    path.write_bytes(previous)
                last = source/'database/migrations/035_whatsapp_human_outbox.sql'
                last.unlink()
                with self.assertRaises(RuntimeError):
                    release.reviewed_migrations()
                (source/'database/migrations/036_unreviewed.sql').write_text('SELECT 1;\n')
                with self.assertRaises(RuntimeError):
                    release.reviewed_migrations()


if __name__ == '__main__':
    unittest.main()
