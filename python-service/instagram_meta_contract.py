"""Fail-closed Instagram Login contracts, without external I/O.

This module prepares the real Meta integration boundary. It deliberately exposes
no FastAPI routes, provider network client, database writes or token storage.
A production integration must supply a durable, single-use session-bound OAuth
state, encrypted token storage, permission checks and tenant mapping separately.
"""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


MAX_WEBHOOK_BYTES = 64 * 1024
MAX_ENTRIES = 50
MAX_EVENTS = 200

INSTAGRAM_LOGIN_SCOPES = frozenset(
    {
        "instagram_business_basic",
        "instagram_business_manage_messages",
        "instagram_business_content_publish",
        "instagram_business_manage_comments",
    }
)
_EMBED_PARAMETERS = frozenset(
    {"client_id", "redirect_uri", "response_type", "scope", "force_reauth", "enable_fb_login"}
)
_SIGNATURE = re.compile(r"sha256=[0-9a-f]{64}\Z")
_STATE = re.compile(r"[A-Za-z0-9_-]{32,160}\Z")


class MetaContractError(ValueError):
    """Invalid Instagram contract, with no secret or personal data in the error."""


@dataclass(frozen=True)
class VerifiedEnvelope:
    """Safe verification summary, not a routable or persisted conversation event."""

    entries: int
    messaging_events: int
    change_events: int


def authorization_url_from_embed(embed_url, callback_uri, state, *, required_scopes):
    """Validate a dashboard-provided Instagram Login embed before adding OAuth state.

    The caller must first persist a hashed, expiring state bound to session,
    workspace and user. This function never generates or saves that state.
    """
    if not isinstance(embed_url, str) or len(embed_url) > 4096:
        raise MetaContractError("URL de autorização inválida.")
    try:
        parsed = urlsplit(embed_url)
        callback = urlsplit(callback_uri)
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except (ValueError, TypeError, AttributeError):
        raise MetaContractError("URL de autorização inválida.") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"www.instagram.com", "instagram.com"}
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path.rstrip("/") != "/oauth/authorize"
        or parsed.fragment
        or callback.scheme != "https"
        or not callback.hostname
        or callback.username is not None
        or callback.password is not None
        or callback.fragment
    ):
        raise MetaContractError("Origem ou callback não autorizado.")
    if not isinstance(state, str) or not _STATE.fullmatch(state):
        raise MetaContractError("State OAuth inválido.")
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys) or not set(keys) <= _EMBED_PARAMETERS:
        raise MetaContractError("Parâmetros OAuth inesperados.")
    data = dict(pairs)
    if (
        not data.get("client_id", "").isdigit()
        or not data["client_id"]
        or data.get("redirect_uri") != callback_uri
        or data.get("response_type") != "code"
    ):
        raise MetaContractError("Configuração OAuth incompatível.")
    granted = data.get("scope", "").split(",")
    required = tuple(required_scopes)
    if (
        not granted
        or len(set(granted)) != len(granted)
        or set(granted) != set(required)
        or "instagram_business_basic" not in required
        or not set(required) <= INSTAGRAM_LOGIN_SCOPES
    ):
        raise MetaContractError("Escopos OAuth incompatíveis.")
    for option in ("force_reauth", "enable_fb_login"):
        if option in data and data[option] not in {"true", "false"}:
            raise MetaContractError("Opção OAuth inválida.")
    data["state"] = state
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(data), ""))


def verify_webhook_signature(raw_body, signature, app_secret, *, max_bytes=MAX_WEBHOOK_BYTES):
    """Authenticate raw webhook bytes before any JSON parsing or processing."""
    if not isinstance(raw_body, bytes) or not raw_body or len(raw_body) > max_bytes:
        raise MetaContractError("Corpo de webhook inválido.")
    if not isinstance(app_secret, str) or len(app_secret) < 32:
        raise MetaContractError("Verificação indisponível.")
    if not isinstance(signature, str) or not _SIGNATURE.fullmatch(signature):
        raise MetaContractError("Assinatura ausente ou inválida.")
    expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise MetaContractError("Assinatura inválida.")


def verify_webhook_challenge(mode, token, challenge, verify_token):
    """Return Meta's challenge only for a correctly authenticated subscription."""
    if not isinstance(verify_token, str) or len(verify_token) < 32:
        raise MetaContractError("Verificação indisponível.")
    if (
        mode != "subscribe"
        or not isinstance(token, str)
        or not hmac.compare_digest(token.encode("utf-8"), verify_token.encode("utf-8"))
        or not isinstance(challenge, str)
        or not 1 <= len(challenge) <= 1024
    ):
        raise MetaContractError("Desafio de webhook inválido.")
    return challenge


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MetaContractError("Chave JSON duplicada.")
        result[key] = value
    return result


def inspect_verified_webhook(raw_body, signature, app_secret):
    """Validate the signed Instagram envelope; never enqueue or send messages.

    The Meta payload schema is intentionally not mapped to workspace or contact
    here. An authenticated account binding and durable replay ledger are required
    before safely forwarding any event to the existing Inbox.
    """
    verify_webhook_signature(raw_body, signature, app_secret)
    try:
        payload = json.loads(raw_body.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (UnicodeError, ValueError, TypeError):
        raise MetaContractError("Envelope JSON inválido.") from None
    if not isinstance(payload, dict) or payload.get("object") != "instagram":
        raise MetaContractError("Evento não pertence ao Instagram.")
    entries = payload.get("entry")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
        raise MetaContractError("Lote Instagram inválido.")
    messages = changes = 0
    for item in entries:
        if not isinstance(item, dict) or not re.fullmatch(r"[0-9]{1,40}", str(item.get("id", ""))):
            raise MetaContractError("Conta Instagram inválida.")
        if "time" in item and (type(item["time"]) is not int or item["time"] < 0):
            raise MetaContractError("Horário Instagram inválido.")
        for field in ("messaging", "changes"):
            events = item.get(field, [])
            if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
                raise MetaContractError("Lista de eventos Instagram inválida.")
            if field == "messaging":
                messages += len(events)
            else:
                changes += len(events)
        if messages + changes > MAX_EVENTS:
            raise MetaContractError("Lote Instagram muito grande.")
    if not messages and not changes:
        raise MetaContractError("Evento Instagram sem alterações.")
    return VerifiedEnvelope(len(entries), messages, changes)
