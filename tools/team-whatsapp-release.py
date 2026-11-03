#!/usr/bin/env python3
"""Narrow, reversible API+gateway release for the authenticated WA pilot.

No migrations, image builds, dependency recreation, provider sends, or changes to
the database, Caddy mounts, private overlays other than the active API overlay,
WAHA, n8n, or PostgreSQL. Read-only by default.
"""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path("/home/ubuntu/socialmei-team")
BACKUPS = Path("/home/ubuntu/socialmei-backups")
PRIVATE = Path("/var/lib/socialmei-wa-pilot")
TOOLS = Path(__file__).resolve().parent
SOURCE = TOOLS.parent
API = "socialmei-team-team-api-1"
GATEWAY = "socialmei-team-team-gateway-1"
POSTGRES = "socialmei-team-team-postgres-1"
WAHA = "socialmei-waha"
N8N = "socialmei-n8n"
SERVICES = ("team-api", "team-gateway")
BASE_SHA = "f836e2ae2e91a69b5acd8fb3337f649dcdbc5cff"
ORIGIN = "https://socialmei-ia.54-94-213-7.sslip.io"
FLAGS = {
    "SOCIALMEI_RELEASE_SHA": None,
    "SOCIALMEI_WAHA_INGRESS_MODE": "team-pilot",
    "SOCIALMEI_WAHA_LAB_ENVIRONMENT": "team-pilot",
    "SOCIALMEI_WAHA_REGISTRY_FILE": "/run/socialmei/private/waha-registry.json",
}
BOT_FLAGS = (
    "SOCIALMEI_WHATSAPP_BOT_ENABLED",
    "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED",
    "SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED",
    "SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED",
    "SOCIALMEI_PROVIDER_SENTIMENT_ENABLED",
)
STATIC_FILES = (
    "socialmei-app.html", "scripts/v22-bootstrap.js", "scripts/v22-backend.js",
    "scripts/v22-frame.js", "scripts/entrada.js", "styles/entrada.css",
)


class Blocked(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise Blocked(code)


def run(args, *, cwd=None, input_bytes=None, timeout=90):
    try:
        result = subprocess.run(args, cwd=cwd, input=input_bytes,
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked("comando_indisponivel") from None
    require(result.returncode == 0, "comando_falhou")
    return result.stdout


def docker(*args, timeout=90, input_bytes=None):
    require(Path("/var/run/docker.sock").is_socket(), "docker_local_indisponivel")
    return run(["docker", "--host=unix:///var/run/docker.sock", *args],
               input_bytes=input_bytes, timeout=timeout)


def inspect(name):
    rows = json.loads(docker("inspect", "--type", "container", name))
    require(len(rows) == 1 and rows[0].get("Name") == "/" + name,
            "container_invalido")
    return rows[0]


def compose_context(api):
    labels = api["Config"]["Labels"]
    wd = Path(labels.get("com.docker.compose.project.working_dir", "")).resolve()
    raw = labels.get("com.docker.compose.project.config_files", "")
    require(wd == ROOT.resolve() and (wd / ".env.team").is_file(),
            "checkout_compose_divergente")
    files = [Path(x.strip()) for x in raw.split(",") if x.strip()]
    files = [x if x.is_absolute() else wd / x for x in files]
    require(files and all(p.is_file() for p in files), "compose_ausente")
    overrides = [p.resolve() for p in files if p.name == "team-api.override.private.json"]
    require(overrides and overrides[-1].is_file(), "override_privado_ausente")
    command = ["docker", "--host=unix:///var/run/docker.sock", "compose",
               "-p", "socialmei-team", "--env-file", str(wd / ".env.team")]
    for path in files:
        command += ["-f", str(path)]
    return wd, files, overrides[-1], command


def render(command, wd):
    model = json.loads(run(command + ["config", "--format", "json"], cwd=wd))
    for service in model.get("services", {}).values():
        for key, value in (service.get("environment") or {}).items():
            if isinstance(value, str):
                service["environment"][key] = value.replace("$$", "$")
    return model


def image_tags(sha):
    return {service: f"socialmei-v33/{service}:{sha}" for service in SERVICES}


def baseline_image_identity(api, gateway):
    for service, container in (("team-api", api), ("team-gateway", gateway)):
        tag = image_tags(BASE_SHA)[service]
        image = json.loads(docker("image", "inspect", tag))
        require(len(image) == 1 and container["Config"]["Image"] == tag
                and container["Image"] == image[0]["Id"], "tag_rollback_nao_corresponde_ao_runtime")


def shape_matches(model, container, service):
    config = model["services"][service]
    networks = {model["networks"][key]["name"] for key in config.get("networks", {})}
    if networks != set((container.get("NetworkSettings") or {}).get("Networks", {})):
        return False
    expected = {
        (v["type"], v.get("source") if v["type"] == "bind" else v.get("source"),
         v["target"], not v.get("read_only", False))
        for v in config.get("volumes", [])
    }
    actual = {
        (v["Type"], v.get("Source") if v["Type"] == "bind" else v.get("Name"),
         v["Destination"], v["RW"])
        for v in container.get("Mounts", [])
    }
    return (expected == actual and not config.get("ports")
            and not (container.get("HostConfig") or {}).get("PortBindings")
            and security_matches(config, container))


def security_matches(config, container):
    host = container.get("HostConfig") or {}
    return (bool(host.get("Privileged")) == bool(config.get("privileged", False))
            and bool(host.get("ReadonlyRootfs")) == bool(config.get("read_only", False))
            and sorted(host.get("CapDrop") or []) == sorted(config.get("cap_drop") or [])
            and sorted(host.get("CapAdd") or []) == sorted(config.get("cap_add") or [])
            and sorted(host.get("SecurityOpt") or []) == sorted(config.get("security_opt") or []))


def security_invariant(container):
    host = container.get("HostConfig") or {}
    return {"user": container["Config"].get("User"),
            **{key: host.get(key) for key in (
                "Privileged", "ReadonlyRootfs", "CapDrop", "CapAdd", "SecurityOpt", "PidMode",
                "IpcMode", "Devices", "DeviceRequests", "Memory", "MemorySwap", "NanoCpus",
                "CpuShares", "PidsLimit", "RestartPolicy", "LogConfig")}}


def env_map(container):
    return dict(item.split("=", 1) for item in container["Config"].get("Env", [])
                if "=" in item)


def validate_runtime(model, api, gateway, postgres, *, expected_sha=None):
    for service, container in (("team-api", api), ("team-gateway", gateway)):
        require(container["State"].get("Running") is True
                and shape_matches(model, container, service),
                "runtime_shape_divergente")
        expected_env = model["services"][service].get("environment") or {}
        actual_env = env_map(container)
        require(all(actual_env.get(key) == str(value)
                    for key, value in expected_env.items()), "runtime_env_divergente")
    require(api["State"].get("Health", {}).get("Status") == "healthy"
            and postgres["State"].get("Running") is True
            and postgres["State"].get("Health", {}).get("Status") == "healthy",
            "api_ou_postgres_sem_saude")
    require(env_map(api).get("SOCIALMEI_AUTH_ENABLED", "").lower()
            in {"true", "1", "yes", "on"}, "auth_nao_confirmada")
    require(env_map(api).get("SOCIALMEI_SHARED_DATA_ENABLED", "").lower()
            in {"true", "1", "yes", "on"}, "dados_compartilhados_desligados")
    require(all(env_map(api).get(name, "false").strip().lower()
                in {"", "0", "false", "no", "off"} for name in BOT_FLAGS),
            "envio_ou_provedor_ativo")
    require(env_map(api).get("SOCIALMEI_WAHA_INGRESS_MODE") == "team-pilot"
            and env_map(api).get("SOCIALMEI_WAHA_LAB_ENVIRONMENT") == "team-pilot"
            and env_map(api).get("SOCIALMEI_WAHA_REGISTRY_FILE")
            == "/run/socialmei/private/waha-registry.json", "modo_piloto_nao_confirmado")
    if expected_sha:
        require(api["Config"]["Image"] == image_tags(expected_sha)["team-api"],
                "tag_api_instalada_divergente")
        require(env_map(api).get("SOCIALMEI_WAHA_INGRESS_MODE") == "team-pilot"
                and env_map(api).get("SOCIALMEI_WAHA_LAB_ENVIRONMENT") == "team-pilot"
                and env_map(api).get("SOCIALMEI_WAHA_REGISTRY_FILE")
                == "/run/socialmei/private/waha-registry.json",
                "modo_piloto_nao_confirmado")
    else:
        require(api["Config"]["Image"] == image_tags(BASE_SHA)["team-api"]
                and gateway["Config"]["Image"] == image_tags(BASE_SHA)["team-gateway"],
                "baseline_imagem_divergente")
        require(env_map(api).get("SOCIALMEI_WAHA_INGRESS_MODE", "disabled").lower()
                in {"team-pilot"}, "ingresso_piloto_baseline_divergente")
    require(any(n == "socialmei_team_egress"
                for n in api["NetworkSettings"]["Networks"]), "egress_ausente")
    ro = {m["Destination"] for m in gateway.get("Mounts", [])
          if m.get("Type") == "bind" and m.get("RW") is False}
    require({"/etc/caddy/Caddyfile", "/etc/caddy/private", "/srv/frontend/config.js"}
            <= ro, "overlays_caddy_privados_ausentes")
    require(any(m.get("Destination") == "/run/socialmei/private"
                and m.get("Type") == "bind" and m.get("RW") is False
                for m in api.get("Mounts", [])), "registry_nao_montado_readonly")


def validate_source(sha):
    require(SOURCE.name == "source" and SOURCE.parent.parent == BACKUPS,
            "fonte_fora_do_stage")
    require(run(["git", "-C", str(SOURCE), "rev-parse", "HEAD"]).decode().strip() == sha,
            "fonte_sha_divergente")
    require(not run(["git", "-C", str(SOURCE), "status", "--porcelain=v1", "--untracked-files=all"]).strip(),
            "fonte_stage_modificada")


def validate_migrations_unchanged():
    expected = sorted(path.name for path in (SOURCE / "database/migrations").glob("*.sql"))
    require(len(expected) == 33, "fonte_nao_contem_33_migrations")
    sql = ("BEGIN TRANSACTION READ ONLY;\n"
           "SELECT COALESCE(json_agg(version ORDER BY version),'[]'::json)::text "
           "FROM socialmei.schema_migrations;\nROLLBACK;\n").encode()
    output = docker("exec", "-i", POSTGRES, "sh", "-c",
                    'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                    "-v ON_ERROR_STOP=1 -At", input_bytes=sql)
    rows = [line.strip() for line in output.decode().splitlines()
            if line.strip().startswith("[")]
    require(len(rows) == 1 and json.loads(rows[0]) == expected,
            "ledger_migrations_nao_e_33")


def verify_backup(backup, db_backup):
    require(backup.parent == PRIVATE and backup.is_dir() and not backup.is_symlink()
            and backup.stat().st_uid == 0 and stat.S_IMODE(backup.stat().st_mode) == 0o700,
            "backup_privado_invalido")
    sums = json.loads((backup / "SHA256SUMS.json").read_text())
    require(len(sums) >= 9, "backup_incompleto")
    for name, value in sums.items():
        require(Path(name).name == name, "nome_de_backup_invalido")
        path = backup / name
        require(path.is_file() and not path.is_symlink()
                and path.stat().st_uid == 0 and stat.S_IMODE(path.stat().st_mode) == 0o600
                and digest_file(path) == value,
                "hash_de_backup_divergente")
    db_receipt = json.loads((db_backup / "concluido.json").read_text())
    require(db_backup.parent == BACKUPS and db_backup.is_dir(), "backup_db_ausente")
    for name, value in db_receipt.get("sha256", {}).items():
        require(digest_file(db_backup / name) == value,
                "backup_db_divergente")
    require({"equipe.dump", "configuracao.tar.gz", "conteudo.txt"}
            <= set(db_receipt.get("sha256", {})), "backup_db_incompleto")
    require(digest_file(backup / "postgres.dump")
            == digest_file(db_backup / "equipe.dump"), "dump_nao_corresponde")
    age = time.time() - (db_backup / "concluido.json").stat().st_mtime
    require(0 <= age <= 900, "backup_db_nao_fresco")
    with tarfile.open(backup / "images-before.tar") as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
        images = {}
        for row in manifest:
            require(isinstance(row, dict) and len(row.get("RepoTags") or []) == 1, "arquivo_rollback_tag_ambigua")
            tag = row["RepoTags"][0]
            service = next((name for name, expected in image_tags(BASE_SHA).items() if expected == tag), None)
            require(service is not None and service not in images, "arquivo_rollback_tag_divergente")
            entry = archive.getmember(row["Config"])
            require(entry.isfile() and entry.size <= 32 * 1024**2, "arquivo_rollback_config_invalida")
            with archive.extractfile(entry) as stream:
                images[service] = {"tag": tag, "image_id": "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()}
    tags = {tag for row in manifest if isinstance(row, dict)
            for tag in row.get("RepoTags", []) or []}
    require(tags == set(image_tags(BASE_SHA).values()), "imagens_de_rollback_divergentes")
    baseline_api = json.loads((backup / "api-runtime.before.json").read_text())
    baseline_gateway = json.loads((backup / "gateway-runtime.before.json").read_text())
    baseline_image_identity(baseline_api, baseline_gateway)
    helper = importer()
    helper.verify_archive_config_digests(backup / "images-before.tar", images, BASE_SHA, "bundle")
    require(all(helper.local_image_status({"images": images}, expected_sha=BASE_SHA).values()), "identidade_rollback_nao_confirmada")
    return sums


def importer():
    importer_path = TOOLS / "team-v33-import-images.py"
    spec = importlib.util.spec_from_file_location("team_pilot_importer", importer_path)
    require(spec and spec.loader, "importador_ausente")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_candidate(importer_path, bundle, sha):
    require(importer_path == TOOLS / "team-v33-import-images.py", "importador_fora_do_commit")
    module = importer()
    receipt = module.read_bundle(bundle, expected_sha=sha)
    status = module.local_image_status(receipt, expected_sha=sha)
    require(all(status.values()), "imagem_candidata_nao_verificada")
    for service, tag in image_tags(sha).items():
        row = json.loads(docker("image", "inspect", tag))[0]
        require(row.get("Config", {}).get("Labels", {}).get(
            "org.opencontainers.image.revision") == sha,
            "label_da_imagem_divergente")


def candidate_model(before, override, original, command, wd, sha):
    service_api = override.setdefault("services", {}).setdefault("team-api", {})
    service_gateway = override.setdefault("services", {}).setdefault("team-gateway", {})
    service_api["image"] = image_tags(sha)["team-api"]
    service_api.setdefault("environment", {}).update({
        key: (sha if key == "SOCIALMEI_RELEASE_SHA" else value)
        for key, value in FLAGS.items()
    })
    service_gateway["image"] = image_tags(sha)["team-gateway"]
    payload = (json.dumps(override, ensure_ascii=False, indent=2) + "\n").encode()
    fd, candidate = tempfile.mkstemp(prefix=".wa-pilot-candidate-", suffix=".json",
                                     dir=original.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
        trial_command = []
        for part in command:
            try:
                same_override = Path(part).resolve() == original
            except OSError:
                same_override = False
            trial_command.append(str(candidate) if same_override else part)
        after = render(trial_command, wd)
        expected = copy.deepcopy(before)
        expected["services"]["team-api"]["image"] = image_tags(sha)["team-api"]
        expected["services"]["team-gateway"]["image"] = image_tags(sha)["team-gateway"]
        for key, value in FLAGS.items():
            expected["services"]["team-api"].setdefault("environment", {})[key] = (
                sha if key == "SOCIALMEI_RELEASE_SHA" else value
            )
        require(after == expected, "compose_candidato_mudou_mais_que_api_gateway_flags")
    finally:
        Path(candidate).unlink(missing_ok=True)
    return payload


def https(path, expected):
    try:
        with urlopen(ORIGIN + path, timeout=12) as response:
            status, body = response.status, response.read()
    except HTTPError as error:
        status, body = error.code, error.read()
    except (URLError, TimeoutError):
        raise Blocked("https_indisponivel") from None
    require(status == expected, "https_status_divergente")
    return body


def digest_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def public_smoke(expected_files=None):
    https("/", 200)
    https("/frontend/entrada.html", 200)
    https("/api/v1/clientes", 401)
    https("/internal/not-found", 404)
    if expected_files is None:
        expected_files = {path: digest_file(SOURCE / "frontend" / path)
                          for path in (*STATIC_FILES, "scripts/v22-whatsapp-bot.js")}
    for path, expected in expected_files.items():
        body = https("/frontend/" + path, 200)
        require(hashlib.sha256(body).hexdigest() == expected, "arquivo_frontend_divergente")


def wait_service(service):
    name = API if service == "team-api" else GATEWAY
    for _ in range(60):
        try:
            obj = inspect(name)
            state = obj.get("State", {})
            if state.get("Running") and (service != "team-api"
                    or state.get("Health", {}).get("Status") == "healthy"):
                if service == "team-gateway":
                    docker("exec", GATEWAY, "wget", "-q", "-T", "2", "-O",
                           "/dev/null", "http://127.0.0.1:80/", timeout=5)
                return obj
        except Blocked:
            pass
        time.sleep(2)
    raise Blocked("servico_nao_saudavel")


def write_atomic(path, payload, old_stat):
    fd, temp = tempfile.mkstemp(prefix=".wa-pilot-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(temp, old_stat.st_uid, old_stat.st_gid)
        os.chmod(temp, stat.S_IMODE(old_stat.st_mode))
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def restore_services(command, wd, attempted):
    failures = []
    for service in attempted:
        require(service in SERVICES, "rollback_servico_fora_do_escopo")
        try:
            run(command + ["up", "-d", "--no-deps", "--no-build", "--pull",
                           "never", "--force-recreate", service], cwd=wd, timeout=180)
            wait_service(service)
        except Exception:
            failures.append(service)
    require(not failures, "rollback_incompleto_verificar_api_e_gateway")


def operate(sha, bundle, backup, db_backup, *, apply=False):
    require(re.fullmatch(r"[0-9a-f]{40}", sha), "sha_invalido")
    require(os.geteuid() == 0, "root_necessario")
    validate_source(sha)
    require(backup.resolve().parent == PRIVATE and db_backup.resolve().parent == BACKUPS,
            "backup_fora_do_escopo")
    require(bundle.resolve().parent == BACKUPS, "pacote_fora_do_escopo")
    lock = open("/run/lock/socialmei-wa-pilot-release.lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise Blocked("outro_cutover_em_andamento") from None
    verify_backup(backup.resolve(), db_backup.resolve())
    verify_candidate(TOOLS / "team-v33-import-images.py", bundle.resolve(), sha)
    api, gateway, postgres = inspect(API), inspect(GATEWAY), inspect(POSTGRES)
    waha, n8n = inspect(WAHA), inspect(N8N)
    require(waha["State"].get("Running") and n8n["State"].get("Running"),
            "waha_ou_n8n_inativo")
    validate_migrations_unchanged()
    waha_id, n8n_id, pg_id = waha["Id"], n8n["Id"], postgres["Id"]
    wd, files, original, command = compose_context(api)
    before_model = render(command, wd)
    validate_runtime(before_model, api, gateway, postgres)
    baseline_image_identity(api, gateway)
    baseline_security = {"team-api": security_invariant(api), "team-gateway": security_invariant(gateway)}
    old_bytes = (backup / "api-override.before-release.json").read_bytes()
    require(original.read_bytes() == old_bytes, "override_diverge_do_backup")
    override = json.loads(old_bytes)
    trial_bytes = candidate_model(before_model, override, original, command, wd, sha)
    require(https("/", 200) != b"", "site_sem_resposta")
    if not apply:
        return {"action": "read_only_preflight_passed", "sha": sha,
                "compose_changes": ["team-api image", "team-gateway image",
                                    "team-api release sha and WhatsApp pilot flags"],
                "migrations_run": False, "containers_changed": False}

    baseline_files = {path: hashlib.sha256(https("/frontend/" + path, 200)).hexdigest()
                      for path in STATIC_FILES}
    stat_before = original.stat()
    require(original.read_bytes() == old_bytes, "override_mudou_antes_do_cutover")
    attempted = []
    replaced = False
    try:
        write_atomic(original, trial_bytes, stat_before)
        replaced = True
        current = render(command, wd)
        expected_api, expected_gateway = inspect(API), inspect(GATEWAY)
        for service in SERVICES:
            attempted.append(service)
            run(command + ["up", "-d", "--no-deps", "--no-build", "--pull",
                           "never", "--force-recreate", service], cwd=wd, timeout=180)
            container = wait_service(service)
            model = render(command, wd)
            if service == "team-api":
                expected_api = container
            else:
                expected_gateway = container
            validate_runtime(model, expected_api, expected_gateway, inspect(POSTGRES),
                             expected_sha=sha)
            require(security_invariant(container) == baseline_security[service], "seguranca_runtime_alterada")
        require(inspect(GATEWAY)["Config"]["Image"] == image_tags(sha)["team-gateway"],
                "tag_gateway_nao_confirmada")
        require(inspect(WAHA)["Id"] == waha_id and inspect(N8N)["Id"] == n8n_id
                and inspect(POSTGRES)["Id"] == pg_id,
                "servico_fora_do_escopo_recriado")
        public_smoke()
        validate_migrations_unchanged()
    except Exception:
        if replaced:
            write_atomic(original, old_bytes, stat_before)
            restore_services(command, wd, attempted)
            rolled = render(command, wd)
            validate_runtime(rolled, inspect(API), inspect(GATEWAY), inspect(POSTGRES))
            require(all(security_invariant(inspect(API if service == "team-api" else GATEWAY))
                        == baseline_security[service] for service in SERVICES), "rollback_seguranca_divergente")
            require(inspect(WAHA)["Id"] == waha_id and inspect(N8N)["Id"] == n8n_id
                    and inspect(POSTGRES)["Id"] == pg_id, "rollback_servico_fora_escopo")
            public_smoke(expected_files=baseline_files)
        raise
    return {"action": "api_gateway_published", "sha": sha,
            "api_healthy": True, "https_static_auth_smoke": True,
            "migrations_run": False, "provider_messages_sent": False,
            "waha_n8n_postgres_recreated": False,
            "rollback_backup": backup.name, "database_backup": db_backup.name}


def fresh_database_backup():
    # The legacy backup chooses its destination from Path.home(). Keep the original operator identity.
    output = run(["sudo", "-u", "ubuntu", "-H", "python3", str(ROOT / "tools/team-maintenance.py"), "backup"],
                 cwd=ROOT, timeout=300).decode()
    matches = set(re.findall(r"/home/ubuntu/socialmei-backups/(team-auto-[0-9]{8}-[0-9]{6}-[a-z0-9]+)", output))
    require(len(matches) == 1, "backup_db_nao_identificado")
    return BACKUPS / matches.pop()


def prepare(sha, bundle):
    require(os.geteuid() == 0, "root_necessario")
    require(re.fullmatch(r"[0-9a-f]{40}", sha), "sha_invalido")
    validate_source(sha)
    require(bundle.resolve().parent == BACKUPS, "pacote_fora_do_escopo")
    verify_candidate(TOOLS / "team-v33-import-images.py", bundle, sha)
    require(PRIVATE.is_dir() and not PRIVATE.is_symlink() and PRIVATE.stat().st_uid == 0
            and stat.S_IMODE(PRIVATE.stat().st_mode) == 0o700, "raiz_privada_insegura")
    lock = open("/run/lock/socialmei-wa-pilot-release.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    api, gateway, postgres = inspect(API), inspect(GATEWAY), inspect(POSTGRES)
    wd, files, override, command = compose_context(api)
    validate_runtime(render(command, wd), api, gateway, postgres)
    baseline_image_identity(api, gateway)
    validate_migrations_unchanged()
    require(shutil.disk_usage(PRIVATE).free >= 1024 ** 3, "espaco_de_backup_insuficiente")
    db_backup = fresh_database_backup()
    receipt = json.loads((db_backup / "concluido.json").read_text())
    require({"equipe.dump", "configuracao.tar.gz", "conteudo.txt"} <= set(receipt.get("sha256", {})), "backup_db_incompleto")
    for name, value in receipt["sha256"].items():
        require(Path(name).name == name and digest_file(db_backup / name) == value, "backup_db_divergente")
    folder = PRIVATE / ("cutover-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    folder.mkdir(mode=0o700)
    def save(name, data):
        fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    def copy_file(source, name):
        fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with source.open("rb") as incoming, os.fdopen(fd, "wb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=1024**2)
            outgoing.flush()
            os.fsync(outgoing.fileno())
    save("api-override.before-release.json", override.read_bytes())
    for src, target in (("equipe.dump", "postgres.dump"), ("configuracao.tar.gz", "configuration.tar.gz"),
                        ("conteudo.txt", "database-toc.txt"), ("concluido.json", "database-backup-receipt.json")):
        copy_file(db_backup / src, target)
    save("registry.before.json", (PRIVATE / "registry/waha-registry.json").read_bytes())
    save("api-runtime.before.json", json.dumps(api).encode())
    save("gateway-runtime.before.json", json.dumps(gateway).encode())
    waha = inspect(WAHA)
    binding = json.loads((PRIVATE / "registry/waha-registry.json").read_text())["bindings"][0]
    key = env_map(waha).get("WAHA_API_KEY") or env_map(waha).get("WAHA_API_KEY_PLAIN")
    ports = (waha["NetworkSettings"].get("Ports") or {}).get("3000/tcp") or []
    require(key and len(ports) == 1 and binding["session"] == "01", "sessao_backup_ambigua")
    req = Request("http://127.0.0.1:" + ports[0]["HostPort"] + "/api/sessions/01", headers={"X-Api-Key": key})
    with urlopen(req, timeout=15) as response:
        session = json.load(response)
    require(session.get("status") == "WORKING" and (session.get("me") or {}).get("id") == binding["account_id"],
            "sessao_backup_divergente")
    save("waha-session.before.json", json.dumps(session).encode())
    save("rollback.public-files.json", json.dumps({path: hashlib.sha256(https("/frontend/" + path, 200)).hexdigest()
                                                 for path in STATIC_FILES}).encode())
    archive = folder / "images-before.tar"
    with archive.open("xb") as stream:
        os.chmod(archive, 0o600)
        result = subprocess.run(["docker", "--host=unix:///var/run/docker.sock", "image", "save",
                                 *image_tags(BASE_SHA).values()], stdout=stream, stderr=subprocess.DEVNULL, timeout=300)
        require(result.returncode == 0, "arquivo_de_imagens_falhou")
        stream.flush()
        os.fsync(stream.fileno())
    sums = {path.name: digest_file(path) for path in folder.iterdir() if path.is_file()}
    save("SHA256SUMS.json", json.dumps(sums, sort_keys=True).encode())
    verify_backup(folder, db_backup)
    return {"action": "fresh_backup_and_rollback_verified", "sha": sha,
            "backup": str(folder), "db_backup": str(db_backup), "files_verified": len(sums),
            "database_restored": False, "containers_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--db-backup", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--inspect", action="store_true")
    modes.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.prepare:
            result = prepare(args.sha, args.bundle)
        else:
            require(args.backup is not None and args.db_backup is not None, "backup_necessario")
            result = operate(args.sha, args.bundle, args.backup, args.db_backup,
                             apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        trace = traceback.extract_tb(exc.__traceback__)
        location = trace[-1] if trace else None
        print(json.dumps({"action": "stopped", "error_code":
                          exc.args[0] if isinstance(exc, Blocked) and exc.args
                          else "verification_failed",
                          "error_type": type(exc).__name__,
                          "error_stage": location.name if location else "unknown",
                          "error_line": location.lineno if location else 0,
                          "migrations_run": False,
                          "provider_messages_sent": False}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
