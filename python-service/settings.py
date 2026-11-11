"""Configuração da API. Lê o ambiente sem guardar ou registrar segredos."""

import os
import json
import re
from dataclasses import dataclass
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ENABLED_VALUES = {"1", "true", "yes", "on"}
DISABLED_VALUES = {"0", "false", "no", "off", ""}


def shared_data_enabled() -> bool:
    # Preserva a interpretação histórica desta flag, inclusive espaços inválidos.
    return os.getenv("SOCIALMEI_SHARED_DATA_ENABLED", "false").lower() in ENABLED_VALUES


def database_readiness_cache_seconds() -> int:
    value = os.getenv("SOCIALMEI_DB_READINESS_CACHE_SECONDS", "300").strip()
    try:
        seconds = int(value)
    except ValueError:
        return 0
    return min(max(seconds, 0), 900)


def authentication_mode() -> str:
    value = os.getenv("SOCIALMEI_AUTH_ENABLED", "false").strip().lower()
    if value in ENABLED_VALUES:
        return "enabled"
    if value in DISABLED_VALUES:
        return "disabled"
    # Um erro de digitação não pode reabrir o workspace sem autenticação.
    return "invalid"


def instagram_token_refresh_enabled() -> bool:
    # Opt-in credential maintenance; unrelated sending/ingress flags stay unchanged.
    return os.getenv("SOCIALMEI_INSTAGRAM_TOKEN_REFRESH_ENABLED", "false").strip().lower() == "true"


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


def business_timezone() -> ZoneInfo:
    name = os.getenv("TZ", "America/Recife").strip() or "America/Recife"
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Fuso horário do negócio inválido.") from None


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


def provider_sentiment_enabled() -> bool:
    # Opt-in service-to-service analysis; never enables provider sending.
    return os.getenv("SOCIALMEI_PROVIDER_SENTIMENT_ENABLED", "false").strip().lower() == "true"


def provider_sentiment_key() -> str:
    return os.getenv("SOCIALMEI_PROVIDER_SENTIMENT_KEY", "")


def provider_sentiment_allowed_workspaces() -> tuple[int, ...]:
    # Explicit pilot allowlist; empty/invalid configuration never sweeps all MEIs.
    value = os.getenv("SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS", "").strip()
    if not value or len(value) > 512:
        return ()
    parts = value.split(",")
    if any(not part.isascii() or not part.isdecimal() or not 1 <= len(part) <= 15 for part in parts):
        return ()
    ids = tuple(sorted({int(part) for part in parts}))
    return ids if all(1 <= item <= 9007199254740991 for item in ids) else ()


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


def instagram_ingress_isolated_enabled() -> bool:
    return (
        os.getenv("SOCIALMEI_INSTAGRAM_INGRESS_MODE", "disabled").strip().lower() == "isolated"
        and os.getenv("SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT", "").strip().lower() == "isolated"
    )


def instagram_direct_isolated_enabled() -> bool:
    return (
        os.getenv("SOCIALMEI_INSTAGRAM_DIRECT_MODE", "disabled").strip().lower() == "isolated"
        and os.getenv("SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT", "").strip().lower() == "isolated"
    )


def waha_ingress_isolated_enabled() -> bool:
    return (
        os.getenv("SOCIALMEI_WAHA_INGRESS_MODE", "disabled").strip().lower() == "isolated"
        and os.getenv("SOCIALMEI_WAHA_LAB_ENVIRONMENT", "").strip().lower() == "isolated"
        and shared_data_enabled()
        and authentication_mode() == "enabled"
    )


def waha_ingress_team_pilot_enabled() -> bool:
    return (
        os.getenv("SOCIALMEI_WAHA_INGRESS_MODE", "disabled").strip().lower() == "team-pilot"
        and os.getenv("SOCIALMEI_WAHA_LAB_ENVIRONMENT", "").strip().lower() == "team-pilot"
        and os.getenv("SOCIALMEI_WAHA_REGISTRY_FILE", "") == "/run/socialmei/private/waha-registry.json"
        and shared_data_enabled()
        and authentication_mode() == "enabled"
    )


def waha_workspace_inbox_requested() -> bool:
    return os.getenv("SOCIALMEI_WAHA_INGRESS_MODE", "disabled").strip().lower() == "workspace-inbox"


def waha_ingress_workspace_enabled() -> bool:
    """Operator-managed receiving only; neither laboratory mode nor sender opt-in."""
    return (
        waha_workspace_inbox_requested()
        and os.getenv("SOCIALMEI_WAHA_WORKSPACE_INBOX_ENABLED", "false").strip().lower() == "true"
        and os.getenv("SOCIALMEI_WAHA_REGISTRY_FILE", "") == "/run/socialmei/private/waha-registry.json"
        and shared_data_enabled()
        and authentication_mode() == "enabled"
    )


def waha_ingress_enabled() -> bool:
    return (
        waha_ingress_isolated_enabled()
        or waha_ingress_team_pilot_enabled()
        or waha_ingress_workspace_enabled()
    )


def whatsapp_bot_allowed_contacts():
    """Unrestricted fixtures only in isolated mode; live pilot needs explicit contacts."""
    if waha_ingress_isolated_enabled():
        return None
    try:
        values = json.loads(os.getenv("SOCIALMEI_WHATSAPP_BOT_ALLOWED_CONTACTS", "[]"))
    except (ValueError, TypeError):
        return frozenset()
    if (not isinstance(values, list) or len(values) > 20
            or any(not isinstance(value, str) or not re.fullmatch(
                r"(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)", value
            ) for value in values)):
        return frozenset()
    return frozenset("waha:" + value for value in values)


def waha_inbox_enabled(workspace_id: int) -> bool:
    return waha_ingress_isolated_enabled() or (
        type(workspace_id) is int and workspace_id == 1
        and waha_ingress_team_pilot_enabled()
    ) or (
        type(workspace_id) is int and 1 <= workspace_id <= 2**63 - 1
        and waha_ingress_workspace_enabled()
    )


@dataclass(frozen=True, repr=False)
class WhatsAppHumanConfiguration:
    workspace_id: int
    instance: str
    session: str
    account_id: str
    contacts: frozenset[str]
    base_url: str
    api_key: str

    def __repr__(self):
        return 'WhatsAppHumanConfiguration(private=<redacted>)'


def whatsapp_human_configuration():
    """Server-owned opt-in for one reviewed WhatsApp human sender; never performs I/O."""
    if waha_workspace_inbox_requested():
        return None
    if os.getenv('SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED', 'false').strip().lower() != 'true':
        return None
    from waha_ingress import DIRECT
    try:
        raw_workspace = os.getenv('SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID', '')
        if not re.fullmatch(r'[1-9][0-9]{0,15}', raw_workspace):
            raise ValueError()
        workspace = int(raw_workspace)
        instance = os.getenv('SOCIALMEI_WHATSAPP_HUMAN_INSTANCE', '')
        session = os.getenv('SOCIALMEI_WHATSAPP_HUMAN_SESSION', '')
        account = os.getenv('SOCIALMEI_WHATSAPP_HUMAN_ACCOUNT_ID', '')
        base_url = os.getenv('SOCIALMEI_WAHA_PRIVATE_BASE_URL', '')
        api_key = os.getenv('SOCIALMEI_WAHA_PRIVATE_API_KEY', '')
        raw_contacts = os.getenv('SOCIALMEI_WHATSAPP_HUMAN_CONTACTS', '')
        if len(raw_contacts) > 4096:
            raise ValueError()
        contacts = json.loads(raw_contacts)
        if (
            os.getenv('SOCIALMEI_WHATSAPP_HUMAN_OWNER', '') != 'dashboard'
            or not waha_inbox_enabled(workspace)
            or not 1 <= workspace <= 9007199254740991
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', instance)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', session)
            or not re.fullmatch(r'[0-9]{1,40}@c\.us', account)
            or base_url not in {'http://waha:3000', 'http://socialmei-waha:3000'}
            or not re.fullmatch(r'[!-~]{16,4096}', api_key)
            or not isinstance(contacts, list) or not 1 <= len(contacts) <= 20
            or any(not isinstance(item, str) or not DIRECT.fullmatch(item) for item in contacts)
            or len(set(contacts)) != len(contacts)
        ):
            raise ValueError()
        return WhatsAppHumanConfiguration(
            workspace, instance, session, account, frozenset(contacts), base_url, api_key,
        )
    except (TypeError, ValueError):
        raise ValueError('Configuração privada de envio WhatsApp indisponível.') from None


def instagram_runtime_enabled() -> bool:
    return (
        os.getenv("SOCIALMEI_INSTAGRAM_RUNTIME_MODE", "disabled").strip().lower() == "connect"
        and authentication_mode() == "enabled" and shared_data_enabled()
    )


def instagram_runtime_configuration() -> dict:
    # Server-only values. Never return this mapping from an API or log it.
    return {
        key: os.getenv("SOCIALMEI_INSTAGRAM_" + suffix, "")
        for key, suffix in {
            "client_id": "CLIENT_ID", "client_secret": "CLIENT_SECRET",
            "graph_version": "GRAPH_VERSION", "authorization_embed": "AUTHORIZATION_EMBED",
            "keyring": "TOKEN_KEYRING", "active_key_id": "TOKEN_ACTIVE_KEY_ID",
            "verify_token": "WEBHOOK_VERIFY_TOKEN", "webhook_aliases": "WEBHOOK_ACCOUNT_ALIASES", "ingress": "RUNTIME_INGRESS_ENABLED",
            "send": "RUNTIME_SEND_ENABLED", "privacy_reviewed": "PROXY_PRIVACY_REVIEWED",
        }.items()
    }


def instagram_live_ingress_enabled() -> bool:
    """Enable workspace inbox visibility only after production webhook ingress is active."""
    return (
        (instagram_runtime_enabled()
         and os.getenv("SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED", "false")
         .strip().lower() == "true") or instagram_n8n_ingress_enabled()
    )


def instagram_n8n_ingress_enabled() -> bool:
    return (
        os.getenv("SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED", "false") == "true"
        and authentication_mode() == "enabled" and shared_data_enabled()
    )


def instagram_n8n_ingress_configuration() -> dict:
    """Private server-only bridge configuration, never returned by API responses."""
    return {
        "auth_mode": os.getenv("SOCIALMEI_INSTAGRAM_N8N_AUTH_MODE", "hmac"),
        "key": os.getenv("SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY", ""),
        "meta_app_secret": os.getenv("SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET", ""),
        "bindings": os.getenv("SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS", ""),
    }


def recovery_smtp_configuration():
    """Opt-in, TLS-only mail delivery. Values are server-side secrets."""
    if os.getenv("SOCIALMEI_RECOVERY_MODE", "disabled") != "smtp":
        raise ValueError("Recovery disabled")
    values = {
        key: os.getenv("SOCIALMEI_SMTP_" + key.upper(), "")
        for key in ("host", "user", "password", "from")
    }
    if any(not value or "\r" in value or "\n" in value for value in values.values()):
        raise ValueError("Incomplete mail configuration")
    values["port"] = int(os.getenv("SOCIALMEI_SMTP_PORT", "465"))
    if values["port"] not in (465, 587):
        raise ValueError("TLS mail port required")
    return values


def release_sha():
    import re
    value = os.getenv('SOCIALMEI_RELEASE_SHA', '')
    return value if re.fullmatch(r'[a-f0-9]{40}', value) else None
