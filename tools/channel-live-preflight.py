#!/usr/bin/env python3
"""Single read-only, sanitized preflight of the live SocialMEI channel stack.

Run on the AWS Docker host. Never starts/stops services, sends messages, changes
database state, reads message contents, or prints environment variable values.
Only deliberately allowlisted metadata leaves the process.
"""
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

CONTAINERS = {
    "api": "socialmei-team-team-api-1",
    "gateway": "socialmei-team-team-gateway-1",
    "worker": "socialmei-menu-worker-continuo",
    "menu_api": "socialmei-menu-public-api-v3",
    "webjs": "socialmei-waha",
    "gows": "socialmei-waha-gows-piloto",
    "n8n": "socialmei-n8n",
    "caddy": "socialmei-caddy",
}

SHA = re.compile(r"sha256:[a-f0-9]{64}\Z")
REVISION = re.compile(r"[a-f0-9]{40}\Z")
SESSION_STATES = {
    "STOPPED", "STARTING", "SCAN_QR_CODE", "PASSKEY_REQUIRED",
    "PASSKEY_CONFIRMATION_REQUIRED", "WORKING", "FAILED",
}
BACKUP = Path("/var/lib/socialmei-prisma-cutover/waha-session-backups")
BACKUP_HMAC = Path(
    "/var/lib/socialmei-prisma-cutover/gows-pairing-prep/gows-webhook-backup.json"
)

# This JavaScript is executed only against WAHA's local HTTP GET endpoint.
# It never prints or returns any session name, QR, message, contact or API key.
SESSION_QUERY = r"""
(async () => {
  const key = process.env.WAHA_API_KEY || process.env.WHATSAPP_API_KEY || "";
  const response = await fetch("http://127.0.0.1:3000/api/sessions?all=true", {
    headers: key ? {"X-Api-Key": key} : {},
    signal: AbortSignal.timeout(8000)
  });
  if (!response.ok) process.exit(2);
  const items = await response.json();
  if (!Array.isArray(items) || items.length > 20) process.exit(3);
  console.log(JSON.stringify(items.map(s => ({
    state: s.status,
    hooks: Array.isArray(s.config?.webhooks) ? s.config.webhooks.length : null
  }))));
})().catch(() => process.exit(4));
"""

# Executes inside the existing API container. The transaction is read-only;
# no row data, database name or credentials are returned to the host.
SCHEMA_QUERY = r"""
import json
from database import connect
with connect() as conn:
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL statement_timeout = '5s'")
    count = conn.execute("SELECT count(*) FROM socialmei.schema_migrations").fetchone()[0]
    print(json.dumps({"count": int(count)}))
"""


class ProbeUnavailable(Exception):
    pass


def command(*args, timeout=20):
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ProbeUnavailable() from None
    if result.returncode != 0 or len(result.stdout) > 120000:
        raise ProbeUnavailable()
    # Never surface raw output or stderr on failures.
    return result.stdout


def docker_inspect(name):
    try:
        obj = json.loads(command("docker", "inspect", "--type=container", name))
        if not isinstance(obj, list) or len(obj) != 1:
            raise ProbeUnavailable()
        if obj[0].get("Name") != "/" + name:
            raise ProbeUnavailable()
        return obj[0]
    except (ValueError, TypeError, KeyError):
        raise ProbeUnavailable() from None


def env_values(obj):
    return dict(
        item.split("=", 1)
        for item in obj.get("Config", {}).get("Env", []) or []
        if isinstance(item, str) and "=" in item
    )


def allowlisted_state(obj):
    s = obj.get("State") or {}
    health = (s.get("Health") or {}).get("Status", "sem_healthcheck")
    if health not in {"healthy", "unhealthy", "starting", "sem_healthcheck"}:
        health = "desconhecido"
    cfg = obj.get("Config") or {}
    labels = cfg.get("Labels") or {}
    image_id = obj.get("Image")
    revision = labels.get("org.opencontainers.image.revision", "")
    return {
        "running": s.get("Running") is True,
        "health": health,
        "image_id": image_id if isinstance(image_id, str) and SHA.fullmatch(image_id) else None,
        "source_revision": revision if isinstance(revision, str) and REVISION.fullmatch(revision) else None,
        "compose_project_ok": isinstance(labels.get("com.docker.compose.project"), str),
    }


def session_summary(raw):
    if not isinstance(raw, list) or len(raw) > 20:
        raise ProbeUnavailable()
    status = []
    hooks = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProbeUnavailable()
        value = item.get("state")
        status.append(value if value in SESSION_STATES else "DESCONHECIDO")
        number = item.get("hooks")
        hooks.append(number if type(number) is int and 0 <= number <= 100 else None)
    return {
        "count": len(raw),
        "states": status,
        "webhook_counts": hooks,
        "working_count": status.count("WORKING"),
    }


def get_sessions(container):
    output = command(
        "docker", "exec", container, "node", "-e", SESSION_QUERY, timeout=15
    )
    try:
        return session_summary(json.loads(output))
    except (ValueError, TypeError):
        raise ProbeUnavailable() from None


def schema_count():
    output = command(
        "docker", "exec", CONTAINERS["api"], "python", "-c",
        SCHEMA_QUERY, timeout=15
    )
    try:
        count = json.loads(output)["count"]
    except (ValueError, TypeError, KeyError):
        raise ProbeUnavailable() from None
    if type(count) is not int or not 0 <= count <= 1000:
        raise ProbeUnavailable()
    return count


def flag(value):
    return str(value).strip().lower() == "true"


def api_flags(obj):
    values = env_values(obj)
    compose = (obj.get("Config", {}).get("Labels") or {}).get(
        "com.docker.compose.project.config_files", ""
    )
    return {
        "receptor_dual_webjs_gows": values.get("SOCIALMEI_WAHA_WEBHOOK_ENGINE") == "WEBJS,GOWS",
        "modo_waha_team_pilot": values.get("SOCIALMEI_WAHA_INGRESS_MODE") == "team-pilot",
        "overlay_dual_no_compose": isinstance(compose, str) and
            "gows-dual-live-20261109/compose.gows-dual.yaml" in compose,
        "instagram_connect": values.get("SOCIALMEI_INSTAGRAM_RUNTIME_MODE") == "connect",
        "instagram_ingress": flag(values.get("SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED")),
        "instagram_send": flag(values.get("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED")),
        "instagram_publish": flag(values.get("SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED")),
        "instagram_proxy_privacy_reviewed": flag(
            values.get("SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED")
        ),
    }


def worker_flags(obj):
    values = env_values(obj)
    target = values.get("SOCIALMEI_MENU_WAHA_URL", "")
    try:
        parsed = urlparse(target)
        correct = (parsed.scheme == "http" and
                   parsed.hostname == CONTAINERS["webjs"] and
                   parsed.port == 3000 and
                   not parsed.username and not parsed.password)
    except ValueError:
        correct = False
    return {"destino_webjs": correct}


def main():
    result = {
        "escopo": "somente_leitura",
        "containers": {},
        "api": None,
        "worker": None,
        "webjs": None,
        "gows": None,
        "migrations_team": None,
        "backup_webjs_presente": None,
        "backup_hmac_gows_presente": None,
        "probes_indisponiveis": [],
    }
    inspected = {}
    for key, name in CONTAINERS.items():
        try:
            obj = docker_inspect(name)
            inspected[key] = obj
            result["containers"][key] = allowlisted_state(obj)
        except ProbeUnavailable:
            result["containers"][key] = {"disponivel": False}
            result["probes_indisponiveis"].append("container_" + key)
    if "api" in inspected:
        result["api"] = api_flags(inspected["api"])
        try:
            result["migrations_team"] = schema_count()
        except ProbeUnavailable:
            result["probes_indisponiveis"].append("migrations_team")
    if "worker" in inspected:
        result["worker"] = worker_flags(inspected["worker"])
    for key in ("webjs", "gows"):
        if key in inspected:
            try:
                result[key] = get_sessions(CONTAINERS[key])
            except ProbeUnavailable:
                result["probes_indisponiveis"].append("sessao_" + key)
    try:
        result["backup_webjs_presente"] = BACKUP.is_dir() and any(
            file.is_file() for file in BACKUP.glob("webjs-session-*.tar.gz")
        )
        result["backup_hmac_gows_presente"] = BACKUP_HMAC.is_file()
    except OSError:
        result["probes_indisponiveis"].append("backups")
    api = result["api"] or {}
    worker = result["worker"] or {}
    webjs = result["webjs"] or {}
    gows = result["gows"] or {}
    result["whatsapp_preservado"] = bool(
        result["containers"]["api"].get("running") is True
        and result["containers"]["api"].get("health") == "healthy"
        and result["containers"]["worker"].get("running") is True
        and result["containers"]["webjs"].get("running") is True
        and result["containers"]["gows"].get("running") is True
        and api.get("receptor_dual_webjs_gows")
        and api.get("modo_waha_team_pilot")
        and worker.get("destino_webjs")
        and webjs.get("working_count") == 1
        and webjs.get("webhook_counts") == [1]
        and gows.get("webhook_counts") == [0]
    )
    # Never promote Instagram or GOWS solely based on metadata and synthetic tests.
    result["instagram_real_homologado"] = False
    result["gows_real_homologado"] = False
    result["resultado"] = (
        "PARCIAL" if result["probes_indisponiveis"] else
        "BASELINE_COLETADO"
    )
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    return 0 if not result["probes_indisponiveis"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
