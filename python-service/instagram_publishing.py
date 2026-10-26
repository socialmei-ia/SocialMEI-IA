"""Explicitly approved, durable single-image Instagram publishing.

Requires a connected Instagram professional account, permitted scopes, workspace
owner/admin, live session, installed schema and opt-in env. Unlike the n8n flow,
this endpoint never triggers a background send or retries uncertain operations.
Meta fetches the user's *public* JPEG URL; private uploads are not supported yet.
"""
import hashlib
import json
import os
import re
from ipaddress import ip_address
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator
from psycopg.rows import dict_row

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
    image_url: str = Field(min_length=15, max_length=2048)
    caption: str = Field(min_length=1, max_length=2200)

    @field_validator("image_url")
    @classmethod
    def validate_image(cls, value):
        return image_url(value)

    @field_validator("caption")
    @classmethod
    def validate_caption(cls, value):
        if not value.strip() or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("Legenda inválida.")
        return value


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
            json.dumps([user["workspace_id"], user["id"], value["image_url"], value["caption"]],
                       ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        request_id = payload.request_id
        with connect() as conn:
            conn.row_factory = dict_row
            _authorize(conn, user, session)
            row = conn.execute(
                "SELECT * FROM socialmei.ig_meta_publications WHERE workspace_id=%s AND request_id=%s",
                (user["workspace_id"], request_id),
            ).fetchone()
            if row:
                if row["content_fingerprint"] != fingerprint or row["created_by"] != user["id"]:
                    raise HTTPException(409, "Identificador usado para outra publicação.")
                return public_view(row)
            connection = self._connection(conn, user)
            token = self._token(user, connection)
            row = conn.execute(
                "INSERT INTO socialmei.ig_meta_publications "
                "(id,workspace_id,request_id,created_by,connection_id,external_account_id,"
                "image_url,caption,content_fingerprint,status) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'creating') RETURNING *",
                (uuid4(), user["workspace_id"], request_id, user["id"], connection["id"],
                 connection["external_account_id"], payload.image_url, payload.caption, fingerprint),
            ).fetchone()
        # The creation claim is committed before the first Meta request. Never
        # retry automatically after a timeout or process crash (unknown outcome).
        outcome = "uncertain"
        error_code = "provider_unconfirmed"
        media_id = None
        container_id = None
        try:
            container_id = self._call(
                connection["external_account_id"], "media",
                {"image_url": payload.image_url, "caption": payload.caption},
                token,
            )
            with connect() as conn:
                conn.execute(
                    "UPDATE socialmei.ig_meta_publications SET container_id=%s,status='created',"
                    "updated_at=NOW() WHERE id=%s AND status='creating'",
                    (container_id, row["id"]),
                )
            # Publish once and record intent before calling Meta.
            with connect() as conn:
                conn.execute(
                    "UPDATE socialmei.ig_meta_publications SET status='publishing',"
                    "updated_at=NOW() WHERE id=%s AND status='created'",
                    (row["id"],),
                )
            media_id = self._call(
                connection["external_account_id"], "media_publish",
                {"creation_id": container_id},
                token,
            )
            outcome, error_code = "published", None
        except (ProviderError, HTTPException):
            pass
        except Exception:
            # No exception chaining: never reveal a token, URL or Meta response.
            pass
        finally:
            token = None
        with connect() as conn:
            conn.row_factory = dict_row
            row = conn.execute(
                "UPDATE socialmei.ig_meta_publications SET status=%s,error_code=%s,"
                "container_id=COALESCE(container_id,%s),media_id=%s,updated_at=NOW() "
                "WHERE id=%s AND status IN ('creating','created','publishing') RETURNING *",
                (outcome, error_code, container_id, media_id, row["id"]),
            ).fetchone()
        if not row:
            raise HTTPException(503, "Registro de publicação não confirmado.")
        return public_view(row)


@router.get("/status")
def status(request: Request):
    user, session = actor(request)
    with connect() as conn:
        _authorize(conn, user, session)
        connected = conn.execute(
            "SELECT 1 FROM socialmei.ig_meta_connections WHERE workspace_id=%s "
            "AND status='connected' AND expires_at>NOW() AND scopes @> %s::text[] LIMIT 1",
            (user["workspace_id"], list(_REQUIRED)),
        ).fetchone()
    return {"available": permitted(), "connected": bool(connected), "format": "public_image_url"}


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
