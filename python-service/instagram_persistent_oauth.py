"""Durable session-bound Instagram OAuth with explicitly injected dependencies.

No default transport or keys, GET callback, token delivery to clients, provider
revocation, message/publication worker, or production configuration is installed.
"""

import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.errors import DeadlockDetected, SerializationFailure, UniqueViolation
from psycopg.rows import dict_row
from pydantic import Field, model_validator

import settings
from account_auth import COOKIE, Strict, current, digest, require_enabled
from database import connect
from instagram_meta_adapter import InstagramAdapter, ProviderError
from instagram_meta_contract import MetaContractError, authorization_url_from_embed
from instagram_token_vault import TokenBinding, TokenVault, VaultError

router = APIRouter(prefix="/api/v1/instagram/meta", tags=["prepared Instagram OAuth"])
STATE_TTL_SECONDS = 300


def oauth_service(request: Request = None):
    from instagram_runtime import runtime_service
    return runtime_service(request, "oauth")


@contextmanager
def db():
    with connect() as conn:
        conn.row_factory = dict_row
        yield conn


def _lock(conn, workspace):
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        (f"instagram-oauth:{workspace}",),
    )


def _authorize(conn, user, session_hash, *, manage=True, lock=True):
    if (
        type(user.get("id")) is not int
        or type(user.get("workspace_id")) is not int
        or not isinstance(session_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", session_hash)
    ):
        raise HTTPException(401, "Sessão indisponível.")
    row = conn.execute(
        "SELECT m.role FROM socialmei.auth_sessoes s "
        "JOIN socialmei.auth_credenciais c ON c.user_id=s.user_id "
        "JOIN socialmei.workspace_members m ON m.workspace_id=s.workspace_id AND m.user_id=s.user_id "
        "WHERE s.token_hash=%s AND s.workspace_id=%s AND s.user_id=%s "
        "AND s.revogada_em IS NULL AND s.expira_em>NOW() AND c.ativo"
        + (" FOR SHARE OF s,c,m" if lock else ""),
        (session_hash, user["workspace_id"], user["id"]),
    ).fetchone()
    if not row:
        raise HTTPException(401, "Sessão ausente ou expirada.")
    if manage and row["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente responsáveis podem gerenciar a conexão.")


def _audit(conn, user, action, connection_id=None):
    conn.execute(
        "INSERT INTO socialmei.ig_meta_audit(workspace_id,user_id,connection_id,action) VALUES(%s,%s,%s,%s)",
        (user["workspace_id"], user["id"], connection_id, action),
    )


def _cancel_states(conn, workspace):
    conn.execute(
        "UPDATE socialmei.ig_meta_oauth_states SET status='cancelled',consumed_at=COALESCE(consumed_at,NOW()) "
        "WHERE workspace_id=%s AND status IN ('pending','exchanging')",
        (workspace,),
    )


def _expire(conn, *, workspace=None, account=None):
    rows = conn.execute(
        "UPDATE socialmei.ig_meta_connections SET status='expired',encrypted_token=NULL,"
        "disconnected_at=NOW(),revision=revision+1 WHERE status='connected' AND expires_at<=NOW() "
        "AND (workspace_id=%s OR external_account_id=%s) RETURNING id,workspace_id",
        (workspace, account),
    ).fetchall()
    for row in rows:
        conn.execute(
            "INSERT INTO socialmei.ig_meta_audit(workspace_id,connection_id,action) VALUES(%s,%s,'expired')",
            (row["workspace_id"], row["id"]),
        )


class InstagramOAuthService:
    def __init__(
        self, *, adapter, vault, authorization_embed, callback_uri, required_scopes
    ):
        if not isinstance(adapter, InstagramAdapter) or not isinstance(
            vault, TokenVault
        ):
            raise ValueError("Dependências Instagram indisponíveis.")
        self.adapter = adapter
        self.vault = vault
        self.callback_uri = callback_uri
        self.required_scopes = frozenset(required_scopes)
        self.authorization_embed = authorization_embed
        authorization_url_from_embed(
            authorization_embed,
            callback_uri,
            "a" * 43,
            required_scopes=self.required_scopes,
        )
        if not adapter.matches_configuration(callback_uri, authorization_embed):
            raise ValueError("Configuração Instagram incompatível.")

    def start(self, user, session_hash):
        state = secrets.token_urlsafe(32)
        url = authorization_url_from_embed(
            self.authorization_embed,
            self.callback_uri,
            state,
            required_scopes=self.required_scopes,
        )
        with db() as conn:
            _lock(conn, user["workspace_id"])
            _authorize(conn, user, session_hash)
            _expire(conn, workspace=user["workspace_id"])
            count = conn.execute(
                "SELECT COUNT(*) AS total FROM socialmei.ig_meta_oauth_states WHERE workspace_id=%s AND created_at>NOW()-INTERVAL '10 minutes'",
                (user["workspace_id"],),
            ).fetchone()["total"]
            if count >= 20:
                raise HTTPException(429, "Aguarde antes de tentar conectar novamente.")
            _cancel_states(conn, user["workspace_id"])
            conn.execute(
                "INSERT INTO socialmei.ig_meta_oauth_states(state_hash,workspace_id,user_id,session_hash,callback_uri,scopes,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    digest(state),
                    user["workspace_id"],
                    user["id"],
                    session_hash,
                    self.callback_uri,
                    sorted(self.required_scopes),
                    datetime.now(timezone.utc) + timedelta(seconds=STATE_TTL_SECONDS),
                ),
            )
            _audit(conn, user, "started")
        return {
            "state": state,
            "authorization_url": url,
            "expires_in": STATE_TTL_SECONDS,
            "provider": "instagram",
        }

    def _failed(self, user, state_hash):
        with db() as conn:
            # Provider completion is asynchronous: the actor may no longer be a member.
            workspace = conn.execute(
                "SELECT id FROM socialmei.workspaces WHERE id=%s FOR KEY SHARE",
                (user["workspace_id"],),
            ).fetchone()
            if not workspace:
                return
            row = conn.execute(
                "UPDATE socialmei.ig_meta_oauth_states SET status='failed' WHERE state_hash=%s AND workspace_id=%s AND status='exchanging' RETURNING state_hash",
                (state_hash, user["workspace_id"]),
            ).fetchone()
            if row:
                conn.execute(
                    "INSERT INTO socialmei.ig_meta_audit(workspace_id,action) VALUES(%s,'failed')",
                    (user["workspace_id"],),
                )

    def callback(self, user, session_hash, state, code, callback_uri, error=None):
        state_hash = digest(state)
        with db() as conn:
            _lock(conn, user["workspace_id"])
            _authorize(conn, user, session_hash)
            if callback_uri != self.callback_uri:
                raise HTTPException(409, "Autorização inválida, expirada ou utilizada.")
            claimed = conn.execute(
                "UPDATE socialmei.ig_meta_oauth_states SET consumed_at=NOW(),status='exchanging' "
                "WHERE state_hash=%s AND workspace_id=%s AND user_id=%s AND session_hash=%s "
                "AND callback_uri=%s AND scopes=%s AND consumed_at IS NULL AND status='pending' AND expires_at>NOW() RETURNING state_hash",
                (
                    state_hash,
                    user["workspace_id"],
                    user["id"],
                    session_hash,
                    self.callback_uri,
                    sorted(self.required_scopes),
                ),
            ).fetchone()
            if not claimed:
                raise HTTPException(409, "Autorização inválida, expirada ou utilizada.")
        # The claim commits before HTTP. A timeout must never reopen the one-use code.
        if error is not None:
            self._failed(user, state_hash)
            raise HTTPException(400, "Autorização não concluída. Inicie novamente.")
        grant = identity = None
        try:
            short = self.adapter.exchange_code(
                code, required_scopes=self.required_scopes
            )
            grant = self.adapter.extend_token(short)
            identity = self.adapter.get_identity(grant)
        except ProviderError:
            pass
        if grant is None or identity is None:
            self._failed(user, state_hash)
            raise HTTPException(
                502, "Não foi possível concluir a conexão. Inicie uma nova autorização."
            )
        connection_id = uuid4()
        binding = TokenBinding(user["workspace_id"], connection_id, identity.user_id)
        encrypted = None
        try:
            encrypted = self.vault.seal(grant.access_token, binding)
        except VaultError:
            pass
        if encrypted is None:
            self._failed(user, state_hash)
            raise HTTPException(503, "Armazenamento seguro indisponível.")
        conflict = False
        try:
            with db() as conn:
                _lock(conn, user["workspace_id"])
                _authorize(conn, user, session_hash)
                state_row = conn.execute(
                    "SELECT status FROM socialmei.ig_meta_oauth_states WHERE state_hash=%s AND workspace_id=%s FOR UPDATE",
                    (state_hash, user["workspace_id"]),
                ).fetchone()
                if not state_row or state_row["status"] != "exchanging":
                    raise HTTPException(409, "Autorização cancelada. Inicie novamente.")
                _expire(conn, workspace=user["workspace_id"], account=identity.user_id)
                owner = conn.execute(
                    "SELECT workspace_id FROM socialmei.ig_meta_connections WHERE external_account_id=%s AND status='connected'",
                    (identity.user_id,),
                ).fetchone()
                if owner and owner["workspace_id"] != user["workspace_id"]:
                    conflict = True
                else:
                    previous = conn.execute(
                        "UPDATE socialmei.ig_meta_connections SET status='disconnected',encrypted_token=NULL,disconnected_at=NOW(),revision=revision+1 WHERE workspace_id=%s AND status='connected' RETURNING id",
                        (user["workspace_id"],),
                    ).fetchall()
                    for row in previous:
                        _audit(conn, user, "disconnected", row["id"])
                if conflict:
                    # Keep the current connection when the verified account is bound elsewhere.
                    raise UniqueViolation()

                conn.execute(
                    "INSERT INTO socialmei.ig_meta_connections(id,workspace_id,external_account_id,account_type,status,scopes,encrypted_token,token_kind,issued_at,expires_at,created_by) VALUES(%s,%s,%s,%s,'connected',%s,%s,%s,%s,%s,%s)",
                    (
                        connection_id,
                        user["workspace_id"],
                        identity.user_id,
                        identity.account_type,
                        sorted(grant.scopes),
                        encrypted,
                        grant.kind,
                        datetime.fromtimestamp(grant.issued_at, timezone.utc),
                        datetime.fromtimestamp(grant.expires_at, timezone.utc),
                        user["id"],
                    ),
                )
                conn.execute(
                    "UPDATE socialmei.ig_meta_oauth_states SET status='connected' WHERE state_hash=%s",
                    (state_hash,),
                )
                _audit(conn, user, "connected", connection_id)
        except (UniqueViolation, DeadlockDetected, SerializationFailure):
            conflict = True
        if conflict:
            self._failed(user, state_hash)
            raise HTTPException(409, "Conta Instagram indisponível para esta conexão.")
        return {
            "status": "connected",
            "connection_id": str(connection_id),
            "provider": "instagram",
        }

    def status(self, user, session_hash):
        with db() as conn:
            _authorize(conn, user, session_hash, manage=False, lock=False)
            row = conn.execute(
                "SELECT * FROM socialmei.ig_meta_connections WHERE workspace_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
                (user["workspace_id"],),
            ).fetchone()
        if not row:
            return {
                "status": "disconnected",
                "provider": "instagram",
                "credential_available": False,
            }
        available = False
        if row["status"] == "connected":
            try:
                self.vault.open(
                    row["encrypted_token"],
                    TokenBinding(
                        user["workspace_id"], row["id"], row["external_account_id"]
                    ),
                )
                available = True
            except VaultError:
                pass
        status = row["status"]
        if status == "connected" and row["expires_at"] <= datetime.now(timezone.utc):
            status, available = "expired", False
        return {
            "status": status,
            "provider": "instagram",
            "connection_id": str(row["id"]),
            "account_type": row["account_type"],
            "scopes": row["scopes"],
            "expires_at": row["expires_at"].isoformat(),
            "credential_available": available,
            "revision": row["revision"],
        }

    def disconnect(self, user, session_hash):
        with db() as conn:
            _lock(conn, user["workspace_id"])
            _authorize(conn, user, session_hash)
            _expire(conn, workspace=user["workspace_id"])
            _cancel_states(conn, user["workspace_id"])
            rows = conn.execute(
                "UPDATE socialmei.ig_meta_connections SET status='disconnected',encrypted_token=NULL,disconnected_at=NOW(),revision=revision+1 WHERE workspace_id=%s AND status='connected' RETURNING id",
                (user["workspace_id"],),
            ).fetchall()
            for row in rows:
                _audit(conn, user, "disconnected", row["id"])
        return {
            "status": "disconnected",
            "provider": "instagram",
            "provider_revoked": False,
        }

    def rotate_key(self, user, session_hash):
        failed = False
        with db() as conn:
            _lock(conn, user["workspace_id"])
            _authorize(conn, user, session_hash)
            _expire(conn, workspace=user["workspace_id"])
            row = conn.execute(
                "SELECT * FROM socialmei.ig_meta_connections WHERE workspace_id=%s AND status='connected' FOR UPDATE",
                (user["workspace_id"],),
            ).fetchone()
            if not row or row["expires_at"] <= datetime.now(timezone.utc):
                raise HTTPException(409, "Conexão indisponível ou expirada.")
            binding = TokenBinding(
                user["workspace_id"], row["id"], row["external_account_id"]
            )
            sealed = None
            try:
                sealed = self.vault.seal(
                    self.vault.open(row["encrypted_token"], binding), binding
                )
            except VaultError:
                failed = True
            if not failed:
                conn.execute(
                    "UPDATE socialmei.ig_meta_connections SET encrypted_token=%s,revision=revision+1 WHERE workspace_id=%s AND id=%s",
                    (sealed, user["workspace_id"], row["id"]),
                )
                _audit(conn, user, "key_rotated", row["id"])
        if failed:
            raise HTTPException(503, "Credencial segura indisponível.")
        return {"status": "rotated", "provider": "instagram"}


class Callback(Strict):
    state: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    code: str | None = Field(default=None, min_length=1, max_length=16384)
    error: str | None = Field(default=None, pattern=r"^[a-z_]{1,80}$")
    callback_uri: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def exclusive_result(self):
        if (self.code is None) == (self.error is None):
            raise ValueError("Resultado OAuth inválido.")
        return self


def _request_identity(request):
    require_enabled()
    if not (settings.instagram_oauth_isolated_enabled() or settings.instagram_runtime_enabled()):
        raise HTTPException(503, "Integração Instagram ainda não habilitada.")
    return current(), digest(request.cookies.get(COOKIE, ""))


class EmptyInput(Strict):
    pass


@router.post("/oauth/start")
def start(
    payload: EmptyInput,
    request: Request,
    service: InstagramOAuthService = Depends(oauth_service),
):
    user, session_hash = _request_identity(request)
    return service.start(user, session_hash)


@router.post("/oauth/callback")
def callback(
    payload: Callback,
    request: Request,
    service: InstagramOAuthService = Depends(oauth_service),
):
    user, session_hash = _request_identity(request)
    return service.callback(
        user,
        session_hash,
        payload.state,
        payload.code,
        payload.callback_uri,
        payload.error,
    )


@router.get("/status")
def status(request: Request, service: InstagramOAuthService = Depends(oauth_service)):
    user, session_hash = _request_identity(request)
    return service.status(user, session_hash)


@router.post("/connection/disconnect")
def disconnect(
    payload: EmptyInput,
    request: Request,
    service: InstagramOAuthService = Depends(oauth_service),
):
    user, session_hash = _request_identity(request)
    return service.disconnect(user, session_hash)


@router.post("/connection/rotate-key")
def rotate_key(
    payload: EmptyInput,
    request: Request,
    service: InstagramOAuthService = Depends(oauth_service),
):
    user, session_hash = _request_identity(request)
    return service.rotate_key(user, session_hash)


@router.get("/oauth/return", include_in_schema=False)
def browser_callback(request: Request, service: InstagramOAuthService = Depends(oauth_service)):
    from fastapi.responses import RedirectResponse
    from pydantic import ValidationError
    user, session_hash = _request_identity(request)
    query = request.scope.get("state", {}).get("instagram_oauth_query")
    allowed = {"state", "code", "error", "error_reason", "error_description"}
    outcome = "failed"
    try:
        if query is None or not set(query) <= allowed or any(len(query.getlist(k)) != 1 for k in query):
            raise ValueError("Callback inválido.")
        payload = Callback(state=query.get("state"), code=query.get("code"), error=query.get("error"), callback_uri=service.callback_uri)
        result = service.callback(user, session_hash, payload.state, payload.code, payload.callback_uri, payload.error)
        if result.get("status") == "connected":
            outcome = "connected"
    except (HTTPException, ValidationError, ValueError):
        pass
    return RedirectResponse(
        "/frontend/socialmei-app.html#instagram=" + outcome, status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"},
    )
