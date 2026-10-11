import json
from datetime import date
from typing import Any, Literal

from client_import import ImportBatch as BaseBatch
from client_import import snapshot_and_hash
from fastapi import APIRouter, HTTPException
from finance_data import FINANCE_COLUMNS, FinanceFields
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sales_data import linked_client
from shared_data import (
    MAX_SAFE_ID,
    ensure_workspace,
    require_shared_data,
    workspace_slug,
)

from database import connect

router = APIRouter(prefix="/api/v1/financeiro/importacoes", tags=["financeiro"])


class LegacyEntry(FinanceFields):
    status: Literal["aberto", "atrasado", "pago"]
    data_pagamento: date | None = None

    @model_validator(mode="after")
    def validate_settlement(self):
        if self.status != "pago" and self.data_pagamento is not None:
            raise ValueError("Data de pagamento exige um lançamento quitado.")
        return self


class FinanceImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_id: int = Field(ge=0, le=MAX_SAFE_ID, strict=True)
    lancamento: LegacyEntry
    extras: dict[str, Any] = Field(default_factory=dict)


class FinanceImportBatch(BaseBatch):
    itens: list[FinanceImportItem] = Field(min_length=1, max_length=500)


def inspect_batch(cur, workspace_id, payload):
    rows = []
    for item in payload.itens:
        _, fingerprint = snapshot_and_hash(item)
        cur.execute(
            "SELECT i.lancamento_id, i.fingerprint, v.excluida FROM socialmei.crm_financeiro_importacoes i JOIN socialmei.crm_financeiro v ON v.id = i.lancamento_id AND v.workspace_id = i.workspace_id WHERE i.workspace_id = %s AND i.origem = %s AND i.local_id = %s",
            (workspace_id, payload.origem, item.local_id),
        )
        prior = cur.fetchone()
        action = (
            "criar"
            if not prior
            else "excluido"
            if prior["excluida"]
            else "conflito"
            if prior["fingerprint"] != fingerprint
            else "existente"
        )
        if not prior and item.lancamento.cliente_id is not None:
            linked_client(cur, workspace_id, item.lancamento.cliente_id)
        rows.append(
            {
                "local_id": item.local_id,
                "lancamento_id": prior["lancamento_id"] if prior else None,
                "acao": action,
            }
        )
    return rows


@router.post("/preview")
def preview_import(payload: FinanceImportBatch):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id FROM socialmei.workspaces WHERE slug = %s", (workspace_slug(),)
        )
        workspace = cur.fetchone()
        results = inspect_batch(cur, workspace["id"] if workspace else None, payload)
    return {
        "origem": str(payload.origem),
        "itens": results,
        "pode_importar": all(r["acao"] in {"criar", "existente"} for r in results),
        "vendas_alteradas": False,
    }


@router.post("/confirmar")
def confirm_import(payload: FinanceImportBatch):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        results = inspect_batch(cur, workspace_id, payload)
        if any(r["acao"] in {"conflito", "excluido"} for r in results):
            raise HTTPException(
                409,
                {
                    "mensagem": "Lote não importado; resolva os conflitos sem trocar a origem.",
                    "itens": results,
                },
            )
        for item, result in zip(payload.itens, results):
            if result["acao"] == "existente":
                continue
            values = item.lancamento.model_dump()
            cur.execute(
                f"INSERT INTO socialmei.crm_financeiro (workspace_id, importada, {', '.join(values)}) VALUES (%s, true, {', '.join(['%s'] * len(values))}) RETURNING {FINANCE_COLUMNS}",
                [workspace_id, *values.values()],
            )
            result["lancamento_id"] = cur.fetchone()["id"]
            snapshot, fingerprint = snapshot_and_hash(item)
            cur.execute(
                "INSERT INTO socialmei.crm_financeiro_importacoes (workspace_id, origem, local_id, lancamento_id, fingerprint, snapshot) VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
                (
                    workspace_id,
                    payload.origem,
                    item.local_id,
                    result["lancamento_id"],
                    fingerprint,
                    json.dumps(snapshot),
                ),
            )
    return {
        "origem": str(payload.origem),
        "itens": results,
        "vendas_alteradas": False,
    }
