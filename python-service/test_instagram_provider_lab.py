"""Authenticated fake-provider tests: disposable Postgres, no network provider."""
import hashlib
import hmac
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4
import psycopg
from account_auth import COOKIE, csrf
from app import app
from fastapi.testclient import TestClient
import test_instagram_simulation as fixtures
from test_instagram_simulation import ENV, TOKEN, ORIGIN, MEDIA

P = "/api/v1/instagram/provider-lab"
KEY = "isolated-test-signing-key-not-production-123"
LAB = {"SOCIALMEI_INSTAGRAM_PROVIDER": "fake", "SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT": "isolated", "SOCIALMEI_INSTAGRAM_LAB_TEST_KEY": KEY, "SOCIALMEI_MESSAGE_ENRICHMENT_MODE": "stub"}
DB = os.getenv("TEST_DATABASE_URL", "")

class DisabledTests(unittest.TestCase):
    def test_flags_fail_closed_and_auth_required(self):
        for config in [{}, {"SOCIALMEI_INSTAGRAM_PROVIDER": "fake"}, {"SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT": "isolated"}]:
            with patch.dict(os.environ, {**ENV, "SOCIALMEI_INSTAGRAM_PROVIDER": "disabled", "SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT": "", **config}), patch("account_auth.session_identity", return_value={"id": 1, "workspace_id": 1, "role": "owner"}), patch("instagram_provider_lab.connect", side_effect=AssertionError("DB accessed")):
                client = TestClient(app, base_url=ORIGIN)
                client.cookies.set(COOKIE, TOKEN)
                self.assertEqual(client.get(P + "/status").status_code, 503)
        with patch.dict(os.environ, {**ENV, **LAB}), patch("account_auth.session_identity", return_value=None):
            self.assertEqual(TestClient(app, base_url=ORIGIN).get(P + "/status").status_code, 401)

@unittest.skipUnless(DB, "Disposable Postgres not configured")
class LabTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.DatabaseTests.setUpClass.__func__)
    tearDown = fixtures.DatabaseTests.tearDown
    def setUp(self):
        fixtures.DatabaseTests.setUp(self)
        extra = patch.dict(os.environ, LAB)
        extra.start()
        self.addCleanup(extra.stop)
    def post(self, path, payload=None):
        return self.client.post(P + path, json={} if payload is None else payload, headers=self.headers)
    def connect_fake(self):
        state = self.post("/oauth/start").json()["state"]
        result = self.post("/oauth/callback", {"state": state, "code": "fake-authorization-code"})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()["account_id"]
    def event(self, account, **changes):
        return {"event_id": str(uuid4()), "account_id": account, "contact_id": "synthetic:customer-1", "contact_name": "Cliente fictício", "message_id": str(uuid4()), "text": "Quanto custa?", "occurred_at": "2026-10-22T15:00:00Z", **changes}
    def send(self, event, raw=None, signature=None):
        body = raw if raw is not None else json.dumps(event, ensure_ascii=False).encode()
        sig = signature if signature is not None else "sha256=" + hmac.new(KEY.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(P + "/webhook", content=body, headers={**self.headers, "Content-Type": "application/json", "X-Hub-Signature-256": sig})
    def test_oauth_session_workspace_expiry_replay_roles_csrf(self):
        state = self.post("/oauth/start").json()["state"]
        data = {"state": state, "code": "fake-authorization-code"}
        self.client.cookies.set(COOKIE, "b" * 64)
        old = self.headers
        self.headers = {"Origin": ORIGIN, "X-SocialMEI-CSRF": csrf("b" * 64)}
        self.assertEqual(self.post("/oauth/callback", data).status_code, 409)
        self.client.cookies.set(COOKIE, TOKEN)
        self.headers = old
        self.identity = self.identities[1]
        self.assertEqual(self.post("/oauth/callback", data).status_code, 409)
        self.identity = self.identities[0]
        self.assertEqual(self.post("/oauth/callback", data).status_code, 200)
        self.assertEqual(self.post("/oauth/callback", data).status_code, 409)
        state2 = self.post("/oauth/start").json()["state"]
        with psycopg.connect(DB) as conn:
            conn.execute("UPDATE socialmei.ig_lab_states SET expires_at=NOW()-INTERVAL '1 second' WHERE workspace_id=%s", (self.identity["workspace_id"],))
        self.assertEqual(self.post("/oauth/callback", {**data, "state": state2}).status_code, 409)
        for role in ("viewer", "member"):
            self.identity = {**self.identities[0], "role": role}
            self.assertEqual(self.post("/oauth/start").status_code, 403)
        self.identity = self.identities[0]
        self.assertEqual(self.client.post(P + "/oauth/start", json={}, headers={"Origin": ORIGIN}).status_code, 403)
        self.assertEqual(self.client.post(P + "/oauth/start", json={}, headers={**self.headers, "Origin": "https://evil.example"}).status_code, 403)
    def test_signature_dedupe_order_tenants_revocation(self):
        account = self.connect_fake()
        event = self.event(account)
        self.assertEqual(self.send(event, signature="sha256=wrong").status_code, 403)
        raw = json.dumps(event).encode()
        sig = "sha256=" + hmac.new(KEY.encode(), raw, hashlib.sha256).hexdigest()
        self.assertEqual(self.send(event, raw=raw+b" ", signature=sig).status_code, 403)
        first = self.send(event)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(self.send(event).json()["replayed"])
        self.assertTrue(self.send(event, raw=json.dumps(event, indent=2).encode()).json()["replayed"])
        alias = {**event, "event_id": str(uuid4())}
        self.assertTrue(self.send(alias).json()["replayed"])
        self.assertEqual(self.send({**alias, "event_id": str(uuid4()), "text": "Conflicting message"}).status_code, 409)
        self.assertEqual(self.send({**event, "text": "Changed"}).status_code, 409)
        second = self.send(self.event(account, occurred_at="2026-10-20T15:00:00-03:00"))
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["conversation_id"], second.json()["conversation_id"])
        with psycopg.connect(DB) as conn:
            rows = conn.execute("SELECT occurred_at FROM socialmei.me_messages WHERE conversation_id=%s ORDER BY occurred_at", (first.json()["conversation_id"],)).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], datetime(2026,10,20,18,tzinfo=timezone.utc))
        self.identity = self.identities[1]
        self.connect_fake()
        self.assertEqual(self.send(event).status_code, 404)
        self.identity = self.identities[0]
        self.assertEqual(self.client.delete(P + "/connection", headers=self.headers).status_code, 200)
        self.assertEqual(self.send(self.event(account)).status_code, 409)
        self.assertEqual(self.client.get(P + "/status").json()["status"], "revoked")
    def test_payload_bounds_invalid_date_duplicate_json_scope(self):
        account = self.connect_fake()
        self.assertEqual(self.send({}, raw=b"x"*16385).status_code, 413)
        self.assertEqual(self.send(self.event(account, occurred_at="2026-10-22T15:00:00")).status_code, 422)
        self.assertEqual(self.send({}, raw=b'{"event_id":"a","event_id":"b"}').status_code, 422)
        self.assertEqual(self.send({**self.event(account), "workspace_id": self.identities[1]["workspace_id"]}).status_code, 422)
    def test_publication_approval_failure_retry_idempotency_isolation(self):
        account = self.connect_fake()
        data = {"account_id": account, "idempotency_key": str(uuid4()), "format": "feed", "caption": "Somente teste", "media": MEDIA}
        first = self.post("/publications", data)
        self.assertEqual(first.status_code, 201, first.text)
        job = first.json()["id"]
        self.assertEqual(self.post("/publications", data).json()["id"], job)
        self.assertEqual(self.post("/publications", {**data, "caption": "Other"}).status_code, 409)
        self.assertEqual(self.post(f"/publications/{job}/run").status_code, 409)
        self.assertEqual(self.post(f"/publications/{job}/approve").status_code, 200)
        self.assertEqual(self.post(f"/publications/{job}/run", {"outcome":"failure"}).json()["status"], "failed")
        result = self.post(f"/publications/{job}/run").json()
        self.assertEqual(result["status"], "simulated-published")
        self.assertFalse(result["published"])
        self.assertTrue(result["provider_result"]["fictional"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(self.post(f"/publications/{job}/run").status_code, 409)
        self.identity = self.identities[1]
        self.assertEqual(self.client.get(P + "/publications").json()["items"], [])
        self.connect_fake()
        self.assertEqual(self.post(f"/publications/{job}/approve").status_code, 409)
        self.assertEqual(self.post("/publications", data).status_code, 404)
    def test_expiration_disconnect_revoke_cancels_approval(self):
        self.assertEqual(self.client.get(P + "/status").json()["status"], "disconnected")
        account = self.connect_fake()
        with psycopg.connect(DB) as conn:
            conn.execute("UPDATE socialmei.ig_lab_connections SET expires_at=NOW()-INTERVAL '1 second' WHERE workspace_id=%s", (self.identity["workspace_id"],))
        self.assertEqual(self.client.get(P + "/status").json()["status"], "expired")
        self.assertEqual(self.send(self.event(account)).status_code, 409)
        self.connect_fake()
        data = {"account_id": account, "idempotency_key": str(uuid4()), "format": "feed", "caption": "Teste", "media": MEDIA}
        job = self.post("/publications", data).json()["id"]
        self.post(f"/publications/{job}/approve")
        self.post("/connection/disconnect")
        self.assertEqual(self.client.get(P + "/status").json()["status"], "disconnected")
        self.connect_fake()
        self.assertEqual(self.post(f"/publications/{job}/run").status_code, 409)
        items = self.client.get(P + "/publications").json()["items"]
        self.assertFalse(items[0]["approved"])
        self.assertEqual(items[0]["status"], "failed")
    def test_retry_limit_concurrent_claim_and_media(self):
        from concurrent.futures import ThreadPoolExecutor
        account = self.connect_fake()
        data = {"account_id": account, "idempotency_key": str(uuid4()), "format": "feed", "caption": "Teste", "media": MEDIA}
        self.assertEqual(self.post("/publications", {**data, "format": "reel"}).status_code, 422)
        job = self.post("/publications", data).json()["id"]
        self.post(f"/publications/{job}/approve")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.post(f"/publications/{job}/run").status_code, range(2)))
        self.assertEqual(sorted(results), [200, 409])
        job2 = self.post("/publications", {**data, "idempotency_key": str(uuid4())}).json()["id"]
        self.post(f"/publications/{job2}/approve")
        for attempt in (1, 2, 3):
            result = self.post(f"/publications/{job2}/run", {"outcome": "failure"})
            self.assertEqual(result.json()["attempts"], attempt)
        self.assertEqual(self.post(f"/publications/{job2}/run").status_code, 409)
