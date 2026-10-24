"""Persistent OAuth tests use disposable PostgreSQL and an injected fake HTTP service."""

import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.parse import urlencode

import psycopg
from fastapi.testclient import TestClient

from account_auth import COOKIE, csrf, digest
from app import app
from instagram_meta_adapter import InstagramAdapter, ProviderResponse
from instagram_token_vault import TokenBinding, TokenVault
from instagram_persistent_oauth import Callback, InstagramOAuthService, oauth_service
import test_instagram_simulation as fixtures
from test_instagram_simulation import DB, ENV, ORIGIN, TOKEN

PREFIX = "/api/v1/instagram/meta"
CALLBACK = ORIGIN + "/instagram/oauth/complete"
SCOPES = frozenset({"instagram_business_basic", "instagram_business_manage_messages"})
EMBED = "https://www.instagram.com/oauth/authorize?" + urlencode(
    {
        "client_id": "123",
        "redirect_uri": CALLBACK,
        "response_type": "code",
        "scope": ",".join(sorted(SCOPES)),
    }
)
OAUTH_ENV = {
    "SOCIALMEI_INSTAGRAM_OAUTH_MODE": "isolated",
    "SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT": "isolated",
}


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.account = "987654321"
        self.fail = False
        self.block = None
        self.started = threading.Event()

    def __call__(self, request):
        self.calls.append(request)
        self.started.set()
        if self.block:
            if not self.block.wait(10):
                raise RuntimeError("Synthetic HTTP timeout")
        if self.fail:
            raise RuntimeError("Synthetic secret must not escape")
        if request.url == "https://api.instagram.com/oauth/access_token":
            value = {
                "data": [
                    {
                        "access_token": "synthetic-short-token",
                        "user_id": self.account,
                        "permissions": ",".join(sorted(SCOPES)),
                        "expires_in": 3600,
                    }
                ]
            }
        elif request.url.endswith("/access_token"):
            value = {
                "access_token": "synthetic-long-token",
                "token_type": "bearer",
                "expires_in": 5184000,
            }
        else:
            value = {
                "id": self.account,
                "username": "synthetic_account",
                "account_type": "BUSINESS",
            }
        return ProviderResponse(200, json.dumps(value).encode())


def service(transport, vault=None):
    return InstagramOAuthService(
        adapter=InstagramAdapter(
            client_id="123",
            client_secret="synthetic-client-secret",
            callback_uri=CALLBACK,
            graph_version="v99.0",
            transport=transport,
        ),
        vault=vault or TokenVault(keys={"one": b"1" * 32}, active_key_id="one"),
        authorization_embed=EMBED,
        callback_uri=CALLBACK,
        required_scopes=SCOPES,
    )


class ClosedTests(unittest.TestCase):
    def test_no_default_provider_and_no_secrets_in_validation(self):
        with patch.dict(os.environ, {**ENV, **OAUTH_ENV}), patch(
            "account_auth.session_identity",
            return_value={"id": 1, "workspace_id": 1, "role": "owner"},
        ), patch(
            "instagram_persistent_oauth.connect",
            side_effect=AssertionError("DB accessed"),
        ):
            client = TestClient(app, base_url=ORIGIN)
            client.cookies.set(COOKIE, TOKEN)
            response = client.get(PREFIX + "/status")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_configuration_alignment_and_result_validation(self):
        adapter = InstagramAdapter(
            client_id="999",
            client_secret="synthetic-secret",
            callback_uri=CALLBACK,
            graph_version="v99.0",
            transport=FakeTransport(),
        )
        vault = TokenVault(keys={"one": b"1" * 32}, active_key_id="one")
        with self.assertRaises(ValueError):
            InstagramOAuthService(
                adapter=adapter,
                vault=vault,
                authorization_embed=EMBED,
                callback_uri=CALLBACK,
                required_scopes=SCOPES,
            )
        adapter = InstagramAdapter(
            client_id="123",
            client_secret="synthetic-secret",
            callback_uri=CALLBACK + "/other",
            graph_version="v99.0",
            transport=FakeTransport(),
        )
        with self.assertRaises(ValueError):
            InstagramOAuthService(
                adapter=adapter,
                vault=vault,
                authorization_embed=EMBED,
                callback_uri=CALLBACK,
                required_scopes=SCOPES,
            )
        for changes in (
            {},
            {"code": "a", "error": "access_denied"},
            {"error": "https://secret"},
        ):
            with self.assertRaises(ValueError):
                Callback.model_validate(
                    {"state": "a" * 43, "callback_uri": CALLBACK, **changes}
                )
        self.assertIsNone(
            Callback.model_validate(
                {"state": "a" * 43, "callback_uri": CALLBACK, "error": "access_denied"}
            ).code
        )

    def test_overridden_service_stays_closed_without_both_isolation_flags(self):
        injected = service(FakeTransport())
        app.dependency_overrides[oauth_service] = lambda: injected
        try:
            for mode, environment in (
                ("disabled", "isolated"),
                ("isolated", ""),
                ("real", "isolated"),
            ):
                with patch.dict(
                    os.environ,
                    {
                        **ENV,
                        "SOCIALMEI_INSTAGRAM_OAUTH_MODE": mode,
                        "SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT": environment,
                    },
                ), patch(
                    "account_auth.session_identity",
                    return_value={"id": 1, "workspace_id": 1, "role": "owner"},
                ), patch(
                    "instagram_persistent_oauth.connect",
                    side_effect=AssertionError("DB accessed"),
                ):
                    client = TestClient(app, base_url=ORIGIN)
                    client.cookies.set(COOKIE, TOKEN)
                    self.assertEqual(client.get(PREFIX + "/status").status_code, 503)
        finally:
            app.dependency_overrides.pop(oauth_service, None)


@unittest.skipUnless(DB, "Disposable PostgreSQL not configured")
class PersistentTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.DatabaseTests.setUpClass.__func__)
    tearDown = fixtures.DatabaseTests.tearDown

    def setUp(self):
        fixtures.DatabaseTests.setUp(self)
        self.transport = FakeTransport()
        self.service = service(self.transport)
        self.extra_env = patch.dict(os.environ, OAUTH_ENV)
        self.extra_env.start()
        self.addCleanup(self.extra_env.stop)
        app.dependency_overrides[oauth_service] = lambda: self.service
        self.addCleanup(app.dependency_overrides.pop, oauth_service, None)
        with psycopg.connect(DB) as conn:
            for i, identity in enumerate(self.identities):
                conn.execute(
                    "INSERT INTO socialmei.auth_credenciais(user_id,senha_hash) VALUES(%s,'$argon2id$fixture')",
                    (identity["id"],),
                )
                for token in ([TOKEN, "b" * 64] if i == 0 else ["c" * 64]):
                    conn.execute(
                        "INSERT INTO socialmei.auth_sessoes(token_hash,user_id,workspace_id,expira_em) VALUES(%s,%s,%s,NOW()+INTERVAL '1 day')",
                        (digest(token), identity["id"], identity["workspace_id"]),
                    )

    def post(self, path, data=None):
        return self.client.post(
            PREFIX + path, json={} if data is None else data, headers=self.headers
        )

    def begin(self):
        response = self.post("/oauth/start")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["state"]

    def complete(self, state):
        return self.post(
            "/oauth/callback",
            {"state": state, "code": "synthetic-code", "callback_uri": CALLBACK},
        )

    def connection(self):
        with psycopg.connect(DB) as conn:
            return conn.execute(
                "SELECT id,external_account_id,encrypted_token,revision,status FROM socialmei.ig_meta_connections WHERE workspace_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
                (self.identities[0]["workspace_id"],),
            ).fetchone()

    def test_durable_hash_ciphertext_status_and_replay(self):
        state = self.begin()
        with psycopg.connect(DB) as conn:
            row = conn.execute(
                "SELECT state_hash,callback_uri,consumed_at FROM socialmei.ig_meta_oauth_states WHERE workspace_id=%s",
                (self.identity["workspace_id"],),
            ).fetchone()
            self.assertEqual(row, (digest(state), CALLBACK, None))
        result = self.complete(state)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertNotIn("synthetic-long-token", result.text)
        connection_id, account, encrypted, revision, status = self.connection()
        self.assertNotIn("synthetic-long-token", encrypted)
        binding = TokenBinding(self.identity["workspace_id"], connection_id, account)
        self.assertEqual(
            self.service.vault.open(encrypted, binding), "synthetic-long-token"
        )
        status = self.client.get(PREFIX + "/status")
        self.assertEqual(status.json()["status"], "connected")
        self.assertNotIn("encrypted_token", status.text)
        self.assertNotIn(encrypted, status.text)
        calls = len(self.transport.calls)
        self.assertEqual(self.complete(state).status_code, 409)
        self.assertEqual(len(self.transport.calls), calls)

    def test_session_workspace_callback_and_expiration(self):
        state = self.begin()
        self.client.cookies.set(COOKIE, "b" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("b" * 64)
        self.assertEqual(self.complete(state).status_code, 409)
        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        self.assertEqual(self.complete(state).status_code, 409)
        self.identity = self.identities[0]
        self.client.cookies.set(COOKIE, TOKEN)
        self.headers["X-SocialMEI-CSRF"] = csrf(TOKEN)
        response = self.post(
            "/oauth/callback",
            {
                "state": state,
                "code": "synthetic-code",
                "callback_uri": CALLBACK + "/other",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.transport.calls, [])
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_oauth_states SET created_at=NOW()-INTERVAL '10 minutes',expires_at=NOW()-INTERVAL '1 second' WHERE state_hash=%s",
                (digest(state),),
            )
        self.assertEqual(self.complete(state).status_code, 409)

    def test_consumption_committed_before_http_failure(self):
        state = self.begin()
        self.transport.fail = True
        response = self.complete(state)
        self.assertEqual(response.status_code, 502, response.text)
        self.assertNotIn("Synthetic secret", response.text)
        self.transport.fail = False
        self.assertEqual(self.complete(state).status_code, 409)
        self.assertEqual(len(self.transport.calls), 1)
        with psycopg.connect(DB) as conn:
            row = conn.execute(
                "SELECT status,consumed_at IS NOT NULL FROM socialmei.ig_meta_oauth_states WHERE state_hash=%s",
                (digest(state),),
            ).fetchone()
            self.assertEqual(row, ("failed", True))

    def test_concurrent_callback_calls_provider_once(self):
        state = self.begin()

        def callback():
            try:
                self.service.callback(
                    self.identities[0], digest(TOKEN), state, "synthetic-code", CALLBACK
                )
                return 200
            except Exception as error:
                return getattr(error, "status_code", 500)

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: callback(), range(2)))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(len(self.transport.calls), 3)

    def test_disconnect_cancels_inflight_callback(self):
        state = self.begin()
        self.transport.block = threading.Event()
        self.transport.started.clear()

        def callback():
            try:
                self.service.callback(
                    self.identities[0], digest(TOKEN), state, "synthetic-code", CALLBACK
                )
                return 200
            except Exception as error:
                return getattr(error, "status_code", 500)

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(callback)
            self.assertTrue(self.transport.started.wait(5))
            self.assertEqual(self.post("/connection/disconnect").status_code, 200)
            self.transport.block.set()
            self.assertEqual(future.result(10), 409)
        self.assertIsNone(self.connection())

    def test_disconnect_reconnect_history_and_global_account_ownership(self):
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        first_id = self.connection()[0]
        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        self.assertEqual(self.complete(self.begin()).status_code, 409)
        self.identity = self.identities[0]
        self.client.cookies.set(COOKIE, TOKEN)
        self.headers["X-SocialMEI-CSRF"] = csrf(TOKEN)
        self.assertEqual(self.post("/connection/disconnect").status_code, 200)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT encrypted_token,status FROM socialmei.ig_meta_connections WHERE id=%s",
                    (first_id,),
                ).fetchone(),
                (None, "disconnected"),
            )
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.assertNotEqual(self.connection()[0], first_id)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.ig_meta_connections WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                2,
            )

    def test_rotation_missing_key_tampering_and_expiry_fail_closed(self):
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        before = self.connection()[2]
        self.service.vault = TokenVault(
            keys={"one": b"1" * 32, "two": b"2" * 32}, active_key_id="two"
        )
        self.assertEqual(self.post("/connection/rotate-key").status_code, 200)
        self.assertTrue(self.connection()[2].startswith("v1:two:"))
        self.assertNotEqual(before, self.connection()[2])
        self.service.vault = TokenVault(keys={"one": b"1" * 32}, active_key_id="one")
        failed_ciphertext = self.connection()[2]
        response = self.post("/connection/rotate-key")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("v1:two", response.text)
        self.assertEqual(failed_ciphertext, self.connection()[2])
        self.assertEqual(
            self.client.get(PREFIX + "/status").json()["credential_available"], False
        )
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '1 day',expires_at=NOW()-INTERVAL '1 second' WHERE workspace_id=%s",
                (self.identity["workspace_id"],),
            )
        self.assertEqual(
            self.client.get(PREFIX + "/status").json()["status"], "expired"
        )

    def test_auth_csrf_roles_validation_and_no_public_callback(self):
        self.assertEqual(self.client.get(PREFIX + "/oauth/callback").status_code, 405)
        self.assertEqual(
            self.client.post(PREFIX + "/oauth/start", json={}).status_code, 403
        )
        self.assertEqual(
            self.post(
                "/oauth/callback", {"state": "bad", "code": "synthetic-secret"}
            ).status_code,
            422,
        )
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.workspace_members SET role='member' WHERE workspace_id=%s",
                (self.identity["workspace_id"],),
            )
        self.identity = {**self.identity, "role": "member"}
        self.assertEqual(self.post("/oauth/start").status_code, 403)
        self.assertEqual(self.client.get(PREFIX + "/status").status_code, 200)

    def test_revoked_session_before_commit_and_new_start_cancel_previous(self):
        state = self.begin()
        newer = self.begin()
        self.assertEqual(self.complete(state).status_code, 409)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE token_hash=%s",
                (digest(TOKEN),),
            )
        self.assertEqual(self.complete(newer).status_code, 401)
        self.assertEqual(self.transport.calls, [])

    def test_constraints_reject_cross_workspace_and_corrupt_binding(self):
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        with psycopg.connect(DB) as conn:
            row = conn.execute(
                "SELECT id,external_account_id,encrypted_token FROM socialmei.ig_meta_connections WHERE workspace_id=%s AND status='connected'",
                (self.identity["workspace_id"],),
            ).fetchone()
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    conn.execute(
                        "INSERT INTO socialmei.ig_meta_audit(workspace_id,user_id,connection_id,action) VALUES(%s,%s,%s,'connected')",
                        (
                            self.identities[1]["workspace_id"],
                            self.identities[1]["id"],
                            row[0],
                        ),
                    )
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET external_account_id='123123' WHERE id=%s",
                (row[0],),
            )
        self.assertEqual(
            self.client.get(PREFIX + "/status").json()["credential_available"], False
        )
        self.assertEqual(self.post("/connection/rotate-key").status_code, 503)

    def test_expiration_clears_ciphertext_and_releases_verified_account(self):
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        old = self.connection()[0]
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '1 day',expires_at=NOW()-INTERVAL '1 second' WHERE id=%s",
                (old,),
            )
        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT status,encrypted_token FROM socialmei.ig_meta_connections WHERE id=%s",
                    (old,),
                ).fetchone(),
                ("expired", None),
            )

    def test_state_session_composite_fk_and_global_account_concurrency(self):
        with psycopg.connect(DB) as conn:
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    conn.execute(
                        "INSERT INTO socialmei.ig_meta_oauth_states(state_hash,workspace_id,user_id,session_hash,callback_uri,scopes,expires_at) VALUES(%s,%s,%s,%s,%s,%s,NOW()+INTERVAL '5 minutes')",
                        (
                            "d" * 64,
                            self.identities[1]["workspace_id"],
                            self.identities[1]["id"],
                            digest(TOKEN),
                            CALLBACK,
                            sorted(SCOPES),
                        ),
                    )
        first = self.service.start(self.identities[0], digest(TOKEN))["state"]
        second = self.service.start(self.identities[1], digest("c" * 64))["state"]

        def callback(args):
            identity, token, state = args
            try:
                self.service.callback(
                    identity, digest(token), state, "synthetic-code", CALLBACK
                )
                return 200
            except Exception as error:
                return getattr(error, "status_code", 500)

        with ThreadPoolExecutor(2) as pool:
            codes = list(
                pool.map(
                    callback,
                    [
                        (self.identities[0], TOKEN, first),
                        (self.identities[1], "c" * 64, second),
                    ],
                )
            )
        self.assertEqual(sorted(codes), [200, 409])
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.ig_meta_connections WHERE external_account_id=%s AND status='connected'",
                    (self.transport.account,),
                ).fetchone()[0],
                1,
            )

    def test_denial_consumes_state_without_http_and_status_is_read_only(self):
        state = self.begin()
        denied = self.post(
            "/oauth/callback",
            {"state": state, "error": "access_denied", "callback_uri": CALLBACK},
        )
        self.assertEqual(denied.status_code, 400, denied.text)
        self.assertEqual(self.complete(state).status_code, 409)
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '1 day',expires_at=NOW()-INTERVAL '1 second' WHERE workspace_id=%s",
                (self.identity["workspace_id"],),
            )
        before = self.connection()
        self.assertEqual(
            self.client.get(PREFIX + "/status").json()["status"], "expired"
        )
        self.assertEqual(self.connection(), before)

    def test_provider_unauthorized_does_not_continue_or_reopen_state(self):
        state = self.begin()
        calls = []

        def unauthorized(request):
            calls.append(request)
            return ProviderResponse(401, b'{"error":{"message":"synthetic-secret"}}')

        self.service = service(unauthorized)
        response = self.complete(state)
        self.assertEqual(response.status_code, 502, response.text)
        self.assertNotIn("synthetic-secret", response.text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.complete(state).status_code, 409)
        self.assertEqual(len(calls), 1)

    def test_session_revocation_demotion_and_member_removal_during_http(self):
        for change in ("revoke", "demote", "remove"):
            with self.subTest(change=change):
                state = self.begin()
                self.transport.block = threading.Event()
                self.transport.started.clear()

                def complete():
                    try:
                        self.service.callback(
                            self.identities[0],
                            digest(TOKEN),
                            state,
                            "synthetic-code",
                            CALLBACK,
                        )
                        return 200
                    except Exception as error:
                        return getattr(error, "status_code", 500)

                with ThreadPoolExecutor(1) as pool:
                    future = pool.submit(complete)
                    self.assertTrue(self.transport.started.wait(5))
                    with psycopg.connect(DB) as conn:
                        if change == "revoke":
                            conn.execute(
                                "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE token_hash=%s",
                                (digest(TOKEN),),
                            )
                        elif change == "demote":
                            conn.execute(
                                "UPDATE socialmei.workspace_members SET role='member' WHERE workspace_id=%s AND user_id=%s",
                                (self.identity["workspace_id"], self.identity["id"]),
                            )
                        else:
                            conn.execute(
                                "DELETE FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s",
                                (self.identity["workspace_id"], self.identity["id"]),
                            )
                    self.transport.block.set()
                    self.assertEqual(
                        future.result(10), 403 if change == "demote" else 401
                    )
                self.assertIsNone(self.connection())
                with psycopg.connect(DB) as conn:
                    if change == "revoke":
                        conn.execute(
                            "UPDATE socialmei.auth_sessoes SET revogada_em=NULL WHERE token_hash=%s",
                            (digest(TOKEN),),
                        )
                    elif change == "demote":
                        conn.execute(
                            "UPDATE socialmei.workspace_members SET role='owner' WHERE workspace_id=%s AND user_id=%s",
                            (self.identity["workspace_id"], self.identity["id"]),
                        )
                self.transport.block = None

    def test_reconnect_audit_and_conflict_preserve_existing_connection(self):
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        old = self.connection()[0]
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        with psycopg.connect(DB) as conn:
            actions = conn.execute(
                "SELECT action FROM socialmei.ig_meta_audit WHERE workspace_id=%s AND connection_id=%s ORDER BY id",
                (self.identity["workspace_id"], old),
            ).fetchall()
            self.assertEqual(actions, [("connected",), ("disconnected",)])
        primary = self.connection()
        self.identity = self.identities[1]
        self.client.cookies.set(COOKIE, "c" * 64)
        self.headers["X-SocialMEI-CSRF"] = csrf("c" * 64)
        self.transport.account = "456456"
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.identity = self.identities[0]
        self.client.cookies.set(COOKIE, TOKEN)
        self.headers["X-SocialMEI-CSRF"] = csrf(TOKEN)
        self.assertEqual(self.complete(self.begin()).status_code, 409)
        self.assertEqual(self.connection(), primary)

    def test_start_rate_limit_and_disabled_account(self):
        for _ in range(20):
            self.begin()
        self.assertEqual(self.post("/oauth/start").status_code, 429)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.auth_credenciais SET ativo=false WHERE user_id=%s",
                (self.identity["id"],),
            )
        self.assertEqual(self.client.get(PREFIX + "/status").status_code, 401)
        self.assertEqual(self.transport.calls, [])

    def test_provider_unauthorized_in_extend_and_identity_never_persists(self):
        for failed_stage in (2, 3):
            with self.subTest(failed_stage=failed_stage):
                state = self.begin()
                calls = []
                fake = FakeTransport()

                def unauthorized(request):
                    calls.append(request)
                    if len(calls) == failed_stage:
                        return ProviderResponse(
                            401, b'{"error":{"message":"synthetic-secret"}}'
                        )
                    return fake(request)

                self.service = service(unauthorized)
                result = self.complete(state)
                self.assertEqual(result.status_code, 502, result.text)
                self.assertNotIn("synthetic-secret", result.text)
                self.assertEqual(len(calls), failed_stage)
                self.assertIsNone(self.connection())
                self.assertEqual(self.complete(state).status_code, 409)
                self.assertEqual(len(calls), failed_stage)
                with psycopg.connect(DB) as conn:
                    self.assertEqual(
                        conn.execute(
                            "SELECT status FROM socialmei.ig_meta_oauth_states WHERE state_hash=%s",
                            (digest(state),),
                        ).fetchone(),
                        ("failed",),
                    )
                    self.assertEqual(
                        conn.execute(
                            "SELECT user_id FROM socialmei.ig_meta_audit WHERE workspace_id=%s AND action='failed' ORDER BY id DESC LIMIT 1",
                            (self.identity["workspace_id"],),
                        ).fetchone(),
                        (None,),
                    )

    def test_membership_removed_during_provider_failure_remains_sanitized(self):
        state = self.begin()
        self.transport.block = threading.Event()
        self.transport.started.clear()
        self.transport.fail = True

        def callback():
            try:
                self.service.callback(
                    self.identities[0], digest(TOKEN), state, "synthetic-code", CALLBACK
                )
                return 200, ""
            except Exception as error:
                return getattr(error, "status_code", 500), str(error)

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(callback)
            self.assertTrue(self.transport.started.wait(5))
            with psycopg.connect(DB) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT consumed_at IS NOT NULL FROM socialmei.ig_meta_oauth_states WHERE state_hash=%s",
                        (digest(state),),
                    ).fetchone(),
                    (True,),
                )
                conn.execute(
                    "DELETE FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s",
                    (self.identity["workspace_id"], self.identity["id"]),
                )
            self.transport.block.set()
            code, message = future.result(10)
            self.assertEqual(code, 502)
            self.assertNotIn("synthetic-secret", message)
            self.assertIsNone(self.connection())
        with psycopg.connect(DB) as conn:
            self.assertIsNone(
                conn.execute(
                    "SELECT state_hash FROM socialmei.ig_meta_oauth_states WHERE state_hash=%s",
                    (digest(state),),
                ).fetchone()
            )
