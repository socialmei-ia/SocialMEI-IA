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
    def __init__(self, *, key, meta_app_secret, bindings, clock=time.time):
        if (not isinstance(key, str) or not 32 <= len(key) <= 256
                or not re.fullmatch(r"[!-~]+", key)
                or not isinstance(meta_app_secret, str) or not 32 <= len(meta_app_secret) <= 256
                or not re.fullmatch(r"[!-~]+", meta_app_secret)
                or key == meta_app_secret
                or not isinstance(bindings, dict) or not 1 <= len(bindings) <= 100
                or any(not isinstance(account, str) or not re.fullmatch(r"[0-9]{1,40}", account)
                       or type(workspace) is not int or not 1 <= workspace <= 9223372036854775807
                       for account, workspace in bindings.items())):
            raise ValueError("Configuração de ingresso n8n indisponível.")
        self._key = key.encode("ascii")
        self._meta_app_secret = meta_app_secret
        self._bindings = dict(bindings)
        self._clock = clock

    def receive(self, raw, timestamp, signature, meta_signature):
        # Relay authentication is not source authentication: both must succeed.
        if (not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_WEBHOOK_BYTES
                or not isinstance(timestamp, str) or not re.fullmatch(r"[1-9][0-9]{9}", timestamp)
                or not isinstance(signature, str) or not re.fullmatch(r"sha256=[0-9a-f]{64}", signature)):
            raise HTTPException(403, "Ingresso n8n não autenticado.")
        expected = "sha256=" + hmac.new(
            self._key, timestamp.encode("ascii") + b"\n" + raw, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature) or abs(self._clock() - int(timestamp)) > 300:
            raise HTTPException(403, "Ingresso n8n não autenticado.")
        try:
            events = parse_message_events(raw, meta_signature, self._meta_app_secret)
        except (MetaContractError, ValueError, TypeError, RecursionError):
            raise HTTPException(403, "Evento Instagram inválido ou não autenticado.") from None
        if any(event.account_id not in self._bindings for event in events):
            raise HTTPException(403, "Conta Instagram não autorizada para esta integração.")
        result = persist_authenticated_events(events, self._bindings)
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
        return InstagramN8NIngressService(key=config["key"], meta_app_secret=config["meta_app_secret"], bindings=bindings)
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
    names = ("x-socialmei-timestamp", "x-socialmei-signature", "x-hub-signature-256")
    if any(len(request.headers.getlist(name)) != 1 for name in names):
        raise HTTPException(403, "Ingresso n8n não autenticado.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_WEBHOOK_BYTES:
            raise HTTPException(413, "Evento Instagram muito grande.")
        raw.extend(chunk)
    return await run_in_threadpool(
        service.receive, bytes(raw), request.headers[names[0]], request.headers[names[1]], request.headers[names[2]],
    )
