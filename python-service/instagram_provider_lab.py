"""Authenticated isolated fake-provider lab. Never opens a network connection.

Not a Meta callback/webhook. All mutations retain session, Origin and CSRF.
No access/refresh token is accepted, produced, persisted or returned.
"""
import hashlib
import hmac
import json
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool

import settings
import message_enrichment as enrichment
from account_auth import COOKIE, current, digest, require_enabled
from database import connect
from instagram_simulation import Strict, PublicationInput
from pydantic import Field

router = APIRouter(prefix="/api/v1/instagram/provider-lab", tags=["isolated fake provider"])
MAX_BODY = 16384


def guard(*, manage=False):
    require_enabled()
    if not settings.instagram_provider_lab_enabled():
        raise HTTPException(503, "Laboratório isolado não habilitado.")
    user = current()
    if manage and user["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente responsáveis podem gerenciar o laboratório.")
    return user


@contextmanager
def db():
    with connect() as conn:
        conn.row_factory = dict_row
        yield conn


def connection(conn, workspace, *, lock=False):
    if lock:
        enrichment.lock_workspace(conn, workspace)
    row = conn.execute(
        "SELECT * FROM socialmei.ig_lab_connections WHERE workspace_id=%s" +
        (" FOR UPDATE" if lock else ""), (workspace,),
    ).fetchone()
    if not row or row["status"] != "connected" or row["expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(409, "Conexão fictícia indisponível ou expirada.")
    return row


def safe_job(row):
    return {"id": str(row["id"]), "account_id": str(row["account_id"]),
            "status": row["status"], "attempts": row["attempts"],
            "approved": row["approved_by"] is not None,
            "provider_result": row["provider_result"],
            "published": False, "transport": "none", "provider": "fake"}


@router.get("/status")
def status():
    user = guard()
    with db() as conn:
        row = conn.execute("SELECT * FROM socialmei.ig_lab_connections WHERE workspace_id=%s", (user["workspace_id"],)).fetchone()
    state = row["status"] if row else "disconnected"
    if state == "connected" and row["expires_at"] <= datetime.now(timezone.utc):
        state = "expired"
    return {"status": state, "account_id": str(row["account_id"]) if row else None,
            "provider": "fake", "transport": "none", "published": False}


@router.post("/oauth/start")
def oauth_start(request: Request):
    user = guard(manage=True)
    state = secrets.token_urlsafe(32)
    with db() as conn:
        enrichment.lock_workspace(conn, user["workspace_id"])
        enrichment.rate_limit(conn, user["workspace_id"])
        conn.execute("INSERT INTO socialmei.ig_lab_states(state_hash,workspace_id,user_id,session_hash,expires_at) VALUES(%s,%s,%s,%s,%s)",
                     (digest(state), user["workspace_id"], user["id"], digest(request.cookies[COOKIE]), datetime.now(timezone.utc) + timedelta(minutes=5)))
    return {"state": state, "fake_code": "fake-authorization-code", "expires_in": 300, "provider": "fake", "redirect": None}


class Callback(Strict):
    state: str = Field(min_length=40, max_length=100)
    code: Literal["fake-authorization-code"]


@router.post("/oauth/callback")
def oauth_callback(payload: Callback, request: Request):
    user = guard(manage=True)
    with db() as conn:
        enrichment.lock_workspace(conn, user["workspace_id"])
        row = conn.execute("UPDATE socialmei.ig_lab_states SET consumed_at=NOW() WHERE state_hash=%s AND workspace_id=%s AND user_id=%s AND session_hash=%s AND consumed_at IS NULL AND expires_at>NOW() RETURNING state_hash",
                           (digest(payload.state), user["workspace_id"], user["id"], digest(request.cookies[COOKIE]))).fetchone()
        if not row:
            raise HTTPException(409, "Autorização fictícia inválida, expirada ou utilizada.")
        # Serialize connection creation/reconnection within the tenant.
        enrichment.lock_workspace(conn, user["workspace_id"])
        old = conn.execute("SELECT account_id FROM socialmei.ig_lab_connections WHERE workspace_id=%s", (user["workspace_id"],)).fetchone()
        account = old["account_id"] if old else uuid4()
        conn.execute("INSERT INTO socialmei.instagram_sim_accounts(workspace_id,id,label,created_by) VALUES(%s,%s,'Conta do provedor fictício',%s) ON CONFLICT DO NOTHING", (user["workspace_id"], account, user["id"]))
        conn.execute("INSERT INTO socialmei.ig_lab_connections(workspace_id,account_id,status,expires_at) VALUES(%s,%s,'connected',NOW()+INTERVAL '1 hour') ON CONFLICT(workspace_id) DO UPDATE SET status='connected',expires_at=EXCLUDED.expires_at", (user["workspace_id"], account))
    return {"status": "connected", "account_id": str(account), "provider": "fake", "transport": "none"}


def end_connection(new_status):
    user = guard(manage=True)
    with db() as conn:
        enrichment.lock_workspace(conn, user["workspace_id"])
        conn.execute("UPDATE socialmei.ig_lab_connections SET status=%s WHERE workspace_id=%s", (new_status, user["workspace_id"]))
        conn.execute("UPDATE socialmei.ig_lab_publications SET status='failed',approved_by=NULL,provider_result=%s WHERE workspace_id=%s AND status IN ('pending','processing')", (Jsonb({"fictional": True, "reason": "connection-revoked"}), user["workspace_id"]))
        conn.execute("UPDATE socialmei.ig_lab_states SET consumed_at=NOW() WHERE workspace_id=%s AND consumed_at IS NULL", (user["workspace_id"],))
    return {"status": new_status, "published": False}


@router.delete("/connection")
def revoke():
    return end_connection("revoked")


@router.post("/connection/disconnect")
def disconnect():
    return end_connection("disconnected")


class Event(Strict):
    event_id: UUID
    account_id: UUID
    contact_id: str = Field(pattern=r"^synthetic:[A-Za-z0-9_.:-]{1,80}$")
    contact_name: enrichment.Label
    message_id: enrichment.Label
    text: enrichment.Text
    occurred_at: datetime


def ingest(raw, signature, workspace):
    key = settings.instagram_provider_lab_signing_key()
    if len(key) < 32 or settings.message_enrichment_mode() != "stub":
        raise HTTPException(503, "Adaptador de testes não configurado.")
    expected = "sha256=" + hmac.new(key.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        raise HTTPException(403, "Assinatura inválida.")
    try:
        data = json.loads(raw, object_pairs_hook=enrichment.unique_json_fields)
        event = Event.model_validate(data)
        incoming = enrichment.Incoming(schema_version=1, operation_id=str(event.event_id), channel="instagram",
            account_ref="synthetic:ig-lab-" + str(event.account_id), contact_ref=event.contact_id,
            contact_name=event.contact_name, external_message_id=event.message_id,
            text=event.text, occurred_at=event.occurred_at)
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(422, "Evento fictício inválido.") from None
    fingerprint = enrichment.fingerprint(event.model_dump(mode="json"))
    with db() as conn:
        linked = connection(conn, workspace, lock=True)
        if str(linked["account_id"]) != str(event.account_id):
            raise HTTPException(404, "Conta fictícia não encontrada neste negócio.")
        prior = conn.execute("SELECT * FROM socialmei.ig_lab_events WHERE workspace_id=%s AND event_id=%s", (linked["workspace_id"], event.event_id)).fetchone()
        if prior:
            if prior["fingerprint"] != fingerprint:
                raise HTTPException(409, "Evento já recebido com outro conteúdo.")
            return {**prior["result"], "replayed": True, "transport": "none"}
        result = enrichment.persist_incoming(conn, linked["workspace_id"], incoming)
        conn.execute("INSERT INTO socialmei.ig_lab_events(workspace_id,event_id,fingerprint,result) VALUES(%s,%s,%s,%s)", (linked["workspace_id"], event.event_id, fingerprint, Jsonb(result)))
        return {**result, "transport": "none"}


@router.post("/webhook")
async def webhook(request: Request):
    user = guard(manage=True)
    if request.query_params or request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(415, "Utilize JSON sem parâmetros de URL.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BODY:
            raise HTTPException(413, "Evento muito grande.")
    return await run_in_threadpool(ingest, bytes(raw), request.headers.get("x-hub-signature-256", ""), user["workspace_id"])


@router.post("/publications", status_code=201)
def enqueue(payload: PublicationInput, response: Response):
    user = guard(manage=True)
    data = payload.model_dump(mode="json")
    fingerprint = enrichment.fingerprint(data)
    with db() as conn:
        linked = connection(conn, user["workspace_id"], lock=True)
        if str(linked["account_id"]) != str(payload.account_id):
            raise HTTPException(404, "Conta fictícia não encontrada neste negócio.")
        inserted = conn.execute("INSERT INTO socialmei.ig_lab_publications(workspace_id,id,account_id,idempotency_key,fingerprint,payload) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,account_id,idempotency_key) DO NOTHING RETURNING id", (user["workspace_id"], uuid4(), payload.account_id, payload.idempotency_key, fingerprint, Jsonb(data))).fetchone()
        row = conn.execute("SELECT * FROM socialmei.ig_lab_publications WHERE workspace_id=%s AND account_id=%s AND idempotency_key=%s", (user["workspace_id"], payload.account_id, payload.idempotency_key)).fetchone()
        if row["fingerprint"] != fingerprint:
            raise HTTPException(409, "Chave já utilizada com outro conteúdo.")
        if not inserted:
            response.status_code = 200
        return safe_job(row)


@router.get("/publications")
def jobs():
    user = guard()
    with db() as conn:
        rows = conn.execute("SELECT * FROM socialmei.ig_lab_publications WHERE workspace_id=%s ORDER BY created_at DESC,id DESC LIMIT 100", (user["workspace_id"],)).fetchall()
    return {"items": [safe_job(row) for row in rows]}


@router.post("/publications/{job_id}/approve")
def approve(job_id: UUID):
    user = guard(manage=True)
    with db() as conn:
        connection(conn, user["workspace_id"], lock=True)
        row = conn.execute("UPDATE socialmei.ig_lab_publications SET approved_by=%s WHERE workspace_id=%s AND id=%s AND status='pending' RETURNING *", (user["id"], user["workspace_id"], job_id)).fetchone()
        if not row:
            raise HTTPException(409, "Publicação fictícia indisponível para aprovação.")
        return safe_job(row)


class Run(Strict):
    outcome: Literal["success", "failure"] = "success"


@router.post("/publications/{job_id}/run")
def run(job_id: UUID, payload: Run):
    user = guard(manage=True)
    with db() as conn:
        connection(conn, user["workspace_id"], lock=True)
        row = conn.execute("UPDATE socialmei.ig_lab_publications SET status='processing',attempts=attempts+1 WHERE workspace_id=%s AND id=%s AND status IN ('pending','failed') AND approved_by IS NOT NULL AND attempts<3 AND (payload->>'scheduled_for' IS NULL OR (payload->>'scheduled_for')::timestamptz<=NOW()) RETURNING *", (user["workspace_id"], job_id)).fetchone()
        if not row:
            raise HTTPException(409, "Job não aprovado, já processado, futuro ou sem tentativas.")
        # Both state changes are atomic: a crash rolls back the claim for safe retry.
        final = "simulated-published" if payload.outcome == "success" else "failed"
        result = {"fictional": True, "provider": "fake", "outcome": payload.outcome, "published": False}
        row = conn.execute("UPDATE socialmei.ig_lab_publications SET status=%s,provider_result=%s WHERE workspace_id=%s AND id=%s AND status='processing' RETURNING *", (final, Jsonb(result), user["workspace_id"], job_id)).fetchone()
        return safe_job(row)
