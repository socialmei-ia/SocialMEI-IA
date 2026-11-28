from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from psycopg.rows import dict_row
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from sales_data import Money, stock_context
from shared_data import MAX_SAFE_ID, ensure_workspace, require_shared_data
from account_auth import current

from database import connect

router = APIRouter(prefix="/api/v1/produtos", tags=["catalogo"])
money_adapter = TypeAdapter(Money)


def validate_catalog_amount(value):
    money_adapter.validate_python(value)
    return value


CatalogAmount = Annotated[float, BeforeValidator(validate_catalog_amount)]


class ProdutoFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nome: str | None = Field(default=None, min_length=1, max_length=160)
    categoria: str | None = Field(default=None, max_length=80)
    descricao: str | None = Field(default=None, max_length=2000)
    tipo: Literal["Produto", "Serviço"] | None = None
    preco: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    custo: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    estoque: int | None = Field(default=None, ge=0, le=MAX_SAFE_ID, strict=True)
    minimo: int | None = Field(default=None, ge=0, le=MAX_SAFE_ID, strict=True)
    status: str | None = Field(default=None, min_length=1, max_length=30)
    duracao_minutos: int | None = Field(default=None, ge=1, le=1440, strict=True)

    @field_validator("categoria", "descricao")
    @classmethod
    def valid_detail_text(cls, value):
        if value is not None:
            if "\x00" in value:
                raise ValueError("Texto inválido.")
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise ValueError("Texto inválido.") from None
        return value


class ProductSnapshot(ProdutoFields):
    nome: str = Field(min_length=1, max_length=160)
    categoria: str = Field(default="", max_length=80)
    descricao: str = Field(default="", max_length=2000)
    tipo: Literal["Produto", "Serviço"] = "Produto"
    preco: float = Field(ge=0, allow_inf_nan=False)
    custo: float = Field(default=0, ge=0, allow_inf_nan=False)
    status: str = Field(default="Ativo", min_length=1, max_length=30)

    @model_validator(mode="after")
    def inventory_matches_type(self):
        if self.tipo != "Serviço" and self.duracao_minutos is not None:
            raise ValueError("Somente serviços possuem duração.")
        for key in ("estoque", "minimo"):
            value = getattr(self, key)
            if self.tipo == "Serviço" and value is not None:
                raise ValueError("Serviços não possuem estoque ou mínimo.")
            if self.tipo == "Produto" and value is None:
                if key in self.model_fields_set:
                    raise ValueError("Produto exige estoque e mínimo não nulos.")
                setattr(self, key, 0)
        return self


class ProdutoCreate(ProductSnapshot):
    preco: CatalogAmount
    custo: CatalogAmount = 0


class ProdutoUpdate(ProdutoFields):
    preco: CatalogAmount | None = None
    custo: CatalogAmount | None = None
    expected_version: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def non_nullable_fields(self):
        for key in ("nome", "tipo", "preco", "custo", "status", "categoria", "descricao"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} não pode ser nulo.")
        return self


class ProdutoOut(ProductSnapshot):
    id: int
    versao: int
    criado_em: datetime
    atualizado_em: datetime


class EstoqueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    delta: int = Field(ge=-MAX_SAFE_ID, le=MAX_SAFE_ID, strict=True)
    expected_version: int = Field(ge=1, strict=True)
    operation_id: UUID | None = None
    motivo: str = Field(default="Ajuste de estoque", min_length=1, max_length=240)

    @field_validator("motivo")
    @classmethod
    def valid_reason(cls, value):
        return ProdutoFields.valid_detail_text(value)

    @model_validator(mode="after")
    def nonzero_delta(self):
        if self.delta == 0:
            raise ValueError("Informe uma alteração de estoque diferente de zero.")
        return self


PRODUCT_COLUMNS = "id, nome, categoria, descricao, tipo, preco, custo, estoque, minimo, status, duracao_minutos, versao, criado_em, atualizado_em"


def insert_product(cur, workspace_id, product):
    values = product.model_dump()
    for key in ("preco", "custo"):
        values[key] = Decimal(str(values[key]))
    stock_context(cur, workspace_id, "Saldo inicial do produto")
    cur.execute(
        f"INSERT INTO socialmei.crm_produtos (workspace_id, {', '.join(values)}) "
        f"VALUES (%s, {', '.join(['%s'] * len(values))}) RETURNING {PRODUCT_COLUMNS}",
        [workspace_id, *values.values()],
    )
    return cur.fetchone()


def lock_product(cur, workspace_id, product_id, version):
    cur.execute(
        f"SELECT {PRODUCT_COLUMNS} FROM socialmei.crm_produtos "
        "WHERE workspace_id = %s AND id = %s FOR UPDATE",
        (workspace_id, product_id),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Item não encontrado.")
    if row["versao"] != version:
        raise HTTPException(
            409, "Item alterado por outra sessão. Recarregue antes de salvar."
        )
    return row


def ensure_no_active_stock_sales(cur, workspace_id, product_id):
    cur.execute(
        "SELECT 1 FROM socialmei.crm_vendas WHERE workspace_id = %s AND produto_id = %s AND estoque_aplicado LIMIT 1",
        (workspace_id, product_id),
    )
    if cur.fetchone():
        raise HTTPException(
            409,
            "O item possui vendas com estoque aplicado. Cancele essas vendas antes de excluir ou mudar o tipo.",
        )


@router.get("", response_model=list[ProdutoOut])
def list_products(
    q: str = Query(default="", max_length=160),
    tipo: Literal["Produto", "Serviço"] | None = Query(default=None),
    status: str | None = Query(default=None, min_length=1, max_length=30),
    estoque_baixo: bool = Query(default=False),
):
    for value in (q, status):
        if value is not None:
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise HTTPException(422, "Filtro de catálogo inválido.") from None
            if "\x00" in value:
                raise HTTPException(422, "Filtro de catálogo inválido.")
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        conditions = ["workspace_id = %s"]
        parameters = [workspace_id]
        if q.strip():
            # Literal substring: percent and underscore are not SQL wildcards.
            conditions.append("strpos(lower(nome), lower(%s)) > 0")
            parameters.append(q.strip())
        if tipo is not None:
            conditions.append("tipo = %s")
            parameters.append(tipo)
        if status is not None:
            conditions.append("status = %s")
            parameters.append(status)
        if estoque_baixo:
            conditions.append("tipo = 'Produto' AND estoque <= minimo")
        cur.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM socialmei.crm_produtos WHERE "
            + " AND ".join(conditions)
            + " ORDER BY nome, id",
            parameters,
        )
        return cur.fetchall()


@router.post("", response_model=ProdutoOut, status_code=201)
def create_product(payload: ProdutoCreate):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        return insert_product(cur, ensure_workspace(conn), payload)


@router.get("/{produto_id}", response_model=ProdutoOut)
def get_product(produto_id: int):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        cur.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM socialmei.crm_produtos WHERE workspace_id = %s AND id = %s",
            (workspace_id, produto_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Item não encontrado.")
        return row


@router.patch("/{produto_id}", response_model=ProdutoOut)
def update_product(produto_id: int, payload: ProdutoUpdate):
    require_shared_data()
    values = payload.model_dump(exclude_unset=True)
    version = values.pop("expected_version")
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        current = lock_product(cur, workspace_id, produto_id, version)
        if "tipo" in values and values["tipo"] != current["tipo"]:
            ensure_no_active_stock_sales(cur, workspace_id, produto_id)
        merged = {key: current[key] for key in ProdutoFields.model_fields}
        try:
            ProductSnapshot.model_validate({**merged, **values})
        except ValidationError:
            raise HTTPException(
                422, "Confira o tipo e os campos de estoque do item."
            ) from None
        if not values:
            return current
        if "estoque" in values:
            stock_context(cur, workspace_id, "Ajuste pelo cadastro do produto", product_id=produto_id)
        cur.execute(
            f"UPDATE socialmei.crm_produtos SET {', '.join(key + ' = %s' for key in values)}, "
            f"versao = versao + 1, atualizado_em = NOW() WHERE workspace_id = %s AND id = %s RETURNING {PRODUCT_COLUMNS}",
            [
                *[
                    Decimal(str(value)) if key in {"preco", "custo"} else value
                    for key, value in values.items()
                ],
                workspace_id,
                produto_id,
            ],
        )
        return cur.fetchone()


@router.post("/{produto_id}/estoque", response_model=ProdutoOut)
def adjust_stock(produto_id: int, payload: EstoqueUpdate):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        if payload.operation_id:
            cur.execute(
                "SELECT current_stock-previous_stock AS delta,reason,product_version FROM socialmei.stock_movements "
                "WHERE workspace_id=%s AND product_id=%s AND operation_id=%s AND sale_id IS NULL",
                (workspace_id, produto_id, payload.operation_id),
            )
            replay = cur.fetchone()
            if replay:
                if (replay["delta"], replay["reason"], replay["product_version"]) != (
                    payload.delta, payload.motivo, payload.expected_version + 1
                ):
                    raise HTTPException(409, "Identificador de ajuste usado com outros dados.")
                cur.execute(f"SELECT {PRODUCT_COLUMNS} FROM socialmei.crm_produtos WHERE workspace_id=%s AND id=%s",
                            (workspace_id, produto_id))
                product = cur.fetchone()
                if not product:
                    raise HTTPException(404, "Item não encontrado.")
                return product
        current = lock_product(cur, workspace_id, produto_id, payload.expected_version)
        if current["tipo"] != "Produto":
            raise HTTPException(422, "Serviços não possuem estoque.")
        stock = current["estoque"] + payload.delta
        if not 0 <= stock <= MAX_SAFE_ID:
            raise HTTPException(
                409, "Ajuste produziria estoque negativo ou acima do limite."
            )
        stock_context(cur, workspace_id, payload.motivo, product_id=produto_id, operation_id=payload.operation_id)
        cur.execute(
            f"UPDATE socialmei.crm_produtos SET estoque = %s, versao = versao + 1, atualizado_em = NOW() "
            f"WHERE workspace_id = %s AND id = %s RETURNING {PRODUCT_COLUMNS}",
            (stock, workspace_id, produto_id),
        )
        return cur.fetchone()


@router.get("/{produto_id}/movimentacoes")
def stock_history(
    produto_id: int,
    tipo: Literal["entrada", "saida"] | None = None,
    before_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
):
    workspace = current()["workspace_id"]
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cur.execute("SET LOCAL statement_timeout='4s'")
        cur.execute("SELECT estoque,minimo,tipo FROM socialmei.crm_produtos WHERE workspace_id=%s AND id=%s",
                    (workspace, produto_id))
        product = cur.fetchone()
        if product is None:
            raise HTTPException(404, "Item não encontrado.")
        params = (workspace, produto_id)
        cur.execute(
            "SELECT count(*) AS count,"
            "COALESCE(sum(GREATEST(current_stock-previous_stock,0)),0)::text AS entradas,"
            "COALESCE(sum(GREATEST(previous_stock-current_stock,0)),0)::text AS saidas "
            "FROM socialmei.stock_movements WHERE workspace_id=%s AND product_id=%s", params,
        )
        totals = cur.fetchone()
        cur.execute(
            "SELECT id,sale_id,actor_id,previous_stock,current_stock,reason,occurred_at "
            "FROM socialmei.stock_movements WHERE workspace_id=%s AND product_id=%s "
            "AND (%s::bigint IS NULL OR id<%s) "
            "AND (%s::text IS NULL OR (%s='entrada')=(current_stock>previous_stock)) "
            "ORDER BY id DESC LIMIT %s", (*params, before_id, before_id, tipo, tipo, limit+1),
        )
        rows = cur.fetchall()
        return {"workspace_id": workspace, "produto_id": produto_id, "estoque": product["estoque"],
                "estoque_baixo": product["tipo"] == "Produto" and product["estoque"] <= product["minimo"],
                "totais": totals, "items": rows[:limit], "next_before_id": rows[limit-1]["id"] if len(rows)>limit else None}


@router.delete("/{produto_id}", status_code=204)
def delete_product(produto_id: int, expected_version: int = Query(ge=1)):
    require_shared_data()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        workspace_id = ensure_workspace(conn)
        lock_product(cur, workspace_id, produto_id, expected_version)
        ensure_no_active_stock_sales(cur, workspace_id, produto_id)
        cur.execute(
            "DELETE FROM socialmei.crm_produtos WHERE workspace_id = %s AND id = %s",
            (workspace_id, produto_id),
        )
    return Response(status_code=204)
