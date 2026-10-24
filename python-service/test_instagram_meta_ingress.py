"""Signed Meta-shaped fixtures only; disposable PostgreSQL and no provider I/O."""

import hashlib
import hmac
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from app import app
from account_auth import COOKIE, csrf
from instagram_meta_ingress import (
    InstagramIngressService,
    ingress_service,
    parse_message_events,
)
import test_instagram_persistent_oauth as oauth
from test_instagram_simulation import DB, ENV, ORIGIN, TOKEN

PATH = "/internal/instagram/meta/webhooks"
KEY = "isolated-signing-secret-never-production-123"
VERIFY = "isolated-verify-token-never-production-123"
FLAGS = {
    "SOCIALMEI_INSTAGRAM_INGRESS_MODE": "isolated",
    "SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT": "isolated",
}


def payload(
    mid="mid-synthetic-fixture",
    text="  Mensagem original\n",
    account="987654321",
    sender="123456789",
    **extra
):
    message = {"mid": mid, "text": text, **extra}
    return {
        "object": "instagram",
        "entry": [
            {
                "id": account,
                "time": 1,
                "messaging": [
                    {
                        "sender": {"id": sender},
                        "recipient": {"id": account},
                        "timestamp": 1792770000123,
                        "message": message,
                    }
                ],
            }
        ],
    }


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode()


def signature(raw):
    return "sha256=" + hmac.new(KEY.encode(), raw, hashlib.sha256).hexdigest()


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.service = InstagramIngressService(app_secret=KEY, verify_token=VERIFY)

    def test_signature_and_parser_reject_before_database(self):
        with patch(
            "instagram_meta_ingress.connect", side_effect=AssertionError("DB accessed")
        ):
            for raw, sig in (
                (b"{}", ""),
                (encoded(payload()), "sha256=" + "0" * 64),
                (b"x" * 65537, "bad"),
            ):
                with self.assertRaises(Exception):
                    self.service.receive(raw, sig)
            raw = b'{"object":"instagram","object":"instagram","entry":[]}'
            with self.assertRaises(Exception):
                self.service.receive(raw, signature(raw))
        events = parse_message_events(
            encoded(payload()), signature(encoded(payload())), KEY
        )
        self.assertEqual(events[0].text, "  Mensagem original\n")

    def test_defaults_closed_and_signature_challenge(self):
        with patch.dict(os.environ, {**ENV, **FLAGS}):
            self.assertEqual(TestClient(app).post(PATH, content=b"{}").status_code, 503)
        self.assertEqual(self.service.challenge("subscribe", VERIFY, "123"), "123")
        with self.assertRaises(Exception):
            self.service.challenge("subscribe", "wrong", "123")

    def test_query_privacy_disabled_success_failure_and_duplicate_headers(self):
        observed = []

        async def recorder(scope, receive, send):
            await app(scope, receive, send)
            if scope.get("type") == "http":
                observed.append(scope.get("query_string"))

        with patch.dict(os.environ, {**ENV, **FLAGS}):
            client = TestClient(recorder)
            query = {
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY,
                "hub.challenge": "123",
            }
            closed = client.get(PATH, params=query)
            self.assertEqual(closed.status_code, 503)
            self.assertEqual(closed.headers["cache-control"], "no-store")
            app.dependency_overrides[ingress_service] = lambda: self.service
            try:
                accepted = client.get(PATH, params=query)
                self.assertEqual((accepted.status_code, accepted.text), (200, "123"))
                self.assertEqual(accepted.headers["x-content-type-options"], "nosniff")
                denied = client.get(
                    PATH + "/", params={**query, "hub.verify_token": "wrong"}
                )
                self.assertEqual(denied.status_code, 403)
                self.assertNotIn(VERIFY, denied.text)
                duplicate = client.post(
                    PATH,
                    content=encoded(payload()),
                    headers=[
                        ("Content-Type", "application/json"),
                        ("X-Hub-Signature-256", signature(encoded(payload()))),
                        ("X-Hub-Signature-256", "bad"),
                    ],
                )
                self.assertEqual(duplicate.status_code, 403)
                self.assertTrue(observed and all(raw == b"" for raw in observed))
            finally:
                app.dependency_overrides.pop(ingress_service, None)

    def test_preflight_privacy_wraps_cors_success_and_rejection(self):
        import importlib.util
        from pathlib import Path
        from instagram_meta_ingress import WebhookQueryPrivacy

        with patch.dict(os.environ, {"SOCIALMEI_CORS_ORIGINS": ORIGIN}):
            spec = importlib.util.spec_from_file_location(
                "instagram_privacy_regression_app", Path(__file__).with_name("app.py")
            )
            configured = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(configured)
            isolated = configured.app
        observed = []

        async def recorder(scope, receive, send):
            await isolated(scope, receive, send)
            if scope.get("type") == "http":
                observed.append(scope.get("query_string"))

        with patch(
            "instagram_meta_ingress.connect", side_effect=AssertionError("DB accessed")
        ):
            client = TestClient(recorder)
            for method, status in (("GET", 200), ("PUT", 400)):
                response = client.options(
                    PATH + "?hub.verify_token=secret-marker",
                    headers={
                        "Origin": ORIGIN,
                        "Access-Control-Request-Method": method,
                    },
                )
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                self.assertNotIn("secret-marker", response.text)
        self.assertEqual(observed, [b"", b""])
        self.assertEqual(isolated.user_middleware[0].cls, WebhookQueryPrivacy)

    def test_identity_body_bounds_and_unsupported_shapes_never_reach_db(self):
        variants = []
        wrong = payload()
        wrong["entry"][0]["messaging"][0]["recipient"]["id"] = "111"
        variants.append(wrong)
        for text in ("", "  ", "bad\x00text", "x" * 8193):
            variants.append(payload(text=text))
        variants.extend([payload(mid="x" * 1025), payload(mid="bad mid")])
        changed = payload()
        changed["entry"][0]["workspace_id"] = 1
        variants.append(changed)
        edits = payload()
        event = edits["entry"][0]["messaging"][0]
        event["message_edit"] = event.pop("message")
        variants.append(edits)
        with patch(
            "instagram_meta_ingress.connect", side_effect=AssertionError("DB accessed")
        ):
            for variant in variants:
                raw = encoded(variant)
                with self.subTest(index=variants.index(variant)), self.assertRaises(
                    Exception
                ):
                    self.service.receive(raw, signature(raw))
        maximum = encoded(payload(mid="m" * 1024, text="á" * 4096))
        self.assertEqual(len(parse_message_events(maximum, signature(maximum), KEY)), 1)
        a = payload()
        b = payload()
        b["entry"][0]["time"] = 999
        self.assertEqual(
            parse_message_events(encoded(a), signature(encoded(a)), KEY)[
                0
            ].canonical_fingerprint,
            parse_message_events(encoded(b), signature(encoded(b)), KEY)[
                0
            ].canonical_fingerprint,
        )


@unittest.skipUnless(DB, "Disposable PostgreSQL not configured")
class DatabaseTests(unittest.TestCase):
    setUpClass = classmethod(oauth.PersistentTests.setUpClass.__func__)
    tearDown = oauth.PersistentTests.tearDown
    begin = oauth.PersistentTests.begin
    complete = oauth.PersistentTests.complete
    post = oauth.PersistentTests.post

    def setUp(self):
        oauth.PersistentTests.setUp(self)
        self.flags = patch.dict(os.environ, FLAGS)
        self.flags.start()
        self.addCleanup(self.flags.stop)
        self.ingress = InstagramIngressService(app_secret=KEY, verify_token=VERIFY)
        app.dependency_overrides[ingress_service] = lambda: self.ingress
        self.addCleanup(app.dependency_overrides.pop, ingress_service, None)
        self.assertEqual(self.complete(self.begin()).status_code, 200)

    def receive(self, value, raw=None):
        raw = encoded(value) if raw is None else raw
        return self.client.post(
            PATH,
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature(raw),
            },
        )

    def test_text_durable_read_original_time_and_json_order_replay(self):
        value = payload(mid="m" * 300)
        first = self.receive(value)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["processed"], 1)
        value["entry"][0]["time"] = 999
        replay = self.receive(value, raw=json.dumps(value, sort_keys=True).encode())
        self.assertEqual(replay.json()["duplicates"], 1)
        rows = self.client.get("/api/v1/message-enrichment/conversations").json()[
            "items"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["origin"], "instagram")
        self.assertEqual(rows[0]["account_ref"], "instagram:987654321")
        self.assertEqual(rows[0]["messages"][0]["text"], "  Mensagem original\n")
        self.assertEqual(
            datetime.fromisoformat(
                rows[0]["messages"][0]["occurred_at"].replace("Z", "+00:00")
            ),
            datetime(2026, 10, 23, 15, 40, 0, 123000, tzinfo=timezone.utc),
        )

    def test_signature_invalid_accounts_scopes_and_disabled_connection(self):
        raw = encoded(payload())
        self.assertEqual(
            self.client.post(
                PATH,
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "bad",
                },
            ).status_code,
            403,
        )
        self.assertEqual(self.receive(payload(account="111")).status_code, 404)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET scopes=ARRAY['instagram_business_basic'] WHERE workspace_id=%s",
                (self.identity["workspace_id"],),
            )
        self.assertEqual(self.receive(payload()).status_code, 404)
        self.assertEqual(self.post("/connection/disconnect").status_code, 200)
        self.assertEqual(self.receive(payload()).status_code, 404)

    def test_echo_unsupported_receipt_never_create_messages(self):
        echo = payload(mid="echo-mid", is_echo=True)
        event = echo["entry"][0]["messaging"][0]
        event["sender"], event["recipient"] = event["recipient"], event["sender"]
        self.assertEqual(self.receive(echo).status_code, 200)
        self.assertEqual(
            self.receive(
                payload(mid="attachment-mid", attachments=[{"type": "image"}])
            ).status_code,
            200,
        )
        receipt = payload()
        event = receipt["entry"][0]["messaging"][0]
        del event["message"]
        event["read"] = {"mid": "read-event"}
        self.assertEqual(self.receive(receipt).status_code, 200)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.me_messages WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.ig_meta_ingress_events WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                3,
            )

    def test_duplicate_concurrent_conflict_and_rollback(self):
        value = payload()
        raw = encoded(value)
        with ThreadPoolExecutor(2) as pool:
            results = list(
                pool.map(lambda _: self.ingress.receive(raw, signature(raw)), range(2))
            )
        self.assertEqual(sorted(row["processed"] for row in results), [0, 1])
        self.assertEqual(
            self.receive(payload(text="Conflicting body")).status_code, 409
        )
        with patch(
            "instagram_meta_ingress._append_inbox_message",
            side_effect=RuntimeError("fixture failure"),
        ):
            response = self.receive(payload(mid="failed-message"))
            self.assertEqual(response.status_code, 503)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.ig_meta_ingress_events WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                1,
            )
        self.assertEqual(self.receive(payload(mid="failed-message")).status_code, 200)

    def test_reconnect_same_thread_and_transfer_does_not_copy_replay(self):
        self.assertEqual(self.receive(payload()).status_code, 200)
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.assertEqual(self.receive(payload(mid="later")).status_code, 200)
        self.assertEqual(self.post("/connection/disconnect").status_code, 200)
        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.assertEqual(self.receive(payload()).json()["duplicates"], 1)
        rows = self.client.get("/api/v1/message-enrichment/conversations").json()[
            "items"
        ]
        self.assertEqual(rows, [])
        self.assertEqual(
            self.receive(payload(mid="new-owner-message")).json()["processed"], 1
        )
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.me_conversations WHERE workspace_id=%s",
                    (self.identities[0]["workspace_id"],),
                ).fetchone()[0],
                1,
            )

    def test_synthetic_api_refuses_provider_data_and_no_stub_enrichment(self):
        self.assertEqual(self.receive(payload()).status_code, 200)
        with patch.dict(
            os.environ,
            {
                "SOCIALMEI_MESSAGE_ENRICHMENT_MODE": "stub",
                "SOCIALMEI_MESSAGE_ENRICHMENT_TEST_KEY": "fixture-enrichment-key-at-least-32-chars",
            },
        ):
            incoming = {
                "schema_version": 1,
                "operation_id": "0f729cff-daf3-475c-87cf-3f71b1c4e083",
                "channel": "instagram",
                "account_ref": "instagram:987654321",
                "contact_ref": "instagram:123456789",
                "contact_name": "Pessoa",
                "external_message_id": "test",
                "text": "test",
            }
            self.assertEqual(
                self.client.post(
                    "/api/v1/message-enrichment/synthetic-messages",
                    json=incoming,
                    headers=self.headers,
                ).status_code,
                422,
            )
            rows = self.client.get("/api/v1/message-enrichment/conversations").json()[
                "items"
            ]
            message = rows[0]["messages"][0]
            result = self.client.post(
                "/api/v1/message-enrichment/messages/" + str(message["id"]) + "/enrich",
                json={
                    "schema_version": 1,
                    "operation_id": "0f729cff-daf3-475c-87cf-3f71b1c4e083",
                    "expected_revision": message["revision"],
                },
                headers=self.headers,
            )
            self.assertEqual(result.status_code, 409, result.text)

    def test_contact_workspace_isolation_and_source_order(self):
        self.assertEqual(self.receive(payload(mid="newer")).status_code, 200)
        older = payload(mid="older")
        older["entry"][0]["messaging"][0]["timestamp"] -= 60000
        self.assertEqual(self.receive(older).status_code, 200)
        self.assertEqual(
            self.receive(payload(mid="other-contact", sender="333")).status_code, 200
        )
        rows = self.client.get("/api/v1/message-enrichment/conversations").json()[
            "items"
        ]
        self.assertEqual(len(rows), 2)
        original = next(
            row for row in rows if row["contact_ref"] == "instagram:123456789"
        )
        self.assertEqual(
            [m["external_message_id"] for m in original["messages"]], ["older", "newer"]
        )
        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        self.assertEqual(
            self.client.get("/api/v1/message-enrichment/conversations").json()["items"],
            [],
        )
        self.transport.account = "111222"
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.assertEqual(
            self.receive(payload(mid="other-business", account="111222")).status_code,
            200,
        )
        rows = self.client.get("/api/v1/message-enrichment/conversations").json()[
            "items"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["account_ref"], "instagram:111222")

    def test_transfer_kind_change_conflicts_and_expiration_blocks_new_data(self):
        self.assertEqual(
            self.receive(
                payload(mid="ignored", attachments=[{"type": "image"}])
            ).status_code,
            200,
        )
        self.assertEqual(self.post("/connection/disconnect").status_code, 200)
        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.assertEqual(self.receive(payload(mid="ignored")).status_code, 409)
        self.assertEqual(
            self.client.get("/api/v1/message-enrichment/conversations").json()["items"],
            [],
        )
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '1 day',expires_at=NOW()-INTERVAL '1 second' WHERE workspace_id=%s AND status='connected'",
                (self.identity["workspace_id"],),
            )
        self.assertEqual(self.receive(payload(mid="expired")).status_code, 404)

    def test_batch_is_atomic_with_unknown_account_and_insert_failure(self):
        batch = payload(mid="atomic")
        batch["entry"].extend(payload(account="999", mid="unknown")["entry"])
        self.assertEqual(self.receive(batch).status_code, 404)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.ig_meta_ingress_events WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                0,
            )
        before = self.ingress
        from instagram_meta_ingress import _append_inbox_message as original

        calls = []

        def fail_second(*args, **kwargs):
            calls.append(True)
            if len(calls) == 2:
                raise RuntimeError("synthetic database failure")
            return original(*args, **kwargs)

        batch = payload(mid="atomic-first")
        batch["entry"][0]["messaging"].extend(
            payload(mid="atomic-second")["entry"][0]["messaging"]
        )
        with patch(
            "instagram_meta_ingress._append_inbox_message", side_effect=fail_second
        ):
            self.assertEqual(self.receive(batch).status_code, 503)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.me_messages WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.ig_meta_ingress_events WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                0,
            )
        self.assertEqual(self.receive(batch).json()["processed"], 2)

    def test_disconnect_and_rebind_between_resolution_and_lock_reject_without_partial_write(
        self,
    ):
        import threading
        from instagram_meta_ingress import lock_oauth_workspace as original_lock

        resolved = threading.Event()
        proceed = threading.Event()

        def paused_lock(conn, workspace):
            resolved.set()
            if not proceed.wait(10):
                raise RuntimeError("synthetic pause expired")
            return original_lock(conn, workspace)

        raw = encoded(payload(mid="disconnection-race"))

        def receive():
            try:
                return self.ingress.receive(raw, signature(raw))
            except Exception as error:
                return getattr(error, "status_code", 500)

        with patch(
            "instagram_meta_ingress.lock_oauth_workspace", side_effect=paused_lock
        ):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(receive)
                self.assertTrue(resolved.wait(5))
                self.assertEqual(self.post("/connection/disconnect").status_code, 200)
                self.identity = self.identities[1]
                self.client.cookies.set(COOKIE, "c" * 64)
                self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
                self.assertEqual(self.complete(self.begin()).status_code, 200)
                proceed.set()
                self.assertEqual(future.result(10), 404)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.me_messages WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                0,
            )

    def test_multitenant_reversed_batches_concurrently_share_global_dedup(self):
        import threading

        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        self.transport.account = "555555"
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        first = payload(mid="cross-first")
        first["entry"].extend(payload(account="555555", mid="cross-second")["entry"])
        second = {**first, "entry": list(reversed(first["entry"]))}
        gate = threading.Barrier(2)

        def receive(value):
            raw = encoded(value)
            gate.wait(5)
            return self.ingress.receive(raw, signature(raw))

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(receive, (first, second)))
        self.assertEqual(sorted(row["processed"] for row in results), [0, 2])
        self.assertEqual(sorted(row["duplicates"] for row in results), [0, 2])
        with psycopg.connect(DB) as conn:
            rows = conn.execute(
                "SELECT workspace_id,COUNT(*) FROM socialmei.ig_meta_ingress_events WHERE workspace_id=ANY(%s) GROUP BY workspace_id",
                ([identity["workspace_id"] for identity in self.identities],),
            ).fetchall()
        self.assertEqual(sorted(count for _, count in rows), [1, 1])

    def test_webhook_needs_no_human_session_but_inbox_read_does(self):
        raw = encoded(payload())
        anonymous = TestClient(app, base_url=ORIGIN)
        result = anonymous.post(
            PATH,
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature(raw),
            },
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(
            anonymous.get("/api/v1/message-enrichment/conversations").status_code, 401
        )
        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        with psycopg.connect(DB) as conn:
            original = conn.execute(
                "SELECT external_account_id,event_key,connection_id,message_id FROM socialmei.ig_meta_ingress_events WHERE workspace_id=%s",
                (self.identities[0]["workspace_id"],),
            ).fetchone()
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    conn.execute(
                        "INSERT INTO socialmei.ig_meta_ingress_events(external_account_id,event_key,workspace_id,connection_id,kind,fingerprint,status,message_id) VALUES(%s,%s,%s,%s,'message',%s,'processed',%s)",
                        (
                            original[0],
                            "d" * 64,
                            self.identity["workspace_id"],
                            original[2],
                            "f" * 64,
                            original[3],
                        ),
                    )
