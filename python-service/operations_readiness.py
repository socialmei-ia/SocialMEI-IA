"""Platform-admin-only, bounded read-only diagnostics. No remote network probes."""

from fastapi import APIRouter
from account_auth import admin, require_enabled
from database import connect, check_database
import settings

router = APIRouter(prefix="/api/v1/admin", tags=["operations"])
EXPECTED_MIGRATIONS = (
    "001_initial_socialmei_schema.sql",
    "002_shared_crm_foundation.sql",
    "003_client_contract.sql",
    "004_client_import.sql",
    "005_shared_catalog.sql",
    "006_shared_sales.sql",
    "007_shared_finance.sql",
    "008_workspace_transfer.sql",
    "009_shared_channel_foundation.sql",
    "010_account_authentication.sql",
    "011_crm_workspace_links.sql",
    "012_instagram_simulation.sql",
    "013_workspace_profile_sync.sql",
    "014_message_enrichment.sql",
    "015_content_preparation.sql",
    "016_opportunity_lifecycle.sql",
    "017_integration_setup.sql",
    "018_instagram_provider_lab.sql",
    "019_instagram_persistent_oauth.sql",
    "020_instagram_durable_webhook.sql",
    "021_instagram_direct_outbox.sql",
    "022_opportunity_planning.sql",
    "023_waha_durable_ingress.sql",
    "024_account_recovery.sql",
    "025_session_management.sql",
    "026_recovery_delivery_queue.sql",
    "027_instagram_image_publications.sql",
)


def database_status():
    try:
        check_database(include_auth=True)
        with connect() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout='2s'")
            versions = conn.execute(
                "SELECT version FROM socialmei.schema_migrations ORDER BY version LIMIT 1000"
            ).fetchall()
            installed = {row[0] for row in versions}
            missing = [
                int(name[:3]) for name in EXPECTED_MIGRATIONS if name not in installed
            ]
            conn.execute(
                "SELECT user_id,token_hash,senha_alterada_em,expira_em,usado_em FROM socialmei.auth_recuperacoes LIMIT 0"
            )
            conn.execute(
                "SELECT user_id,generation,status,queued_at,started_at,finished_at FROM socialmei.auth_recuperacao_envios LIMIT 0"
            )
            tables = conn.execute(
                "SELECT to_regclass('socialmei.auth_recuperacoes'),to_regclass('socialmei.auth_sessoes'),to_regclass('socialmei.auth_recuperacao_envios')"
            ).fetchone()
            session_handle = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='socialmei' AND table_name='auth_sessoes' AND column_name='public_id')"
            ).fetchone()[0]
        return {
            "status": (
                "schema_incomplete"
                if missing or not all(tables) or not session_handle
                else "ready"
            ),
            "expected_migrations": len(EXPECTED_MIGRATIONS),
            "missing_migrations": missing,
            "recovery_schema": bool(tables[0]),
            "session_management_schema": bool(session_handle),
        }
    except Exception:
        return {
            "status": "unavailable",
            "expected_migrations": len(EXPECTED_MIGRATIONS),
        }


def recovery_queue_status():
    try:
        with connect() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout='2s'")
            rows = conn.execute(
                "SELECT status,COUNT(*) FROM socialmei.auth_recuperacao_envios GROUP BY status"
            ).fetchall()
        return {"status": "available", "counts": {row[0]: row[1] for row in rows}}
    except Exception:
        return {"status": "unavailable"}


@router.get("/diagnostics")
def diagnostics():
    require_enabled()
    admin()
    try:
        settings.recovery_smtp_configuration()
        email = "configured_not_verified"
    except (ValueError, TypeError):
        email = "disabled_or_incomplete"
    return {
        "service": "socialmei-crm-api",
        "release_sha": settings.release_sha(),
        "authentication": settings.authentication_mode(),
        "database": database_status(),
        "email": email,
        "recovery_queue": recovery_queue_status(),
        "providers": {
            "n8n": "not_verified",
            "instagram": "not_verified",
            "waha": "not_verified",
        },
        "scope": "local_process_and_database_only",
    }
