"""Workspace service bookings. No external scheduling, messages or billing."""

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from types import SimpleNamespace
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator, model_validator

from agenda import Strict, ReminderCreate, boundary, business_zone, configure, identity
from database import connect
from shared_data import MAX_SAFE_ID
from channel_booking import (BookingPolicyUpdate, MessageContext, ResourceRequest, SlotRequest,
    ConfirmationRequest, read_policy, save_policy, services_for_message, resources_for_message,
    slots_for_message, confirm_for_message, signing_key_for_context)

router = APIRouter(prefix="/api/v1/agenda", tags=["agenda"], dependencies=[Depends(boundary)])
RESOURCE_COLUMNS = "id,nome,ativo,revision,created_at,updated_at"
APPOINTMENT_COLUMNS = "id,cliente_id,servico_id,resource_id,client_name,service_name,duration_minutes,price,scheduled_for,ends_at,notes,status,revision,created_at,updated_at"


@router.get("/channel-booking")
def channel_booking_settings():
    user = identity()
    with connect() as conn:
        configure(conn)
        return read_policy(conn, user["workspace_id"])


@router.put("/channel-booking")
def update_channel_booking_settings(payload: BookingPolicyUpdate):
    user = identity(write=True)
    if user["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente a administração pode configurar agendamentos pelos canais.")
    with connect() as conn:
        configure(conn)
        result = save_policy(conn, user["workspace_id"], payload)
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,%s)",
                     (user["id"], f"agenda:{user['workspace_id']}:config"))
    return result


def booking_context(user, payload):
    return (user["workspace_id"], payload.conversation_id, payload.source_message_id, payload.origin)


@router.post("/channel-booking/services")
def channel_booking_services(payload: MessageContext):
    return services_for_message(*booking_context(identity(write=True), payload))


@router.post("/channel-booking/resources")
def channel_booking_resources(payload: ResourceRequest):
    return resources_for_message(*booking_context(identity(write=True), payload), payload.service_id)


@router.post("/channel-booking/slots")
def channel_booking_slots(payload: SlotRequest):
    context = booking_context(identity(write=True), payload)
    with connect() as conn:
        configure(conn)
        key = signing_key_for_context(conn, *context)
        return slots_for_message(*context, payload.service_id, payload.resource_id, payload.day,
                                 key, page=payload.page, connection=conn)


@router.post("/channel-booking/confirm")
def channel_booking_confirm(payload: ConfirmationRequest):
    context = booking_context(identity(write=True), payload)
    with connect() as conn:
        configure(conn)
        key = signing_key_for_context(conn, *context)
        return confirm_for_message(*context, payload.confirmation, key, confirmed=payload.confirmed,
                                   connection=conn)


class ResourceCreate(Strict):
    operation_id: UUID
    nome: str = Field(min_length=1, max_length=160)

    @field_validator("nome")
    @classmethod
    def valid_name(cls, value):
        return ReminderCreate.valid_text(value, SimpleNamespace(field_name="title"))


class ResourceUpdate(Strict):
    expected_revision: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    nome: str | None = Field(default=None, min_length=1, max_length=160)
    ativo: bool | None = Field(default=None, strict=True)

    @field_validator("nome")
    @classmethod
    def valid_name(cls, value):
        return ResourceCreate.valid_name(value) if value is not None else value

    @model_validator(mode="after")
    def not_null(self):
        if any(getattr(self, k) is None for k in self.model_fields_set - {"expected_revision"}):
            raise ValueError("Os campos do recurso não podem ser nulos.")
        return self


class AppointmentCreate(Strict):
    operation_id: UUID
    cliente_id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    servico_id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    resource_id: UUID
    scheduled_for: datetime
    notes: str = Field(default="", max_length=1000)

    @field_validator("scheduled_for", mode="before")
    @classmethod
    def explicit_datetime(cls, value):
        return ReminderCreate.explicit_datetime(value)

    @field_validator("scheduled_for")
    @classmethod
    def aware_datetime(cls, value):
        return ReminderCreate.aware_datetime(value)

    @field_validator("notes")
    @classmethod
    def valid_text(cls, value):
        return ReminderCreate.valid_text(value, SimpleNamespace(field_name="notes"))


class AppointmentUpdate(Strict):
    expected_revision: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    scheduled_for: datetime | None = None
    status: Literal["pending", "done", "cancelled"] | None = None

    @field_validator("scheduled_for", mode="before")
    @classmethod
    def explicit_datetime(cls, value):
        return ReminderCreate.explicit_datetime(value)

    @field_validator("scheduled_for")
    @classmethod
    def aware_datetime(cls, value):
        return ReminderCreate.aware_datetime(value)

    @model_validator(mode="after")
    def not_empty(self):
        fields = self.model_fields_set - {"expected_revision"}
        if not fields or any(getattr(self, k) is None for k in fields):
            raise ValueError("Informe data ou estado do agendamento.")
        return self


def fingerprint(payload):
    value = payload.model_dump(mode="json", exclude={"operation_id"})
    if "scheduled_for" in value:
        value["scheduled_for"] = payload.scheduled_for.astimezone(timezone.utc).isoformat()
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def view(row):
    result = dict(row)
    for key in ("creation_fingerprint", "workspace_id"):
        result.pop(key, None)
    for key, value in result.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
    if "price" in result:
        result["price"] = float(result["price"])
        result["title"] = result["service_name"]
    return result


def lock_resource(conn, workspace_id, resource_id, require_active=True):
    row = conn.execute(
        f"SELECT {RESOURCE_COLUMNS} FROM socialmei.agenda_resources WHERE workspace_id=%s AND id=%s FOR UPDATE",
        (workspace_id, resource_id),
    ).fetchone()
    if not row or (require_active and not row["ativo"]):
        raise HTTPException(422, "Selecione um recurso ativo deste negócio.")
    return row


def lock_workspace(conn, workspace_id):
    # Catalog/client writes lock workspace before their rows. Take the FK lock
    # first too, so a concurrent edit cannot form a workspace/product deadlock.
    if not conn.execute(
        "SELECT id FROM socialmei.workspaces WHERE id=%s FOR KEY SHARE",
        (workspace_id,),
    ).fetchone():
        raise HTTPException(403, "Negócio indisponível.")


def service(conn, workspace_id, service_id):
    row = conn.execute(
        "SELECT id,nome,preco,duracao_minutos,versao FROM socialmei.crm_produtos "
        "WHERE workspace_id=%s AND id=%s AND tipo='Serviço' AND status='Ativo' FOR SHARE",
        (workspace_id, service_id),
    ).fetchone()
    if not row or row["duracao_minutos"] is None:
        raise HTTPException(422, "Selecione um serviço ativo deste negócio com duração definida.")
    return row


def end_time(start, minutes):
    try:
        return start + timedelta(minutes=minutes)
    except (OverflowError, ValueError):
        raise HTTPException(422, "Data do agendamento inválida.") from None


def free(conn, workspace_id, resource_id, start, end, ignore=None):
    return not conn.execute(
        "SELECT 1 FROM socialmei.agenda_appointments WHERE workspace_id=%s AND resource_id=%s "
        "AND status!='cancelled' AND scheduled_for<%s AND ends_at>%s AND (%s::uuid IS NULL OR id!=%s::uuid) LIMIT 1",
        (workspace_id, resource_id, end, start, ignore, ignore),
    ).fetchone()


def history(conn, workspace_id, row):
    conn.execute(
        "INSERT INTO socialmei.agenda_appointment_history(workspace_id,appointment_id,revision,scheduled_for,ends_at,status) "
        "VALUES(%s,%s,%s,%s,%s,%s)",
        (workspace_id, row["id"], row["revision"], row["scheduled_for"], row["ends_at"], row["status"]),
    )


@router.get("/resources")
def list_resources():
    user = identity()
    with connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        configure(conn)
        rows = conn.execute(f"SELECT {RESOURCE_COLUMNS} FROM socialmei.agenda_resources WHERE workspace_id=%s ORDER BY nome,id LIMIT 501", (user["workspace_id"],)).fetchall()
    return {"items": [view(row) for row in rows[:500]], "truncated": len(rows)>500}


@router.post("/resources", status_code=201)
def create_resource(payload: ResourceCreate):
    user = identity(write=True)
    value = fingerprint(payload)
    with connect() as conn:
        configure(conn)
        lock_workspace(conn, user["workspace_id"])
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"agenda-resource:{user['workspace_id']}:{payload.operation_id}",))
        previous = conn.execute(f"SELECT {RESOURCE_COLUMNS},creation_fingerprint FROM socialmei.agenda_resources WHERE workspace_id=%s AND id=%s", (user["workspace_id"], payload.operation_id)).fetchone()
        if previous:
            if previous["creation_fingerprint"] != value:
                raise HTTPException(409, "Identificador já usado para outro recurso.")
            return view(previous)
        row = conn.execute(f"INSERT INTO socialmei.agenda_resources(workspace_id,id,nome,creation_fingerprint) VALUES(%s,%s,%s,%s) RETURNING {RESOURCE_COLUMNS}", (user["workspace_id"], payload.operation_id, payload.nome, value)).fetchone()
    return view(row)


@router.patch("/resources/{resource_id}")
def update_resource(resource_id: UUID, payload: ResourceUpdate):
    user = identity(write=True)
    with connect() as conn:
        configure(conn)
        lock_workspace(conn, user["workspace_id"])
        row = lock_resource(conn, user["workspace_id"], resource_id, False)
        if row["revision"] != payload.expected_revision or row["revision"] >= MAX_SAFE_ID:
            raise HTTPException(409, "O recurso mudou. Recarregue antes de salvar.")
        row = conn.execute(f"UPDATE socialmei.agenda_resources SET nome=%s,ativo=%s,revision=revision+1,updated_at=NOW() WHERE workspace_id=%s AND id=%s RETURNING {RESOURCE_COLUMNS}", (payload.nome if payload.nome is not None else row["nome"], payload.ativo if payload.ativo is not None else row["ativo"], user["workspace_id"], resource_id)).fetchone()
    return view(row)


@router.get("/availability")
def availability(resource_id: UUID, servico_id: int = Query(ge=1, le=MAX_SAFE_ID), scheduled_for: str = Query()):
    user = identity()
    try:
        start = ReminderCreate.aware_datetime(ReminderCreate.explicit_datetime(datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))))
    except (ValueError, OverflowError):
        raise HTTPException(422, "Informe data e horário com fuso horário.") from None
    with connect() as conn:
        configure(conn)
        lock_resource(conn, user["workspace_id"], resource_id)
        item = service(conn, user["workspace_id"], servico_id)
        end = end_time(start, item["duracao_minutos"])
        available = free(conn, user["workspace_id"], resource_id, start, end)
    return {"available": available, "scheduled_for": start.isoformat(), "ends_at": end.isoformat(), "reservation_created": False}


@router.post("/appointments", status_code=201)
def create_appointment(payload: AppointmentCreate):
    user = identity(write=True)
    with connect() as conn:
        configure(conn)
        return create_appointment_in(conn, user["workspace_id"], payload)


def existing_appointment_in(conn, workspace_id, payload):
    """Serialize retries and return only an exact operation already persisted."""
    value = fingerprint(payload)
    lock_workspace(conn, workspace_id)
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"appointment:{workspace_id}:{payload.operation_id}",))
    previous = conn.execute(f"SELECT {APPOINTMENT_COLUMNS},creation_fingerprint FROM socialmei.agenda_appointments WHERE workspace_id=%s AND id=%s", (workspace_id, payload.operation_id)).fetchone()
    if previous:
        if previous["creation_fingerprint"] != value:
            raise HTTPException(409, "Identificador já usado para outro agendamento.")
        resource = conn.execute("SELECT nome FROM socialmei.agenda_resources WHERE workspace_id=%s AND id=%s", (workspace_id, previous["resource_id"])).fetchone()
        return view({**previous, "resource_name": resource["nome"]})
    return None


def create_appointment_in(conn, workspace_id, payload):
    """Shared transaction for the authenticated site and authorized channel adapters."""
    previous = existing_appointment_in(conn, workspace_id, payload)
    if previous is not None:
        return previous
    value = fingerprint(payload)
    resource = lock_resource(conn, workspace_id, payload.resource_id)
    item = service(conn, workspace_id, payload.servico_id)
    client = conn.execute("SELECT nome FROM socialmei.crm_clientes WHERE workspace_id=%s AND id=%s FOR SHARE", (workspace_id, payload.cliente_id)).fetchone()
    if not client:
        raise HTTPException(422, "Selecione um cliente deste negócio.")
    end = end_time(payload.scheduled_for, item["duracao_minutos"])
    if not free(conn, workspace_id, payload.resource_id, payload.scheduled_for, end):
        raise HTTPException(409, "Horário ocupado para este recurso. Escolha outro horário.")
    row = conn.execute(
        "INSERT INTO socialmei.agenda_appointments(workspace_id,id,cliente_id,servico_id,resource_id,client_name,service_name,duration_minutes,price,scheduled_for,ends_at,notes,creation_fingerprint) "
        f"VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {APPOINTMENT_COLUMNS}",
        (workspace_id, payload.operation_id, payload.cliente_id, payload.servico_id, payload.resource_id, client["nome"], item["nome"], item["duracao_minutos"], item["preco"], payload.scheduled_for, end, payload.notes, value),
    ).fetchone()
    history(conn, workspace_id, row)
    return view({**row, "resource_name": resource["nome"]})


@router.get("/appointments")
def list_appointments(from_date: date | None = Query(None), to_date: date | None = Query(None), include_cancelled: bool = False):
    user = identity()
    zone = business_zone()
    today = datetime.now(zone).date()
    start, end = from_date or today-timedelta(days=7), to_date or today+timedelta(days=90)
    if start>end or (end-start).days>365:
        raise HTTPException(422, "Selecione um período de até 366 dias.")
    try:
        since, until = datetime.combine(start,time.min,tzinfo=zone), datetime.combine(end+timedelta(days=1),time.min,tzinfo=zone)
    except (ValueError, OverflowError):
        raise HTTPException(422, "Período inválido.") from None
    with connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        configure(conn)
        cols = ",".join("a."+c for c in APPOINTMENT_COLUMNS.split(","))
        rows = conn.execute(f"SELECT {cols},r.nome AS resource_name FROM socialmei.agenda_appointments a JOIN socialmei.agenda_resources r ON r.workspace_id=a.workspace_id AND r.id=a.resource_id WHERE a.workspace_id=%s AND a.scheduled_for>=%s AND a.scheduled_for<%s AND (%s OR a.status!='cancelled') ORDER BY a.scheduled_for,a.id LIMIT 501", (user["workspace_id"], since, until, include_cancelled)).fetchall()
    return {"items": [view(r) for r in rows[:500]], "from_date": start.isoformat(), "to_date": end.isoformat(), "truncated": len(rows)>500}


@router.get("/appointments/{appointment_id}/history")
def appointment_history(appointment_id: UUID):
    user = identity()
    with connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        configure(conn)
        rows = conn.execute("SELECT revision,scheduled_for,ends_at,status,recorded_at FROM socialmei.agenda_appointment_history WHERE workspace_id=%s AND appointment_id=%s ORDER BY revision", (user["workspace_id"], appointment_id)).fetchall()
    if not rows:
        raise HTTPException(404, "Agendamento não encontrado.")
    return {"items": [view(row) for row in rows]}


@router.patch("/appointments/{appointment_id}")
def update_appointment(appointment_id: UUID, payload: AppointmentUpdate):
    user = identity(write=True)
    with connect() as conn:
        configure(conn)
        lock_workspace(conn, user["workspace_id"])
        row = conn.execute("SELECT resource_id FROM socialmei.agenda_appointments WHERE workspace_id=%s AND id=%s", (user["workspace_id"], appointment_id)).fetchone()
        if not row:
            raise HTTPException(404, "Agendamento não encontrado.")
        resource = lock_resource(conn, user["workspace_id"], row["resource_id"], False)
        row = conn.execute(f"SELECT {APPOINTMENT_COLUMNS} FROM socialmei.agenda_appointments WHERE workspace_id=%s AND id=%s FOR UPDATE", (user["workspace_id"], appointment_id)).fetchone()
        if row["revision"] != payload.expected_revision or row["revision"] >= MAX_SAFE_ID:
            raise HTTPException(409, "O agendamento mudou. Recarregue antes de salvar.")
        start = payload.scheduled_for or row["scheduled_for"]
        status = payload.status or row["status"]
        end = end_time(start, row["duration_minutes"])
        if status != "cancelled":
            if not resource["ativo"] and (payload.scheduled_for is not None or row["status"]=="cancelled"):
                raise HTTPException(422, "Reative o recurso antes de reagendar.")
            if not free(conn, user["workspace_id"], row["resource_id"], start, end, appointment_id):
                raise HTTPException(409, "Horário ocupado para este recurso. Escolha outro horário.")
        saved = conn.execute(f"UPDATE socialmei.agenda_appointments SET scheduled_for=%s,ends_at=%s,status=%s,revision=revision+1,updated_at=NOW() WHERE workspace_id=%s AND id=%s RETURNING {APPOINTMENT_COLUMNS}", (start,end,status,user["workspace_id"],appointment_id)).fetchone()
        history(conn,user["workspace_id"],saved)
    return view({**saved,"resource_name":resource["nome"]})
