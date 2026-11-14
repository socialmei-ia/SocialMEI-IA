"""Execute the CI profile selector against isolated SQL-file fixtures; never runs SQL."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/repository-checks.yml'
CANDIDATE_WORKFLOW = ROOT / '.github/workflows/team-v33-candidate-images.yml'
BASH = shutil.which('bash')
if Path('C:/Program Files/Git/bin/bash.exe').is_file():
    BASH = 'C:/Program Files/Git/bin/bash.exe'


def selector():
    source = WORKFLOW.read_text(encoding='utf-8')
    start = source.index("profile=$(python - <<'PY'\n")
    script = source[start:].split('\n', 1)[1].split('\n          PY\n', 1)[0]
    return textwrap.dedent(script)


class RepositoryReleaseWorkflowTests(unittest.TestCase):
    @unittest.skipUnless(BASH, 'Bash required to execute workflow build branches')
    def test_api_build_context_is_root_only_for_profile040(self):
        source = WORKFLOW.read_text(encoding='utf-8')
        start = source.index('            if [ "$profile" = 040 ]; then\n')
        repository_build = textwrap.dedent(source[start:].split('\n            image=', 1)[0])
        source = CANDIDATE_WORKFLOW.read_text(encoding='utf-8')
        start = source.index('      - name: Build API image outside production VPS\n')
        candidate_build = textwrap.dedent(source[start:].split('        run: |\n', 1)[1]
                                         .split('\n      - name:', 1)[0])
        for version in ('035', '038', '039', '040'):
            for workflow, script in (('repository', repository_build), ('candidate', candidate_build)):
                with self.subTest(version=version, workflow=workflow):
                    prefix = ('docker() { printf "%s\\n" "$*"; };\n'
                              f'profile={version}; RELEASE_PROFILE={version}; '
                              'sha=fixture-sha; CANDIDATE_SHA=fixture-sha;\n')
                    result = subprocess.run([BASH, '-c', prefix + script],
                                            capture_output=True, text=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    commands = result.stdout.strip().splitlines()
                    self.assertEqual(len(commands), 1, result.stdout)
                    expected = ('-f deploy/team/Dockerfile.release040-api .'
                                if version == '040' else '-f python-service/Dockerfile python-service')
                    self.assertTrue(commands[0].endswith(expected), commands[0])
                    self.assertIn('--build-arg SOCIALMEI_RELEASE_SHA=fixture-sha', commands[0])

    def run_selector(self, version, *, corrupt=False):
        with TemporaryDirectory() as folder:
            target = Path(folder)
            (target / 'tools').mkdir()
            migrations = target / 'database/migrations'
            migrations.mkdir(parents=True)
            shutil.copyfile(ROOT / 'tools/team-release-profile.py', target / 'tools/team-release-profile.py')
            for source in sorted((ROOT / 'database/migrations').glob('*.sql')):
                if int(source.name[:3]) <= version:
                    shutil.copyfile(source, migrations / source.name)
            if version > 40:
                (migrations / '041_unreviewed.sql').write_text('SELECT 1;\n', encoding='utf-8')
            if corrupt:
                path = migrations / '040_identity_activation.sql'
                path.write_bytes(path.read_bytes() + b'\n')
            return subprocess.run([sys.executable, '-c', selector()], cwd=target,
                                  capture_output=True, text=True, timeout=20)

    def test_all_reviewed_profiles_select_their_exact_validator(self):
        for version in (35, 38, 39, 40):
            with self.subTest(version=version):
                result = self.run_selector(version)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), f'{version:03}')

    def test_unknown_or_modified_migrations_never_select_a_rehearsal(self):
        for version, corrupt in ((41, False), (40, True)):
            with self.subTest(version=version, corrupt=corrupt):
                result = self.run_selector(version, corrupt=corrupt)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
