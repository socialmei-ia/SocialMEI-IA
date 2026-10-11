import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from database import check_database, connect, shared_data_enabled

router = APIRouter(prefix="/api/v1", tags=["shared-data"])


def require_shared_data() -> None:
    if not shared_data_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistência compartilhada desativada neste ambiente.",
        )


def workspace_slug() -> str:
    return os.getenv("SOCIALMEI_WORKSPACE_SLUG", "development").strip() or "development"


def workspace_name() -> str:
    return os.getenv("SOCIALMEI_WORKSPACE_NAME", "SocialMEI Development").strip() or "SocialMEI Development"


def ensure_workspace(conn) -> int:
    slug = workspace_slug()
    nome = workspace_name()

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO socialmei.workspaces (slug, nome)
            VALUES (%s, %s)
            ON CONFLICT (slug)
            DO UPDATE SET nome = EXCLUDED.nome, atualizado_em = NOW()
            RETURNING id
            """,
            (slug, nome),
        )
        row = cur.fetchone()
        return int(row["id"])


class ClienteCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=160)
    telefone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    instagram: str | None = Field(default=None, max_length=160)
    status: str = Field(default="Ativo", min_length=1, max_length=30)
    observacao: str | None = Field(default=None, max_length=5000)
    tags: list[str] = Field(default_factory=list)
    legacy_local_id: int | None = Field(default=None, ge=0)


class ClienteUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=160)
    telefone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    instagram: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, min_length=1, max_length=30)
    observacao: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = None


class ClienteOut(ClienteCreate):
    id: int
    criado_em: Any
    atualizado_em: Any


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    tags = row.get("tags")
    if isinstance(tags, str):
        row["tags"] = json.loads(tags)
    return row


@router.get("/clientes", response_model=list[ClienteOut])
def list_clientes():
    require_shared_data()

    with connect() as conn:
        workspace_id = ensure_workspace(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, nome, telefone, email, instagram, status, observacao,
                       tags, legacy_local_id, criado_em, atualizado_em
                FROM socialmei.crm_clientes
                WHERE workspace_id = %s
                ORDER BY nome, id
                """,
                (workspace_id,),
            )
            return [normalize_row(row) for row in cur.fetchall()]


@router.post("/clientes", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def create_cliente(payload: ClienteCreate):
    require_shared_data()

    with connect() as conn:
        workspace_id = ensure_workspace(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO socialmei.crm_clientes (
                    workspace_id, nome, telefone, email, instagram, status,
                    observacao, tags, legacy_local_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                RETURNING id, nome, telefone, email, instagram, status, observacao,
                          tags, legacy_local_id, criado_em, atualizado_em
                """,
                (
                    workspace_id,
                    payload.nome,
                    payload.telefone,
                    payload.email,
                    payload.instagram,
                    payload.status,
                    payload.observacao,
                    json.dumps(payload.tags),
                    payload.legacy_local_id,
                ),
            )
            return normalize_row(cur.fetchone())


@router.get("/clientes/{cliente_id}", response_model=ClienteOut)
def get_cliente(cliente_id: int):
    require_shared_data()

    with connect() as conn:
        workspace_id = ensure_workspace(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, nome, telefone, email, instagram, status, observacao,
                       tags, legacy_local_id, criado_em, atualizado_em
                FROM socialmei.crm_clientes
                WHERE workspace_id = %s AND id = %s
                """,
                (workspace_id, cliente_id),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")

    return normalize_row(row)


@router.patch("/clientes/{cliente_id}", response_model=ClienteOut)
def update_cliente(cliente_id: int, payload: ClienteUpdate):
    require_shared_data()
    values = payload.model_dump(exclude_unset=True)

    if not values:
        return get_cliente(cliente_id)

    allowed = {
        "nome": "nome",
        "telefone": "telefone",
        "email": "email",
        "instagram": "instagram",
        "status": "status",
        "observacao": "observacao",
        "tags": "tags",
    }

    assignments = []
    params: list[Any] = []
    for key, value in values.items():
        column = allowed[key]
        if key == "tags":
            assignments.append(f"{column} = %s::jsonb")
            params.append(json.dumps(value))
        else:
            assignments.append(f"{column} = %s")
            params.append(value)

    assignments.append("atualizado_em = NOW()")

    with connect() as conn:
        workspace_id = ensure_workspace(conn)
        params.extend([workspace_id, cliente_id])

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                UPDATE socialmei.crm_clientes
                SET {", ".join(assignments)}
                WHERE workspace_id = %s AND id = %s
                RETURNING id, nome, telefone, email, instagram, status, observacao,
                          tags, legacy_local_id, criado_em, atualizado_em
                """,
                params,
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")

    return normalize_row(row)


@router.delete("/clientes/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cliente(cliente_id: int):
    require_shared_data()

    with connect() as conn:
        workspace_id = ensure_workspace(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM socialmei.crm_clientes
                WHERE workspace_id = %s AND id = %s
                """,
                (workspace_id, cliente_id),
            )
            deleted = cur.rowcount

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def database_health_payload() -> dict[str, Any]:
    if not shared_data_enabled():
        return {
            "status": "disabled",
            "shared_data": False,
        }

    check_database()
    return {
        "status": "healthy",
        "shared_data": True,
        "workspace": workspace_slug(),
    }
