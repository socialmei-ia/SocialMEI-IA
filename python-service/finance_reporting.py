"""Recorded paid flows, kept separate from sales revenue and bank balances."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, model_validator

from account_auth import current as current_account
from database import connect
from sales_data import Money
from workspace_reporting import scope, sales_period, _money
import settings

router = APIRouter(prefix="/api/v1/reporting", tags=["finance reporting"])


def paid(conn, workspace, start, end):
    row = conn.execute(
        "SELECT count(*) AS count,"
        "COALESCE(sum(valor) FILTER(WHERE tipo='receita'),0) AS incoming,"
        "COALESCE(sum(valor) FILTER(WHERE tipo='despesa'),0) AS outgoing "
        "FROM socialmei.crm_financeiro_caixa WHERE workspace_id=%s AND data BETWEEN %s AND %s",
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
                "SELECT count(*) FILTER(WHERE status IN ('aberto','atrasado')) AS count,"
                "COALESCE(sum(valor-liquidado_parcial) FILTER(WHERE status IN ('aberto','atrasado') AND tipo='receita'),0) AS incoming,"
                "COALESCE(sum(valor-liquidado_parcial) FILTER(WHERE status IN ('aberto','atrasado') AND tipo='despesa'),0) AS outgoing,"
                "count(*) FILTER(WHERE status='pago' AND data_pagamento IS NULL) AS undated_paid_count "
                "FROM socialmei.crm_financeiro WHERE workspace_id=%s AND NOT excluida "
                "AND vencimento BETWEEN %s AND %s", (workspace, start, end),
            ).fetchone()
            overdue = conn.execute(
                "SELECT count(*) AS count,"
                "COALESCE(sum(valor-liquidado_parcial) FILTER(WHERE tipo='receita'),0) AS incoming,"
                "COALESCE(sum(valor-liquidado_parcial) FILTER(WHERE tipo='despesa'),0) AS outgoing "
                "FROM socialmei.crm_financeiro WHERE workspace_id=%s AND NOT excluida "
                "AND status IN ('aberto','atrasado') AND vencimento<%s",
                (workspace, today),
            ).fetchone()
            daily = {r["day"]: r for r in conn.execute(
                "SELECT data AS day,"
                "COALESCE(sum(valor) FILTER(WHERE tipo='receita'),0) AS incoming,"
                "COALESCE(sum(valor) FILTER(WHERE tipo='despesa'),0) AS outgoing "
                "FROM socialmei.crm_financeiro_caixa WHERE workspace_id=%s AND data BETWEEN %s AND %s GROUP BY data",
                (workspace, start, end),
            ).fetchall()}
            categories = conn.execute(
                "SELECT NULLIF(categoria,'') AS category,tipo AS kind,count(*) AS count,sum(valor) AS total "
                "FROM socialmei.crm_financeiro_caixa WHERE workspace_id=%s AND data BETWEEN %s AND %s "
                "GROUP BY categoria,tipo ORDER BY total DESC,categoria,tipo LIMIT 101",
                (workspace, start, end),
            ).fetchall()
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
            "overdue": {"count": overdue["count"], "incoming": _money(overdue["incoming"]),
                        "outgoing": _money(overdue["outgoing"]), "as_of": today.isoformat()},
            "undated_paid_count": pending["undated_paid_count"], "daily": series,
            "categories": [{"category": row["category"], "kind": row["kind"], "count": row["count"],
                            "total": _money(row["total"])} for row in categories[:100]],
            "categories_truncated": len(categories) > 100,
            "description": "Entradas e saídas registradas, incluindo parcelas, por data de pagamento. O saldo representa movimentações internas. Vendas não são somadas novamente.",
            "pending_description": "Pendências abertas por vencimento no período. Lançamentos pagos sem data de pagamento ficam fora do saldo e são sinalizados quando vencem neste intervalo."}


MEI_2026_SOURCE = "https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_DESENQUADRAMENTO_SIMEI.pdf"
MEI_LIMIT_UPDATE = "https://legis.senado.leg.br/norma/44276013/publicacao/44280206"


class MeiTracking(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    operation_id: UUID
    expected_revision: int = Field(ge=0, le=2_147_483_646, strict=True)
    opened_on: date
    prior_through: date | None = None
    prior_amount: Money | None = None
    source_note: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def valid_period(self):
        if self.prior_through is None:
            if self.prior_amount is not None or self.source_note:
                raise ValueError("Informe a data final do período anterior.")
        elif self.prior_amount is None or not self.source_note or self.prior_through < self.opened_on:
            raise ValueError("Confira o valor, a data e a referência do faturamento anterior.")
        if "\x00" in self.source_note or any(0xD800 <= ord(ch) <= 0xDFFF for ch in self.source_note):
            raise ValueError("Referência inválida.")
        return self


def tracking_actor(write=False):
    workspace = scope()
    user = current_account()
    roles = {"owner", "admin"} if write else {"owner", "admin", "member", "viewer"}
    if user["role"] not in roles:
        raise HTTPException(403, "Acompanhamento do MEI indisponível para este acesso.")
    return workspace, user["id"]


def mei_limit(year, opened_on):
    # Later increases depend on the annual budgets under LC 238/2026 art. 3.
    if not 2018 <= year <= 2026 or opened_on.year > year:
        return None
    if opened_on.year == year:
        return (13 - opened_on.month) * Decimal("6750.00")
    return Decimal("81000.00")


def tracking_row(conn, workspace):
    return conn.execute(
        "SELECT * FROM socialmei.mei_tracking_revisions WHERE workspace_id=%s ORDER BY revision DESC LIMIT 1",
        (workspace,),
    ).fetchone()


@router.get("/mei")
def mei_tracking():
    workspace, _ = tracking_actor()
    try:
        today = datetime.now(settings.business_timezone()).date()
        start = today.replace(month=1, day=1)
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SET LOCAL statement_timeout='3s'")
            profile = tracking_row(conn, workspace)
            boundary = profile["prior_through"] if profile else None
            has_prior = boundary is not None and start <= boundary < today
            recorded_from = max(start, profile["opened_on"]) if profile else start
            if has_prior:
                recorded_from = max(recorded_from, boundary + timedelta(days=1))
            sales = conn.execute(
                "SELECT COALESCE(sum(valor),0) AS annual,"
                "COALESCE(sum(valor) FILTER(WHERE data >= %s),0) AS counted "
                "FROM socialmei.crm_vendas WHERE workspace_id=%s AND NOT excluida "
                "AND status IN ('Pago','Pendente') AND data BETWEEN %s AND %s",
                (recorded_from, workspace, start, today),
            ).fetchone()
    except (psycopg.Error, ValueError):
        raise HTTPException(503, "Acompanhamento do MEI indisponível.") from None
    prior = profile["prior_amount"] if has_prior else Decimal(0)
    estimated = sales["counted"] + prior
    limit = mei_limit(today.year, profile["opened_on"]) if profile else None
    usage = estimated / limit if limit is not None else None
    level = None
    if usage is not None:
        level = "exceeded" if usage > 1 else "near" if usage >= Decimal("0.8") else "below"
    return {
        "workspace_id": workspace, "year": today.year, "as_of": today,
        "revision": profile["revision"] if profile else 0,
        "opened_on": profile["opened_on"] if profile else None,
        "prior_through": boundary if has_prior else None, "prior_amount": _money(prior),
        "source_note": profile["source_note"] if has_prior else "",
        "system_sales": _money(sales["annual"]), "system_sales_used": _money(sales["counted"]),
        "system_from": recorded_from, "estimate": _money(estimated),
        "limit": _money(limit) if limit is not None else None, "level": level,
        "limit_source": MEI_2026_SOURCE if today.year <= 2026 else MEI_LIMIT_UPDATE,
    }


@router.post("/mei")
def save_mei_tracking(payload: MeiTracking):
    workspace, actor = tracking_actor(write=True)
    try:
        today = datetime.now(settings.business_timezone()).date()
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET LOCAL lock_timeout='3s'")
            conn.execute("SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE", (workspace,))
            fields = ("opened_on", "prior_through", "prior_amount", "source_note")
            values = tuple(getattr(payload, name) for name in fields)
            prior = conn.execute(
                "SELECT * FROM socialmei.mei_tracking_revisions WHERE workspace_id=%s AND operation_id=%s",
                (workspace, payload.operation_id),
            ).fetchone()
            if prior:
                if (tuple(prior[name] for name in fields) != values or prior["actor_id"] != actor
                        or prior["revision"] != payload.expected_revision + 1):
                    raise HTTPException(409, "Identificador usado com outros dados.")
                return {"revision": prior["revision"]}
            if payload.opened_on > today or (payload.prior_through is not None and not
                                            today.replace(month=1, day=1) <= payload.prior_through < today):
                raise HTTPException(422, "Use uma abertura já ocorrida e um período anterior completo deste ano.")
            profile = tracking_row(conn, workspace)
            revision = profile["revision"] if profile else 0
            if payload.expected_revision != revision:
                raise HTTPException(409, "O acompanhamento mudou. Reabra antes de salvar.")
            conn.execute(
                "INSERT INTO socialmei.mei_tracking_revisions "
                "(workspace_id,revision,operation_id,actor_id,opened_on,prior_through,prior_amount,source_note) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (workspace, revision + 1, payload.operation_id, actor, *values),
            )
            return {"revision": revision + 1}
    except (psycopg.Error, ValueError):
        raise HTTPException(503, "Não foi possível salvar o acompanhamento do MEI.") from None


class DasRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    operation_id: UUID
    expected_revision: int = Field(ge=0, le=2_147_483_646, strict=True)
    competencia: date
    pago_em: date | None = None
    valor: Money | None = None
    referencia: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def valid_receipt(self):
        if self.competencia.day != 1 or self.competencia.year < 2009:
            raise ValueError("Informe a competência como mês válido.")
        if self.pago_em is None:
            if self.valor is not None or not self.expected_revision:
                raise ValueError("Sinalize a correção de um registro existente.")
        elif self.pago_em < self.competencia or self.valor is None or self.valor <= 0:
            raise ValueError("Confira a data e o valor do pagamento informado.")
        if any(ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in self.referencia):
            raise ValueError("Referência inválida.")
        return self


@router.get("/mei/das")
def das_records(competencia: date | None = None):
    workspace, _ = tracking_actor()
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout='3s'")
            columns = "competencia,revision,pago_em,valor::text,referencia,registrado_em"
            if competencia is None:
                query = (f"SELECT DISTINCT ON (competencia) {columns} FROM socialmei.mei_das_revisions "
                         "WHERE workspace_id=%s ORDER BY competencia DESC,revision DESC LIMIT 60")
                params = (workspace,)
            else:
                query = (f"SELECT {columns} FROM socialmei.mei_das_revisions "
                         "WHERE workspace_id=%s AND competencia=%s ORDER BY revision DESC LIMIT 60")
                params = (workspace, competencia)
            return {"workspace_id": workspace, "items": conn.execute(query, params).fetchall()}
    except psycopg.Error:
        raise HTTPException(503, "Histórico do DAS indisponível.") from None


@router.post("/mei/das")
def record_das(payload: DasRecord):
    workspace, actor = tracking_actor(write=True)
    try:
        today = datetime.now(settings.business_timezone()).date()
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET LOCAL lock_timeout='3s'")
            conn.execute("SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE", (workspace,))
            fields = ("competencia", "pago_em", "valor", "referencia")
            values = tuple(getattr(payload, field) for field in fields)
            receipt = conn.execute(
                "SELECT * FROM socialmei.mei_das_revisions WHERE workspace_id=%s AND operation_id=%s",
                (workspace, payload.operation_id),
            ).fetchone()
            if receipt:
                if (tuple(receipt[name] for name in fields) != values or receipt["actor_id"] != actor
                        or receipt["revision"] != payload.expected_revision + 1):
                    raise HTTPException(409, "Identificador usado com outros dados.")
                return {"revision": receipt["revision"]}
            if payload.competencia > today or (payload.pago_em and payload.pago_em > today):
                raise HTTPException(422, "Informe uma competência e uma data que já ocorreram.")
            latest = conn.execute(
                "SELECT revision,pago_em FROM socialmei.mei_das_revisions "
                "WHERE workspace_id=%s AND competencia=%s ORDER BY revision DESC LIMIT 1",
                (workspace, payload.competencia),
            ).fetchone()
            revision = latest["revision"] if latest else 0
            if revision != payload.expected_revision or (payload.pago_em is None and not latest["pago_em"]):
                raise HTTPException(409, "O registro do DAS mudou. Atualize e confira o histórico.")
            conn.execute(
                "INSERT INTO socialmei.mei_das_revisions"
                "(workspace_id,revision,operation_id,actor_id,competencia,pago_em,valor,referencia) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (workspace, revision + 1, payload.operation_id, actor, *values),
            )
            return {"revision": revision + 1}
    except (psycopg.Error, ValueError):
        raise HTTPException(503, "Não foi possível registrar o DAS.") from None
