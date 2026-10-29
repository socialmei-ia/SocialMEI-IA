#!/usr/bin/env python3
"""Read-only Team v33 preflight before shipping candidate API/gateway images.

The live Team checkout has a private Caddy hotfix; never reset it. A new
Compose file must NOT replace the current running topology: this audit records
the network/mount/label invariants that an image-only publisher must preserve.
No Docker build, pull, restart, Compose up, migration, env display or API send.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path("/home/ubuntu/socialmei-team")
SOURCE = Path("/home/ubuntu/socialmei-backups/team-v33-c19d44b6ef6b/source")
EXPECTED_SHA = "c19d44b6ef6b8f125e6cafe60a7adfc0477cf454"
BACKUP_NAME = "team-auto-20261029-005509-e2bfd3"
DB_NAME = "socialmei-team-team-postgres-1"
API_NAME = "socialmei-team-team-api-1"
GATEWAY_NAME = "socialmei-team-team-gateway-1"
EXPECTED_MOUNTS = (
    "/etc/caddy/Caddyfile",
    "/etc/caddy/private",
    "/srv/frontend/config.js",
)
SENSITIVE_FLAGS = (
    "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED",
    "SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED",
    "SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED",
    "SOCIALMEI_WHATSAPP_BOT_ENABLED",
    "SOCIALMEI_PROVIDER_SENTIMENT_ENABLED",
)
EXPECTED_NEW_TABLES = (
    "wa_bot_access", "wa_bot_conversations", "wa_bot_decisions",
    "me_provider_sentiment_jobs",
)
POSTGRES_LEDGER = (
    "BEGIN TRANSACTION READ ONLY;\n"
    "SELECT COALESCE(json_agg(version ORDER BY version),'[]'::json)::text "
    "FROM socialmei.schema_migrations;\n"
    "ROLLBACK;\n"
)


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def command(argv, *, input_text=None, timeout=20):
    try:
        p = subprocess.run(argv, input=input_text, text=True, capture_output=True,
                           check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("comando_indisponivel") from None
    require(p.returncode == 0, "comando_falhou")
    return p.stdout


def docker(*args, **kw):
    require(Path("/var/run/docker.sock").is_socket(), "docker_local_indisponivel")
    return command(["docker", "--host=unix:///var/run/docker.sock", *args], **kw)


def inspect(name):
    raw = json.loads(docker("inspect", "--type", "container", name))
    require(len(raw) == 1 and raw[0].get("Name") == "/" + name,
            "container_invalido")
    return raw[0]


def env_flags(api):
    env = {}
    for line in api.get("Config", {}).get("Env") or []:
        if "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    require(env.get("SOCIALMEI_AUTH_ENABLED", "").lower()
            in ("true", "1", "yes", "on"), "auth_nao_confirmada")
    disabled = {
        name: env.get(name, "false").strip().lower() in ("", "0", "false")
        for name in SENSITIVE_FLAGS
    }
    require(all(disabled.values()), "envios_ou_ingresso_ativos")
    require(env.get("SOCIALMEI_WAHA_INGRESS_MODE", "disabled").lower()
            in ("", "disabled"), "ingresso_waha_ativo")
    return {"auth_enabled": True, "providers_disabled": all(disabled.values())}


def container_summary(name, obj):
    state = obj.get("State") or {}
    config = obj.get("Config") or {}
    host = obj.get("HostConfig") or {}
    labels = config.get("Labels") or {}
    nets = sorted((obj.get("NetworkSettings") or {}).get("Networks") or {})
    mounts = obj.get("Mounts") or []
    require(state.get("Running") is True, "servico_nao_ativo")
    require(not host.get("PortBindings"), "porta_publicada_no_team")
    require(len(obj.get("Image", "")) == 71
            and re.fullmatch("sha256:[a-f0-9]{64}", obj["Image"]),
            "imagem_instalada_invalida")
    require(labels.get("com.docker.compose.project") == "socialmei-team",
            "servico_fora_do_compose_team")
    require(labels.get("com.docker.compose.service") == name.removeprefix(
        "socialmei-team-").removesuffix("-1"),
        "servico_compose_inesperado")
    require(bool(labels.get("com.docker.compose.project.config_files"))
            and bool(labels.get("com.docker.compose.project.working_dir")),
            "origem_compose_ausente")
    return {
        "running": True,
        "health": (state.get("Health") or {}).get("Status", "not_configured"),
        "image_id": obj["Image"],
        "networks": nets,
        "has_compose_provenance": True,
        "bind_targets_readonly": sorted(
            m["Destination"] for m in mounts
            if m.get("Type") == "bind" and m.get("RW") is False
        ),
        "bind_targets_writable": sorted(
            m["Destination"] for m in mounts
            if m.get("Type") == "bind" and m.get("RW") is True
        ),
    }


def ledger_current(names):
    query = docker(
        "exec", "-i", DB_NAME, "sh", "-c",
        'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -At',
        input_text=POSTGRES_LEDGER,
    )
    lines = [line.strip() for line in query.splitlines()
             if line.strip().startswith("[")]
    require(len(lines) == 1, "ledger_indisponivel")
    got = json.loads(lines[0])
    require(got == names, "ledger_nao_esta_em_033")
    query = (
        "BEGIN TRANSACTION READ ONLY;\n"
        "SELECT json_build_object("
        + ",".join(
            f"'{name}', to_regclass('socialmei.{name}') IS NOT NULL"
            for name in EXPECTED_NEW_TABLES
        )
        + ")::text;\nROLLBACK;\n"
    )
    raw = docker(
        "exec", "-i", DB_NAME, "sh", "-c",
        'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -At',
        input_text=query,
    )
    rows = [line.strip() for line in raw.splitlines() if line.strip().startswith("{")]
    require(len(rows) == 1, "tabelas_033_indisponiveis")
    result = json.loads(rows[0])
    require(set(result) == set(EXPECTED_NEW_TABLES) and all(
        value is True for value in result.values()
    ), "tabelas_033_ausentes")


def prepared_source():
    require(SOURCE.is_dir() and not SOURCE.is_symlink(), "stage_ausente")
    require(command(["git", "-C", str(SOURCE), "rev-parse", "HEAD"]).strip()
            == EXPECTED_SHA, "stage_divergente")
    require(not command(
        ["git", "-C", str(SOURCE), "status", "--porcelain=v1", "--untracked-files=all"]
    ).strip(), "stage_modificado")
    versions = sorted(p.name for p in (SOURCE / "database/migrations").glob("*.sql"))
    require(len(versions) == 33 and len(set(versions)) == 33, "migrations_de_stage_divergentes")
    require(all(name[:3] == f"{i:03}" and re.fullmatch(
        r"\d{3}_[a-z0-9_]+\.sql", name)
        for i, name in enumerate(versions, 1)), "migrations_de_stage_divergentes")
    require(versions[-2:] == [
        "032_whatsapp_bot_conversations.sql", "033_provider_sentiment_jobs.sql",
    ], "migrations_de_stage_divergentes")
    for path in (
        "python-service/Dockerfile", "deploy/team/Dockerfile",
        "frontend/socialmei-app.html", "deploy/team/Caddyfile",
    ):
        require((SOURCE / path).is_file(), "fonte_de_imagem_incompleta")
    return versions


def gateway_guard(obj, summary):
    actual = {m["Destination"]: m for m in obj.get("Mounts") or []}
    require(all(dest in actual and actual[dest].get("Type") == "bind"
                and actual[dest].get("RW") is False
                for dest in EXPECTED_MOUNTS), "montagem_privada_do_caddy_ausente")
    require(set(summary["bind_targets_readonly"]) >= set(EXPECTED_MOUNTS),
            "montagem_privada_do_caddy_ausente")
    require(not summary["bind_targets_writable"],
            "gateway_com_montagem_gravavel")
    # The running gateway's private Caddyfile takes precedence over the
    # Caddyfile baked into its image. Do not replace it from SOURCE.
    caddy_mount = actual["/etc/caddy/Caddyfile"]["Source"]
    require(Path(caddy_mount).is_file(), "caddyfile_privado_indisponivel")
    caddy_sha = hashlib.sha256(Path(caddy_mount).read_bytes()).hexdigest()
    installed_sha = docker(
        "exec", GATEWAY_NAME, "sha256sum", "/etc/caddy/Caddyfile",
    ).split()[0]
    require(caddy_sha == installed_sha, "caddyfile_montado_divergente")
    return {
        "private_caddyfile_mounted_readonly": True,
        "private_caddyfile_sha256": caddy_sha,
        "new_gateway_must_preserve_private_mount": True,
    }


def run_audit():
    versions = prepared_source()
    containers = {
        API_NAME: inspect(API_NAME),
        GATEWAY_NAME: inspect(GATEWAY_NAME),
        DB_NAME: inspect(DB_NAME),
    }
    summaries = {
        "api": container_summary(API_NAME, containers[API_NAME]),
        "gateway": container_summary(GATEWAY_NAME, containers[GATEWAY_NAME]),
        "database": container_summary(DB_NAME, containers[DB_NAME]),
    }
    require(summaries["api"]["health"] == "healthy"
            and summaries["database"]["health"] == "healthy", "api_ou_banco_sem_health")
    require(len(set(summaries["api"]["networks"]) &
                set(summaries["database"]["networks"])) == 1,
            "rede_do_banco_ambigua")
    require("socialmei_team_automation" not in summaries["database"]["networks"],
            "banco_na_rede_de_automacao")
    require(not summaries["database"]["bind_targets_writable"], "montagem_gravavel_no_banco")
    flags = env_flags(containers[API_NAME])
    gateway = gateway_guard(containers[GATEWAY_NAME], summaries["gateway"])
    ledger_current(versions)
    require((SOURCE.parent / "stage-receipt.json").is_file(),
            "recibo_do_stage_ausente")
    require(Path("/home/ubuntu/socialmei-backups", BACKUP_NAME, "concluido.json").is_file(),
            "recibo_do_backup_ausente")
    docker_images = {}
    for service in ("team-api", "team-gateway"):
        tag = f"socialmei-v33/{service}:{EXPECTED_SHA}"
        try:
            values = json.loads(docker("image", "inspect", tag))
        except RuntimeError:
            docker_images[service] = False
        else:
            require(len(values) == 1 and (values[0].get("Config") or {}).get(
                "Labels", {}).get("org.opencontainers.image.revision") == EXPECTED_SHA,
                "imagem_candidata_com_sha_errado")
            docker_images[service] = True
    mem = 0
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            mem = int(line.split()[1]) // 1024
            break
    return {
        "mode": "read_only_runtime_image_audit",
        "stage_sha": EXPECTED_SHA,
        "database_migrations": 33,
        "backup_receipt_present": True,
        "flags": flags,
        "services": summaries,
        "gateway_privacy": gateway,
        "candidate_images_preloaded": docker_images,
        "memory_available_mib": mem,
        "disk_available_gib": round(shutil.disk_usage("/").free / 1024**3, 1),
        "compose_source_drift_not_assumed_safe": True,
        "only_image_and_explicit_revision_may_change": True,
        "deployment_executed": False,
        "docker_build_executed": False,
        "provider_message_sent": False,
        "next_stage": "build_candidate_images_outside_low_memory_vps_then_guarded_publish",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["team"], required=True)
    args = parser.parse_args()
    try:
        report = run_audit()
    except RuntimeError as exc:
        # Never echo raw source file contents, credentials or Docker stderr.
        allowed = {
            "stage_ausente", "stage_divergente", "stage_modificado",
            "migrations_de_stage_divergentes", "fonte_de_imagem_incompleta",
            "container_invalido", "servico_nao_ativo", "porta_publicada_no_team",
            "imagem_instalada_invalida", "servico_fora_do_compose_team",
            "servico_compose_inesperado", "origem_compose_ausente",
            "ledger_nao_esta_em_033", "ledger_indisponivel",
            "tabelas_033_indisponiveis", "tabelas_033_ausentes",
            "api_ou_banco_sem_health", "rede_do_banco_ambigua",
            "banco_na_rede_de_automacao", "montagem_gravavel_no_banco",
            "auth_nao_confirmada", "envios_ou_ingresso_ativos",
            "ingresso_waha_ativo", "montagem_privada_do_caddy_ausente",
            "gateway_com_montagem_gravavel", "caddyfile_privado_indisponivel",
            "caddyfile_montado_divergente", "recibo_do_stage_ausente",
            "recibo_do_backup_ausente", "imagem_candidata_com_sha_errado",
            "comando_falhou", "comando_indisponivel", "docker_local_indisponivel",
        }
        print(json.dumps({
            "mode": "read_only_runtime_image_audit",
            "status": "blocked",
            "error_code": str(exc) if str(exc) in allowed else "erro_sanitizado",
            "deployment_executed": False, "docker_build_executed": False,
        }))
        raise SystemExit(1) from None
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
