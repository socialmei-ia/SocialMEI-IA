#!/usr/bin/env python3
"""Private Instagram #212 n8n staging, no service or workflow mutation.

Exports the existing n8n workflow into a root-private AWS backup, reads connected
OAuth account bindings in a READ ONLY transaction, and stages a disabled-at-runtime
relay environment for later controlled activation. Never exposes credentials,
payloads or external account IDs in stdout, never touches WhatsApp, and never
publishes a workflow or restarts a container.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import uuid

ROOT = Path("/var/lib/socialmei-ig212-backups/ig212-c2edda7b5aec47af9eef53908592e3e3")
API = "socialmei-team-team-api-1"
GW = "socialmei-team-team-gateway-1"
N8N = "socialmei-n8n"
PG = "socialmei-team-team-postgres-1"
WORKFLOW = "LHlqroY2xzvpYAmD"
SRC = ROOT / "instagram212-n8n-export.private.json"
ENV = ROOT / "instagram212-n8n-relay.private.env"
BINDINGS = ROOT / "instagram212-account-bindings.private.json"
HOTFIX = "socialmei-v33/team-api:345a074310673640084c7634e3da75dd72491813-psycopg337"
GATEWAY = "socialmei-v33/team-gateway:345a074310673640084c7634e3da75dd72491813"


class Refuse(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Refuse(code)


def call(args, timeout=90):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise Refuse("command_unavailable_or_timeout") from None
    require(p.returncode == 0, "command_failed")
    return p.stdout


def inspect(name):
    value = json.loads(call(["docker", "inspect", "--type=container", name], timeout=30))
    require(len(value) == 1, "container_not_found")
    return value[0]


def private(path):
    require(path.exists() and path.is_file() and not path.is_symlink()
            and path.stat().st_uid == 0
            and stat.S_IMODE(path.stat().st_mode) == 0o600,
            "private_file_unexpected")
    return path


def create_bytes(path, content):
    # Idempotence: existing staging is never silently overwritten or rotated.
    if path.exists() or path.is_symlink():
        require(private(path).read_bytes() == content, "stage_changed")
        return
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_workflow():
    if SRC.exists():
        data = json.loads(private(SRC).read_text())
        require(isinstance(data, list) and len(data) == 1 or isinstance(data, dict),
                "workflow_export_invalid")
        return data[0] if isinstance(data, list) else data
    tmp_name = "socialmei-ig212-export-" + uuid.uuid4().hex + ".json"
    tmp_path = "/tmp/" + tmp_name
    try:
        call(["docker", "exec", N8N, "n8n", "export:workflow",
              "--id=" + WORKFLOW, "--output=" + tmp_path], timeout=90)
        tmp_host = ROOT / (".n8n-tmp-" + uuid.uuid4().hex)
        try:
            call(["docker", "cp", N8N + ":" + tmp_path, str(tmp_host)], timeout=45)
            os.chmod(tmp_host, 0o600)
            data = json.loads(private(tmp_host).read_text())
            workflow = data[0] if isinstance(data, list) and len(data) == 1 else data
            require(isinstance(workflow, dict), "workflow_export_invalid")
            require(workflow.get("id") == WORKFLOW and
                    isinstance(workflow.get("nodes"), list) and
                    isinstance(workflow.get("connections"), dict),
                    "workflow_export_mismatch")
            require(workflow.get("active") is True, "workflow_inactive")
            create_bytes(SRC, tmp_host.read_bytes())
            return workflow
        finally:
            if tmp_host.exists() and not tmp_host.is_symlink():
                tmp_host.unlink()
    finally:
        # Removal is confined to a newly generated ephemeral file; it is NOT
        # a workflow operation or deletion of n8n data.
        subprocess.run(["docker", "exec", N8N, "rm", "-f", tmp_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=20, check=False)


def read_bindings():
    if BINDINGS.exists():
        value = json.loads(private(BINDINGS).read_text())
        require(isinstance(value, dict) and 1 <= len(value) <= 2,
                "existing_binding_invalid")
        return value
    sql = (
        "BEGIN READ ONLY; SELECT COALESCE(json_agg(json_build_object("
        "'source',external_account_id,"
        "'workspace_id',workspace_id,"
        "'connection_account_id',external_account_id"
        ")),'[]'::json) FROM socialmei.ig_meta_connections "
        "WHERE status='connected' AND expires_at>NOW(); COMMIT;"
    )
    raw = call([
        "docker", "exec", PG, "sh", "-c",
        'psql -X -A -t -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"',
        "sh", sql
    ], timeout=35)
    # psql outputs one JSON row plus command status (BEGIN/COMMIT).
    rows = [line.strip() for line in raw.decode().splitlines()
            if line.strip().startswith("[") and line.strip().endswith("]")]
    require(len(rows) == 1, "oauth_query_unavailable")
    items = json.loads(rows[0])
    require(isinstance(items, list) and 1 <= len(items) <= 2,
            "oauth_connected_account_unavailable")
    bindings = {}
    for item in items:
        source, account, workspace = (
            item["source"], item["connection_account_id"], item["workspace_id"]
        )
        require(isinstance(source, str) and re.fullmatch(r"[0-9]{1,40}", source)
                and isinstance(account, str) and re.fullmatch(r"[0-9]{1,40}", account)
                and type(workspace) is int and workspace > 0
                and source not in bindings,
                "oauth_binding_invalid")
        bindings[source] = {"workspace_id": workspace,
                            "connection_account_id": account}
    create_bytes(BINDINGS, (json.dumps(bindings, sort_keys=True) + "\n").encode())
    return bindings


def prepare():
    require(os.geteuid() == 0 and ROOT.is_dir() and not ROOT.is_symlink()
            and ROOT.stat().st_uid == 0
            and stat.S_IMODE(ROOT.stat().st_mode) == 0o700,
            "private_backup_unavailable")
    api, gw, n8n, db = (inspect(x) for x in (API, GW, N8N, PG))
    require(api.get("Config", {}).get("Image") == HOTFIX and
            gw.get("Config", {}).get("Image") == GATEWAY and
            api.get("State", {}).get("Health", {}).get("Status") == "healthy" and
            n8n["State"].get("Running") is True and
            db["State"].get("Running") is True,
            "runtime_not_ready")
    require(private(ROOT / "hotfix337-publication.private.json")
            and json.loads((ROOT / "hotfix337-publication.private.json").read_text()).get(
                "phase") == "published_api_gateway_only",
            "hotfix_receipt_unavailable")
    env = dict(x.split("=", 1) for x in api["Config"].get("Env", []) if "=" in x)
    require(env.get("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED", "false").lower() == "false"
            and env.get("SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED", "false").lower() == "false"
            and env.get("SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED", "false").lower() == "false",
            "ingress_or_sending_already_active")
    meta = env.get("SOCIALMEI_INSTAGRAM_CLIENT_SECRET", "")
    require(isinstance(meta, str) and
            32 <= len(meta) <= 256 and
            re.fullmatch(r"[!-~]+", meta) and "'" not in meta,
            "meta_secret_unsuitable_for_private_staging")

    workflow = read_workflow()
    hooks = [node for node in workflow["nodes"]
             if node.get("type") == "n8n-nodes-base.webhook"
             and node.get("parameters", {}).get("httpMethod") == "POST"]
    require(len(hooks) == 1, "workflow_webhook_ambiguous")
    require(workflow.get("active") is True
            and 8 <= len(workflow["nodes"]) <= 25,
            "workflow_structure_unexpected")
    bindings = read_bindings()
    if not ENV.exists():
        key = secrets.token_urlsafe(48)
        settings = {
            "SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED": "true",
            "SOCIALMEI_INSTAGRAM_N8N_AUTH_MODE": "header",
            "SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY": key,
            "SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET": meta,
            "SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS": json.dumps(
                bindings, separators=(",", ":"), sort_keys=True),
        }
        require(all("\n" not in v and "\r" not in v and "'" not in v
                    for v in settings.values()), "private_env_unsuitable")
        content = "".join(k + "='" + v + "'\n" for k, v in settings.items())
        create_bytes(ENV, content.encode())
    else:
        private(ENV)
        names = set(x.partition("=")[0] for x in ENV.read_text().splitlines())
        require(names == {
            "SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED",
            "SOCIALMEI_INSTAGRAM_N8N_AUTH_MODE",
            "SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY",
            "SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET",
            "SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS",
        }, "existing_staging_env_unexpected")

    active_v = workflow.get("activeVersionId") or workflow.get("publishedVersionId")
    saved_v = workflow.get("versionId")
    return {
        "resultado": "INSTAGRAM_212_N8N_PRIVADO_PREPARADO",
        "n8n_export_privado": True,
        "n8n_workflow_id_correto": True,
        "n8n_nos_salvos": len(workflow["nodes"]),
        "n8n_webhook_post": len(hooks),
        "publicado_versus_salvo": (
            "diferentes" if active_v and saved_v and active_v != saved_v else
            "iguais" if active_v and saved_v else "nao_comprovado_pelo_export"
        ),
        "contas_oauth_vinculadas": len(bindings),
        "credencial_relay_preparada": True,
        "meta_secret_proveniencia": "oauth_client_secret_existente",
        "whatsapp_modificado": False,
        "n8n_workflow_modificado": False,
        "api_reiniciada": False,
        "recepcao_instagram_ativada": False,
    }


def main():
    try:
        print(json.dumps(prepare(), ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        code = str(e) if isinstance(e, Refuse) and re.fullmatch(
            r"[a-z0-9_]+", str(e)) else "preparacao_nao_concluida"
        print(json.dumps({"resultado": "BLOQUEADO", "motivo": code,
                          "alteracoes_em_producao": False,
                          "arquivos_privados_parciais_possiveis": True},
                         ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
