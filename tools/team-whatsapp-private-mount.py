#!/usr/bin/env python3
"""Mount an isolated registry directory in the current Team API, without replacing the deployment.

This tool edits ONLY the existing Team API private Compose JSON override,
then recreates ONLY the Team API with the same pinned image. It cannot send
messages or change WAHA, n8n, gateway, PostgreSQL, networks, or service flags.
Read-only by default; --apply requires root. Never print config/env values.
"""
import argparse
import copy
import datetime
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time


API = "socialmei-team-team-api-1"
TARGET = "/run/socialmei/private"
OVERRIDE = "team-api.override.private.json"
BACKUPS = Path("/var/lib/socialmei-wa-pilot")


class Blocked(Exception):
    pass


def call(args, *, cwd=None, timeout=60):
    try:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked("Docker/Compose indisponivel: " + type(exc).__name__) from None
    if result.returncode:
        # The underlying error may contain private paths/secrets, so never echo output.
        raise Blocked("Comando falhou: " + " ".join(args[:2]))
    return result.stdout


def get_api():
    rows = json.loads(call(["docker", "inspect", API]))
    if len(rows) != 1 or not rows[0]["State"].get("Running"):
        raise Blocked("API Team nao esta ativa")
    api = rows[0]
    labels = api.get("Config", {}).get("Labels") or {}
    if (labels.get("com.docker.compose.project") != "socialmei-team"
            or labels.get("com.docker.compose.service") != "team-api"):
        raise Blocked("API nao pertence ao Compose Team")
    return api


def invocation(api):
    labels = api["Config"].get("Labels") or {}
    wd = Path(labels.get("com.docker.compose.project.working_dir", "")).resolve()
    raw = labels.get("com.docker.compose.project.config_files", "")
    if not raw or not wd.is_dir() or not (wd / ".env.team").is_file():
        raise Blocked("Origem Compose Team incompleta")
    sources = [Path(item.strip()) for item in raw.split(",") if item.strip()]
    files = [p if p.is_absolute() else wd / p for p in sources]
    if not all(p.is_file() for p in files):
        raise Blocked("Arquivo Compose original nao encontrado")
    choices = {str(p.resolve()) for p in files if p.name == OVERRIDE}
    if len(choices) != 1:
        raise Blocked("Override privado da API ambiguo ou ausente")
    original = Path(next(iter(choices)))
    # Keep the exact original list, including repeated private overlays.
    cmd = ["docker", "compose", "-p", "socialmei-team", "--env-file", str(wd / ".env.team")]
    for p in files:
        cmd += ["-f", str(p)]
    return wd, files, original, cmd


def render(cmd, wd):
    return json.loads(call(cmd + ["config", "--format", "json"], cwd=wd))


def model_mounts(model):
    svc = model["services"]["team-api"]
    volumes = svc.get("volumes") or []
    if not isinstance(volumes, list):
        raise Blocked("Volumes Team API inesperados")
    return volumes


def assert_current(api, model):
    svc = model["services"]["team-api"]
    if api["Config"].get("Image") != svc.get("image"):
        raise Blocked("Imagem da API difere do Compose atual")
    if svc.get("ports") or api.get("HostConfig", {}).get("PortBindings"):
        raise Blocked("API apresenta portas publicadas")
    service_nets = svc.get("networks") or {}
    expected = {model["networks"][name]["name"] for name in service_nets}
    actual = set(api.get("NetworkSettings", {}).get("Networks") or {})
    if expected != actual:
        raise Blocked("Redes da API divergem do Compose atual")
    current_mounts = {
        (m["Type"], m["Source"], m["Destination"], m["RW"])
        for m in (api.get("Mounts") or [])
    }
    target_mounts = {
        (m["type"], m["source"], m["target"], not m.get("read_only", False))
        for m in model_mounts(model)
    }
    if current_mounts != target_mounts:
        raise Blocked("Volumes da API divergem do Compose atual")
    env = dict(pair.split("=", 1) for pair in api["Config"].get("Env", []) if "=" in pair)
    if any(env.get(key) != str(value) for key, value in (svc.get("environment") or {}).items()):
        raise Blocked("Ambiente da API diverge do Compose atual")
    if api.get("State", {}).get("Health", {}).get("Status") != "healthy":
        raise Blocked("API nao esta saudavel")
    if any(m["target"] == TARGET for m in model_mounts(model)):
        raise Blocked("Volume privado ja configurado: nao duplicar")


def check_candidate(before, after, source):
    b = copy.deepcopy(before)
    a = copy.deepcopy(after)
    old_volumes = b["services"]["team-api"].pop("volumes", [])
    new_volumes = a["services"]["team-api"].pop("volumes", [])
    if a != b:
        raise Blocked("A mudanca afetaria outras configuracoes alem do volume API")
    additional = [
        v for v in new_volumes
        if v.get("type") == "bind" and v.get("source") == str(source)
        and v.get("target") == TARGET and v.get("read_only") is True
    ]
    if (len(additional) != 1 or len(new_volumes) != len(old_volumes) + 1
            or [v for v in new_volumes if v is not additional[0]] != old_volumes):
        raise Blocked("A mudanca nao e somente o volume solicitado")


def write_private(path, content, owner=None):
    fd, temporary = tempfile.mkstemp(prefix=".wa-compose-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if owner is not None:
            os.chown(temporary, owner.st_uid, owner.st_gid)
            os.chmod(temporary, stat.S_IMODE(owner.st_mode))
        else:
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def healthy():
    for _ in range(18):
        api = get_api()
        if api.get("State", {}).get("Health", {}).get("Status") == "healthy":
            return True
        time.sleep(5)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Change private Compose file, recreate only Team API; rollback on error")
    args = parser.parse_args()
    api = get_api()
    wd, files, original, command = invocation(api)
    model = render(command, wd)
    assert_current(api, model)
    try:
        override = json.loads(original.read_text())
    except (OSError, ValueError):
        raise Blocked("Override privado nao e JSON valido") from None
    if not isinstance(override, dict):
        raise Blocked("Override privado invalido")
    service = override.get("services", {}).get("team-api")
    if not isinstance(service, dict):
        raise Blocked("Override nao configura a Team API")
    if service.get("volumes"):
        raise Blocked("Override ja define volumes: exige revisao manual")
    source = wd / "deploy/team/private/whatsapp-pilot"
    if not source.parent.is_dir():
        raise Blocked("Pasta privada base nao existe")
    # Never share files used by gateway or expose a secret through existing mounts.
    new = copy.deepcopy(override)
    new["services"]["team-api"]["volumes"] = [{
        "type": "bind", "source": str(source), "target": TARGET,
        "read_only": True, "bind": {"create_host_path": False}
    }]
    encoded = (json.dumps(new, ensure_ascii=False, indent=2) + "\n").encode()
    fd, trial = tempfile.mkstemp(prefix=".wa-candidate-", suffix=".json", dir=str(original.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
        candidate_command = []
        for part in command:
            candidate_command.append(str(trial) if part == str(original) else part)
        candidate = render(candidate_command, wd)
        check_candidate(model, candidate, source)
    finally:
        if os.path.exists(trial):
            os.unlink(trial)
    print("BASELINE_API_SAUDAVEL: SIM")
    print("COMPOSE_ATUAL_COMPATIVEL: SIM")
    print("ALTERACAO_EXCLUSIVA: VOLUME_PRIVADO_TEAM_API")
    print("IMAGEM_REDES_FLAGS_OUTROS_SERVICOS: PRESERVADOS")
    if not args.apply:
        print("MODO: SOMENTE_LEITURA")
        return
    if os.geteuid() != 0:
        raise Blocked("Aplicacao exige sudo para manter segredo HMAC root-owned")
    if source.exists():
        if (not source.is_dir() or source.is_symlink()
                or source.stat().st_uid != 0
                or stat.S_IMODE(source.stat().st_mode) != 0o700):
            raise Blocked("Pasta dedicada ja existe com propriedade/permissoes invalidas")
    else:
        source.mkdir(mode=0o700)
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    if BACKUPS.stat().st_uid != 0 or stat.S_IMODE(BACKUPS.stat().st_mode) != 0o700:
        raise Blocked("Diretorio de backup privado inseguro")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = BACKUPS / ("api-override-" + stamp + ".json")
    if backup.exists():
        raise Blocked("Backup ja existe")
    previous = original.read_bytes()
    backup.touch(mode=0o600, exist_ok=False)
    os.chmod(backup, 0o600)
    backup.write_bytes(previous)
    state = original.stat()
    # Recheck runtime immediately before applying to avoid stale candidate.
    assert_current(get_api(), render(command, wd))
    replaced = False
    try:
        write_private(original, encoded, state)
        replaced = True
        call(command + ["up", "-d", "--no-deps", "--no-build", "--pull", "never",
                        "team-api"], cwd=wd, timeout=180)
        if not healthy():
            raise Blocked("API nao ficou saudavel apos ajuste do volume")
        live = get_api()
        m = [x for x in (live.get("Mounts") or []) if x.get("Destination") == TARGET]
        if len(m) != 1 or not m[0].get("RW") is False or m[0].get("Source") != str(source):
            raise Blocked("Volume novo nao confirmado no runtime")
    except Exception:
        if replaced:
            try:
                write_private(original, previous, state)
                call(command + ["up", "-d", "--no-deps", "--no-build", "--pull",
                                "never", "team-api"], cwd=wd, timeout=180)
                print("ROLLBACK_COMPOSE: APLICADO")
            except Exception:
                print("ROLLBACK_COMPOSE: FALHOU; consultar backup root-owned em /var/lib/socialmei-wa-pilot")
        raise
    print("VOLUME_PRIVADO_API: MONTADO_SOMENTE_LEITURA")
    print("SAUDE_API: HEALTHY")
    print("SERVICOS_WAHA_N8N_POSTGRES_GATEWAY: NAO_RECRIADOS")
    print("BOT_WEBHOOK_FLAGS_ENVIO: INALTERADOS")
    print("PROXIMO_PASSO: provisionar canal da equipe usando o script existente")


if __name__ == "__main__":
    try:
        main()
    except Blocked as exc:
        print("BLOQUEADO:", str(exc), file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print("BLOQUEADO: erro inesperado (" + type(exc).__name__ + ")",
              file=sys.stderr)
        sys.exit(2)
