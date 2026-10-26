"""Private operational diagnostics report evidence without secrets or provider calls."""

import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import app
import test_account_auth as accounts


@unittest.skipUnless(accounts.DB, "Disposable PostgreSQL required")
class DiagnosticsTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    @classmethod
    def setUpClass(cls):
        import importlib.util
        from pathlib import Path
        import psycopg

        accounts.AccountDatabaseTests.setUpClass.__func__(cls)
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "ops_migrate", root / "tools/team_migrate.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.connect = lambda: psycopg.connect(accounts.DB)
        module.migrate(root / "database/migrations")

    def test_admin_only_no_secrets_and_no_live_health_claim(self):
        owner = self.register("diag-owner@example.test")
        anon = TestClient(app, base_url=accounts.ORIGIN)
        self.assertEqual(anon.get("/api/v1/admin/diagnostics").status_code, 401)
        self.assertEqual(owner.get("/api/v1/admin/diagnostics").status_code, 403)
        with patch.dict(
            os.environ,
            {
                "SOCIALMEI_RELEASE_SHA": "a" * 40,
                "SOCIALMEI_SMTP_PASSWORD": "secret-do-not-expose",
            },
        ):
            result = self.admin_client.get("/api/v1/admin/diagnostics")
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertEqual(body["release_sha"], "a" * 40)
        self.assertEqual(body["database"]["status"], "ready")
        self.assertEqual(body["database"]["expected_migrations"], 29)
        self.assertEqual(body["providers"]["n8n"], "not_verified")
        self.assertNotIn("secret-do-not-expose", result.text)
        self.assertEqual(result.headers["cache-control"], "no-store")

    def test_missing_queue_schema_never_reports_ready(self):
        import psycopg

        with psycopg.connect(accounts.DB) as conn:
            conn.execute(
                "ALTER TABLE socialmei.auth_recuperacao_envios RENAME TO recovery_queue_hidden"
            )
        try:
            response = self.admin_client.get("/api/v1/admin/diagnostics")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["database"]["status"], "unavailable")
            self.assertEqual(response.json()["recovery_queue"]["status"], "unavailable")
        finally:
            with psycopg.connect(accounts.DB) as conn:
                conn.execute(
                    "ALTER TABLE socialmei.recovery_queue_hidden RENAME TO auth_recuperacao_envios"
                )

    def test_bad_release_and_database_error_are_sanitized(self):
        with patch.dict(
            os.environ, {"SOCIALMEI_RELEASE_SHA": "not-a-commit-secret"}
        ), patch(
            "operations_readiness.connect",
            side_effect=RuntimeError("private-dsn-password"),
        ):
            response = self.admin_client.get("/api/v1/admin/diagnostics")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["release_sha"])
        self.assertEqual(response.json()["database"]["status"], "unavailable")
        self.assertNotIn("private-dsn", response.text)


class SchemaManifestTests(unittest.TestCase):
    def test_manifest_tracks_exact_source_migrations(self):
        from pathlib import Path
        from operations_readiness import EXPECTED_MIGRATIONS

        self.assertEqual(
            tuple(
                sorted(
                    path.name
                    for path in (
                        Path(__file__).resolve().parents[1] / "database/migrations"
                    ).glob("*.sql")
                )
            ),
            EXPECTED_MIGRATIONS,
        )
