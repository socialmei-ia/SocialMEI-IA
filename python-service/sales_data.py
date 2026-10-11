import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shared_data import MAX_SAFE_ID, ensure_workspace, require_shared_data

from database import connect

router = APIRouter(prefix="/api/v1/vendas", tags=["vendas"])
Money = Annotated[
    Decimal, Field(ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
]
MAX_MONEY = Decimal("9999999999999.99")
SALE_COLUMNS = "id, cliente_id, produto_id, cliente, item, tipo_item, data, quantidade, preco, desconto, valor, pagamento, observacao, status, estoque_aplicado, importada, excluida, versao, criado_em, atualizado_em"


class VendaFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cliente_id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    produto_id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    data: date
    quantidade: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    preco: Money
    desconto: Money = Decimal(0)
    pagamento: str = Field(default="Pix", min_length=1, max_length=40)
    observacao: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def valid_total(self):
        if self.desconto > self.preco * self.quantidade:
            raise ValueError("Desconto maior que o valor da venda.")
        if self.preco * self.quantidade - self.desconto > MAX_MONEY:
            raise ValueError("Valor da venda acima do limite.")
        return self


class VendaCreate(VendaFields):
    operation_id: UUID
    status: Literal["Rascunho", "Pendente"] = "Pendente"


class VendaEdit(VendaFields):
    operation_id: UUID
    expected_version: int = Field(ge=1, strict=True)


class VendaAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    expected_version: int = Field(ge=1, strict=True)


class VendaOut(BaseModel):
    id: int
    cliente_id: int | None
    produto_id: int | None
    cliente: str
    item: str
    tipo_item: str | None
    data: date
    quantidade: int
    preco: float | None
    desconto: float
    valor: float
    pagamento: str
    observacao: str
    status: str
    estoque_aplicado: bool
    importada: bool
    excluida: bool
    versao: int
    criado_em: datetime
    atualizado_em: datetime


def operation_fingerprint(kind, sale_id, payload):
    text = json.dumps(
        {"acao": kind, "venda_id": sale_id, "dados": payload.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode()).hexdigest()


def begin_operation(cur, workspace_id, kind, sale_id, payload):
    fingerprint = operation_fingerprint(kind, sale_id, payload)
    cur.execute(
        "SELECT fingerprint, resposta FROM socialmei.crm_venda_operacoes WHERE workspace_id = %s AND operation_id = %s",
        (workspace_id, payload.operation_id),
    )
    previous = cur.fetchone()
    if previous and previous["fingerprint"] != fingerprint:
        raise HTTPException(409, "Identidade de operação já usada com outros dados.")
    return fingerprint, previous["resposta"] if previous else None


def finish_operation(cur, workspace_id, payload, fingerprint, row):
    response = VendaOut.model_validate(row).model_dump(mode="json")
    cur.execute(
        "INSERT INTO socialmei.crm_venda_operacoes (workspace_id, operation_id, fingerprint, resposta) VALUES (%s, %s, %s, %s::jsonb)",
        (workspace_id, payload.operation_id, fingerprint, json.dumps(response)),
    )
    return response


def lock_sale(cur, workspace_id, sale_id, version):
    cur.execute(
        f"SELECT {SALE_COLUMNS} FROM socialmei.crm_vendas WHERE workspace_id = %s AND id = %s FOR UPDATE",
        (workspace_id, sale_id),
    )
    sale = cur.fetchone()
    if not sale or sale["excluida"]:
        raise HTTPException(404, "Venda não encontrada.")
    if sale["versao"] != version:
        raise HTTPException(
            409, "Venda alterada por outra sessão. Recarregue antes de salvar."
        )
    return sale


def linked_client(cur, workspace_id, client_id):
    cur.execute(
        "SELECT nome FROM socialmei.crm_clientes WHERE workspace_id = %s AND id = %s",
        (workspace_id, client_id),
    )
    client = cur.fetchone()
    if not client:
        raise HTTPException(422, "Cliente não existe neste workspace.")
    return client


def linked_product(cur, workspace_id, product_id):
    cur.execute(
        "SELECT id, nome, tipo, estoque FROM socialmei.crm_produtos WHERE workspace_id = %s AND id = %s FOR UPDATE",
        (workspace_id, product_id),
    )
    product = cur.fetchone()
    if not product:
        raise HTTPException(422, "Item não existe neste workspace.")
    return product


def move_stock(cur, workspace_id, previous, product, quantity, active):
    deltas = {}
    if previous and previous["estoque_aplicado"]:
        if previous["produto_id"] is None:
            raise HTTPException(
                409, "Item de estoque original indisponível; não foi possível estornar."
            )
        deltas[previous["produto_id"]] = previous["quantidade"]
    applied = bool(active and product and product["tipo"] == "Produto")
    if applied:
        deltas[product["id"]] = deltas.get(product["id"], 0) - quantity
    for product_id in sorted(deltas):
        delta = deltas[product_id]
        if not delta:
            continue
        item = linked_product(cur, workspace_id, product_id)
        if item["tipo"] != "Produto" or not 0 <= item["estoque"] + delta <= MAX_SAFE_ID:
            raise HTTPException(
                409,
                "Estoque insuficiente ou estorno acima do limite. Nenhuma alteração foi salva.",
            )
        cur.execute(
            "UPDATE socialmei.crm_produtos SET estoque = estoque + %s, versao = versao + 1, atualizado_em = NOW() WHERE workspace_id = %s AND id = %s",
            (delta, workspace_id, product_id),
        )
    return applied


@router.get("", response_model=list[VendaOut])
def list_sales():
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        cur.execute(
            f"SELECT {SALE_COLUMNS} FROM socialmei.crm_vendas WHERE workspace_id = %s AND NOT excluida ORDER BY data DESC, id DESC",
            (workspace_id,),
        )
        return cur.fetchall()


@router.get("/{venda_id}", response_model=VendaOut)
def get_sale(venda_id: int):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        cur.execute(
            f"SELECT {SALE_COLUMNS} FROM socialmei.crm_vendas WHERE workspace_id = %s AND id = %s AND NOT excluida",
            (workspace_id, venda_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Venda não encontrada.")
        return row


@router.post("", response_model=VendaOut, status_code=201)
def create_sale(payload: VendaCreate):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        fingerprint, replay = begin_operation(cur, workspace_id, "criar", None, payload)
        if replay:
            return replay
        client = linked_client(cur, workspace_id, payload.cliente_id)
        product = linked_product(cur, workspace_id, payload.produto_id)
        applied = move_stock(
            cur,
            workspace_id,
            None,
            product,
            payload.quantidade,
            payload.status == "Pendente",
        )
        values = payload.model_dump(exclude={"operation_id"})
        values.update(
            cliente=client["nome"],
            item=product["nome"],
            tipo_item=product["tipo"],
            valor=payload.preco * payload.quantidade - payload.desconto,
            estoque_aplicado=applied,
        )
        cur.execute(
            f"INSERT INTO socialmei.crm_vendas (workspace_id, {', '.join(values)}) VALUES (%s, {', '.join(['%s'] * len(values))}) RETURNING {SALE_COLUMNS}",
            [workspace_id, *values.values()],
        )
        return finish_operation(cur, workspace_id, payload, fingerprint, cur.fetchone())


@router.patch("/{venda_id}", response_model=VendaOut)
def edit_sale(venda_id: int, payload: VendaEdit):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        fingerprint, replay = begin_operation(
            cur, workspace_id, "editar", venda_id, payload
        )
        if replay:
            return replay
        previous = lock_sale(cur, workspace_id, venda_id, payload.expected_version)
        if previous["importada"] or previous["status"] not in {"Pendente", "Rascunho"}:
            raise HTTPException(
                409,
                "Esta venda mantém seu histórico. Duplique como rascunho para criar outra.",
            )
        client = linked_client(cur, workspace_id, payload.cliente_id)
        product = linked_product(cur, workspace_id, payload.produto_id)
        applied = move_stock(
            cur,
            workspace_id,
            previous,
            product,
            payload.quantidade,
            previous["status"] == "Pendente",
        )
        values = payload.model_dump(exclude={"operation_id", "expected_version"})
        values.update(
            cliente=client["nome"],
            item=product["nome"],
            tipo_item=product["tipo"],
            valor=payload.preco * payload.quantidade - payload.desconto,
            estoque_aplicado=applied,
        )
        cur.execute(
            f"UPDATE socialmei.crm_vendas SET {', '.join(k + ' = %s' for k in values)}, versao = versao + 1, atualizado_em = NOW() WHERE workspace_id = %s AND id = %s RETURNING {SALE_COLUMNS}",
            [*values.values(), workspace_id, venda_id],
        )
        return finish_operation(cur, workspace_id, payload, fingerprint, cur.fetchone())


def change_sale(venda_id, payload, kind):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        fingerprint, replay = begin_operation(
            cur, workspace_id, kind, venda_id, payload
        )
        if replay:
            return replay
        previous = lock_sale(cur, workspace_id, venda_id, payload.expected_version)
        target = {
            "registrar": "Pendente",
            "pagar": "Pago",
            "cancelar": "Cancelado",
            "excluir": "Cancelado",
        }[kind]
        if kind in {"pagar", "registrar"} and previous["status"] == "Cancelado":
            raise HTTPException(
                409, "Venda cancelada não pode ser reativada. Crie outra venda."
            )
        if kind == "registrar" and previous["status"] not in {"Rascunho", "Pendente"}:
            raise HTTPException(409, "Venda já paga não retorna a pendente.")
        if previous["status"] == target and kind != "excluir":
            return finish_operation(cur, workspace_id, payload, fingerprint, previous)
        active = target in {"Pendente", "Pago"}
        applied = False
        if not previous["importada"]:
            if active and previous["status"] in {"Pendente", "Pago"}:
                applied = previous["estoque_aplicado"]
            else:
                product = (
                    linked_product(cur, workspace_id, previous["produto_id"])
                    if active
                    else None
                )
                applied = move_stock(
                    cur, workspace_id, previous, product, previous["quantidade"], active
                )
        cur.execute(
            f"UPDATE socialmei.crm_vendas SET status = %s, estoque_aplicado = %s, excluida = %s, versao = versao + 1, atualizado_em = NOW() WHERE workspace_id = %s AND id = %s RETURNING {SALE_COLUMNS}",
            (target, applied, kind == "excluir", workspace_id, venda_id),
        )
        return finish_operation(cur, workspace_id, payload, fingerprint, cur.fetchone())


@router.post("/{venda_id}/registrar", response_model=VendaOut)
def register_sale(venda_id: int, payload: VendaAction):
    return change_sale(venda_id, payload, "registrar")


@router.post("/{venda_id}/pagar", response_model=VendaOut)
def pay_sale(venda_id: int, payload: VendaAction):
    return change_sale(venda_id, payload, "pagar")


@router.post("/{venda_id}/cancelar", response_model=VendaOut)
def cancel_sale(venda_id: int, payload: VendaAction):
    return change_sale(venda_id, payload, "cancelar")


@router.post("/{venda_id}/excluir", response_model=VendaOut)
def remove_sale(venda_id: int, payload: VendaAction):
    return change_sale(venda_id, payload, "excluir")
