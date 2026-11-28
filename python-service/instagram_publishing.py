"""Explicitly approved, durable single-image Instagram publishing.

Requires a connected Instagram professional account, permitted scopes, workspace
owner/admin, live session, installed schema and opt-in env. Unlike the n8n flow,
this endpoint never triggers a background send or retries uncertain operations.
Meta fetches a public JPEG URL or an expiring locally uploaded JPEG.
"""
import base64
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from threading import BoundedSemaphore
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from psycopg import Error as DatabaseError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import AwareDatetime, Field, ValidationError, field_validator, model_validator
from starlette.concurrency import run_in_threadpool
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from account_auth import COOKIE, Strict, current, digest, require_enabled
from database import connect
from instagram_meta_adapter import ProviderError, ProviderRequest
from instagram_persistent_oauth import _authorize
from instagram_token_vault import TokenBinding, VaultError

router = APIRouter(prefix="/api/v1/instagram/publishing", tags=["Instagram image publication"])
_REQUIRED = ("instagram_business_basic", "instagram_business_content_publish")
_ID = re.compile(r"[0-9]{1,40}\Z")
_DOMAIN = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")


def permitted():
    return os.getenv("SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED", "false").strip().lower() == "true"


def image_url(value):
    if not isinstance(value, str) or not 15 <= len(value) <= 2048:
        raise ValueError("Informe uma URL HTTPS pública de imagem.")
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        try:
            ip_address(host)
            raise ValueError("A imagem deve usar um domínio público.")
        except ValueError as exc:
            if str(exc) == "A imagem deve usar um domínio público.":
                raise
        if (
            parts.scheme != "https" or parts.port not in (None, 443)
            or parts.username or parts.password or parts.query or parts.fragment
            or not _DOMAIN.fullmatch(host)
            or host.endswith((".local", ".internal", ".test", ".example", ".invalid"))
            or any(ord(c) < 33 or ord(c) > 126 for c in value)
        ):
            raise ValueError("Use uma URL HTTPS pública, sem parâmetros ou fragmentos.")
    except (ValueError, AttributeError) as exc:
        raise ValueError("URL da imagem não permitida.") from None
    return value


class ImagePost(Strict):
    request_id: UUID
    image_url: str | None = Field(default=None, min_length=15, max_length=2048)
    media_id: UUID | None = None
    connection_id: UUID | None = None
    caption: str = Field(min_length=1, max_length=2200)

    @field_validator("image_url")
    @classmethod
    def validate_image(cls, value):
        return image_url(value) if value is not None else None

    @model_validator(mode="after")
    def exactly_one_image(self):
        if (self.image_url is None) == (self.media_id is None):
            raise ValueError("Selecione uma foto ou informe uma URL.")
        return self

    @field_validator("caption")
    @classmethod
    def validate_caption(cls, value):
        if not value.strip() or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("Legenda inválida.")
        return value


def schedule_enabled():
    return permitted() and os.getenv("SOCIALMEI_INSTAGRAM_SCHEDULE_ENABLED") == "YES"


def schedule_schema_ready():
    try:
        with connect() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout='2s'")
            return conn.execute(
                "SELECT EXISTS (SELECT 1 FROM socialmei.schema_migrations WHERE version=%s)",
                ("048_instagram_scheduled_images.sql",),
            ).fetchone()[0]
    except DatabaseError:
        return False


class ScheduleTime(Strict):
    scheduled_at: AwareDatetime
    timezone: str = Field(min_length=1, max_length=80)

    @field_validator("scheduled_at", mode="before")
    @classmethod
    def timestamp_with_offset(cls, value):
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})", value
        ):
            raise ValueError("Informe data e hora com o deslocamento do fuso.")
        return value

    @model_validator(mode="after")
    def valid_time(self):
        try:
            local = self.scheduled_at.astimezone(ZoneInfo(self.timezone))
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Selecione um fuso horário válido.") from None
        if local.utcoffset() != self.scheduled_at.utcoffset():
            raise ValueError("O horário e o fuso selecionado são incompatíveis.")
        return self

    def validate_window(self):
        now = datetime.now(timezone.utc)
        if not now + timedelta(minutes=1) <= self.scheduled_at <= now + timedelta(days=30):
            raise HTTPException(422, "Escolha um horário entre um minuto e 30 dias no futuro.")


class ScheduleImage(ImagePost, ScheduleTime):
    @model_validator(mode="after")
    def durable_source(self):
        if self.image_url is None or self.connection_id is None:
            raise ValueError("Confirme a conta e informe uma URL HTTPS durável da foto.")
        return self


class Reschedule(ScheduleTime):
    revision: int = Field(ge=1)


class CancelSchedule(Strict):
    revision: int = Field(ge=1)


class DraftDocument(Strict):
    f: Literal["story", "feed", "reel"]
    titulo: str = Field(min_length=1, max_length=50)
    leg: str = Field(default="", max_length=2200)
    tema: str = Field(default="", max_length=1000)
    prod: str = Field(default="", max_length=240)
    obj: str = Field(default="", max_length=120)
    tom: str = Field(default="", max_length=120)
    cta: str = Field(default="", max_length=240)
    tags: str = Field(default="", max_length=500)
    alt: str = Field(default="", max_length=400)
    zoom: str = Field(default="1", pattern=r"^\d(?:\.\d{1,2})?$")
    image_id: UUID | None = None
    image_x: float = Field(default=50, ge=0, le=100, allow_inf_nan=False)
    image_y: float = Field(default=50, ge=0, le=100, allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def safe_content(cls, value):
        if isinstance(value, str) and ("\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value)):
            raise ValueError("Texto inválido para o rascunho.")
        return value

    @field_validator("titulo", mode="after")
    @classmethod
    def title_present(cls, value):
        if not value.strip():
            raise ValueError("Informe um título.")
        return value.strip()


class DraftUpdate(Strict):
    operation_id: UUID
    expected_revision: int = Field(ge=0, le=2_147_483_646, strict=True)
    archived: bool = False
    document: DraftDocument


def draft_user(write=False):
    require_enabled()
    user = current()
    roles = {"owner", "admin", "member"} if write else {"owner", "admin", "member", "viewer"}
    if user["role"] not in roles:
        raise HTTPException(403, "Acesso à biblioteca de conteúdo indisponível para este papel.")
    return user


@router.get("/drafts")
def library_drafts():
    user = draft_user()
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout='3s'")
            rows = conn.execute(
                "SELECT id,revision,document,updated_at FROM ("
                "SELECT DISTINCT ON (draft_id) draft_id AS id,revision,document,archived,updated_at "
                "FROM socialmei.editorial_draft_revisions WHERE workspace_id=%s ORDER BY draft_id,revision DESC"
                ") latest WHERE NOT archived ORDER BY updated_at DESC,id LIMIT 101",
                (user["workspace_id"],),
            ).fetchall()
        return {"workspace_id": user["workspace_id"], "items": rows[:100], "truncated": len(rows) > 100}
    except DatabaseError:
        raise HTTPException(503, "Biblioteca indisponível. Seus rascunhos foram preservados.") from None


@router.put("/drafts/{draft_id}")
def save_library_draft(draft_id: UUID, payload: DraftUpdate):
    user = draft_user(write=True)
    workspace, actor = user["workspace_id"], user["id"]
    document = payload.document.model_dump(mode="json")
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET LOCAL lock_timeout='3s'")
            conn.execute("SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE", (workspace,))
            receipt = conn.execute(
                "SELECT draft_id AS id,revision,document,updated_at,archived,actor_id "
                "FROM socialmei.editorial_draft_revisions WHERE workspace_id=%s AND operation_id=%s",
                (workspace, payload.operation_id),
            ).fetchone()
            if receipt:
                if (receipt["id"] != draft_id or DraftDocument.model_validate(receipt["document"]).model_dump(mode="json") != document
                        or receipt["archived"] != payload.archived or receipt["actor_id"] != actor
                        or receipt["revision"] != payload.expected_revision + 1):
                    raise HTTPException(409, "Identificador usado com outros dados.")
                return {key: receipt[key] for key in ("id", "revision", "document", "updated_at")}
            latest = conn.execute(
                "SELECT revision,archived FROM socialmei.editorial_draft_revisions "
                "WHERE workspace_id=%s AND draft_id=%s ORDER BY revision DESC LIMIT 1",
                (workspace, draft_id),
            ).fetchone()
            revision = latest["revision"] if latest else 0
            if revision != payload.expected_revision or (latest and latest["archived"]) or (payload.archived and not latest):
                raise HTTPException(409, "Este rascunho mudou ou foi arquivado. Atualize a biblioteca.")
            asset = payload.document.image_id
            if asset is not None and not conn.execute(
                "SELECT 1 FROM socialmei.editorial_draft_assets WHERE workspace_id=%s AND id=%s FOR KEY SHARE",
                (workspace, asset),
            ).fetchone():
                raise HTTPException(404, "Imagem indisponível neste negócio.")
            return conn.execute(
                "INSERT INTO socialmei.editorial_draft_revisions "
                "(workspace_id,draft_id,revision,operation_id,actor_id,document,archived,asset_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
                "RETURNING draft_id AS id,revision,document,updated_at",
                (workspace, draft_id, revision + 1, payload.operation_id, actor, Jsonb(document), payload.archived, asset),
            ).fetchone()
    except DatabaseError:
        raise HTTPException(503, "Não foi possível confirmar o rascunho.") from None


class DraftAssetUpload(Strict):
    image_base64: str = Field(min_length=1, max_length=2796204)


_asset_normalizers = BoundedSemaphore(value=2)


def store_draft_asset(user, payload):
    from instagram_media import normalize_image

    if not _asset_normalizers.acquire(blocking=False):
        raise HTTPException(429, "Aguarde um instante para salvar outra imagem.")
    try:
        raw = normalize_image(payload.image_base64, library=True)
    finally:
        _asset_normalizers.release()
    digest = hashlib.sha256(raw).hexdigest()
    workspace = user["workspace_id"]
    with connect() as conn:
        conn.execute("SET LOCAL lock_timeout='3s'")
        conn.execute("SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE", (workspace,))
        existing = conn.execute(
            "SELECT id FROM socialmei.editorial_draft_assets WHERE workspace_id=%s AND fingerprint=%s",
            (workspace, digest),
        ).fetchone()
        if existing:
            return {"id": existing[0]}
        count, size = conn.execute(
            "SELECT count(*),COALESCE(sum(octet_length(image_bytes)),0) "
            "FROM socialmei.editorial_draft_assets WHERE workspace_id=%s", (workspace,),
        ).fetchone()
        if count >= 50 or size + len(raw) > 24 * 1024 * 1024:
            raise HTTPException(409, "A biblioteca atingiu o limite de 50 imagens ou 24 MiB.")
        asset = uuid4()
        conn.execute(
            "INSERT INTO socialmei.editorial_draft_assets(workspace_id,id,fingerprint,image_bytes,actor_id) "
            "VALUES(%s,%s,%s,%s,%s)", (workspace, asset, digest, raw, user["id"]),
        )
        return {"id": asset}


@router.post("/draft-assets")
async def upload_draft_asset(request: Request):
    user = draft_user(write=True)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 2_797_000:
            raise HTTPException(413, "A foto deve ter até 2 MiB.")
        body.extend(chunk)
    try:
        payload = DraftAssetUpload.model_validate_json(bytes(body))
    except ValidationError:
        raise HTTPException(422, "Informe os dados válidos de uma imagem.") from None
    try:
        return await run_in_threadpool(store_draft_asset, user, payload)
    except DatabaseError:
        raise HTTPException(503, "Biblioteca de imagens indisponível.") from None


@router.get("/draft-assets")
def list_draft_assets():
    workspace = draft_user()["workspace_id"]
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT id,created_at FROM socialmei.editorial_draft_assets WHERE workspace_id=%s "
            "ORDER BY created_at DESC,id LIMIT 50", (workspace,),
        ).fetchall()
    return {"workspace_id": workspace, "items": rows}


@router.get("/draft-assets/{asset_id}")
def read_draft_asset(asset_id: UUID):
    workspace = draft_user()["workspace_id"]
    with connect() as conn:
        row = conn.execute(
            "SELECT image_bytes FROM socialmei.editorial_draft_assets WHERE workspace_id=%s AND id=%s",
            (workspace, asset_id),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Imagem indisponível.")
    return {"id": asset_id, "workspace_id": workspace, "image_base64": base64.b64encode(row[0]).decode("ascii")}


def scheduler_role(conn, workspace, user):
    return conn.execute(
        "SELECT 1 FROM socialmei.workspace_members m JOIN socialmei.auth_credenciais c "
        "ON c.user_id=m.user_id AND c.ativo WHERE m.workspace_id=%s AND m.user_id=%s "
        "AND m.role IN ('owner','admin') FOR SHARE OF m,c", (workspace, user),
    ).fetchone() is not None

def service(request: Request):
    from instagram_runtime import runtime_service
    if not permitted():
        raise HTTPException(503, "Publicação ainda não habilitada.")
    return runtime_service(request, "publish")


def actor(request):
    require_enabled()
    user = current()
    session = digest(request.cookies.get(COOKIE, ""))
    return user, session


def external_id(value):
    if type(value) not in (int, str) or not _ID.fullmatch(str(value)):
        raise ProviderError(outcome_unknown=True)
    return str(value)


def public_view(row):
    return {
        "id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "status": row["status"],
        "media_id": row["media_id"],
        "error_code": row["error_code"],
        "created_at": row["created_at"].isoformat(),
        **({"scheduled_at": row["scheduled_at"].isoformat(), "timezone": row["schedule_timezone"],
            "revision": row["schedule_revision"], "caption": row["caption"]} if row.get("scheduled_at") else {}),
    }


class InstagramPublishingService:
    def __init__(self, adapter, vault):
        self.adapter, self.vault = adapter, vault

    def _connection(self, conn, user):
        row = conn.execute(
            "SELECT id,external_account_id,encrypted_token FROM socialmei.ig_meta_connections "
            "WHERE workspace_id=%s AND status='connected' AND expires_at>NOW() "
            "AND scopes @> %s::text[] ORDER BY created_at DESC LIMIT 1 FOR SHARE",
            (user["workspace_id"], list(_REQUIRED)),
        ).fetchone()
        if not row:
            raise HTTPException(409, "Conecte o Instagram profissional com permissão de publicação.")
        return row

    def _token(self, user, connection):
        try:
            return self.vault.open(
                connection["encrypted_token"],
                TokenBinding(user["workspace_id"], connection["id"], connection["external_account_id"]),
            )
        except VaultError:
            raise HTTPException(503, "Credencial Instagram indisponível.") from None

    def _call(self, account, path, form, token):
        # HTTPS host and path are generated from validated provider metadata.
        data = self.adapter._request(
            ProviderRequest(
                "POST",
                f"https://graph.instagram.com/{self.adapter._version}/{account}/{path}",
                headers={"Authorization": "Bearer " + token},
                form=form,
            ),
            retryable=False,
            success_codes=range(200, 300),
        )
        return external_id(data.get("id"))

    def publish_image(self, user, session, payload):
        value = payload.model_dump(mode="json")
        fingerprint = hashlib.sha256(
            json.dumps([user["workspace_id"], user["id"], value["image_url"], value["media_id"], value["caption"], value["connection_id"]],
                       ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        request_id = payload.request_id
        with connect() as conn:
            conn.row_factory = dict_row
            _authorize(conn, user, session)
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                         (f"instagram-publication:{user['workspace_id']}:{request_id}",))
            row = conn.execute(
                "SELECT * FROM socialmei.ig_meta_publications WHERE workspace_id=%s AND request_id=%s",
                (user["workspace_id"], request_id),
            ).fetchone()
            if row:
                if row["content_fingerprint"] != fingerprint or row["created_by"] != user["id"]:
                    raise HTTPException(409, "Identificador usado para outra publicação.")
                return public_view(row)
            connection = self._connection(conn, user)
            if payload.connection_id and payload.connection_id != connection['id']:
                raise HTTPException(409, "A conta Instagram mudou. Confira o perfil novamente.")
            token = self._token(user, connection)
            resolved_url = payload.image_url
            if payload.media_id:
                from instagram_media import resolve_media
                resolved_url = resolve_media(conn, user, payload.media_id)
            row = conn.execute(
                "INSERT INTO socialmei.ig_meta_publications "
                "(id,workspace_id,request_id,created_by,connection_id,external_account_id,"
                "image_url,caption,content_fingerprint,status) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'creating') RETURNING *",
                (uuid4(), user["workspace_id"], request_id, user["id"], connection["id"],
                 connection["external_account_id"], resolved_url, payload.caption, fingerprint),
            ).fetchone()
        # A committed claim precedes the only container creation request.
        try:
            container_id = self._call(
                connection["external_account_id"], "media",
                {"image_url": resolved_url, "caption": payload.caption}, token,
            )
        except Exception:
            return self._result(row["id"], "uncertain", "container_unconfirmed")
        finally:
            token = None
        with connect() as conn:
            conn.execute("UPDATE socialmei.ig_meta_publications SET container_id=%s,"
                         "status='created',updated_at=NOW() WHERE id=%s AND status='creating'",
                         (container_id, row["id"]))
        return self.advance(user, session, row["id"])

    def schedule(self, user, session, payload):
        workspace=user["workspace_id"]
        value=payload.model_dump(mode="json")
        signature=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        with connect() as conn:
            conn.row_factory=dict_row
            _authorize(conn,user,session)
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                         (f"instagram-publication:{workspace}:{payload.request_id}",))
            found=conn.execute("SELECT * FROM socialmei.ig_meta_publications WHERE workspace_id=%s AND request_id=%s",
                               (workspace,payload.request_id)).fetchone()
            if found:
                if found["content_fingerprint"]!=signature or found["created_by"]!=user["id"]:
                    raise HTTPException(409,"Identificador usado para outra publicação.")
                return public_view(found)
            payload.validate_window()
            account=self._connection(conn,user)
            if payload.connection_id!=account["id"]:
                raise HTTPException(409,"A conta Instagram mudou. Confira o perfil novamente.")
            row=conn.execute(
                "INSERT INTO socialmei.ig_meta_publications(id,workspace_id,request_id,created_by,connection_id,external_account_id,"
                "image_url,caption,content_fingerprint,status,scheduled_at,schedule_timezone,schedule_revision) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'scheduled',%s,%s,1) RETURNING *",
                (uuid4(),workspace,payload.request_id,user["id"],account["id"],account["external_account_id"],
                 payload.image_url,payload.caption,signature,payload.scheduled_at,payload.timezone),
            ).fetchone()
            return public_view(row)

    def process_scheduled_once(self):
        if not schedule_enabled():
            return False
        with connect() as conn:
            conn.row_factory=dict_row
            row=conn.execute(
                "SELECT * FROM socialmei.ig_meta_publications WHERE scheduled_at IS NOT NULL AND ("
                "(status='scheduled' AND scheduled_at<=NOW() AND (checked_at IS NULL OR checked_at<=NOW()-INTERVAL '60 seconds')) OR "
                "(status='created' AND (checked_at IS NULL OR checked_at<=NOW()-INTERVAL '60 seconds')) OR "
                "(status IN ('creating','publishing') AND updated_at<=NOW()-INTERVAL '5 minutes')) "
                "ORDER BY CASE WHEN status='scheduled' THEN scheduled_at ELSE COALESCE(checked_at,updated_at) END,id "
                "LIMIT 1 FOR UPDATE SKIP LOCKED",
            ).fetchone()
            if not row:
                return False
            if row["status"] in {"creating","publishing"}:
                conn.execute("UPDATE socialmei.ig_meta_publications SET status='uncertain',error_code='dispatch_interrupted',"
                             "updated_at=NOW() WHERE id=%s",(row["id"],))
                return True
            now = datetime.now(timezone.utc)
            if row["status"] == "scheduled" and row["scheduled_at"] < now - timedelta(hours=24):
                conn.execute("UPDATE socialmei.ig_meta_publications SET status='failed',error_code='schedule_missed',"
                             "updated_at=NOW() WHERE id=%s", (row["id"],))
                return True
            if row["status"] == "created" and row["updated_at"] < now - timedelta(minutes=30):
                conn.execute("UPDATE socialmei.ig_meta_publications SET status='uncertain',error_code='processing_timeout',"
                             "updated_at=NOW() WHERE id=%s", (row["id"],))
                return True
            user={"id":row["created_by"],"workspace_id":row["workspace_id"]}
            try:
                if not scheduler_role(conn,user["workspace_id"],user["id"]):
                    raise HTTPException(403)
                connection=self._connection(conn,user)
                if connection["id"]!=row["connection_id"] or connection["external_account_id"]!=row["external_account_id"]:
                    raise HTTPException(409)
                token=self._token(user,connection)
            except HTTPException as error:
                # An unavailable credential may recover. Keep the operation in the queue briefly.
                if error.status_code==503:
                    conn.execute("UPDATE socialmei.ig_meta_publications SET checked_at=NOW() WHERE id=%s",(row["id"],))
                    return False
                conn.execute("UPDATE socialmei.ig_meta_publications SET status='failed',error_code='authorization_changed',"
                             "updated_at=NOW() WHERE id=%s",(row["id"],))
                return True
            if row["status"]=="created":
                if not self._check_finished(conn,row,token):
                    return True
                route,form="media_publish",{"creation_id":row["container_id"]}
            else:
                conn.execute("UPDATE socialmei.ig_meta_publications SET status='creating',updated_at=NOW() WHERE id=%s",(row["id"],))
                route,form="media",{"image_url":row["image_url"],"caption":row["caption"]}
        expected = "creating" if route == "media" else "publishing"
        try:
            provider_id = self._call(row["external_account_id"], route, form, token)
        except ProviderError as error:
            if not error.outcome_unknown and error.status_code in {400, 401, 403, 404, 413, 415, 422, 429}:
                code = "provider_rate_limit" if error.status_code == 429 else "provider_rejected"
                self._result(row["id"], "failed", code, expected=expected)
            else:
                self._result(row["id"], "uncertain", "dispatch_unconfirmed", expected=expected)
        else:
            if route == "media":
                with connect() as conn:
                    conn.execute(
                        "UPDATE socialmei.ig_meta_publications SET container_id=%s,status='created',"
                        "checked_at=NULL,updated_at=NOW() WHERE id=%s AND status='creating'",
                        (provider_id, row["id"]),
                    )
            else:
                self._result(row["id"], "published", None, provider_id, expected="publishing")
        return True

    def _check_finished(self,conn,row,token):
        try:
            data=self.adapter._request(ProviderRequest(
                "GET",f"https://graph.instagram.com/{self.adapter._version}/{row['container_id']}",
                headers={"Authorization":"Bearer "+token},params={"fields":"status_code"},
            ),retryable=True)
            state=data.get("status_code")
        except ProviderError:
            state="UNAVAILABLE"
        conn.execute("UPDATE socialmei.ig_meta_publications SET checked_at=NOW() WHERE id=%s",(row["id"],))
        if state in {"IN_PROGRESS","UNAVAILABLE"}:
            return False
        if state!="FINISHED":
            conn.execute("UPDATE socialmei.ig_meta_publications SET status=%s,error_code=%s,updated_at=NOW() WHERE id=%s",
                         ("failed" if state in {"ERROR","EXPIRED"} else "uncertain",
                          "media_processing_failed" if state in {"ERROR","EXPIRED"} else "provider_unconfirmed",row["id"]))
            return False
        conn.execute("UPDATE socialmei.ig_meta_publications SET status='publishing',updated_at=NOW() WHERE id=%s",(row["id"],))
        return True

    def _result(self, publication_id, status, error_code, media_id=None, *, expected=None):
        with connect() as conn:
            conn.row_factory = dict_row
            row = conn.execute(
                "UPDATE socialmei.ig_meta_publications SET status=%s,error_code=%s,"
                "media_id=%s,updated_at=NOW() WHERE id=%s AND (%s::text IS NULL OR status=%s) RETURNING *",
                (status, error_code, media_id, publication_id, expected, expected),
            ).fetchone()
        return public_view(row) if row else None

    def engagement(self, user, session, publication_id):
        with connect() as conn:
            conn.row_factory = dict_row
            _authorize(conn, user, session)
            row = conn.execute(
                "SELECT connection_id,external_account_id,media_id FROM socialmei.ig_meta_publications "
                "WHERE workspace_id=%s AND id=%s AND status='published'",
                (user["workspace_id"], publication_id),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Publicação confirmada não encontrada.")
            connection = self._connection(conn, user)
            if (connection["id"], connection["external_account_id"]) != (row["connection_id"], row["external_account_id"]):
                raise HTTPException(409, "Conecte a conta que publicou este conteúdo.")
            token = self._token(user, connection)
        try:
            media = external_id(row["media_id"])
            result = self.adapter._request(ProviderRequest(
                "GET", f"https://graph.instagram.com/{self.adapter._version}/{media}",
                headers={"Authorization": "Bearer " + token},
                params={"fields": "id,like_count,comments_count"},
            ), retryable=True)
            if external_id(result.get("id")) != media:
                raise ProviderError()
        except ProviderError:
            raise HTTPException(503, "Métricas temporariamente indisponíveis no Instagram.") from None
        finally:
            token = None
        with connect() as conn:
            conn.row_factory = dict_row
            _authorize(conn, user, session, lock=False)
        metrics = {}
        for name in ("like_count", "comments_count"):
            value = result.get(name)
            metrics[name] = value if type(value) is int and 0 <= value <= 9007199254740991 else None
        return metrics


    def advance(self, user, session, publication_id):
        # Explicit POST continuation of an existing approved intention. GETs never send.
        with connect() as conn:
            conn.row_factory = dict_row
            _authorize(conn, user, session)
            row = conn.execute(
                "SELECT *,created_at<NOW()-INTERVAL '5 minutes' AS too_old, "
                "checked_at IS NOT NULL AND checked_at>NOW()-INTERVAL '60 seconds' AS throttled "
                "FROM socialmei.ig_meta_publications WHERE id=%s AND workspace_id=%s FOR UPDATE",
                (publication_id, user["workspace_id"]),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Publicação não encontrada.")
            if row.get("scheduled_at") or row["status"] != "created" or row["throttled"]:
                return public_view(row)
            if row['too_old']:
                row = conn.execute("UPDATE socialmei.ig_meta_publications SET status='uncertain',"
                                   "error_code='processing_timeout',updated_at=NOW() WHERE id=%s RETURNING *",
                                   (row['id'],)).fetchone()
                return public_view(row)
            connection = self._connection(conn, user)
            if connection['id'] != row['connection_id']:
                raise HTTPException(409, "A conta Instagram mudou. Confira a publicação anterior.")
            token = self._token(user, connection)
            try:
                data = self.adapter._request(ProviderRequest(
                    "GET", f"https://graph.instagram.com/{self.adapter._version}/{row['container_id']}",
                    headers={"Authorization": "Bearer " + token}, params={"fields": "status_code"},
                ), retryable=True)
                state = data.get('status_code')
            except ProviderError:
                state = 'UNAVAILABLE'
            conn.execute("UPDATE socialmei.ig_meta_publications SET checked_at=NOW() WHERE id=%s", (row['id'],))
            if state == 'IN_PROGRESS' or state == 'UNAVAILABLE':
                return public_view(row)
            if state != 'FINISHED':
                # No guessed success, and never republish a PUBLISHED container.
                row = conn.execute("UPDATE socialmei.ig_meta_publications SET status='uncertain',"
                                   "error_code=%s,updated_at=NOW() WHERE id=%s RETURNING *",
                                   ('media_processing_failed' if state in {'ERROR','EXPIRED'} else 'provider_unconfirmed', row['id'])).fetchone()
                return public_view(row)
            conn.execute("UPDATE socialmei.ig_meta_publications SET status='publishing',updated_at=NOW() "
                         "WHERE id=%s", (row['id'],))
        # Only the row-lock owner commits publishing intent; concurrent continuations do nothing.
        try:
            media_id = self._call(row['external_account_id'], 'media_publish',
                                  {'creation_id': row['container_id']}, token)
        except Exception:
            return self._result(row['id'], 'uncertain', 'publication_unconfirmed')
        finally:
            token = None
        return self._result(row['id'], 'published', None, media_id)


@router.get("/status")
def status(request: Request):
    user, session = actor(request)
    with connect() as conn:
        conn.row_factory = dict_row
        _authorize(conn, user, session)
        connected = conn.execute(
            "SELECT 1 FROM socialmei.ig_meta_connections WHERE workspace_id=%s "
            "AND status='connected' AND expires_at>NOW() AND scopes @> %s::text[] LIMIT 1",
            (user["workspace_id"], list(_REQUIRED)),
        ).fetchone()
    from instagram_runtime import schema_ready
    runtime = getattr(request.app.state, "instagram_runtime", None)
    available = permitted() and getattr(runtime, 'publish', None) is not None and schema_ready('publish')
    return {"available": available, "connected": bool(connected),
            "format": "local_image_or_public_url", "upload_available": available,
            "schedule_available": available and schedule_enabled() and schedule_schema_ready()}


@router.get("/account")
def account(request: Request, publisher: InstagramPublishingService = Depends(service)):
    user, session = actor(request)
    with connect() as conn:
        conn.row_factory = dict_row
        _authorize(conn, user, session)
        connection = publisher._connection(conn, user)
        token = publisher._token(user, connection)
    try:
        result = publisher.adapter._request(ProviderRequest(
            'GET', f'https://graph.instagram.com/{publisher.adapter._version}/me',
            params={'fields': 'id,username,account_type'},
            headers={'Authorization': 'Bearer ' + token},
        ), retryable=True)
        username = result.get('username')
        if (str(result.get('id')) != connection['external_account_id']
                or not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,30}', username)):
            raise ProviderError()
        return {'username': username, 'connection_id': str(connection['id'])}
    except ProviderError:
        raise HTTPException(503, 'Não foi possível confirmar o perfil Instagram. Tente novamente.') from None
    finally:
        token = None


@router.post("/image")
def publish_image(
    payload: ImagePost, request: Request,
    publisher: InstagramPublishingService = Depends(service),
):
    user, session = actor(request)
    return publisher.publish_image(user, session, payload)


@router.get("/recent")
def recent(request: Request, publisher: InstagramPublishingService = Depends(service)):
    user, session = actor(request)
    with connect() as conn:
        conn.row_factory = dict_row
        _authorize(conn, user, session, manage=False)
        rows = conn.execute(
            "SELECT * FROM socialmei.ig_meta_publications WHERE workspace_id=%s "
            "ORDER BY created_at DESC LIMIT 25",
            (user["workspace_id"],),
        ).fetchall()
    return {"items": [public_view(row) for row in rows]}


@router.post("/{publication_id}/engagement")
def publication_engagement(publication_id: UUID, request: Request, response: Response,
                           publisher: InstagramPublishingService = Depends(service)):
    user, session = actor(request)
    response.headers["Cache-Control"] = "no-store"
    return publisher.engagement(user, session, publication_id)



@router.post("/{publication_id}/continue")
def continue_publication(publication_id: UUID, request: Request,
                         publisher: InstagramPublishingService = Depends(service)):
    user, session = actor(request)
    return publisher.advance(user, session, publication_id)


def require_schedule():
    if not schedule_enabled():
        raise HTTPException(503, "Agendamento de publicações ainda indisponível.")


@router.post("/scheduled")
def schedule_publication(payload: ScheduleImage, request: Request,
                         publisher: InstagramPublishingService = Depends(service)):
    require_schedule()
    user,session=actor(request)
    return publisher.schedule(user,session,payload)


@router.get("/scheduled")
def scheduled_publications(request: Request):
    require_schedule()
    user,session=actor(request)
    with connect() as conn:
        conn.row_factory=dict_row
        _authorize(conn,user,session,manage=False)
        rows=conn.execute("SELECT * FROM socialmei.ig_meta_publications WHERE workspace_id=%s AND scheduled_at IS NOT NULL "
                          "ORDER BY scheduled_at DESC,id LIMIT 100",(user["workspace_id"],)).fetchall()
    return {"items":[public_view(row) for row in rows]}


def edit_schedule(publication_id, payload, request, *, cancel):
    require_schedule()
    user,session=actor(request)
    with connect() as conn:
        conn.row_factory=dict_row
        _authorize(conn,user,session)
        row=conn.execute("SELECT * FROM socialmei.ig_meta_publications WHERE workspace_id=%s AND id=%s "
                         "AND scheduled_at IS NOT NULL FOR UPDATE",(user["workspace_id"],publication_id)).fetchone()
        if not row:
            raise HTTPException(404,"Publicação agendada não encontrada.")
        if row["status"]!="scheduled" or row["schedule_revision"]!=payload.revision:
            raise HTTPException(409,"A publicação mudou ou já começou. Atualize a lista.")
        if cancel:
            query="UPDATE socialmei.ig_meta_publications SET status='cancelled',schedule_revision=schedule_revision+1,updated_at=NOW() WHERE id=%s RETURNING *"
            values=(publication_id,)
        else:
            payload.validate_window()
            query="UPDATE socialmei.ig_meta_publications SET scheduled_at=%s,schedule_timezone=%s,schedule_revision=schedule_revision+1,updated_at=NOW() WHERE id=%s RETURNING *"
            values=(payload.scheduled_at,payload.timezone,publication_id)
        return public_view(conn.execute(query,values).fetchone())


@router.patch("/scheduled/{publication_id}")
def reschedule_publication(publication_id: UUID, payload: Reschedule, request: Request):
    return edit_schedule(publication_id,payload,request,cancel=False)


@router.post("/scheduled/{publication_id}/cancel")
def cancel_publication_schedule(publication_id: UUID, payload: CancelSchedule, request: Request):
    return edit_schedule(publication_id,payload,request,cancel=True)
