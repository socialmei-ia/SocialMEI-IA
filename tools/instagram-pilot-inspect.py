"""Read-only team Instagram preflight. Prints allowlisted metadata, never credentials."""
import json
import re
import subprocess

API = "socialmei-team-team-api-1"
CLIENT_ID = "27816981071315232"
ORIGIN = "https://socialmei-ia.54-94-213-7.sslip.io"


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError("Consulta indisponível; detalhes privados não foram exibidos.")
    return result.stdout


def proxy_summary(config, source):
    logs = config.get("logging", {}).get("logs", {})
    output = []
    for settings in logs.values():
        encoder = settings.get("encoder") or {}
        fields = encoder.get("fields") or {}
        output.append({
            "encoder": encoder.get("format") if encoder.get("format") in {"filter", "json", "console"} else "outro/default",
            "remove_uri_completa": encoder.get("format") == "filter" and fields.get("request>uri", {}).get("filter") == "delete",
            "remove_headers_request": encoder.get("format") == "filter" and fields.get("request>headers", {}).get("filter") == "delete",
        })
    return {"fonte": source, "logging_explicito": bool(logs), "encoders": output}


def inspect_proxy(container):
    try:
        value = run(["docker", "exec", container, "wget", "-qO-", "http://127.0.0.1:2019/config/"])
        return proxy_summary(json.loads(value), "configuracao_ativa")
    except (RuntimeError, ValueError):
        try:
            value = run(["docker", "exec", container, "caddy", "adapt", "--config", "/etc/caddy/Caddyfile"])
            return proxy_summary(json.loads(value), "arquivo_ativo_nao_confirmado")
        except (RuntimeError, ValueError):
            return {"fonte": "nao_confirmada"}


def api_summary(env):
    version = env.get("SOCIALMEI_INSTAGRAM_GRAPH_VERSION", "")
    return {
        "modo": env.get("SOCIALMEI_INSTAGRAM_RUNTIME_MODE", "disabled") if env.get("SOCIALMEI_INSTAGRAM_RUNTIME_MODE", "disabled") in {"disabled", "connect"} else "outro",
        "client_id_corresponde_ao_painel": env.get("SOCIALMEI_INSTAGRAM_CLIENT_ID") == CLIENT_ID,
        "app_secret_presente": bool(env.get("SOCIALMEI_INSTAGRAM_CLIENT_SECRET")),
        "keyring_presente": bool(env.get("SOCIALMEI_INSTAGRAM_TOKEN_KEYRING")),
        "key_id_presente": bool(env.get("SOCIALMEI_INSTAGRAM_TOKEN_ACTIVE_KEY_ID")),
        "origin_corresponde_ao_site": env.get("SOCIALMEI_AUTH_ORIGIN") == ORIGIN,
        "graph_version": version if re.fullmatch(r"v[1-9][0-9]{0,2}\.0", version) else "nao_configurada",
        "webhook_token_presente": bool(env.get("SOCIALMEI_INSTAGRAM_WEBHOOK_VERIFY_TOKEN")),
    }


def workflow_versions():
    fmt = '{{range .Config.Env}}{{$v := split . "="}}{{if eq (index $v 0) "DB_POSTGRESDB_DATABASE"}}{{index $v 1}}{{end}}{{end}}'
    db = run(["docker", "inspect", "--format", fmt, "socialmei-n8n"]).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", db):
        raise RuntimeError("Banco não identificado.")
    sql = """
    SELECT jsonb_build_object(
      'workflow', w.id,
      'salva_igual_ativa', to_jsonb(w)->>'versionId' = to_jsonb(w)->>'activeVersionId',
      'versoes_graph', (SELECT jsonb_agg(DISTINCT version) FROM (
        SELECT substring(n->'parameters'->>'url' FROM '/(v[0-9]{1,3}\\.0)/') AS version
        FROM jsonb_array_elements(w.nodes::jsonb) n
        WHERE n->>'type'='n8n-nodes-base.httpRequest'
          AND (n->'parameters'->>'url' LIKE '%graph.instagram.com/%'
               OR n->'parameters'->>'url' LIKE '%graph.facebook.com/%')
      ) v WHERE version IS NOT NULL)
    ) FROM public.workflow_entity w
    WHERE w.id IN ('LHlqroY2xzvpYAmD','A0EcNxcRvfWnMwKI');
    """
    raw = run(["docker", "exec", "-i", "--env", "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10s",
               "socialmei-postgres", "sh", "-c", 'exec psql -X -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -At', "instagram-read-only", db], input=sql)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def main():
    env = json.loads(run(["docker", "inspect", "--format", "{{json .Config.Env}}", API]))
    result = {"api": api_summary(dict(value.split("=", 1) for value in env)),
              "caddy_publico": inspect_proxy("socialmei-caddy"),
              "gateway": inspect_proxy("socialmei-team-team-gateway-1")}
    try:
        result["workflows"] = workflow_versions()
    except (RuntimeError, ValueError):
        result["workflows"] = "consulta_nao_concluida"
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Inspeção não concluída. Nenhum segredo ou alteração foi enviado.")
