#!/usr/bin/env python3
"""Guarded pilot channel provisioning for the EXISTING WAHA session.

Read-only by default. --prepare-channel writes only a CRM channel and a private
HMAC registry (no Docker/network/webhook/flag/n8n change and no messages sent).
Run on the Ubuntu host, never in the WAHA or API container.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


API = "socialmei-team-team-api-1"
WAHA = "socialmei-waha"
N8N = "socialmei-n8n"
ALIAS = "socialmei-equipe-piloto"


class Blocked(Exception):
    pass


def docker(*args, data=None, timeout=40):
    try:
        p = subprocess.run(["docker", *args], input=data, capture_output=True,
                           text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked("Docker inacessivel: " + type(exc).__name__) from None
    if p.returncode:
        # Do not print stderr: Docker/backend errors may contain secrets.
        raise Blocked("Comando Docker falhou: " + " ".join(args[:2]))
    return p.stdout


def inspect(name):
    value = json.loads(docker("inspect", name))
    if len(value) != 1 or not value[0].get("State", {}).get("Running"):
        raise Blocked("Container ausente/parado: " + name)
    return value[0]


def container_env(container):
    return dict(item.split("=", 1) for item in container["Config"].get("Env", [])
                if "=" in item)


def endpoint(container):
    ports = (container["NetworkSettings"].get("Ports") or {}).get("3000/tcp") or []
    if ports:
        return "http://127.0.0.1:" + str(ports[0]["HostPort"])
    networks = container["NetworkSettings"].get("Networks") or {}
    network = networks.get("socialmei_default")
    if not network:
        network = next(iter(networks.values()), {})
    address = network.get("IPAddress")
    if not address:
        raise Blocked("WAHA sem endereco local acessivel")
    return "http://" + address + ":3000"


def read_url(url, api_key):
    req = Request(url, headers={"X-Api-Key": api_key})
    try:
        with urlopen(req, timeout=10) as result:
            return json.load(result)
    except Exception as exc:
        raise Blocked("Consulta local WAHA falhou: " + type(exc).__name__) from None


def account_id(value):
    if isinstance(value, dict):
        value = value.get("id") or value.get("_serialized")
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,40}@c\.us", value):
        return value
    return None


def session_info(waha, suffix):
    env = container_env(waha)
    key = env.get("WAHA_API_KEY") or env.get("WAHA_API_KEY_PLAIN")
    if not key:
        raise Blocked("Chave local da API WAHA nao encontrada")
    base = endpoint(waha)
    sessions = read_url(base + "/api/sessions?all=true", key)
    if not isinstance(sessions, list):
        raise Blocked("Formato de sessoes WAHA inesperado")
    working = [s for s in sessions if isinstance(s, dict) and
               str(s.get("status", "")).upper() == "WORKING"]
    if len(working) != 1:
        raise Blocked("E necessario exatamente uma sessao WAHA WORKING")
    s = working[0]
    name = s.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[!-~]{1,160}", name):
        raise Blocked("Nome de sessao WAHA invalido")
    config = s.get("config") or {}
    engine = str(config.get("engine") or env.get("WHATSAPP_DEFAULT_ENGINE") or "WEBJS").upper()
    if engine != "WEBJS":
        raise Blocked("Engine nao homologada para este piloto: " + engine)
    identity = account_id(s.get("me"))
    if not identity:
        identity = account_id(read_url(base + "/api/sessions/" + quote(name, safe="") + "/me", key))
    if not identity or not identity.split("@", 1)[0].endswith(suffix):
        raise Blocked("Numero WAHA nao confere com sufixo autorizado")
    hooks = [h for h in config.get("webhooks", []) if isinstance(h, dict)]
    active = [h for h in hooks
              if urlsplit(str(h.get("url", ""))).path.startswith("/webhook-test/")
              and "message" in (h.get("events") or [])]
    if len(active) != 1:
        raise Blocked("Esperado um webhook de teste WAHA com evento message")
    secret = (active[0].get("hmac") or {}).get("key")
    if not isinstance(secret, str) or not 32 <= len(secret.encode()) <= 4096:
        raise Blocked("Segredo HMAC da sessao nao satisfaz o contrato do receptor")
    return {"name": name, "account": identity, "hmac": secret,
            "hook_test": True, "engine": engine}


DB_PY = """
import json, sys
from database import connect
from psycopg.rows import dict_row
arg = json.load(sys.stdin)
with connect() as conn:
    conn.row_factory = dict_row
    conn.execute("SET LOCAL lock_timeout='3s'")
    conn.execute("SET LOCAL statement_timeout='10s'")
    if arg['operation'] == 'inspect':
        conn.execute("SET TRANSACTION READ ONLY")
        w = conn.execute("SELECT id FROM socialmei.workspaces WHERE id=%s",
                         (arg['workspace_id'],)).fetchone()
        total = conn.execute("SELECT COUNT(*) AS n FROM socialmei.crm_canais WHERE provedor='waha'").fetchone()['n']
        members = conn.execute("SELECT COUNT(*) AS n FROM socialmei.workspace_members "
                               "WHERE workspace_id=%s AND role IN ('owner','admin')",
                               (arg['workspace_id'],)).fetchone()['n']
        out = dict(workspace_exists=bool(w), channel_count=total, manager_count=members)
    elif arg['operation'] == 'reserve':
        if not conn.execute("SELECT id FROM socialmei.workspaces WHERE id=%s FOR SHARE",
                            (arg['workspace_id'],)).fetchone():
            raise ValueError('workspace_missing')
        if conn.execute("SELECT COUNT(*) AS n FROM socialmei.crm_canais WHERE provedor='waha'").fetchone()['n']:
            raise ValueError('waha_channel_already_registered')
        row = conn.execute(
            "INSERT INTO socialmei.crm_canais"
            "(workspace_id,instancia,sessao,nome,identificador_conta,ativo,ingress_provisioned,envio_habilitado)"
            " VALUES(%s,%s,%s,%s,%s,FALSE,FALSE,FALSE) RETURNING id,versao",
            (arg['workspace_id'],arg['instance'],arg['session'],'WhatsApp piloto',
             arg['account'])).fetchone()
        out = dict(channel_id=row['id'], revision=row['versao'])
    elif arg['operation'] == 'finalize':
        row = conn.execute(
            "UPDATE socialmei.crm_canais SET ativo=TRUE,ingress_provisioned=TRUE,"
            "atualizado_em=NOW() WHERE id=%s AND workspace_id=%s AND instancia=%s "
            "AND sessao=%s AND identificador_conta=%s AND versao=%s AND NOT ativo "
            "AND NOT ingress_provisioned AND NOT envio_habilitado RETURNING id",
            (arg['channel_id'],arg['workspace_id'],arg['instance'],arg['session'],
             arg['account'],arg['revision'])).fetchone()
        if not row:
            raise ValueError('finalization_refused')
        out = dict(finalized=True)
    else:
        raise ValueError('invalid_operation')
    print(json.dumps(out))
"""


def database(operation, **fields):
    data = json.dumps({"operation": operation, **fields})
    raw = docker("exec", "-i", API, "python", "-c", DB_PY, data=data)
    try:
        return json.loads(raw)
    except ValueError:
        raise Blocked("API retornou formato inesperado") from None


def private_dir(api):
    mounts = [m for m in api.get("Mounts", [])
              if m.get("Destination") == "/run/socialmei/private"
              and m.get("Type") == "bind"]
    if len(mounts) != 1:
        raise Blocked("Mount privado da API nao encontrado")
    path = Path(mounts[0]["Source"])
    if not path.is_dir() or path.is_symlink():
        raise Blocked("Diretorio privado ausente/invalido")
    if os.stat(path).st_mode & 0o077:
        raise Blocked("Diretorio privado deve ser inacessivel a grupo/outros")
    return path


def registry_file(path, binding):
    file = path / "waha-registry.json"
    if file.exists() or file.is_symlink():
        raise Blocked("Registro privado ja existe; nao sera sobrescrito")
    payload = {"version": 1, "bindings": [binding]}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(data) > 65536:
        raise Blocked("Registro privado excede tamanho permitido")
    fd = os.open(str(file), os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            os.fchmod(fh.fileno(), 0o600)
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        try:
            file.unlink()
        finally:
            raise
    return file


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace-id", type=int, default=1)
    p.add_argument("--number-suffix", default="5976")
    p.add_argument("--prepare-channel", action="store_true",
                   help="Write database channel and HMAC registry; does NOT activate the bot")
    p.add_argument("--confirm", default="", help="For --prepare-channel use TEAM-1")
    a = p.parse_args()
    if a.workspace_id != 1:
        raise Blocked("Piloto limitado ao workspace da equipe (ID 1)")
    if not re.fullmatch(r"[0-9]{4}", a.number_suffix):
        raise Blocked("Informe apenas os quatro ultimos digitos")
    wa = inspect(WAHA)
    api = inspect(API)
    n8n = inspect(N8N)
    session = session_info(wa, a.number_suffix)
    db = database("inspect", workspace_id=a.workspace_id)
    private = private_dir(api)
    api_networks = set(api["NetworkSettings"].get("Networks", {}))
    n8n_networks = set(n8n["NetworkSettings"].get("Networks", {}))
    wa_networks = set(wa["NetworkSettings"].get("Networks", {}))
    shared_api_n8n = bool(api_networks & n8n_networks)
    shared_api_wa = bool(api_networks & wa_networks)
    print("WORKSPACE_ID:", a.workspace_id)
    print("WORKSPACE_EXISTE:", db["workspace_exists"])
    print("GESTORES_CADASTRADOS:", db["manager_count"])
    print("CANAIS_WAHA_EXISTENTES:", db["channel_count"])
    print("WAHA_WORKING_E_NUMERO_VALIDADO: SIM")
    print("ENGINE_WEBJS: SIM")
    print("HMAC_PRESENTE: SIM")
    print("REGISTRY_EXISTENTE:", (private / "waha-registry.json").exists())
    print("REDE_API_N8N:", "CONECTADA" if shared_api_n8n else "PENDENTE")
    print("REDE_API_WAHA:", "CONECTADA" if shared_api_wa else "PENDENTE")
    print("WEBHOOK_ATUAL: TESTE_N8N")
    if not a.prepare_channel:
        print("MODO: LEITURA; NADA FOI ALTERADO")
        return
    if a.confirm != "TEAM-1":
        raise Blocked("--prepare-channel exige --confirm TEAM-1")
    if not db["workspace_exists"] or db["channel_count"]:
        raise Blocked("Workspace inexistente ou canal WAHA ja cadastrado")
    if (private / "waha-registry.json").exists():
        raise Blocked("Registry ja existe; revisao manual necessaria")
    # An inert row is reserved first: it cannot receive or send anything.
    reserved = database("reserve", workspace_id=a.workspace_id, instance=ALIAS,
                        session=session["name"], account=session["account"])
    binding = dict(instance=ALIAS, session=session["name"],
                   account_id=session["account"], workspace_id=a.workspace_id,
                   channel_id=reserved["channel_id"], hmac_key=session["hmac"],
                   revision=reserved["revision"])
    try:
        registry_file(private, binding)
    except Exception:
        # Keep the DB row inactive for human repair, rather than a risky rollback.
        raise Blocked("Canal reservado INATIVO; falhou registro privado. Nao repetir sem revisar.") from None
    try:
        database("finalize", workspace_id=a.workspace_id,
                 channel_id=reserved["channel_id"], instance=ALIAS,
                 session=session["name"], account=session["account"],
                 revision=reserved["revision"])
    except Exception:
        raise Blocked("Registry criado, canal pode estar INATIVO. Verificar antes de repetir.") from None
    print("CANAL_PILOTO_ID:", reserved["channel_id"])
    print("CANAL_REGISTRADO: SIM")
    print("REGISTRY_PRIVADO_CRIADO: SIM")
    print("FLAGS_DA_API_MODIFICADAS: NAO")
    print("WORKFLOWS_WEBHOOKS_REDES_MODIFICADOS: NAO")
    print("MENSAGENS_ENVIADAS: 0")
    print("PROXIMA_FASE: configurar ponte privada, ingresso HMAC e remetente unico")


if __name__ == "__main__":
    try:
        main()
    except Blocked as exc:
        print("BLOQUEADO:", str(exc), file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        # No traceback or credentials in public operator logs.
        print("BLOQUEADO: erro inesperado (" + type(exc).__name__ + ")",
              file=sys.stderr)
        sys.exit(2)
