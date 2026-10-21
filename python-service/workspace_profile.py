"""Versioned workspace onboarding and membership-scoped user preferences."""

import json
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints,
    model_validator,
)

from account_auth import current, require_enabled
from database import connect

router = APIRouter(prefix="/api/v1", tags=["workspace profile"])
SEGMENTS = set(
    "barber hairdresser manicure perfume cosmetics beautyReseller tailoring fashion "
    "bakery snack restaurant commerce market convenience phoneRepair electronics "
    "consulting tutor laboratory photography design services other".split()
)
MODULES = set(
    "clients inbox opportunities products services appointments orders deliveries "
    "inventory team sales finance reports".split()
)

def database_text(value):
    # PostgreSQL JSONB rejects NUL and unpaired Unicode surrogates.
    if "\x00" in value:
        raise ValueError("Texto inválido.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("Texto inválido.") from None
    return value


Text = Annotated[
    str, StringConstraints(strict=True, max_length=120), AfterValidator(database_text)
]
Ignored = Annotated[
    str, StringConstraints(strict=True, max_length=160), AfterValidator(database_text)
]
Revision = Annotated[StrictInt, Field(ge=0, le=9007199254740990)]
QuietTime = Annotated[
    str, StringConstraints(pattern=r"^(?:|(?:[01][0-9]|2[0-3]):[0-5][0-9])$")
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Capabilities(Strict):
    appointments: StrictBool
    orders: StrictBool
    deliveries: StrictBool
    inventory: StrictBool
    team: StrictBool
    walkIns: StrictBool
    quotes: StrictBool
    onlineOrders: StrictBool
    recurring: StrictBool


class BusinessProfile(Strict):
    version: StrictInt
    businessName: Text
    segment: Text
    activity: Text
    offers: list[Literal["products", "services"]] = Field(min_length=1, max_length=2)
    services: list[Text] = Field(max_length=30)
    productCategories: list[Text] = Field(max_length=30)
    capabilities: Capabilities
    modules: list[Text] = Field(max_length=30)
    ignoredSuggestions: list[Ignored] = Field(max_length=60)
    completed: StrictBool

    @model_validator(mode="after")
    def validate_contract(self):
        if not self.completed:
            raise ValueError("Conclua o perfil antes de salvar.")
        if self.version != 1 or self.segment not in SEGMENTS or set(self.modules) - MODULES:
            raise ValueError("Perfil inválido.")
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 32768:
            raise ValueError("Perfil muito grande.")
        return self

    def normalized(self, business_name):
        data = self.model_dump()
        for key in ("businessName", "activity"):
            data[key] = data[key].strip()
        # Account identity owns the business name; onboarding never renames a workspace.
        data["businessName"] = business_name.strip()[:120]
        for key in ("offers", "services", "productCategories", "modules"):
            data[key] = list(dict.fromkeys(
                item.strip() for item in data[key] if item.strip()
            ))
        data["ignoredSuggestions"] = list(dict.fromkeys(data["ignoredSuggestions"]))
        if "products" not in data["offers"]:
            data["productCategories"] = []
            data["capabilities"]["inventory"] = False
        if "services" not in data["offers"]:
            data["services"] = []
            data["capabilities"]["appointments"] = False
        data["modules"] = [
            item for item in data["modules"]
            if (item not in ("products", "services") or item in data["offers"])
            and (item not in data["capabilities"] or data["capabilities"][item])
        ]
        return data


class Notifications(Strict):
    message: StrictBool
    payment: StrictBool
    pending: StrictBool
    routine: StrictBool
    channel: Literal["app"]
    quietFrom: QuietTime
    quietTo: QuietTime

    @model_validator(mode="after")
    def quiet_pair(self):
        if bool(self.quietFrom) != bool(self.quietTo):
            raise ValueError("Informe início e fim do horário silencioso.")
        return self


class Preferences(Strict):
    theme: Literal["auto", "light", "dark"]
    notificationsEnabled: StrictBool
    notifications: Notifications


def default_preferences():
    return {
        "theme": "auto",
        "notificationsEnabled": True,
        "notifications": {
            "message": True, "payment": True, "pending": True, "routine": True,
            "channel": "app", "quietFrom": "", "quietTo": "",
        },
    }


class VersionedPatch(Strict):
    schema_version: StrictInt
    expected_revision: Revision

    @model_validator(mode="after")
    def schema(self):
        if self.schema_version != 1:
            raise ValueError("Versão não suportada.")
        return self


class ProfilePatch(VersionedPatch):
    profile: BusinessProfile


class PreferencesPatch(VersionedPatch):
    preferences: Preferences


def identity(request, response):
    response.headers["Cache-Control"] = "no-store"
    try:
        require_enabled()
    except HTTPException as error:
        error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
        raise
    if request.query_params:
        raise HTTPException(422, "Confira os campos informados.")
    return current()


def storage(table, user, column, value=None, expected=None):
    """Single-statement CAS handles absent-row races without blind upserts."""
    keys = {"workspace_id": user["workspace_id"]}
    if table == "auth_preferences":
        keys["user_id"] = user["id"]
    table_sql = sql.Identifier("socialmei", table)
    where = sql.SQL(" AND ").join(
        sql.SQL("{}=%s").format(sql.Identifier(key)) for key in keys
    )
    try:
        with connect() as conn:
            if expected is None:
                query = sql.SQL("SELECT revision, {} FROM {} WHERE {}").format(
                    sql.Identifier(column), table_sql, where
                )
                row = conn.execute(query, tuple(keys.values())).fetchone()
            elif expected == 0:
                columns = [*keys, column]
                query = sql.SQL(
                    "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING "
                    "RETURNING revision, {}"
                ).format(
                    table_sql,
                    sql.SQL(",").join(map(sql.Identifier, columns)),
                    sql.SQL(",").join(sql.Placeholder() for _ in columns),
                    sql.Identifier(column),
                )
                row = conn.execute(query, (*keys.values(), Jsonb(value))).fetchone()
            else:
                query = sql.SQL(
                    "UPDATE {} SET {}=%s, revision=revision+1, atualizado_em=NOW() "
                    "WHERE {} AND revision=%s RETURNING revision, {}"
                ).format(table_sql, sql.Identifier(column), where, sql.Identifier(column))
                row = conn.execute(
                    query, (Jsonb(value), *keys.values(), expected)
                ).fetchone()
            if expected is not None and row is None:
                raise HTTPException(
                    409, "Os dados mudaram em outra sessão. Recarregue antes de salvar."
                )
            return row
    except (psycopg.Error, RuntimeError):
        raise HTTPException(
            503, "Preferências temporariamente indisponíveis.",
            headers={"Cache-Control": "no-store"},
        ) from None


@router.get("/workspace-profile")
def get_profile(request: Request, response: Response):
    user = identity(request, response)
    row = storage("workspace_profiles", user, "profile")
    profile = (
        BusinessProfile.model_validate(row[1]).normalized(user["nome_negocio"])
        if row else None
    )
    return {"schema_version": 1, "revision": row[0] if row else 0, "profile": profile}


@router.patch("/workspace-profile")
def patch_profile(payload: ProfilePatch, request: Request, response: Response):
    user = identity(request, response)
    if user["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente responsáveis pelo negócio podem alterar o perfil.")
    profile = payload.profile.normalized(user["nome_negocio"])
    row = storage("workspace_profiles", user, "profile", profile, payload.expected_revision)
    return {"schema_version": 1, "revision": row[0], "profile": row[1]}


@router.get("/auth/preferences")
def get_preferences(request: Request, response: Response):
    user = identity(request, response)
    row = storage("auth_preferences", user, "preferences")
    return {
        "schema_version": 1, "revision": row[0] if row else 0,
        "preferences": row[1] if row else default_preferences(),
    }


@router.patch("/auth/preferences")
def patch_preferences(payload: PreferencesPatch, request: Request, response: Response):
    user = identity(request, response)
    row = storage(
        "auth_preferences", user, "preferences",
        payload.preferences.model_dump(), payload.expected_revision,
    )
    return {"schema_version": 1, "revision": row[0], "preferences": row[1]}
