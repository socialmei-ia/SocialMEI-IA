#!/usr/bin/env python3
"""Prepare a private, unreachable-legacy Instagram n8n candidate; no publish.

Uses the exact pinned #212 source helper inside a temporary n8n Node process.
The live workflow, n8n credentials, app env and WhatsApp are left unchanged.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path("/var/lib/socialmei-ig212-backups/ig212-c2edda7b5aec47af9eef53908592e3e3")
SOURCE = ROOT / "instagram212-n8n-export.private.json"
RELAY = ROOT / "instagram212-n8n-relay.private.env"
CANDIDATE = ROOT / "instagram212-workflow-candidate.private.json"
RECEIPT = ROOT / "instagram212-workflow-candidate-receipt.private.json"
N8N = "socialmei-n8n"
API = "socialmei-team-team-api-1"
WORKFLOW = "LHlqroY2xzvpYAmD"
PLACEHOLDER = "SOCIALMEI212_PENDING_NATIVE_CREDENTIAL"
EXPECTED_HELPER_BLOB = "7b075c269350b8374f6c97ba09691835fee81102"
HELPER = "// Offline preparation only. Never imports, publishes or executes a live workflow.\nimport { createHash } from \"node:crypto\";\nimport { readFile, writeFile } from \"node:fs/promises\";\nimport { pathToFileURL } from \"node:url\";\n\nexport const WORKFLOW = \"LHlqroY2xzvpYAmD\";\nexport const NAMES = {\n  prepare: \"SocialMEI preparar ingresso\",\n  persist: \"SocialMEI persistir antes da IA\",\n  validate: \"SocialMEI validar recibo\",\n  ack: \"SocialMEI confirmar persistencia\",\n  fail: \"SocialMEI recusar sem persistencia\",\n  resume: \"SocialMEI retomar fluxo existente\",\n};\nexport const PREPARE = `const items = $input.all();\nif (items.length !== 1) throw new Error('Ingresso requer um unico envelope.');\nconst input = items[0];\nconst signature = input.json.headers?.['x-hub-signature-256'];\nif (typeof signature !== 'string' || !/^sha256=[a-f0-9]{64}$/.test(signature)) throw new Error('Assinatura Meta ausente.');\nconst raw = await this.helpers.getBinaryDataBuffer(0, 'data');\nif (!raw.length || raw.length > 65536) throw new Error('Envelope fora do limite.');\nconst body = raw.toString('utf8');\nif (!Buffer.from(body, 'utf8').equals(raw)) throw new Error('UTF-8 invalido.');\nconst parsed = JSON.parse(body);\nif (!parsed || parsed.object !== 'instagram' || !Array.isArray(parsed.entry)) throw new Error('Envelope Instagram invalido.');\nconst timestamp = String(Math.floor(Date.now() / 1000));\nreturn [{json:{timestamp, meta_signature:signature}, binary:input.binary}];`;\n\nfunction edge(name) {\n  return { node: name, type: \"main\", index: 0 };\n}\n\nexport function prepare(\n  source,\n  { sourceSha, publishedVersion, apiOrigin, credentialId, webhookNodeId, resumeLegacy = false },\n) {\n  if (typeof resumeLegacy !== \"boolean\") throw new Error(\"Modo de retomada invalido.\");\n  if (typeof credentialId !== \"string\" || !/^[A-Za-z0-9_-]{1,128}$/.test(credentialId))\n    throw new Error(\"Credencial nativa de ingresso obrigatoria.\");\n  if (!/^[a-f0-9]{64}$/.test(sourceSha || \"\")) throw new Error(\"Hash de origem obrigatorio.\");\n  const origin = new URL(apiOrigin);\n  if (\n    origin.protocol !== \"https:\" ||\n    origin.origin !== apiOrigin ||\n    origin.username ||\n    origin.password\n  )\n    throw new Error(\"Origem HTTPS explicita obrigatoria.\");\n  if (source.id !== WORKFLOW || !publishedVersion || source.versionId !== publishedVersion)\n    throw new Error(\"Exporte a revisao publicada do workflow existente.\");\n  if (!Array.isArray(source.nodes) || !source.connections || typeof source.connections !== \"object\")\n    throw new Error(\"Grafo invalido.\");\n  const candidate = structuredClone(source);\n  const hooks = candidate.nodes\n    .filter((n) => n.type === \"n8n-nodes-base.webhook\" && n.parameters?.httpMethod === \"POST\")\n    .filter((n) => webhookNodeId === undefined || n.id === webhookNodeId);\n  if (hooks.length !== 1) throw new Error(\"Esperado um unico webhook POST.\");\n  const hook = hooks[0];\n  if (hook.parameters.multipleMethods || hook.parameters.options?.binaryData)\n    throw new Error(\"Modo do webhook requer revisao manual.\");\n  const old = candidate.connections[hook.name];\n  if (\n    !old ||\n    Object.keys(old).some((key) => key !== \"main\") ||\n    old.main?.length !== 1 ||\n    !old.main[0].length\n  )\n    throw new Error(\"Saida do webhook nao reconhecida.\");\n  const byName = new Map(candidate.nodes.map((node) => [node.name, node]));\n  if (\n    byName.size !== candidate.nodes.length ||\n    candidate.nodes.some((node) => Object.values(NAMES).includes(node.name))\n  )\n    throw new Error(\"Nomes duplicados ou preparacao ja aplicada.\");\n  const pending = old.main[0].map((target) => target.node),\n    seen = new Set();\n  while (pending.length) {\n    const name = pending.pop();\n    if (seen.has(name)) continue;\n    seen.add(name);\n    const node = byName.get(name);\n    if (!node || name === hook.name || node.type === \"n8n-nodes-base.respondToWebhook\")\n      throw new Error(\"Resposta ou ciclo no caminho legado requer revisao.\");\n    for (const output of candidate.connections[name]?.main || [])\n      for (const target of output) pending.push(target.node);\n  }\n  hook.parameters.responseMode = \"responseNode\";\n  hook.parameters.options = { ...hook.parameters.options, rawBody: true };\n  // Failures in preparation/signing also produce 503, never an early acknowledgement.\n  const make = (key, type, typeVersion, parameters, error = false) => ({\n    id: `socialmei-persist-${key}`,\n    name: NAMES[key],\n    type,\n    typeVersion,\n    position: [300, Object.keys(NAMES).indexOf(key) * 180],\n    parameters,\n    ...(error ? { onError: \"continueErrorOutput\", retryOnFail: false } : {}),\n  });\n  const prepared = `$('${NAMES.prepare}').first().json`;\n  const persisted = `$('${NAMES.persist}').first().json`;\n  const validate = `const receipt = $input.first().json;\nif (receipt.received !== true || typeof receipt.continue_automation !== 'boolean' || ['processed','duplicates','ignored'].some(key => !Number.isInteger(receipt[key]) || receipt[key] < 0 || receipt[key] > 1000)) throw new Error('Recibo de persistencia invalido.');\nif (receipt.continue_automation !== (receipt.processed > 0 && receipt.duplicates === 0 && receipt.ignored === 0)) throw new Error('Recibo de automacao divergente.');\nreturn $input.all();`;\n  const resume = `const receipt = ${persisted};\nif (receipt.continue_automation !== true || !Number.isInteger(receipt.processed) || receipt.processed < 1 || receipt.duplicates !== 0 || receipt.ignored !== 0) return [];\nreturn $(${JSON.stringify(hook.name)}).all().map(item => {\n  const restored = {...item};\n  if (item.binary) {\n    const {data: rawIngress, ...remaining} = item.binary;\n    if (Object.keys(remaining).length) restored.binary = remaining;\n    else delete restored.binary;\n  }\n  return restored;\n});`;\n  candidate.nodes.push(\n    make(\n      \"prepare\",\n      \"n8n-nodes-base.code\",\n      2,\n      { mode: \"runOnceForAllItems\", jsCode: PREPARE },\n      true,\n    ),\n    make(\n      \"persist\",\n      \"n8n-nodes-base.httpRequest\",\n      4.2,\n      {\n        authentication: \"genericCredentialType\",\n        genericAuthType: \"httpBearerAuth\",\n        method: \"POST\",\n        url: apiOrigin + \"/webhooks/instagram/n8n\",\n        sendHeaders: true,\n        headerParameters: {\n          parameters: [\n            { name: \"X-SocialMEI-Timestamp\", value: `={{ ${prepared}.timestamp }}` },\n            { name: \"X-Hub-Signature-256\", value: `={{ ${prepared}.meta_signature }}` },\n          ],\n        },\n        sendBody: true,\n        contentType: \"binaryData\",\n        inputDataFieldName: \"data\",\n        options: {\n          timeout: 10000,\n          redirect: { redirect: { followRedirects: false } },\n          response: { response: { responseFormat: \"json\", neverError: false } },\n        },\n      },\n      true,\n    ),\n    make(\"ack\", \"n8n-nodes-base.respondToWebhook\", 1.4, {\n      respondWith: \"text\",\n      responseBody: \"EVENT_RECEIVED\",\n      options: { responseCode: 200 },\n    }),\n    make(\n      \"validate\",\n      \"n8n-nodes-base.code\",\n      2,\n      { mode: \"runOnceForAllItems\", jsCode: validate },\n      true,\n    ),\n    make(\"fail\", \"n8n-nodes-base.respondToWebhook\", 1.4, {\n      respondWith: \"text\",\n      responseBody: \"INGRESS_UNAVAILABLE\",\n      options: { responseCode: 503 },\n    }),\n    make(\"resume\", \"n8n-nodes-base.code\", 2, { mode: \"runOnceForAllItems\", jsCode: resume }),\n  );\n  candidate.nodes.find((node) => node.name === NAMES.persist).credentials = {\n    httpBearerAuth: { id: credentialId, name: \"SocialMEI Instagram ingresso\" },\n  };\n  candidate.connections[hook.name] = { main: [[edge(NAMES.prepare)]] };\n  for (const [key, next] of [\n    [\"prepare\", \"persist\"],\n    [\"persist\", \"validate\"],\n    [\"validate\", \"ack\"],\n  ])\n    candidate.connections[NAMES[key]] = { main: [[edge(NAMES[next])], [edge(NAMES.fail)]] };\n  candidate.connections[NAMES.ack] = { main: resumeLegacy ? [[edge(NAMES.resume)]] : [[]] };\n  candidate.connections[NAMES.resume] = resumeLegacy ? old : { main: [[]] };\n  // Credentials, existing nodes/expressions and webhook identity remain in this PRIVATE file.\n  return {\n    target_workflow_id: WORKFLOW,\n    expected_published_version_id: publishedVersion,\n    source_sha256: sourceSha,\n    automatically_publish: false,\n    resume_legacy_automation: resumeLegacy,\n    candidate: {\n      name: candidate.name,\n      nodes: candidate.nodes,\n      connections: candidate.connections,\n      settings: candidate.settings || {},\n    },\n  };\n}\n\nexport async function main(args) {\n  const names = [\n    \"input\",\n    \"output\",\n    \"expected-sha256\",\n    \"published-version\",\n    \"api-origin\",\n    \"credential-id\",\n  ];\n  const options = {};\n  for (let i = 0; i < args.length; i += 2) {\n    const key = args[i]?.replace(/^--/, \"\");\n    if (\n      ![...names, \"webhook-node-id\", \"resume-legacy\"].includes(key) ||\n      !args[i + 1] ||\n      options[key]\n    )\n      throw new Error(\"Argumentos invalidos.\");\n    options[key] = args[i + 1];\n  }\n  if (names.some((name) => !options[name])) throw new Error(\"Argumentos obrigatorios ausentes.\");\n  if (\n    options[\"resume-legacy\"] !== undefined &&\n    ![\"true\", \"false\"].includes(options[\"resume-legacy\"])\n  )\n    throw new Error(\"Modo de retomada invalido.\");\n  const bytes = await readFile(options.input);\n  const hash = createHash(\"sha256\").update(bytes).digest(\"hex\");\n  if (hash !== options[\"expected-sha256\"]) throw new Error(\"Export diverge do hash aprovado.\");\n  const result = prepare(JSON.parse(bytes), {\n    sourceSha: hash,\n    publishedVersion: options[\"published-version\"],\n    apiOrigin: options[\"api-origin\"],\n    credentialId: options[\"credential-id\"],\n    webhookNodeId: options[\"webhook-node-id\"],\n    resumeLegacy: options[\"resume-legacy\"] === \"true\",\n  });\n  await writeFile(options.output, JSON.stringify(result, null, 2) + \"\\n\", {\n    flag: \"wx\",\n    mode: 0o600,\n  });\n  return { prepared: true, workflow_id: WORKFLOW, source_sha256: hash, production_changed: false };\n}\n\nif (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)\n  main(process.argv.slice(2))\n    .then((result) => console.log(JSON.stringify(result)))\n    .catch(() => {\n      console.error(\n        \"Preparacao recusada. Confira os argumentos e o export publicado privado; detalhes omitidos.\",\n      );\n      process.exitCode = 1;\n    });\n"
NAMES = {
    "prepare": "SocialMEI preparar ingresso",
    "persist": "SocialMEI persistir antes da IA",
    "validate": "SocialMEI validar recibo",
    "ack": "SocialMEI confirmar persistencia",
    "fail": "SocialMEI recusar sem persistencia",
    "resume": "SocialMEI retomar fluxo existente",
}


class Stop(Exception):
    pass


def require(condition, code):
    if not condition:
        raise Stop(code)


def call(args, data=None, timeout=70):
    try:
        p = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("node_execution_unavailable") from None
    require(p.returncode == 0, "node_candidate_failed")
    return p.stdout


def private_file(path):
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_uid == 0
            and stat.S_IMODE(path.stat().st_mode) == 0o600,
            "private_input_changed")
    return path


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_once(path, payload):
    require(path.parent == ROOT and ROOT.is_dir() and not ROOT.is_symlink(),
            "invalid_private_target")
    if path.exists() or path.is_symlink():
        require(private_file(path).read_bytes() == payload,
                "candidate_already_changed")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(payload)
        out.flush()
        os.fsync(out.fileno())


def helper_identity():
    raw = HELPER.encode("utf-8")
    check = hashlib.sha1(
        ("blob " + str(len(raw)) + "\x00").encode() + raw).hexdigest()
    require(check == EXPECTED_HELPER_BLOB, "official_helper_changed")
    return raw


def origin():
    item = json.loads(call([
        "docker", "inspect", "--type", "container", API
    ], timeout=25))[0]
    require(item.get("State", {}).get("Health", {}).get("Status") == "healthy",
            "api_unhealthy")
    env = dict(x.split("=", 1) for x in item["Config"]["Env"] if "=" in x)
    host = env.get("SOCIALMEI_AUTH_ORIGIN", "")
    require(re.fullmatch(r"https://[A-Za-z0-9.-]{4,253}(?::443)?", host),
            "api_origin_invalid")
    require(env.get("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED", "false") == "false"
            and env.get("SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED", "false") == "false"
            and env.get("SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED", "false") == "false",
            "provider_already_activated")
    return host


def exported_workflow(raw):
    item = json.loads(raw)
    if isinstance(item, list):
        require(len(item) == 1, "export_item_count")
        item = item[0]
    require(isinstance(item, dict) and item.get("id") == WORKFLOW
            and item.get("active") is True and
            isinstance(item.get("nodes"), list) and
            len(item["nodes"]) == 17 and
            isinstance(item.get("connections"), dict),
            "workflow_export_not_expected")
    # Important: n8n 2.x drafts and published versions may be different.
    # Never overwrite the working workflow using a saved-but-unpublished draft.
    published = item.get("activeVersionId") or item.get("publishedVersionId")
    require(isinstance(published, str) and
            published and published == item.get("versionId"),
            "workflow_published_version_not_equal_saved")
    hooks = [n for n in item["nodes"]
             if n.get("type") == "n8n-nodes-base.webhook"
             and n.get("parameters", {}).get("httpMethod") == "POST"]
    require(len(hooks) == 1 and isinstance(hooks[0].get("id"), str),
            "workflow_webhook_not_unique")
    return item, published, hooks[0]["id"]


NODE_SCRIPT = r"""
const b64 = process.argv[1];
const mod = await import('data:text/javascript;base64,' + b64);
let chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const inp = JSON.parse(Buffer.concat(chunks).toString('utf8'));
const out = mod.prepare(inp.source, {
  sourceSha: inp.sourceSha,
  publishedVersion: inp.publishedVersion,
  apiOrigin: inp.apiOrigin,
  credentialId: inp.credentialId,
  webhookNodeId: inp.webhookNodeId,
  resumeLegacy: false,
});
process.stdout.write(JSON.stringify(out));
"""


def generate(raw, workflow, published, hook_id, api_origin):
    # No secrets are included in command arguments. Exported workflow is
    # delivered by stdin and returned solely to a root-private host file.
    import base64
    js = base64.b64encode(helper_identity()).decode("ascii")
    payload = {
        "source": workflow,
        "sourceSha": hash_bytes(raw),
        "publishedVersion": published,
        "webhookNodeId": hook_id,
        "apiOrigin": api_origin,
        "credentialId": PLACEHOLDER,
    }
    output = call([
        "docker", "exec", "-i", N8N,
        "node", "--input-type=module", "-e", NODE_SCRIPT, js
    ], data=json.dumps(payload).encode("utf-8"), timeout=90)
    require(len(output) <= 1000000, "candidate_too_large")
    candidate = json.loads(output)
    validate_candidate(workflow, candidate)
    return output, candidate


def reachable(graph, start):
    seen = set()
    queue = [start]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        for branch in (graph.get(name, {}).get("main") or []):
            for edge in branch:
                queue.append(edge["node"])
    return seen


def validate_candidate(original, prepared):
    target = prepared.get("candidate")
    require(prepared.get("target_workflow_id") == WORKFLOW and
            prepared.get("automatically_publish") is False and
            prepared.get("resume_legacy_automation") is False and
            isinstance(target, dict), "unsafe_candidate_metadata")
    before_nodes = original["nodes"]
    after_nodes = target.get("nodes")
    require(isinstance(after_nodes, list) and
            len(after_nodes) == len(before_nodes) + len(NAMES) and
            len(after_nodes) == 23, "candidate_nodes_changed")
    old_names = {n["name"] for n in before_nodes}
    require(len(old_names) == len(before_nodes), "duplicate_existing_nodes")
    new_names = {n["name"] for n in after_nodes}
    require(len(new_names) == len(after_nodes) and
            new_names == old_names | set(NAMES.values()),
            "candidate_node_scope_changed")
    by_name = {n["name"]: n for n in after_nodes}
    hook = next(n for n in before_nodes
                if n.get("type") == "n8n-nodes-base.webhook"
                and n.get("parameters", {}).get("httpMethod") == "POST")
    for n in before_nodes:
        updated = by_name[n["name"]]
        if n["name"] != hook["name"]:
            require(updated == n, "legacy_node_modified")
        else:
            require(updated.get("id") == n.get("id") and
                    updated["parameters"]["responseMode"] == "responseNode"
                    and updated["parameters"]["options"]["rawBody"] is True,
                    "webhook_parameters_unexpected")
    reach = reachable(target["connections"], hook["name"])
    expected_reach = {hook["name"], NAMES["prepare"], NAMES["persist"],
                      NAMES["validate"], NAMES["ack"], NAMES["fail"]}
    require(reach == expected_reach,
            "legacy_automation_still_reachable")
    credential = by_name[NAMES["persist"]].get("credentials", {}).get(
        "httpBearerAuth", {})
    require(credential.get("id") == PLACEHOLDER,
            "native_credential_placeholder_changed")
    require(target.get("settings", {}) == original.get("settings", {}),
            "original_settings_changed")
    # Nodes/other expressions of original workflow were preserved intact.
    # The published workflow is unchanged until distinct authorized activation.


def prepare():
    require(os.geteuid() == 0 and ROOT.is_dir() and not ROOT.is_symlink()
            and ROOT.stat().st_uid == 0 and
            stat.S_IMODE(ROOT.stat().st_mode) == 0o700,
            "private_folder_invalid")
    require(private_file(RELAY).stat().st_size > 100,
            "relay_settings_missing")
    source_bytes = private_file(SOURCE).read_bytes()
    source, published, hook_id = exported_workflow(source_bytes)
    body, generated = generate(
        source_bytes, source, published, hook_id, origin()
    )
    # This is only a private candidate. The placeholder must be replaced
    # by a real n8n native Bearer credential before any publish operation.
    write_once(CANDIDATE, body)
    receipt = {
        "source_sha256": hash_bytes(source_bytes),
        "candidate_sha256": hash_bytes(body),
        "official_helper_blob": EXPECTED_HELPER_BLOB,
        "source_version": published,
        "workflow_id": WORKFLOW,
        "nodes_before": 17, "nodes_proposed": 23,
        "resume_legacy": False, "credential_placeholder": True,
        "published": False, "production_changed": False,
    }
    write_once(RECEIPT, (json.dumps(
        receipt, sort_keys=True, indent=2) + "\n").encode())
    return {
        "resultado": "INSTAGRAM_212_WORKFLOW_RECEIVE_ONLY_PREPARADO",
        "nos_atual": 17, "nos_propostos": 23,
        "webhook_raw_body": True,
        "ia_antiga_alcancavel": False,
        "credencial_n8n_a_criar": True,
        "workflow_publicado": False,
        "whatsapp_alterado": False,
        "api_reiniciada": False,
    }


def main():
    try:
        print(json.dumps(prepare(), ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, Stop) and re.fullmatch(
            r"[a-z_]+", str(error)
        ) else "preparacao_incompleta"
        print(json.dumps({
            "resultado": "BLOQUEADO",
            "motivo": code,
            "workflow_publicado": False,
            "producao_alterada": False,
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
