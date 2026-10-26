"""Bounded provider HTTP, synthetic transports only; never opens a socket."""

import logging
import unittest
from unittest.mock import patch

import httpx
from instagram_meta_adapter import ProviderError, ProviderRequest
from instagram_http_transport import InstagramHTTPTransport


class InstagramHTTPTransportTests(unittest.TestCase):
    def transport(self, handler, **options):
        def factory(**kwargs):
            self.assertIs(kwargs["verify"], True)
            self.assertIs(kwargs["follow_redirects"], False)
            return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

        return InstagramHTTPTransport(client_factory=factory, **options)

    def test_oauth_request_preserves_form_and_bounded_response(self):
        def handler(request):
            self.assertEqual(request.url.host, "api.instagram.com")
            self.assertIn(b"client_secret=synthetic-only", request.content)
            return httpx.Response(200, json={"access_token": "synthetic-result"})

        result = self.transport(handler)(
            ProviderRequest(
                "POST",
                "https://api.instagram.com/oauth/access_token",
                form={"client_secret": "synthetic-only"},
            )
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"synthetic-result", result.body)

    def test_untrusted_destinations_and_redirects_never_followed(self):
        calls = []
        transport = self.transport(
            lambda r: calls.append(r)
            or httpx.Response(302, headers={"location": "https://evil.example/token"})
        )
        for url in (
            "http://api.instagram.com/oauth/access_token",
            "https://evil.example/token",
            "https://graph.instagram.com:444/access_token",
            "https://user:secret@graph.instagram.com/access_token",
            "https://graph.instagram.com/access_token#fragment",
            "https://graph.instagram.com/unsupported",
        ):
            with self.assertRaises(ProviderError):
                transport(ProviderRequest("GET", url))
        self.assertEqual(calls, [])
        result = transport(
            ProviderRequest("GET", "https://graph.instagram.com/access_token")
        )
        self.assertEqual(result.status_code, 302)
        self.assertEqual(len(calls), 1)

    def test_sending_requires_separate_explicit_permission(self):
        calls = []
        transport = self.transport(lambda r: calls.append(r) or httpx.Response(200))
        with self.assertRaises(ProviderError):
            transport(
                ProviderRequest(
                    "POST",
                    "https://graph.instagram.com/v99.0/123/messages",
                    json_body=b"{}",
                )
            )
        self.assertEqual(calls, [])

    def test_oversize_response_and_network_failure_are_sanitized(self):
        transport = self.transport(lambda r: httpx.Response(200, content=b"x" * 100))
        with self.assertRaises(ProviderError):
            transport(
                ProviderRequest(
                    "GET",
                    "https://graph.instagram.com/access_token",
                    max_response_bytes=32,
                )
            )

        def fail(request):
            raise httpx.ReadTimeout("private-token-in-url", request=request)

        with self.assertRaises(ProviderError) as error:
            self.transport(fail)(
                ProviderRequest("GET", "https://graph.instagram.com/access_token")
            )
        self.assertNotIn("private-token", str(error.exception))
        self.assertTrue(error.exception.outcome_unknown)

    def test_http_debug_logs_cannot_expose_tokens(self):
        records = []

        class Recorder(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        loggers = [logging.getLogger(name) for name in ("httpx", "httpcore.http11")]
        handler = Recorder()
        previous = [logger.level for logger in loggers]
        for logger in loggers:
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        try:

            def provider(request):
                logging.getLogger("httpcore.http11").debug(
                    "secret synthetic-provider-secret"
                )
                return httpx.Response(200, json={})

            self.transport(provider)(
                ProviderRequest(
                    "GET",
                    "https://graph.instagram.com/access_token",
                    params={"access_token": "synthetic-provider-secret"},
                )
            )
            logging.getLogger("httpx").info("ordinary request logging retained")
            self.assertFalse(
                any("synthetic-provider-secret" in value for value in records)
            )
            self.assertIn("ordinary request logging retained", records)
        finally:
            for logger, level in zip(loggers, previous):
                logger.removeHandler(handler)
                logger.setLevel(level)
