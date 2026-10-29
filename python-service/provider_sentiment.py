"""Internal, opt-in n8n sentiment classification for already verified provider messages.

The provider webhook (Meta/WAHA), not this service, establishes ownership and
stores inbox messages. This module never contacts providers or sends replies.
"""
import hashlib
import hmac
import json
import uuid
from contextlib import contextmanager

import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

import settings
from database import connect

router = APIRouter(prefix="/internal/message-enrichment/provider", tags=["private provider analysis"])
MAX_BATCH = 10


class ResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    claim_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    sentiment: Literal["positive", "negative", "neutral", "uncertain"]
    confidence: Literal["low", "medium", "high"]
    explanation: str = Field(min_length=1, max_length=500)

    def checked_explanation(self):
        text = self.explanation.strip()
        if not text or any(ord(c) < 32 and c not in "\t\n\r" for c in text):
            raise HTTPException(422, "Resultado inválido.")
        if len(text.encode("utf-8")) > 500:
            raise HTTPException(422, "Resultado inválido.")
        return text


def service_enabled():
    return (
        settings.shared_data_enabled()
        and settings.authentication_mode() == "enabled"
        and settings.provider_sentiment_enabled()
        and len(settings.provider_sentiment_key()) >= 32
        and bool(settings.provider_sentiment_allowed_workspaces())
    )


def authorize(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if not service_enabled():
        raise HTTPException(503, "Análise externa indisponível.")
    if request.query_params:
        raise HTTPException(422, "Consulta inválida.")
    authorization = request.headers.get("authorization", "")
    expected = "Bearer " + settings.provider_sentiment_key()
    if not hmac.compare_digest(authorization.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, "Acesso não autorizado.")


@contextmanager
def database():
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET LOCAL statement_timeout='8s'")
            yield conn
    except (psycopg.Error, RuntimeError):
        raise HTTPException(503, "Serviço de análise indisponível.") from None


def fingerprint(result):
    value = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@router.get("/claims")
def claim_messages(request: Request, response: Response):
    """Lease at most 10 verified provider messages; never include synthetic data."""
    authorize(request, response)
    with database() as conn:
        conn.execute("SET LOCAL lock_timeout='2s'")
        messages = conn.execute(
            """
            SELECT m.workspace_id,m.id,m.origin,m.text
            FROM socialmei.me_messages AS m
            LEFT JOIN socialmei.me_provider_sentiment_jobs AS j
              ON j.workspace_id=m.workspace_id AND j.message_id=m.id
            WHERE m.origin IN ('instagram','waha')
              AND m.workspace_id = ANY(%s)
              AND m.occurred_at >= NOW()-INTERVAL '7 days'
              AND (
                j.message_id IS NULL
                OR (j.status='processing' AND j.lease_until < NOW() AND j.attempt < 3)
              )
            ORDER BY m.id ASC
            LIMIT %s FOR UPDATE OF m SKIP LOCKED
            """,
            (list(settings.provider_sentiment_allowed_workspaces()), MAX_BATCH),
        ).fetchall()
        tasks = []
        for message in messages:
            claim = uuid.uuid4()
            row = conn.execute(
                """
                INSERT INTO socialmei.me_provider_sentiment_jobs
                    (workspace_id,message_id,claim_id,lease_until)
                VALUES (%s,%s,%s,NOW()+INTERVAL '5 minutes')
                ON CONFLICT(workspace_id,message_id) DO UPDATE
                    SET claim_id=EXCLUDED.claim_id,
                        lease_until=EXCLUDED.lease_until,
                        attempt=me_provider_sentiment_jobs.attempt+1,
                        updated_at=NOW()
                WHERE me_provider_sentiment_jobs.status='processing'
                  AND me_provider_sentiment_jobs.lease_until<NOW()
                  AND me_provider_sentiment_jobs.attempt<3
                RETURNING claim_id,attempt
                """,
                (message["workspace_id"], message["id"], claim),
            ).fetchone()
            if row:
                tasks.append({
                    "claim_id": str(row["claim_id"]),
                    "message_id": message["id"],
                    "origin": message["origin"],
                    "text": message["text"],
                    "attempt": row["attempt"],
                })
        return {"items": tasks, "schema_version": 1, "send_enabled": False}


@router.post("/results")
def save_result(payload: ResultInput, request: Request, response: Response):
    """Accept one sentiment receipt for the current claim, never a reply/send."""
    authorize(request, response)
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(422, "Resultado inválido.")
    result = {
        "sentiment": payload.sentiment,
        "confidence": payload.confidence,
        "explanation": payload.checked_explanation(),
    }
    digest = fingerprint(result)
    with database() as conn:
        row = conn.execute(
            """
            SELECT * FROM socialmei.me_provider_sentiment_jobs
            WHERE claim_id=%s FOR UPDATE
            """,
            (payload.claim_id,),
        ).fetchone()
        if not row or row["workspace_id"] not in settings.provider_sentiment_allowed_workspaces():
            # Rotating a lease invalidates stale claims; no other workspace ID
            # or user-supplied account reference is trusted.
            raise HTTPException(404, "Operação não encontrada.")
        if row["status"] == "completed":
            if row["result_fingerprint"] != digest:
                raise HTTPException(409, "Resultado diferente do já registrado.")
            return {"status": "completed", "message_id": row["message_id"], "replayed": True}
        conn.execute(
            """
            UPDATE socialmei.me_provider_sentiment_jobs
            SET status='completed',sentiment=%s,confidence=%s,explanation=%s,
                result_fingerprint=%s,completed_at=NOW(),updated_at=NOW()
            WHERE workspace_id=%s AND message_id=%s AND claim_id=%s AND status='processing'
            """,
            (
                result["sentiment"], result["confidence"], result["explanation"],
                digest, row["workspace_id"], row["message_id"], payload.claim_id,
            ),
        )
        return {"status": "completed", "message_id": row["message_id"], "replayed": False}
