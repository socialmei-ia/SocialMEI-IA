"""Bounded HTTPS transport for server-owned Instagram requests, never auto-enabled."""

from contextvars import ContextVar
import logging
import re
import time
from urllib.parse import urlsplit

import httpx

from instagram_meta_adapter import (
    MAX_RESPONSE_BYTES,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)

_sensitive_request = ContextVar("instagram_sensitive_http", default=False)


class _PrivateHTTPLogs(logging.Filter):
    def filter(self, record):
        # httpx INFO includes query strings; httpcore DEBUG can include credentials.
        return not _sensitive_request.get()


_private_logs = _PrivateHTTPLogs()


def _protect_http_logs():
    names = ["httpx", "httpcore", *list(logging.Logger.manager.loggerDict)]
    for name in names:
        if (
            name == "httpx"
            or name == "httpcore"
            or name.startswith(("httpx.", "httpcore."))
        ):
            logger = logging.getLogger(name)
            if _private_logs not in logger.filters:
                logger.addFilter(_private_logs)


class InstagramHTTPTransport:
    def __init__(
        self, *, allow_sends=False, client_factory=httpx.Client, clock=time.monotonic
    ):
        if (
            type(allow_sends) is not bool
            or not callable(client_factory)
            or not callable(clock)
        ):
            raise ProviderError()
        self._allow_sends = allow_sends
        self._client_factory = client_factory
        self._clock = clock

    def _allowed(self, request):
        if not isinstance(request, ProviderRequest):
            raise ProviderError()
        try:
            url = urlsplit(request.url)
            trusted = (
                url.scheme == "https"
                and url.port in (None, 443)
                and not url.username
                and not url.password
                and not url.query
                and not url.fragment
                and request.follow_redirects is False
                and type(request.timeout_seconds) is int
                and 1 <= request.timeout_seconds <= 10
                and type(request.max_response_bytes) is int
                and 1 <= request.max_response_bytes <= MAX_RESPONSE_BYTES
            )
            oauth = (
                url.hostname == "api.instagram.com"
                and url.path == "/oauth/access_token"
                and request.method == "POST"
            ) or (
                url.hostname == "graph.instagram.com"
                and request.method == "GET"
                and (
                    url.path in {"/access_token", "/refresh_access_token"}
                    or re.fullmatch(r"/v[1-9][0-9]{0,2}\.0/me", url.path)
                )
            )
            sending = (
                self._allow_sends
                and url.hostname == "graph.instagram.com"
                and request.method == "POST"
                and re.fullmatch(r"/v[1-9][0-9]{0,2}\.0/[0-9]{1,40}/messages", url.path)
            )
            if not trusted or not (oauth or sending):
                raise ProviderError()
        except (TypeError, ValueError, AttributeError):
            raise ProviderError() from None

    def __call__(self, request):
        self._allowed(request)
        token = _sensitive_request.set(True)
        _protect_http_logs()
        failed = False
        try:
            with self._client_factory(
                verify=True,
                follow_redirects=False,
                trust_env=True,
                timeout=httpx.Timeout(
                    request.timeout_seconds, connect=min(5, request.timeout_seconds)
                ),
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=0),
            ) as client:
                _protect_http_logs()
                started = self._clock()
                kwargs = {
                    "params": dict(request.params),
                    "headers": dict(request.headers),
                }
                if request.json_body:
                    kwargs["content"] = request.json_body
                elif request.form:
                    kwargs["data"] = dict(request.form)
                with client.stream(request.method, request.url, **kwargs) as response:
                    body = bytearray()
                    for chunk in response.iter_bytes(
                        chunk_size=min(8192, request.max_response_bytes + 1)
                    ):
                        if (
                            len(body) + len(chunk) > request.max_response_bytes
                            or self._clock() - started > request.timeout_seconds
                        ):
                            raise ProviderError(outcome_unknown=True)
                        body.extend(chunk)
                    return ProviderResponse(
                        response.status_code,
                        bytes(body),
                        {
                            k: v
                            for k, v in response.headers.items()
                            if k.lower() in {"retry-after", "content-type"}
                        },
                    )
        except Exception:
            # Do not chain URL/body/proxy/credential-bearing transport exceptions.
            failed = True
        finally:
            _sensitive_request.reset(token)
        if failed:
            raise ProviderError(outcome_unknown=True) from None
