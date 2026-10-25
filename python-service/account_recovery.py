"""Opt-in email recovery. No account discovery, automatic login or provider calls by default."""

import secrets
import smtplib
import ssl

import psycopg
from email.message import EmailMessage

from fastapi import APIRouter, HTTPException, Request, Response
from uuid import uuid4
from pydantic import Field, field_validator
import settings
from database import connect
from account_auth import (
    Strict,
    normalize_email,
    validate_new_password,
    require_enabled,
    digest,
    hash_password,
    throttle,
    COOKIE,
)

router = APIRouter(prefix="/api/v1", tags=["accounts"])


class RecoveryRequest(Strict):
    email: str = Field(max_length=255)
    _email = field_validator("email")(normalize_email)


class RecoveryConfirm(Strict):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    nova: str = Field(min_length=8, max_length=128)
    _password = field_validator("nova")(validate_new_password)


def configured():
    require_enabled()
    try:
        config = settings.recovery_smtp_configuration()
    except (ValueError, TypeError):
        raise HTTPException(
            503,
            "Recuperação por e-mail indisponível neste ambiente. Procure o administrador.",
        ) from None
    try:
        with connect() as conn:
            if not all(
                conn.execute(
                    "SELECT to_regclass('socialmei.auth_recuperacoes'),to_regclass('socialmei.auth_recuperacao_envios')"
                ).fetchone()
            ):
                raise HTTPException(503, "Recuperação por e-mail ainda não instalada.")
    except psycopg.Error:
        raise HTTPException(503, "Recuperação temporariamente indisponível.") from None
    return config


def send_recovery_mail(address, token, config):
    message = EmailMessage()
    message["From"] = config["from"]
    message["To"] = address
    message["Subject"] = "SocialMEI — recuperar acesso"
    message.set_content(
        "Recebemos um pedido para redefinir sua senha no SocialMEI.\n\n"
        "No site em que você solicitou a recuperação, cole este código:\n\n"
        + token
        + "\n\nVálido por 15 minutos e uma única utilização. "
        "Se não foi você, ignore este e-mail e não compartilhe o código.\n"
    )
    context = ssl.create_default_context()
    if config["port"] == 465:
        server = smtplib.SMTP_SSL(config["host"], 465, timeout=10, context=context)
    else:
        server = smtplib.SMTP(config["host"], 587, timeout=10)
    with server:
        if config["port"] == 587:
            server.starttls(context=context)
        server.login(config["user"], config["password"])
        server.send_message(message)


def queue_recovery(address):
    with connect() as conn:
        row = conn.execute(
            "SELECT c.user_id FROM socialmei.auth_credenciais c JOIN socialmei.users u ON u.id=c.user_id WHERE LOWER(BTRIM(u.email))=%s AND c.ativo FOR UPDATE OF c",
            (address,),
        ).fetchone()
        if not row:
            return
        conn.execute(
            "UPDATE socialmei.auth_recuperacoes SET usado_em=NOW() WHERE user_id=%s AND usado_em IS NULL",
            (row[0],),
        )
        conn.execute(
            "INSERT INTO socialmei.auth_recuperacao_envios(user_id,generation,status) VALUES(%s,%s,'pending') ON CONFLICT(user_id) DO UPDATE SET generation=EXCLUDED.generation,status='pending',queued_at=NOW(),started_at=NULL,finished_at=NULL",
            (row[0], uuid4()),
        )


def process_one():
    """Explicit worker invocation. Commit claim before SMTP; never retry uncertain sends."""
    config = configured()
    with connect() as conn:
        # No credential locks here: reclaim only abandoned delivery state.
        conn.execute(
            "UPDATE socialmei.auth_recuperacao_envios SET status='uncertain',finished_at=NOW() WHERE status='processing' AND started_at<NOW()-INTERVAL '2 minutes'"
        )
        candidate = conn.execute(
            "SELECT user_id FROM socialmei.auth_recuperacao_envios WHERE status='pending' ORDER BY queued_at,user_id LIMIT 1"
        ).fetchone()
    if not candidate:
        return False
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        # Same lock order as requests/password changes and confirmations.
        account = conn.execute(
            "SELECT c.user_id,c.senha_alterada_em,u.email,c.ativo FROM socialmei.auth_credenciais c JOIN socialmei.users u ON u.id=c.user_id WHERE c.user_id=%s FOR UPDATE OF c",
            (candidate[0],),
        ).fetchone()
        job = conn.execute(
            "SELECT generation,queued_at<NOW()-INTERVAL '15 minutes' FROM socialmei.auth_recuperacao_envios WHERE user_id=%s AND status='pending' FOR UPDATE",
            (candidate[0],),
        ).fetchone()
        if not job:
            return False
        if not account or not account[3] or job[1]:
            conn.execute(
                "UPDATE socialmei.auth_recuperacao_envios SET status='expired',finished_at=NOW() WHERE user_id=%s",
                (candidate[0],),
            )
            return True
        conn.execute(
            "INSERT INTO socialmei.auth_recuperacoes(user_id,token_hash,senha_alterada_em,expira_em) VALUES(%s,%s,%s,NOW()+INTERVAL '15 minutes') ON CONFLICT(user_id) DO UPDATE SET token_hash=EXCLUDED.token_hash,senha_alterada_em=EXCLUDED.senha_alterada_em,expira_em=EXCLUDED.expira_em,usado_em=NULL",
            (account[0], digest(token), account[1]),
        )
        conn.execute(
            "UPDATE socialmei.auth_recuperacao_envios SET status='processing',started_at=NOW() WHERE user_id=%s",
            (account[0],),
        )
    status = "sent"
    try:
        send_recovery_mail(account[2], token, config)
    except Exception:
        # SMTP might have accepted before the connection failed. No automatic retry.
        status = "uncertain"
    with connect() as conn:
        if status == "uncertain":
            conn.execute(
                "UPDATE socialmei.auth_recuperacoes SET usado_em=NOW() WHERE token_hash=%s",
                (digest(token),),
            )
        conn.execute(
            "UPDATE socialmei.auth_recuperacao_envios SET status=%s,finished_at=NOW() WHERE user_id=%s AND generation=%s AND status='processing'",
            (status, account[0], job[0]),
        )
    return True


@router.post("/auth/recovery/request", status_code=202)
def request_recovery(payload: RecoveryRequest, request: Request):
    configured()
    throttle(payload.email, "recovery-email")
    throttle(request.client.host if request.client else "unknown", "recovery-peer")
    queue_recovery(payload.email)
    return {
        "message": "Se houver uma conta ativa com esse e-mail, enviaremos um código. Confira também o spam. O envio pode demorar; se não chegar, tente novamente mais tarde."
    }


@router.post("/auth/recovery/confirm", status_code=204)
def confirm_recovery(payload: RecoveryConfirm, request: Request, response: Response):
    configured()
    throttle(request.client.host if request.client else "unknown", "recovery-confirm")
    with connect() as conn:
        # Same lock order as password changes: credential, then recovery row.
        row = conn.execute(
            "SELECT c.user_id FROM socialmei.auth_credenciais c JOIN socialmei.auth_recuperacoes r ON r.user_id=c.user_id WHERE r.token_hash=%s FOR UPDATE OF c",
            (digest(payload.token),),
        ).fetchone()
        valid = (
            row
            and conn.execute(
                "SELECT 1 FROM socialmei.auth_recuperacoes r JOIN socialmei.auth_credenciais c ON c.user_id=r.user_id WHERE r.user_id=%s AND r.token_hash=%s AND r.usado_em IS NULL AND r.expira_em>NOW() AND c.ativo AND c.senha_alterada_em=r.senha_alterada_em FOR UPDATE OF r",
                (row[0], digest(payload.token)),
            ).fetchone()
        )
        if not valid:
            raise HTTPException(
                400, "Código inválido, expirado ou já utilizado. Solicite outro."
            )
        conn.execute(
            "UPDATE socialmei.auth_credenciais SET senha_hash=%s,senha_alterada_em=NOW() WHERE user_id=%s",
            (hash_password(payload.nova), row[0]),
        )
        conn.execute(
            "UPDATE socialmei.auth_recuperacoes SET usado_em=NOW() WHERE user_id=%s",
            (row[0],),
        )
        conn.execute(
            "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE user_id=%s AND revogada_em IS NULL",
            (row[0],),
        )
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'senha_recuperada')",
            (row[0],),
        )
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
