"""Explicit, audited exports of the authenticated owner's business records."""
import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import io
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import model_validator

from account_auth import Strict, current, require_enabled, throttle
from database import connect
import settings

router = APIRouter(prefix="/api/v1/exports", tags=["business CSV"])
Kind = Literal["clientes", "produtos", "vendas", "financeiro", "agendamentos"]
LIMIT = 10000
# Fixed projections intentionally exclude free-form private notes, secrets and messages.
MODELS = {
    "clientes": ("crm_clientes", "criado_em", True, "id,nome,email,telefone,criado_em", ["ID", "Nome", "E-mail", "Telefone", "Cadastro"], ""),
    "produtos": ("crm_produtos", "criado_em", True, "id,nome,categoria,tipo,preco,estoque,status,duracao_minutos", ["ID", "Nome", "Categoria", "Tipo", "Preço (R$)", "Estoque", "Status", "Duração (min)"], ""),
    "vendas": ("crm_vendas", "data", False, "id,cliente,item,data,quantidade,preco,desconto,valor,status", ["ID", "Cliente", "Item", "Data", "Quantidade", "Preço (R$)", "Desconto (R$)", "Total (R$)", "Status"], " AND NOT excluida"),
    "financeiro": ("crm_financeiro", "vencimento", False, "id,descricao,tipo,valor,vencimento,status,data_pagamento", ["ID", "Descrição", "Tipo", "Valor (R$)", "Vencimento", "Status", "Pagamento"], " AND NOT excluida"),
    "agendamentos": ("agenda_appointments", "scheduled_for", True, "id,client_name,service_name,scheduled_for,ends_at,status", ["ID", "Cliente", "Serviço", "Início", "Fim", "Status"], ""),
}


class ExportPeriod(Strict):
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def valid_period(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("Informe início e fim do período.")
        if self.start and (self.end == date.max or self.end < self.start or (self.end-self.start).days >= 366):
            raise ValueError("Escolha um período de até 366 dias.")
        return self


def cell(value, zone):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(zone).strftime("%d/%m/%Y %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, Decimal):
        return format(value, ".2f").replace(".", ",")
    text = str(value)
    # Excel may interpret formulas even after leading whitespace.
    if isinstance(value, str) and (text.lstrip(" \t\r\n\v\f\ufeff").startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n"))):
        text = "'" + text
    return text


@router.post("/{kind}")
def export(kind: Kind, payload: ExportPeriod):
    require_enabled()
    user = current()
    if user["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente responsáveis podem exportar estes dados.")
    throttle(str(user["id"]), "export_csv", timeout_seconds=3)
    try:
        zone = settings.business_timezone()
    except ValueError:
        raise HTTPException(503, "Confira o fuso horário do negócio.") from None
    table, field, timestamp, columns, titles, extra = MODELS[kind]
    where = "workspace_id=%s" + extra
    params = [user["workspace_id"]]
    if payload.start:
        if timestamp:
            begin = datetime.combine(payload.start, time.min, zone)
            finish = datetime.combine(payload.end + timedelta(days=1), time.min, zone)
        else:
            begin, finish = payload.start, payload.end + timedelta(days=1)
        where += f" AND {field}>=%s AND {field}<%s"
        params += [begin, finish]
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writerow(titles)
    with connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        conn.execute("SET LOCAL statement_timeout='10s'")
        # Check before sending any bytes: never silently truncate a larger business.
        count = conn.execute(f"SELECT count(*) FROM socialmei.{table} WHERE {where}", params).fetchone()[0]
        if count > LIMIT:
            raise HTTPException(422, "Há mais de 10 mil registros. Reduza o período para exportar sem cortes.")
        with conn.cursor(name="business_export") as cursor:
            cursor.execute(f"SELECT {columns} FROM socialmei.{table} WHERE {where} ORDER BY {field},id", params)
            for row in cursor:
                writer.writerow([cell(value, zone) for value in row])
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,%s)",
                     (user["id"], f"export_{kind}:{user['workspace_id']}"))
    suffix = f"{payload.start}_{payload.end}" if payload.start else "todos"
    return {"filename": f"socialmei-{kind}-{suffix}.csv", "row_count": count,
            "timezone": zone.key, "csv": "\ufeff" + buffer.getvalue()}
