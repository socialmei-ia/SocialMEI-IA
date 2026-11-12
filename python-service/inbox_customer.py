"""Explicit tenant-scoped CRM links for enabled inbox conversations. No transport."""

import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field, StrictInt

import settings
from message_enrichment import Id, SAFE_MAX, Strict, db, guard, lock_workspace

router = APIRouter(prefix="/api/v1/message-enrichment", tags=["inbox CRM"])


class CustomerLink(Strict):
    expected_revision: Annotated[StrictInt, Field(ge=0, le=SAFE_MAX-1)]
    cliente_id: Annotated[StrictInt, Field(ge=1, le=SAFE_MAX)] | None


def enabled_origins(workspace):
    # Keep exactly the same visibility boundary as message_enrichment.conversations.
    origins = ["synthetic"] if settings.message_enrichment_mode() == "stub" else []
    if settings.instagram_ingress_isolated_enabled() or settings.instagram_live_ingress_enabled():
        origins.append("instagram")
    if settings.waha_inbox_enabled(workspace):
        origins.append("waha")
    return origins


def public_view(conn, workspace, row):
    customer = None
    if row["cliente_id"] is not None:
        customer = conn.execute(
            "SELECT id,nome,telefone,email FROM socialmei.crm_clientes "
            "WHERE workspace_id=%s AND id=%s",
            (workspace, row["cliente_id"]),
        ).fetchone()
    return {
        "conversation_id": row["id"],
        "revision": row["revision"],
        "cliente_id": row["cliente_id"],
        "customer": customer,
    }


@router.get("/conversations/{conversation_id}/customer")
def get_customer(conversation_id: Id, request: Request, response: Response):
    workspace = guard(request, response, read_inbox=True)["workspace_id"]
    with db() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL statement_timeout='5s'")
        row = conn.execute(
            "SELECT id,revision,cliente_id FROM socialmei.me_conversations "
            "WHERE workspace_id=%s AND id=%s AND origin=ANY(%s)",
            (workspace, conversation_id, enabled_origins(workspace)),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Conversa não encontrada.")
        return public_view(conn, workspace, row)



def exact_whatsapp_phone(contact_ref):
    """Only an authenticated WhatsApp number, never an Instagram-scoped ID."""
    if not isinstance(contact_ref, str):
        return None
    match = re.fullmatch(r"waha:([1-9][0-9]{7,14})@c\.us", contact_ref)
    return match.group(1) if match else None


@router.get("/conversations/{conversation_id}/customer-suggestions")
def customer_suggestions(conversation_id: Id, request: Request, response: Response):
    """Read-only, exact-match CRM hints; operators must confirm using set_customer.

    Never auto-link, import a customer, or infer that a numeric Meta ID is a phone.
    A duplicate phone deliberately yields no candidate to prevent mistaken links.
    """
    workspace = guard(request, response, read_inbox=True)["workspace_id"]
    with db() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL statement_timeout='5s'")
        row = conn.execute(
            "SELECT origin,contact_ref,cliente_id FROM socialmei.me_conversations "
            "WHERE workspace_id=%s AND id=%s AND origin=ANY(%s)",
            (workspace, conversation_id, enabled_origins(workspace)),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Conversa não encontrada.")
        result = {"conversation_id": conversation_id, "candidates": [],
                  "requires_confirmation": True, "ambiguous": False}
        if row["cliente_id"] is not None:
            return result
        if row["origin"] != "waha":
            return result
        number = exact_whatsapp_phone(row["contact_ref"])
        if number is None:
            return result
        customers = conn.execute(
            "SELECT id,nome FROM socialmei.crm_clientes "
            "WHERE workspace_id=%s AND regexp_replace(COALESCE(telefone,''),"
            "'[^0-9]','','g')=%s ORDER BY id LIMIT 2",
            (workspace, number),
        ).fetchall()
        if len(customers) > 1:
            result["ambiguous"] = True
        elif customers:
            result["candidates"] = [{"id": customers[0]["id"],
                                     "nome": customers[0]["nome"]}]
        return result


@router.get("/conversations/{conversation_id}/assistant-context")
def assistant_context(conversation_id: Id, request: Request, response: Response):
    """Minimal authenticated context for a future AI draft, never a sender.

    Incoming text is untrusted data; no tool or automation executes it here.
    Restricted to operator roles and channels explicitly visible in the inbox.
    """
    workspace = guard(request, response, read_inbox=True, write=True)["workspace_id"]
    allowed = [x for x in enabled_origins(workspace) if x in {"instagram", "waha"}]
    with db() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL statement_timeout='5s'")
        row = conn.execute(
            "SELECT id,origin,cliente_id FROM socialmei.me_conversations "
            "WHERE workspace_id=%s AND id=%s AND origin=ANY(%s)",
            (workspace, conversation_id, allowed),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Conversa não encontrada.")
        messages = conn.execute(
            "SELECT id,text,occurred_at FROM socialmei.me_messages "
            "WHERE workspace_id=%s AND conversation_id=%s AND origin=%s "
            "ORDER BY occurred_at DESC,id DESC LIMIT 6",
            (workspace, conversation_id, row["origin"]),
        ).fetchall()
        customer = None
        if row["cliente_id"] is not None:
            customer = conn.execute(
                "SELECT id,nome FROM socialmei.crm_clientes "
                "WHERE workspace_id=%s AND id=%s",
                (workspace, row["cliente_id"]),
            ).fetchone()
        products = conn.execute(
            "SELECT id,nome,tipo,preco,duracao_minutos "
            "FROM socialmei.crm_produtos WHERE workspace_id=%s AND status='Ativo' "
            "ORDER BY nome,id LIMIT 8",
            (workspace,),
        ).fetchall()
    return {
        "conversation_id": conversation_id,
        "origin": row["origin"],
        "customer": customer,
        "recent_untrusted_messages": [
            {"message_id": item["id"], "text": item["text"][:600]}
            for item in reversed(messages)
        ],
        "catalog_snapshot": products,
        "context_only": True,
        "send_enabled": False,
        "requires_human_review": True,
    }


@router.patch("/conversations/{conversation_id}/customer")
def set_customer(conversation_id: Id, payload: CustomerLink, request: Request, response: Response):
    workspace = guard(request, response, read_inbox=True, write=True)["workspace_id"]
    origins = enabled_origins(workspace)
    with db() as conn:
        conn.execute("SET LOCAL lock_timeout='3s'")
        conn.execute("SET LOCAL statement_timeout='5s'")
        lock_workspace(conn, workspace)
        if not conn.execute(
            "SELECT id FROM socialmei.me_conversations WHERE workspace_id=%s AND id=%s AND origin=ANY(%s)",
            (workspace, conversation_id, origins),
        ).fetchone():
            raise HTTPException(404, "Conversa não encontrada.")
        # CRM writes use workspace -> customer. Keep that order before the inbox row.
        if payload.cliente_id is not None and not conn.execute(
            "SELECT id FROM socialmei.crm_clientes WHERE workspace_id=%s AND id=%s FOR SHARE",
            (workspace, payload.cliente_id),
        ).fetchone():
            raise HTTPException(404, "Cliente não encontrado neste negócio.")
        row = conn.execute(
            "SELECT id,revision,cliente_id FROM socialmei.me_conversations "
            "WHERE workspace_id=%s AND id=%s AND origin=ANY(%s) FOR UPDATE",
            (workspace, conversation_id, origins),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Conversa não encontrada.")
        if row["revision"] != payload.expected_revision:
            raise HTTPException(409, "A conversa mudou. Recarregue antes de vincular o cliente.")
        if row["cliente_id"] != payload.cliente_id:
            row = conn.execute(
                "UPDATE socialmei.me_conversations SET cliente_id=%s,revision=revision+1 "
                "WHERE workspace_id=%s AND id=%s RETURNING id,revision,cliente_id",
                (payload.cliente_id, workspace, conversation_id),
            ).fetchone()
        return public_view(conn, workspace, row)
