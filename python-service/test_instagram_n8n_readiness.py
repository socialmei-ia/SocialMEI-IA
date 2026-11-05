"""Workspace-scoped status for the optional n8n Instagram receive bridge.

No external HTTP, live events, or database service is required for these tests.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from instagram_n8n_ingress import InstagramN8NIngressService
from instagram_runtime import (
    InstagramRuntime,
    n8n_incoming_for_workspace,
    readiness,
)

RELAY = "synthetic-relay-key-for-readiness-12345"
META = "synthetic-meta-secret-for-readiness-123456"


class N8NReadinessTests(unittest.TestCase):
    def setUp(self):
        self.bridge = InstagramN8NIngressService(
            key=RELAY,
            meta_app_secret=META,
            bindings={"987654321": 1},
            auth_mode="header",
        )
        self.request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(instagram_runtime=InstagramRuntime()))
        )

    def test_binding_is_workspace_scoped_and_rejects_boolean_ids(self):
        self.assertTrue(self.bridge.has_workspace(1))
        self.assertFalse(self.bridge.has_workspace(2))
        self.assertFalse(self.bridge.has_workspace(True))
        self.assertFalse(self.bridge.has_workspace("1"))

    def test_invalid_or_disabled_relay_fails_closed(self):
        with patch("instagram_runtime.settings.instagram_n8n_ingress_enabled", return_value=False):
            self.assertFalse(n8n_incoming_for_workspace(1))
        with patch("instagram_runtime.settings.instagram_n8n_ingress_enabled", return_value=True), patch(
            "instagram_n8n_ingress.ingress_service", side_effect=ValueError("private-token")
        ):
            self.assertFalse(n8n_incoming_for_workspace(1))
        with patch("instagram_runtime.settings.instagram_n8n_ingress_enabled", return_value=True), patch(
            "instagram_n8n_ingress.ingress_service", return_value=self.bridge
        ):
            self.assertFalse(n8n_incoming_for_workspace(True))
            self.assertTrue(n8n_incoming_for_workspace(1))
            self.assertFalse(n8n_incoming_for_workspace(2))

    def test_readiness_reports_only_own_configured_receive_and_never_enables_send(self):
        with (
            patch("instagram_runtime.require_enabled"),
            patch("instagram_runtime.whatsapp_readiness", return_value={}),
            patch("instagram_runtime.schema_ready", return_value=True),
            patch("instagram_runtime.settings.instagram_n8n_ingress_enabled", return_value=True),
            patch("instagram_n8n_ingress.ingress_service", return_value=self.bridge),
        ):
            with patch("instagram_runtime.current", return_value={"workspace_id": 1}):
                status = readiness(self.request)["instagram"]
                self.assertTrue(status["incoming_available"])
                self.assertTrue(status["n8n_ingress_configured"])
                self.assertFalse(status["send_enabled"])
                self.assertNotIn(RELAY, str(status))
                self.assertNotIn(META, str(status))
            with patch("instagram_runtime.current", return_value={"workspace_id": 2}):
                status = readiness(self.request)["instagram"]
                self.assertFalse(status["incoming_available"])
                self.assertFalse(status["n8n_ingress_configured"])

    def test_missing_schema_stays_unavailable(self):
        with (
            patch("instagram_runtime.require_enabled"),
            patch("instagram_runtime.current", return_value={"workspace_id": 1}),
            patch("instagram_runtime.whatsapp_readiness", return_value={}),
            patch("instagram_runtime.schema_ready", return_value=False),
            patch("instagram_runtime.settings.instagram_n8n_ingress_enabled", return_value=True),
            patch("instagram_n8n_ingress.ingress_service", return_value=self.bridge),
        ):
            status = readiness(self.request)["instagram"]
            self.assertFalse(status["incoming_available"])
            self.assertFalse(status["n8n_ingress_configured"])

    def test_existing_direct_ingress_remains_available_independently(self):
        self.request.app.state.instagram_runtime = InstagramRuntime(
            "configured", ingress=object()
        )
        with (
            patch("instagram_runtime.require_enabled"),
            patch("instagram_runtime.current", return_value={"workspace_id": 1}),
            patch("instagram_runtime.whatsapp_readiness", return_value={}),
            patch("instagram_runtime.schema_ready", return_value=True),
            patch("instagram_runtime.settings.instagram_n8n_ingress_enabled", return_value=False),
        ):
            status = readiness(self.request)["instagram"]
            self.assertTrue(status["incoming_available"])
            self.assertFalse(status["n8n_ingress_configured"])


if __name__ == "__main__":
    unittest.main()
