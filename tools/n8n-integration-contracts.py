#!/usr/bin/env python3
"""Contratos estruturais sanitizados de workflows n8n relevantes ao corte SocialMEI.

GET em workflow salvo e versao publicada. Nao le dados de execucao, credenciais
ou mensagens; nao revela caminhos/URLs/parametros/prompts/tokens.
"""
import getpass
import json
import subprocess
import sys

SCRIPT = r"""
(async () => {
  let key = "";
  for await (const chunk of process.stdin) key += chunk.toString();
  if (!key.trim()) throw Error("no_auth");
  const origin = "http://127.0.0.1:5678/api/v1";
  const ids = [
    "LHlqroY2xzvpYAmD", "NFcJfjvpaUsjh1x1",
    "A0EcNxcRvfWnMwKI", "uNfLQ5ZJsLX9iu12",
    "I0LzS0yk4MTV8NPr", "TuvBHyIAK0k8VBlX",
    "BtvlHv4mt90tn70z", "WWzhvmdPh9LrpuYy",
    "dPWzzYxwzPjhPiZj", "rVFOLd96gRwhKUJR"
  ];
  const types = new Set([
    "webhook", "switch", "httpRequest", "agent", "lmChatGroq",
    "lmChatGoogleGemini", "memoryBufferWindow", "postgres", "code",
    "formTrigger", "form", "wait", "toolWorkflow", "executeWorkflow",
    "scheduleTrigger", "respondToWebhook", "manualTrigger", "set", "if",
    "googleSheets", "function", "functionItem", "merge", "noOp", "stopAndError",
    "splitInBatches", "executeWorkflowTrigger", "chatTrigger"
  ]);
  async function get(path, allowAbsent=false) {
    const res = await fetch(origin + path, {
      headers: {"X-N8N-API-KEY":key.trim()},
      signal: AbortSignal.timeout(15000)
    });
    if (!res.ok) {
      if (allowAbsent) return null;
      throw Error("api");
    }
    return res.json();
  }
  const type = n => {
    const name = String(n.type || "").split(".").pop();
    return types.has(name) ? name : "other";
  };
  function destination(value) {
    if (typeof value !== "string") return "none";
    const lower = value.toLowerCase();
    if (lower.includes("graph.instagram.com")) return "meta_instagram";
    if (lower.includes("graph.facebook.com")) return "meta_facebook";
    if (/\b(?:waha|sendtext)\b/.test(lower)) return "waha";
    if (lower.includes("/internal/instagram/")) return "socialmei_ig_internal";
    if (lower.includes("/internal/waha/") || lower.includes("/internal/whatsapp/"))
      return "socialmei_whatsapp_internal";
    if (lower.includes("/internal/message-enrichment/"))
      return "socialmei_analysis_internal";
    if (lower.includes("/api/v1/") || lower.includes("team-api"))
      return "socialmei_api_or_other";
    if (lower.includes("imgbb")) return "image_host";
    if (lower.includes("sheets.googleapis.com")) return "google_sheets";
    if (/^(https?:\/\/|=)/.test(lower)) return "other_or_dynamic";
    return "none";
  }
  const method = v =>
    ["GET","POST","PUT","PATCH","DELETE"].includes(String(v).toUpperCase())
    ? String(v).toUpperCase() : "other";
  const auth = v =>
    ["none","genericCredentialType","predefinedCredentialType"].includes(v)
    ? v : "other";
  const genericAuth = v =>
    ["httpBearerAuth","httpHeaderAuth","httpTemplatedCustomAuth",
     "httpBasicAuth","httpDigestAuth","httpQueryAuth","httpCustomAuth"].includes(v)
    ? v : "other_or_none";
  function graph(workflow) {
    if (!workflow || !Array.isArray(workflow.nodes)) return null;
    const names = new Map(workflow.nodes.map((n,i) => [n.name, i]));
    const nodes = workflow.nodes.map((n,i) => {
      const item = {index:i, type:type(n), disabled:n.disabled === true};
      if (type(n) === "webhook") {
        item.method = method(n.parameters?.httpMethod || "GET");
        item.response_mode = ["onReceived","responseNode","lastNode"].includes(n.parameters?.responseMode)
          ? n.parameters.responseMode : "default_or_other";
        item.path_present = !!n.parameters?.path;
      }
      if (type(n) === "httpRequest") {
        const p = n.parameters || {};
        item.method = method(p.method || "GET");
        item.destination = destination(p.url);
        item.auth = auth(p.authentication || "none");
        item.generic_auth = genericAuth(p.genericAuthType);
        item.credential_ref_count = Object.keys(n.credentials || {}).length;
        const hs = p.headerParameters?.parameters;
        item.auth_header_inline = Array.isArray(hs) && hs.some(h =>
          String(h.name || "").toLowerCase() === "authorization");
        item.bearer_literal = Array.isArray(hs) && hs.some(h =>
          String(h.name || "").toLowerCase() === "authorization" &&
          typeof h.value === "string" && /^Bearer\s+/i.test(h.value));
        item.body_format = p.specifyBody === "json" || p.contentType === "json"
          ? "json" : p.sendBody ? "configured_other" : "none";
      }
      if (type(n) === "postgres") {
        item.operation = ["executeQuery","insert","update","select","delete"].includes(n.parameters?.operation)
          ? n.parameters.operation : "other_or_none";
        item.credential_ref_count = Object.keys(n.credentials || {}).length;
      }
      if (type(n) === "formTrigger") item.form_present = true;
      return item;
    });
    const edges = [];
    for (const [from, kinds] of Object.entries(workflow.connections || {})) {
      if (!names.has(from) || !kinds || typeof kinds !== "object") continue;
      for (const [kind, groups] of Object.entries(kinds)) {
        if (!Array.isArray(groups)) continue;
        for (let branch=0; branch<groups.length;branch++) {
          for (const edge of groups[branch] || []) {
            if (names.has(edge.node)) edges.push({
              from:names.get(from),to:names.get(edge.node),
              port:["main","ai_languageModel","ai_memory","ai_tool"].includes(kind)
                ? kind : "other",branch
            });
          }
        }
      }
    }
    return {nodes, edges};
  }
  const results=[];
  for (const id of ids) {
    const saved = await get("/workflows/" + id + "?excludePinnedData=true", true);
    if (!saved) {results.push({id, status:"not_found"}); continue;}
    let published = null;
    if (saved.active && saved.activeVersionId) {
      published = await get("/workflows/" + id + "/versions/" +
        encodeURIComponent(saved.activeVersionId),true);
    }
    results.push({
      id,
      active:saved.active === true,
      different_versions:!!saved.activeVersionId &&
        saved.versionId !== saved.activeVersionId,
      saved:graph(saved),
      published:graph(published)
    });
  }
  console.log(JSON.stringify({ok:true, read_only:true, results}));
})().catch(() => console.log(JSON.stringify({ok:false})));
"""


def main():
    if sys.argv[1:] != ["--target", "team"]:
        raise SystemExit("Uso: python3 tools/n8n-integration-contracts.py --target team")
    key = getpass.getpass("Chave da API n8n (oculta): ")
    if not key.strip():
        raise SystemExit("Chave nao fornecida.")
    try:
        proc = subprocess.run(
            ["docker", "exec", "-i", "socialmei-n8n", "node", "-e", SCRIPT],
            input=key,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        if proc.returncode:
            raise ValueError("container")
        result = json.loads(proc.stdout)
        if result.get("ok") is not True or result.get("read_only") is not True:
            raise ValueError("api")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise SystemExit("Consulta indisponivel. Nenhum workflow foi alterado.") from None
    finally:
        key = ""


if __name__ == "__main__":
    main()
