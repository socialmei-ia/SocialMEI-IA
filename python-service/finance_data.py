import hashlib
import json
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field
from sales_data import Money, linked_client
from shared_data import MAX_SAFE_ID, ensure_workspace, require_shared_data

from database import connect

router = APIRouter(prefix="/api/v1/financeiro", tags=["financeiro"])
FINANCE_COLUMNS = "id, cliente_id, descricao, pessoa, tipo, valor, vencimento, status, data_pagamento, importada, excluida, versao, criado_em, atualizado_em"


class FinanceFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cliente_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_ID, strict=True)
    descricao: str = Field(min_length=1, max_length=240)
    pessoa: str = Field(default="", max_length=160)
    tipo: Literal["receita", "despesa"]
    valor: Money
    vencimento: date


class FinanceCreate(FinanceFields):
    operation_id: UUID
    status: Literal["aberto", "pago"] = "aberto"


class FinanceEdit(FinanceFields):
    operation_id: UUID
    expected_version: int = Field(ge=1, strict=True)


class FinanceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    expected_version: int = Field(ge=1, strict=True)


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


def begin_operation(cur, workspace_id, kind, entry_id, payload):
    serialized = json.dumps(
        {
            "acao": kind,
            "lancamento_id": entry_id,
            "dados": payload.model_dump(mode="json"),
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
    values = payload.model_dump(exclude={"operation_id", "expected_version"})
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
        return cur.fetchall()


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
        values["data_pagamento"] = date.today() if payload.status == "pago" else None
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
        if prior["status"] == "pago":
            raise HTTPException(
                409,
                "Lançamento quitado mantém seu histórico. Crie outro para corrigir.",
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
            cur.execute(
                f"UPDATE socialmei.crm_financeiro SET status = 'pago', data_pagamento = %s, versao = versao + 1, atualizado_em = NOW() WHERE workspace_id = %s AND id = %s RETURNING {FINANCE_COLUMNS}",
                (date.today(), workspace_id, entry_id),
            )
        else:
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
