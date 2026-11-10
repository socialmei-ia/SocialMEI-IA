#!/usr/bin/env python3
"""Prepare a pinned, private, no-deploy API/gateway #212 Compose overlay.

Requires a successful, isolated 038 backup receipt. Refuses any public or
production mutation. Does not publish services, update automations, or call providers.
The private plan is NOT release authorization or a rollback rehearsal.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile

ROOT = Path("/home/ubuntu/socialmei-team")
ENV = ROOT / ".env.team"
BACKUPS = Path("/var/lib/socialmei-ig212-backups")
CANDIDATE = "345a074310673640084c7634e3da75dd72491813"
BASELINE = "a4720f8b7ea98a67cb40b7b3208acdd7e8bcd510"
TARGETS = {
    "team-api": {
        "name": "socialmei-team-team-api-1",
        "base_id": "sha256:cd88dcbbb9f3d4a6d998eccd18b664d34507989bb47fe1f17602c1faecf4d5a2",
        "candidate_id": "sha256:db132bb3ba656388ef093654821cad7d37291ddc7c2f328e50eadbfd8b38f628",
        "layers": 16,
    },
    "team-gateway": {
        "name": "socialmei-team-team-gateway-1",
        "base_id": "sha256:78691bf1c19d0dcd7416986cc3f36adc6f07614f27a49f24b6659c6854441d50",
        "candidate_id": "sha256:52362398f87cad52847efbac3289f208f8e953616f5f3e436b0e7287fae2cf3a",
        "layers": 12,
    },
}
PROTECTED = (
    "socialmei-team-team-postgres-1", "socialmei-waha",
    "socialmei-menu-worker-continuo", "socialmei-waha-gows-piloto",
    "socialmei-n8n",
)
ENV_FALSE = ("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED",
             "SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED")
HASH_FILES = ("postgres.dump", "images-before.tar", "private-config.tar",
              "baseline-inspect.json")


class Blocked(Exception):
    pass


def require(value, code):
    if not value:
        raise Blocked(code)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def call(args, *, input_bytes=None, timeout=65):
    try:
        p = subprocess.run(
            args, input=input_bytes, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout, cwd=ROOT,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked("command_unavailable") from None
    require(p.returncode == 0 and len(p.stdout) < 4000000, "command_failed")
    return p.stdout


def docker_inspect(name, kind="container"):
    value = json.loads(call(["docker", "inspect", "--type", kind, name], timeout=25))
    require(isinstance(value, list) and len(value) == 1, "inspection_invalid")
    return value[0]


def same_runtime(now, before):
    fields = ("Id", "Image", "RestartCount")
    for field in fields:
        if now.get(field) != before.get(field):
            return False
    state = lambda obj: (obj.get("State") or {})
    return all(
        state(now).get(key) == state(before).get(key)
        for key in ("Running", "StartedAt")
    )


def secure_folder(path):
    require(path.parent == BACKUPS and
            re.fullmatch(r"ig212-[0-9a-f]{32}", path.name) and
            path.is_dir() and not path.is_symlink() and
            path.resolve() == path and path.stat().st_uid == 0 and
            stat.S_IMODE(path.stat().st_mode) == 0o700,
            "backup_folder_invalid")
    return path


def secure_file(path):
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_uid == 0 and
            stat.S_IMODE(path.stat().st_mode) == 0o600,
            "private_file_invalid")
    return path


def verify_config_archive(path):
    """Compare recorded bytes to originals, without extracting or printing them."""
    seen = set()
    with tarfile.open(path, mode="r:") as tar:
        names = tar.getnames()
        require("config/path-map.private.json" in names, "private_archive_map_missing")
        item = tar.extractfile("config/path-map.private.json")
        require(item is not None, "private_archive_map_missing")
        mapping = json.load(item)
        require(isinstance(mapping, dict) and mapping and len(mapping) <= 200,
                "private_archive_map_invalid")
        require(all(re.fullmatch(r"[a-f0-9]{64}", key) and
                    isinstance(p, str) and p.startswith("/") and
                    hashlib.sha256(p.encode()).hexdigest() == key
                    for key, p in mapping.items()),
                "private_archive_paths_invalid")
        for member in tar:
            if member.name == "config/path-map.private.json":
                continue
            parts = member.name.split("/")
            require(len(parts) >= 3 and parts[0] == "config" and
                    parts[1] in mapping and member.name not in seen,
                    "private_archive_entry_invalid")
            seen.add(member.name)
            root = Path(mapping[parts[1]])
            rel = parts[2:]
            require(all(part not in ("", "..") for part in rel),
                    "private_archive_traversal")
            target = root if rel == ["."] else root.joinpath(*rel)
            require(not target.is_symlink() and
                    (target.is_dir() or target.is_file()),
                    "private_file_changed")
            if member.isdir():
                require(target.is_dir(), "private_directory_changed")
            elif member.isfile():
                require(target.is_file() and target.stat().st_size == member.size,
                        "private_file_changed")
                stream = tar.extractfile(member)
                require(stream is not None, "private_file_changed")
                h = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
                require(h.hexdigest() == digest(target), "private_file_changed")
            else:
                raise Blocked("private_archive_special_entry")
    require(bool(seen), "private_archive_empty")


def compose_files(container, expected_count):
    labels = (container.get("Config") or {}).get("Labels") or {}
    require(labels.get("com.docker.compose.project") == "socialmei-team" and
            Path(labels.get("com.docker.compose.project.working_dir", "")).resolve() == ROOT,
            "compose_project_changed")
    paths = [
        Path(p) for p in labels.get(
            "com.docker.compose.project.config_files", "").split(",") if p
    ]
    require(len(paths) == expected_count and all(
        p.is_absolute() and p.is_file() and not p.is_symlink() and
        p.resolve() == p for p in paths),
        "compose_files_changed")
    return paths


def compose_args(paths):
    out = ["docker", "compose", "-p", "socialmei-team",
           "--env-file", str(ENV)]
    for path in paths:
        out.extend(["-f", str(path)])
    return out


def candidate_overlay(service):
    require(service in TARGETS, "service_invalid")
    model = {
        "services": {
            service: {
                "image": f"socialmei-v33/{service}:{CANDIDATE}",
            }
        }
    }
    if service == "team-api":
        model["services"][service]["environment"] = {
            "SOCIALMEI_RELEASE_SHA": CANDIDATE,
        }
    return model


def safe_diff(before, after, service):
    """Only selected image and release SHA can change in fully resolved Compose."""
    expected = copy.deepcopy(before)
    expected["services"][service]["image"] = candidate_overlay(
        service)["services"][service]["image"]
    if service == "team-api":
        expected["services"][service].setdefault("environment", {})[
            "SOCIALMEI_RELEASE_SHA"
        ] = CANDIDATE
    return after == expected


def prepare(folder):
    require(os.geteuid() == 0, "root_required")
    require(ROOT.is_dir() and not ROOT.is_symlink(), "checkout_unavailable")
    require(ENV.is_file() and not ENV.is_symlink(), "env_unavailable")
    secure_folder(folder)
    receipt = json.loads(secure_file(folder / "receipt.private.json").read_text())
    require(receipt.get("profile") == "038" and
            receipt.get("candidate") == CANDIDATE and
            receipt.get("baseline") == BASELINE and
            receipt.get("restore_verified") is True and
            receipt.get("restore_network") == "none" and
            receipt.get("restore_schema_migrations") == 38 and
            receipt.get("restore_tables") == 74 and
            receipt.get("protected_runtime_unchanged") is True and
            receipt.get("compose_api_layers") == 16 and
            receipt.get("compose_gateway_layers") == 12,
            "restore_receipt_invalid")
    hashes = receipt.get("hashes")
    require(isinstance(hashes, dict) and
            set(HASH_FILES) <= set(hashes) and
            all(isinstance(hashes[k], str) and
                re.fullmatch(r"[a-f0-9]{64}", hashes[k]) for k in HASH_FILES),
            "restore_hashes_invalid")
    for name in HASH_FILES:
        require(digest(secure_file(folder / name)) == hashes[name],
                "backup_artifact_changed")
    before = json.loads(
        secure_file(folder / "baseline-inspect.json").read_text()
    )
    names = [v["name"] for v in TARGETS.values()] + list(PROTECTED)
    require(set(before) == set(names), "backup_container_set_changed")
    # Snapshot includes private config files. Verify all original sources still
    # match that archive; a modified overlay or env must stop the cutover plan.
    verify_config_archive(folder / "private-config.tar")
    current = {name: docker_inspect(name) for name in names}
    require(all(same_runtime(current[n], before[n]) for n in names),
            "running_baseline_changed")
    require(current[TARGETS["team-api"]["name"]]["State"][
                "Health"]["Status"] == "healthy", "api_unhealthy")
    require(all(current[n]["State"]["Running"] is True for n in names),
            "protected_service_stopped")
    source_env = dict(x.split("=", 1) for x in
                      current[TARGETS["team-api"]["name"]]["Config"]["Env"]
                      if "=" in x)
    require(all(source_env.get(name, "false").lower() == "false"
                for name in ENV_FALSE), "instagram_outbound_must_stay_disabled")
    result = {}
    for service, cfg in TARGETS.items():
        img = docker_inspect(candidate_overlay(service)["services"][service]["image"],
                             kind="image")
        require(img.get("Id") == cfg["candidate_id"] and
                img.get("Os") == "linux" and
                img.get("Architecture") == "amd64" and
                (img.get("Config", {}).get("Labels") or {}).get(
                    "org.opencontainers.image.revision") == CANDIDATE,
                "candidate_image_identity_changed")
        existing = current[cfg["name"]]
        require(existing["Image"] == cfg["base_id"] and
                (existing["Config"].get("Labels") or {}).get(
                    "org.opencontainers.image.revision") == BASELINE,
                "running_image_changed")
        paths = compose_files(existing, cfg["layers"])
        args = compose_args(paths)
        old = json.loads(call(args + ["config", "--format", "json"]))
        model = old["services"][service]
        require(model.get("image") == existing["Config"].get("Image"),
                "baseline_compose_image_changed")
        active_env = dict(x.split("=", 1) for x in existing["Config"]["Env"]
                          if "=" in x)
        require(all(active_env.get(k) == ("" if v is None else str(v))
                    for k, v in (model.get("environment") or {}).items()),
                "baseline_compose_env_changed")
        overlay = candidate_overlay(service)
        proposal = json.loads(
            call(args + ["-f", "-", "config", "--format", "json"],
                 input_bytes=json.dumps(overlay).encode())
        )
        require(safe_diff(old, proposal, service),
                "candidate_compose_diff_unexpected")
        result[service] = {
            "overlay": overlay,
            "baseline_model_sha256": hashlib.sha256(
                json.dumps(old, sort_keys=True).encode()).hexdigest(),
            "candidate_model_sha256": hashlib.sha256(
                json.dumps(proposal, sort_keys=True).encode()).hexdigest(),
            "layers": len(paths),
        }
    # Verify nothing restarted while we were inspecting/configuring.
    after = {name: docker_inspect(name) for name in names}
    require(all(same_runtime(after[n], before[n]) for n in names),
            "baseline_changed_during_prepare")
    # Only files inside the root-private, owned, verified backup directory.
    for service, item in result.items():
        name = f"{service}.ig212.candidate.compose.json"
        payload = json.dumps(item["overlay"], sort_keys=True).encode() + b"\n"
        path = folder / name
        if path.exists():
            require(secure_file(path).read_bytes() == payload,
                    "candidate_overlay_already_differs")
        else:
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                  0o600), "wb") as out:
                out.write(payload)
    plan = {
        "release": CANDIDATE,
        "baseline": BASELINE,
        "backup_receipt_sha256": digest(folder / "receipt.private.json"),
        "overlay_sha256": {
            service: digest(folder / f"{service}.ig212.candidate.compose.json")
            for service in TARGETS
        },
        "model_sha256": {k: {"before": v["baseline_model_sha256"],
                            "after": v["candidate_model_sha256"]}
                         for k, v in result.items()},
        "baseline_containers": {
            name: {
                "id": before[name]["Id"], "image": before[name]["Image"],
                "started": before[name]["State"]["StartedAt"],
            } for name in names
        },
        "status": "PREPARED_NO_DEPLOY",
        "apply_authorized": False,
        "workflow_n8n_changed": False,
        "production_changed": False,
    }
    plan_path = folder / "cutover-plan.private.json"
    payload = json.dumps(plan, sort_keys=True, indent=2).encode()
    if plan_path.exists():
        require(secure_file(plan_path).read_bytes() == payload,
                "plan_already_differs")
    else:
        with os.fdopen(os.open(plan_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                              0o600), "wb") as out:
            out.write(payload)
    return {
        "resultado": "PLANO_212_PREPARADO_SEM_DEPLOY",
        "plano_privado": str(plan_path),
        "api_camadas": result["team-api"]["layers"],
        "gateway_camadas": result["team-gateway"]["layers"],
        "imagem_e_compose_validados": True,
        "backup_validado": True,
        "containers_preservados": True,
        "deploy_autorizado": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", required=True)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if not args.prepare:
        print(json.dumps({"resultado": "PREPARE_ONLY", "production_changed": False}))
        return 0
    try:
        report = prepare(Path(args.backup))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, Blocked) and re.fullmatch(
            r"[a-z0-9_]+", str(error)
        ) else "plan_blocked_details_redacted"
        print(json.dumps({"resultado": "BLOQUEADO", "motivo": code,
                          "deploy_executado": False,
                          "backup_pode_conter_arquivos_preparados": True}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
