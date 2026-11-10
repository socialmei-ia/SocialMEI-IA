#!/usr/bin/env python3
"""Release #212 hotfix: pin known-good psycopg 3.3.7; stage, test, then cutover.

The official 345a image is immutable. Build a new derivative tag with a single
driver change. Never disable SSL, migrate databases, touch n8n or send messages.
--apply demands explicit operator authorization; rollback has its own mode.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import fcntl

BASE = "a4720f8b7ea98a67cb40b7b3208acdd7e8bcd510"
SHA = "345a074310673640084c7634e3da75dd72491813"
API = "socialmei-team-team-api-1"
GW = "socialmei-team-team-gateway-1"
BASE_API_ID = "sha256:cd88dcbbb9f3d4a6d998eccd18b664d34507989bb47fe1f17602c1faecf4d5a2"
BASE_GW_ID = "sha256:78691bf1c19d0dcd7416986cc3f36adc6f07614f27a49f24b6659c6854441d50"
OFFICIAL_API_ID = "sha256:db132bb3ba656388ef093654821cad7d37291ddc7c2f328e50eadbfd8b38f628"
OFFICIAL_GW_ID = "sha256:52362398f87cad52847efbac3289f208f8e953616f5f3e436b0e7287fae2cf3a"
OFFICIAL_API = "socialmei-v33/team-api:" + SHA
OFFICIAL_GW = "socialmei-v33/team-gateway:" + SHA
HOTFIX = "socialmei-v33/team-api:" + SHA + "-psycopg337"
BACKUP = Path("/var/lib/socialmei-ig212-backups/ig212-c2edda7b5aec47af9eef53908592e3e3")
ROOT = Path("/home/ubuntu/socialmei-team")
ENV = ROOT / ".env.team"
LOCK = Path("/run/lock/socialmei-wa-pilot-release.lock")
JOURNAL = BACKUP / "hotfix337-publication.private.json"
PLAN = BACKUP / "cutover-plan.private.json"
PROTECTED = (
    "socialmei-team-team-postgres-1",
    "socialmei-waha",
    "socialmei-menu-worker-continuo",
    "socialmei-waha-gows-piloto",
    "socialmei-n8n",
)
REQUIRED_FILES = ("postgres.dump", "images-before.tar", "private-config.tar", "baseline-inspect.json")
ALLOW = "AUTORIZO-IG212-HOTFIX337-SEM-N8N"
ALLOW_ROLLBACK = "AUTORIZO-ROLLBACK-IG212-HOTFIX337"


class Stop(Exception):
    pass


def check(ok, code):
    if not ok:
        raise Stop(code)


def run(cmd, *, stdin=None, timeout=80, cwd=None):
    try:
        p = subprocess.run(
            cmd, input=stdin, cwd=cwd, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("execution_failed_or_timed_out") from None
    check(p.returncode == 0, "execution_failed")
    return p.stdout


def docker(name, image=False):
    r = json.loads(run(["docker", "inspect", "--type", "image" if image else "container",
                         name], timeout=25))
    check(isinstance(r, list) and len(r) == 1, "docker_identity_invalid")
    return r[0]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def private_file(path):
    check(path.is_file() and not path.is_symlink()
          and path.stat().st_uid == 0
          and stat.S_IMODE(path.stat().st_mode) == 0o600,
          "private_file_invalid")
    return path


def private_backup():
    check(os.geteuid() == 0, "root_required")
    check(BACKUP.resolve() == BACKUP and BACKUP.is_dir()
          and not BACKUP.is_symlink() and BACKUP.stat().st_uid == 0
          and stat.S_IMODE(BACKUP.stat().st_mode) == 0o700,
          "backup_directory_invalid")
    check(ROOT.is_dir() and ROOT.resolve() == ROOT and
          ENV.is_file() and not ENV.is_symlink(), "compose_directory_invalid")
    receipt = json.loads(private_file(BACKUP / "receipt.private.json").read_text())
    check(receipt.get("profile") == "038" and
          receipt.get("candidate") == SHA and
          receipt.get("baseline") == BASE and
          receipt.get("restore_verified") is True and
          receipt.get("restore_schema_migrations") == 38 and
          receipt.get("restore_tables") == 74,
          "backup_restore_receipt_invalid")
    for name in REQUIRED_FILES:
        check(digest(private_file(BACKUP / name)) ==
              receipt.get("hashes", {}).get(name), "backup_hash_changed")
    prior = json.loads(private_file(BACKUP / "publication212.private.json").read_text())
    check(prior.get("phase") == "restored_previous_images"
          and prior.get("attempted") == ["team-api"]
          and prior.get("restored") == ["team-api"],
          "prior_rollback_not_confirmed")
    prepared = json.loads(private_file(PLAN).read_text())
    check(prepared.get("release") == SHA and
          prepared.get("baseline") == BASE and
          prepared.get("status") == "PREPARED_NO_DEPLOY" and
          prepared.get("apply_authorized") is False and
          prepared.get("workflow_n8n_changed") is False,
          "original_plan_invalid")
    return prepared


def snapshot():
    names = (API, GW) + PROTECTED
    return {name: docker(name) for name in names}


def stable(old, new):
    return (old.get("Id") == new.get("Id")
            and old.get("Image") == new.get("Image")
            and old.get("RestartCount") == new.get("RestartCount")
            and old.get("State", {}).get("StartedAt") ==
            new.get("State", {}).get("StartedAt")
            and old.get("State", {}).get("Running") ==
            new.get("State", {}).get("Running"))


def protected_unchanged(reference):
    for name in PROTECTED:
        check(stable(reference[name], docker(name)), "protected_runtime_changed")


def current_baseline(reference=None):
    a, g = docker(API), docker(GW)
    check(a.get("Image") == BASE_API_ID and g.get("Image") == BASE_GW_ID,
          "baseline_image_changed")
    check((a.get("Config", {}).get("Labels") or {}).get(
              "org.opencontainers.image.revision") == BASE and
          (g.get("Config", {}).get("Labels") or {}).get(
              "org.opencontainers.image.revision") == BASE,
          "baseline_revision_changed")
    check(a.get("State", {}).get("Health", {}).get("Status") == "healthy"
          and a["State"].get("Running") is True and
          g["State"].get("Running") is True,
          "baseline_unhealthy")
    if reference is not None:
        check(stable(reference[API], a) and stable(reference[GW], g),
              "baseline_runtime_changed")
    return a, g


def image_pin():
    ap, gw = docker(OFFICIAL_API, image=True), docker(OFFICIAL_GW, image=True)
    check(ap.get("Id") == OFFICIAL_API_ID and gw.get("Id") == OFFICIAL_GW_ID,
          "official_image_identity_changed")
    for obj in (ap, gw):
        check(obj.get("Os") == "linux" and obj.get("Architecture") == "amd64"
              and (obj.get("Config", {}).get("Labels") or {}).get(
                  "org.opencontainers.image.revision") == SHA,
              "official_image_revision_changed")


def compose_paths(container, expected):
    lbl = container.get("Config", {}).get("Labels") or {}
    check(lbl.get("com.docker.compose.project") == "socialmei-team"
          and Path(lbl.get("com.docker.compose.project.working_dir", "")).resolve() == ROOT,
          "compose_project_changed")
    paths = [Path(x) for x in lbl.get(
        "com.docker.compose.project.config_files", "").split(",") if x]
    check(len(paths) == expected and all(
        p.is_absolute() and p.resolve() == p and p.is_file() and not p.is_symlink()
        for p in paths), "compose_path_changed")
    return paths


def compose_args(obj, count):
    out = ["docker", "compose", "-p", "socialmei-team",
           "--env-file", str(ENV)]
    for path in compose_paths(obj, count):
        out.extend(["-f", str(path)])
    return out


def model(args):
    return json.loads(run(args + ["config", "--format", "json"], timeout=90, cwd=ROOT))


def overlay(service):
    tag = HOTFIX if service == "team-api" else OFFICIAL_GW
    out = {"services": {service: {"image": tag}}}
    if service == "team-api":
        out["services"][service]["environment"] = {"SOCIALMEI_RELEASE_SHA": SHA}
    return out


def plan_diff(ref, prepared):
    import copy
    output = {}
    for service, container, count in (
        ("team-api", ref[API], 16), ("team-gateway", ref[GW], 12)
    ):
        args = compose_args(container, count)
        before = model(args)
        check(before["services"][service]["image"] ==
              container["Config"]["Image"], "compose_baseline_image_changed")
        fingerprint = hashlib.sha256(json.dumps(
            before, sort_keys=True).encode()).hexdigest()
        check(fingerprint == prepared.get("model_sha256", {}).get(
            service, {}).get("before"), "compose_baseline_changed")
        after = json.loads(run(
            args + ["-f", "-", "config", "--format", "json"],
            stdin=json.dumps(overlay(service)).encode(), cwd=ROOT, timeout=90
        ))
        expected = copy.deepcopy(before)
        expected["services"][service]["image"] = overlay(service)[
            "services"][service]["image"]
        if service == "team-api":
            expected["services"][service].setdefault(
                "environment", {})["SOCIALMEI_RELEASE_SHA"] = SHA
        check(after == expected, "compose_change_out_of_scope")
        output[service] = {"args": args, "before": fingerprint}
    return output


def smoke(image, existing):
    code = (
        "import json,sys,psycopg,importlib.metadata;"
        "from psycopg import pq;"
        "from shared_data import database_health_payload;"
        "r=database_health_payload();"
        "good=(r.get('status')=='healthy' and psycopg.__version__=='3.3.7'"
        " and importlib.metadata.version('psycopg-binary')=='3.3.7'"
        " and pq.__impl__=='binary');"
        "print(json.dumps({'version':psycopg.__version__,'healthy':bool(good)}));"
        "sys.exit(0 if good else 3)"
    )
    vars = existing["Config"]["Env"]
    check(all("\n" not in x and "\r" not in x for x in vars),
          "multiline_environment_rejected")
    args = [
        "docker", "run", "--rm", "--pull", "never",
        "--network", "container:" + API,
        "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--pids-limit", "128", "--memory", "512m",
        "--env-file", "/dev/stdin", "--entrypoint", "python",
        image, "-B", "-c", code,
    ]
    raw = run(args, stdin=("\n".join(vars) + "\n").encode(), timeout=75)
    try:
        result = json.loads(raw.decode().strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise Stop("smoke_output_unexpected") from None
    check(result == {"version": "3.3.7", "healthy": True},
          "driver337_db_health_failed")


def stage_image(existing, reference):
    image_pin()
    # Build a derivative on the server. Never overwrite the exact official tag.
    recipe = (
        "FROM " + OFFICIAL_API + "\n"
        "RUN python -m pip install --no-cache-dir --disable-pip-version-check"
        " --only-binary=:all: --force-reinstall"
        " 'psycopg[binary]==3.3.7'\n"
        'LABEL org.socialmei.hotfix.psycopg="3.3.7"\n'
        'LABEL org.socialmei.hotfix.base="' + SHA + '"\n'
    )
    build = BACKUP / "hotfix337-build"
    if not build.exists():
        build.mkdir(mode=0o700)
    check(build.is_dir() and not build.is_symlink()
          and build.stat().st_uid == 0, "build_folder_invalid")
    dockerfile = build / "Dockerfile"
    if dockerfile.exists():
        check(dockerfile.is_file() and not dockerfile.is_symlink()
              and dockerfile.read_text() == recipe, "build_recipe_changed")
    else:
        fd = os.open(dockerfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(recipe)
    try:
        staged = docker(HOTFIX, image=True)
        check((staged.get("Config", {}).get("Labels") or {}).get(
            "org.socialmei.hotfix.base") == SHA, "hotfix_tag_altered")
    except Stop as exc:
        if str(exc) != "execution_failed":
            raise
        run(["docker", "build", "--pull=false", "--network=default",
             "-f", str(dockerfile), "-t", HOTFIX, str(build)], timeout=480)
        staged = docker(HOTFIX, image=True)
    labels = (staged.get("Config") or {}).get("Labels") or {}
    check(labels.get("org.opencontainers.image.revision") == SHA
          and labels.get("org.socialmei.hotfix.psycopg") == "3.3.7"
          and labels.get("org.socialmei.hotfix.base") == SHA
          and staged.get("Os") == "linux"
          and staged.get("Architecture") == "amd64", "built_image_invalid")
    current_baseline(reference)
    protected_unchanged(reference)
    smoke(HOTFIX, existing)
    current_baseline(reference)
    protected_unchanged(reference)
    return staged.get("Id")


def write_journal(state):
    data = json.dumps(state, sort_keys=True, indent=2).encode()
    fd, tmp = tempfile.mkstemp(prefix=".hotfix337-", dir=BACKUP)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, JOURNAL)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def wait_for(name, expected_id, api=False):
    for _ in range(55):
        c = docker(name)
        if c.get("Image") == expected_id and c["State"].get("Running") is True:
            health = (c["State"].get("Health") or {}).get("Status")
            if (api and health == "healthy") or (not api and health in (None, "healthy")):
                return c
            check(health in ("starting", None), "new_container_unhealthy")
        time.sleep(2)
    raise Stop("new_container_health_timeout")


def same_security(before, after):
    b = before.get("HostConfig") or {}
    a = after.get("HostConfig") or {}
    for key in ("Privileged", "CapAdd", "CapDrop", "SecurityOpt",
                "NetworkMode", "PortBindings", "Binds", "ReadonlyRootfs",
                "PidMode", "IpcMode", "Devices", "RestartPolicy"):
        check(b.get(key) == a.get(key), "runtime_security_changed")
    def mounts(obj):
        return sorted((x.get("Type"), x.get("Source"),
                       x.get("Destination"), x.get("RW"))
                      for x in obj.get("Mounts", []))
    check(mounts(before) == mounts(after), "runtime_mount_changed")


def compose_up(args, *, overlay_file=None, service):
    cmd = args + (["-f", str(overlay_file)] if overlay_file else [])
    return run(cmd + ["up", "-d", "--no-deps", "--no-build", "--pull",
                      "never", service], timeout=230, cwd=ROOT)


def rollback(ref, commands, state):
    state["phase"] = "restoring"
    write_journal(state)
    for service in reversed(state["attempted"]):
        name = API if service == "team-api" else GW
        identity = BASE_API_ID if service == "team-api" else BASE_GW_ID
        old = ref[name]
        now = docker(name)
        check(now.get("Image") in (identity,
              state.get("image_id") if service == "team-api" else OFFICIAL_GW_ID),
              "foreign_image_requires_manual_recovery")
        if not stable(now, old):
            command = commands[service]["args"]
            run(command + ["up", "-d", "--force-recreate", "--no-deps",
                           "--no-build", "--pull", "never", service],
                timeout=230, cwd=ROOT)
            restored = wait_for(name, identity, api=(name == API))
            check(restored["Config"]["Image"] == old["Config"]["Image"],
                  "rollback_original_tag_changed")
            same_security(old, restored)
        if service not in state["restored"]:
            state["restored"].append(service)
        write_journal(state)
    protected_unchanged(ref)
    state["phase"] = "restored_previous_images"
    write_journal(state)


def release():
    prepared = private_backup()
    image_pin()
    ref = snapshot()
    current_baseline(ref)
    protected_unchanged(ref)
    commands = plan_diff(ref, prepared)
    check(not JOURNAL.exists() and not JOURNAL.is_symlink(),
          "hotfix_journal_already_exists")
    staged_id = stage_image(ref[API], ref)
    # Fully rendered config (all existing layers, plus only the image overlay)
    # already compared before any runtime change.
    files = {}
    for service in ("team-api", "team-gateway"):
        path = BACKUP / (service + ".hotfix337.compose.json")
        data = json.dumps(overlay(service), sort_keys=True).encode()
        if path.exists():
            check(private_file(path).read_bytes() == data,
                  "overlay_changed")
        else:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        files[service] = path
    state = {
        "base": BASE, "source": SHA,
        "image_id": staged_id, "phase": "ready",
        "attempted": [], "restored": [],
        "workflow_changed": False, "migrations_executed": False,
        "baseline": {n: {"id": obj["Id"], "image": obj["Image"]}
                     for n, obj in ref.items()},
    }
    write_journal(state)
    try:
        for service, name, expected, api in (
            ("team-api", API, staged_id, True),
            ("team-gateway", GW, OFFICIAL_GW_ID, False),
        ):
            protected_unchanged(ref)
            if service == "team-api":
                current_baseline(ref)
            else:
                check(stable(ref[GW], docker(GW)), "gateway_baseline_changed")
            state["attempted"].append(service)
            state["phase"] = "updating_" + service.replace("-", "_")
            write_journal(state)
            compose_up(commands[service]["args"],
                       overlay_file=files[service], service=service)
            current = wait_for(name, expected, api=api)
            check(current["Config"]["Image"] ==
                  overlay(service)["services"][service]["image"],
                  "candidate_tag_changed")
            same_security(ref[name], current)
            protected_unchanged(ref)
        state["phase"] = "published_api_gateway_only"
        write_journal(state)
        return {
            "resultado": "IG212_HOTFIX337_API_GATEWAY_PUBLICADOS",
            "driver": "3.3.7",
            "api_saudavel": True,
            "gateway_publicado": True,
            "whatsapp_preservado": True,
            "n8n_alterado": False,
            "instagram_mensagens_reais_homologadas": False,
        }
    except Exception:
        state["phase"] = "recovery_required"
        write_journal(state)
        try:
            rollback(ref, commands, state)
        except Exception:
            state["phase"] = "manual_recovery_required"
            write_journal(state)
        raise


def recover():
    private_backup()
    state = json.loads(private_file(JOURNAL).read_text())
    check(state.get("base") == BASE and state.get("source") == SHA
          and state.get("workflow_changed") is False
          and state.get("migrations_executed") is False
          and state.get("phase") in (
              "ready", "updating_team_api", "updating_team_gateway",
              "published_api_gateway_only", "recovery_required",
              "manual_recovery_required", "restoring"),
          "journal_not_recoverable")
    ref = json.loads(private_file(
        BACKUP / "baseline-inspect.json").read_text())
    # The earlier baseline archive contains the immutable original Compose
    # labels, image and runtime security profile, even though the API's
    # container ID was changed during the previous (successful) rollback.
    # For a partially deployed hotfix, use that recorded baseline to
    # reconstruct the old service with force-recreate.
    check(ref[API].get("Image") == BASE_API_ID
          and ref[GW].get("Image") == BASE_GW_ID, "backup_baseline_invalid")
    for name in PROTECTED:
        check(stable(ref[name], docker(name)), "protected_runtime_changed")
    commands = plan_diff(ref, json.loads(private_file(PLAN).read_text()))
    rollback(ref, commands, state)
    return {"resultado": "IG212_HOTFIX337_ROLLBACK_CONCLUIDO",
            "whatsapp_preservado": True, "n8n_alterado": False}


def main():
    parser = argparse.ArgumentParser()
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--apply", action="store_true")
    options.add_argument("--rollback", action="store_true")
    parser.add_argument("--authorization")
    args = parser.parse_args()
    if not args.apply and not args.rollback:
        print(json.dumps({"resultado": "PREPARE_ONLY"}))
        return 0
    lock = None
    try:
        if args.apply:
            check(args.authorization == ALLOW, "hotfix_explicit_authorization_required")
        else:
            check(args.authorization == ALLOW_ROLLBACK, "rollback_authorization_required")
        check(os.geteuid() == 0, "root_required")
        lock = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = release() if args.apply else recover()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as err:
        code = str(err) if isinstance(err, Stop) and re.fullmatch(
            r"[a-z0-9_]+", str(err)
        ) else "operation_failed_details_redacted"
        phase = "not_started"
        if JOURNAL.exists() and JOURNAL.is_file():
            try:
                phase = json.loads(JOURNAL.read_text()).get("phase", "unknown")
            except Exception:
                phase = "unknown"
        print(json.dumps({
            "resultado": "BLOQUEADO", "motivo": code,
            "journal_fase": phase,
            "producao_pode_ter_sido_alterada": phase not in ("not_started", "ready"),
            "repetir_apply": False,
        }))
        return 2
    finally:
        if lock is not None:
            os.close(lock)


if __name__ == "__main__":
    raise SystemExit(main())
