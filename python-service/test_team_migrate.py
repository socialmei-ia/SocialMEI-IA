import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "team_migrate", ROOT / "tools/team_migrate.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
DB = os.getenv("TEST_DATABASE_URL", "").strip()


@unittest.skipUnless(DB, "TEST_DATABASE_URL não configurado")
class TeamMigrationTests(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = DB

    def test_replay_migrations_does_not_duplicate_version_records(self):
        directory = ROOT / "database/migrations"
        module.migrate(directory)
        with psycopg.connect(DB) as conn:
            before = conn.execute(
                "SELECT version FROM socialmei.schema_migrations ORDER BY version"
            ).fetchall()
        module.migrate(directory)
        with psycopg.connect(DB) as conn:
            after = conn.execute(
                "SELECT version FROM socialmei.schema_migrations ORDER BY version"
            ).fetchall()
        self.assertEqual(before, after)
        self.assertTrue(
            {p.name for p in directory.glob("*.sql")} <= {row[0] for row in after}
        )

    def test_failed_migration_rolls_back_schema_and_record(self):
        module.migrate(ROOT / "database/migrations")
        name = "ci_probe_" + uuid4().hex
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "999_failure.sql").write_text(
                f"CREATE TABLE socialmei.{name} (id INT); SELECT non_existent_column;"
            )
            with self.assertRaises(psycopg.Error):
                module.migrate(Path(directory))
        with psycopg.connect(DB) as conn:
            self.assertIsNone(
                conn.execute(
                    "SELECT to_regclass(%s)", ("socialmei." + name,)
                ).fetchone()[0]
            )
            self.assertIsNone(
                conn.execute(
                    "SELECT version FROM socialmei.schema_migrations WHERE version='999_failure.sql'"
                ).fetchone()
            )
