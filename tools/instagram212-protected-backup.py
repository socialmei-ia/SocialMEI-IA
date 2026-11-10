#!/usr/bin/env python3
"""Instagram #212: audited pre-cutover backup and isolated PostgreSQL restore.

Explicit --create-backup creates root-private artifacts and an ephemeral,
network-isolated restore container; it NEVER deploys API/gateway, changes any
running production container, imports n8n, migrates, sends Meta/WA messages,
or reads message bodies into the printed report.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import time
import uuid

ROOT = Path("/home/ubuntu/socialmei-team")
DEST = Path("/var/lib/socialmei-ig212-backups")
ENV = ROOT / ".env.team"
BASE = "a4720f8b7ea98a67cb40b7b3208acdd7e8bcd510"
CANDIDATE = "345a074310673640084c7634e3da75dd72491813"
API_ID = "sha256:cd88dcbbb9f3d4a6d998eccd18b664d34507989bb47fe1f17602c1faecf4d5a2"
GATEWAY_ID = "sha256:78691bf1c19d0dcd7416986cc3f36adc6f07614f27a49f24b6659c6854441d50"
TARGETS = {
    "api": ("socialmei-team-team-api-1", "team-api", API_ID),
    "gateway": ("socialmei-team-team-gateway-1", "team-gateway", GATEWAY_ID),
}
PROTECTED = (
    "socialmei-team-team-postgres-1",
    "socialmei-waha",
    "socialmei-menu-worker-continuo",
    "socialmei-waha-gows-piloto",
    "socialmei-n8n",
)
MIN_DISK = 3 * 1024**3


class GateError(Exception):
    pass


def require(ok, code):
    if not ok:
        raise GateError(code)


def call(args, *, timeout=40, stdout=None, stdin=None):
    try:
        result = subprocess.run(
            args, stdout=stdout or subprocess.PIPE,
            stderr=subprocess.PIPE, stdin=stdin, timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise GateError("command_unavailable") from None
    require(result.returncode == 0, "command_failed")
    return result.stdout if stdout is None else b""


def inspect(name, kind="container"):
    items = json.loads(call(["docker", "inspect", "--type", kind, name], timeout=20))
    require(len(items) == 1, "docker_inspection_unavailable")
    return items[0]


def fingerprint(obj):
    state = obj.get("State") or {}
    return {
        "container_id": obj.get("Id"),
        "image_id": obj.get("Image"),
        "running": state.get("Running") is True,
        "started": state.get("StartedAt"),
        "restart_count": obj.get("RestartCount"),
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular(path, code):
    require(path.is_file() and not path.is_symlink(), code)
    return path


def safe_dir(path, *, create=False):
    require(not path.is_symlink(), "directory_symlink")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(path.is_dir(), "directory_missing")
    require(path.stat().st_uid == 0, "directory_owner")
    require(stat.S_IMODE(path.stat().st_mode) == 0o700, "directory_mode")
    return path


def files_for(obj):
    labels = obj.get("Config", {}).get("Labels") or {}
    require(labels.get("com.docker.compose.project") == "socialmei-team", "compose_project_mismatch")
    wd = Path(labels.get("com.docker.compose.project.working_dir") or "").resolve()
    require(wd == ROOT, "compose_directory_mismatch")
    paths = [
        Path(p) for p in (labels.get("com.docker.compose.project.config_files") or "").split(",")
        if p
    ]
    require(paths and all(p.is_absolute() and p == p.resolve()
                          and p.is_file() and not p.is_symlink() for p in paths),
            "compose_files_mismatch")
    return paths


def compose_model(files):
    args = ["docker", "compose", "-p", "socialmei-team", "--env-file", str(ENV)]
    for path in files:
        args.extend(("-f", str(path)))
    obj = json.loads(call(args + ["config", "--format", "json"], timeout=60))
    return obj


def prepared():
    require(os.geteuid() == 0, "root_required")
    regular(ENV, "private_env_missing")
    require(ROOT.is_dir() and ROOT.resolve() == ROOT, "root_directory_mismatch")
    require(shutil.disk_usage(DEST.parent).free >= MIN_DISK, "insufficient_disk_space")
    names = [x[0] for x in TARGETS.values()] + list(PROTECTED)
    before = {name: inspect(name) for name in names}
    require(all(value.get("State", {}).get("Running") for value in before.values()),
            "protected_container_stopped")
    require(before[TARGETS["api"][0]]["State"].get("Health", {}).get("Status") == "healthy",
            "api_unhealthy")
    config_paths = []
    for _key, (name, service, expected_id) in TARGETS.items():
        current = before[name]
        require(current.get("Image") == expected_id, "baseline_image_mismatch")
        require((current.get("Config", {}).get("Labels") or {}).get(
            "org.opencontainers.image.revision") == BASE, "baseline_revision_mismatch")
        paths = files_for(current)
        config_paths.extend(paths)
        model = compose_model(paths)["services"][service]
        require(model.get("image") == current["Config"].get("Image"),
                "compose_image_mismatch")
        real = dict(x.split("=", 1) for x in current["Config"]["Env"] if "=" in x)
        require(all(real.get(k) == ("" if v is None else str(v))
                    for k, v in (model.get("environment") or {}).items()),
                "compose_environment_mismatch")
    api_files = files_for(before[TARGETS["api"][0]])
    gw_files = files_for(before[TARGETS["gateway"][0]])
    require(len(api_files) == 16 and len(gw_files) == 12,
            "compose_layer_count_changed")

    # The two pinned images must already be staged; never pull, build, or load.
    for service in ("team-api", "team-gateway"):
        image = inspect(f"socialmei-v33/{service}:{CANDIDATE}", kind="image")
        require((image.get("Config", {}).get("Labels") or {}).get(
            "org.opencontainers.image.revision") == CANDIDATE,
            "candidate_image_unavailable")
    return before, list(dict.fromkeys(config_paths))


def save_config(path, paths, before):
    # Private archive: root-only; includes .env.team and all effective Compose files
    # plus bind mounts. Do not print archive metadata/paths outside private folder.
    names = [ENV, *paths]
    for key, (container, _, _) in TARGETS.items():
        for mount in before[container].get("Mounts", []):
            require(mount.get("Type") == "bind" and mount.get("RW") is False,
                    "protected_mount_unexpected")
            names.append(Path(mount["Source"]))
    names = list(dict.fromkeys(names))
    for root in names:
        require(root.is_absolute() and not root.is_symlink()
                and (root.is_file() or root.is_dir()), "private_path_invalid")
    manifest = {}
    count = 0
    total_bytes = 0
    with tarfile.open(path, "w") as archive:
        for root in names:
            key = hashlib.sha256(str(root).encode()).hexdigest()
            manifest[key] = str(root)
            members = [root, *sorted(root.rglob("*"))] if root.is_dir() else [root]
            for member in members:
                require(not member.is_symlink() and (member.is_dir() or member.is_file()),
                        "private_file_type_invalid")
                count += 1
                require(count <= 20000, "private_file_count_excess")
                relative = "." if member == root else str(member.relative_to(root))
                arcname = "config/" + key + "/" + relative
                if member.is_file():
                    total_bytes += member.stat().st_size
                    require(total_bytes <= 2 * 1024**3, "private_size_excess")
                archive.add(member, arcname=arcname, recursive=False)
        data = json.dumps(manifest, sort_keys=True).encode()
        import io
        info = tarfile.TarInfo("config/path-map.private.json")
        info.mode = 0o600
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return count


def backup():
    before, paths = prepared()
    safe_dir(DEST, create=True)
    folder = DEST / ("ig212-" + uuid.uuid4().hex)
    safe_dir(folder, create=True)
    result = {"resultado": "BLOQUEADO", "producao_alterada": False}
    restore_name = "socialmei-ig212-restore-" + uuid.uuid4().hex[:16]
    started_restore = False
    restore_data = folder / "restore-data"
    try:
        # Do not expose contents of inspect, env or Compose in stdout.
        private = folder / "baseline-inspect.json"
        private.write_text(json.dumps(before, sort_keys=True))
        os.chmod(private, 0o600)

        configs = folder / "private-config.tar"
        count = save_config(configs, paths, before)

        # Save the *currently running* application images to permit rollback.
        old_images = folder / "images-before.tar"
        tags = [before[v[0]]["Config"]["Image"] for v in TARGETS.values()]
        require(len(tags) == 2 and all(isinstance(tag, str) and tag for tag in tags),
                "baseline_image_tag_missing")
        call(["docker", "image", "save", "-o", str(old_images), *tags], timeout=600)
        with tarfile.open(old_images, "r") as archive:
            require(len(archive.getmembers()) > 0, "image_archive_empty")

        dump = folder / "postgres.dump"
        with dump.open("xb") as output:
            os.chmod(dump, 0o600)
            call([
                "docker", "exec", "socialmei-team-team-postgres-1",
                "sh", "-c",
                'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges'
            ], stdout=output, timeout=600)
        require(dump.stat().st_size > 1024, "postgres_dump_empty")

        # Restore to a fresh container with no network, published ports or app access.
        pg_image = before["socialmei-team-team-postgres-1"]["Image"]
        restore_data.mkdir(mode=0o700)
        os.chmod(restore_data, 0o700)
        call([
            "docker", "run", "--detach", "--pull", "never",
            "--name", restore_name,
            "--label", "socialmei.ig212.restore=" + restore_name,
            "--network", "none", "--restart", "no", "--pids-limit", "256",
            "--memory", "768m", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
            "-v", str(restore_data) + ":/var/lib/postgresql/data",
            pg_image,
        ], timeout=60)
        started_restore = True
        for _ in range(90):
            ping = subprocess.run(
                ["docker", "exec", restore_name, "pg_isready", "-U", "postgres"],
                capture_output=True, timeout=5
            )
            if ping.returncode == 0:
                break
            time.sleep(1)
        else:
            raise GateError("isolated_postgres_not_ready")

        with dump.open("rb") as inp:
            call([
                "docker", "exec", "-i", restore_name,
                "pg_restore", "-U", "postgres", "-d", "postgres",
                "--no-owner", "--no-privileges", "--exit-on-error"
            ], stdin=inp, timeout=600)
        sql = ("SELECT (SELECT count(*) FROM socialmei.schema_migrations),"
               " (SELECT count(*) FROM pg_tables WHERE schemaname='socialmei');")
        line = call([
            "docker", "exec", restore_name,
            "psql", "-U", "postgres", "-d", "postgres", "-At", "-c", sql
        ], timeout=30).decode().strip()
        counts = [int(x) for x in line.split("|")]
        require(len(counts) == 2 and counts[0] == 38 and counts[1] == 74,
                "isolated_restore_schema_mismatch")

        # Ensure no production container was recreated during backup/restore.
        after = {name: inspect(name) for name in before}
        require(all(fingerprint(after[name]) == fingerprint(before[name])
                    for name in before), "production_state_changed")

        hashes = {name: sha256_file(folder / name)
                  for name in ("postgres.dump", "images-before.tar",
                               "private-config.tar", "baseline-inspect.json")}
        receipt = {
            "profile": "038", "candidate": CANDIDATE, "baseline": BASE,
            "restore_verified": True, "restore_network": "none",
            "restore_schema_migrations": counts[0], "restore_tables": counts[1],
            "compose_api_layers": 16, "compose_gateway_layers": 12,
            "private_entries": count, "hashes": hashes,
            "protected_runtime_unchanged": True,
        }
        receipt_file = folder / "receipt.private.json"
        receipt_file.write_text(json.dumps(receipt, sort_keys=True, indent=2))
        os.chmod(receipt_file, 0o600)
        result = {
            "resultado": "BACKUP_038_RESTAURADO_EM_ISOLAMENTO",
            "pasta_privada": str(folder),
            "backup_postgres_sha256": hashes["postgres.dump"],
            "backup_imagens_sha256": hashes["images-before.tar"],
            "restauracao_isolada": True, "migrations": counts[0],
            "tabelas": counts[1], "containers_anteriores_preservados": True,
            "producao_alterada": False,
        }
    finally:
        if started_restore:
            # Only remove our own labelled test container; never match by prefix.
            try:
                obj = inspect(restore_name)
                if (obj.get("Config", {}).get("Labels") or {}).get(
                    "socialmei.ig212.restore") == restore_name:
                    call(["docker", "rm", "-f", "-v", restore_name], timeout=45)
            except GateError:
                pass
        # Retain private evidence; do not remove a partially completed backup.
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-backup", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if not args.create_backup:
        print(json.dumps({
            "resultado": "PREPARE_ONLY", "criou_backup": False,
            "producao_alterada": False,
        }))
        return 0
    try:
        report = backup()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        code = str(exc) if isinstance(exc, GateError) and re.fullmatch(
            r"[a-z_]+", str(exc)
        ) else "backup_incompleto"
        print(json.dumps({
            "resultado": "BLOQUEADO", "motivo": code,
            "producao_alterada": False,
            "aviso": "Backup parcial pode existir na pasta privada; nao publicar."
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
