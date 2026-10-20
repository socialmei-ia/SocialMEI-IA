"""Tenant-scoped Instagram dry-run. No network calls or real publication."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from account_auth import current, require_enabled
from database import connect

router = APIRouter(prefix="/api/v1/instagram/simulation", tags=["instagram-simulation"])
FORMATS = {
    "feed": {"image/jpeg", "image/png", "image/webp"},
    "reel": {"video/mp4", "video/webm"},
    "story": {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"},
}


def guard(*, write=False, manage=False):
    require_enabled()
    if os.getenv("SOCIALMEI_INSTAGRAM_MODE", "disabled").strip().lower() != "simulation":
        raise HTTPException(503, "Simulação Instagram não habilitada.")
    user = current()
    if write and user["role"] not in {"owner", "admin", "member"}:
        raise HTTPException(403, "Acesso somente leitura.")
    if manage and user["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente o responsável pode criar conta fictícia.")
    return user


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AccountInput(Strict):
    label: str = Field(min_length=1, max_length=80)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value):
        if not value.strip():
            raise ValueError("Nome fictício obrigatório.")
        return value.strip()


class MediaManifest(Strict):
    name: str = Field(min_length=1, max_length=180)
    mime: str
    size: int = Field(gt=0, le=50 * 1024 * 1024)

    @field_validator("name")
    @classmethod
    def safe_filename(cls, value):
        if any(ch in value for ch in "\r\n/\\") or not value.strip():
            raise ValueError("Nome de arquivo inválido.")
        return value


class PublicationInput(Strict):
    account_id: UUID
    idempotency_key: UUID
    format: str
    caption: str = Field(max_length=2200)
    media: list[MediaManifest] = Field(min_length=1, max_length=10)
    scheduled_for: datetime | None = None

    @model_validator(mode="after")
    def validate_publication(self):
        if self.format not in FORMATS:
            raise ValueError("Formato inválido.")
        if self.format != "feed" and len(self.media) != 1:
            raise ValueError("Story/Reel exige um arquivo.")
        for media in self.media:
            if media.mime not in FORMATS[self.format]:
                raise ValueError("Mídia incompatível com formato.")
            limit = 10 if media.mime.startswith("image/") else 50
            if media.size > limit * 1024 * 1024:
                raise ValueError("Mídia excede o limite.")
        if self.scheduled_for:
            if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
                raise ValueError("Agendamento exige fuso horário.")
            moment = self.scheduled_for.astimezone(timezone.utc)
            now = datetime.now(timezone.utc)
            if not now + timedelta(seconds=30) < moment < now + timedelta(days=365):
                raise ValueError("Agendamento no passado ou fora do limite.")
        return self


def view(row):
    return {
        "id": str(row["id"]),
        "account_id": str(row["account_id"]),
        "format": row["format"],
        "caption": row["caption"],
        "media": row["media_manifest"],
        "scheduled_for": row["scheduled_for"],
        "status": "simulated",
        "created_at": row["created_at"],
        "published": False,
    }


@router.get("/status")
def status():
    guard()
    return {"mode": "simulation", "transport": "none", "published": False}


@router.get("/accounts")
def accounts():
    user = guard()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id,label,created_at FROM socialmei.instagram_sim_accounts "
            "WHERE workspace_id=%s ORDER BY created_at DESC LIMIT 50",
            (user["workspace_id"],),
        )
        return {"items": [
            {"id": str(row["id"]), "label": row["label"], "simulated": True}
            for row in cur.fetchall()
        ]}


@router.post("/accounts", status_code=201)
def add_account(payload: AccountInput):
    user = guard(write=True, manage=True)
    account_id = uuid4()
    with connect() as conn:
        conn.execute(
            "INSERT INTO socialmei.instagram_sim_accounts "
            "(workspace_id,id,label,created_by) VALUES (%s,%s,%s,%s)",
            (user["workspace_id"], account_id, payload.label, user["id"]),
        )
    return {"id": str(account_id), "label": payload.label, "simulated": True}


@router.post("/publications", status_code=201)
def simulate(payload: PublicationInput, response: Response):
    user = guard(write=True)
    manifest = [item.model_dump() for item in payload.media]
    data = {
        "account_id": str(payload.account_id),
        "format": payload.format,
        "caption": payload.caption,
        "media": manifest,
        "scheduled_for": payload.scheduled_for.astimezone(timezone.utc).isoformat()
        if payload.scheduled_for else None,
    }
    fingerprint = hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT 1 FROM socialmei.instagram_sim_accounts WHERE workspace_id=%s AND id=%s",
            (user["workspace_id"], payload.account_id),
        )
        if not cur.fetchone():
            raise HTTPException(404, "Conta fictícia não encontrada neste negócio.")
        cur.execute(
            "INSERT INTO socialmei.instagram_sim_publications "
            "(workspace_id,id,account_id,requested_by,idempotency_key,fingerprint,"
            "format,caption,media_manifest,scheduled_for) VALUES "
            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(workspace_id,account_id,idempotency_key) DO NOTHING RETURNING id",
            (
                user["workspace_id"], uuid4(), payload.account_id, user["id"],
                payload.idempotency_key, fingerprint, payload.format, payload.caption,
                Jsonb(manifest), payload.scheduled_for,
            ),
        )
        inserted = cur.fetchone()
        cur.execute(
            "SELECT id,account_id,format,caption,media_manifest,scheduled_for,status,"
            "created_at,fingerprint FROM socialmei.instagram_sim_publications "
            "WHERE workspace_id=%s AND account_id=%s AND idempotency_key=%s",
            (user["workspace_id"], payload.account_id, payload.idempotency_key),
        )
        row = cur.fetchone()
        if row is None or row["fingerprint"] != fingerprint:
            raise HTTPException(409, "Chave já usada com outro conteúdo.")
        if not inserted:
            response.status_code = 200
        return view(row)


@router.get("/publications")
def publications():
    user = guard()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id,account_id,format,caption,media_manifest,scheduled_for,status,created_at "
            "FROM socialmei.instagram_sim_publications WHERE workspace_id=%s "
            "ORDER BY created_at DESC,id DESC LIMIT 30",
            (user["workspace_id"],),
        )
        return {"items": [view(row) for row in cur.fetchall()]}


@router.get("/publications/{publication_id}")
def publication(publication_id: UUID):
    user = guard()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id,account_id,format,caption,media_manifest,scheduled_for,status,created_at "
            "FROM socialmei.instagram_sim_publications WHERE workspace_id=%s AND id=%s",
            (user["workspace_id"], publication_id),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(404, "Simulação não encontrada neste negócio.")
    return view(row)
