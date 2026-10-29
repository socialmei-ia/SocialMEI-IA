"""Instagram Login HTTP contracts with a mandatory injected transport.

Not registered in the application. No default HTTP client, token persistence,
public callback, publishing or automatic retries. Direct sending requires the explicitly injected transport. Secret-bearing request
fields are for a trusted transport only, never product responses or logs.
"""

import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping
from urllib.parse import parse_qsl, urlsplit

from instagram_meta_contract import INSTAGRAM_LOGIN_SCOPES

MAX_RESPONSE_BYTES = 32768
MAX_LONG_LIFETIME = 60 * 24 * 3600
BASIC_SCOPE = "instagram_business_basic"


class ProviderError(ValueError):
    """Local error metadata, never a provider response or transport exception."""

    def __init__(
        self,
        *,
        status_code=None,
        retry_after=None,
        retryable=False,
        outcome_unknown=False,
    ):
        super().__init__("Operação Instagram indisponível ou resposta inválida.")
        self.status_code = status_code
        self.retry_after = retry_after
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown


@dataclass(frozen=True)
class ProviderRequest:
    method: str
    url: str
    params: Mapping[str, str] = field(default_factory=dict, repr=False)
    form: Mapping[str, str] = field(default_factory=dict, repr=False)
    timeout_seconds: int = 10
    max_response_bytes: int = MAX_RESPONSE_BYTES
    follow_redirects: bool = False
    json_body: bytes = field(default=b"", repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
        object.__setattr__(self, "form", MappingProxyType(dict(self.form)))


@dataclass(frozen=True)
class ProviderResponse:
    status_code: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class TokenGrant:
    access_token: str = field(repr=False)
    user_id: str = field(repr=False)
    scopes: frozenset[str]
    issued_at: int
    expires_at: int
    kind: str


@dataclass(frozen=True)
class InstagramIdentity:
    user_id: str = field(repr=False)
    username: str = field(repr=False)
    account_type: str


def _opaque(value, *, maximum=16384):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise ProviderError()
    if not value.isascii() or any(
        ord(char) <= 32 or ord(char) >= 127 for char in value
    ):
        raise ProviderError()
    return value


def _user_id(value):
    if type(value) not in (int, str) or not re.fullmatch(r"[0-9]{1,40}", str(value)):
        raise ProviderError()
    return str(value)


def _scopes(values):
    if not isinstance(values, (tuple, list, set, frozenset)) or not all(
        isinstance(v, str) for v in values
    ):
        raise ProviderError()
    result = frozenset(values)
    if (
        len(result) != len(values)
        or BASIC_SCOPE not in result
        or not result <= INSTAGRAM_LOGIN_SCOPES
    ):
        raise ProviderError()
    return result


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError()


class InstagramAdapter:
    def __init__(
        self,
        *,
        client_id,
        client_secret,
        callback_uri,
        graph_version,
        transport: Callable[[ProviderRequest], ProviderResponse],
        clock=time.time,
    ):
        _user_id(client_id)
        _opaque(client_secret)
        valid_callback = False
        try:
            parsed = urlsplit(callback_uri)
            valid_callback = (
                isinstance(callback_uri, str)
                and len(callback_uri) <= 2048
                and parsed.scheme == "https"
                and bool(parsed.hostname)
                and parsed.port in (None, 443)
                and parsed.username is None
                and parsed.password is None
                and not parsed.fragment
                and not parsed.query
                and not any(
                    ord(char) <= 32 or ord(char) >= 127 for char in callback_uri
                )
            )
        except (ValueError, TypeError, AttributeError):
            pass
        if (
            not valid_callback
            or not isinstance(graph_version, str)
            or not re.fullmatch(r"v[1-9][0-9]{0,2}\.0", graph_version)
            or not callable(transport)
            or not callable(clock)
        ):
            raise ProviderError()
        self._client_id = str(client_id)
        self._client_secret = client_secret
        self._callback_uri = callback_uri
        self._version = graph_version
        self._transport = transport
        self._clock = clock

    def matches_configuration(self, callback_uri, authorization_embed):
        """Compare public OAuth metadata without exposing client credentials."""
        try:
            parameters = dict(parse_qsl(urlsplit(authorization_embed).query))
        except (ValueError, TypeError, AttributeError):
            return False
        return (
            callback_uri == self._callback_uri
            and parameters.get("client_id") == self._client_id
        )

    def _now(self):
        value = self._clock()
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ProviderError()
        return int(value)

    def _grant(self, grant, *, kind=None):
        if not isinstance(grant, TokenGrant):
            raise ProviderError()
        _opaque(grant.access_token)
        _user_id(grant.user_id)
        _scopes(grant.scopes)
        now = self._now()
        if (
            not isinstance(grant.kind, str)
            or grant.kind not in {"short", "long"}
            or (kind and grant.kind != kind)
            or type(grant.issued_at) is not int
            or type(grant.expires_at) is not int
            or not 0 <= grant.issued_at <= now < grant.expires_at
            or grant.expires_at - grant.issued_at > MAX_LONG_LIFETIME
        ):
            raise ProviderError()
        return now

    def _request(self, request, *, retryable, success_codes=(200,)):
        response = None
        try:
            response = self._transport(request)
        except Exception:
            # Raise outside the handler: even __context__ cannot retain provider secrets.
            pass
        if response is None:
            logging.getLogger("socialmei.instagram.adapter").warning("instagram_transport_unavailable")
            raise ProviderError(retryable=retryable, outcome_unknown=True)
        if (
            not isinstance(response, ProviderResponse)
            or type(response.status_code) is not int
            or not 100 <= response.status_code <= 599
            or not isinstance(response.body, bytes)
            or len(response.body) > MAX_RESPONSE_BYTES
        ):
            raise ProviderError(outcome_unknown=not retryable)
        if response.status_code not in success_codes:
            delay = None
            if isinstance(response.headers, Mapping):
                value = next(
                    (
                        v
                        for k, v in response.headers.items()
                        if isinstance(k, str) and k.lower() == "retry-after"
                    ),
                    None,
                )
                if isinstance(value, str) and re.fullmatch(r"[0-9]{1,9}", value):
                    delay = max(1, min(int(value), 3600))
            temporary = response.status_code == 429 or response.status_code >= 500
            raise ProviderError(
                status_code=response.status_code,
                retry_after=delay,
                retryable=retryable and temporary,
                outcome_unknown=response.status_code >= 500,
            )
        result = None
        try:
            result = json.loads(
                response.body.decode("utf-8"),
                object_pairs_hook=_object,
                parse_constant=_invalid_constant,
            )
        except (ValueError, UnicodeError, RecursionError):
            pass
        if not isinstance(result, dict) or "error" in result or "error_type" in result:
            logging.getLogger("socialmei.instagram.adapter").warning(
                "instagram_response_rejected http_status=%d json_object=%s error_field=%s",
                response.status_code, isinstance(result, dict),
                isinstance(result, dict) and ("error" in result or "error_type" in result),
            )
            raise ProviderError(outcome_unknown=not retryable)
        return result

    def exchange_code(self, code, *, required_scopes):
        required = _scopes(required_scopes)
        code = _opaque(code)
        payload = self._request(
            ProviderRequest(
                "POST",
                "https://api.instagram.com/oauth/access_token",
                form={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._callback_uri,
                    "code": code,
                },
            ),
            retryable=False,
        )
        grant = None
        try:
            grant = self._exchange_grant(payload, required)
        except ProviderError:
            pass
        if grant is None:
            wrapped = payload.get("data")
            item = wrapped[0] if isinstance(wrapped, list) and len(wrapped) == 1 and isinstance(wrapped[0], dict) else payload
            value = item.get("permissions")
            kind = "missing" if value is None else "text" if isinstance(value, str) else "list" if isinstance(value, list) else "other"
            values = value.split(",") if isinstance(value, str) else value if isinstance(value, list) else []
            strings = isinstance(value, (str, list)) and all(isinstance(v, str) for v in values)
            provided = set(values) if strings else set()
            token_valid = identity_valid = False
            try:
                _opaque(item.get("access_token"))
                token_valid = True
            except ProviderError:
                pass
            try:
                _user_id(item.get("user_id"))
                identity_valid = True
            except ProviderError:
                pass
            lifetime = item.get("expires_in", 3600)
            logging.getLogger("socialmei.instagram.adapter").warning(
                "instagram_exchange_rejected http_status=200 wrapped=%s permissions_kind=%s token_present=%s identity_present=%s expires_present=%s permission_count=%d permission_strings=%s required_present=%s scopes_known=%s permissions_distinct=%s extra_insights=%s token_valid=%s identity_valid=%s expires_valid=%s",
                "data" in payload, kind, "access_token" in item, "user_id" in item, "expires_in" in item,
                len(values), strings, strings and required <= provided,
                strings and provided <= INSTAGRAM_LOGIN_SCOPES,
                strings and len(provided) == len(values),
                strings and "instagram_business_manage_insights" in provided,
                token_valid, identity_valid, type(lifetime) is int and 1 <= lifetime <= 3600,
            )
            raise ProviderError(outcome_unknown=True)
        return grant

    def _exchange_grant(self, payload, required):
        # Instagram Login may return the authorized short-lived token directly,
        # or in a single-entry data array. Never guess between ambiguous grants.
        wrapped = payload.get("data")
        if "data" in payload:
            if (
                not isinstance(wrapped, list)
                or len(wrapped) != 1
                or not isinstance(wrapped[0], dict)
                or any(key in payload for key in ("access_token", "user_id", "permissions"))
            ):
                raise ProviderError()
            data = wrapped[0]
        else:
            data = payload
        permissions = data.get("permissions")
        if isinstance(permissions, str):
            permissions = permissions.split(",")
        elif not isinstance(permissions, list):
            raise ProviderError()
        if not all(isinstance(value, str) for value in permissions) or len(set(permissions)) != len(permissions):
            raise ProviderError()
        # Meta can return an additional grant from prior consent. Do not request,
        # persist or enable insights; keep the supported permissions strictly scoped.
        scopes = _scopes([value for value in permissions if value != "instagram_business_manage_insights"])
        if not required <= scopes:
            raise ProviderError()
        lifetime = data.get("expires_in", 3600)
        if type(lifetime) is not int or not 1 <= lifetime <= 3600:
            raise ProviderError()
        now = self._now()
        return TokenGrant(
            _opaque(data.get("access_token")),
            _user_id(data.get("user_id")),
            scopes,
            now,
            now + lifetime,
            "short",
        )

    def send_direct(self, access_token, account_id, recipient_id, text):
        account_id, recipient_id = _user_id(account_id), _user_id(recipient_id)
        token = _opaque(access_token)
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text.encode("utf-8")) > 1000
            or any(ord(c) < 32 and c not in "\t\n\r" for c in text)
        ):
            raise ProviderError()
        try:
            data = self._request(
                ProviderRequest(
                    "POST",
                    f"https://graph.instagram.com/{self._version}/{account_id}/messages",
                    json_body=json.dumps(
                        {"recipient": {"id": recipient_id}, "message": {"text": text}},
                        ensure_ascii=False,
                    ).encode(),
                    headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                    },
                ),
                retryable=False,
                success_codes=range(200, 300),
            )
        except ProviderError as error:
            if error.status_code is not None and (
                error.status_code < 400 or error.status_code == 408
            ):
                raise ProviderError(
                    status_code=error.status_code, outcome_unknown=True
                ) from None
            raise
        mid = data.get("message_id")
        if (
            set(data) != {"recipient_id", "message_id"}
            or data.get("recipient_id") != recipient_id
            or not isinstance(mid, str)
            or not re.fullmatch(r"[!-~]{1,1024}", mid)
        ):
            raise ProviderError(outcome_unknown=True)
        return {"recipient_id": recipient_id, "message_id": mid}

    def get_identity(self, grant):
        self._grant(grant)
        data = self._request(
            ProviderRequest(
                "GET",
                f"https://graph.instagram.com/{self._version}/me",
                params={
                    "fields": "id,username,account_type",
                    "access_token": grant.access_token,
                },
            ),
            retryable=True,
        )
        user_id = _user_id(data.get("id"))
        username = data.get("username")
        account_type = data.get("account_type")
        if (
            user_id != grant.user_id
            or not isinstance(username, str)
            or not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", username)
            or not isinstance(account_type, str)
            or account_type not in {"BUSINESS", "MEDIA_CREATOR"}
        ):
            raise ProviderError()
        return InstagramIdentity(user_id, username, account_type)

    def _long_token(self, grant, payload, now):
        lifetime = payload.get("expires_in")
        if (
            type(lifetime) is not int
            or not 1 <= lifetime <= MAX_LONG_LIFETIME
            or not isinstance(payload.get("token_type"), str)
            or payload["token_type"].lower() != "bearer"
        ):
            raise ProviderError()
        return TokenGrant(
            _opaque(payload.get("access_token")),
            grant.user_id,
            grant.scopes,
            now,
            now + lifetime,
            "long",
        )

    def extend_token(self, grant):
        now = self._grant(grant, kind="short")
        payload = self._request(
            ProviderRequest(
                "GET",
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": self._client_secret,
                    "access_token": grant.access_token,
                },
            ),
            retryable=False,
        )
        return self._long_token(grant, payload, now)

    def refresh_token(self, grant):
        now = self._grant(grant, kind="long")
        if now - grant.issued_at < 86400:
            raise ProviderError()
        payload = self._request(
            ProviderRequest(
                "GET",
                "https://graph.instagram.com/refresh_access_token",
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": grant.access_token,
                },
            ),
            retryable=False,
        )
        return self._long_token(grant, payload, now)
