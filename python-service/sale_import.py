import json
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from client_import import ImportBatch as BaseBatch
from client_import import snapshot_and_hash
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field
from sales_data import SALE_COLUMNS, Money, linked_client, linked_product
from shared_data import (
    MAX_SAFE_ID,
    ensure_workspace,
    require_shared_data,
    workspace_slug,
)

from database import connect

router = APIRouter(prefix="/api/v1/vendas/importacoes", tags=["vendas"])


class LegacySale(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cliente: str = Field(min_length=1, max_length=160)
    item: str = Field(default="", max_length=160)
    cliente_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_ID, strict=True)
    produto_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_ID, strict=True)
    data: date
    quantidade: int = Field(default=1, ge=1, le=MAX_SAFE_ID, strict=True)
    preco: Money | None = None
    desconto: Money = Decimal(0)
    valor: Money
    pagamento: str = Field(default="Não informado", min_length=1, max_length=40)
    observacao: str = Field(default="", max_length=5000)
    status: Literal["Pago", "Pendente", "Cancelado", "Rascunho"]


class SaleImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_id: int = Field(ge=0, le=MAX_SAFE_ID, strict=True)
    venda: LegacySale
    extras: dict[str, Any] = Field(default_factory=dict)


class SaleImportBatch(BaseBatch):
    itens: list[SaleImportItem] = Field(min_length=1, max_length=500)


def inspect_batch(cur, workspace_id, payload):
    rows = []
    for item in payload.itens:
        _, fingerprint = snapshot_and_hash(item)
        cur.execute(
            "SELECT i.venda_id, i.fingerprint, v.excluida FROM socialmei.crm_venda_importacoes i JOIN socialmei.crm_vendas v ON v.id = i.venda_id AND v.workspace_id = i.workspace_id WHERE i.workspace_id = %s AND i.origem = %s AND i.local_id = %s",
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
        if not prior and item.venda.cliente_id is not None:
            linked_client(cur, workspace_id, item.venda.cliente_id)
        if not prior and item.venda.produto_id is not None:
            linked_product(cur, workspace_id, item.venda.produto_id)
        rows.append(
            {
                "local_id": item.local_id,
                "venda_id": prior["venda_id"] if prior else None,
                "acao": action,
            }
        )
    return rows


@router.post("/preview")
def preview_import(payload: SaleImportBatch):
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
        "estoque_movimentado": False,
    }


@router.post("/confirmar")
def confirm_import(payload: SaleImportBatch):
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
            values = item.venda.model_dump()
            if item.venda.produto_id is not None:
                values["tipo_item"] = linked_product(
                    cur, workspace_id, item.venda.produto_id
                )["tipo"]
            cur.execute(
                f"INSERT INTO socialmei.crm_vendas (workspace_id, importada, {', '.join(values)}) VALUES (%s, true, {', '.join(['%s'] * len(values))}) RETURNING {SALE_COLUMNS}",
                [workspace_id, *values.values()],
            )
            result["venda_id"] = cur.fetchone()["id"]
            snapshot, fingerprint = snapshot_and_hash(item)
            cur.execute(
                "INSERT INTO socialmei.crm_venda_importacoes (workspace_id, origem, local_id, venda_id, fingerprint, snapshot) VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
                (
                    workspace_id,
                    payload.origem,
                    item.local_id,
                    result["venda_id"],
                    fingerprint,
                    json.dumps(snapshot),
                ),
            )
    return {
        "origem": str(payload.origem),
        "itens": results,
        "estoque_movimentado": False,
    }
