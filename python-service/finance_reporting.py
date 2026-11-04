"""Recorded paid flows, kept separate from sales revenue and bank balances."""
from datetime import date, timedelta
from decimal import Decimal

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from database import connect
from workspace_reporting import scope, sales_period, _money
import settings

router = APIRouter(prefix="/api/v1/reporting", tags=["finance reporting"])


def paid(conn, workspace, start, end):
    row = conn.execute(
        "SELECT count(*) AS count,"
        "COALESCE(sum(valor) FILTER(WHERE tipo='receita'),0) AS incoming,"
        "COALESCE(sum(valor) FILTER(WHERE tipo='despesa'),0) AS outgoing "
        "FROM socialmei.crm_financeiro WHERE workspace_id=%s AND NOT excluida "
        "AND status='pago' AND data_pagamento BETWEEN %s AND %s",
        (workspace, start, end),
    ).fetchone()
    return {"count": row["count"], "incoming": _money(row["incoming"]),
            "outgoing": _money(row["outgoing"]),
            "balance": _money(row["incoming"] - row["outgoing"])}


@router.get("/finance")
def finance(start: date | None = Query(None), end: date | None = Query(None)):
    workspace = scope()
    if start is not None or end is not None:
        sales_period(start, end, date.min)
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
            today = conn.execute("SELECT CURRENT_DATE AS today").fetchone()["today"]
            start, end, days, prior_start, prior_end = sales_period(start, end, today)
            current = paid(conn, workspace, start, end)
            previous = paid(conn, workspace, prior_start, prior_end)
            pending = conn.execute(
                "SELECT count(*) FILTER(WHERE status='aberto') AS count,"
                "COALESCE(sum(valor) FILTER(WHERE status='aberto' AND tipo='receita'),0) AS incoming,"
                "COALESCE(sum(valor) FILTER(WHERE status='aberto' AND tipo='despesa'),0) AS outgoing,"
                "count(*) FILTER(WHERE status='pago' AND data_pagamento IS NULL) AS undated_paid_count "
                "FROM socialmei.crm_financeiro WHERE workspace_id=%s AND NOT excluida "
                "AND vencimento BETWEEN %s AND %s", (workspace, start, end),
            ).fetchone()
            daily = {r["day"]: r for r in conn.execute(
                "SELECT data_pagamento AS day,"
                "COALESCE(sum(valor) FILTER(WHERE tipo='receita'),0) AS incoming,"
                "COALESCE(sum(valor) FILTER(WHERE tipo='despesa'),0) AS outgoing "
                "FROM socialmei.crm_financeiro WHERE workspace_id=%s AND NOT excluida "
                "AND status='pago' AND data_pagamento BETWEEN %s AND %s GROUP BY data_pagamento",
                (workspace, start, end),
            ).fetchall()}
    except psycopg.Error:
        raise HTTPException(503, "Não foi possível consultar o financeiro. Tente novamente.") from None
    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = daily.get(day, {"incoming": Decimal(0), "outgoing": Decimal(0)})
        series.append({"date": day.isoformat(), "incoming": _money(row["incoming"]),
                       "outgoing": _money(row["outgoing"]),
                       "balance": _money(row["incoming"] - row["outgoing"])})
    return {"workspace_id": workspace,
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days, "timezone": zone},
            "paid": current,
            "previous": {"start": prior_start.isoformat(), "end": prior_end.isoformat(), **previous},
            "balance_change": _money(Decimal(current["balance"]) - Decimal(previous["balance"])),
            "pending": {"count": pending["count"], "incoming": _money(pending["incoming"]),
                        "outgoing": _money(pending["outgoing"])},
            "undated_paid_count": pending["undated_paid_count"], "daily": series,
            "description": "Entradas e saídas registradas como pagas, pela data de pagamento. O saldo do período não representa lucro nem saldo bancário. Vendas não são somadas novamente.",
            "pending_description": "Pendências abertas por vencimento no período. Lançamentos pagos sem data de pagamento ficam fora do saldo e são sinalizados quando vencem neste intervalo."}
