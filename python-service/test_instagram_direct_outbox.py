"""Direct contract fixtures; no provider I/O or production credentials."""

import json
import unittest
from instagram_meta_adapter import InstagramAdapter, ProviderResponse, ProviderError
from instagram_direct_outbox import DraftInput


class ContractTests(unittest.TestCase):
    def adapter(self, response):
        self.calls = []

        def transport(request):
            self.calls.append(request)
            return response

        return InstagramAdapter(
            client_id="123",
            client_secret="fixture-secret",
            callback_uri="https://example.test/callback",
            graph_version="v99.0",
            transport=transport,
        )

    def test_reply_text_bounds_and_destination_not_browser_selected(self):
        from pydantic import ValidationError
        from uuid import uuid4

        data = {"operation_id": str(uuid4()), "source_message_id": 1, "text": "á" * 500}
        self.assertEqual(DraftInput(**data).text, "á" * 500)
        for patch in (
            {"text": "á" * 501},
            {"text": "   "},
            {"text": "bad\x00text"},
            {"recipient_id": "123"},
            {"workspace_id": 1},
        ):
            with self.assertRaises(ValidationError):
                DraftInput(**{**data, **patch})

    def test_direct_receipt_is_strict_and_request_hides_secrets(self):
        adapter = self.adapter(
            ProviderResponse(200, b'{"recipient_id":"222","message_id":"mid-1"}')
        )
        receipt = adapter.send_direct("fixture-token", "111", "222", "  Original\n")
        self.assertEqual(receipt, {"recipient_id": "222", "message_id": "mid-1"})
        request = self.calls[0]
        self.assertEqual(request.url, "https://graph.instagram.com/v99.0/111/messages")
        self.assertEqual(
            json.loads(request.json_body),
            {"recipient": {"id": "222"}, "message": {"text": "  Original\n"}},
        )
        self.assertNotIn("fixture-token", repr(request))
        self.assertNotIn("Original", repr(request))
        for body in (
            b"{}",
            b'{"recipient_id":"333","message_id":"mid"}',
            b'{"recipient_id":"222","message_id":"bad mid"}',
        ):
            with self.assertRaises(ProviderError) as error:
                self.adapter(ProviderResponse(200, body)).send_direct(
                    "fixture-token", "111", "222", "test"
                )
            self.assertTrue(error.exception.outcome_unknown)

    def test_provider_rejections_and_unknown_are_distinct_without_auto_retry(self):
        for status, unknown in (
            (400, False),
            (401, False),
            (429, False),
            (500, True),
            (101, True),
            (301, True),
            (302, True),
            (307, True),
            (308, True),
            (408, True),
        ):
            adapter = self.adapter(
                ProviderResponse(status, b"{}", {"Retry-After": "2"})
            )
            with self.assertRaises(ProviderError) as error:
                adapter.send_direct("fixture-token", "111", "222", "text")
            self.assertEqual(error.exception.outcome_unknown, unknown)
            self.assertEqual(len(self.calls), 1)
        receipt = self.adapter(
            ProviderResponse(201, b'{"recipient_id":"222","message_id":"created"}')
        ).send_direct("fixture-token", "111", "222", "text")
        self.assertEqual(receipt["message_id"], "created")

    def test_default_dependency_never_constructs_transport_or_reads_database(self):
        from fastapi import HTTPException
        from instagram_direct_outbox import outbox_service

        with self.assertRaises(HTTPException) as error:
            outbox_service()
        self.assertEqual(error.exception.status_code, 503)


import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4, UUID
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from app import app
from account_auth import digest, COOKIE, csrf
from instagram_direct_outbox import InstagramDirectService, outbox_service
from instagram_token_vault import TokenVault
import test_instagram_meta_ingress as ingress
from test_instagram_simulation import DB, TOKEN, ORIGIN

PREFIX = "/api/v1/instagram/direct"


@unittest.skipUnless(DB, "Disposable PostgreSQL not configured")
class DatabaseTests(unittest.TestCase):
    setUpClass = classmethod(ingress.DatabaseTests.setUpClass.__func__)
    tearDown = ingress.DatabaseTests.tearDown
    begin = ingress.DatabaseTests.begin
    complete = ingress.DatabaseTests.complete
    post = ingress.DatabaseTests.post

    def setUp(self):
        ingress.DatabaseTests.setUp(self)
        self.extra_flags = patch.dict(
            os.environ, {"SOCIALMEI_INSTAGRAM_DIRECT_MODE": "isolated"}
        )
        self.extra_flags.start()
        self.addCleanup(self.extra_flags.stop)
        self.send_calls = []
        self.send_error = None
        self.send_response = None
        self.send_gate = None
        self.started = threading.Event()

        def transport(request):
            self.send_calls.append(request)
            self.started.set()
            if self.send_gate and not self.send_gate.wait(10):
                raise RuntimeError("fixture timeout")
            if self.send_error:
                raise self.send_error
            return self.send_response or ProviderResponse(
                200, b'{"recipient_id":"123456789","message_id":"reply-fixture"}'
            )

        adapter = InstagramAdapter(
            client_id="123",
            client_secret="fixture-secret",
            callback_uri="https://example.test/callback",
            graph_version="v99.0",
            transport=transport,
        )
        self.direct = InstagramDirectService(adapter=adapter, vault=self.service.vault)
        app.dependency_overrides[outbox_service] = lambda: self.direct
        self.addCleanup(app.dependency_overrides.pop, outbox_service, None)
        self.source = self.incoming()

    def incoming(self, **values):
        value = ingress.payload(mid=str(uuid4()), **values)
        value["entry"][0]["messaging"][0]["timestamp"] = int(time.time() * 1000)
        raw = ingress.encoded(value)
        self.ingress.receive(raw, ingress.signature(raw))
        with psycopg.connect(DB) as conn:
            return conn.execute(
                "SELECT id FROM socialmei.me_messages WHERE workspace_id=%s ORDER BY id DESC LIMIT 1",
                (self.identity["workspace_id"],),
            ).fetchone()[0]

    def request(self, path, data=None, method="post"):
        return getattr(self.client, method)(
            PREFIX + path, json={} if data is None else data, headers=self.headers
        )

    def draft(self, **patches):
        response = self.request(
            "/jobs",
            {
                "operation_id": str(uuid4()),
                "source_message_id": self.source,
                "text": " Original reply\n",
                **patches,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def approved(self):
        row = self.draft()
        response = self.request(
            "/jobs/" + row["id"] + "/approve",
            {"operation_id": str(uuid4()), "expected_revision": row["revision"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def run_job(self, row):
        return self.request("/jobs/" + row["id"] + "/run")

    def test_approval_confirmation_replay_and_history(self):
        operation = str(uuid4())
        row = self.draft(operation_id=operation)
        self.assertEqual(self.draft(operation_id=operation)["id"], row["id"])
        conflict = self.request(
            "/jobs",
            {
                "operation_id": operation,
                "source_message_id": self.source,
                "text": "changed",
            },
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.run_job(row).status_code, 409)
        approved = self.request(
            "/jobs/" + row["id"] + "/approve",
            {"operation_id": str(uuid4()), "expected_revision": row["revision"]},
        )
        self.assertEqual(approved.status_code, 200)
        result = self.run_job(row)
        self.assertEqual(result.json()["status"], "confirmed", result.text)
        self.assertEqual(result.json()["provider_message_id"], "reply-fixture")
        self.assertEqual(self.run_job(row).status_code, 409)
        self.assertEqual(len(self.send_calls), 1)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.ig_direct_attempts WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.ig_direct_events WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                4,
            )

    def test_edit_invalidates_approval_and_cancel_uses_revision(self):
        row = self.approved()
        response = self.request(
            "/jobs/" + row["id"],
            {
                "operation_id": str(uuid4()),
                "expected_revision": row["revision"],
                "source_message_id": self.source,
                "text": "Changed",
            },
            method="put",
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "draft")
        self.assertEqual(self.run_job(row).status_code, 409)
        self.assertEqual(
            self.request(
                "/jobs/" + row["id"] + "/cancel",
                {"operation_id": str(uuid4()), "expected_revision": row["revision"]},
            ).status_code,
            409,
        )
        self.assertEqual(
            self.request(
                "/jobs/" + row["id"] + "/cancel",
                {
                    "operation_id": str(uuid4()),
                    "expected_revision": response.json()["revision"],
                },
            ).json()["status"],
            "cancelled",
        )
        self.assertEqual(self.send_calls, [])

    def test_timeout_malformed_and_server_error_are_uncertain_without_retry(self):
        for response, error in [
            (None, RuntimeError("secret fixture")),
            (ProviderResponse(200, b"{}"), None),
            (ProviderResponse(500, b"{}"), None),
        ]:
            row = self.approved()
            self.send_error = error
            self.send_response = response
            result = self.run_job(row)
            self.assertEqual(result.json()["status"], "uncertain", result.text)
            self.assertEqual(self.run_job(row).status_code, 409)
        self.assertEqual(len(self.send_calls), 3)

    def test_known_rejection_and_rate_limit_only_safe_retry(self):
        row = self.approved()
        self.send_response = ProviderResponse(401, b"{}")
        self.assertEqual(self.run_job(row).json()["status"], "failed")
        row = self.approved()
        self.send_response = ProviderResponse(429, b"{}", {"Retry-After": "1"})
        self.assertEqual(self.run_job(row).json()["status"], "retry_ready")
        self.assertEqual(self.run_job(row).status_code, 409)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_direct_jobs SET run_after=NOW()-INTERVAL '1 second' WHERE workspace_id=%s AND id=%s",
                (self.identity["workspace_id"], row["id"]),
            )
        self.send_response = None
        self.assertEqual(self.run_job(row).json()["status"], "confirmed")

    def test_concurrent_workers_and_claim_is_committed_before_transport(self):
        row = self.approved()
        self.send_gate = threading.Event()
        entered = threading.Event()

        def competing():
            entered.set()
            return self.run_job(row)

        with ThreadPoolExecutor(2) as pool:
            future = pool.submit(
                self.direct.run, self.identity, digest(TOKEN), UUID(row["id"])
            )
            self.assertTrue(self.started.wait(5))
            with psycopg.connect(DB) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT status FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND id=%s",
                        (self.identity["workspace_id"], row["id"]),
                    ).fetchone()[0],
                    "dispatching",
                )
            competitor = pool.submit(competing)
            self.assertTrue(entered.wait(5))
            self.assertFalse(competitor.done())
            self.send_gate.set()
            self.assertEqual(future.result(10)["status"], "confirmed")
            self.assertEqual(competitor.result(10).status_code, 409)
        self.assertEqual(len(self.send_calls), 1)

    def test_claim_loss_recovered_as_uncertain_not_resent(self):
        row = self.approved()

        original_send = self.direct.adapter.send_direct

        def crash(*args):
            original_send(*args)
            raise SystemExit("fixture process loss")

        with patch.object(self.direct.adapter, "send_direct", side_effect=crash):
            with self.assertRaises(SystemExit):
                self.direct.run(self.identity, digest(TOKEN), UUID(row["id"]))
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_direct_jobs SET lease_until=NOW()-INTERVAL '1 second' WHERE workspace_id=%s AND id=%s",
                (self.identity["workspace_id"], row["id"]),
            )
        self.assertEqual(self.run_job(row).json()["status"], "uncertain")
        self.assertEqual(len(self.send_calls), 1)

    def test_revocation_window_scopes_decryption_fail_before_claim(self):
        row = self.approved()
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.me_messages SET occurred_at=NOW()-INTERVAL '25 hours' WHERE id=%s",
                (self.source,),
            )
        self.assertEqual(self.run_job(row).status_code, 409)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.me_messages SET occurred_at=NOW() WHERE id=%s",
                (self.source,),
            )
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET scopes=ARRAY['instagram_business_basic'] WHERE workspace_id=%s AND status='connected'",
                (self.identity["workspace_id"],),
            )
        self.assertEqual(self.run_job(row).status_code, 409)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET scopes=ARRAY['instagram_business_basic','instagram_business_manage_messages'],encrypted_token='broken' WHERE workspace_id=%s AND status='connected'",
                (self.identity["workspace_id"],),
            )
        self.assertEqual(self.run_job(row).status_code, 503)
        self.assertEqual(self.send_calls, [])
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT attempts FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND id=%s",
                    (self.identity["workspace_id"], row["id"]),
                ).fetchone()[0],
                0,
            )

    def test_mixed_tenants_cannot_select_or_run_other_source(self):
        row = self.approved()
        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        self.assertEqual(
            self.request(
                "/jobs",
                {
                    "operation_id": str(uuid4()),
                    "source_message_id": self.source,
                    "text": "cross",
                },
            ).status_code,
            404,
        )
        self.assertEqual(self.run_job(row).status_code, 404)
        self.assertEqual(self.client.get(PREFIX + "/jobs").json()["items"], [])
        self.assertEqual(self.send_calls, [])

    def test_approver_session_revoked_and_role_demoted_block_dispatch(self):
        row = self.approved()
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE token_hash=%s",
                (digest(TOKEN),),
            )
        self.client.cookies.set(COOKIE, "b" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("b" * 64)
        self.assertEqual(self.run_job(row).status_code, 401)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.auth_sessoes SET revogada_em=NULL WHERE token_hash=%s",
                (digest(TOKEN),),
            )
            conn.execute(
                "UPDATE socialmei.workspace_members SET role='viewer' WHERE workspace_id=%s AND user_id=%s",
                (self.identity["workspace_id"], self.identity["id"]),
            )
        self.assertEqual(self.run_job(row).status_code, 403)
        self.assertEqual(self.send_calls, [])

    def test_rotation_preserves_reply_but_reconnect_invalidates_old_source(self):
        row = self.approved()
        from instagram_token_vault import TokenBinding

        with psycopg.connect(DB) as conn:
            linked = conn.execute(
                "SELECT id,external_account_id,encrypted_token FROM socialmei.ig_meta_connections WHERE workspace_id=%s AND status='connected'",
                (self.identity["workspace_id"],),
            ).fetchone()
            binding = TokenBinding(self.identity["workspace_id"], linked[0], linked[1])
            rotated = TokenVault(
                keys={"one": b"1" * 32, "two": b"2" * 32}, active_key_id="two"
            )
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET encrypted_token=%s WHERE id=%s",
                (
                    rotated.seal(self.service.vault.open(linked[2], binding), binding),
                    linked[0],
                ),
            )
        self.direct.vault = rotated
        self.assertEqual(self.run_job(row).json()["status"], "confirmed")
        row = self.approved()
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.assertEqual(self.run_job(row).status_code, 409)

    def test_membership_and_session_cleanup_preserve_history_and_prevent_claim(self):
        row = self.approved()
        with psycopg.connect(DB) as conn:
            conn.execute(
                "DELETE FROM socialmei.auth_sessoes WHERE token_hash=%s",
                (digest(TOKEN),),
            )
        self.client.cookies.set(COOKIE, "b" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("b" * 64)
        self.assertEqual(self.run_job(row).status_code, 401)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "DELETE FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s",
                (self.identity["workspace_id"], self.identity["id"]),
            )
        self.assertEqual(self.run_job(row).status_code, 401)
        with psycopg.connect(DB) as conn:
            saved = conn.execute(
                "SELECT status,approved_by FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND id=%s",
                (self.identity["workspace_id"], row["id"]),
            ).fetchone()
        self.assertEqual(saved, ("approved", None))
        self.assertEqual(self.send_calls, [])

    def test_http_origin_csrf_and_default_closed_without_send(self):
        row = self.draft()
        path = PREFIX + "/jobs/" + row["id"] + "/approve"
        payload = {"operation_id": str(uuid4()), "expected_revision": row["revision"]}
        self.assertEqual(
            self.client.post(
                path, json=payload, headers={"Origin": ORIGIN}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                path,
                json=payload,
                headers={**self.headers, "Origin": "https://other.example.test"},
            ).status_code,
            403,
        )
        app.dependency_overrides.pop(outbox_service)
        try:
            self.assertEqual(self.client.get(PREFIX + "/jobs").status_code, 503)
        finally:
            app.dependency_overrides[outbox_service] = lambda: self.direct
        self.assertEqual(self.send_calls, [])

    def test_expired_connection_and_future_message_do_not_extend_reply_window(self):
        row = self.approved()
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.me_messages SET occurred_at=NOW()+INTERVAL '7 days' WHERE id=%s",
                (self.source,),
            )
            conn.execute(
                "UPDATE socialmei.ig_meta_ingress_events SET received_at=NOW()-INTERVAL '25 hours' WHERE workspace_id=%s AND message_id=%s",
                (self.identity["workspace_id"], self.source),
            )
        self.assertEqual(self.run_job(row).status_code, 409)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_ingress_events SET received_at=NOW() WHERE workspace_id=%s AND message_id=%s",
                (self.identity["workspace_id"], self.source),
            )
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '2 days',expires_at=NOW()-INTERVAL '1 day' WHERE workspace_id=%s AND status='connected'",
                (self.identity["workspace_id"],),
            )
        self.assertEqual(self.run_job(row).status_code, 409)
        self.assertEqual(self.send_calls, [])

    def test_database_rejects_approval_without_revision_or_fingerprint(self):
        row = self.draft()
        with psycopg.connect(DB) as conn:
            with self.assertRaises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(
                        "UPDATE socialmei.ig_direct_jobs SET status='approved' WHERE workspace_id=%s AND id=%s",
                        (self.identity["workspace_id"], row["id"]),
                    )

    def test_disposable_tenant_deletion_cascades_only_its_own_outbox_history(self):
        row = self.approved()
        self.assertEqual(self.run_job(row).json()["status"], "confirmed")
        workspace = self.identity["workspace_id"]
        other = self.identities[1]["workspace_id"]
        with psycopg.connect(DB) as conn:
            conn.execute("DELETE FROM socialmei.workspaces WHERE id=%s", (workspace,))
            for table in (
                "ig_direct_jobs",
                "ig_direct_events",
                "ig_direct_attempts",
                "ig_direct_operations",
            ):
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM socialmei."
                        + table
                        + " WHERE workspace_id=%s",
                        (workspace,),
                    ).fetchone()[0],
                    0,
                )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.workspaces WHERE id=%s", (other,)
                ).fetchone()[0],
                1,
            )

    def test_destination_field_tampering_cannot_bypass_approved_fingerprint(self):
        row = self.approved()
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_direct_jobs SET recipient_id='555' WHERE workspace_id=%s AND id=%s",
                (self.identity["workspace_id"], row["id"]),
            )
        self.assertEqual(self.run_job(row).status_code, 409)
        other_source = self.incoming(sender="333")
        with psycopg.connect(DB) as conn:
            other = conn.execute(
                "SELECT conversation_id FROM socialmei.me_messages WHERE id=%s",
                (other_source,),
            ).fetchone()[0]
            conn.execute(
                "UPDATE socialmei.ig_direct_jobs SET recipient_id='123456789',conversation_id=%s WHERE workspace_id=%s AND id=%s",
                (other, self.identity["workspace_id"], row["id"]),
            )
        self.assertEqual(self.run_job(row).status_code, 409)
        self.assertEqual(self.send_calls, [])

    def race_before_dispatch_gate(self, revoke):
        row = self.approved()
        claimed = threading.Event()
        proceed = threading.Event()
        original = self.direct._dispatch

        def paused(*args):
            claimed.set()
            if not proceed.wait(10):
                raise RuntimeError("fixture gate pause expired")
            return original(*args)

        with patch.object(self.direct, "_dispatch", side_effect=paused):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(
                    self.direct.run, self.identity, digest(TOKEN), UUID(row["id"])
                )
                self.assertTrue(claimed.wait(5))
                if revoke:
                    with psycopg.connect(DB) as conn:
                        conn.execute(
                            "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE token_hash=%s",
                            (digest(TOKEN),),
                        )
                else:
                    self.assertEqual(
                        self.post("/connection/disconnect").status_code, 200
                    )
                proceed.set()
                self.assertEqual(future.result(10)["status"], "failed")
        self.assertEqual(self.send_calls, [])

    def test_logout_winning_before_dispatch_gate_blocks_http(self):
        self.race_before_dispatch_gate(True)

    def test_disconnect_winning_before_dispatch_gate_blocks_http(self):
        self.race_before_dispatch_gate(False)

    def test_late_receipt_never_resurrects_recovered_uncertain_claim(self):
        row = self.approved()
        original = self.direct._dispatch

        def recover_before_receipt(*args):
            receipt = original(*args)
            with psycopg.connect(DB) as conn:
                conn.execute(
                    "UPDATE socialmei.ig_direct_jobs SET lease_until=NOW()-INTERVAL '1 second' WHERE workspace_id=%s AND id=%s",
                    (self.identity["workspace_id"], row["id"]),
                )
            self.assertEqual(
                self.direct.run(self.identity, digest(TOKEN), UUID(row["id"]))[
                    "status"
                ],
                "uncertain",
            )
            return receipt

        with patch.object(self.direct, "_dispatch", side_effect=recover_before_receipt):
            self.assertEqual(self.run_job(row).json()["status"], "uncertain")
        self.assertEqual(len(self.send_calls), 1)
        self.assertEqual(self.run_job(row).status_code, 409)
        with psycopg.connect(DB) as conn:
            actions = [
                r[0]
                for r in conn.execute(
                    "SELECT action FROM socialmei.ig_direct_events WHERE workspace_id=%s AND job_id=%s ORDER BY id",
                    (self.identity["workspace_id"], row["id"]),
                ).fetchall()
            ]
        self.assertEqual(actions, ["created", "approved", "dispatching", "uncertain"])

    def test_all_mutation_routes_preserve_origin_and_csrf(self):
        row = self.draft()
        for method, path, payload in (
            (
                "post",
                "/jobs",
                {
                    "operation_id": str(uuid4()),
                    "source_message_id": self.source,
                    "text": "test",
                },
            ),
            (
                "put",
                "/jobs/" + row["id"],
                {
                    "operation_id": str(uuid4()),
                    "expected_revision": 1,
                    "source_message_id": self.source,
                    "text": "changed",
                },
            ),
            (
                "post",
                "/jobs/" + row["id"] + "/approve",
                {"operation_id": str(uuid4()), "expected_revision": 1},
            ),
            (
                "post",
                "/jobs/" + row["id"] + "/cancel",
                {"operation_id": str(uuid4()), "expected_revision": 1},
            ),
            ("post", "/jobs/" + row["id"] + "/run", {}),
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    getattr(self.client, method)(
                        PREFIX + path, json=payload, headers={"Origin": ORIGIN}
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    getattr(self.client, method)(
                        PREFIX + path,
                        json=payload,
                        headers={
                            **self.headers,
                            "Origin": "https://other.example.test",
                        },
                    ).status_code,
                    403,
                )
        self.assertEqual(self.send_calls, [])

    def test_dispatch_gate_winning_serializes_session_revocation_after_http(self):
        row = self.approved()
        self.send_gate = threading.Event()
        revoking = threading.Event()

        def revoke():
            with psycopg.connect(DB) as conn:
                revoking.set()
                conn.execute(
                    "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE token_hash=%s",
                    (digest(TOKEN),),
                )
            return True

        with ThreadPoolExecutor(2) as pool:
            sending = pool.submit(
                self.direct.run, self.identity, digest(TOKEN), UUID(row["id"])
            )
            self.assertTrue(self.started.wait(5))
            revocation = pool.submit(revoke)
            self.assertTrue(revoking.wait(5))
            self.assertFalse(revocation.done())
            self.send_gate.set()
            self.assertEqual(sending.result(10)["status"], "confirmed")
            self.assertTrue(revocation.result(10))
        self.assertEqual(len(self.send_calls), 1)

    def test_different_approver_removal_before_job_lock_does_not_deadlock(self):
        row = self.draft()
        owner = self.identity
        member = {
            **self.identities[1],
            "workspace_id": owner["workspace_id"],
            "role": "member",
        }
        with psycopg.connect(DB) as conn:
            conn.execute(
                "INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'member')",
                (owner["workspace_id"], member["id"]),
            )
            conn.execute(
                "INSERT INTO socialmei.auth_sessoes(token_hash,user_id,workspace_id,expira_em) VALUES(%s,%s,%s,NOW()+INTERVAL '1 day')",
                (digest("d" * 64), member["id"], owner["workspace_id"]),
            )
        self.identity = member
        self.client.cookies.set(COOKIE, "d" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("d" * 64)
        self.assertEqual(
            self.request(
                "/jobs/" + row["id"] + "/approve",
                {"operation_id": str(uuid4()), "expected_revision": 1},
            ).status_code,
            200,
        )
        self.identity = owner
        self.client.cookies.set(COOKIE, TOKEN)
        self.headers["X-SocialMEI-CSRF"] = csrf(TOKEN)
        observed = threading.Event()
        proceed = threading.Event()
        original = self.direct._authorize

        def paused(conn, user, session, **kwargs):
            if user["id"] == member["id"]:
                observed.set()
                if not proceed.wait(10):
                    raise RuntimeError("fixture membership pause expired")
            return original(conn, user, session, **kwargs)

        with patch.object(self.direct, "_authorize", side_effect=paused):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(self.run_job, row)
                self.assertTrue(observed.wait(5))
                with psycopg.connect(DB) as conn:
                    conn.execute("SET LOCAL statement_timeout='3s'")
                    conn.execute(
                        "DELETE FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s",
                        (owner["workspace_id"], member["id"]),
                    )
                proceed.set()
                self.assertEqual(future.result(10).status_code, 401)
        self.assertEqual(self.send_calls, [])

    def test_expired_dispatch_is_quarantined_after_approver_session_revocation(self):
        row = self.draft()
        self.client.cookies.set(COOKIE, "b" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("b" * 64)
        self.assertEqual(
            self.request(
                "/jobs/" + row["id"] + "/approve",
                {"operation_id": str(uuid4()), "expected_revision": 1},
            ).status_code,
            200,
        )
        self.client.cookies.set(COOKIE, TOKEN)
        self.headers["X-SocialMEI-CSRF"] = csrf(TOKEN)
        original = self.direct.adapter.send_direct

        def crash(*args):
            original(*args)
            raise SystemExit("fixture crash after effect")

        with patch.object(self.direct.adapter, "send_direct", side_effect=crash):
            with self.assertRaises(SystemExit):
                self.direct.run(self.identity, digest(TOKEN), UUID(row["id"]))
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE token_hash=%s",
                (digest("b" * 64),),
            )
            conn.execute(
                "UPDATE socialmei.ig_direct_jobs SET lease_until=NOW()-INTERVAL '1 second' WHERE workspace_id=%s AND id=%s",
                (self.identity["workspace_id"], row["id"]),
            )
        self.assertEqual(self.run_job(row).json()["status"], "uncertain")
        self.assertEqual(len(self.send_calls), 1)
