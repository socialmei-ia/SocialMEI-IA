"""Importação atômica de um dataset local; nunca sobrescreve clientes remotos."""

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shared_data import (
    CLIENTE_COLUMNS,
    MAX_SAFE_ID,
    ClienteCreate,
    ensure_workspace,
    require_shared_data,
    workspace_slug,
)

from database import connect

router = APIRouter(prefix="/api/v1/clientes/importacoes", tags=["shared-data"])


class ImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_id: int = Field(ge=0, le=MAX_SAFE_ID, strict=True)
    cliente: ClienteCreate
    extras: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_legacy_id(self):
        if self.cliente.legacy_local_id is not None:
            raise ValueError("Use local_id no item, sem legacy_local_id no cliente.")
        return self


class ImportBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origem: UUID
    itens: list[ImportItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_batch(self):
        ids = [item.local_id for item in self.itens]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs locais repetidos no lote.")
        try:
            encoded = json.dumps(self.model_dump(mode="json"), allow_nan=False)
        except ValueError as error:
            raise ValueError("Snapshot deve conter JSON finito.") from error
        if len(encoded.encode("utf-8")) > 2_000_000:
            raise ValueError("Lote excede 2 MB; divida em lotes menores.")
        return self


def snapshot_and_hash(item):
    snapshot = item.model_dump(mode="json")
    canonical = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return snapshot, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def inspect_batch(cur, workspace_id, payload):
    results = []
    for item in payload.itens:
        _, fingerprint = snapshot_and_hash(item)
        cur.execute(
            "SELECT cliente_id, fingerprint FROM socialmei.crm_cliente_importacoes "
            "WHERE workspace_id = %s AND origem = %s AND local_id = %s",
            (workspace_id, payload.origem, item.local_id),
        )
        previous = cur.fetchone()
        action = "criar"
        if previous:
            if previous["cliente_id"] is None:
                action = "excluido"
            elif previous["fingerprint"] != fingerprint:
                action = "conflito"
            else:
                action = "existente"
        results.append(
            {
                "local_id": item.local_id,
                "cliente_id": previous["cliente_id"] if previous else None,
                "acao": action,
            }
        )
    return results


@router.post("/preview")
def preview_import(payload: ImportBatch):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Prévia não cria workspace, clientes ou mapeamentos.
        cur.execute(
            "SELECT id FROM socialmei.workspaces WHERE slug = %s", (workspace_slug(),)
        )
        workspace = cur.fetchone()
        results = inspect_batch(cur, workspace["id"] if workspace else None, payload)
    return {
        "origem": str(payload.origem),
        "itens": results,
        "pode_importar": all(row["acao"] in {"criar", "existente"} for row in results),
    }


@router.post("/confirmar")
def confirm_import(payload: ImportBatch):
    require_shared_data()
    with connect() as conn:
        # ensure_workspace serializa operações do mesmo workspace na transação.
        workspace_id = ensure_workspace(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            results = inspect_batch(cur, workspace_id, payload)
            if any(row["acao"] in {"conflito", "excluido"} for row in results):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "mensagem": "Lote não importado. Resolva os conflitos sem trocar a identidade de origem.",
                        "itens": results,
                    },
                )
            for item, result in zip(payload.itens, results):
                if result["acao"] == "existente":
                    continue
                values = item.cliente.model_dump()
                columns = list(values)
                params = [
                    json.dumps(value) if key == "tags" else value
                    for key, value in values.items()
                ]
                placeholders = [
                    "%s::jsonb" if key == "tags" else "%s" for key in columns
                ]
                cur.execute(
                    f"INSERT INTO socialmei.crm_clientes (workspace_id, {', '.join(columns)}) "
                    f"VALUES (%s, {', '.join(placeholders)}) RETURNING {CLIENTE_COLUMNS}",
                    [workspace_id, *params],
                )
                result["cliente_id"] = cur.fetchone()["id"]
                snapshot, fingerprint = snapshot_and_hash(item)
                cur.execute(
                    "INSERT INTO socialmei.crm_cliente_importacoes "
                    "(workspace_id, origem, local_id, cliente_id, fingerprint, snapshot) "
                    "VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
                    (
                        workspace_id,
                        payload.origem,
                        item.local_id,
                        result["cliente_id"],
                        fingerprint,
                        json.dumps(snapshot),
                    ),
                )
    return {"origem": str(payload.origem), "itens": results}
