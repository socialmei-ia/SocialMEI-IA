import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sales_data import Money, linked_client
from shared_data import MAX_SAFE_ID, ensure_workspace, require_shared_data
from account_auth import current

from database import connect
import settings

router = APIRouter(prefix="/api/v1/financeiro", tags=["financeiro"])
FINANCE_COLUMNS = "id, cliente_id, descricao, pessoa, tipo, valor, vencimento, status, data_pagamento, importada, excluida, versao, criado_em, atualizado_em, categoria, liquidado_parcial, venda_id"


def payment_date() -> date:
    try:
        return datetime.now(settings.business_timezone()).date()
    except ValueError:
        raise HTTPException(503, "Confira o fuso horário configurado para o negócio.") from None


class FinanceFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cliente_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_ID, strict=True)
    descricao: str = Field(min_length=1, max_length=240)
    pessoa: str = Field(default="", max_length=160)
    tipo: Literal["receita", "despesa"]
    valor: Money
    vencimento: date


class CategorizedFinanceFields(FinanceFields):
    categoria: str | None = Field(default=None, max_length=80)

    @field_validator("categoria")
    @classmethod
    def valid_category(cls, value):
        if value is not None and any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("Confira a categoria informada.")
        return value


class FinanceCreate(CategorizedFinanceFields):
    operation_id: UUID
    status: Literal["aberto", "pago"] = "aberto"


class FinanceEdit(CategorizedFinanceFields):
    operation_id: UUID
    expected_version: int = Field(ge=1, strict=True)


class FinanceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    expected_version: int = Field(ge=1, strict=True)


class Settlement(FinanceAction):
    valor: Money
    data: date


class SaleReceivable(FinanceAction):
    vencimento: date


class SettlementCorrection(FinanceAction):
    parcela_id: UUID
    motivo: str = Field(min_length=1, max_length=300)

    @field_validator("motivo")
    @classmethod
    def safe_reason(cls, value):
        if not value.strip() or any(ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value):
            raise ValueError("Informe um motivo válido.")
        return value.strip()


class CashItem(BaseModel):
    valor: Decimal
    data: date


class FinanceOut(BaseModel):
    id: int
    cliente_id: int | None
    descricao: str
    pessoa: str
    tipo: str
    valor: float
    vencimento: date
    status: str
    data_pagamento: date | None
    importada: bool
    excluida: bool
    versao: int
    criado_em: datetime
    atualizado_em: datetime
    categoria: str = ""
    liquidado_parcial: Decimal = Decimal("0.00")
    parcelas: list[CashItem] = Field(default_factory=list)
    venda_id: int | None = None


def begin_operation(cur, workspace_id, kind, entry_id, payload):
    # Packets from before category support must keep the same idempotency fingerprint.
    excluded = {"categoria"} if "categoria" not in payload.model_fields_set else set()
    serialized = json.dumps(
        {
            "acao": kind,
            "lancamento_id": entry_id,
            "dados": payload.model_dump(mode="json", exclude=excluded),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    cur.execute(
        "SELECT fingerprint, resposta FROM socialmei.crm_financeiro_operacoes WHERE workspace_id = %s AND operation_id = %s",
        (workspace_id, payload.operation_id),
    )
    prior = cur.fetchone()
    if prior and prior["fingerprint"] != fingerprint:
        raise HTTPException(409, "Identidade de operação já usada com outros dados.")
    return fingerprint, prior["resposta"] if prior else None


def finish_operation(cur, workspace_id, payload, fingerprint, row):
    response = FinanceOut.model_validate(row).model_dump(mode="json")
    cur.execute(
        "INSERT INTO socialmei.crm_financeiro_operacoes (workspace_id, operation_id, fingerprint, resposta) VALUES (%s, %s, %s, %s::jsonb)",
        (workspace_id, payload.operation_id, fingerprint, json.dumps(response)),
    )
    return response


def lock_entry(cur, workspace_id, entry_id, version):
    cur.execute(
        f"SELECT {FINANCE_COLUMNS} FROM socialmei.crm_financeiro WHERE workspace_id = %s AND id = %s FOR UPDATE",
        (workspace_id, entry_id),
    )
    row = cur.fetchone()
    if not row or row["excluida"]:
        raise HTTPException(404, "Lançamento não encontrado.")
    if row["versao"] != version:
        raise HTTPException(
            409, "Lançamento alterado por outra sessão. Recarregue antes de salvar."
        )
    return row


def entry_values(cur, workspace_id, payload):
    excluded = {"operation_id", "expected_version"}
    if "categoria" not in payload.model_fields_set:
        excluded.add("categoria")
    values = payload.model_dump(exclude=excluded)
    if "categoria" in values:
        values["categoria"] = values["categoria"] or ""
    if payload.cliente_id is not None:
        values["pessoa"] = linked_client(cur, workspace_id, payload.cliente_id)["nome"]
    return values


@router.get("", response_model=list[FinanceOut])
def list_entries():
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        cur.execute(
            f"SELECT {FINANCE_COLUMNS} FROM socialmei.crm_financeiro WHERE workspace_id = %s AND NOT excluida ORDER BY vencimento DESC, id DESC",
            (workspace_id,),
        )
        entries = cur.fetchall()
        cur.execute(
            "SELECT lancamento_id,valor,data FROM socialmei.crm_financeiro_liquidacoes "
            "WHERE workspace_id=%s AND estornado_em IS NULL ORDER BY data,id",
            (workspace_id,),
        )
        by_id = {entry["id"]: entry for entry in entries}
        for row in cur.fetchall():
            if row["lancamento_id"] in by_id:
                by_id[row["lancamento_id"]].setdefault("parcelas", []).append(row)
        return entries


@router.get("/{lancamento_id}", response_model=FinanceOut)
def get_entry(lancamento_id: int):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        cur.execute(
            f"SELECT {FINANCE_COLUMNS} FROM socialmei.crm_financeiro WHERE workspace_id = %s AND id = %s AND NOT excluida",
            (workspace_id, lancamento_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Lançamento não encontrado.")
        return row


@router.post("", response_model=FinanceOut, status_code=201)
def create_entry(payload: FinanceCreate):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        fingerprint, replay = begin_operation(cur, workspace_id, "criar", None, payload)
        if replay:
            return replay
        values = entry_values(cur, workspace_id, payload)
        values["data_pagamento"] = payment_date() if payload.status == "pago" else None
        cur.execute(
            f"INSERT INTO socialmei.crm_financeiro (workspace_id, {', '.join(values)}) VALUES (%s, {', '.join(['%s'] * len(values))}) RETURNING {FINANCE_COLUMNS}",
            [workspace_id, *values.values()],
        )
        return finish_operation(cur, workspace_id, payload, fingerprint, cur.fetchone())


@router.patch("/{lancamento_id}", response_model=FinanceOut)
def edit_entry(lancamento_id: int, payload: FinanceEdit):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        fingerprint, replay = begin_operation(
            cur, workspace_id, "editar", lancamento_id, payload
        )
        if replay:
            return replay
        prior = lock_entry(cur, workspace_id, lancamento_id, payload.expected_version)
        if prior["venda_id"]:
            raise HTTPException(409, "Para corrigir esta venda, cancele o recebível após revisar as parcelas.")
        if prior["status"] == "pago" or prior["liquidado_parcial"]:
            raise HTTPException(
                409,
                "Lançamento com quitação registrada mantém seu histórico. Corrija as parcelas antes de editar.",
            )
        values = entry_values(cur, workspace_id, payload)
        cur.execute(
            f"UPDATE socialmei.crm_financeiro SET {', '.join(k + ' = %s' for k in values)}, versao = versao + 1, atualizado_em = NOW() WHERE workspace_id = %s AND id = %s RETURNING {FINANCE_COLUMNS}",
            [*values.values(), workspace_id, lancamento_id],
        )
        return finish_operation(cur, workspace_id, payload, fingerprint, cur.fetchone())


def change_entry(entry_id, payload, kind):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        fingerprint, replay = begin_operation(
            cur, workspace_id, kind, entry_id, payload
        )
        if replay:
            return replay
        prior = lock_entry(cur, workspace_id, entry_id, payload.expected_version)
        if kind == "pagar" and prior["status"] == "pago":
            return finish_operation(cur, workspace_id, payload, fingerprint, prior)
        if kind == "pagar":
            if prior["liquidado_parcial"] or prior["venda_id"]:
                row = register_payment(cur, workspace_id, prior, payload, current()["id"],
                                       prior["valor"] - prior["liquidado_parcial"], payment_date())
                return finish_operation(cur, workspace_id, payload, fingerprint, row)
            cur.execute(
                f"UPDATE socialmei.crm_financeiro SET status = 'pago', data_pagamento = %s, versao = versao + 1, atualizado_em = NOW() WHERE workspace_id = %s AND id = %s RETURNING {FINANCE_COLUMNS}",
                (payment_date(), workspace_id, entry_id),
            )
        else:
            if prior["liquidado_parcial"]:
                raise HTTPException(409, "Corrija as parcelas registradas antes de cancelar a conta.")
            cur.execute(
                f"UPDATE socialmei.crm_financeiro SET excluida = true, versao = versao + 1, atualizado_em = NOW() WHERE workspace_id = %s AND id = %s RETURNING {FINANCE_COLUMNS}",
                (workspace_id, entry_id),
            )
        return finish_operation(cur, workspace_id, payload, fingerprint, cur.fetchone())


@router.post("/{lancamento_id}/pagar", response_model=FinanceOut)
def pay_entry(lancamento_id: int, payload: FinanceAction):
    return change_entry(lancamento_id, payload, "pagar")


@router.post("/{lancamento_id}/excluir", response_model=FinanceOut)
def remove_entry(lancamento_id: int, payload: FinanceAction):
    return change_entry(lancamento_id, payload, "excluir")


def register_payment(cur, workspace, entry, payload, actor, amount, day):
    total = entry["liquidado_parcial"] + amount
    if amount <= 0 or total > entry["valor"] or entry["status"] == "pago":
        raise HTTPException(409, "O valor precisa ser positivo e caber no saldo aberto.")
    if day > payment_date():
        raise HTTPException(422, "Informe uma data de pagamento que já ocorreu.")
    cur.execute(
        "INSERT INTO socialmei.crm_financeiro_liquidacoes(workspace_id,id,lancamento_id,valor,data,autor_id) "
        "VALUES(%s,%s,%s,%s,%s,%s)",
        (workspace, payload.operation_id, entry["id"], amount, day, actor),
    )
    return update_settlement_balance(cur, workspace, entry, total)


def update_settlement_balance(cur, workspace, entry, total):
    settled = total == entry["valor"]
    if entry["venda_id"] and settled != (entry["status"] == "pago"):
        cur.execute(
            "UPDATE socialmei.crm_vendas SET status=%s,versao=versao+1,atualizado_em=NOW() "
            "WHERE workspace_id=%s AND id=%s AND NOT excluida AND status=%s RETURNING id",
            ("Pago" if settled else "Pendente", workspace, entry["venda_id"], "Pendente" if settled else "Pago"),
        )
        if not cur.fetchone():
            raise HTTPException(409, "O estado da venda diverge do recebível. Confira o histórico.")
    cur.execute(
        f"UPDATE socialmei.crm_financeiro SET liquidado_parcial=%s,status=%s,"
        "data_pagamento=CASE WHEN %s THEN (SELECT max(data) FROM socialmei.crm_financeiro_liquidacoes "
        "WHERE workspace_id=%s AND lancamento_id=%s AND estornado_em IS NULL) ELSE NULL END,"
        f"versao=versao+1,atualizado_em=NOW() WHERE workspace_id=%s AND id=%s RETURNING {FINANCE_COLUMNS}",
        (total, "pago" if settled else "aberto", settled, workspace, entry["id"], workspace, entry["id"]),
    )
    return cur.fetchone()


@router.get("/{lancamento_id}/liquidacoes")
def settlement_history(lancamento_id: int):
    user = current()
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT 1 FROM socialmei.crm_financeiro WHERE workspace_id=%s AND id=%s",
            (user["workspace_id"], lancamento_id),
        )
        if not cur.fetchone():
            raise HTTPException(404, "Lançamento não encontrado.")
        cur.execute(
            "SELECT id,valor::text,data,criado_em,estornado_em,motivo_estorno "
            "FROM socialmei.crm_financeiro_liquidacoes WHERE workspace_id=%s AND lancamento_id=%s ORDER BY data DESC,id",
            (user["workspace_id"], lancamento_id),
        )
        return {"items": cur.fetchall()}


def change_settlement(entry_id, payload, *, reverse=False):
    user = current()
    workspace = user["workspace_id"]
    if user["role"] not in {"owner", "admin", "member"}:
        raise HTTPException(403, "Acesso somente leitura.")
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        ensure_workspace(conn)
        kind = "corrigir_parcela" if reverse else "liquidar_parcela"
        fingerprint, replay = begin_operation(cur, workspace, kind, entry_id, payload)
        if replay:
            return replay
        entry = lock_entry(cur, workspace, entry_id, payload.expected_version)
        if reverse:
            cur.execute(
                "UPDATE socialmei.crm_financeiro_liquidacoes SET estornado_em=now(),estornado_por=%s,motivo_estorno=%s "
                "WHERE workspace_id=%s AND lancamento_id=%s AND id=%s AND estornado_em IS NULL RETURNING valor",
                (user["id"], payload.motivo, workspace, entry_id, payload.parcela_id),
            )
            settlement = cur.fetchone()
            if not settlement:
                raise HTTPException(404, "Parcela ativa não encontrada.")
            row = update_settlement_balance(cur, workspace, entry, entry["liquidado_parcial"] - settlement["valor"])
        else:
            row = register_payment(cur, workspace, entry, payload, user["id"], payload.valor, payload.data)
        return finish_operation(cur, workspace, payload, fingerprint, row)


@router.post("/{lancamento_id}/liquidacoes", response_model=FinanceOut)
def record_settlement(lancamento_id: int, payload: Settlement):
    return change_settlement(lancamento_id, payload)


@router.post("/{lancamento_id}/estornar-parcela", response_model=FinanceOut)
def reverse_settlement(lancamento_id: int, payload: SettlementCorrection):
    return change_settlement(lancamento_id, payload, reverse=True)


@router.post("/de-venda/{venda_id}", response_model=FinanceOut, status_code=201)
def create_sale_receivable(venda_id: int, payload: SaleReceivable):
    user = current()
    if user["role"] not in {"owner", "admin", "member"}:
        raise HTTPException(403, "Acesso somente leitura.")
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace = ensure_workspace(conn)
        fingerprint, replay = begin_operation(cur, workspace, "recebivel_venda", venda_id, payload)
        if replay:
            return replay
        cur.execute(
            "SELECT cliente_id,cliente,item,valor,status,versao FROM socialmei.crm_vendas "
            "WHERE workspace_id=%s AND id=%s AND NOT excluida FOR UPDATE",
            (workspace, venda_id),
        )
        sale = cur.fetchone()
        if not sale:
            raise HTTPException(404, "Venda não encontrada neste negócio.")
        if sale["status"] != "Pendente" or sale["versao"] != payload.expected_version or sale["valor"] <= 0:
            raise HTTPException(409, "Escolha uma venda pendente com valor positivo e revisão atual.")
        cur.execute("SELECT 1 FROM socialmei.crm_financeiro WHERE workspace_id=%s AND venda_id=%s AND NOT excluida",
                    (workspace, venda_id))
        if cur.fetchone():
            raise HTTPException(409, "Esta venda já tem um recebível ativo.")
        cur.execute(
            "INSERT INTO socialmei.crm_financeiro(workspace_id,cliente_id,descricao,pessoa,tipo,valor,"
            "vencimento,status,categoria,venda_id) VALUES(%s,%s,%s,%s,'receita',%s,%s,'aberto','Vendas',%s) "
            f"RETURNING {FINANCE_COLUMNS}",
            (workspace, sale["cliente_id"], f"Venda #{venda_id} · {sale['item']}"[:240], sale["cliente"][:160],
             sale["valor"], payload.vencimento, venda_id),
        )
        return finish_operation(cur, workspace, payload, fingerprint, cur.fetchone())
