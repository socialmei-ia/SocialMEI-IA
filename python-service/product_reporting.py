"""Actionable catalogue lists, with current stock distinct from period sales."""
from datetime import date
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from database import connect
from shared_data import MAX_SAFE_ID
from workspace_reporting import scope, report_period, _money
import settings

router = APIRouter(prefix="/api/v1/reporting", tags=["product reporting"])


@router.get("/products")
def products(start: date | None = Query(None), end: date | None = Query(None),
             kind: Literal['low_stock', 'no_sales'] = Query('low_stock'),
             after: int = Query(0, ge=0, le=MAX_SAFE_ID), limit: int = Query(50, ge=1, le=50)):
    workspace = scope()
    if start is not None or end is not None:
        report_period(start, end, date.min)
    try:
        zone = settings.business_timezone().key
    except ValueError:
        raise HTTPException(503, "Confira o fuso horário do negócio.") from None
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SET LOCAL statement_timeout='3s'")
            conn.execute("SELECT set_config('TimeZone',%s,true)", (zone,))
            clock = conn.execute("SELECT CURRENT_DATE AS today,CURRENT_TIMESTAMP AS as_of").fetchone()
            start, end, days = report_period(start, end, clock['today'])
            base = (
                "WITH items AS (SELECT p.id,p.nome,p.categoria,p.preco,p.estoque,p.minimo,"
                "p.estoque<=p.minimo AS low_stock,NOT EXISTS(SELECT 1 FROM socialmei.crm_vendas v "
                "WHERE v.workspace_id=p.workspace_id AND v.produto_id=p.id AND NOT v.excluida "
                "AND v.status IN ('Pago','Pendente') AND v.data BETWEEN %s AND %s) AS no_sales "
                "FROM socialmei.crm_produtos p WHERE p.workspace_id=%s AND p.tipo='Produto' AND p.status='Ativo') "
            )
            args = (start, end, workspace)
            totals = conn.execute(base + "SELECT count(*) AS active_products,count(*) FILTER(WHERE low_stock) AS low_stock,count(*) FILTER(WHERE no_sales) AS no_sales FROM items", args).fetchone()
            # kind is a closed enum; all user values remain bound parameters.
            predicate = 'low_stock' if kind == 'low_stock' else 'no_sales'
            rows = conn.execute(base + "SELECT * FROM items WHERE " + predicate + " AND id>%s ORDER BY id LIMIT %s", (*args, after, limit + 1)).fetchall()
    except psycopg.Error:
        raise HTTPException(503, "Não foi possível consultar os produtos. Tente novamente.") from None
    page = rows[:limit]
    return {"workspace_id": workspace, "kind": kind,
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days, "timezone": zone},
            "as_of": clock['as_of'].isoformat(), "totals": dict(totals),
            "products": [{"id": r['id'], "name": r['nome'], "category": r['categoria'],
                          "price": _money(r['preco']), "stock": r['estoque'], "minimum": r['minimo']} for r in page],
            "next_after": page[-1]['id'] if len(rows) > limit else None,
            "description": "Somente produtos ativos do catálogo atual. Estoque baixo: quantidade atual menor ou igual ao mínimo configurado. Não é quantidade vendida nem estoque histórico.",
            "sales_description": "Sem vendas: nenhuma venda paga ou pendente, não excluída, vinculada ao produto no período. Cancelamentos e serviços ficam fora. Preço exibido é o atual do catálogo, não receita."}
