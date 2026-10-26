"""Durable Instagram-shaped ingress, disabled without isolated injected secrets.

No provider HTTP, profile lookup, outbound messages, publications or raw payload
storage. Trusted identity comes only from a live stored OAuth account binding.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from psycopg.rows import dict_row
from starlette.datastructures import QueryParams
from starlette.concurrency import run_in_threadpool

import settings
from database import connect, shared_data_enabled
from instagram_meta_contract import (
    MAX_EVENTS,
    MAX_WEBHOOK_BYTES,
    MetaContractError,
    inspect_verified_webhook,
    verify_webhook_challenge,
)
from instagram_persistent_oauth import _lock as lock_oauth_workspace
from message_enrichment import _append_inbox_message, fingerprint

PATH = "/internal/instagram/meta/webhooks"
PUBLIC_PATH = "/webhooks/instagram"
OAUTH_RETURN_PATH = "/api/v1/instagram/meta/oauth/return"
router = APIRouter(tags=["prepared Instagram ingress"])
MAX_MID_BYTES = 1024  # Product ingress bound; not a claimed Meta maximum.


class WebhookQueryPrivacy:
    """Remove query secrets from ASGI URLs even when dependencies reject the call."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").rstrip("/") in {PATH, PUBLIC_PATH, OAUTH_RETURN_PATH}:
            raw = scope.get("query_string", b"")
            scope["query_string"] = b""
            state = scope.setdefault("state", {})
            state["instagram_oauth_query" if scope.get("path", "").rstrip("/") == OAUTH_RETURN_PATH else "instagram_webhook_query"] = (
                QueryParams(raw) if len(raw) <= 4096 else None
            )
            original_send = send

            async def private_send(message):
                if message["type"] == "http.response.start":
                    headers = [
                        (k, v)
                        for k, v in message.get("headers", [])
                        if k.lower()
                        not in {b"cache-control", b"x-content-type-options", b"referrer-policy"}
                    ]
                    message = {
                        **message,
                        "headers": [
                            *headers,
                            (b"cache-control", b"no-store"),
                            (b"x-content-type-options", b"nosniff"),
                            (b"referrer-policy", b"no-referrer"),
                        ],
                    }
                await original_send(message)

            send = private_send
        await self.app(scope, receive, send)


def ingress_service(request: Request = None):
    from instagram_runtime import runtime_service
    return runtime_service(request, "ingress")


def _enabled():
    if (
        not (settings.instagram_ingress_isolated_enabled() or settings.instagram_runtime_enabled())
        or not shared_data_enabled()
        or settings.authentication_mode() != "enabled"
    ):
        raise HTTPException(503, "Recepção Instagram ainda não habilitada.")


def _account(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,40}", value):
        raise MetaContractError("Identidade Instagram inválida.")
    return value


def _mid(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= MAX_MID_BYTES
        or not value.isascii()
        or not re.fullmatch(r"[!-~]+", value)
    ):
        raise MetaContractError("Identidade da mensagem inválida.")
    return value


def _time(value):
    if type(value) is not int or not 0 <= value <= 253402300799999:
        raise MetaContractError("Horário da mensagem inválido.")
    return datetime.fromtimestamp(value // 1000, timezone.utc).replace(
        microsecond=(value % 1000) * 1000
    )


def _text(value):
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(c) < 32 and c not in "\t\n\r" for c in value)
    ):
        raise MetaContractError("Texto da mensagem inválido.")
    try:
        raw = value.encode("utf-8")
    except UnicodeError:
        raise MetaContractError("Texto da mensagem inválido.") from None
    if len(raw) > 8192:
        raise MetaContractError("Texto da mensagem excede o limite.")
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError()


@dataclass(frozen=True)
class MessageEvent:
    account_id: str = field(repr=False)
    sender_id: str = field(repr=False)
    recipient_id: str = field(repr=False)
    mid: str = field(repr=False)
    occurred_at: datetime
    kind: str
    text: str | None = field(default=None, repr=False)
    content_hash: str | None = field(default=None, repr=False)

    @property
    def event_key(self):
        identity = [
            "message" if self.kind in {"message", "echo", "unsupported"} else self.kind,
            self.mid,
        ]
        if self.kind == "receipt":
            identity.append(self.occurred_at.isoformat())
        return fingerprint(identity)

    @property
    def canonical_fingerprint(self):
        return fingerprint(
            {
                "account": self.account_id,
                "sender": self.sender_id,
                "recipient": self.recipient_id,
                "mid": self.mid,
                "occurred_at": self.occurred_at.isoformat(),
                "kind": self.kind,
                "text": self.text,
                "content_hash": self.content_hash,
            }
        )

    @property
    def channel(self):
        return "instagram"

    @property
    def account_ref(self):
        return "instagram:" + self.account_id

    @property
    def contact_ref(self):
        return "instagram:" + self.sender_id

    @property
    def contact_name(self):
        return "Contato do Instagram"

    @property
    def external_message_id(self):
        return self.mid


def parse_message_events(raw, signature, app_secret):
    # Existing verifier authenticates the raw bytes before parsing and enforces envelope bounds.
    inspect_verified_webhook(raw, signature, app_secret)
    try:
        body = json.loads(
            raw, object_pairs_hook=_unique, parse_constant=_invalid_constant
        )
    except (ValueError, UnicodeError, RecursionError):
        raise MetaContractError("Envelope Instagram inválido.") from None
    if set(body) - {"object", "entry"}:
        raise MetaContractError("Envelope Instagram incompatível.")
    events = []
    for entry in body["entry"]:
        if set(entry) - {"id", "time", "messaging", "changes"} or entry.get("changes"):
            raise MetaContractError("Tipo de evento Instagram ainda não suportado.")
        account = _account(entry.get("id"))
        for event in entry.get("messaging", []):
            if set(event) - {
                "sender",
                "recipient",
                "timestamp",
                "message",
                "read",
                "delivery",
            }:
                raise MetaContractError("Tipo de evento Instagram ainda não suportado.")
            sender, recipient = event.get("sender"), event.get("recipient")
            if (
                not isinstance(sender, dict)
                or set(sender) != {"id"}
                or not isinstance(recipient, dict)
                or set(recipient) != {"id"}
            ):
                raise MetaContractError("Identidade do evento inválida.")
            sender_id, recipient_id = _account(sender["id"]), _account(recipient["id"])
            occurred = _time(event.get("timestamp"))
            variants = [
                name for name in ("message", "read", "delivery") if name in event
            ]
            if len(variants) != 1:
                raise MetaContractError("Tipo de evento Instagram inválido.")
            variant = variants[0]
            details = event[variant]
            if not isinstance(details, dict):
                raise MetaContractError("Evento Instagram inválido.")
            if variant == "message":
                mid = _mid(details.get("mid"))
                echo = details.get("is_echo", False)
                if type(echo) is not bool:
                    raise MetaContractError("Indicador de eco inválido.")
                if echo:
                    if sender_id != account or recipient_id == account:
                        raise MetaContractError("Identidade de eco inválida.")
                    kind, text = "echo", None
                else:
                    if recipient_id != account or sender_id == account:
                        raise MetaContractError("Conta destinatária incompatível.")
                    unsupported = (
                        set(details) - {"mid", "text", "is_echo"}
                    ) or "text" not in details
                    kind = "unsupported" if unsupported else "message"
                    text = _text(details["text"]) if kind == "message" else None
                content_hash = fingerprint(details) if kind != "message" else None
                events.append(
                    MessageEvent(
                        account,
                        sender_id,
                        recipient_id,
                        mid,
                        occurred,
                        kind,
                        text,
                        content_hash,
                    )
                )
            else:
                if recipient_id != account or sender_id == account:
                    raise MetaContractError("Conta de recibo incompatível.")
                if variant == "read" and set(details) == {"mid"}:
                    mids = [_mid(details["mid"])]
                else:
                    raise MetaContractError("Recibo Instagram ainda não suportado.")
                for mid in mids:
                    events.append(
                        MessageEvent(
                            account,
                            sender_id,
                            recipient_id,
                            mid,
                            occurred,
                            "receipt",
                            content_hash=fingerprint([variant, mid]),
                        )
                    )
            if len(events) > MAX_EVENTS:
                raise MetaContractError("Lote Instagram muito grande.")
    if not events:
        raise MetaContractError("Evento Instagram vazio.")
    return events


class InstagramIngressService:
    def __init__(self, *, app_secret, verify_token):
        if (
            not isinstance(app_secret, str)
            or len(app_secret) < 32
            or not isinstance(verify_token, str)
            or len(verify_token) < 32
        ):
            raise ValueError("Verificação Instagram indisponível.")
        self._app_secret = app_secret
        self._verify_token = verify_token

    def challenge(self, mode, token, challenge):
        try:
            return verify_webhook_challenge(mode, token, challenge, self._verify_token)
        except MetaContractError:
            pass
        raise HTTPException(403, "Verificação Instagram inválida.")

    def receive(self, raw, signature):
        events = None
        try:
            events = parse_message_events(raw, signature, self._app_secret)
        except (MetaContractError, ValueError, TypeError, RecursionError):
            pass
        if events is None:
            raise HTTPException(403, "Evento Instagram inválido ou não autenticado.")
        accounts = sorted({event.account_id for event in events})
        result = {"received": True, "processed": 0, "ignored": 0, "duplicates": 0}
        failed = False
        try:
            with connect() as conn:
                conn.row_factory = dict_row
                conn.execute("SET LOCAL lock_timeout='3s'")
                conn.execute("SET LOCAL statement_timeout='10s'")
                for account in accounts:
                    conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                        ("instagram-ingress:" + account,),
                    )
                bindings = {}
                for account in accounts:
                    row = conn.execute(
                        "SELECT id,workspace_id,external_account_id FROM socialmei.ig_meta_connections WHERE external_account_id=%s AND status='connected' AND expires_at>NOW() AND scopes @> ARRAY['instagram_business_basic','instagram_business_manage_messages']::text[]",
                        (account,),
                    ).fetchone()
                    if not row:
                        raise HTTPException(
                            404, "Conta Instagram não disponível para recebimento."
                        )
                    bindings[account] = row
                for workspace in sorted({r["workspace_id"] for r in bindings.values()}):
                    lock_oauth_workspace(conn, workspace)
                for account, row in bindings.items():
                    current = conn.execute(
                        "SELECT id FROM socialmei.ig_meta_connections WHERE id=%s AND workspace_id=%s AND external_account_id=%s AND status='connected' AND expires_at>NOW() AND scopes @> ARRAY['instagram_business_basic','instagram_business_manage_messages']::text[] FOR SHARE",
                        (row["id"], row["workspace_id"], account),
                    ).fetchone()
                    if not current:
                        raise HTTPException(
                            404, "Conta Instagram não disponível para recebimento."
                        )
                for event in events:
                    binding = bindings[event.account_id]
                    prior = conn.execute(
                        "SELECT fingerprint FROM socialmei.ig_meta_ingress_events WHERE external_account_id=%s AND event_key=%s",
                        (event.account_id, event.event_key),
                    ).fetchone()
                    if prior:
                        if prior["fingerprint"] != event.canonical_fingerprint:
                            raise HTTPException(
                                409,
                                "Identidade de evento já recebida com outro conteúdo.",
                            )
                        result["duplicates"] += 1
                        continue
                    message_id = None
                    if event.kind == "message":
                        persisted = _append_inbox_message(
                            conn,
                            binding["workspace_id"],
                            event,
                            event.canonical_fingerprint,
                            origin="instagram",
                        )
                        message_id = persisted["message_id"]
                    conn.execute(
                        "INSERT INTO socialmei.ig_meta_ingress_events(external_account_id,event_key,workspace_id,connection_id,kind,fingerprint,status,message_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            event.account_id,
                            event.event_key,
                            binding["workspace_id"],
                            binding["id"],
                            event.kind,
                            event.canonical_fingerprint,
                            "processed" if message_id else "ignored",
                            message_id,
                        ),
                    )
                    result["processed" if message_id else "ignored"] += 1
        except HTTPException:
            raise
        except (psycopg.Error, RuntimeError):
            failed = True
        if failed:
            raise HTTPException(
                503,
                "Recepção temporariamente indisponível; nenhum lote foi confirmado.",
            )
        return result


@router.get(PUBLIC_PATH)
@router.get(PATH)
@router.get(PATH + "/", include_in_schema=False)
def challenge(
    request: Request, service: InstagramIngressService = Depends(ingress_service)
):
    _enabled()
    query = request.scope.get("state", {}).get("instagram_webhook_query")
    keys = {"hub.mode", "hub.verify_token", "hub.challenge"}
    if (
        query is None
        or set(query) != keys
        or any(len(query.getlist(key)) != 1 for key in keys)
    ):
        raise HTTPException(403, "Verificação Instagram inválida.")
    value = service.challenge(
        query["hub.mode"], query["hub.verify_token"], query["hub.challenge"]
    )
    return PlainTextResponse(
        value,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post(PUBLIC_PATH)
@router.post(PATH)
@router.post(PATH + "/", include_in_schema=False)
async def webhook(
    request: Request, service: InstagramIngressService = Depends(ingress_service)
):
    _enabled()
    query = request.scope.get("state", {}).get("instagram_webhook_query")
    if query is None or query:
        raise HTTPException(422, "Evento Instagram não aceita parâmetros de URL.")
    if len(request.headers.getlist("x-hub-signature-256")) != 1:
        raise HTTPException(403, "Assinatura Instagram ausente ou ambígua.")
    if (
        len(request.headers.getlist("content-type")) != 1
        or request.headers.get("content-type", "").split(";", 1)[0].lower()
        != "application/json"
    ):
        raise HTTPException(415, "Utilize JSON.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_WEBHOOK_BYTES:
            raise HTTPException(413, "Evento Instagram muito grande.")
        raw.extend(chunk)
    return await run_in_threadpool(
        service.receive, bytes(raw), request.headers.get("x-hub-signature-256", "")
    )
