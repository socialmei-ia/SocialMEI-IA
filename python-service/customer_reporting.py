"""Persisted customer purchase indicators, with no identity for report-only access."""
from datetime import date

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from account_auth import current
from database import connect
from workspace_reporting import scope, report_period, _money
import settings

router = APIRouter(prefix="/api/v1/reporting", tags=["customer reporting"])
VALID = "workspace_id=%s AND NOT excluida AND status IN ('Pago','Pendente') AND cliente_id IS NOT NULL"


@router.get("/customers")
def customers(start: date | None = Query(None), end: date | None = Query(None)):
    workspace = scope()
    if start is not None or end is not None:
        report_period(start, end, date.min)
    try:
        zone = settings.business_timezone().key
    except ValueError:
        raise HTTPException(503, "Confira o fuso horário do negócio.") from None
    identified = current()["role"] != "report_viewer"
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SET LOCAL statement_timeout='3s'")
            conn.execute("SELECT set_config('TimeZone',%s,true)",(zone,))
            today = conn.execute("SELECT CURRENT_DATE AS today").fetchone()["today"]
            start,end,days = report_period(start,end,today)
            new = conn.execute(
                "SELECT count(*) AS n FROM socialmei.crm_clientes WHERE workspace_id=%s "
                "AND criado_em>=%s::date AND criado_em<(%s::date+1)",(workspace,start,end),
            ).fetchone()["n"]
            counts = conn.execute(
                "WITH valid AS (SELECT cliente_id,data FROM socialmei.crm_vendas WHERE "+VALID+"), "
                "buyers AS (SELECT cliente_id,count(*) AS purchases FROM valid WHERE data BETWEEN %s AND %s GROUP BY cliente_id) "
                "SELECT count(*) AS buyers,count(*) FILTER(WHERE purchases>=2) AS repeat_buyers,"
                "count(*) FILTER(WHERE EXISTS(SELECT 1 FROM valid v WHERE v.cliente_id=b.cliente_id AND v.data<%s)) AS returning_buyers FROM buyers b",
                (workspace,start,end,start),
            ).fetchone()
            ranked = []
            if identified:
                ranked = [
                    {"id":row["id"],"name":row["nome"],"purchases":row["purchases"],"total":_money(row["total"])}
                    for row in conn.execute(
                        "SELECT c.id,c.nome,count(*) AS purchases,sum(v.valor) AS total "
                        "FROM socialmei.crm_vendas v JOIN socialmei.crm_clientes c "
                        "ON c.workspace_id=v.workspace_id AND c.id=v.cliente_id "
                        "WHERE v.workspace_id=%s AND NOT v.excluida AND v.status IN ('Pago','Pendente') "
                        "AND v.data BETWEEN %s AND %s GROUP BY c.id,c.nome "
                        "ORDER BY purchases DESC,total DESC,c.id LIMIT 10",(workspace,start,end),
                    ).fetchall()
                ]
    except psycopg.Error:
        raise HTTPException(503,"Não foi possível consultar os clientes. Tente novamente.") from None
    return {"workspace_id":workspace,"period":{"start":start.isoformat(),"end":end.isoformat(),"days":days,"timezone":zone},
            "new_customers":new,**dict(counts),"identification_available":identified,"customers":ranked,
            "description":"Compras válidas: vendas pagas ou pendentes, não excluídas e vinculadas a um cliente cadastrado. Não representam recebimentos.",
            "repeat_description":"Recorrentes no período: pelo menos duas vendas válidas distintas dentro do intervalo.",
            "returning_description":"Voltaram a comprar: compra válida no período e outra anterior ao início selecionado. Vendas sem cliente cadastrado ficam fora destes indicadores."}
