"""Server wiring and OAuth browser roundtrip; all provider calls are synthetic."""

import base64
import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import psycopg
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import app
from account_auth import COOKIE
from instagram_meta_ingress import WebhookQueryPrivacy
from instagram_runtime import RETURN_PATH, build_runtime, schema_ready
import test_account_auth as accounts

DB, ENV, ORIGIN = accounts.DB, accounts.ENV, accounts.ORIGIN
from test_instagram_persistent_oauth import FakeTransport
from test_instagram_meta_ingress import payload as incoming_payload

SECRET = "synthetic-runtime-secret-never-real-123"
VERIFY = "synthetic-runtime-verify-never-real-123"
SCOPES = "instagram_business_basic,instagram_business_manage_messages"


def configuration():
    callback = ORIGIN + RETURN_PATH
    return {
        **ENV,
        "SOCIALMEI_INSTAGRAM_RUNTIME_MODE": "connect",
        "SOCIALMEI_INSTAGRAM_CLIENT_ID": "123",
        "SOCIALMEI_INSTAGRAM_CLIENT_SECRET": SECRET,
        "SOCIALMEI_INSTAGRAM_GRAPH_VERSION": "v99.0",
        "SOCIALMEI_INSTAGRAM_SCOPES": SCOPES,
        "SOCIALMEI_INSTAGRAM_AUTHORIZATION_EMBED": "https://www.instagram.com/oauth/authorize?"
        + urlencode(
            {
                "client_id": "123",
                "redirect_uri": callback,
                "response_type": "code",
                "scope": SCOPES,
            }
        ),
        "SOCIALMEI_INSTAGRAM_TOKEN_KEYRING": json.dumps(
            {"test": base64.urlsafe_b64encode(b"t" * 32).decode()}
        ),
        "SOCIALMEI_INSTAGRAM_TOKEN_ACTIVE_KEY_ID": "test",
        "SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED": "true",
        "SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED": "true",
        "SOCIALMEI_INSTAGRAM_WEBHOOK_VERIFY_TOKEN": VERIFY,
    }


class RuntimeConfigurationTests(unittest.TestCase):
    def test_live_direct_requires_explicit_dashboard_sender_ownership(self):
        for owner, expected in [('unassigned',False),('n8n',False),('dashboard',True)]:
            with self.subTest(owner=owner), patch.dict(os.environ,{**configuration(),
                'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED':'true',
                'SOCIALMEI_INSTAGRAM_DIRECT_OWNER':owner},clear=True), patch('instagram_runtime.InstagramHTTPTransport',return_value=FakeTransport()):
                runtime=build_runtime()
                self.assertEqual(runtime.status,'configured')
                self.assertEqual(runtime.send,expected)
                self.assertEqual(runtime.direct.allow_dispatch,expected)

    def test_disabled_ignores_unused_secrets_and_never_constructs_transport(self):
        with patch.dict(
            os.environ, {"SOCIALMEI_INSTAGRAM_CLIENT_SECRET": SECRET}, clear=True
        ), patch(
            "instagram_runtime.InstagramHTTPTransport",
            side_effect=AssertionError("transport constructed"),
        ):
            self.assertEqual(build_runtime().status, "disabled")

    def test_configured_reuses_services_without_network_and_keeps_sending_off(self):
        fake = FakeTransport()
        with patch.dict(os.environ, configuration(), clear=True), patch(
            "instagram_runtime.InstagramHTTPTransport", return_value=fake
        ):
            runtime = build_runtime()
            self.assertEqual(runtime.status, "configured")
            self.assertIsNotNone(runtime.oauth)
            self.assertIsNotNone(runtime.ingress)
            self.assertIsNotNone(runtime.direct)
            self.assertFalse(runtime.send)
            self.assertEqual(fake.calls, [])
            with self.assertRaises(Exception) as error:
                runtime.direct.run({}, "", None)
            self.assertEqual(error.exception.status_code, 503)
            self.assertNotIn(SECRET, repr(runtime))

    def test_invalid_configuration_does_not_crash_crm_or_echo_secrets(self):
        cases = [
            {"SOCIALMEI_AUTH_ENABLED": "false"},
            {"SOCIALMEI_INSTAGRAM_CLIENT_SECRET": "short"},
            {"SOCIALMEI_INSTAGRAM_TOKEN_KEYRING": '{"test":"a","test":"b"}'},
            {"SOCIALMEI_INSTAGRAM_TOKEN_ACTIVE_KEY_ID": "missing"},
            {"SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED": "false"},
            {"SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED": "yes"},
            {"SOCIALMEI_INSTAGRAM_GRAPH_VERSION": "latest"},
            {
                "SOCIALMEI_INSTAGRAM_AUTHORIZATION_EMBED": "https://evil.example/authorize"
            },
        ]
        for case in cases:
            with self.subTest(case=list(case)), patch.dict(
                os.environ, {**configuration(), **case}, clear=True
            ):
                self.assertEqual(build_runtime().status, "configuration_invalid")
                with TestClient(app, base_url=ORIGIN) as client:
                    self.assertEqual(client.get("/health").status_code, 200)
                    response = client.get("/api/v1/instagram/meta/status")
                    self.assertNotIn(SECRET, response.text)

    def test_schema_failure_is_unavailable_not_fake_success(self):
        with patch(
            "instagram_runtime.connect",
            side_effect=RuntimeError("private connection data"),
        ):
            self.assertFalse(schema_ready("oauth"))

    def test_schema_requires_dependency_migrations_not_just_existing_tables(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value = cursor
        cursor.fetchone.return_value = (True,)
        cursor.fetchall.return_value = [
            ("019_instagram_persistent_oauth.sql",),
            ("021_instagram_direct_outbox.sql",),
        ]
        with patch("instagram_runtime.connect", return_value=connection):
            self.assertFalse(schema_ready("direct"))
        cursor.fetchall.return_value.append(("020_instagram_durable_webhook.sql",))
        with patch("instagram_runtime.connect", return_value=connection):
            self.assertTrue(schema_ready("direct"))
        tables = [
            call.args[1][0]
            for call in connection.execute.call_args_list
            if call.args[0] == "SELECT to_regclass(%s)"
        ]
        self.assertIn("socialmei.ig_meta_connections", tables)
        self.assertIn("socialmei.ig_meta_ingress_events", tables)

    def test_public_provider_routes_stay_closed_without_configured_runtime(self):
        with patch.dict(os.environ, ENV, clear=True), TestClient(
            app, base_url=ORIGIN
        ) as client:
            self.assertEqual(client.get("/webhooks/instagram").status_code, 503)
            response = client.get(RETURN_PATH)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers.get("referrer-policy"), "no-referrer")
            self.assertEqual(
                client.get("/api/v1/integrations/readiness").status_code, 401
            )

    def test_sensitive_queries_are_removed_before_routes_and_error_responses(self):
        probe = FastAPI()

        @probe.get(RETURN_PATH)
        @probe.get("/webhooks/instagram")
        def inspect(request: Request):
            return {"query": request.url.query}

        probe.add_middleware(WebhookQueryPrivacy)
        client = TestClient(probe)
        for path in (RETURN_PATH, "/webhooks/instagram"):
            response = client.get(path + "?code=private-code&state=private-state")
            self.assertEqual(response.json()["query"], "")
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers.get("referrer-policy"), "no-referrer")
            self.assertNotIn("private-code", response.text)


@unittest.skipUnless(DB, "Disposable PostgreSQL not configured")
class RuntimeDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        accounts.AccountDatabaseTests.setUpClass.__func__(cls)
        import importlib.util
        import io
        from contextlib import redirect_stdout
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "runtime_test_migrator", root / "tools/team_migrate.py"
        )
        migrator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migrator)
        with patch.dict(os.environ, {"DATABASE_URL": DB}), redirect_stdout(
            io.StringIO()
        ):
            migrator.migrate(root / "database/migrations")

    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def test_real_session_oauth_callback_inbox_and_tenant_isolation(self):
        first = self.register("first-runtime@example.test")
        other = self.register("other-runtime@example.test")
        fake = FakeTransport()
        with patch.dict(os.environ, configuration()), patch(
            "instagram_runtime.InstagramHTTPTransport", return_value=fake
        ), TestClient(app, base_url=ORIGIN, headers=first.headers) as client:
            client.cookies.update(first.cookies)
            readiness = client.get("/api/v1/integrations/readiness")
            self.assertEqual(readiness.status_code, 200, readiness.text)
            self.assertTrue(readiness.json()["instagram"]["oauth_available"])
            self.assertFalse(readiness.json()["instagram"]["send_enabled"])
            self.assertNotIn(SECRET, readiness.text)
            started = client.post("/api/v1/instagram/meta/oauth/start", json={})
            self.assertEqual(started.status_code, 200, started.text)
            state = started.json()["state"]
            self.assertEqual(
                client.get("/api/v1/instagram/meta/status").json()["status"],
                "disconnected",
            )
            wrong_business = other.get(
                RETURN_PATH,
                params={"state": state, "code": "synthetic-code"},
                follow_redirects=False,
            )
            self.assertEqual(wrong_business.status_code, 303)
            self.assertTrue(wrong_business.headers["location"].endswith("=failed"))
            self.assertEqual(fake.calls, [])
            completed = client.get(
                RETURN_PATH,
                params={"state": state, "code": "synthetic-code"},
                follow_redirects=False,
            )
            self.assertEqual(completed.status_code, 303)
            self.assertTrue(completed.headers["location"].endswith("=connected"))
            self.assertNotIn(state, completed.headers["location"])
            self.assertNotIn("synthetic-code", completed.headers["location"])
            self.assertEqual(
                client.get("/api/v1/instagram/meta/status").json()["status"],
                "connected",
            )
            self.assertEqual(
                other.get("/api/v1/instagram/meta/status").json()["status"],
                "disconnected",
            )
            count = len(fake.calls)
            replay = client.get(
                RETURN_PATH,
                params={"state": state, "code": "synthetic-code"},
                follow_redirects=False,
            )
            self.assertTrue(replay.headers["location"].endswith("=failed"))
            self.assertEqual(len(fake.calls), count)
            provider = TestClient(app, base_url=ORIGIN)
            query = {
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY,
                "hub.challenge": "synthetic-challenge",
            }
            self.assertEqual(
                provider.get("/webhooks/instagram", params=query).text,
                "synthetic-challenge",
            )
            raw = json.dumps(incoming_payload()).encode()
            signature = (
                "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
            )
            result = provider.post(
                "/webhooks/instagram",
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": signature,
                },
            )
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["processed"], 1)
            duplicate = provider.post(
                "/webhooks/instagram",
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": signature,
                },
            )
            self.assertEqual(duplicate.json()["duplicates"], 1)
            with psycopg.connect(DB) as conn:
                rows = conn.execute(
                    "SELECT workspace_id, encrypted_token FROM socialmei.ig_meta_connections WHERE status='connected'"
                ).fetchall()
                self.assertEqual(len(rows), 1)
                self.assertNotIn("synthetic-long-token", rows[0][1])
                message = conn.execute(
                    "SELECT workspace_id FROM socialmei.me_messages WHERE origin='instagram'"
                ).fetchall()
                self.assertEqual(message, [(rows[0][0],)])
