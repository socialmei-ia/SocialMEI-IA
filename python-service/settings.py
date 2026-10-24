"""Configuração da API. Lê o ambiente sem guardar ou registrar segredos."""

import os
from urllib.parse import quote

ENABLED_VALUES = {"1", "true", "yes", "on"}
DISABLED_VALUES = {"0", "false", "no", "off", ""}


def shared_data_enabled() -> bool:
    # Preserva a interpretação histórica desta flag, inclusive espaços inválidos.
    return os.getenv("SOCIALMEI_SHARED_DATA_ENABLED", "false").lower() in ENABLED_VALUES


def authentication_mode() -> str:
    value = os.getenv("SOCIALMEI_AUTH_ENABLED", "false").strip().lower()
    if value in ENABLED_VALUES:
        return "enabled"
    if value in DISABLED_VALUES:
        return "disabled"
    # Um erro de digitação não pode reabrir o workspace sem autenticação.
    return "invalid"


def authentication_origin() -> str:
    return os.getenv("SOCIALMEI_AUTH_ORIGIN", "").strip()


def registration_mode() -> str:
    # Somente a opção explícita abre o cadastro; valores inválidos exigem convite.
    value = os.getenv("SOCIALMEI_REGISTRATION_MODE", "invite").strip().lower()
    return "open" if value == "open" else "invite"


def cors_origins() -> list[str]:
    origins = [
        origin.strip()
        for origin in os.getenv("SOCIALMEI_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if "*" in origins:
        raise RuntimeError("Configure origens CORS explícitas, sem wildcard.")
    return origins


def workspace_slug() -> str:
    return os.getenv("SOCIALMEI_WORKSPACE_SLUG", "development").strip() or "development"


def workspace_name() -> str:
    return (
        os.getenv("SOCIALMEI_WORKSPACE_NAME", "SocialMEI Development").strip()
        or "SocialMEI Development"
    )


def n8n_read_token() -> str:
    return os.getenv("SOCIALMEI_N8N_READ_TOKEN", "")


def database_url() -> str:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    host = os.getenv("POSTGRES_HOST", "").strip()
    user = os.getenv("POSTGRES_USER", "").strip()
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DB", "").strip()
    port = os.getenv("POSTGRES_PORT", "5432").strip() or "5432"

    if not all([host, user, database]):
        raise RuntimeError("PostgreSQL não configurado para a API compartilhada.")

    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}"
    )


def message_enrichment_mode() -> str:
    return os.getenv("SOCIALMEI_MESSAGE_ENRICHMENT_MODE", "disabled").strip().lower()


def message_enrichment_signing_key() -> str:
    # This isolated adapter never reuses a connector or n8n credential.
    return os.getenv("SOCIALMEI_MESSAGE_ENRICHMENT_TEST_KEY", "")


def channel_ingress_mode() -> str:
    return os.getenv("SOCIALMEI_CHANNEL_INGRESS_MODE", "disabled").strip().lower()


def channel_ingress_signing_key() -> str:
    return os.getenv("SOCIALMEI_CHANNEL_INGRESS_TEST_KEY", "")


def content_preparation_mode() -> str:
    return os.getenv("SOCIALMEI_CONTENT_PREPARATION_MODE", "disabled").strip().lower()


def instagram_provider_lab_enabled() -> bool:
    return (
        os.getenv("SOCIALMEI_INSTAGRAM_PROVIDER", "disabled").strip().lower() == "fake"
        and os.getenv("SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT", "").strip().lower() == "isolated"
    )


def instagram_provider_lab_signing_key() -> str:
    return os.getenv("SOCIALMEI_INSTAGRAM_LAB_TEST_KEY", "")


def instagram_oauth_isolated_enabled() -> bool:
    return (
        os.getenv("SOCIALMEI_INSTAGRAM_OAUTH_MODE", "disabled").strip().lower() == "isolated"
        and os.getenv("SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT", "").strip().lower() == "isolated"
    )
