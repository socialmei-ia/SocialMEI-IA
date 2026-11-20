"""Read-only CRM233 release preflight using each container's own Compose chain.

Run on the Docker host. Does not load/build images, write overlays or restart.
Raw Compose configuration and environment stay in memory; only hashes leave it.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from decimal import Decimal

SHA = "17cfd1956416c2d4c8431fec11800f73254bde12"
API = "socialmei-team-team-api-1"
GATEWAY = "socialmei-team-team-gateway-1"
OLD_API = "socialmei-v33/team-api:d4618e85b5b9924835974e13b2e2f4c711735e97"
NEW_API = "socialmei-v33/team-api:" + SHA
PREMIUM = "socialmei-premium-gateway:v6.5.1-cadastro-claro-1"
ASSET = "/srv/frontend/scripts/v22-inbox-customer.js"
JS_HASH = "b50ce7dc0a29c7da8d2d972a31ab252d5cfb90778fc28f0c511d9e0322c87a85"
ZIP_HASH = "7aabc0f0ef393791f4c69b80a15516e99a5e00dcf1fd99ec8151cff6a7f43c76"


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def run(args, *, source=None, cwd=None):
    p = subprocess.run(args, input=source, capture_output=True, text=True,
                       cwd=cwd, timeout=90)
    require(p.returncode == 0, "READ_COMMAND_FAILED")
    return p.stdout


def inspect(name):
    return json.loads(run(["docker", "inspect", name]))[0]


def chain(container, service):
    labels = container["Config"].get("Labels") or {}
    require(labels.get("com.docker.compose.project") == "socialmei-team", "PROJECT_CHANGED")
    require(labels.get("com.docker.compose.service") == service, "SERVICE_CHANGED")
    folder = labels["com.docker.compose.project.working_dir"]
    files = labels["com.docker.compose.project.config_files"].split(",")
    require(files and all(Path(f).is_absolute() and Path(f).is_file() for f in files),
            "COMPOSE_FILES_UNAVAILABLE")
    command = ["docker", "compose", "--project-directory", folder, "-p", "socialmei-team"]
    for file in files:
        command.extend(["-f", file])
    return command, folder, files


def validate_change(before, after, service, *, asset_source=None):
    expected = copy.deepcopy(before)
    if service == "team-api":
        require(expected["services"][service]["image"] == OLD_API, "API_COMPOSE_DRIFT")
        expected["services"][service]["image"] = NEW_API
    else:
        require(expected["services"][service]["image"] == PREMIUM, "PREMIUM_COMPOSE_DRIFT")
        volumes = expected["services"][service].setdefault("volumes", [])
        require(not any(v.get("target") == ASSET for v in volumes), "ASSET_ALREADY_MOUNTED")
        added = [v for v in after["services"][service].get("volumes", [])
                 if v.get("target") == ASSET]
        require(len(added) == 1 and added[0].get("type") == "bind"
                and added[0].get("source") == asset_source
                and added[0].get("read_only") is True, "UNEXPECTED_ASSET_MOUNT")
        volumes.extend(added)
    require(expected == after, "CHANGE_EXCEEDS_API_IMAGE_OR_SINGLE_JS")


def validate_runtime(service, container, document=None):
    """A rendered baseline must preserve the running environment and bind mounts."""
    image = json.loads(run(["docker", "image", "inspect", container["Image"]]))[0]["Config"]
    environment = dict(item.split("=", 1) for item in image.get("Env", []) if "=" in item)
    environment.update(service.get("environment") or {})
    live = dict(item.split("=", 1) for item in container["Config"].get("Env", []) if "=" in item)
    require(environment == live, "RUNNING_ENVIRONMENT_DIFFERS_FROM_COMPOSE")
    mounts = {m["target"]: m for m in service.get("volumes", [])}
    for mount in container.get("Mounts", []):
        if mount["Type"] != "bind":
            continue
        configured = mounts.get(mount["Destination"], {})
        require(configured.get("type") == "bind" and configured.get("source") == mount["Source"]
                and bool(configured.get("read_only", False)) == (not mount["RW"]),
                "RUNNING_MOUNT_DIFFERS_FROM_COMPOSE")
    require({m["Destination"] for m in container.get("Mounts", [])} == set(mounts),
            "RUNNING_MOUNT_TARGETS_DIFFER_FROM_COMPOSE")
    for field in ("command", "entrypoint"):
        live_field = "Cmd" if field == "command" else "Entrypoint"
        configured = service.get(field)
        if configured is None:
            configured = image.get(live_field)
        require(configured == container["Config"].get(live_field), "RUNNING_COMMAND_DIFFERS_FROM_COMPOSE")
    if document is None:
        return
    networks = {document["networks"][key]["name"] for key in service.get("networks", {})}
    require(networks == set(container.get("NetworkSettings", {}).get("Networks", {})),
            "RUNNING_NETWORKS_DIFFER_FROM_COMPOSE")
    host = container["HostConfig"]
    require(service.get("restart", "no") == host.get("RestartPolicy", {}).get("Name", "no"),
            "RUNNING_RESTART_POLICY_DIFFERS_FROM_COMPOSE")
    ports = {}
    for port in service.get("ports", []):
        key = str(port["target"]) + "/" + port.get("protocol", "tcp")
        ports.setdefault(key, []).append({"HostIp": port.get("host_ip", ""), "HostPort": str(port["published"])})
    require(ports == (host.get("PortBindings") or {}), "RUNNING_PORT_BINDINGS_DIFFER_FROM_COMPOSE")
    for configured, actual in (("read_only", "ReadonlyRootfs"), ("privileged", "Privileged")):
        require(bool(service.get(configured, False)) == bool(host.get(actual)), "RUNNING_SECURITY_FLAGS_DIFFER_FROM_COMPOSE")
    limits = service.get("deploy", {}).get("resources", {}).get("limits", {})
    reservations = service.get("deploy", {}).get("resources", {}).get("reservations", {})

    def memory(value):
        text = str(value).lower()
        for suffix, scale in (("gb", 1024**3), ("g", 1024**3), ("mb", 1024**2),
                              ("m", 1024**2), ("kb", 1024), ("k", 1024), ("b", 1)):
            if text.endswith(suffix):
                return int(Decimal(text[:-len(suffix)]) * scale)
        return int(value)

    for expected, actual in ((memory(service.get("mem_limit", limits.get("memory", 0))), "Memory"),
                             (memory(service.get("mem_reservation", reservations.get("memory", 0))), "MemoryReservation"),
                             (memory(service.get("memswap_limit", 0)), "MemorySwap"),
                             (int(Decimal(str(service.get("cpus", limits.get("cpus", 0)))) * 10**9), "NanoCpus"),
                             (int(service.get("cpu_shares", 0)), "CpuShares"),
                             (int(service.get("pids_limit", limits.get("pids", 0))), "PidsLimit")):
        require(expected == (host.get(actual) or 0), "RUNNING_RESOURCE_LIMITS_DIFFER_FROM_COMPOSE")
    for configured, actual in (("cap_add", "CapAdd"), ("cap_drop", "CapDrop"), ("security_opt", "SecurityOpt")):
        require(set(service.get(configured) or []) == set(host.get(actual) or []),
                "RUNNING_SECURITY_OPTIONS_DIFFER_FROM_COMPOSE")
    require(service.get("user", image.get("User", "")) == container["Config"].get("User", ""),
            "RUNNING_USER_DIFFERS_FROM_COMPOSE")


def prepare(package):
    package = Path(package).resolve(strict=True)
    asset = package / "v22-inbox-customer.js"
    require(not asset.is_symlink() and asset.is_file(), "ASSET_UNAVAILABLE")
    require(hashlib.sha256(asset.read_bytes()).hexdigest() == JS_HASH, "ASSET_HASH_MISMATCH")
    api, gateway = inspect(API), inspect(GATEWAY)
    require(api["Config"]["Image"] == OLD_API, "ACTIVE_API_CHANGED")
    require(json.loads(run(["docker", "image", "inspect", OLD_API]))[0]["Id"] == api["Image"],
            "OLD_API_TAG_DRIFT")
    require(api["State"].get("Health", {}).get("Status") == "healthy", "API_NOT_HEALTHY")
    require(gateway["Config"]["Image"] == PREMIUM, "ACTIVE_PREMIUM_CHANGED")
    require(gateway["State"]["Status"] == "running", "PREMIUM_NOT_RUNNING")
    require(json.loads(run(["docker", "image", "inspect", PREMIUM]))[0]["Id"] == gateway["Image"],
            "PREMIUM_TAG_DRIFT")
    for item in gateway.get("Mounts", []):
        target = item["Destination"].rstrip("/")
        require(not (ASSET == target or ASSET.startswith(target + "/")), "EXISTING_ASSET_PARENT_MOUNT")
    image = json.loads(run(["docker", "image", "inspect", NEW_API]))[0]
    require(image["Config"].get("Labels", {}).get("org.opencontainers.image.revision") == SHA,
            "CANDIDATE_REVISION_MISMATCH")
    # Immutable ID must match the certified package; a tag/revision label is insufficient.
    import zipfile
    with (package / "images.zip").open("rb") as stream:
        require(hashlib.file_digest(stream, "sha256").hexdigest() == ZIP_HASH, "PACKAGE_HASH_MISMATCH")
    with zipfile.ZipFile(package / "images.zip") as archive:
        receipt_bytes = archive.read("image-receipt.json")
        hashes = dict(line.split(maxsplit=1) for line in archive.read("SHA256SUMS").decode().splitlines())
        require(hashes.get(hashlib.sha256(receipt_bytes).hexdigest()) == "image-receipt.json",
                "RECEIPT_HASH_MISMATCH")
        receipt = json.loads(receipt_bytes)
    require(receipt["source_sha"] == SHA and receipt["release_profile"] == "040", "RECEIPT_MISMATCH")
    require(receipt["images"]["team-api"]["image_id"] == image["Id"], "IMAGE_ID_MISMATCH")
    output = {"mode": "read_only_preflight", "source_sha": SHA, "images_already_loaded": True,
              "api_old_image_id": api["Image"], "api_new_image_id": image["Id"],
              "premium_image_id_preserved": gateway["Image"], "asset_sha256": JS_HASH,
              "services": {}, "production_modified": False}
    for name, container in (("team-api", api), ("team-gateway", gateway)):
        command, folder, files = chain(container, name)
        before = json.loads(run(command + ["config", "--format", "json"], cwd=folder))
        validate_runtime(before["services"][name], container, before)
        overlay = {"services": {name: {"image": NEW_API}}} if name == "team-api" else {
            "services": {name: {"volumes": [{"type": "bind", "source": str(asset),
                                              "target": ASSET, "read_only": True}]}}}
        after = json.loads(run(command + ["-f", "-", "config", "--format", "json"],
                               source=json.dumps(overlay), cwd=folder))
        validate_change(before, after, name, asset_source=str(asset))
        output["services"][name] = {"compose_file_count": len(files),
            "baseline_config_sha256": digest(before), "candidate_config_sha256": digest(after),
            "chain_sha256": digest(files), "live_config_sha256": digest({
                "Config": container["Config"], "HostConfig": container["HostConfig"],
                "Mounts": container["Mounts"], "Image": container["Image"]}),
            "permitted_delta": "image" if name == "team-api" else "one_readonly_js_bind"}
    # A readiness request is read-only; never invoke the migrator/entrypoint as a test.
    code = "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health/db',timeout=12); assert r.status==200"
    run(["docker", "exec", API, "python", "-B", "-c", code])
    output["health_db"] = 200
    output["release_plan_sha256"] = digest(output)
    output["next_step"] = "explicit_operational_approval_then_fresh_preflight_and_backup"
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.package), indent=2))
    except Exception as error:
        print(json.dumps({"complete": False, "production_modified": False,
                          "reason": str(error) if type(error) is RuntimeError else type(error).__name__}))
        raise SystemExit(1)
