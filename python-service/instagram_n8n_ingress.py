"""Authenticated n8n ingress: durable Inbox persistence before optional AI/sends."""
import hashlib
import hmac
import json
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

import settings
from instagram_meta_contract import MAX_WEBHOOK_BYTES, MetaContractError
from instagram_meta_ingress import (
    BoundMessageEvent,
    MessageEvent,
    bound_event,
    parse_message_events,
    persist_authenticated_events,
)

PATH = "/webhooks/instagram/n8n"
router = APIRouter(tags=["authenticated Instagram n8n ingress"])


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate binding")
        result[key] = value
    return result


class InstagramN8NIngressService:
    def __init__(self, *, key, meta_app_secret, bindings, clock=time.time, auth_mode="hmac"):
        if (not isinstance(key, str) or not 32 <= len(key) <= 256
                or not re.fullmatch(r"[!-~]+", key)
                or not isinstance(meta_app_secret, str) or not 32 <= len(meta_app_secret) <= 256
                or not re.fullmatch(r"[!-~]+", meta_app_secret)
                or key == meta_app_secret
                or not isinstance(bindings, dict) or not 1 <= len(bindings) <= 100
                or not isinstance(auth_mode, str) or auth_mode not in {"hmac", "header"}):
            raise ValueError("Configuração de ingresso n8n indisponível.")
        normalized = {}
        targets = set()
        for source, binding in bindings.items():
            if type(binding) is int:
                workspace, account = binding, source
            elif isinstance(binding, dict) and set(binding) == {"workspace_id", "connection_account_id"}:
                workspace, account = binding["workspace_id"], binding["connection_account_id"]
            else:
                raise ValueError("Vínculo de ingresso n8n inválido.")
            if (not isinstance(source, str) or not re.fullmatch(r"[0-9]{1,40}", source)
                    or not isinstance(account, str) or not re.fullmatch(r"[0-9]{1,40}", account)
                    or type(workspace) is not int or not 1 <= workspace <= 9223372036854775807
                    or account in targets):
                raise ValueError("Vínculo de ingresso n8n inválido.")
            targets.add(account)
            normalized[source] = (workspace, account)
        self._key = key.encode("ascii")
        self._meta_app_secret = meta_app_secret
        self._bindings = normalized
        self._clock = clock
        self.auth_mode = auth_mode

    def has_workspace(self, workspace_id):
        """Only report configured ingress for the authenticated workspace."""
        return type(workspace_id) is int and any(
            workspace == workspace_id for workspace, _ in self._bindings.values()
        )

    def receive(self, raw, timestamp, signature, meta_signature, relay_key=None):
        # Relay authentication is not source authentication: both must succeed.
        if (not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_WEBHOOK_BYTES
                or not isinstance(timestamp, str) or not re.fullmatch(r"[1-9][0-9]{9}", timestamp)):
            raise HTTPException(403, "Ingresso n8n não autenticado.")
        if abs(self._clock() - int(timestamp)) > 300:
            raise HTTPException(403, "Ingresso n8n não autenticado.")
        if self.auth_mode == "hmac":
            if not isinstance(signature, str) or not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
                raise HTTPException(403, "Ingresso n8n não autenticado.")
            expected = "sha256=" + hmac.new(
                self._key, timestamp.encode("ascii") + b"\n" + raw, hashlib.sha256,
            ).hexdigest()
            authenticated = hmac.compare_digest(expected, signature)
        else:
            # Native n8n Bearer Auth keeps the relay key encrypted in its credential store.
            # TLS protects the credential/timestamp; the Meta HMAC still authenticates the body.
            authenticated = (isinstance(relay_key, str) and 32 <= len(relay_key) <= 256
                             and bool(re.fullmatch(r"[!-~]+", relay_key))
                             and hmac.compare_digest(self._key, relay_key.encode("ascii")))
        if not authenticated:
            raise HTTPException(403, "Ingresso n8n não autenticado.")
        try:
            events = parse_message_events(raw, meta_signature, self._meta_app_secret)
        except (MetaContractError, ValueError, TypeError, RecursionError):
            raise HTTPException(403, "Evento Instagram inválido ou não autenticado.") from None
        if any(event.account_id not in self._bindings for event in events):
            raise HTTPException(403, "Conta Instagram não autorizada para esta integração.")
        canonical_bindings = {account: workspace for workspace, account in self._bindings.values()}
        events = [bound_event(event, self._bindings[event.account_id][1]) for event in events]
        result = persist_authenticated_events(events, canonical_bindings)
        # Retries/mixed batches must not trigger duplicate or speculative replies.
        result["continue_automation"] = (
            result["processed"] > 0 and result["duplicates"] == 0 and result["ignored"] == 0
        )
        return result


def ingress_service():
    if not settings.instagram_n8n_ingress_enabled():
        raise HTTPException(503, "Ingresso n8n ainda não habilitado.")
    try:
        config = settings.instagram_n8n_ingress_configuration()
        bindings = json.loads(config["bindings"], object_pairs_hook=_unique)
        return InstagramN8NIngressService(key=config["key"], meta_app_secret=config["meta_app_secret"],
                                         bindings=bindings, auth_mode=config["auth_mode"])
    except (ValueError, TypeError, KeyError, RecursionError):
        raise HTTPException(503, "Configuração de ingresso n8n indisponível.") from None


@router.post(PATH)
async def webhook(request: Request, service=Depends(ingress_service)):
    query = request.scope.get("state", {}).get("instagram_webhook_query")
    if query is None or query or request.headers.getlist("origin"):
        raise HTTPException(403, "Solicitação de ingresso n8n inválida.")
    if (len(request.headers.getlist("content-type")) != 1
            or request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json"):
        raise HTTPException(415, "Utilize JSON.")
    relay_header = "authorization" if service.auth_mode == "header" else "x-socialmei-signature"
    other_header = "x-socialmei-signature" if service.auth_mode == "header" else "authorization"
    names = ("x-socialmei-timestamp", relay_header, "x-hub-signature-256")
    if any(len(request.headers.getlist(name)) != 1 for name in names):
        raise HTTPException(403, "Ingresso n8n não autenticado.")
    if request.headers.getlist(other_header):
        raise HTTPException(403, "Ingresso n8n não autenticado.")
    relay_key = None
    if service.auth_mode == "header":
        authorization = request.headers[relay_header]
        if not authorization.startswith("Bearer "):
            raise HTTPException(403, "Ingresso n8n não autenticado.")
        relay_key = authorization[len("Bearer "):]
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_WEBHOOK_BYTES:
            raise HTTPException(413, "Evento Instagram muito grande.")
        raw.extend(chunk)
    return await run_in_threadpool(
        service.receive, bytes(raw), request.headers[names[0]],
        request.headers[relay_header] if service.auth_mode == "hmac" else None,
        request.headers[names[2]],
        relay_key,
    )
