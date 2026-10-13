import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from app import app
from shared_data import database_health_payload

DB = os.getenv("TEST_DATABASE_URL", "").strip()
ENV = {
    "SOCIALMEI_SHARED_DATA_ENABLED": "true",
    "SOCIALMEI_AUTH_ENABLED": "true",
    "SOCIALMEI_AUTH_ORIGIN": "https://app.example.com",
    "SOCIALMEI_WORKSPACE_SLUG": "health-isolated-test",
}


class HealthConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)

    def test_enabled_auth_validates_configuration_before_database(self):
        for changes in (
            {"SOCIALMEI_AUTH_ENABLED": "treu"},
            {"SOCIALMEI_AUTH_ORIGIN": "http://app.example.com"},
            {"SOCIALMEI_SHARED_DATA_ENABLED": "false"},
        ):
            with patch.dict(os.environ, changes), patch("shared_data.check_database") as check:
                response = self.client.get("/health/db")
                self.assertEqual(response.status_code, 503)
                check.assert_not_called()

    def test_disabled_shared_data_does_not_open_database(self):
        with patch.dict(os.environ, {
            "SOCIALMEI_AUTH_ENABLED": "false",
            "SOCIALMEI_SHARED_DATA_ENABLED": "false",
        }), patch("shared_data.check_database") as check:
            response = self.client.get("/health/db")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "disabled")
            self.assertEqual(response.json()["shared_data"], False)
            self.assertEqual(response.json()["capabilities"]["auth"]["schema"], "not_checked")
            check.assert_not_called()

    def test_auth_disabled_does_not_require_auth_schema(self):
        for value in ("false", "0", "no", "off", ""):
            with patch.dict(os.environ, {"SOCIALMEI_AUTH_ENABLED": value}), patch(
                "shared_data.check_database", return_value="unavailable"
            ) as check:
                payload = database_health_payload()
                self.assertEqual(payload["status"], "healthy")
                self.assertEqual(payload["capabilities"]["auth"]["enabled"], False)
                self.assertEqual(payload["capabilities"]["channels"]["connection"], "not_checked")
                check.assert_called_once_with(include_auth=False)

    def test_auth_enabled_reports_schema_without_claiming_channel_connection(self):
        with patch("shared_data.check_database", return_value="prepared") as check:
            payload = database_health_payload()
            self.assertEqual(payload["status"], "healthy")
            self.assertEqual(payload["workspace"], "health-isolated-test")
            self.assertEqual(payload["capabilities"]["auth"], {"enabled": True, "schema": "ready"})
            self.assertEqual(payload["capabilities"]["channels"], {"schema": "prepared", "connection": "not_checked"})
            check.assert_called_once_with(include_auth=True)

    def test_database_exception_is_sanitized_on_public_health_endpoint(self):
        with patch("shared_data.check_database", side_effect=RuntimeError("private-marker")):
            response = self.client.get("/health/db")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private-marker", response.text)
            self.assertEqual(set(response.json()), {"detail"})


@unittest.skipUnless(DB, "TEST_DATABASE_URL nao configurado; exige PostgreSQL isolado")
class DatabaseHealthIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrations = Path(__file__).resolve().parents[1] / "database/migrations"
        with psycopg.connect(DB, autocommit=True) as conn:
            for migration in sorted(migrations.glob("*.sql")):
                conn.execute(migration.read_text(), prepare=False)
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS socialmei.schema_migrations "
                    "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
                )
                conn.execute(
                    "INSERT INTO socialmei.schema_migrations (version) VALUES (%s) "
                    "ON CONFLICT DO NOTHING", (migration.name,)
                )

    def setUp(self):
        self.env = patch.dict(os.environ, {**ENV, "DATABASE_URL": DB})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)

    @contextmanager
    def renamed_table(self, table):
        renamed = "health_test_" + table
        with psycopg.connect(DB, autocommit=True) as conn:
            conn.execute(psycopg.sql.SQL("ALTER TABLE socialmei.{} RENAME TO {}").format(
                psycopg.sql.Identifier(table), psycopg.sql.Identifier(renamed),
            ))
            try:
                yield
            finally:
                conn.execute(psycopg.sql.SQL("ALTER TABLE socialmei.{} RENAME TO {}").format(
                    psycopg.sql.Identifier(renamed), psycopg.sql.Identifier(table),
                ))

    @contextmanager
    def missing_migration(self, version):
        with psycopg.connect(DB, autocommit=True) as conn:
            row = conn.execute(
                "DELETE FROM socialmei.schema_migrations WHERE version=%s "
                "RETURNING version, applied_at", (version,)
            ).fetchone()
            self.assertIsNotNone(row)
            try:
                yield
            finally:
                conn.execute(
                    "INSERT INTO socialmei.schema_migrations (version, applied_at) VALUES (%s, %s)", row
                )

    def test_full_schema_is_ready_without_creating_workspace(self):
        with psycopg.connect(DB) as conn:
            before = conn.execute("SELECT COUNT(*) FROM socialmei.workspaces").fetchone()[0]
        response = self.client.get("/health/db")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["capabilities"]["auth"]["schema"], "ready")
        self.assertEqual(response.json()["capabilities"]["channels"]["schema"], "prepared")
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM socialmei.workspaces").fetchone()[0], before)

    def test_missing_auth_table_fails_only_when_auth_enabled(self):
        with self.renamed_table("auth_credenciais"):
            self.assertEqual(self.client.get("/health/db").status_code, 503)
            with patch.dict(os.environ, {"SOCIALMEI_AUTH_ENABLED": "false"}):
                self.assertEqual(self.client.get("/health/db").status_code, 200)

    def test_missing_auth_column_is_not_healthy(self):
        with psycopg.connect(DB, autocommit=True) as conn:
            conn.execute("ALTER TABLE socialmei.auth_sessoes RENAME COLUMN expira_em TO health_test_expira_em")
            try:
                self.assertEqual(self.client.get("/health/db").status_code, 503)
            finally:
                conn.execute("ALTER TABLE socialmei.auth_sessoes RENAME COLUMN health_test_expira_em TO expira_em")

    def test_missing_crm_migration_is_not_healthy(self):
        with self.missing_migration("008_workspace_transfer.sql"):
            self.assertEqual(self.client.get("/health/db").status_code, 503)

    def test_missing_workspace_table_is_not_healthy_without_auth(self):
        with self.renamed_table("workspaces"), patch.dict(
            os.environ, {"SOCIALMEI_AUTH_ENABLED": "false"}
        ):
            self.assertEqual(self.client.get("/health/db").status_code, 503)

    def test_missing_auth_migration_fails_only_when_auth_enabled(self):
        with self.missing_migration("010_account_authentication.sql"):
            self.assertEqual(self.client.get("/health/db").status_code, 503)
            with patch.dict(os.environ, {"SOCIALMEI_AUTH_ENABLED": "false"}):
                self.assertEqual(self.client.get("/health/db").status_code, 200)

    def test_missing_channel_table_preserves_crm_health(self):
        with self.renamed_table("crm_eventos_canal"):
            response = self.client.get("/health/db")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["capabilities"]["channels"]["schema"], "unavailable")
            self.assertEqual(response.json()["capabilities"]["channels"]["connection"], "not_checked")

    def test_missing_channel_migration_is_not_prepared(self):
        with self.missing_migration("009_shared_channel_foundation.sql"):
            response = self.client.get("/health/db")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["capabilities"]["channels"]["schema"], "unavailable")


if __name__ == "__main__":
    unittest.main()
