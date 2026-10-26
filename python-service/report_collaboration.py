"""Owner-managed read-only reporting access for already registered accounts.

No public PostgreSQL user, credential disclosure or invitation email. Each
member chooses an existing workspace using a new server-verified session.
"""
from pydantic import Field, field_validator
from fastapi import APIRouter, HTTPException, Request, Response
from psycopg.rows import dict_row

from account_auth import (
    COOKIE, Strict, current, digest, identity_in, issue_session,
    normalize_email, public_identity, require_enabled, throttle,
)
from database import connect

router = APIRouter(prefix="/api/v1", tags=["read-only report collaborators"])


class ExistingUser(Strict):
    email: str = Field(max_length=255)
    _email = field_validator("email")(normalize_email)


class WorkspaceSelection(Strict):
    workspace_id: int = Field(ge=1, strict=True)


def owner():
    require_enabled()
    user = current()
    if user["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente responsáveis podem autorizar relatórios.")
    return user


@router.get("/reporting/access")
def list_viewers():
    user = owner()
    with connect() as conn:
        conn.row_factory = dict_row
        people = conn.execute(
            "SELECT u.id,u.nome,u.email,m.criado_em "
            "FROM socialmei.workspace_members m JOIN socialmei.users u ON u.id=m.user_id "
            "WHERE m.workspace_id=%s AND m.role='viewer' "
            "ORDER BY m.criado_em,u.id LIMIT 25",
            (user["workspace_id"],),
        ).fetchall()
    return {"items": people}


@router.post("/reporting/access")
def add_viewer(payload: ExistingUser):
    user = owner()
    throttle(payload.email, "report-viewer")
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute(
            "SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE",
            (user["workspace_id"],),
        )
        number = conn.execute(
            "SELECT COUNT(*) AS n FROM socialmei.workspace_members "
            "WHERE workspace_id=%s AND role='viewer'",
            (user["workspace_id"],),
        ).fetchone()["n"]
        candidate = conn.execute(
            "SELECT u.id FROM socialmei.users u "
            "JOIN socialmei.auth_credenciais c ON c.user_id=u.id AND c.ativo "
            "WHERE lower(btrim(u.email))=%s",
            (payload.email,),
        ).fetchone()
        if not candidate:
            raise HTTPException(
                409, "A pessoa precisa criar uma conta SocialMEI antes de acessar relatórios."
            )
        existing = conn.execute(
            "SELECT role FROM socialmei.workspace_members "
            "WHERE workspace_id=%s AND user_id=%s",
            (user["workspace_id"], candidate["id"]),
        ).fetchone()
        if existing:
            return {"granted": existing["role"] == "viewer", "already_member": True}
        if number >= 20:
            raise HTTPException(429, "Limite de 20 visualizadores por negócio.")
        conn.execute(
            "INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) "
            "VALUES(%s,%s,'viewer')",
            (user["workspace_id"], candidate["id"]),
        )
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria(user_id,alvo_user_id,acao) "
            "VALUES(%s,%s,'acesso_relatorio_concedido')",
            (user["id"], candidate["id"]),
        )
    return {"granted": True, "already_member": False}


@router.delete("/reporting/access/{viewer_id}", status_code=204)
def revoke_viewer(viewer_id: int):
    user = owner()
    with connect() as conn:
        row = conn.execute(
            "DELETE FROM socialmei.workspace_members "
            "WHERE workspace_id=%s AND user_id=%s AND role='viewer' RETURNING user_id",
            (user["workspace_id"], viewer_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Visualizador não encontrado.")
        # Auth sessions reference the exact workspace membership by FK cascade.
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria(user_id,alvo_user_id,acao) "
            "VALUES(%s,%s,'acesso_relatorio_revogado')",
            (user["id"], viewer_id),
        )
    return None


@router.get("/auth/workspaces")
def workspaces():
    require_enabled()
    user = current()
    with connect() as conn:
        conn.row_factory = dict_row
        records = conn.execute(
            "SELECT w.id,w.nome,m.role "
            "FROM socialmei.workspace_members m JOIN socialmei.workspaces w "
            "ON w.id=m.workspace_id "
            "JOIN socialmei.auth_credenciais c ON c.user_id=m.user_id AND c.ativo "
            "WHERE m.user_id=%s ORDER BY m.criado_em,w.id LIMIT 50",
            (user["id"],),
        ).fetchall()
    return {"active_workspace_id": user["workspace_id"], "items": records}


@router.post("/auth/workspaces/switch")
def switch(payload: WorkspaceSelection, request: Request, response: Response):
    require_enabled()
    user = current()
    token = request.cookies.get(COOKIE, "")
    if payload.workspace_id == user["workspace_id"]:
        return public_identity(user, token)
    with connect() as conn:
        conn.row_factory = dict_row
        target = conn.execute(
            "SELECT 1 FROM socialmei.workspace_members m "
            "JOIN socialmei.auth_credenciais c ON c.user_id=m.user_id AND c.ativo "
            "WHERE m.workspace_id=%s AND m.user_id=%s FOR SHARE OF m,c",
            (payload.workspace_id, user["id"]),
        ).fetchone()
        if not target:
            raise HTTPException(403, "Você não possui acesso a este negócio.")
        # The current HttpOnly cookie's session is revoked only after the new
        # workspace and role have been validated.
        revoked = conn.execute(
            "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() "
            "WHERE token_hash=%s AND user_id=%s AND workspace_id=%s "
            "AND revogada_em IS NULL RETURNING user_id",
            (digest(token), user["id"], user["workspace_id"]),
        ).fetchone()
        if not revoked:
            raise HTTPException(401, "Sessão expirada. Entre novamente.")
        new_token = issue_session(conn, user["id"], payload.workspace_id, response, False)
        data = identity_in(conn, user["id"], payload.workspace_id)
        if not data:
            raise HTTPException(403, "Negócio indisponível.")
        return public_identity(data, new_token)
