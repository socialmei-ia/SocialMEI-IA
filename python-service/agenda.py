"""Manual workspace reminders. No automatic sending or external scheduling."""

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator

import settings
from account_auth import current, require_enabled
from database import connect
from shared_data import MAX_SAFE_ID


def boundary(response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        yield
    except (psycopg.Error, RuntimeError):
        raise HTTPException(
            503, "Agenda temporariamente indisponível. Recarregue antes de tentar novamente."
        ) from None


router = APIRouter(
    prefix="/api/v1/agenda", tags=["agenda"], dependencies=[Depends(boundary)]
)
WRITERS = {"owner", "admin", "member"}
READERS = WRITERS | {"viewer"}
COLUMNS = "id, title, scheduled_for, notes, cliente_id, status, revision, created_at, updated_at"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReminderCreate(Strict):
    operation_id: UUID
    title: str = Field(min_length=1, max_length=160)
    scheduled_for: datetime
    notes: str = Field(default="", max_length=1000)
    cliente_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_ID, strict=True)

    @field_validator("scheduled_for", mode="before")
    @classmethod
    def explicit_datetime(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Informe data e horário com fuso horário.")
        return value

    @field_validator("scheduled_for")
    @classmethod
    def aware_datetime(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Informe o fuso horário do lembrete.")
        try:
            value.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise ValueError("Data do lembrete inválida.") from None
        return value

    @field_validator("title", "notes")
    @classmethod
    def valid_text(cls, value, info):
        allowed = "\n\r\t" if info.field_name == "notes" else ""
        if any(ord(char) < 32 and char not in allowed for char in value):
            raise ValueError("Texto inválido.")
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise ValueError("Texto inválido.") from None
        return value


class ReminderUpdate(Strict):
    expected_revision: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    status: Literal["pending", "done", "cancelled"]


def identity(write=False):
    require_enabled()
    user = current()
    if user["role"] not in (WRITERS if write else READERS):
        raise HTTPException(403, "Este acesso não permite alterar a agenda." if write else "Acesso à agenda indisponível.")
    return user


def business_zone():
    try:
        return settings.business_timezone()
    except ValueError:
        raise HTTPException(503, "Confira o fuso horário configurado para o negócio.") from None


def configure(conn):
    conn.row_factory = dict_row
    conn.execute("SET LOCAL lock_timeout='3s'")
    conn.execute("SET LOCAL statement_timeout='5s'")


def public_view(row):
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "scheduled_for": row["scheduled_for"].isoformat(),
        "notes": row["notes"],
        "cliente_id": row["cliente_id"],
        "client_name": row.get("client_name"),
        "status": row["status"],
        "revision": row["revision"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@router.get("")
def list_reminders(
    from_date: date | None = Query(None), to_date: date | None = Query(None)
):
    user = identity()
    zone = business_zone()
    today = datetime.now(zone).date()
    start = from_date or today - timedelta(days=7)
    end = to_date or today + timedelta(days=90)
    if start > end or (end - start).days > 365:
        raise HTTPException(422, "Selecione um período de até 366 dias.")
    try:
        since = datetime.combine(start, time.min, tzinfo=zone)
        until = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone)
    except (ValueError, OverflowError):
        raise HTTPException(422, "Período inválido.") from None
    with connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        configure(conn)
        fields = ", ".join("r." + name for name in COLUMNS.split(", "))
        rows = conn.execute(
            f"SELECT {fields},c.nome AS client_name FROM socialmei.agenda_reminders r "
            "LEFT JOIN socialmei.crm_clientes c ON c.workspace_id=r.workspace_id AND c.id=r.cliente_id "
            "WHERE r.workspace_id=%s AND r.status!='cancelled' "
            "AND r.scheduled_for>=%s AND r.scheduled_for<%s "
            "ORDER BY r.scheduled_for,r.id LIMIT 501",
            (user["workspace_id"], since, until),
        ).fetchall()
    return {
        "items": [public_view(row) for row in rows[:500]],
        "from_date": start.isoformat(), "to_date": end.isoformat(),
        "truncated": len(rows) > 500,
    }


@router.post("", status_code=201)
def create_reminder(payload: ReminderCreate):
    user = identity(write=True)
    value = payload.model_dump(mode="json", exclude={"operation_id"})
    value["scheduled_for"] = payload.scheduled_for.astimezone(timezone.utc).isoformat()
    fingerprint = hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    with connect() as conn:
        configure(conn)
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"agenda:{user['workspace_id']}:{payload.operation_id}",),
        )
        previous = conn.execute(
            f"SELECT {COLUMNS},creation_fingerprint FROM socialmei.agenda_reminders "
            "WHERE workspace_id=%s AND id=%s",
            (user["workspace_id"], payload.operation_id),
        ).fetchone()
        if previous:
            if previous["creation_fingerprint"] != fingerprint:
                raise HTTPException(409, "Identificador já usado para outro lembrete.")
            return public_view(previous)
        if payload.cliente_id is not None and not conn.execute(
            "SELECT 1 FROM socialmei.crm_clientes WHERE workspace_id=%s AND id=%s FOR SHARE",
            (user["workspace_id"], payload.cliente_id),
        ).fetchone():
            raise HTTPException(422, "Cliente não encontrado neste negócio.")
        row = conn.execute(
            f"INSERT INTO socialmei.agenda_reminders "
            "(workspace_id,id,title,scheduled_for,notes,cliente_id,creation_fingerprint) "
            f"VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING {COLUMNS}",
            (user["workspace_id"], payload.operation_id, payload.title,
             payload.scheduled_for, payload.notes, payload.cliente_id, fingerprint),
        ).fetchone()
    return public_view(row)


@router.patch("/{reminder_id}")
def update_reminder(reminder_id: UUID, payload: ReminderUpdate):
    user = identity(write=True)
    with connect() as conn:
        configure(conn)
        row = conn.execute(
            f"SELECT {COLUMNS} FROM socialmei.agenda_reminders "
            "WHERE workspace_id=%s AND id=%s FOR UPDATE",
            (user["workspace_id"], reminder_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Lembrete não encontrado.")
        if row["revision"] != payload.expected_revision:
            raise HTTPException(409, "O lembrete mudou. Recarregue antes de salvar.")
        if row["revision"] >= MAX_SAFE_ID:
            raise HTTPException(409, "Este lembrete atingiu o limite de revisões.")
        saved = conn.execute(
            "UPDATE socialmei.agenda_reminders SET status=%s,revision=revision+1,updated_at=NOW() "
            f"WHERE workspace_id=%s AND id=%s RETURNING {COLUMNS}",
            (payload.status, user["workspace_id"], reminder_id),
        ).fetchone()
    return public_view(saved)
