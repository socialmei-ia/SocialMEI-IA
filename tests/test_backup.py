import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "Requires POSIX Bash and executable fixture scripts")
class BackupTests(unittest.TestCase):
    def run_backup(self, failure="", volume="actual_project_n8n_data"):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        project = Path(workspace.name)
        for directory in ["bin", "backups", "python-service", "database", "n8n-workflows"]:
            (project / directory).mkdir()
        for filename in ["compose.yaml", "compose.override.yaml", "Caddyfile", ".env"]:
            (project / filename).write_text("test fixture\n")
        docker = project / "bin/docker"
        docker.write_text("""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$MOCK_LOG"
case "$1" in
  inspect) printf '%s' "$MOCK_VOLUME" ;;
  exec)
    [[ "$MOCK_FAILURE" != "dump" ]] || exit 4
    printf 'mock database dump' ;;
  run)
    [[ "$MOCK_FAILURE" != "archive" ]] || exit 3
    output="${@: -4:1}"
    touch "$MOCK_BACKUPS/${output#/backup/}" ;;
  compose)
    if [[ "$2" = "start" && "$MOCK_FAILURE" = "restart" ]]; then exit 5; fi ;;
  *) exit 9 ;;
esac
""")
        docker.chmod(0o700)
        environment = {
            **os.environ,
            "PATH": str(project / "bin") + os.pathsep + os.environ["PATH"],
            "SOCIALMEI_PROJECT_DIR": str(project),
            "MOCK_LOG": str(project / "docker.log"),
            "MOCK_BACKUPS": str(project / "backups"),
            "MOCK_VOLUME": volume,
            "MOCK_FAILURE": failure,
        }
        result = subprocess.run(["bash", str(ROOT / "backup.sh")], env=environment,
                                capture_output=True, text=True, timeout=10)
        return result, project

    def test_success_uses_actual_volume_and_private_complete_archives(self):
        result, project = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("actual_project_n8n_data:/data:ro", (project / "docker.log").read_text())
        files = list((project / "backups").iterdir())
        self.assertEqual(len(files), 3)
        self.assertFalse(any(file.name.endswith(".partial") for file in files))
        self.assertTrue(all(file.stat().st_mode & 0o077 == 0 for file in files))

    def test_archive_failure_restarts_n8n_and_cleans_partial_files(self):
        result, project = self.run_backup("archive")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("compose start n8n", (project / "docker.log").read_text())
        self.assertFalse(list((project / "backups").glob("*.partial")))
        self.assertNotIn("Backup concluído", result.stdout)

    def test_dump_failure_does_not_stop_n8n(self):
        result, project = self.run_backup("dump")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("compose stop", (project / "docker.log").read_text())
        self.assertFalse(list((project / "backups").iterdir()))

    def test_restart_failure_is_reported_as_failure(self):
        result, project = self.run_backup("restart")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("intervenção necessária", result.stderr)

    def test_missing_volume_never_stops_service(self):
        result, project = self.run_backup(volume="")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("compose stop", (project / "docker.log").read_text())


if __name__ == "__main__":
    unittest.main()
