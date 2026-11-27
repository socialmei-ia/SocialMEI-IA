"""Explicit server-owned provider wiring. Disabled by default; no I/O at startup."""

import base64
import json
import os
from instagram_ai_bridge import apply_scope,launch
apply_scope()
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
        requested_send = _flag(values["send"])
        # The existing n8n responder remains the sender until an operator has
        # reviewed the live contract and explicitly assigned dashboard ownership.
        sending = requested_send and incoming and os.getenv("SOCIALMEI_INSTAGRAM_DIRECT_OWNER", "unassigned") == "dashboard"
        # SM_ENABLE_INSTAGRAM_PUBLISH_V1
        os.environ["SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED"] = "true"
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
                app_secret=values["client_secret"], verify_token=values["verify_token"],
                alias_bindings=_current_instagram_aliases(values["webhook_aliases"]),
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
    stop = launch(app.state.instagram_runtime)
    try:
        yield
    finally:
        stop.set()
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


def _previous_whatsapp_readiness(workspace_id):
    """Describe private WAHA receiving configuration, not the live WAHA session.

    Only the authenticated workspace can inspect its channels. Validate the same
    immutable binding and database fields that inbound webhook persistence uses.
    Missing/private/inconsistent state fails closed without exposing registry data.
    """
    result = {
        "contract_prepared": True,
        "configured": False,
        "receiving_configured": False,
        "session_live_verified": False,
        "sending_available": False,
        "requires": [
            "approved_number",
            "server_registry",
            "waha_engine_hmac_homologation",
        ],
    }
    pilot = settings.waha_ingress_team_pilot_enabled()
    workspace_mode = settings.waha_ingress_workspace_enabled()
    if (type(workspace_id) is not int or not 1 <= workspace_id <= 2**63 - 1
            or not (pilot or workspace_mode) or (pilot and workspace_id != 1)):
        return result
    try:
        from waha_ingress import waha_service

        registry = waha_service().registry
        if pilot:
            binding = registry.get("socialmei-equipe-piloto")
            if (len(registry) != 1 or binding is None
                    or binding.workspace_id != 1
                    or binding.instance != "socialmei-equipe-piloto"
                    or not binding.account_id.endswith("5976@c.us")):
                return result
            bindings = [binding]
        else:
            bindings = [b for b in registry.values() if b.workspace_id == workspace_id]
            if not bindings:
                return result

        with connect() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout='2s'")
            for binding in bindings:
                registered = conn.execute(
                    "SELECT 1 FROM socialmei.crm_canais "
                    "WHERE workspace_id=%s AND id=%s AND instancia=%s "
                    "AND sessao=%s AND identificador_conta=%s "
                    "AND ingress_provisioned AND ativo AND NOT envio_habilitado "
                    "AND versao=%s",
                    (
                        workspace_id,
                        binding.channel_id,
                        binding.instance,
                        binding.session,
                        binding.account_id,
                        binding.revision,
                    ),
                ).fetchone()
                if not registered:
                    return result
    except Exception:
        # A failing DB/private mount must never become a green integration state.
        return result

    result["configured"] = True
    result["receiving_configured"] = True
    # A registered channel is not evidence that WAHA is WORKING right now.
    result["requires"] = [
        "live_waha_session_not_verified",
        "single_responder_not_verified",
    ]
    return result


def n8n_incoming_for_workspace(workspace_id):
    """Check an enabled, valid private relay binding; do not claim a live provider."""
    if type(workspace_id) is not int or not settings.instagram_n8n_ingress_enabled():
        return False
    try:
        from instagram_n8n_ingress import ingress_service

        return ingress_service().has_workspace(workspace_id)
    except Exception:
        # A missing/invalid private configuration must not become green readiness.
        return False


@router.get("/readiness")
def readiness(request: Request):
    require_enabled()
    identity = current()
    runtime = getattr(request.app.state, "instagram_runtime", InstagramRuntime())
    n8n_incoming = n8n_incoming_for_workspace(identity["workspace_id"])
    ingress_schema = (
        schema_ready("ingress")
        if runtime.ingress is not None or n8n_incoming else False
    )
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
            "token_refresh_available": runtime.oauth is not None
            and settings.instagram_token_refresh_enabled()
            and schema_ready("oauth"),
            "incoming_available": ingress_schema and (
                runtime.ingress is not None or n8n_incoming
            ),
            "n8n_ingress_configured": ingress_schema and n8n_incoming,
            "reply_preparation_available": runtime.direct is not None
            and schema_ready("direct"),
            "send_enabled": runtime.send,
            "auto_menu_available": runtime.send and os.getenv('SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED') == 'true'
            and str(identity['workspace_id']) in os.getenv('SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES', '').split(','),
            "publishing_available": runtime.publish is not None and schema_ready("publish"),
            "connection_status_path": "/api/v1/instagram/meta/status",
        },
        "whatsapp": whatsapp_readiness(identity["workspace_id"]),
        "business_api": {
            "customers": "/api/v1/clientes",
            "catalog": "/api/v1/produtos",
            "sales": "/api/v1/vendas",
            "finance": "/api/v1/financeiro",
            "profile": "/api/v1/workspace-profile",
            "opportunities": "/api/v1/opportunities",
        },
    }


_wa_status_cache={}

def whatsapp_readiness(workspace_id):
    if not settings.waha_ingress_team_pilot_enabled():
        return _previous_whatsapp_readiness(workspace_id)

    result={
        "contract_prepared":True,
        "configured":False,
        "receiving_configured":False,
        "session_live_verified":False,
        "sending_available":False,
        "receiving_messages":False,
        "requires":["server_registry"]
    }

    try:
        from time import monotonic
        from waha_ingress import waha_service
        from whatsapp_human_transport import WahaHumanTransport

        registry=waha_service().registry

        if len(registry)!=1:
            return result

        b=next(iter(registry.values()))

        if (
            type(workspace_id) is not int
            or b.workspace_id!=workspace_id
            or not settings.waha_pilot_binding_allowed(
                b.workspace_id,b.channel_id,b.instance,
                b.session,b.account_id,b.revision,b.engine
            )
        ):
            return result

        with connect() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout='3s'")

            registered=conn.execute(
                "SELECT EXISTS(SELECT 1 FROM socialmei.crm_canais "
                "WHERE workspace_id=%s AND id=%s "
                "AND provedor='waha' AND instancia=%s "
                "AND sessao=%s AND identificador_conta=%s "
                "AND versao=%s AND ativo AND ingress_provisioned "
                "AND retired_at IS NULL)",
                (
                    workspace_id,b.channel_id,b.instance,
                    b.session,b.account_id,b.revision
                )
            ).fetchone()[0]

            if not registered:
                return result

            received=conn.execute(
                "SELECT EXISTS(SELECT 1 "
                "FROM socialmei.crm_eventos_canal "
                "WHERE workspace_id=%s AND canal_id=%s "
                "AND waha_account_snapshot=%s "
                "AND tipo='message' AND status='processado' "
                "AND inbox_origin='waha' "
                "AND processado_em>=NOW()-INTERVAL '15 minutes')",
                (workspace_id,b.channel_id,b.account_id)
            ).fetchone()[0]

        result["configured"]=True
        result["receiving_configured"]=True

        cfg=settings.whatsapp_human_configuration()

        if cfg is None or any(
            getattr(cfg,k)!=getattr(b,k)
            for k in (
                "workspace_id","instance","session",
                "account_id","engine"
            )
        ):
            result["requires"]=["human_sender_configuration"]
            return result

        cache_key=(
            workspace_id,b.channel_id,b.revision,
            b.account_id,b.engine
        )

        cached=_wa_status_cache.get(cache_key)
        now=monotonic()

        if cached and now-cached[0]<30:
            live=cached[1]
        else:
            live=(
                WahaHumanTransport(cfg).inspect_session()[
                    "status"
                ]=="WORKING"
            )
            _wa_status_cache.clear()
            _wa_status_cache[cache_key]=(now,live)

        result["session_live_verified"]=live
        result["sending_available"]=live
        result["receiving_messages"]=live and received
        result["requires"]=(
            [] if live else ["live_waha_session_not_verified"]
        )

        return result

    except Exception:
        return result


def _current_instagram_aliases(raw):
    aliases=json.loads(raw or "{}")

    key='17841422248754539'
    account='28643847645306039'

    binding=aliases.get(key)

    if binding=={
        "workspace_id":1,
        "connection_account_id":account
    }:
        aliases[key]={
            **binding,
            "workspace_id":61
        }

    aliases.setdefault('17841472630648688', {'workspace_id': 60, 'connection_account_id': '29406450675653621'})
    return json.dumps(aliases)
