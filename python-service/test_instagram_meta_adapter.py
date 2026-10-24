"""Synthetic Meta HTTP contracts; no socket, token store or external account."""

import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from instagram_meta_adapter import (
    InstagramAdapter,
    ProviderError,
    ProviderResponse,
    TokenGrant,
)

BASIC = "instagram_business_basic"
SCOPES = (BASIC, "instagram_business_manage_messages")
TOKEN = "synthetic-token-not-a-credential"
SECRET = "synthetic-app-secret-not-a-credential"
CALLBACK = "https://socialmei.invalid/meta/callback"


def response(payload, status=200, headers=None):
    return ProviderResponse(status, json.dumps(payload).encode(), headers or {})


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class InstagramAdapterTests(unittest.TestCase):
    def adapter(self, *responses, **kwargs):
        transport = FakeTransport(*responses)
        adapter = InstagramAdapter(
            client_id="1234",
            client_secret=SECRET,
            callback_uri=CALLBACK,
            graph_version="v25.0",
            transport=transport,
            clock=lambda: 100000,
            **kwargs,
        )
        return adapter, transport

    def exchange_response(self, **overrides):
        data = {
            "access_token": TOKEN,
            "user_id": "9876",
            "permissions": ",".join(SCOPES),
        }
        data.update(overrides)
        return response({"data": [data]})

    def grant(self, **kwargs):
        return replace(
            TokenGrant(TOKEN, "9876", frozenset(SCOPES), 100000, 103600, "short"),
            **kwargs,
        )

    def test_exchange_fixed_endpoint_form_and_scopes(self):
        adapter, transport = self.adapter(self.exchange_response())
        grant = adapter.exchange_code("synthetic-code", required_scopes=SCOPES)
        request = transport.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url, "https://api.instagram.com/oauth/access_token")
        self.assertEqual(
            request.form,
            {
                "client_id": "1234",
                "client_secret": SECRET,
                "redirect_uri": CALLBACK,
                "grant_type": "authorization_code",
                "code": "synthetic-code",
            },
        )
        self.assertFalse(request.follow_redirects)
        self.assertEqual(request.timeout_seconds, 10)
        self.assertEqual(request.max_response_bytes, 32768)
        self.assertEqual(grant.user_id, "9876")
        self.assertEqual(grant.scopes, frozenset(SCOPES))
        self.assertEqual(grant.expires_at, 103600)
        for value in (TOKEN, SECRET, "synthetic-code"):
            self.assertNotIn(value, repr(request))
            self.assertNotIn(value, repr(grant))
            self.assertNotIn(value, repr(adapter))

    def test_no_default_network_transport(self):
        with self.assertRaises(TypeError):
            InstagramAdapter(
                client_id="1234",
                client_secret=SECRET,
                callback_uri=CALLBACK,
                graph_version="v25.0",
            )

    def test_reject_invalid_configuration_without_transport_calls(self):
        for config in (
            {"callback_uri": "http://socialmei.invalid/callback"},
            {"callback_uri": "https://user:secret@socialmei.invalid/callback"},
            {"callback_uri": CALLBACK + "#fragment"},
            {"callback_uri": CALLBACK + "?access_token=secret"},
            {"callback_uri": "https://socialmei.invalid:bad/callback"},
            {"graph_version": "v25.0/../../me"},
            {"client_id": "bad"},
            {"client_secret": ""},
            {"transport": None},
        ):
            args = dict(
                client_id="1234",
                client_secret=SECRET,
                callback_uri=CALLBACK,
                graph_version="v25.0",
                transport=FakeTransport(),
            )
            args.update(config)
            with self.subTest(config=list(config)), self.assertRaises(ProviderError):
                InstagramAdapter(**args)

    def test_reject_scope_or_code_before_exchange(self):
        adapter, transport = self.adapter()
        for scopes in (
            (),
            ("pages_read_engagement",),
            (BASIC, BASIC),
            (BASIC, "unknown"),
        ):
            with self.subTest(scopes=scopes), self.assertRaises(ProviderError):
                adapter.exchange_code("code", required_scopes=scopes)
        for code in ("", "bad\ncode", 123, "a" * 20000):
            with self.subTest(code_type=type(code).__name__), self.assertRaises(
                ProviderError
            ):
                adapter.exchange_code(code, required_scopes=SCOPES)
        self.assertEqual(transport.requests, [])

    def test_reject_denied_or_malformed_token_grants(self):
        for overrides in (
            {"access_token": ""},
            {"access_token": "bad\ntoken"},
            {"access_token": "x" * 20000},
            {"user_id": True},
            {"user_id": "not-numeric"},
            {"permissions": BASIC},
            {"permissions": ",".join(SCOPES) + ",pages_read_engagement"},
            {"permissions": ",".join(SCOPES) + "," + BASIC},
            {"expires_in": 0},
            {"expires_in": True},
            {"expires_in": 3601},
            {"expires_in": float("nan")},
        ):
            adapter, _ = self.adapter(self.exchange_response(**overrides))
            with self.subTest(fields=list(overrides)), self.assertRaises(ProviderError):
                adapter.exchange_code("code", required_scopes=SCOPES)

    def test_reject_ambiguous_oversized_or_invalid_json(self):
        for raw in (
            b"[]",
            b'{"data":[]}',
            b'{"data":[{},{}]}',
            b'{"data":[],"data":[]}',
            b'{"a":NaN}',
            b"\xff",
            b"x" * 32769,
            b"{}",
            b"{",
        ):
            adapter, _ = self.adapter(ProviderResponse(200, raw, {}))
            with self.subTest(size=len(raw)), self.assertRaises(ProviderError):
                adapter.exchange_code("code", required_scopes=SCOPES)

    def test_exchange_transport_failure_has_no_retry_or_secret_exception_chain(self):
        adapter, transport = self.adapter(RuntimeError(SECRET + TOKEN))
        with self.assertRaises(ProviderError) as caught:
            adapter.exchange_code("code", required_scopes=SCOPES)
        self.assertEqual(len(transport.requests), 1)
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertFalse(caught.exception.retryable)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertNotIn(TOKEN, repr(caught.exception))

    def test_reject_redirects_without_second_request(self):
        adapter, transport = self.adapter(
            response({}, 302, {"Location": "https://evil.invalid/"})
        )
        with self.assertRaises(ProviderError):
            adapter.exchange_code("code", required_scopes=SCOPES)
        self.assertEqual(len(transport.requests), 1)

    def test_provider_errors_only_expose_safe_status_and_bounded_retry(self):
        for status in (400, 401, 403, 429, 500, 503):
            adapter, transport = self.adapter(
                response(
                    {"error_message": SECRET + TOKEN}, status, {"Retry-After": "999999"}
                )
            )
            with self.subTest(status=status), self.assertRaises(
                ProviderError
            ) as caught:
                adapter.exchange_code("code", required_scopes=SCOPES)
            self.assertEqual(caught.exception.status_code, status)
            self.assertFalse(caught.exception.retryable)
            self.assertEqual(caught.exception.retry_after, 3600)
            self.assertNotIn(SECRET, str(caught.exception))
            self.assertEqual(len(transport.requests), 1)

    def test_identity_only_uses_grant_and_verifies_professional_account(self):
        adapter, transport = self.adapter(
            response(
                {"id": "9876", "username": "synthetic_mei", "account_type": "BUSINESS"}
            )
        )
        identity = adapter.get_identity(self.grant())
        request = transport.requests[0]
        self.assertEqual(request.url, "https://graph.instagram.com/v25.0/me")
        self.assertEqual(request.params["access_token"], TOKEN)
        self.assertEqual(request.params["fields"], "id,username,account_type")
        self.assertNotIn(TOKEN, repr(request))
        self.assertEqual(identity.user_id, "9876")
        self.assertEqual(identity.account_type, "BUSINESS")

    def test_identity_mismatch_or_personal_account_is_rejected(self):
        for payload in (
            {"id": "9877", "username": "synthetic", "account_type": "BUSINESS"},
            {"id": "9876", "username": "synthetic", "account_type": "PERSONAL"},
            {"id": "9876", "username": "bad\nname", "account_type": "BUSINESS"},
            {"id": "9876", "username": "synthetic"},
        ):
            adapter, _ = self.adapter(response(payload))
            with self.subTest(payload_fields=list(payload)), self.assertRaises(
                ProviderError
            ):
                adapter.get_identity(self.grant())

    def test_expired_grant_never_reaches_transport(self):
        adapter, transport = self.adapter()
        with self.assertRaises(ProviderError):
            adapter.get_identity(self.grant(expires_at=100000))
        self.assertEqual(transport.requests, [])

    def test_extend_token_and_refresh_preserve_identity_and_scopes(self):
        adapter, transport = self.adapter(
            response(
                {
                    "access_token": TOKEN + "-long",
                    "token_type": "bearer",
                    "expires_in": 5184000,
                }
            ),
            response(
                {
                    "access_token": TOKEN + "-refresh",
                    "token_type": "bearer",
                    "expires_in": 5184000,
                }
            ),
        )
        long = adapter.extend_token(self.grant())
        self.assertEqual(long.kind, "long")
        self.assertEqual(long.scopes, frozenset(SCOPES))
        self.assertEqual(long.user_id, "9876")
        self.assertEqual(
            transport.requests[0].url, "https://graph.instagram.com/access_token"
        )
        self.assertEqual(
            transport.requests[0].params["grant_type"], "ig_exchange_token"
        )
        refreshed = adapter.refresh_token(
            replace(
                long,
                issued_at=long.issued_at - 86400,
                expires_at=long.expires_at - 86400,
            )
        )
        self.assertEqual(refreshed.issued_at, 100000)
        self.assertEqual(
            transport.requests[1].url,
            "https://graph.instagram.com/refresh_access_token",
        )
        self.assertEqual(transport.requests[1].params["grant_type"], "ig_refresh_token")
        self.assertNotIn(SECRET, repr(transport.requests))
        self.assertNotIn(TOKEN, repr(refreshed))

    def test_refresh_requires_live_long_token_at_least_24_hours_old(self):
        adapter, transport = self.adapter()
        for grant in (
            self.grant(),
            self.grant(kind="long"),
            self.grant(kind="long", issued_at=0, expires_at=99999),
        ):
            with self.subTest(kind=grant.kind), self.assertRaises(ProviderError):
                adapter.refresh_token(grant)
        self.assertEqual(transport.requests, [])

    def test_extend_rejects_invalid_expiry_and_wrong_token_type(self):
        for payload in (
            {"access_token": TOKEN, "token_type": "bearer", "expires_in": True},
            {"access_token": TOKEN, "token_type": "bearer", "expires_in": 0},
            {"access_token": TOKEN, "token_type": "bearer", "expires_in": 5184001},
            {"access_token": TOKEN, "token_type": "unknown", "expires_in": 100},
        ):
            adapter, _ = self.adapter(response(payload))
            with self.subTest(payload_fields=list(payload)), self.assertRaises(
                ProviderError
            ):
                adapter.extend_token(self.grant())

    def test_no_default_socket_operation(self):
        with patch(
            "socket.create_connection", side_effect=AssertionError("network forbidden")
        ):
            adapter, _ = self.adapter(self.exchange_response())
            adapter.exchange_code("code", required_scopes=SCOPES)

    def test_malformed_identity_type_remains_sanitized(self):
        for account_type in ({}, []):
            adapter, _ = self.adapter(
                response(
                    {
                        "id": "9876",
                        "username": "synthetic",
                        "account_type": account_type,
                    }
                )
            )
            with self.subTest(
                account_type=type(account_type).__name__
            ), self.assertRaises(ProviderError):
                adapter.get_identity(self.grant())

    def test_malformed_grant_kind_is_rejected_before_transport(self):
        adapter, transport = self.adapter()
        with self.assertRaises(ProviderError):
            adapter.get_identity(self.grant(kind=[]))
        self.assertEqual(transport.requests, [])

    def test_unusable_exchange_response_has_unknown_outcome(self):
        for result in (
            ProviderResponse(200, b"invalid", {}),
            response({"data": []}),
            ProviderResponse(200, b"x" * 32769, {}),
            "invalid-response",
        ):
            adapter, transport = self.adapter(result)
            with self.subTest(response_type=type(result).__name__), self.assertRaises(
                ProviderError
            ) as caught:
                adapter.exchange_code("code", required_scopes=SCOPES)
            self.assertTrue(caught.exception.outcome_unknown)
            self.assertFalse(caught.exception.retryable)
            self.assertEqual(len(transport.requests), 1)
