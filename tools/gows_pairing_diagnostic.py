#!/usr/bin/env python3
"""Read-only, privacy-preserving diagnostics for an isolated WAHA GOWS pilot.

Run on the Docker host with permission to inspect the project containers.
Does not pair, restart, stop, send messages, read a QR or change webhooks.
It intentionally never displays session names, phone numbers, logs or secrets.
"""
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

WEBJS = "socialmei-waha"
GOWS = "socialmei-waha-gows-piloto"
API = "socialmei-team-team-api-1"
WORKER = "socialmei-menu-worker-continuo"
BACKUP_ROOT = Path("/var/lib/socialmei-prisma-cutover/waha-session-backups")

STATES = frozenset({
    "STOPPED", "STARTING", "SCAN_QR_CODE", "PASSKEY_REQUIRED",
    "PASSKEY_CONFIRMATION_REQUIRED", "WORKING", "FAILED",
})
REASONS = frozenset({
    "ClientOutdated", "ConnectFailure", "LoggedOut", "TemporaryBan",
    "StreamReplaced", "UnknownLogout", "ClientPayloadError",
})
SIGNALS = {
    "PASSKEY": r"passkey[_ -]?(?:required|confirmation)|webauthn",
    "CLIENTE_DESATUALIZADO": r"ClientOutdated|client.?outdated",
    "FALHA_CONEXAO": r"ConnectFailure|connection refused|dial tcp|network is unreachable",
    "TIMEOUT": r"timed out|timeout|deadline exceeded|expired",
    "FALHA_PAREAMENTO": r"pairing.{0,30}(?:fail|error)|link.{0,30}(?:fail|error)",
    "SESSAO_SUBSTITUIDA": r"StreamReplaced|stream replaced",
    "SESSAO_DESCONECTADA": r"LoggedOut|logged out",
}


def safe_state(value):
    """Never echo unexpected provider strings or private data."""
    return value if isinstance(value, str) and value in STATES else "DESCONHECIDO"


def safe_reason(value):
    return value if isinstance(value, str) and value in REASONS else "NAO_INFORMADO"


def signals_from_logs(raw):
    """Classify locally; no raw log lines or private tokens leave this function."""
    if not isinstance(raw, str):
        raw = ""
    return {name: bool(re.search(pattern, raw, re.IGNORECASE))
            for name, pattern in SIGNALS.items()}


def cmd(args, *, timeout=25):
    p = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, check=False
    )
    if p.returncode:
        raise RuntimeError("COMANDO_FALHOU")
    # Docker may write container logs to stderr; never print either raw stream.
    if len(args) > 1 and args[0] == "docker" and args[1] == "logs":
        return p.stdout + "\n" + p.stderr
    return p.stdout


def docker(*args, timeout=25):
    # Explicit read-only command allowlist. 'exec' may only run the query below.
    if args[0] not in {"inspect", "logs", "exec"}:
        raise ValueError("OPERACAO_PROIBIDA")
    if args[0] == "exec" and (
        len(args) != 5 or args[1] not in {WEBJS, GOWS}
        or args[2:4] != ("node", "-e")
        or args[4] != SESSION_QUERY
    ):
        raise ValueError("EXEC_INESPERADO")
    return cmd(["docker", *args], timeout=timeout)


def inspect(name):
    result = json.loads(docker("inspect", name))
    if not isinstance(result, list) or len(result) != 1:
        raise ValueError("INSPECAO_INVALIDA")
    return result[0]


def envs(obj):
    return dict(part.split("=", 1) for part in obj["Config"]["Env"] if "=" in part)


# WAHA key stays inside the container. Only status, webhook count and
# allowlisted reason code leave its process; never QR, account ID or name.
SESSION_QUERY = r"""
(async () => {
  const key = process.env.WAHA_API_KEY || process.env.WHATSAPP_API_KEY || "";
  const headers = key ? {"X-Api-Key": key} : {};
  const res = await fetch("http://127.0.0.1:3000/api/sessions?all=true", {
    headers, signal: AbortSignal.timeout(8000)
  });
  if (!res.ok) throw Error("HTTP");
  const list = await res.json();
  if (!Array.isArray(list)) throw Error("FORMATO");
  console.log(JSON.stringify(list.map(s => {
    const data = s.data || s.statusData || {};
    const reason = data.reason || s.reason || {};
    return {
      status: s.status,
      hookCount: Array.isArray(s.config?.webhooks)
        ? s.config.webhooks.length : null,
      reasonEvent: reason.event || null,
      reasonCode: Number.isInteger(reason.Reason) ? reason.Reason : null
    };
  })));
})().catch(() => process.exit(1));
"""


def sessions(container):
    result = json.loads(docker(
        "exec", container, "node", "-e", SESSION_QUERY, timeout=20
    ))
    if not isinstance(result, list) or len(result) > 20:
        raise ValueError("SESSOES_INVALIDAS")
    return result


def inspect_backup():
    return BACKUP_ROOT.is_dir() and any(
        item.is_file() for item in BACKUP_ROOT.glob("webjs-session-*.tar.gz")
    )


def main():
    print("=== DIAGNOSTICO GOWS - SOMENTE LEITURA ===", flush=True)
    try:
        containers = {name: inspect(name) for name in (API, WORKER, WEBJS, GOWS)}
        running = all(item.get("State", {}).get("Running") for item in containers.values())
        api_healthy = (
            containers[API].get("State", {}).get("Health", {}).get("Status") == "healthy"
        )
        api_dual = envs(containers[API]).get(
            "SOCIALMEI_WAHA_WEBHOOK_ENGINE"
        ) == "WEBJS,GOWS"
        worker_webjs = urlparse(
            envs(containers[WORKER]).get("SOCIALMEI_MENU_WAHA_URL", "")
        ).hostname == WEBJS
        gows_engine = envs(containers[GOWS]).get("WHATSAPP_DEFAULT_ENGINE") == "GOWS"

        print("CONTAINERS_ATIVOS =", bool(running))
        print("API_SAUDAVEL =", bool(api_healthy))
        print("API_DUAL =", bool(api_dual))
        print("WORKER_SEGUE_WEBJS =", bool(worker_webjs))
        print("ENGINE_GOWS_CORRETO =", bool(gows_engine))
        print("BACKUP_WEBJS_PRESENTE =", bool(inspect_backup()))

        if not all((running, api_healthy, api_dual, worker_webjs, gows_engine)):
            print("RESULTADO = CONFIGURACAO_DIVERGENTE")
            return 2

        old = sessions(WEBJS)
        new = sessions(GOWS)
        webjs_working = sum(safe_state(s.get("status")) == "WORKING" for s in old)
        print("WEBJS_WORKING =", webjs_working)
        if webjs_working != 1:
            print("RESULTADO = WEBJS_NAO_SAUDAVEL")
            return 2
        print("TOTAL_SESSOES_GOWS =", len(new))
        if len(new) != 1:
            print("RESULTADO = SESSAO_GOWS_AMBIGUA")
            return 2

        state = safe_state(new[0].get("status"))
        hook_count = new[0].get("hookCount")
        print("GOWS_STATUS =", state)
        print("GOWS_WEBHOOKS =", hook_count if type(hook_count) is int and
              0 <= hook_count <= 100 else "DESCONHECIDO")
        print("GOWS_MOTIVO =", safe_reason(new[0].get("reasonEvent")))
        code = new[0].get("reasonCode")
        print("GOWS_CODIGO =", code if type(code) is int and
              0 <= code <= 999 else "NAO_INFORMADO")

        raw_logs = docker("logs", "--since", "30m", "--tail", "500", GOWS)
        for key, present in signals_from_logs(raw_logs).items():
            print("LOG_" + key + " =", present)

        if hook_count != 0:
            print("RESULTADO = WEBHOOK_GOWS_NAO_CONFIRMADO_DESATIVADO")
        elif state in {"PASSKEY_REQUIRED", "PASSKEY_CONFIRMATION_REQUIRED"}:
            print("RESULTADO = VERIFICAR_PASSKEY_OFICIAL")
        elif state == "FAILED":
            print("RESULTADO = FALHA_REQUER_INVESTIGACAO")
        elif state == "SCAN_QR_CODE":
            print("RESULTADO = QR_ATUALIZAVEL_NAO_EXIBIDO")
        else:
            print("RESULTADO = ESTADO_REGISTRADO")

        print("ALTERACOES_NA_PRODUCAO = NENHUMA")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired,
            json.JSONDecodeError):
        print("RESULTADO = CONSULTA_INDISPONIVEL")
        print("ALTERACOES_NA_PRODUCAO = NENHUMA")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
