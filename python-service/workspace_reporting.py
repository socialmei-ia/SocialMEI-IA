"""Workspace-bounded reporting for authenticated members (including viewer).

No direct database exposure, raw PII, mutable SQL, admin connection or public
download. Monetary amounts are returned as decimal strings to avoid float loss.
"""
import csv
import io

from fastapi import APIRouter, HTTPException, Query, Response
from psycopg.rows import dict_row

from account_auth import current, require_enabled
from database import connect
import settings

router = APIRouter(prefix="/api/v1/reporting", tags=["workspace reporting"])


def scope():
    require_enabled()
    user = current()
    if user.get("role") not in {"owner", "admin", "member", "viewer", "report_viewer"}:
        raise HTTPException(403, "Acesso aos relatórios indisponível.")
    return user["workspace_id"]


def _stats(conn, workspace, days):
    rows = conn.execute(
        "SELECT status,COUNT(*)::bigint AS items,COALESCE(SUM(valor),0) AS total "
        "FROM socialmei.crm_vendas "
        "WHERE workspace_id=%s AND NOT excluida "
        "AND data BETWEEN CURRENT_DATE-(%s::integer - 1) AND CURRENT_DATE "
        "GROUP BY status ORDER BY status",
        (workspace, days),
    ).fetchall()
    sales = {row["status"]: {
        "quantidade": row["items"], "valor": str(row["total"])
    } for row in rows}
    rows = conn.execute(
        "SELECT tipo,status,COUNT(*)::bigint AS items,COALESCE(SUM(valor),0) AS total "
        "FROM socialmei.crm_financeiro "
        "WHERE workspace_id=%s AND NOT excluida "
        "AND vencimento BETWEEN CURRENT_DATE-(%s::integer - 1) AND CURRENT_DATE "
        "GROUP BY tipo,status ORDER BY tipo,status",
        (workspace, days),
    ).fetchall()
    finance = [
        {"tipo": row["tipo"], "status": row["status"],
         "quantidade": row["items"], "valor": str(row["total"])}
        for row in rows
    ]
    counts = conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM socialmei.crm_clientes WHERE workspace_id=%s) AS clientes, "
        "(SELECT COUNT(*) FROM socialmei.crm_produtos WHERE workspace_id=%s AND status='Ativo') AS itens_ativos, "
        "(SELECT COUNT(*) FROM socialmei.crm_produtos WHERE workspace_id=%s "
        "AND status='Ativo' AND tipo='Produto' AND estoque<=minimo) AS estoque_baixo",
        (workspace, workspace, workspace),
    ).fetchone()
    attendance = None
    channel_schema = conn.execute(
        "SELECT COUNT(*) AS columns FROM information_schema.columns "
        "WHERE table_schema='socialmei' AND table_name IN ('me_conversations','me_messages') "
        "AND column_name='origin'"
    ).fetchone()['columns']
    if channel_schema == 2:
        attendance = [dict(row) for row in conn.execute(
            "SELECT c.channel,m.origin,COUNT(DISTINCT c.id)::bigint AS conversations, "
            "COUNT(m.id)::bigint AS messages FROM socialmei.me_conversations c "
            "JOIN socialmei.me_messages m ON m.workspace_id=c.workspace_id AND m.conversation_id=c.id "
            "WHERE c.workspace_id=%s AND m.occurred_at>=CURRENT_DATE-(%s::integer-1) "
            "AND m.occurred_at<CURRENT_DATE+1 GROUP BY c.channel,m.origin ORDER BY c.channel,m.origin",
            (workspace, days),
        ).fetchall()]
    return {
        "period_days": days,
        "as_of": conn.execute("SELECT CURRENT_DATE AS as_of").fetchone()["as_of"].isoformat(),
        "totals": dict(counts),
        "sales_by_status": sales,
        "finance_by_type_and_status": finance,
        "attendance": attendance,
        "attendance_description": "Mensagens recebidas persistidas por canal e origem. Dados de laboratório não comprovam tráfego real; entrega e resolução não são medidas.",
        "description": "Vendas por data de venda; lançamentos por vencimento, sem duplicar saldos.",
    }


def summary(days: int):
    workspace = scope()
    try:
        zone = settings.business_timezone().key
    except ValueError:
        raise HTTPException(503, "Confira o fuso horário configurado para o negócio.") from None
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='3000ms'")
        conn.execute("SELECT set_config('TimeZone', %s, true)", (zone,))
        return _stats(conn, workspace, days)


@router.get("/overview")
def overview(days: int = Query(30, ge=1, le=366)):
    return summary(days)


def csv_rows(report):
    """Only trusted fixed labels and enum/numeric database aggregate values."""
    yield ("Seção", "Tipo", "Situação", "Quantidade", "Valor (R$)")
    for status, record in sorted(report["sales_by_status"].items()):
        yield ("Vendas", "", status, record["quantidade"], record["valor"])
    for record in report["finance_by_type_and_status"]:
        yield ("Financeiro", record["tipo"], record["status"],
               record["quantidade"], record["valor"])
    for record in report.get('attendance') or []:
        yield ('Mensagens recebidas', record['channel'], record['origin'], record['messages'], '')
        yield ('Conversas com recebimento', record['channel'], record['origin'], record['conversations'], '')
    for key, value in report["totals"].items():
        yield ("Resumo", "", key, value, "")


@router.get("/overview.csv")
def export_csv(days: int = Query(30, ge=1, le=366)):
    report = summary(days)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    for record in csv_rows(report):
        writer.writerow(record)
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=socialmei-relatorio.csv",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
