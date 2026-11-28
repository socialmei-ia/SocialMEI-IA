"""Freeze and switch only the production gateway for Premium 7.9.11."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import time
from urllib.request import Request, urlopen

GATEWAY = "socialmei-team-team-gateway-1"
API = "socialmei-team-team-api-1"
SERVICE = "team-gateway"
PROJECT = "socialmei-team"
PUBLIC = "https://socialmei-ia.54-94-213-7.sslip.io"
ASSETS = "/srv/frontend"
REPLACED_BIND = ASSETS + "/scripts/v22-inbox-customer.js"
ARCHIVE_HASH = "463daca04427c86ffa90c02eb7905d8a268de8d29d8c53e6fd369f75ad840929"


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def run(*args):
    result = subprocess.run(args, capture_output=True, timeout=90, check=False)
    require(result.returncode == 0, "Command failed: " + " ".join(args[:3]))
    return result.stdout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def inspect(name):
    return json.loads(run("docker", "inspect", name))[0]


def wiring(item):
    config = item["Config"]
    host = item["HostConfig"]
    return {
        "image": item["Image"],
        "config": {key: config[key] for key in ("Entrypoint", "Cmd", "Env", "User")},
        "network": {key: sorted(value["Aliases"] or [])
                    for key, value in item["NetworkSettings"]["Networks"].items()},
        "restart": host["RestartPolicy"],
        "ports": host["PortBindings"] or {},
        "mounts": sorted([mount["Type"], mount["Source"], mount["Destination"], mount["RW"]]
                         for mount in item["Mounts"]),
    }


def others():
    rows = run("docker", "ps", "--no-trunc", "-a", "--format", "{{.Names}} {{.ID}}").decode().splitlines()
    return sorted(row for row in rows if row.split()[0] != GATEWAY)


def compose(path, *args):
    return run("docker", "compose", "-p", PROJECT, "-f", str(path), *args)


def public(path):
    request = Request(PUBLIC + path, headers={"Cache-Control": "no-cache", "Accept-Encoding": "identity"})
    with urlopen(request, timeout=12) as response:
        require(response.status == 200, "HTTPS route unavailable")
        return response.read()


def database_ready():
    run("docker", "exec", API, "python", "-c",
        "from urllib.request import urlopen; assert urlopen('http://127.0.0.1:8000/health/db',timeout=5).status==200")


def artifact(folder):
    manifest = read(folder / "manifest.json")
    require(manifest["version"] == "7.9.11" and manifest["profile"] == "schema046"
            and manifest["source_archive_sha256"] == ARCHIVE_HASH, "Unexpected archive identity")
    frontend = folder / "frontend"
    files = {path.relative_to(frontend).as_posix() for path in frontend.rglob("*") if path.is_file()}
    if "config.js" in files:
        placeholder = frontend / "config.js"
        require(not placeholder.is_symlink() and placeholder.stat().st_size == 0, "Unexpected bundled config")
        files.remove("config.js")
    require(files == set(manifest["files"]) and "config.js" not in files, "Unexpected release files")
    for name, expected in manifest["files"].items():
        relative = PurePosixPath(name)
        path = frontend / name
        require(not relative.is_absolute() and ".." not in relative.parts and not path.is_symlink()
                and path.resolve().is_relative_to(frontend), "Unsafe asset path")
        require(digest(path.read_bytes()) == expected, "Release checksum failed")
    return manifest["files"]


def verify_assets(assets):
    def check(item):
        name, expected = item
        require(digest(public("/frontend/" + name)) == expected, "HTTPS file mismatch: " + name)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(check, assets.items()))


def verify_gateway(expected, config_hash):
    for attempt in range(12):
        try:
            current = inspect(GATEWAY)
            require(current["State"]["Running"] and wiring(current) == expected, "Gateway runtime differs")
            require(digest(public("/frontend/config.js")) == config_hash, "Runtime config differs")
            public("/api/v1/auth/session")
            database_ready()
            return
        except (RuntimeError, OSError):
            if attempt == 11:
                raise
            time.sleep(2)


def freeze(folder, backup):
    files = artifact(folder)
    current = inspect(GATEWAY)
    old = wiring(current)
    saved = read(backup / "gateway.inspect.private.json")[0]
    require(current["Id"] == saved["Id"] and old == wiring(saved), "Gateway drift since backup")
    subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=backup,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    live_model_path = Path(current["Config"]["Labels"]["com.docker.compose.project.config_files"])
    model = read(live_model_path)
    rollback = copy.deepcopy(model)
    rollback["services"][SERVICE]["image"] = old["image"]
    require(set(rollback["services"]) == {SERVICE}, "Expected gateway-only starting composition")
    candidate = copy.deepcopy(rollback)
    service = candidate["services"][SERVICE]
    mounts = service["volumes"]
    require(all(isinstance(mount, dict) for mount in mounts), "Expected normalized mounts")
    require(sum(mount["target"] == REPLACED_BIND for mount in mounts) == 1, "Expected active inbox mount")
    require(not any(mount["target"] == ASSETS for mount in mounts), "Unexpected frontend mount")
    service["volumes"] = [mount for mount in mounts if mount["target"] != REPLACED_BIND]
    service["volumes"].append({"type": "bind", "source": str(folder / "frontend"),
                               "target": ASSETS, "read_only": True})
    expected = copy.deepcopy(old)
    expected["mounts"] = sorted(
        [mount for mount in old["mounts"] if mount[2] != REPLACED_BIND]
        + [["bind", str(folder / "frontend"), ASSETS, False]]
    )
    paths = {role: folder / (role + ".compose.private.json") for role in ("candidate", "rollback")}
    for role, config in (("candidate", candidate), ("rollback", rollback)):
        write(paths[role], config)
        compose(paths[role], "config", "--quiet")
    config_source = next(Path(mount[1]) for mount in old["mounts"] if mount[2] == ASSETS + "/config.js")
    config_hash = digest(config_source.read_bytes())
    # An existing mount point is required beneath the read-only parent bind.
    (folder / "frontend/config.js").touch(exist_ok=True)
    verify_gateway(old, config_hash)
    baseline = {name: digest(public("/frontend/" + name))
                for name in ("entrada.html", "socialmei-app.html", "scripts/v22-inbox-customer.js")}
    database_ready()
    plan = {
        "before": old, "after": expected, "others": others(), "gateway_id": current["Id"],
        "config": config_hash, "baseline": baseline, "backup": str(backup),
        "compose": {role: digest(path.read_bytes()) for role, path in paths.items()},
        "manifest": digest((folder / "manifest.json").read_bytes()),
        "driver": digest(Path(__file__).read_bytes()),
    }
    rollback_mounts = [(source, destination) for kind, source, destination, writable in old["mounts"]
                       if kind == "bind" and not writable and destination.startswith(ASSETS + "/")]
    smoke_local(folder, old["image"], rollback_mounts, baseline, config_hash)
    smoke_local(folder, old["image"], [(str(folder / "frontend"), ASSETS),
                (str(config_source), ASSETS + "/config.js")], files, config_hash)
    require(others() == plan["others"], "Other containers changed during preflight")
    path = folder / "plan.private.json"
    write(path, plan)
    print("PREFLIGHT_OK", digest(path.read_bytes()), len(files))


def smoke_local(folder, image, mounts, files, config_hash):
    name = folder.name.replace(".", "-") + "-preflight"
    created = False
    binds = [arg for source, target in mounts for arg in
             ("--mount", f"type=bind,source={source},target={target},readonly")]
    try:
        run("docker", "create", "--pull", "never", "--name", name, "--network", "none", *binds,
            "--entrypoint", "caddy", image, "file-server", "--root", ASSETS, "--listen", ":8080")
        created = True
        run("docker", "start", name)
        for attempt in range(12):
            try:
                result = run("docker", "exec", name, "wget", "-qO-", "http://127.0.0.1:8080/socialmei-app.html")
                require(digest(result) == files["socialmei-app.html"], "Isolated gateway served a different app")
                break
            except RuntimeError:
                if attempt == 11:
                    raise
                time.sleep(1)
        result = run("docker", "exec", name, "wget", "-qO-", "http://127.0.0.1:8080/config.js")
        require(digest(result) == config_hash, "Isolated gateway config mount failed")
        for asset in ("entrada.html", "scripts/v22-inbox-customer.js"):
            result = run("docker", "exec", name, "wget", "-qO-", "http://127.0.0.1:8080/" + asset)
            require(digest(result) == files[asset], "Isolated gateway asset mismatch: " + asset)
    finally:
        if created:
            run("docker", "rm", "-f", name)


def cut(action, folder, approved):
    path = folder / "plan.private.json"
    require(digest(path.read_bytes()) == approved, "Plan hash changed")
    plan = read(path)
    require(digest(Path(__file__).read_bytes()) == plan["driver"], "Publication driver changed")
    paths = {role: folder / (role + ".compose.private.json") for role in ("candidate", "rollback")}
    require(all(digest(path.read_bytes()) == plan["compose"][role] for role, path in paths.items()),
            "Composition hash changed")
    require(digest((folder / "manifest.json").read_bytes()) == plan["manifest"], "Manifest hash changed")
    files = artifact(folder)

    def switch(role):
        compose(paths[role], "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", SERVICE)

    def rollback():
        switch("rollback")
        verify_gateway(plan["before"], plan["config"])
        verify_assets(plan["baseline"])
        require(others() == plan["others"], "Other containers changed")
        write(folder / "result.json", {"status": "rolled_back", "plan_sha256": approved})
        print("ROLLBACK_OK")

    require(others() == plan["others"], "Other container identities changed")
    if action == "rollback":
        require(wiring(inspect(GATEWAY)) == plan["after"], "Current gateway does not match this release")
        rollback()
        return
    require(inspect(GATEWAY)["Id"] == plan["gateway_id"], "Gateway changed after preflight")
    verify_gateway(plan["before"], plan["config"])
    try:
        switch("candidate")
        verify_gateway(plan["after"], plan["config"])
        verify_assets(files)
        require(digest(public("/")) == files["index.html"], "Site entry mismatch")
        require(others() == plan["others"], "Other containers changed")
    except Exception:
        rollback()
        raise
    write(folder / "result.json", {"status": "published", "plan_sha256": approved, "files": len(files)})
    print("PUBLISHED", len(files), approved)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "publish", "rollback"))
    parser.add_argument("folder", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--plan-sha256")
    args = parser.parse_args()
    folder = args.folder.resolve(strict=True)
    require(os.geteuid() == 0 and folder.parent == Path("/var/lib/socialmei")
            and folder.name.startswith("premium7911-release."), "Private server context required")
    with Path("/var/lib/socialmei/.premium7911.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "freeze":
            require(args.backup is not None, "Backup path required")
            freeze(folder, args.backup.resolve(strict=True))
        else:
            cut(args.action, folder, args.plan_sha256)


if __name__ == "__main__":
    main()
