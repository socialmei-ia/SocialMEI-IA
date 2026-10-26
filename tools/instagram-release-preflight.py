"""Prepare-only by default; opt-in local Docker metadata inspection, without changes."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

_spec = importlib.util.spec_from_file_location(
    "instagram_pilot_inspect", Path(__file__).with_name("instagram-pilot-inspect.py")
)
pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot)

CONTAINERS = {
    "api": "socialmei-team-team-api-1",
    "gateway": "socialmei-team-team-gateway-1",
    "public_proxy": "socialmei-caddy",
}
FLAGS = (
    "SOCIALMEI_AUTH_ENABLED",
    "SOCIALMEI_SHARED_DATA_ENABLED",
    "SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED",
    "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED",
    "SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED",
    "SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED",
)
DB_SQL = """BEGIN READ ONLY;
SELECT jsonb_build_object(
 'migration_count', (SELECT COUNT(*) FROM socialmei.schema_migrations),
 'migration_max', (SELECT MAX(substring(version FROM '^[0-9]+')::integer) FROM socialmei.schema_migrations),
 'connected_unexpired_with_ciphertext', (SELECT COUNT(*) FROM socialmei.ig_meta_connections
   WHERE status='connected' AND expires_at>NOW() AND encrypted_token IS NOT NULL));
ROLLBACK;
"""
WORKFLOW_SQL = """BEGIN READ ONLY;
SELECT jsonb_build_object(
 'active', COALESCE((to_jsonb(w)->>'active')::boolean,false),
 'saved_equals_active', to_jsonb(w)->>'versionId'=to_jsonb(w)->>'activeVersionId',
 'method', COALESCE(n->'parameters'->>'httpMethod','GET'),
 'response_mode', COALESCE(n->'parameters'->>'responseMode','onReceived'),
 'raw_body', COALESCE((n->'parameters'->'options'->>'rawBody')::boolean,false),
 'path_sha256', encode(sha256(convert_to(COALESCE(n->'parameters'->>'path',''),'UTF8')),'hex'))
FROM public.workflow_entity w CROSS JOIN LATERAL jsonb_array_elements(w.nodes::jsonb) n
WHERE w.id IN ('LHlqroY2xzvpYAmD','A0EcNxcRvfWnMwKI')
  AND n->>'type'='n8n-nodes-base.webhook';
ROLLBACK;
"""


def safe_count(value):
    return value if type(value) is int and value >= 0 else None


def container_summary(value):
    config, state = value.get("Config", {}), value.get("State", {})
    env = dict(item.split("=", 1) for item in config.get("Env", []) if "=" in item)
    digest = value.get("Image", "")
    revision = (config.get("Labels") or {}).get("org.opencontainers.image.revision", "")
    health = (state.get("Health") or {}).get("Status", "unknown")
    return {
        "image_sha256": digest if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) else None,
        "revision": revision if re.fullmatch(r"[0-9a-f]{40}", revision) else None,
        "running": state.get("Running") is True,
        "health": health if health in {"healthy", "unhealthy", "starting"} else "unknown",
        "flags": {key: env.get(key, "").strip().lower() == "true" for key in FLAGS},
        "runtime_connect_mode": env.get("SOCIALMEI_INSTAGRAM_RUNTIME_MODE", "").strip().lower() == "connect",
    }


def proxy_routes(config):
    records = []

    def walk(node, paths=(), methods=()):
        if isinstance(node, list):
            for child in node:
                walk(child, paths, methods)
        elif isinstance(node, dict):
            matches = node.get("match")
            if matches:
                # Caddy match entries are OR alternatives; keep each branch separate.
                for match in matches:
                    walk({key: value for key, value in node.items() if key != "match"},
                         tuple(match.get("path", paths)), tuple(match.get("method", methods)))
                return
            if node.get("handler") == "reverse_proxy":
                deletions = (node.get("headers") or {}).get("request", {}).get("delete", [])
                records.append({
                    "paths": paths, "methods": methods,
                    "api": len(node.get("upstreams", [])) == 1 and node["upstreams"][0].get("dial") == "team-api:8000",
                    "strips": {header.lower() for header in deletions},
                })
            for key, child in node.items():
                if key not in {"match", "headers", "upstreams"}:
                    walk(child, paths, methods)

    walk(config.get("apps", {}).get("http", {}))
    media = [row for row in records if "/media/instagram/*" in row["paths"] and row["api"]]
    webhook = [row for row in records if "/webhooks/instagram" in row["paths"] and row["api"]]
    return {
        "media_get_to_api": any(row["methods"] == ("GET",) for row in media),
        "media_strips_authorization_cookie": bool(media) and all(
            {"authorization", "cookie"} <= row["strips"] for row in media),
        "media_proxy_get_only": bool(media) and all(row["methods"] == ("GET",) for row in media),
        "webhook_get_to_api": any(not row["methods"] or "GET" in row["methods"] for row in webhook),
        "webhook_post_to_api": any(not row["methods"] or "POST" in row["methods"] for row in webhook),
    }


def inspect_proxy(container):
    try:
        raw = pilot.run(["docker", "exec", container, "wget", "-qO-", "http://127.0.0.1:2019/config/"], timeout=20)
        config, source = json.loads(raw), "active"
    except (RuntimeError, ValueError):
        raw = pilot.run(["docker", "exec", container, "caddy", "adapt", "--config", "/etc/caddy/Caddyfile"], timeout=20)
        config, source = json.loads(raw), "disk_active_unconfirmed"
    return {"source": source, "privacy": pilot.proxy_summary(config, source), "routes": proxy_routes(config)}


def sql_read(container, sql, database=None):
    command = ['docker', 'exec', '-i', '--env',
               'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10s',
               container, 'sh', '-c',
               'exec psql -X -q -U "$POSTGRES_USER" -d "${1:-$POSTGRES_DB}" -v ON_ERROR_STOP=1 -At',
               'instagram-read-only']
    if database is not None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", database):
            raise RuntimeError("Banco não identificado.")
        command.append(database)
    raw = pilot.run(command, input=sql, timeout=20)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def database_summary():
    result = sql_read("socialmei-team-team-postgres-1", DB_SQL)[0]
    return {key: safe_count(result.get(key)) for key in (
        "migration_count", "migration_max", "connected_unexpired_with_ciphertext")}


def workflow_summary():
    fmt = '{{range .Config.Env}}{{$v := split . "="}}{{if eq (index $v 0) "DB_POSTGRESDB_DATABASE"}}{{index $v 1}}{{end}}{{end}}'
    database = pilot.run(["docker", "inspect", "--format", fmt, "socialmei-n8n"], timeout=20).strip()
    rows = sql_read("socialmei-postgres", WORKFLOW_SQL, database)
    output = []
    for row in rows:
        path_hash = row.get("path_sha256", "")
        output.append({
            "active": row.get("active") is True,
            "saved_equals_active": row.get("saved_equals_active") if type(row.get("saved_equals_active")) is bool else None,
            "method": row.get("method") if row.get("method") in {"GET", "POST"} else "other",
            "response_mode": row.get("response_mode") if row.get("response_mode") in {"onReceived", "lastNode", "responseNode", "streaming"} else "other",
            "raw_body": row.get("raw_body") is True,
            "path_sha256": path_hash if re.fullmatch(r"[0-9a-f]{64}", path_hash) else None,
        })
    return {"source": "saved_nodes_active_version_not_read", "webhooks": output}


def inspect_team():
    result = {"mode": "read_only_inspection", "target": "team", "checks": {}}
    checks = result["checks"]
    for name, container in CONTAINERS.items():
        try:
            value = json.loads(pilot.run(["docker", "inspect", container], timeout=20))[0]
            checks[name] = container_summary(value)
        except Exception:
            checks[name] = {"available": False}
    for name, inspect in (
        ("gateway_routes", lambda: inspect_proxy(CONTAINERS["gateway"])),
        ("public_proxy_privacy", lambda: inspect_proxy(CONTAINERS["public_proxy"])),
        ("database", database_summary), ("workflows", workflow_summary),
    ):
        try:
            checks[name] = inspect()
        except Exception:
            checks[name] = {"available": False}
    result["complete"] = all(value.get("available", True) for value in checks.values())
    gateway = checks["gateway_routes"]
    result["gateway_requirements_confirmed"] = (
        gateway.get("source") == "active" and all(gateway.get("routes", {}).values())
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["team"], required=True)
    parser.add_argument("--inspect", action="store_true", help="Read metadata through the local Docker daemon; never SSH or modify configuration.")
    args = parser.parse_args(argv)
    result = inspect_team() if args.inspect else {
        "mode": "prepare_only", "target": "team", "inspection_requested": False,
        "required_gateway": {"media_get_to_api": True, "strip_authorization_cookie": True,
                             "webhook_get_post_to_api": True},
        "mutations": False, "calls_meta": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.inspect and not result["complete"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("Inspeção não concluída; nenhum detalhe privado foi exibido.")
