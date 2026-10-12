"""Transferência inicial, atômica, do notebook para o workspace da equipe."""

import hashlib
import json
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from catalog_data import ProdutoOut
from fastapi import APIRouter, HTTPException
from finance_import import LegacyEntry
from psycopg.rows import dict_row
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from sale_import import LegacySale
from shared_data import (
    MAX_SAFE_ID,
    ClienteOut,
    ensure_workspace,
    require_shared_data,
    workspace_slug,
)

from database import connect

router = APIRouter(prefix="/api/v1/transferencias", tags=["transferencia"])
PreciseAmount = Annotated[
    Decimal, Field(ge=0, max_digits=50, decimal_places=20, allow_inf_nan=False)
]


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    versao: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    criado_em: AwareDatetime
    atualizado_em: AwareDatetime


class TransferClient(ClienteOut, Metadata):
    id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    versao: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    criado_em: AwareDatetime
    atualizado_em: AwareDatetime
    total: PreciseAmount | None = None
    pendente: PreciseAmount | None = None


class TransferProduct(ProdutoOut, Metadata):
    id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    versao: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    criado_em: AwareDatetime
    atualizado_em: AwareDatetime
    preco: PreciseAmount
    custo: PreciseAmount


class TransferSale(LegacySale, Metadata):
    tipo_item: Literal["Produto", "Serviço"] | None = None
    estoque_aplicado: bool = Field(strict=True)
    importada: bool = Field(strict=True)
    excluida: bool = Field(strict=True)

    @model_validator(mode="after")
    def valid_stock_state(self):
        if not self.importada:
            if self.preco is None:
                raise ValueError("Venda operacional exige preço.")
            base = self.preco * self.quantidade
            if self.desconto > base or self.valor != base - self.desconto:
                raise ValueError(
                    "Total da venda operacional não corresponde aos campos."
                )
        if self.estoque_aplicado and (
            self.importada
            or self.excluida
            or self.tipo_item != "Produto"
            or self.status not in {"Pendente", "Pago"}
            or self.produto_id is None
        ):
            raise ValueError("Estado de estoque da venda inválido.")
        return self


class TransferFinance(LegacyEntry, Metadata):
    importada: bool = Field(strict=True)
    excluida: bool = Field(strict=True)


class TransferPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formato: Literal["socialmei-workspace-transfer"]
    versao_formato: Literal[1]
    origem: UUID
    workspace_origem: Literal["development"]
    exportado_em: AwareDatetime
    clientes: list[TransferClient] = Field(max_length=500)
    produtos: list[TransferProduct] = Field(max_length=500)
    vendas: list[TransferSale] = Field(max_length=500)
    financeiro: list[TransferFinance] = Field(max_length=500)

    @field_validator("versao_formato", mode="before")
    @classmethod
    def strict_format_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Versão de formato inválida.")
        return value

    @model_validator(mode="after")
    def validate_snapshot(self):
        if not any([self.clientes, self.produtos, self.vendas, self.financeiro]):
            raise ValueError("A fonte não contém registros.")
        for records in [self.clientes, self.produtos, self.vendas, self.financeiro]:
            if len({r.id for r in records}) != len(records):
                raise ValueError("IDs repetidos na fonte.")
        clients = {r.id for r in self.clientes}
        products = {r.id: r for r in self.produtos}
        for sale in self.vendas:
            if sale.cliente_id is not None and sale.cliente_id not in clients:
                raise ValueError("Vínculo de cliente ausente da fonte.")
            if sale.produto_id is not None and sale.produto_id not in products:
                raise ValueError("Vínculo de item ausente da fonte.")
            if sale.estoque_aplicado and products[sale.produto_id].tipo != "Produto":
                raise ValueError("Baixa de estoque vinculada a serviço.")
        for entry in self.financeiro:
            if entry.cliente_id is not None and entry.cliente_id not in clients:
                raise ValueError("Vínculo financeiro ausente da fonte.")
        encoded = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, allow_nan=False
        )
        if len(encoded.encode()) > 2_000_000:
            raise ValueError("A transferência excede 2 MB.")
        return self


class TransferConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pacote: TransferPacket
    preview_token: str = Field(pattern=r"^[a-f0-9]{64}$")


def require_team():
    require_shared_data()
    if workspace_slug() != "team":
        raise HTTPException(
            503, "Transferência disponível somente no workspace da equipe."
        )


def packet_fingerprint(packet):
    # Timestamp de exportação não cria um dataset novo quando a fonte não mudou.
    data = packet.model_dump(mode="json", exclude={"exportado_em"})
    for name in ["clientes", "produtos", "vendas", "financeiro"]:
        data[name].sort(key=lambda r: r["id"])
    return hashlib.sha256(
        json.dumps(
            data,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def receipt(cur, workspace_id, packet):
    cur.execute(
        "SELECT origem, fingerprint, resposta FROM socialmei.crm_transferencias WHERE workspace_id = %s",
        (workspace_id,),
    )
    row = cur.fetchone()
    if row and (
        str(row["origem"]) != str(packet.origem)
        or row["fingerprint"] != packet_fingerprint(packet)
    ):
        raise HTTPException(
            409,
            "Este workspace já recebeu uma transferência diferente. Não troque a origem nem reaplique outro snapshot.",
        )
    return row["resposta"] if row else None


def destination_state(cur, workspace_id):
    state = {}
    for name in ["clientes", "produtos", "vendas", "financeiro"]:
        cur.execute(
            f"SELECT id, versao FROM socialmei.crm_{name} WHERE workspace_id = %s ORDER BY id",
            (workspace_id,),
        )
        state[name] = cur.fetchall()
    token = hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return token, {name: len(rows) for name, rows in state.items()}


def insert_record(cur, workspace_id, table, record, client_map, product_map):
    values = record.model_dump(exclude={"id"})
    if table == "clientes":
        # Identidade de importação local antiga não identifica o novo workspace.
        values["legacy_local_id"] = None
    if "cliente_id" in values:
        values["cliente_id"] = client_map.get(values["cliente_id"])
    if "produto_id" in values:
        values["produto_id"] = product_map.get(values["produto_id"])
    params = [json.dumps(v) if k == "tags" else v for k, v in values.items()]
    placeholders = ["%s::jsonb" if k == "tags" else "%s" for k in values]
    cur.execute(
        f"INSERT INTO socialmei.crm_{table} (workspace_id, {', '.join(values)}) VALUES (%s, {', '.join(placeholders)}) RETURNING id",
        [workspace_id, *params],
    )
    return cur.fetchone()["id"]


@router.post("/preview")
def preview_transfer(packet: TransferPacket):
    require_team()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cur.execute(
            "SELECT id FROM socialmei.workspaces WHERE slug = %s", (workspace_slug(),)
        )
        workspace = cur.fetchone()
        workspace_id = workspace["id"] if workspace else None
        previous = receipt(cur, workspace_id, packet)
        token, current = destination_state(cur, workspace_id)
        return {
            "origem": str(packet.origem),
            "workspace_destino": workspace_slug(),
            "ja_transferido": previous is not None,
            "preview_token": token,
            "fonte": {name: len(getattr(packet, name)) for name in current},
            "destino_atual": current,
            "vendas_com_baixa_preservada": sum(
                v.estoque_aplicado for v in packet.vendas
            ),
            "vendas_excluidas": sum(v.excluida for v in packet.vendas),
            "financeiro_excluido": sum(v.excluida for v in packet.financeiro),
        }


@router.post("/confirmar")
def confirm_transfer(payload: TransferConfirm):
    require_team()
    packet = payload.pacote
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        previous = receipt(cur, workspace_id, packet)
        if previous:
            return {**previous, "ja_transferido": True}
        token, _ = destination_state(cur, workspace_id)
        if token != payload.preview_token:
            raise HTTPException(
                409,
                "O destino mudou após a prévia. Confira uma nova prévia antes de confirmar.",
            )
        maps = {name: {} for name in ["clientes", "produtos", "vendas", "financeiro"]}
        for name, mapping in maps.items():
            for record in getattr(packet, name):
                mapping[str(record.id)] = insert_record(
                    cur,
                    workspace_id,
                    name,
                    record,
                    {int(k): v for k, v in maps["clientes"].items()},
                    {int(k): v for k, v in maps["produtos"].items()},
                )
        response = {
            "origem": str(packet.origem),
            "workspace_destino": workspace_slug(),
            "ja_transferido": False,
            "quantidades": {name: len(mapping) for name, mapping in maps.items()},
            "mapa_ids": maps,
        }
        cur.execute(
            "INSERT INTO socialmei.crm_transferencias (workspace_id, origem, fingerprint, snapshot, resposta) VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)",
            (
                workspace_id,
                packet.origem,
                packet_fingerprint(packet),
                json.dumps(packet.model_dump(mode="json"), ensure_ascii=False),
                json.dumps(response),
            ),
        )
        return response
