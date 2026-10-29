"""Read-only catalog lookup for a provisioned WAHA/n8n session.

No new webhook, bot, WhatsApp sender or automatic replies. The n8n workflow
may call this GET endpoint with a per-channel bearer credential issued once
by an authenticated owner. The URL never supplies a workspace identifier.
"""
import hashlib
import os
import re
import secrets
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from account_auth import current, require_enabled
from database import connect

router = APIRouter(prefix="/api/v1", tags=["WAHA catalog menu"])
_INSTANCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{64}\Z")
MENU = (
    "1 - Ver produtos",
    "2 - Consultar preço e disponibilidade",
    "3 - Conhecer serviços",
    "4 - Solicitar orçamento",
    "5 - Falar com atendente",
)


class ChannelAccess(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    channel_id: int = Field(ge=1)


def enabled():
    return os.getenv("SOCIALMEI_WA_CATALOG_ENABLED", "false").strip().lower() == "true"


def require_owner():
    require_enabled()
    user = current()
    if user["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente responsáveis podem vincular o WhatsApp.")
    return user


def issue_secret():
    return secrets.token_urlsafe(48)


def token_digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def auth_channel(instance, authorization):
    if not enabled():
        raise HTTPException(503, "Consulta WhatsApp ainda não habilitada.")
    if not _INSTANCE.fullmatch(instance):
        raise HTTPException(422, "Instância inválida.")
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not _TOKEN.fullmatch(supplied):
        raise HTTPException(401, "Credencial técnica inválida.")
    with connect() as conn:
        row = conn.execute(
            "SELECT a.workspace_id,a.channel_id FROM socialmei.wa_catalog_access a "
            "JOIN socialmei.crm_canais c "
            "ON c.workspace_id=a.workspace_id AND c.id=a.channel_id "
            "WHERE a.token_hash=%s AND a.instance=%s AND a.enabled "
            "AND c.ativo AND c.instancia=a.instance AND c.provedor='waha'",
            (token_digest(supplied), instance),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Credencial técnica inválida.")
    return row[0]


@router.post("/whatsapp/catalog/access")
def provision(data: ChannelAccess):
    user = require_owner()
    token = issue_secret()
    with connect() as conn:
        conn.row_factory = dict_row
        channel = conn.execute(
            "SELECT id,instancia FROM socialmei.crm_canais "
            "WHERE workspace_id=%s AND id=%s AND ativo AND provedor='waha' FOR UPDATE",
            (user["workspace_id"], data.channel_id),
        ).fetchone()
        if not channel:
            raise HTTPException(404, "Canal WAHA ativo não encontrado neste negócio.")
        conn.execute(
            "INSERT INTO socialmei.wa_catalog_access "
            "(workspace_id,channel_id,instance,token_hash,issued_by) "
            "VALUES(%s,%s,%s,%s,%s) "
            "ON CONFLICT(workspace_id,channel_id) DO UPDATE SET "
            "instance=EXCLUDED.instance,token_hash=EXCLUDED.token_hash,"
            "enabled=TRUE,issued_by=EXCLUDED.issued_by,issued_at=NOW()",
            (user["workspace_id"], data.channel_id,
             channel["instancia"], token_digest(token), user["id"]),
        )
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'whatsapp_catalog_rotated')", (user['id'],))
    # One-time bearer: display only once and save it in the n8n credentials vault.
    return {"instance": channel["instancia"], "token_once": token,
            "note": "Guarde este token apenas nas credenciais privadas do n8n."}


@router.get("/whatsapp/catalog/access")
def access_status():
    user = require_owner()
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT c.id AS channel_id,c.instancia AS instance,c.nome AS name,c.ativo AS active,"
            "c.envio_habilitado AS sending_enabled,c.estado_provedor AS provider_state,"
            "c.verificado_em AS verified_at,COALESCE(a.enabled,false) AS enabled,"
            "(a.channel_id IS NOT NULL) AS credential_configured,a.issued_at "
            "FROM socialmei.crm_canais c LEFT JOIN socialmei.wa_catalog_access a "
            "ON a.workspace_id=c.workspace_id AND a.channel_id=c.id "
            "WHERE c.workspace_id=%s AND c.provedor='waha' ORDER BY c.id LIMIT 100",
            (user["workspace_id"],),
        ).fetchall()
    return {"enabled": enabled(), "channels": rows}


@router.delete("/whatsapp/catalog/access/{channel_id}", status_code=204)
def revoke(channel_id: int):
    user = require_owner()
    with connect() as conn:
        row = conn.execute(
            "DELETE FROM socialmei.wa_catalog_access "
            "WHERE workspace_id=%s AND channel_id=%s RETURNING channel_id",
            (user["workspace_id"], channel_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Canal não encontrado.")
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'whatsapp_catalog_revoked')", (user['id'],))
    return None


def product_view(row):
    stock = row["estoque"]
    # New catalog items may start with stock=0 before inventory is verified.
    # Never tell a WhatsApp customer that the item is sold out from this default.
    available = (
        "servico_sem_estoque"
        if row["tipo"] == "Serviço"
        else "em_estoque" if stock is not None and stock > 0 else "nao_confirmada"
    )
    return {
        "nome": row["nome"], "tipo": row["tipo"], "preco": str(row["preco"]),
        "estoque": stock if row["tipo"] == "Produto" else None,
        "disponibilidade": available,
    }


def menu_action(choice):
    return {
        "0": "menu",
        "1": "products",
        "2": "availability",
        "3": "services",
        "4": "quote_handoff",
        "5": "human_handoff",
    }[choice]


@router.get("/integracoes/whatsapp/menu")
def menu(
    response: Response,
    instancia: str = Query(min_length=1, max_length=80),
    opcao: Literal["0", "1", "2", "3", "4", "5"] = Query("0"),
    produto: str = Query("", max_length=160),
    authorization: str | None = Header(default=None),
):
    workspace = auth_channel(instancia, authorization)
    action = menu_action(opcao)
    response.headers["Cache-Control"] = "no-store"
    if action == "menu":
        return {"action": action, "options": list(MENU), "items": []}
    if action.endswith("_handoff"):
        return {
            "action": action, "items": [],
            "message": "Um atendente precisa confirmar os detalhes do pedido.",
        }
    query = produto.strip()
    if action == "availability" and len(query) < 2:
        return {
            "action": "ask_product", "items": [],
            "message": "Qual produto deseja consultar? Informe o nome.",
        }
    if "\x00" in query:
        raise HTTPException(422, "Consulta inválida.")
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout='3000ms'")
        clauses = ["workspace_id=%s", "status='Ativo'"]
        params = [workspace]
        if action in {"products", "availability"}:
            clauses.append("tipo='Produto'")
        if action == "services":
            clauses.append("tipo='Serviço'")
        if query:
            clauses.append("strpos(lower(nome),lower(%s))>0")
            params.append(query)
        sql = (
            "SELECT nome,tipo,preco,estoque FROM socialmei.crm_produtos "
            "WHERE " + " AND ".join(clauses) + " ORDER BY nome,id LIMIT 10"
        )
        items = [product_view(row) for row in conn.execute(sql, params).fetchall()]
    return {
        "action": action,
        "items": items,
        "message": "Nenhum item encontrado. Consulte um atendente." if not items else
        "Dados consultados no catálogo do negócio; confirme antes de fechar o pedido.",
    }
