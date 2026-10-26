"""Read-only workspace reporting and WhatsApp catalog query foundation.

All queries are scoped to the authenticated application's workspace. Existing
n8n technical token endpoints remain separate; do not expose a generic SQL API.
"""
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from account_auth import current, require_enabled
from database import connect
from shared_data import require_shared_data

router = APIRouter(prefix="/api/v1/workspace-insights", tags=["Workspace read-only insights"])


def _actor():
    require_shared_data()
    require_enabled()
    user = current()
    if user["role"] not in ("owner", "admin", "member", "viewer"):
        raise HTTPException(403, "Consulta não autorizada.")
    return user


@router.get("/overview")
def overview():
    user = _actor()
    workspace = user["workspace_id"]
    with connect() as conn:
        row = conn.execute(
            "SELECT "
            "(SELECT count(*) FROM socialmei.crm_clientes WHERE workspace_id=%s) AS clients,"
            "(SELECT count(*) FROM socialmei.crm_produtos WHERE workspace_id=%s) AS catalog_items,"
            "(SELECT count(*) FROM socialmei.crm_vendas WHERE workspace_id=%s AND NOT excluida) AS sales,"
            "(SELECT count(*) FROM socialmei.crm_financeiro WHERE workspace_id=%s AND NOT excluida) AS finance_entries",
            (workspace,workspace,workspace,workspace),
        ).fetchone()
    return {
        "workspace_id": workspace,
        "clients": row[0],
        "catalog_items": row[1],
        "sales": row[2],
        "finance_entries": row[3],
    }


@router.get("/availability")
def availability(q: str = Query(min_length=2,max_length=80), limit: int = Query(default=10,ge=1,le=20)):
    user = _actor()
    name = q.strip()
    if len(name) < 2 or any(ord(ch) < 32 for ch in name):
        raise HTTPException(422, "Consulta inválida.")
    with connect() as conn:
        conn.row_factory = dict_row
        records = conn.execute(
            "SELECT id,nome,tipo,preco,estoque,status FROM socialmei.crm_produtos "
            "WHERE workspace_id=%s AND nome ILIKE %s ESCAPE '\\' "
            "ORDER BY CASE WHEN lower(nome)=lower(%s) THEN 0 ELSE 1 END,nome,id LIMIT %s",
            (user["workspace_id"],"%" + name.replace("\\","\\\\").replace("%","\\%").replace("_","\\_") + "%",name,limit),
        ).fetchall()
    items=[]
    for item in records:
        active = item["status"].strip().lower() in ("ativo","disponível","disponivel")
        kind = item["tipo"]
        # Zero is the catalog's default; without explicit stock tracking, it cannot
        # establish that this product is sold out.
        quantity = item["estoque"] if kind == "Produto" else None
        availability = (
            "inactive" if not active else
            "service" if kind == "Serviço" else
            "in_stock" if quantity is not None and quantity > 0 else
            "unconfirmed"
        )
        items.append({
            "id":item["id"],"name":item["nome"],"type":kind,
            "price":str(item["preco"]), "availability": availability,
            "stock":quantity if active and kind=="Produto" else None,
        })
    return {"items":items,"source":"workspace_catalog","automated_reply_enabled":False}
