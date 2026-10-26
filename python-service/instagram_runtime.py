"""Explicit server-owned provider wiring. Disabled by default; no I/O at startup."""

import base64
import json
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Request

import settings
from account_auth import current, origin, require_enabled
from database import connect
from instagram_http_transport import InstagramHTTPTransport
from instagram_meta_adapter import InstagramAdapter
from instagram_meta_contract import INSTAGRAM_LOGIN_SCOPES
from instagram_token_vault import TokenVault

RETURN_PATH = "/api/v1/instagram/meta/oauth/return"
PUBLIC_WEBHOOK_PATH = "/webhooks/instagram"
router = APIRouter(prefix="/api/v1/integrations", tags=["backend readiness"])


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Configuração duplicada.")
        result[key] = value
    return result


def _flag(value):
    if value not in {"", "false", "true"}:
        raise ValueError("Flag inválida.")
    return value == "true"


class InstagramRuntime:
    def __init__(
        self, status="disabled", *, oauth=None, ingress=None, direct=None,
        publish=None, send=False
    ):
        self.status = status
        self.oauth = oauth
        self.ingress = ingress
        self.direct = direct
        self.publish = publish
        self.send = send

    def __repr__(self):
        return "InstagramRuntime(status=" + repr(self.status) + ", secrets=<redacted>)"


def build_runtime():
    mode = os.getenv("SOCIALMEI_INSTAGRAM_RUNTIME_MODE", "disabled").strip().lower()
    if mode in {"", "disabled"}:
        return InstagramRuntime()
    try:
        if mode != "connect" or not settings.instagram_runtime_enabled():
            raise ValueError("Runtime indisponível.")
        values = settings.instagram_runtime_configuration()
        if not _flag(values["privacy_reviewed"]):
            raise ValueError("Revisão de privacidade pendente.")
        incoming = _flag(values["ingress"])
        sending = _flag(values["send"])
        publishing = _flag(os.getenv("SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED", "false"))
        scopes = frozenset(os.getenv("SOCIALMEI_INSTAGRAM_SCOPES", "").split(","))
        if (
            "instagram_business_basic" not in scopes
            or not scopes <= INSTAGRAM_LOGIN_SCOPES
        ):
            raise ValueError("Escopos inválidos.")
        if (incoming or sending) and "instagram_business_manage_messages" not in scopes:
            raise ValueError("Escopo de mensagens ausente.")
        if publishing and "instagram_business_content_publish" not in scopes:
            raise ValueError("Escopo de publicacao ausente.")
        if not 32 <= len(values["client_secret"]) <= 16384:
            raise ValueError("Segredo inválido.")
        if len(values["keyring"]) > 4096:
            raise ValueError("Keyring inválido.")
        encoded = json.loads(values["keyring"], object_pairs_hook=_unique)
        if not isinstance(encoded, dict) or not 1 <= len(encoded) <= 16:
            raise ValueError("Keyring inválido.")
        keys = {}
        for key, value in encoded.items():
            if not isinstance(value, str) or len(value) not in (43, 44):
                raise ValueError("Chave inválida.")
            raw = base64.b64decode(
                value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
            )
            if len(raw) != 32 or base64.urlsafe_b64encode(raw).rstrip(
                b"="
            ).decode() != value.rstrip("="):
                raise ValueError("Chave inválida.")
            keys[key] = raw
        vault = TokenVault(keys=keys, active_key_id=values["active_key_id"])
        callback_uri = origin().rstrip("/") + RETURN_PATH
        adapter = InstagramAdapter(
            client_id=values["client_id"],
            client_secret=values["client_secret"],
            callback_uri=callback_uri,
            graph_version=values["graph_version"],
            transport=InstagramHTTPTransport(allow_sends=sending, allow_publishing=publishing),
        )
        from instagram_persistent_oauth import InstagramOAuthService
        from instagram_meta_ingress import InstagramIngressService
        from instagram_direct_outbox import InstagramDirectService

        oauth = InstagramOAuthService(
            adapter=adapter,
            vault=vault,
            authorization_embed=values["authorization_embed"],
            callback_uri=callback_uri,
            required_scopes=scopes,
        )
        ingress = (
            InstagramIngressService(
                app_secret=values["client_secret"], verify_token=values["verify_token"]
            )
            if incoming
            else None
        )
        direct = (
            InstagramDirectService(adapter=adapter, vault=vault, allow_dispatch=sending)
            if "instagram_business_manage_messages" in scopes
            else None
        )
        publisher = None
        if publishing:
            from instagram_publishing import InstagramPublishingService
            publisher = InstagramPublishingService(adapter=adapter, vault=vault)
        return InstagramRuntime(
            "configured", oauth=oauth, ingress=ingress, direct=direct,
            publish=publisher, send=sending
        )
    except Exception:
        # A provider configuration problem cannot disable CRM/login or echo secrets.
        return InstagramRuntime("configuration_invalid")


@asynccontextmanager
async def runtime_lifespan(app):
    app.state.instagram_runtime = build_runtime()
    yield
    app.state.instagram_runtime = InstagramRuntime()


OAUTH_TABLES = ("ig_meta_oauth_states", "ig_meta_connections", "ig_meta_audit")
INGRESS_TABLES = (
    *OAUTH_TABLES,
    "ig_meta_ingress_events",
    "me_conversations",
    "me_messages",
    "me_external_messages",
)
SCHEMA_TABLES = {
    "oauth": OAUTH_TABLES,
    "ingress": INGRESS_TABLES,
    "publish": (*OAUTH_TABLES, "ig_meta_publications", "ig_meta_media"),
    "direct": (
        *INGRESS_TABLES,
        "ig_direct_jobs",
        "ig_direct_operations",
        "ig_direct_attempts",
        "ig_direct_events",
    ),
}
SCHEMA_MIGRATIONS = {
    "oauth": {"019_instagram_persistent_oauth.sql"},
    "ingress": {
        "019_instagram_persistent_oauth.sql",
        "020_instagram_durable_webhook.sql",
    },
    "publish": {"019_instagram_persistent_oauth.sql", "027_instagram_image_publications.sql", "028_instagram_temporary_media.sql"},
    "direct": {
        "019_instagram_persistent_oauth.sql",
        "020_instagram_durable_webhook.sql",
        "021_instagram_direct_outbox.sql",
    },
}


def schema_ready(capability):
    try:
        with connect() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout='2s'")
            versions = {
                row[0]
                for row in conn.execute(
                    "SELECT version FROM socialmei.schema_migrations"
                ).fetchall()
            }
            if not SCHEMA_MIGRATIONS[capability] <= versions:
                return False
            for table in SCHEMA_TABLES[capability]:
                if not conn.execute(
                    "SELECT to_regclass(%s)", ("socialmei." + table,)
                ).fetchone()[0]:
                    return False
        return True
    except Exception:
        return False


def runtime_service(request, capability):
    if request is None:
        raise HTTPException(503, "Integração Instagram não configurada.")
    runtime = getattr(request.app.state, "instagram_runtime", None)
    service = getattr(runtime, capability, None)
    if (
        not settings.instagram_runtime_enabled()
        or runtime is None
        or runtime.status != "configured"
        or service is None
        or not schema_ready(capability)
    ):
        raise HTTPException(
            503, "Integração Instagram não configurada ou schema indisponível."
        )
    return service


@router.get("/readiness")
def readiness(request: Request):
    require_enabled()
    current()
    runtime = getattr(request.app.state, "instagram_runtime", InstagramRuntime())
    return {
        "source": "server",
        "n8n": {
            "workflow_review": "pending_live_contract",
            "workflow_runtime_status": "not_verified",
            "sending_available": False,
            "publishing_available": False,
        },
        "instagram": {
            "configuration": runtime.status,
            "oauth_available": runtime.oauth is not None and schema_ready("oauth"),
            "incoming_available": runtime.ingress is not None
            and schema_ready("ingress"),
            "reply_preparation_available": runtime.direct is not None
            and schema_ready("direct"),
            "send_enabled": runtime.send,
            "publishing_available": runtime.publish is not None and schema_ready("publish"),
            "connection_status_path": "/api/v1/instagram/meta/status",
        },
        "whatsapp": {
            "contract_prepared": True,
            "configured": False,
            "sending_available": False,
            "requires": [
                "approved_number",
                "server_registry",
                "waha_engine_hmac_homologation",
            ],
        },
        "business_api": {
            "customers": "/api/v1/clientes",
            "catalog": "/api/v1/produtos",
            "sales": "/api/v1/vendas",
            "finance": "/api/v1/financeiro",
            "profile": "/api/v1/workspace-profile",
            "opportunities": "/api/v1/opportunities",
        },
    }
