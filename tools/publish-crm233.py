"""Apply the reviewed CRM233 plan only after explicit operational approval.

No migrations, image imports, database writes, channel changes or worker restart.
API and premium gateway use independent original Compose chains and rollbacks.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

spec = importlib.util.spec_from_file_location("crm_preflight", Path(__file__).with_name("prepare-crm233-release.py"))
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def write_private(path, value):
    # Exclusive creation prevents overwriting an earlier rollback or approval.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    path.chmod(0o600)


def deploy(command, service, folder):
    result = subprocess.run(command + ["up", "-d", "--no-deps", "--no-build", "--pull", "never",
                                       "--force-recreate", service], cwd=folder,
                            capture_output=True, timeout=210)
    preflight.require(result.returncode == 0, "SERVICE_RECREATE_FAILED")


def wait(name, image, healthy=False):
    until = time.monotonic() + 120
    while time.monotonic() < until:
        obj = preflight.inspect(name)
        if (obj["Image"] == image and obj["State"]["Status"] == "running"
                and (not healthy or obj["State"].get("Health", {}).get("Status") == "healthy")):
            return
        time.sleep(3)
    raise RuntimeError("SERVICE_HEALTH_FAILED")


def apply(package, approved_plan):
    os.umask(0o077)
    package = Path(package).resolve(strict=True)
    plan = preflight.prepare(package)
    preflight.require(plan["release_plan_sha256"] == approved_plan, "APPROVED_BASELINE_CHANGED")
    directory = package / ("approved-release-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    directory.mkdir(mode=0o700)
    write_private(directory / "preflight.json", plan)
    items = []
    for service, name, image in (("team-api", preflight.API, plan["api_new_image_id"]),
                                 ("team-gateway", preflight.GATEWAY, plan["premium_image_id_preserved"])):
        current = preflight.inspect(name)
        command, folder, files = preflight.chain(current, service)
        original = json.loads(preflight.run(command + ["config", "--format", "json"], cwd=folder))
        preflight.require(preflight.digest(original) == plan["services"][service]["baseline_config_sha256"],
                          "BASELINE_CHANGED_BEFORE_BACKUP")
        # Rollback uses a frozen, resolved Compose document and immutable image ID.
        original["services"][service]["image"] = current["Image"]
        frozen = directory / (service + ".rollback.private.json")
        write_private(frozen, original)
        rollback = ["docker", "compose", "--project-directory", folder, "-p", "socialmei-team", "-f", str(frozen)]
        # Configuration files and raw inspect are private and never printed.
        write_private(directory / (service + ".inspect.private.json"), current)
        saved = []
        for index, file in enumerate(files):
            destination = directory / f"{service}-{index}.compose.private.backup"
            with destination.open("xb") as stream:
                stream.write(Path(file).read_bytes())
            saved.append({"source": file, "backup": str(destination),
                          "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
        write_private(directory / (service + ".files.private.json"), saved)
        overlay = directory / (service + ".override.json")
        doc = {"services": {service: {"image": preflight.NEW_API}}} if service == "team-api" else {
            "services": {service: {"volumes": [{"type": "bind", "source": str(package / "v22-inbox-customer.js"),
                                                 "target": preflight.ASSET, "read_only": True}]}}}
        write_private(overlay, doc)
        candidate_command = command + ["-f", str(overlay)]
        rendered = json.loads(preflight.run(candidate_command + ["config", "--format", "json"], cwd=folder))
        preflight.require(preflight.digest(rendered) == plan["services"][service]["candidate_config_sha256"],
                          "PERSISTED_PLAN_CHANGED")
        items.append({"service": service, "name": name, "command": command,
                      "candidate": candidate_command, "folder": folder,
                      "rollback": rollback,
                      "old_image": current["Image"], "image": image})
    write_private(directory / "rollback.private.json", [{"service": i["service"], "cwd": i["folder"],
        "argv": i["rollback"] + ["up", "-d", "--no-deps", "--no-build", "--pull", "never",
                               "--force-recreate", i["service"]], "expected_image_id": i["old_image"]}
        for i in reversed(items)])
    attempted = []
    try:
        for item in items:
            # Recheck that source Compose files have not changed since the backups.
            saved = json.loads((directory / (item["service"] + ".files.private.json")).read_text())
            preflight.require(all(hashlib.sha256(Path(f["source"]).read_bytes()).hexdigest() == f["sha256"]
                                  for f in saved), "COMPOSE_CHANGED_AFTER_BACKUP")
            attempted.append(item)
            deploy(item["candidate"], item["service"], item["folder"])
            wait(item["name"], item["image"], item["service"] == "team-api")
        loaded = preflight.run(["docker", "exec", preflight.GATEWAY, "sha256sum", preflight.ASSET]).split()[0]
        preflight.require(loaded == preflight.JS_HASH, "SERVED_JS_HASH_MISMATCH")
        code = "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/health/db',timeout=12).status==200"
        preflight.run(["docker", "exec", preflight.API, "python", "-B", "-c", code])
        write_private(directory / "result.json", {"status": "published", "source_sha": preflight.SHA,
            "plan_sha256": approved_plan, "premium_image_preserved": True,
            "migrations_run": False, "workers_changed": False, "channel_bindings_changed": False})
        print(json.dumps({"status": "published", "source_sha": preflight.SHA,
                          "premium_image_preserved": True}))
    except Exception:
        failed = []
        for item in reversed(attempted):
            try:
                deploy(item["rollback"], item["service"], item["folder"])
                wait(item["name"], item["old_image"], item["service"] == "team-api")
            except Exception:
                failed.append(item["service"])
        write_private(directory / "result.json", {"status": "rollback_failed" if failed else "rolled_back",
                                                  "failed_rollback_services": failed})
        raise RuntimeError("ROLLBACK_REQUIRES_OPERATOR" if failed else "PUBLICATION_FAILED_ROLLED_BACK") from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--approved-plan", required=True, help="SHA256 approved by the owner after preflight")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        preflight.require(args.apply, "EXPLICIT_APPLY_REQUIRED_USE_READ_ONLY_PREFLIGHT_FIRST")
        apply(args.package, args.approved_plan)
    except Exception as error:
        print(json.dumps({"status": "blocked_or_failed",
                          "reason": str(error) if type(error) is RuntimeError else type(error).__name__}))
        raise SystemExit(1)
