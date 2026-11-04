"""Workspace-bounded reporting for authenticated members (including viewer).

No direct database exposure, raw PII, mutable SQL, admin connection or public
download. Monetary amounts are returned as decimal strings to avoid float loss.
"""
import csv
import io
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

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


def _money(value):
    return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def report_period(start, end, today):
    if (start is None) != (end is None):
        raise HTTPException(422, "Informe as duas datas do período.")
    if start is None:
        start, end = today - timedelta(days=29), today
    days = (end - start).days + 1
    if days < 1 or days > 366:
        raise HTTPException(422, "Escolha um período de 1 a 366 dias, em ordem cronológica.")
    return start, end, days


def sales_period(start, end, today):
    start, end, days = report_period(start, end, today)
    try:
        previous_end = start - timedelta(days=1)
        previous_start = start - timedelta(days=days)
    except OverflowError:
        raise HTTPException(422, "As datas não permitem comparar com o período anterior.") from None
    return start, end, days, previous_start, previous_end


def _sales_totals(conn, workspace, start, end):
    row = conn.execute(
        "SELECT COUNT(*)::bigint AS count,COALESCE(SUM(valor),0) AS total,"
        "COALESCE(AVG(valor),0) AS average_ticket FROM socialmei.crm_vendas "
        "WHERE workspace_id=%s AND NOT excluida AND status IN ('Pago','Pendente') "
        "AND data BETWEEN %s AND %s",
        (workspace, start, end),
    ).fetchone()
    return {"count": row["count"], "total": _money(row["total"]),
            "average_ticket": _money(row["average_ticket"])}


@router.get("/sales")
def sales(start: date | None = Query(None), end: date | None = Query(None)):
    workspace = scope()
    if start is not None or end is not None:
        sales_period(start, end, date.min)
    try:
        zone = settings.business_timezone().key
    except ValueError:
        raise HTTPException(503, "Confira o fuso horário configurado para o negócio.") from None
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='3000ms'")
        conn.execute("SELECT set_config('TimeZone', %s, true)", (zone,))
        today = conn.execute("SELECT CURRENT_DATE AS today").fetchone()["today"]
        start, end, days, previous_start, previous_end = sales_period(start, end, today)
        current = _sales_totals(conn, workspace, start, end)
        previous = _sales_totals(conn, workspace, previous_start, previous_end)
        daily = [
            {"date": row["day"].isoformat(), "count": row["count"], "total": _money(row["total"])}
            for row in conn.execute(
                "SELECT d.day::date AS day,COUNT(v.id)::bigint AS count,"
                "COALESCE(SUM(v.valor),0) AS total "
                "FROM generate_series(%s::date,%s::date,INTERVAL '1 day') d(day) "
                "LEFT JOIN socialmei.crm_vendas v ON v.data=d.day::date AND v.workspace_id=%s "
                "AND NOT v.excluida AND v.status IN ('Pago','Pendente') "
                "GROUP BY d.day ORDER BY d.day", (start, end, workspace),
            ).fetchall()
        ]
        products = [
            {"product_id": row["produto_id"], "name": row["item"],
             "quantity": str(row["quantity"]), "sales_count": row["sales_count"], "total": _money(row["total"])}
            for row in conn.execute(
                "SELECT produto_id,item,SUM(quantidade) AS quantity,COUNT(*)::bigint AS sales_count,"
                "SUM(valor) AS total FROM socialmei.crm_vendas "
                "WHERE workspace_id=%s AND NOT excluida AND status IN ('Pago','Pendente') "
                "AND data BETWEEN %s AND %s GROUP BY produto_id,item "
                "ORDER BY total DESC,item,produto_id NULLS LAST LIMIT 10", (workspace, start, end),
            ).fetchall()
        ]
    previous_total = Decimal(previous["total"])
    change = None if previous_total == 0 else _money(
        (Decimal(current["total"]) - previous_total) / previous_total * 100
    )
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days,
                   "timezone": zone, "previous_start": previous_start.isoformat(),
                   "previous_end": previous_end.isoformat()},
        "current": current, "previous": previous, "change_total_percent": change,
        "daily": daily, "products": products,
        "description": "Vendas pagas e pendentes por data de venda, sem rascunhos, cancelamentos ou exclusões. Não representa receita recebida nem saldo bancário. Ranking por valor e nome registrado na venda; sem nomes de clientes.",
    }


@router.get("/appointments")
def appointments(start: date | None = Query(None), end: date | None = Query(None)):
    workspace = scope()
    if start is not None or end is not None:
        report_period(start, end, date.min)
    try:
        zone = settings.business_timezone().key
    except ValueError:
        raise HTTPException(503, "Confira o fuso horário configurado para o negócio.") from None
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='3000ms'")
        conn.execute("SELECT set_config('TimeZone', %s, true)", (zone,))
        clock = conn.execute("SELECT CURRENT_DATE AS today,CURRENT_TIMESTAMP AS as_of").fetchone()
        start, end, days = report_period(start, end, clock["today"])
        scheduled = conn.execute(
            "SELECT COUNT(*)::bigint AS total,"
            "COUNT(*) FILTER (WHERE status='pending')::bigint AS pending,"
            "COUNT(*) FILTER (WHERE status='done')::bigint AS done,"
            "COUNT(*) FILTER (WHERE status='cancelled')::bigint AS cancelled,"
            "COUNT(*) FILTER (WHERE status='pending' AND scheduled_for>=CURRENT_TIMESTAMP)::bigint AS upcoming_pending "
            "FROM socialmei.agenda_appointments WHERE workspace_id=%s "
            "AND scheduled_for>=%s::date AND scheduled_for<(%s::date+1)",
            (workspace, start, end),
        ).fetchone()
        reschedules = conn.execute(
            "WITH revisions AS (SELECT scheduled_for,recorded_at,"
            "LAG(scheduled_for) OVER (PARTITION BY appointment_id ORDER BY revision) AS previous_schedule "
            "FROM socialmei.agenda_appointment_history WHERE workspace_id=%s) "
            "SELECT COUNT(*)::bigint AS events FROM revisions "
            "WHERE previous_schedule IS NOT NULL AND scheduled_for!=previous_schedule "
            "AND recorded_at>=%s::date AND recorded_at<(%s::date+1)",
            (workspace, start, end),
        ).fetchone()["events"]
        services = [dict(row) for row in conn.execute(
            "SELECT servico_id AS service_id,service_name AS name,COUNT(*)::bigint AS total,"
            "COUNT(*) FILTER (WHERE status='pending')::bigint AS pending,"
            "COUNT(*) FILTER (WHERE status='done')::bigint AS done,"
            "COUNT(*) FILTER (WHERE status='cancelled')::bigint AS cancelled "
            "FROM socialmei.agenda_appointments WHERE workspace_id=%s "
            "AND scheduled_for>=%s::date AND scheduled_for<(%s::date+1) "
            "GROUP BY servico_id,service_name ORDER BY total DESC,service_name,servico_id NULLS LAST LIMIT 10",
            (workspace, start, end),
        ).fetchall()]
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days, "timezone": zone},
        "as_of": clock["as_of"].isoformat(),
        "scheduled": {key: scheduled[key] for key in ("total", "pending", "done", "cancelled")},
        "upcoming_pending": scheduled["upcoming_pending"],
        "reschedule_events": reschedules,
        "services": services,
        "description": "Contagens pelo horário atual de início do agendamento no período selecionado, com o estado registrado. Pendente não significa atendimento realizado. Não mede ocupação, comparecimento ou receita.",
        "upcoming_description": "Próximos: somente agendamentos pendentes com início a partir do instante da consulta e dentro do período selecionado.",
        "reschedule_description": "Alterações de horário: eventos do histórico registrados no período, mesmo que o horário agendado esteja fora dele. Criação e mudanças apenas de estado não são reagendamentos.",
    }


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
