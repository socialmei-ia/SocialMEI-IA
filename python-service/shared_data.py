import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from psycopg.errors import UniqueViolation, ForeignKeyViolation
from psycopg.rows import dict_row
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from database import check_database, connect, shared_data_enabled
from contact_validation import validate_phone, validate_instagram
from auth_context import principal
from account_auth import enabled as auth_enabled, require_enabled as require_auth_enabled
import settings

router = APIRouter(prefix="/api/v1", tags=["shared-data"])


def require_shared_data() -> None:
    if not shared_data_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistência compartilhada desativada neste ambiente.",
        )


def workspace_slug() -> str:
    if principal.get():
        return principal.get()["workspace_slug"]
    return settings.workspace_slug()


def workspace_name() -> str:
    if principal.get():
        return principal.get()["nome_negocio"]
    return settings.workspace_name()


def ensure_workspace(conn) -> int:
    if principal.get():
        user = principal.get()
        row = conn.execute(
            "SELECT id FROM socialmei.workspaces WHERE id=%s AND slug=%s FOR UPDATE",
            (user["workspace_id"], user["workspace_slug"]),
        ).fetchone()
        if not row:
            raise HTTPException(403, "Negócio indisponível.")
        return int(row[0])
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


Tag = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
MAX_SAFE_ID = 9_007_199_254_740_991


class ClienteFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nome: str | None = Field(default=None, min_length=1, max_length=160)
    telefone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    instagram: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, min_length=1, max_length=30)
    observacao: str | None = Field(default=None, max_length=5000)
    tags: list[Tag] | None = Field(default=None, max_length=50)
    cidade: str | None = Field(default=None, max_length=160)
    desde: str | None = Field(default=None, max_length=160)
    categoria: str | None = Field(default=None, max_length=160)
    cadastro_original_em: AwareDatetime | None = Field(default=None, alias="criadoEm")
    observacao_atualizada_em: AwareDatetime | None = Field(
        default=None, alias="observacaoAtualizada"
    )
    avatar_url: str | None = Field(default=None, alias="avatarUrl", max_length=2048)
    foto: str | None = Field(default=None, max_length=2048)
    # Snapshot legado: não representa um saldo calculado pelo backend.
    ultima: str | None = Field(default=None, max_length=80)
    total: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    pendente: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ClienteCreate(ClienteFields):
    nome: str = Field(min_length=1, max_length=160)
    status: str = Field(default="Ativo", min_length=1, max_length=30)
    tags: list[Tag] = Field(default_factory=list, max_length=50)
    legacy_local_id: int | None = Field(default=None, ge=0, le=MAX_SAFE_ID, strict=True)


class ClienteUpdate(ClienteFields):
    expected_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def reject_required_nulls(self):
        for field in ("nome", "status", "tags", "expected_version"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} não pode ser nulo.")
        return self


class ClienteOut(ClienteCreate):
    # Os campos internos usam os aliases públicos já presentes no frontend.
    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, str_strip_whitespace=True
    )
    id: int
    versao: int
    criado_em: datetime
    atualizado_em: datetime


CLIENTE_COLUMNS = (
    "id, nome, telefone, email, instagram, status, observacao, tags, legacy_local_id, "
    "cidade, desde, categoria, cadastro_original_em, observacao_atualizada_em, "
    "avatar_url, foto, ultima, total, pendente, versao, criado_em, atualizado_em"
)
EDITABLE_COLUMNS = set(ClienteFields.model_fields)


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    tags = row.get("tags")
    if isinstance(tags, str):
        row["tags"] = json.loads(tags)
    return row


def lock_cliente(cur, workspace_id: int, cliente_id: int, expected_version: int | None):
    cur.execute(
        f"SELECT {CLIENTE_COLUMNS} FROM socialmei.crm_clientes "
        "WHERE workspace_id = %s AND id = %s FOR UPDATE",
        (workspace_id, cliente_id),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    if expected_version is not None and row["versao"] != expected_version:
        raise HTTPException(
            status_code=409,
            detail="Cliente alterado por outra sessão. Recarregue antes de salvar.",
        )
    return row


@router.get("/clientes", response_model=list[ClienteOut])
def list_clientes():
    require_shared_data()
    with connect() as conn:
        workspace_id = ensure_workspace(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {CLIENTE_COLUMNS} FROM socialmei.crm_clientes "
                "WHERE workspace_id = %s ORDER BY nome, id",
                (workspace_id,),
            )
            return [normalize_row(row) for row in cur.fetchall()]


def validate_contact_changes(values: dict) -> None:
    # Valida somente entradas novas; contatos legados continuam legíveis.
    for field, validator in (("telefone", validate_phone), ("instagram", validate_instagram)):
        if field in values:
            try:
                values[field] = validator(values[field])
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/clientes", response_model=ClienteOut, status_code=status.HTTP_201_CREATED
)
def create_cliente(payload: ClienteCreate):
    require_shared_data()
    values = payload.model_dump()
    validate_contact_changes(values)
    columns = list(values)
    params = [
        json.dumps(value) if key == "tags" else value for key, value in values.items()
    ]
    placeholders = ["%s::jsonb" if key == "tags" else "%s" for key in columns]
    try:
        with connect() as conn:
            workspace_id = ensure_workspace(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"INSERT INTO socialmei.crm_clientes (workspace_id, {', '.join(columns)}) "
                    f"VALUES (%s, {', '.join(placeholders)}) RETURNING {CLIENTE_COLUMNS}",
                    [workspace_id, *params],
                )
                return normalize_row(cur.fetchone())
    except UniqueViolation as error:
        if error.diag.constraint_name != "ux_crm_clientes_workspace_legacy_local":
            raise
        raise HTTPException(
            status_code=409,
            detail="ID local já utilizado neste workspace. Não repita a importação por POST.",
        ) from error


@router.get("/clientes/{cliente_id}", response_model=ClienteOut)
def get_cliente(cliente_id: int):
    require_shared_data()
    with connect() as conn:
        workspace_id = ensure_workspace(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {CLIENTE_COLUMNS} FROM socialmei.crm_clientes "
                "WHERE workspace_id = %s AND id = %s",
                (workspace_id, cliente_id),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return normalize_row(row)


@router.patch("/clientes/{cliente_id}", response_model=ClienteOut)
def update_cliente(cliente_id: int, payload: ClienteUpdate):
    require_shared_data()
    values = payload.model_dump(exclude_unset=True)
    validate_contact_changes(values)
    expected_version = values.pop("expected_version", None)
    # A allowlist é interna; nomes de colunas nunca vêm de texto recebido.
    assert set(values).issubset(EDITABLE_COLUMNS)
    with connect() as conn:
        workspace_id = ensure_workspace(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            current = lock_cliente(cur, workspace_id, cliente_id, expected_version)
            if not values:
                return normalize_row(current)
            assignments = [
                f"{key} = %s::jsonb" if key == "tags" else f"{key} = %s"
                for key in values
            ]
            params = [
                json.dumps(value) if key == "tags" else value
                for key, value in values.items()
            ]
            assignments.extend(["atualizado_em = NOW()", "versao = versao + 1"])
            cur.execute(
                f"UPDATE socialmei.crm_clientes SET {', '.join(assignments)} "
                f"WHERE workspace_id = %s AND id = %s RETURNING {CLIENTE_COLUMNS}",
                [*params, workspace_id, cliente_id],
            )
            return normalize_row(cur.fetchone())


@router.delete("/clientes/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cliente(
    cliente_id: int,
    expected_version: Annotated[int | None, Query(ge=1)] = None,
):
    require_shared_data()
    with connect() as conn:
        workspace_id = ensure_workspace(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            lock_cliente(cur, workspace_id, cliente_id, expected_version)
            try:
                cur.execute(
                    "DELETE FROM socialmei.crm_clientes WHERE workspace_id = %s AND id = %s",
                    (workspace_id, cliente_id),
                )
            except ForeignKeyViolation:
                raise HTTPException(
                    409,
                    "Este cliente possui oportunidades ou histórico vinculado e não pode ser excluído. Preserve o cadastro para consultar as negociações.",
                ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def database_health_payload() -> dict[str, Any]:
    authentication = auth_enabled()
    if authentication:
        require_auth_enabled()
    if not shared_data_enabled():
        return {
            "status": "disabled",
            "shared_data": False,
            "capabilities": {
                "crm": "disabled",
                "auth": {"enabled": False, "schema": "not_checked"},
                "channels": {"schema": "not_checked", "connection": "not_checked"},
            },
        }

    channels = check_database(include_auth=authentication)
    return {
        "status": "healthy",
        "shared_data": True,
        "workspace": workspace_slug(),
        "capabilities": {
            "crm": "ready",
            "auth": {
                "enabled": authentication,
                "schema": "ready" if authentication else "not_checked",
            },
            "channels": {"schema": channels, "connection": "not_checked"},
        },
    }
