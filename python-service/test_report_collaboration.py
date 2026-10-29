"""No public database account: reports require explicit current workspace."""
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app import app
from account_auth import REPORT_ONLY
from report_collaboration import ExistingUser, WorkspaceSelection


class ReportViewerGuards(unittest.TestCase):
    def test_existing_user_email_normalization_and_rejection(self):
        self.assertEqual(ExistingUser(email="  PESSOA@EXAMPLE.TEST  ").email, "pessoa@example.test")
        for value in ("", "sem-arroba", "a@" + "x" * 300):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExistingUser(email=value)

    def test_workspace_selection_strict(self):
        for value in (0, -1, "1", 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                WorkspaceSelection(workspace_id=value)
        self.assertEqual(WorkspaceSelection(workspace_id=32).workspace_id, 32)

    def test_least_privilege_allowlist(self):
        allowed = {
            ("GET", "/api/v1/reporting/overview"),
            ("GET", "/api/v1/reporting/overview.csv"),
            ("GET", "/api/v1/auth/workspaces"),
            ("POST", "/api/v1/auth/workspaces/switch"),
            ("POST", "/api/v1/auth/logout"),
        }
        self.assertEqual(REPORT_ONLY, allowed)
        for method, path in (
            ("GET", "/api/v1/clientes"),
            ("GET", "/api/v1/financeiro"),
            ("GET", "/api/v1/knowledge/pdf"),
            ("GET", "/api/v1/instagram/meta/status"),
            ("POST", "/api/v1/reporting/overview"),
            ("GET", "/api/v1/reporting/access"),
        ):
            self.assertNotIn((method, path), REPORT_ONLY)

    def test_report_viewer_apis_require_session(self):
        with patch.dict(os.environ, {
            "SOCIALMEI_AUTH_ENABLED": "true",
            "SOCIALMEI_AUTH_ORIGIN": "https://app.example.com",
            "SOCIALMEI_SHARED_DATA_ENABLED": "true",
        }):
            client = TestClient(app, base_url="https://app.example.com")
            self.assertEqual(client.get("/api/v1/reporting/access").status_code, 401)
            self.assertEqual(client.get("/api/v1/auth/workspaces").status_code, 401)
            self.assertEqual(
                client.post("/api/v1/reporting/access",
                    headers={"Origin": "https://app.example.com"},
                    json={"email": "viewer@example.test"}).status_code,
                401,
            )
            self.assertEqual(
                client.post("/api/v1/auth/workspaces/switch",
                    headers={"Origin": "https://app.example.com"},
                    json={"workspace_id": 7}).status_code,
                401,
            )
