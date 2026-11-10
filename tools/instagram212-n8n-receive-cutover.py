#!/usr/bin/env python3
"""Controlled receive-only activation of Instagram 212. No AI or outbound sends.

Run on AWS as root, with a console/PTY to enter the n8n API key privately.
The operator cannot change WhatsApp, n8n stacks or Meta subscriptions.
A private journal records staged credential, workflow draft and publication.
"""
import argparse
import copy
from getpass import getpass
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

B = Path("/var/lib/socialmei-ig212-backups/ig212-c2edda7b5aec47af9eef53908592e3e3")
ROOT = Path("/home/ubuntu/socialmei-team")
SOURCE = B / "instagram212-n8n-export.private.json"
PREPARED = B / "instagram212-workflow-candidate.private.json"
RECEIPT = B / "instagram212-workflow-candidate-receipt.private.json"
STAGED = B / "instagram212-n8n-relay.private.env"
PLAN = B / "hotfix337-publication.private.json"
JOURNAL = B / "instagram212-receive-cutover.private.json"
OVERLAY = B / "instagram212-receive-only.compose.json"
LOCK = Path("/run/lock/socialmei-wa-pilot-release.lock")
API = "socialmei-team-team-api-1"
GW = "socialmei-team-team-gateway-1"
N8N = "socialmei-n8n"
WID = "LHlqroY2xzvpYAmD"
IMAGE = "socialmei-v33/team-api:345a074310673640084c7634e3da75dd72491813-psycopg337"
GW_IMAGE = "socialmei-v33/team-gateway:345a074310673640084c7634e3da75dd72491813"
AUTH = "AUTORIZO-IG212-RECEBIMENTO-N8N-SEM-IA"
PROTECT = (
    "socialmei-team-team-postgres-1",
    "socialmei-waha", "socialmei-menu-worker-continuo",
    "socialmei-waha-gows-piloto", "socialmei-n8n",
)
NAMES = {
    "prepare": "SocialMEI preparar ingresso",
    "persist": "SocialMEI persistir antes da IA",
    "validate": "SocialMEI validar recibo",
    "ack": "SocialMEI confirmar persistencia",
    "fail": "SocialMEI recusar sem persistencia",
    "resume": "SocialMEI retomar fluxo existente",
}


class Block(Exception):
    pass


def verify(ok, code):
    if not ok:
        raise Block(code)


def call(cmd, data=None, timeout=90):
    try:
        p = subprocess.run(cmd, input=data, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout, cwd=ROOT)
    except (OSError, subprocess.TimeoutExpired):
        raise Block("command_timeout_or_missing") from None
    verify(p.returncode == 0, "operation_failed")
    return p.stdout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def private(path):
    verify(path.is_file() and not path.is_symlink()
           and path.stat().st_uid == 0
           and stat.S_IMODE(path.stat().st_mode) == 0o600,
           "private_file_unavailable")
    return path


def obj(path):
    return json.loads(private(path).read_text())


def atomic(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    fd, temp = tempfile.mkstemp(prefix=".receive212-", dir=B)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def inspect(name):
    result = json.loads(call(["docker", "inspect", "--type=container", name], timeout=25))
    verify(isinstance(result, list) and len(result) == 1, "container_unavailable")
    return result[0]


def stable(x, y):
    return (x.get("Id") == y.get("Id")
            and x.get("Image") == y.get("Image")
            and x.get("RestartCount") == y.get("RestartCount")
            and x.get("State", {}).get("StartedAt") == y.get("State", {}).get("StartedAt")
            and x.get("State", {}).get("Running") == y.get("State", {}).get("Running"))


def protected(base):
    for name in PROTECT:
        verify(stable(base[name], inspect(name)), "protected_service_changed")


def private_environment():
    env = {}
    for line in private(STAGED).read_text().splitlines():
        key, eq, value = line.partition("=")
        verify(bool(eq) and re.fullmatch(r"[A-Z0-9_]+", key)
               and value.startswith("'") and value.endswith("'"),
               "stage_environment_invalid")
        verify(key not in env, "duplicate_staged_key")
        env[key] = value[1:-1]
    allowed = {"SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED",
               "SOCIALMEI_INSTAGRAM_N8N_AUTH_MODE",
               "SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY",
               "SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET",
               "SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS"}
    verify(set(env) == allowed and
           env["SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED"] == "true" and
           env["SOCIALMEI_INSTAGRAM_N8N_AUTH_MODE"] == "header" and
           32 <= len(env["SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY"]) <= 256 and
           32 <= len(env["SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET"]) <= 256,
           "stage_environment_incomplete")
    binds = json.loads(env["SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS"])
    verify(isinstance(binds, dict) and 1 <= len(binds) <= 2
           and all(re.fullmatch(r"[0-9]{1,40}", k) for k in binds),
           "account_bindings_invalid")
    return env


def graph_reachable(graph, start):
    found, stack = set(), [start]
    while stack:
        name = stack.pop()
        if name in found:
            continue
        found.add(name)
        for output in graph.get(name, {}).get("main", []):
            for edge in output:
                stack.append(edge["node"])
    return found


def candidate():
    raw = private(SOURCE).read_bytes()
    before = json.loads(raw)
    if isinstance(before, list):
        verify(len(before) == 1, "source_shape_invalid")
        before = before[0]
    package = obj(PREPARED)
    r = obj(RECEIPT)
    after = package.get("candidate")
    verify(before.get("id") == WID and
           before.get("active") is True and
           isinstance(before.get("activeVersionId"), str) and
           before["activeVersionId"] == before.get("versionId"),
           "published_version_not_pinned")
    verify(r.get("source_sha256") == sha(raw) and
           r.get("candidate_sha256") == sha(private(PREPARED).read_bytes()) and
           r.get("source_version") == before["versionId"] and
           r.get("workflow_id") == WID and
           r.get("credential_placeholder") is True and
           r.get("published") is False and
           r.get("resume_legacy") is False and
           package.get("resume_legacy_automation") is False and
           package.get("automatically_publish") is False,
           "candidate_receipt_invalid")
    verify(isinstance(after, dict) and
           len(after.get("nodes", [])) == 23 and
           len(before.get("nodes", [])) == 17,
           "candidate_nodes_unexpected")
    originals = {x["name"]: x for x in before["nodes"]}
    planned = {x["name"]: x for x in after["nodes"]}
    verify(len(originals) == 17 and len(planned) == 23 and
           set(planned) == set(originals) | set(NAMES.values()),
           "candidate_node_scope_changed")
    for name in originals:
        if originals[name]["type"] != "n8n-nodes-base.webhook":
            verify(planned[name] == originals[name], "legacy_node_modified")
    hook = next(x for x in before["nodes"] if
                x["type"] == "n8n-nodes-base.webhook" and
                x.get("parameters", {}).get("httpMethod") == "POST")
    verify(planned[hook["name"]].get("id") == hook.get("id")
           and planned[hook["name"]]["parameters"].get("responseMode") == "responseNode"
           and planned[hook["name"]]["parameters"].get("options", {}).get("rawBody") is True,
           "webhook_receiving_shape_changed")
    expected = {hook["name"], NAMES["prepare"], NAMES["persist"],
                NAMES["validate"], NAMES["ack"], NAMES["fail"]}
    verify(graph_reachable(after["connections"], hook["name"]) == expected,
           "old_automation_reachable")
    verify(after.get("settings", {}) == before.get("settings", {}),
           "workflow_settings_changed")
    return before, after


def check_oauth_scopes(relay):
    # Read-only database proof before creating a credential or modifying n8n.
    code = """import json
from database import connect
with connect() as conn:
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL statement_timeout = '4s'")
    rows = conn.execute("SELECT external_account_id,workspace_id FROM socialmei.ig_meta_connections WHERE status='connected' AND expires_at>NOW() AND scopes @> ARRAY['instagram_business_basic','instagram_business_manage_messages']::text[]").fetchall()
    print(json.dumps({str(account): workspace for account,workspace in rows}))
"""
    # Python string compile on the actual container; no SQL or token output
    # goes to the terminal. Neither user nor chat sees OAuth account IDs.
    r = call(["docker", "exec", API, "python", "-B", "-c", code], timeout=20)
    try:
        current = json.loads(r)
        expected = json.loads(relay["SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS"])
        verify(isinstance(current, dict) and set(current) == set(expected) and
               all(current.get(k) == v["workspace_id"] and
                   k == v["connection_account_id"] for k,v in expected.items()),
               "oauth_scopes_or_bindings_not_ready")
    except (ValueError, TypeError, KeyError):
        raise Block("oauth_scopes_or_bindings_not_ready") from None


def compose_args(api):
    labels = api.get("Config", {}).get("Labels") or {}
    verify(labels.get("com.docker.compose.project") == "socialmei-team" and
           Path(labels.get("com.docker.compose.project.working_dir", "")) == ROOT,
           "compose_runtime_changed")
    paths = [Path(x) for x in labels.get(
        "com.docker.compose.project.config_files", "").split(",") if x]
    verify(len(paths) == 17 and all(
        p.is_absolute() and p.is_file() and not p.is_symlink() and p.resolve() == p
        for p in paths), "compose_layers_changed")
    args = ["docker", "compose", "-p", "socialmei-team",
            "--env-file", str(ROOT / ".env.team")]
    for p in paths:
        args += ["-f", str(p)]
    return args


def model(args, extra=None):
    cmd = list(args)
    if extra is not None:
        cmd += ["-f", "-"]
    cmd += ["config", "--format", "json"]
    return json.loads(call(cmd, data=json.dumps(extra).encode() if extra is not None else None,
                           timeout=90))


def ensure_compose(base, additions):
    args = compose_args(base)
    before = model(args)
    verify(before["services"]["team-api"]["image"] == IMAGE and
           base.get("Config", {}).get("Image") == IMAGE,
           "api_image_not_expected")
    runtime = dict(x.split("=", 1) for x in base["Config"]["Env"] if "=" in x)
    verify(runtime.get("SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED", "false") != "true"
           and runtime.get("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED", "false") == "false"
           and runtime.get("SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED", "false") == "false",
           "ingress_or_sender_already_enabled")
    import copy
    overlay = {"services": {"team-api": {"environment": additions}}}
    after = model(args, overlay)
    expected = copy.deepcopy(before)
    for k, v in additions.items():
        expected["services"]["team-api"].setdefault("environment", {})[k] = v
    verify(after == expected, "compose_changes_out_of_scope")
    verify(not OVERLAY.exists() and not OVERLAY.is_symlink(),
           "activation_overlay_already_exists")
    return args, overlay


API_JS = r"""
(async () => {
  let chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  const inp = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  const allowed = new Set([
    'GET /workflows/' + inp.id,
    'POST /credentials',
    'PUT /workflows/' + inp.id,
    'POST /workflows/' + inp.id + '/activate',
  ]);
  if (!allowed.has(inp.method + ' ' + inp.path)) {
    process.stdout.write(JSON.stringify({ok:false,code:'path_not_allowed'}));
    return;
  }
  try {
    const resp = await fetch('http://127.0.0.1:5678/api/v1' + inp.path, {
      method: inp.method,
      headers: {'X-N8N-API-KEY': inp.key,
                'Content-Type': 'application/json', 'Accept': 'application/json'},
      body: inp.method === 'GET' ? undefined : JSON.stringify(inp.body || {}),
      signal: AbortSignal.timeout(20000),
    });
    const body = await resp.json().catch(() => null);
    process.stdout.write(JSON.stringify({ok:resp.ok,status:resp.status,body}));
  } catch (_) {
    process.stdout.write(JSON.stringify({ok:false,code:'n8n_request_unavailable'}));
  }
})();
"""


def n8n(key, method, path, body=None, *, required=True):
    verify(re.fullmatch(r"/(?:workflows/" + re.escape(WID) +
           r"(?:/activate)?|credentials)", path),
           "n8n_api_path_out_of_scope")
    raw = call([
        "docker", "exec", "-i", N8N, "node", "-e", API_JS
    ], data=json.dumps({
        "key": key, "method": method, "path": path,
        "body": body, "id": WID,
    }, separators=(",", ":")).encode(), timeout=50)
    response = json.loads(raw)
    if required:
        verify(response.get("ok") is True, "n8n_api_operation_rejected")
    return response


def public_status(value):
    verify(isinstance(value, dict) and value.get("id") == WID
           and isinstance(value.get("versionId"), str)
           and isinstance(value.get("nodes"), list)
           and isinstance(value.get("connections"), dict),
           "n8n_workflow_metadata_unexpected")
    return value


def validate_current(current, original):
    current = public_status(current)
    verify(current.get("active") is True
           and current.get("activeVersionId") == original.get("activeVersionId")
           and current["versionId"] == original["versionId"],
           "n8n_published_version_changed")
    # API and CLI exports can contain extra metadata; compare all original
    # trigger/connection identities while rejecting silent edits.
    orig = {n["id"]: n for n in original["nodes"]}
    observed = {n["id"]: n for n in current["nodes"]}
    verify(set(orig) == set(observed) and
           all(orig[x] == observed[x] for x in orig) and
           current["connections"] == original["connections"],
           "workflow_external_changes_detected")
    return current


def check_production(previous):
    a = inspect(API)
    g = inspect(GW)
    verify(a.get("State", {}).get("Health", {}).get("Status") == "healthy"
           and a.get("Config", {}).get("Image") == IMAGE
           and g.get("Config", {}).get("Image") == GW_IMAGE,
           "runtime_precondition_changed")
    verify(stable(previous[GW], g), "gateway_changed")
    protected(previous)
    return a


def wait_api():
    for _ in range(40):
        a = inspect(API)
        if a.get("Config", {}).get("Image") == IMAGE:
            health = a.get("State", {}).get("Health", {}).get("Status")
            if health == "healthy" and a["State"].get("Running") is True:
                return a
            verify(health in ("starting", "healthy"), "new_api_unhealthy")
        time.sleep(2)
    raise Block("new_api_health_timeout")


def same_security(old, new):
    for key in ("Privileged", "CapAdd", "CapDrop", "SecurityOpt",
                "NetworkMode", "PortBindings", "Binds",
                "ReadonlyRootfs", "Devices", "RestartPolicy"):
        verify(old["HostConfig"].get(key) == new["HostConfig"].get(key),
               "runtime_security_changed")
    def mounts(x):
        return sorted((m.get("Type"), m.get("Source"),
                       m.get("Destination"), m.get("RW"))
                      for m in x.get("Mounts", []))
    verify(mounts(old) == mounts(new), "mounts_changed")


def write_overlay(overlay):
    data = (json.dumps(overlay, sort_keys=True) + "\n").encode()
    fd = os.open(OVERLAY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def compare_response_status(api):
    # Authentication is enforced before Meta payload parsing. This probe
    # cannot persist an event because it includes no Meta signature/body.
    # Reach the temporary network namespace using the candidate image,
    # without creating a second API with production credentials.
    p = subprocess.run([
        "docker", "exec", API, "python", "-B", "-c",
        ("import urllib.request,urllib.error;"
         "req=urllib.request.Request('http://127.0.0.1:8000/webhooks/instagram/n8n',"
         "data=b'{}',headers={'Content-Type':'application/json'},method='POST');"
         "\ntry: urllib.request.urlopen(req,timeout=5); print('UNEXPECTED')"
         "\nexcept urllib.error.HTTPError as e: print(e.code)")
    ], capture_output=True, timeout=15)
    verify(p.returncode == 0 and p.stdout.strip() == b"403",
           "relay_auth_guard_not_active")


def rollback_api(before, args):
    current = inspect(API)
    if stable(before, current):
        return
    call(args + ["up", "-d", "--force-recreate", "--no-deps",
                 "--no-build", "--pull", "never", "team-api"], timeout=210)
    current = wait_api()
    verify(current.get("Config", {}).get("Env") == before.get("Config", {}).get("Env")
           and current["Config"]["Image"] == before["Config"]["Image"],
           "api_rollback_configuration_changed")
    same_security(before, current)


def stage_credential(key, relay, state):
    # Create credential *only after* checking ownership of the workflow and
    # no conflicting activation journal. Its plaintext never goes to logs.
    payload = {
        "name": "SocialMEI Instagram ingresso 212",
        "type": "httpBearerAuth",
        "data": {"token": relay["SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY"]},
    }
    response = n8n(key, "POST", "/credentials", payload)["body"]
    verify(isinstance(response, dict) and
           re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(response.get("id", ""))),
           "n8n_credential_create_unconfirmed")
    state["credential_id"] = response["id"]
    state["phase"] = "credential_created"
    atomic(JOURNAL, state)
    return response["id"]


def patch_candidate(after, credential_id):
    plan = copy.deepcopy(after)
    node = next(n for n in plan["nodes"] if n["name"] == NAMES["persist"])
    verify(node["type"] == "n8n-nodes-base.httpRequest"
           and node["credentials"]["httpBearerAuth"]["id"] ==
           "SOCIALMEI212_PENDING_NATIVE_CREDENTIAL",
           "placeholder_credential_not_expected")
    node["credentials"]["httpBearerAuth"]["id"] = credential_id
    node["credentials"]["httpBearerAuth"]["name"] = "SocialMEI Instagram ingresso 212"
    headers = node["parameters"].get("headerParameters", {}).get("parameters", [])
    verify(not any(x.get("name", "").lower() == "content-type" for x in headers),
           "relay_headers_unexpected")
    # Backend accepts only application/json; raw bytes still go as binaryData.
    headers.append({"name": "Content-Type", "value": "application/json"})
    return {"name": plan["name"], "nodes": plan["nodes"],
            "connections": plan["connections"], "settings": plan["settings"]}


def rollback_workflow(key, state):
    before = state.get("old_version_id")
    if not before or not state.get("draft_written"):
        return
    now = n8n(key, "GET", "/workflows/" + WID, required=False)
    if not now.get("ok"):
        state["workflow_recovery"] = "manual"
        atomic(JOURNAL, state)
        return
    current = now.get("body", {})
    if current.get("activeVersionId") == before:
        state["workflow_recovery"] = "old_published_unchanged"
        atomic(JOURNAL, state)
        return
    if current.get("activeVersionId") == state.get("new_version_id"):
        response = n8n(key, "POST", "/workflows/" + WID + "/activate",
                       {"versionId": before}, required=False)
        if response.get("ok") is True:
            state["workflow_recovery"] = "old_version_republished"
            atomic(JOURNAL, state)
            return
    state["workflow_recovery"] = "manual"
    atomic(JOURNAL, state)


def activate(key):
    verify(os.geteuid() == 0
           and B.is_dir() and not B.is_symlink()
           and B.stat().st_uid == 0
           and stat.S_IMODE(B.stat().st_mode) == 0o700,
           "private_backup_unavailable")
    verify(bool(re.fullmatch(r"[A-Za-z0-9_.\-]{32,4096}", key or "")),
           "n8n_api_key_required")
    verify(not JOURNAL.exists() and not JOURNAL.is_symlink(),
           "cutover_journal_already_exists")
    hotfix = obj(PLAN)
    verify(hotfix.get("phase") == "published_api_gateway_only",
           "api_gateway_hotfix_not_confirmed")
    old, after = candidate()
    relay = private_environment()
    check_oauth_scopes(relay)
    base = {n: inspect(n) for n in (API, GW) + PROTECT}
    check_production(base)
    args, overlay = ensure_compose(base[API], relay)
    live = n8n(key, "GET", "/workflows/" + WID)["body"]
    validate_current(live, old)
    state = {
        "phase": "preparing",
        "source": "345a074310673640084c7634e3da75dd72491813",
        "old_version_id": old["versionId"],
        "new_version_id": None,
        "draft_written": False,
        "credential_id": None,
        "api_changed": False,
        "n8n_published": False,
        "whatsapp_changed": False,
    }
    atomic(JOURNAL, state)
    try:
        credential_id = stage_credential(key, relay, state)
        planned = patch_candidate(after, credential_id)
        update = n8n(key, "PUT", "/workflows/" + WID, planned)["body"]
        verify(isinstance(update, dict) and
               isinstance(update.get("versionId"), str) and
               update.get("id") == WID,
               "n8n_draft_update_unconfirmed")
        state["new_version_id"] = update["versionId"]
        state["draft_written"] = True
        state["phase"] = "draft_saved_not_published"
        atomic(JOURNAL, state)
        verify(update.get("activeVersionId") == old["versionId"],
               "n8n_unexpected_early_publish")
        protected(base)
        verify(stable(base[API], inspect(API)), "api_changed_before_cutover")
        write_overlay(overlay)
        state["phase"] = "updating_api_config"
        atomic(JOURNAL, state)
        call(args + ["-f", str(OVERLAY), "up", "-d",
                     "--no-deps", "--no-build", "--pull",
                     "never", "team-api"], timeout=210)
        new_api = wait_api()
        state["api_changed"] = True
        state["phase"] = "api_receiver_ready"
        atomic(JOURNAL, state)
        same_security(base[API], new_api)
        protected(base)
        compare_response_status(new_api)
        before_publish = public_status(
            n8n(key, "GET", "/workflows/" + WID)["body"])
        verify(before_publish["activeVersionId"] == old["versionId"]
               and before_publish["versionId"] == state["new_version_id"],
               "n8n_draft_changed_before_publish")
        state["phase"] = "publishing_receive_only"
        atomic(JOURNAL, state)
        result = n8n(key, "POST", "/workflows/" + WID + "/activate",
                     {"versionId": state["new_version_id"]})["body"]
        verify(isinstance(result, dict), "publication_response_invalid")
        # Publishing is async: require observed activeVersionId to match the
        # newly authorized draft before claiming success.
        observed = None
        for i in range(16):
            observed = public_status(n8n(
                key, "GET", "/workflows/" + WID)["body"])
            if observed["activeVersionId"] == state["new_version_id"] and observed.get("active") is True:
                break
            time.sleep(2)
        verify(observed is not None and
               observed.get("activeVersionId") == state["new_version_id"]
               and observed.get("active") is True,
               "workflow_published_version_not_confirmed")
        protected(base)
        verify(inspect(API).get("State", {}).get("Health", {}).get("Status") == "healthy",
               "api_became_unhealthy")
        state["n8n_published"] = True
        state["phase"] = "receive_only_published"
        atomic(JOURNAL, state)
        return {
            "resultado": "INSTAGRAM_212_RECEBIMENTO_PUBLICADO",
            "n8n_23_nos": True,
            "ingresso_api_saudavel": True,
            "reenvio_antigo_ia": False,
            "whatsapp_preservado": True,
            "meta_mensagem_real_confirmada": False,
            "proximo_passo": "enviar_mensagem_real_instagram_para_caixa",
        }
    except Exception:
        state["phase"] = "recovery_required"
        atomic(JOURNAL, state)
        try:
            rollback_workflow(key, state)
        except Exception:
            state["workflow_recovery"] = "manual"
            atomic(JOURNAL, state)
        try:
            rollback_api(base[API], args)
            state["api_recovery"] = "healthy_previous"
        except Exception:
            state["api_recovery"] = "manual"
        try:
            protected(base)
        except Exception:
            state["protected_services_recovery"] = "manual"
        state["phase"] = ("restored_previous_runtime" if
                          state.get("api_recovery") == "healthy_previous" and
                          state.get("workflow_recovery") in (
                              "old_published_unchanged", "old_version_republished")
                          else "manual_recovery_required")
        atomic(JOURNAL, state)
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--authorization", required=True)
    args = p.parse_args()
    lock_fd = None
    try:
        verify(args.authorization == AUTH, "explicit_receive_only_authorization_required")
        verify(os.geteuid() == 0, "root_required")
        lock_fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        key = getpass("Chave API n8n (oculta, não cole no chat): ").strip()
        result = activate(key)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        reason = str(error) if isinstance(error, Block) and re.fullmatch(
            r"[a-z0-9_]+", str(error)) else "operation_failed_details_redacted"
        phase = "not_started"
        if JOURNAL.is_file() and not JOURNAL.is_symlink():
            try:
                phase = obj(JOURNAL).get("phase", "unknown")
            except Exception:
                phase = "unknown"
        print(json.dumps({
            "resultado": "BLOQUEADO", "motivo": reason,
            "journal_fase": phase, "nao_repetir_automaticamente": True,
        }, ensure_ascii=False))
        return 2
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
