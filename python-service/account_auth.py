"""Opt-in account authentication. Opaque sessions; no browser-issued workspace."""

import hashlib
import hmac
import re
import secrets
import threading
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from auth_context import principal
from fastapi import APIRouter, HTTPException, Request, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from database import connect, shared_data_enabled
from contact_validation import validate_phone
import settings

COOKIE = "__Host-socialmei-session"
HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
HASH_LIMIT = threading.BoundedSemaphore(2)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
TECHNICAL = {
    "/api/v1/integracoes/" + name
    for name in ["resumo", "clientes", "produtos", "vendas", "financeiro"]
}
PUBLIC = {"/api/v1/auth/login", "/api/v1/auth/register"}
router = APIRouter(prefix="/api/v1", tags=["accounts"])


def enabled():
    return settings.authentication_mode() != "disabled"


def origin():
    value = settings.authentication_origin()
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # Validate malformed ports before accepting the origin.
    except ValueError:
        raise HTTPException(503, "Autenticação não configurada.") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(503, "Autenticação não configurada.")
    return value


def require_enabled():
    if not enabled() or not shared_data_enabled():
        raise HTTPException(503, "Autenticação não ativada neste ambiente.")
    if settings.authentication_mode() != "enabled":
        raise HTTPException(503, "Autenticação não configurada.")
    origin()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf(token):
    return hmac.new(token.encode(), b"socialmei-csrf-v1", hashlib.sha256).hexdigest()


def normalize_email(value):
    value = value.strip().lower()
    if len(value) > 255 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("Informe um e-mail válido.")
    return value


def hash_password(value):
    if not 12 <= len(value) <= 128:
        raise ValueError("Use uma senha de 12 a 128 caracteres.")
    if not HASH_LIMIT.acquire(timeout=2):
        raise HTTPException(503, "Aguarde e tente novamente.")
    try:
        return HASHER.hash(value)
    finally:
        HASH_LIMIT.release()


def verify_password(value, hashed):
    if not HASH_LIMIT.acquire(timeout=2):
        raise HTTPException(503, "Aguarde e tente novamente.")
    try:
        return HASHER.verify(hashed, value)
    except (VerificationError, InvalidHashError):
        return False
    finally:
        HASH_LIMIT.release()


IDENTITY = "u.id, u.nome, u.email, u.telefone, c.administrador_plataforma, m.role, w.id AS workspace_id, w.slug AS workspace_slug, w.nome AS nome_negocio, w.configuracao"


def session_identity(token):
    if not re.fullmatch(r"[A-Za-z0-9_-]{64}", token or ""):
        return None
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {IDENTITY} FROM socialmei.auth_sessoes s JOIN socialmei.users u ON u.id=s.user_id JOIN socialmei.auth_credenciais c ON c.user_id=u.id JOIN socialmei.workspace_members m ON m.user_id=u.id AND m.workspace_id=s.workspace_id JOIN socialmei.workspaces w ON w.id=m.workspace_id WHERE s.token_hash=%s AND s.revogada_em IS NULL AND s.expira_em>NOW() AND c.ativo",
            (digest(token),),
        )
        return cur.fetchone()


def public_identity(user, token):
    return {
        "usuario": {
            key: user[key]
            for key in ["id", "nome", "email", "telefone", "administrador_plataforma"]
        },
        "negocio": {
            "id": user["workspace_id"],
            "slug": user["workspace_slug"],
            "nome": user["nome_negocio"],
            "configuracao": user["configuracao"],
        },
        "papel": user["role"],
        "csrf_token": csrf(token),
    }


def current():
    user = principal.get()
    if not user:
        raise HTTPException(401, "Entre na sua conta.")
    return user


def admin():
    user = current()
    if not user["administrador_plataforma"]:
        raise HTTPException(403, "Acesso reservado ao administrador do projeto.")
    return user


class AccountMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if (
            not enabled()
            or not path.startswith("/api/v1/")
            or (request.method == "GET" and path in TECHNICAL)
        ):
            return await call_next(request)
        context_token = None
        try:
            require_enabled()
            if path == "/api/v1/auth/registration" and request.method == "GET":
                response = await call_next(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            if (
                request.method not in {"GET", "HEAD", "OPTIONS"}
                and request.headers.get("origin") != origin()
            ):
                raise HTTPException(403, "Origem não permitida.")
            if path in PUBLIC and request.method == "POST":
                if (
                    request.headers.get("content-type", "").split(";", 1)[0].lower()
                    != "application/json"
                    or request.headers.get("x-socialmei-client") != "browser"
                ):
                    raise HTTPException(403, "Solicitação de autenticação inválida.")
                response = await call_next(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            token = request.cookies.get(COOKIE, "")
            user = await run_in_threadpool(session_identity, token)
            if not user:
                raise HTTPException(401, "Sessão ausente ou expirada. Entre novamente.")
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                if not hmac.compare_digest(
                    request.headers.get("x-socialmei-csrf", "").encode(),
                    csrf(token).encode(),
                ):
                    raise HTTPException(403, "Confira a sessão antes de salvar.")
                if user["role"] == "viewer" and not path.startswith("/api/v1/auth/"):
                    raise HTTPException(403, "Este acesso permite somente leitura.")
            if (
                path.startswith("/api/v1/transferencias")
                and not user["administrador_plataforma"]
            ):
                raise HTTPException(
                    403, "Transferência reservada ao administrador do projeto."
                )
            context_token = principal.set(user)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        except HTTPException as error:
            return JSONResponse(
                {"detail": error.detail},
                status_code=error.status_code,
                headers={"Cache-Control": "no-store", **(error.headers or {})},
            )
        except psycopg.Error:
            return JSONResponse(
                {"detail": "Autenticação temporariamente indisponível."},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        finally:
            if context_token is not None:
                principal.reset(context_token)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Strict):
    email: str = Field(max_length=255)
    senha: str = Field(min_length=1, max_length=128)
    lembrar: bool = False

    _email = field_validator("email")(normalize_email)


class Register(Login):
    _phone = field_validator("telefone")(validate_phone)

    nome: str = Field(min_length=1, max_length=160)
    telefone: str = Field(default="", max_length=40)
    senha: str = Field(min_length=12, max_length=128)
    convite: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{64}$")

    @field_validator("nome")
    @classmethod
    def name(cls, value):
        if not value.strip():
            raise ValueError("Informe seu nome.")
        return value.strip()


class Profile(Strict):
    _phone = field_validator("telefone")(validate_phone)

    nome: str | None = Field(default=None, min_length=1, max_length=160)
    telefone: str | None = Field(default=None, max_length=40)
    nome_negocio: str | None = Field(default=None, min_length=1, max_length=160)
    configuracao_negocio: dict | None = None

    @field_validator("configuracao_negocio")
    @classmethod
    def business_contact(cls, value):
        if value is not None and "telefone" in value:
            phone = value["telefone"]
            if phone is not None and not isinstance(phone, str):
                raise ValueError("Informe o telefone como texto.")
            validate_phone(phone)
        return value


class Password(Strict):
    atual: str = Field(min_length=1, max_length=128)
    nova: str = Field(min_length=12, max_length=128)


class Invite(Strict):
    email: str = Field(max_length=255)
    _email = field_validator("email")(normalize_email)


def throttle(address, action):
    # Database counters survive process/container restart. No password or email in keys.
    with connect() as conn:
        for key, seconds, maximum in [
            ("global:" + action, 60, 30),
            (action + ":" + address, 900, 10),
        ]:
            count = conn.execute(
                "INSERT INTO socialmei.auth_limites (chave) VALUES (%s) ON CONFLICT (chave) DO UPDATE SET tentativas=CASE WHEN auth_limites.inicio<NOW()-make_interval(secs=>%s) THEN 1 ELSE auth_limites.tentativas+1 END, inicio=CASE WHEN auth_limites.inicio<NOW()-make_interval(secs=>%s) THEN NOW() ELSE auth_limites.inicio END RETURNING tentativas",
                (digest(key), seconds, seconds),
            ).fetchone()[0]
            if count > maximum:
                conn.commit()
                raise HTTPException(
                    429,
                    "Aguarde antes de tentar novamente.",
                    headers={"Retry-After": str(seconds)},
                )


def issue_session(conn, user_id, workspace_id, response, remember):
    token = secrets.token_urlsafe(48)
    seconds = 7 * 86400 if remember else 86400
    conn.execute(
        "INSERT INTO socialmei.auth_sessoes (token_hash,user_id,workspace_id,expira_em) VALUES (%s,%s,%s,NOW()+make_interval(secs=>%s))",
        (digest(token), user_id, workspace_id, seconds),
    )
    response.set_cookie(
        COOKIE,
        token,
        max_age=seconds if remember else None,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return token


def identity_in(conn, user_id, workspace_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {IDENTITY} FROM socialmei.users u JOIN socialmei.auth_credenciais c ON c.user_id=u.id JOIN socialmei.workspace_members m ON m.user_id=u.id JOIN socialmei.workspaces w ON w.id=m.workspace_id WHERE u.id=%s AND w.id=%s AND c.ativo",
            (user_id, workspace_id),
        )
        return cur.fetchone()


@router.post("/auth/login")
def login(payload: Login, response: Response):
    require_enabled()
    throttle(payload.email, "login")
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT u.id, c.senha_hash, c.ativo FROM socialmei.users u JOIN socialmei.auth_credenciais c ON c.user_id=u.id WHERE LOWER(BTRIM(u.email))=%s FOR UPDATE OF c",
            (payload.email,),
        )
        user = cur.fetchone()
        valid = verify_password(
            payload.senha, user["senha_hash"] if user else DUMMY_HASH
        )
        if not user or not user["ativo"] or not valid:
            raise HTTPException(401, "E-mail ou senha inválidos.")
        cur.execute(
            "SELECT workspace_id FROM socialmei.workspace_members WHERE user_id=%s ORDER BY criado_em,workspace_id LIMIT 1",
            (user["id"],),
        )
        membership = cur.fetchone()
        if not membership:
            raise HTTPException(401, "E-mail ou senha inválidos.")
        token = issue_session(
            conn, user["id"], membership["workspace_id"], response, payload.lembrar
        )
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria (user_id,acao) VALUES (%s,'login')",
            (user["id"],),
        )
        result = public_identity(
            identity_in(conn, user["id"], membership["workspace_id"]), token
        )
    return result


@router.get("/auth/registration")
def registration_policy():
    require_enabled()
    return {"mode": settings.registration_mode()}


@router.post("/auth/register", status_code=201)
def register(payload: Register, response: Response):
    require_enabled()
    throttle(payload.email, "register")
    use_invite = settings.registration_mode() != "open" or payload.convite is not None
    if use_invite and not payload.convite:
        raise HTTPException(400, "Informe o convite recebido do administrador.")
    try:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            if use_invite:
                cur.execute(
                    "SELECT token_hash FROM socialmei.auth_convites WHERE token_hash=%s AND email=%s AND usado_em IS NULL AND revogado_em IS NULL AND expira_em>NOW() FOR UPDATE",
                    (digest(payload.convite), payload.email),
                )
                if not cur.fetchone():
                    raise HTTPException(
                        400, "Cadastro não concluído. Confira seu convite e os dados."
                    )
            hashed = hash_password(payload.senha)
            user_id = conn.execute(
                "INSERT INTO socialmei.users (email,nome,telefone) VALUES (%s,%s,%s) RETURNING id",
                (payload.email, payload.nome, payload.telefone),
            ).fetchone()[0]
            workspace_id = conn.execute(
                "INSERT INTO socialmei.workspaces (slug,nome) VALUES (%s,%s) RETURNING id",
                ("mei-" + uuid4().hex, ("Negócio de " + payload.nome)[:160]),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO socialmei.auth_credenciais (user_id,senha_hash) VALUES (%s,%s)",
                (user_id, hashed),
            )
            conn.execute(
                "INSERT INTO socialmei.workspace_members (workspace_id,user_id,role) VALUES (%s,%s,'owner')",
                (workspace_id, user_id),
            )
            if use_invite:
                conn.execute(
                    "UPDATE socialmei.auth_convites SET usado_em=NOW(),user_id=%s WHERE token_hash=%s",
                    (user_id, digest(payload.convite)),
                )
            conn.execute(
                "INSERT INTO socialmei.auth_auditoria (user_id,acao) VALUES (%s,'cadastro')",
                (user_id,),
            )
            token = issue_session(
                conn, user_id, workspace_id, response, payload.lembrar
            )
            return public_identity(identity_in(conn, user_id, workspace_id), token)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            400,
            "Cadastro não concluído. Confira os dados ou entre na sua conta existente.",
        ) from None


@router.get("/auth/me")
def me(request: Request):
    require_enabled()
    return public_identity(current(), request.cookies[COOKIE])


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response):
    require_enabled()
    with connect() as conn:
        conn.execute(
            "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE token_hash=%s",
            (digest(request.cookies[COOKIE]),),
        )
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")


@router.post("/auth/password", status_code=204)
def password(payload: Password, response: Response):
    user = current()
    throttle(user["email"], "password")
    with connect() as conn:
        row = conn.execute(
            "SELECT senha_hash FROM socialmei.auth_credenciais WHERE user_id=%s AND ativo FOR UPDATE",
            (user["id"],),
        ).fetchone()
        if not row or not verify_password(payload.atual, row[0]):
            raise HTTPException(400, "Confira sua senha atual.")
        conn.execute(
            "UPDATE socialmei.auth_credenciais SET senha_hash=%s,senha_alterada_em=NOW() WHERE user_id=%s",
            (hash_password(payload.nova), user["id"]),
        )
        conn.execute(
            "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE user_id=%s AND revogada_em IS NULL",
            (user["id"],),
        )
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria (user_id,acao) VALUES (%s,'senha_alterada')",
            (user["id"],),
        )
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")


@router.patch("/auth/profile")
def profile(payload: Profile, request: Request):
    user = current()
    if (
        payload.nome_negocio is not None or payload.configuracao_negocio is not None
    ) and user["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente o responsável pode alterar o negócio.")
    import json

    business = payload.configuracao_negocio
    if business is not None:
        allowed = {"cnpj", "telefone", "horario", "pix", "logo"}
        if (
            set(business) - allowed
            or any(not isinstance(v, str) for v in business.values())
            or len(json.dumps(business).encode()) > 1500000
        ):
            raise HTTPException(422, "Confira os campos do negócio.")
        for key, value in business.items():
            if key != "logo" and len(value) > 160:
                raise HTTPException(422, "Confira os limites do negócio.")
            if (
                key == "logo"
                and value
                and not re.fullmatch(
                    r"data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+", value
                )
            ):
                raise HTTPException(422, "Logo inválida.")
    if any(
        v is not None and not v.strip() for v in [payload.nome, payload.nome_negocio]
    ):
        raise HTTPException(422, "Informe um nome.")
    with connect() as conn:
        if payload.nome is not None:
            conn.execute(
                "UPDATE socialmei.users SET nome=%s WHERE id=%s",
                (payload.nome.strip(), user["id"]),
            )
        if payload.telefone is not None:
            conn.execute(
                "UPDATE socialmei.users SET telefone=%s WHERE id=%s",
                (payload.telefone, user["id"]),
            )
        if payload.nome_negocio is not None:
            conn.execute(
                "UPDATE socialmei.workspaces SET nome=%s,atualizado_em=NOW() WHERE id=%s",
                (payload.nome_negocio.strip(), user["workspace_id"]),
            )
        if business is not None:
            conn.execute(
                "UPDATE socialmei.workspaces SET configuracao=configuracao || %s::jsonb,atualizado_em=NOW() WHERE id=%s",
                (json.dumps(business), user["workspace_id"]),
            )
        return public_identity(
            identity_in(conn, user["id"], user["workspace_id"]), request.cookies[COOKIE]
        )


def create_invite(conn, address, actor):
    address = normalize_email(address)
    row = conn.execute(
        "SELECT 1 FROM socialmei.auth_credenciais WHERE user_id=%s AND ativo AND administrador_plataforma FOR UPDATE",
        (actor,),
    ).fetchone()
    if not row:
        raise HTTPException(403, "Administrador indisponível.")
    if conn.execute(
        "SELECT 1 FROM socialmei.users WHERE LOWER(BTRIM(email))=%s", (address,)
    ).fetchone():
        raise HTTPException(409, "E-mail já cadastrado. Use recuperação de acesso.")
    conn.execute(
        "UPDATE socialmei.auth_convites SET revogado_em=NOW() WHERE email=%s AND usado_em IS NULL AND revogado_em IS NULL",
        (address,),
    )
    token = secrets.token_urlsafe(48)
    conn.execute(
        "INSERT INTO socialmei.auth_convites (token_hash,email,criado_por,expira_em) VALUES (%s,%s,%s,NOW()+INTERVAL '3 days')",
        (digest(token), address, actor),
    )
    conn.execute(
        "INSERT INTO socialmei.auth_auditoria (user_id,acao) VALUES (%s,'convite_criado')",
        (actor,),
    )
    return token


@router.get("/admin/users")
def users():
    admin()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT u.id,u.nome,u.email,c.ativo,c.administrador_plataforma,u.criado_em FROM socialmei.users u JOIN socialmei.auth_credenciais c ON c.user_id=u.id ORDER BY u.id LIMIT 500"
        )
        return cur.fetchall()


@router.post("/admin/invites", status_code=201)
def invite(payload: Invite):
    actor = admin()
    with connect() as conn:
        return {
            "email": payload.email,
            "convite": create_invite(conn, payload.email, actor["id"]),
            "validade_dias": 3,
        }


@router.post("/admin/users/{user_id}/disable", status_code=204)
def disable(user_id: int):
    actor = admin()
    with connect() as conn:
        # All admin changes serialize to prevent last-admin races.
        conn.execute("SELECT pg_advisory_xact_lock(72426002)")
        row = conn.execute(
            "SELECT administrador_plataforma FROM socialmei.auth_credenciais WHERE user_id=%s FOR UPDATE",
            (user_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Conta não encontrada.")
        if row[0]:
            raise HTTPException(
                409, "Administradores são gerenciados pelo procedimento privado."
            )
        conn.execute(
            "UPDATE socialmei.auth_credenciais SET ativo=false WHERE user_id=%s",
            (user_id,),
        )
        conn.execute(
            "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE user_id=%s AND revogada_em IS NULL",
            (user_id,),
        )
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria (user_id,alvo_user_id,acao) VALUES (%s,%s,'conta_desativada')",
            (actor["id"], user_id),
        )
