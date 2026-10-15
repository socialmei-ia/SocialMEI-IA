"""Acesso técnico de leitura, separado do login do navegador."""

import secrets
from typing import Generic, TypeVar

from catalog_data import PRODUCT_COLUMNS, ProdutoOut
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from finance_data import FINANCE_COLUMNS, FinanceOut
from psycopg.rows import dict_row
from pydantic import BaseModel
from sales_data import SALE_COLUMNS, VendaOut
from shared_data import CLIENTE_COLUMNS, ClienteOut, require_shared_data, workspace_slug

from database import connect
from settings import n8n_read_token


def authorize(authorization: str | None = Header(default=None)):
    require_shared_data()
    expected = n8n_read_token()
    if workspace_slug() != "team" or len(expected) < 32:
        raise HTTPException(503, "Integração de leitura não configurada.")
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        supplied.encode(), expected.encode()
    ):
        raise HTTPException(
            401, "Credencial técnica inválida.", headers={"WWW-Authenticate": "Bearer"}
        )


router = APIRouter(
    prefix="/api/v1/integracoes",
    tags=["n8n-read-only"],
    dependencies=[Depends(authorize)],
)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    itens: list[T]
    offset: int
    limit: int
    proximo_offset: int | None


def rows(table, columns, limit, offset, excluded=False):
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cur.execute(
            f"SELECT {columns} FROM socialmei.crm_{table} "
            "WHERE workspace_id = (SELECT id FROM socialmei.workspaces WHERE slug = %s)"
            + (" AND NOT excluida" if excluded else "")
            + " ORDER BY id LIMIT %s OFFSET %s",
            ("team", limit + 1, offset),
        )
        data = cur.fetchall()
        return {
            "itens": data[:limit],
            "offset": offset,
            "limit": limit,
            "proximo_offset": offset + limit if len(data) > limit else None,
        }


@router.get("/resumo")
def summary(response: Response):
    response.headers["Cache-Control"] = "no-store"
    counts = {}
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        for area in ["clientes", "produtos", "vendas", "financeiro"]:
            cur.execute(
                f"SELECT COUNT(*) AS total FROM socialmei.crm_{area} "
                "WHERE workspace_id = (SELECT id FROM socialmei.workspaces WHERE slug = %s)"
                + (" AND NOT excluida" if area in {"vendas", "financeiro"} else ""),
                ("team",),
            )
            counts[area] = cur.fetchone()["total"]
    return {
        "status": "healthy",
        "workspace": "team",
        "acesso": "leitura",
        "registros": counts,
    }


@router.get("/clientes", response_model=Page[ClienteOut])
def clients(
    response: Response,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=2_147_483_647),
):
    response.headers["Cache-Control"] = "no-store"
    return rows("clientes", CLIENTE_COLUMNS, limit, offset)


@router.get("/produtos", response_model=Page[ProdutoOut])
def products(
    response: Response,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=2_147_483_647),
):
    response.headers["Cache-Control"] = "no-store"
    return rows("produtos", PRODUCT_COLUMNS, limit, offset)


@router.get("/vendas", response_model=Page[VendaOut])
def sales(
    response: Response,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=2_147_483_647),
):
    response.headers["Cache-Control"] = "no-store"
    return rows("vendas", SALE_COLUMNS, limit, offset, True)


@router.get("/financeiro", response_model=Page[FinanceOut])
def finance(
    response: Response,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=2_147_483_647),
):
    response.headers["Cache-Control"] = "no-store"
    return rows("financeiro", FINANCE_COLUMNS, limit, offset, True)
