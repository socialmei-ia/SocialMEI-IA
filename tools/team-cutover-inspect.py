#!/usr/bin/env python3
"""Read-only, secret-free cutover inspection for the SocialMEI Team AWS stack.

This does not modify Git, Docker, PostgreSQL, n8n, Meta or WAHA.
It cannot authorize deployment or live sends. Run on the authorized Ubuntu host.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path("/home/ubuntu/socialmei-team")
CONTAINERS = {
    "team_api": "socialmei-team-team-api-1",
    "team_gateway": "socialmei-team-team-gateway-1",
    "team_database": "socialmei-team-team-postgres-1",
    "n8n": "socialmei-n8n",
    "waha": "socialmei-waha",
}
EXPECTED_MIGRATIONS = {
    "032_whatsapp_bot_conversations.sql",
    "033_provider_sentiment_jobs.sql",
}
AUTOMATION_NETWORK = "socialmei_team_automation"
SQL = """BEGIN TRANSACTION READ ONLY;
SELECT json_build_object(
  'versions', COALESCE(json_agg(version ORDER BY version), '[]'::json),
  'bot_table', to_regclass('socialmei.wa_bot_conversations') IS NOT NULL,
  'sentiment_table', to_regclass('socialmei.me_provider_sentiment_jobs') IS NOT NULL
)::text
FROM socialmei.schema_migrations;
ROLLBACK;
"""


def run_read_only(args, *, input_text=None, timeout=14):
    """Never print stdout/stderr of a subprocess: they may contain secrets."""
    try:
        completed = subprocess.run(
            args, input=input_text, capture_output=True, text=True,
            check=False, timeout=timeout,
        )
        if completed.returncode:
            return None
        return completed.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def inspect_summary(data, service):
    if not isinstance(data, dict):
        return {"available": False}
    state = data.get("State") or {}
    config = data.get("Config") or {}
    env = dict(s.split("=", 1) for s in config.get("Env", []) if isinstance(s, str) and "=" in s)
    raw_health = (state.get("Health") or {}).get("Status")
    health = raw_health if raw_health in ("healthy", "unhealthy", "starting") else "unknown"
    networks = set((data.get("NetworkSettings") or {}).get("Networks") or {})
    labels = config.get("Labels") or {}
    image_rev = labels.get("org.opencontainers.image.revision", "")
    release_sha = image_rev if isinstance(image_rev, str) and re.fullmatch(r"[0-9a-f]{40}", image_rev) else None
    ports = (data.get("HostConfig") or {}).get("PortBindings") or {}
    result = {
        "available": True,
        "running": state.get("Running") is True,
        "health": health,
        "release_sha": release_sha,
        "host_ports_bound": bool(ports),
        "automation_network": AUTOMATION_NETWORK in networks,
    }
    if service == "team_api":
        mode = env.get("SOCIALMEI_INSTAGRAM_RUNTIME_MODE", "disabled")
        result["flags"] = {
            "auth_enabled": env.get("SOCIALMEI_AUTH_ENABLED", "false").strip().lower() in {"true", "1", "yes", "on"},
            "instagram_runtime": mode if mode in {"disabled", "connect"} else "other_or_invalid",
            "instagram_ingress": env.get("SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED", "false").strip().lower() == "true",
            "instagram_send": env.get("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED", "false").strip().lower() == "true",
            "instagram_publications": env.get("SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED", "false").strip().lower() == "true",
            "instagram_direct_owner": env.get("SOCIALMEI_INSTAGRAM_DIRECT_OWNER", "unassigned") if env.get("SOCIALMEI_INSTAGRAM_DIRECT_OWNER", "unassigned") in {"dashboard", "n8n", "unassigned"} else "other_or_invalid",
            "wa_ingress": env.get("SOCIALMEI_WAHA_INGRESS_MODE", "disabled") if env.get("SOCIALMEI_WAHA_INGRESS_MODE", "disabled") in {"disabled", "isolated"} else "other_or_invalid",
            "wa_bot_enabled": env.get("SOCIALMEI_WHATSAPP_BOT_ENABLED", "false").strip().lower() == "true",
            "sentiment_enabled": env.get("SOCIALMEI_PROVIDER_SENTIMENT_ENABLED", "false").strip().lower() == "true",
            "sentiment_key_configured": len(env.get("SOCIALMEI_PROVIDER_SENTIMENT_KEY", "")) >= 32,
            "sentiment_workspaces_configured": bool(re.fullmatch(r"[1-9][0-9]{0,14}(?:,[1-9][0-9]{0,14})*", env.get("SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS", ""))),
        }
    if service == "waha":
        engine = env.get("WHATSAPP_DEFAULT_ENGINE", "unknown").strip().upper()
        result["default_engine"] = engine if engine in ("WEBJS", "GOWS") else "unknown_or_other"
    return result


def migration_summary(result):
    if not isinstance(result, dict):
        return {"available": False}
    versions = result.get("versions")
    if not isinstance(versions, list) or not all(
        isinstance(v, str) and re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", v)
        for v in versions
    ):
        return {"available": False}
    expected = sorted(EXPECTED_MIGRATIONS)
    return {
        "available": True,
        "total": len(versions),
        "max_prefix": max((int(v[:3]) for v in versions), default=None),
        "has_032": expected[0] in versions and result.get("bot_table") is True,
        "has_033": expected[1] in versions and result.get("sentiment_table") is True,
        "duplicate_versions": len(versions) != len(set(versions)),
        "ledger_has_gaps": sorted(int(v[:3]) for v in versions) != list(range(1, max((int(v[:3]) for v in versions), default=0) + 1)),
        "future_or_unknown_versions": any(int(v[:3]) > 33 for v in versions),
    }


def assess(report, expected_sha):
    blockers = []
    if not report["source"]["clean"]:
        blockers.append("checkout_com_alteracoes")
    if report["source"]["sha"] != expected_sha:
        blockers.append("checkout_diferente_do_candidato")
    services = report["containers"]
    for service in ("team_api", "team_gateway", "team_database", "n8n", "waha"):
        if not services[service].get("running"):
            blockers.append("container_indisponivel_" + service)
    if services["team_api"].get("health") != "healthy":
        blockers.append("api_nao_saudavel")
    if services["team_api"].get("host_ports_bound") or services["team_database"].get("host_ports_bound"):
        blockers.append("porta_privada_exposta_no_host")
    flags = services["team_api"].get("flags") or {}
    if not flags.get("auth_enabled"):
        blockers.append("autenticacao_da_api_desabilitada")
    if flags.get("instagram_send") and flags.get("instagram_direct_owner") != "dashboard":
        blockers.append("envio_instagram_sem_proprietario_correto")
    if flags.get("sentiment_enabled") and (
        not flags.get("sentiment_key_configured")
        or not flags.get("sentiment_workspaces_configured")
    ):
        blockers.append("sentimento_ativo_sem_credenciais_ou_allowlist")
    db = report["database"]
    if not db.get("available"):
        blockers.append("ledger_do_banco_indisponivel")
    elif db.get("duplicate_versions") or db.get("ledger_has_gaps") or db.get("future_or_unknown_versions"):
        blockers.append("ledger_incompativel")
    if services["team_database"].get("automation_network"):
        blockers.append("postgres_conectado_a_rede_automation")
    return {
        "preflight_unblocked": not blockers,
        "blockers": blockers,
        "deployment_executed": False,
        "provider_message_sent": False,
        "real_provider_validation": "pendente",
        "next_stage": "backup_restauravel_e_plano_de_deploy" if not blockers else "corrigir_bloqueios",
    }


def collect(expected_sha, runner=run_read_only, root=ROOT):
    git_head = runner(["git", "-C", str(root), "rev-parse", "HEAD"])
    status = runner(["git", "-C", str(root), "status", "--porcelain"])
    head = (git_head or "").strip()
    source = {"sha": head if re.fullmatch(r"[0-9a-f]{40}", head) else None,
              "clean": status is not None and not status.strip()}
    containers = {}
    for service, name in CONTAINERS.items():
        raw = runner(["docker", "inspect", "--type", "container", name])
        data = None
        if raw is not None:
            try:
                value = json.loads(raw)
                if isinstance(value, list) and len(value) == 1:
                    data = value[0]
            except (ValueError, TypeError):
                pass
        containers[service] = inspect_summary(data, service)

    raw_db = runner(
        ["docker", "exec", "-i", CONTAINERS["team_database"], "sh", "-c",
         'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -At'],
        input_text=SQL, timeout=25,
    )
    database = {"available": False}
    if raw_db is not None:
        for line in raw_db.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    database = migration_summary(json.loads(line))
                except (ValueError, TypeError):
                    pass
                break
    report = {"mode": "only_read", "candidate_sha": expected_sha,
              "source": source, "containers": containers, "database": database}
    report["decision"] = assess(report, expected_sha)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["team"], required=True)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_sha):
        parser.error("SHA de 40 caracteres obrigatório.")
    try:
        result = collect(args.expected_sha)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        # Do not print raw Docker inspect, .env, database credentials or errors.
        raise SystemExit("Inspecao indisponivel; nada foi alterado.") from None


if __name__ == "__main__":
    main()
