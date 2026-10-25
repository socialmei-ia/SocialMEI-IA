"""Own-account session inventory. No IP, user-agent or bearer hashes exposed."""

from uuid import UUID

from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import Field
from account_auth import (
    current,
    require_enabled,
    Strict,
    COOKIE,
    digest,
    verify_password,
    throttle,
)
from database import connect

router = APIRouter(prefix="/api/v1/auth/sessions", tags=["accounts"])


class ConfirmPassword(Strict):
    atual: str = Field(min_length=1, max_length=128)


def identity():
    require_enabled()
    return current()


@router.get("")
def sessions(request: Request):
    user = identity()
    with connect() as conn:
        rows = conn.execute(
            "SELECT public_id,criada_em,expira_em,token_hash=%s AS is_current FROM socialmei.auth_sessoes WHERE user_id=%s AND revogada_em IS NULL AND expira_em>NOW() ORDER BY is_current DESC,criada_em DESC,public_id LIMIT 100",
            (digest(request.cookies[COOKIE]), user["id"]),
        ).fetchall()
    return {
        "sessions": [
            {
                "id": str(row[0]),
                "created_at": row[1],
                "expires_at": row[2],
                "current": row[3],
            }
            for row in rows
        ]
    }


@router.post("/revoke-others", status_code=204)
def revoke_others(payload: ConfirmPassword, request: Request):
    user = identity()
    throttle(user["email"], "revoke-sessions")
    with connect() as conn:
        row = conn.execute(
            "SELECT senha_hash FROM socialmei.auth_credenciais WHERE user_id=%s AND ativo FOR UPDATE",
            (user["id"],),
        ).fetchone()
        if not row or not verify_password(payload.atual, row[0]):
            raise HTTPException(400, "Confira sua senha atual.")
        conn.execute(
            "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE user_id=%s AND token_hash<>%s AND revogada_em IS NULL",
            (user["id"], digest(request.cookies[COOKIE])),
        )
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'outras_sessoes_revogadas')",
            (user["id"],),
        )


@router.post("/{session_id}/revoke", status_code=204)
def revoke(session_id: UUID, request: Request, response: Response):
    user = identity()
    with connect() as conn:
        row = conn.execute(
            "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE public_id=%s AND user_id=%s AND revogada_em IS NULL AND expira_em>NOW() RETURNING token_hash=%s",
            (session_id, user["id"], digest(request.cookies[COOKIE])),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Sessão não encontrada.")
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'sessao_revogada')",
            (user["id"],),
        )
    if row[0]:
        response.delete_cookie(
            COOKIE, path="/", secure=True, httponly=True, samesite="lax"
        )
