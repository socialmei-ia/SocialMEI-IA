// Offline preparation only. Never imports, publishes or executes a live workflow.
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

export const WORKFLOW = "LHlqroY2xzvpYAmD";
export const NAMES = {
  prepare: "SocialMEI preparar ingresso",
  sign: "SocialMEI assinar ingresso",
  persist: "SocialMEI persistir antes da IA",
  validate: "SocialMEI validar recibo",
  ack: "SocialMEI confirmar persistencia",
  fail: "SocialMEI recusar sem persistencia",
  resume: "SocialMEI retomar fluxo existente",
};
export const PREPARE = `const items = $input.all();
if (items.length !== 1) throw new Error('Ingresso requer um unico envelope.');
const input = items[0];
const signature = input.json.headers?.['x-hub-signature-256'];
if (typeof signature !== 'string' || !/^sha256=[a-f0-9]{64}$/.test(signature)) throw new Error('Assinatura Meta ausente.');
const raw = await this.helpers.getBinaryDataBuffer(0, 'data');
if (!raw.length || raw.length > 65536) throw new Error('Envelope fora do limite.');
const body = raw.toString('utf8');
if (!Buffer.from(body, 'utf8').equals(raw)) throw new Error('UTF-8 invalido.');
const parsed = JSON.parse(body);
if (!parsed || parsed.object !== 'instagram' || !Array.isArray(parsed.entry)) throw new Error('Envelope Instagram invalido.');
const timestamp = String(Math.floor(Date.now() / 1000));
return [{json:{timestamp, body_text:body, meta_signature:signature, signing_input:timestamp+'\\n'+body}}];`;

function edge(name) {
  return { node: name, type: "main", index: 0 };
}

export function prepare(source, { sourceSha, publishedVersion, apiOrigin }) {
  if (!/^[a-f0-9]{64}$/.test(sourceSha || "")) throw new Error("Hash de origem obrigatorio.");
  const origin = new URL(apiOrigin);
  if (
    origin.protocol !== "https:" ||
    origin.origin !== apiOrigin ||
    origin.username ||
    origin.password
  )
    throw new Error("Origem HTTPS explicita obrigatoria.");
  if (source.id !== WORKFLOW || !publishedVersion || source.versionId !== publishedVersion)
    throw new Error("Exporte a revisao publicada do workflow existente.");
  if (!Array.isArray(source.nodes) || !source.connections || typeof source.connections !== "object")
    throw new Error("Grafo invalido.");
  const candidate = structuredClone(source);
  const hooks = candidate.nodes.filter(
    (n) => n.type === "n8n-nodes-base.webhook" && n.parameters?.httpMethod === "POST",
  );
  if (hooks.length !== 1) throw new Error("Esperado um unico webhook POST.");
  const hook = hooks[0];
  if (hook.parameters.multipleMethods || hook.parameters.options?.binaryData)
    throw new Error("Modo do webhook requer revisao manual.");
  const old = candidate.connections[hook.name];
  if (
    !old ||
    Object.keys(old).some((key) => key !== "main") ||
    old.main?.length !== 1 ||
    !old.main[0].length
  )
    throw new Error("Saida do webhook nao reconhecida.");
  const byName = new Map(candidate.nodes.map((node) => [node.name, node]));
  if (
    byName.size !== candidate.nodes.length ||
    candidate.nodes.some((node) => Object.values(NAMES).includes(node.name))
  )
    throw new Error("Nomes duplicados ou preparacao ja aplicada.");
  const pending = old.main[0].map((target) => target.node),
    seen = new Set();
  while (pending.length) {
    const name = pending.pop();
    if (seen.has(name)) continue;
    seen.add(name);
    const node = byName.get(name);
    if (!node || name === hook.name || node.type === "n8n-nodes-base.respondToWebhook")
      throw new Error("Resposta ou ciclo no caminho legado requer revisao.");
    for (const output of candidate.connections[name]?.main || [])
      for (const target of output) pending.push(target.node);
  }
  hook.parameters.responseMode = "responseNode";
  hook.parameters.options = { ...hook.parameters.options, rawBody: true };
  // Failures in preparation/signing also produce 503, never an early acknowledgement.
  const make = (key, type, typeVersion, parameters, error = false) => ({
    id: `socialmei-persist-${key}`,
    name: NAMES[key],
    type,
    typeVersion,
    position: [300, Object.keys(NAMES).indexOf(key) * 180],
    parameters,
    ...(error ? { onError: "continueErrorOutput", retryOnFail: false } : {}),
  });
  const prepared = `$('${NAMES.prepare}').first().json`;
  const persisted = `$('${NAMES.persist}').first().json`;
  const validate = `const receipt = $input.first().json;
if (receipt.received !== true || typeof receipt.continue_automation !== 'boolean' || ['processed','duplicates','ignored'].some(key => !Number.isInteger(receipt[key]) || receipt[key] < 0 || receipt[key] > 1000)) throw new Error('Recibo de persistencia invalido.');
if (receipt.continue_automation !== (receipt.processed > 0 && receipt.duplicates === 0 && receipt.ignored === 0)) throw new Error('Recibo de automacao divergente.');
return $input.all();`;
  const resume = `const receipt = ${persisted};
if (receipt.continue_automation !== true || !Number.isInteger(receipt.processed) || receipt.processed < 1 || receipt.duplicates !== 0 || receipt.ignored !== 0) return [];
return $(${JSON.stringify(hook.name)}).all().map(item => {
  const restored = {...item};
  if (item.binary) {
    const {data: rawIngress, ...remaining} = item.binary;
    if (Object.keys(remaining).length) restored.binary = remaining;
    else delete restored.binary;
  }
  return restored;
});`;
  candidate.nodes.push(
    make(
      "prepare",
      "n8n-nodes-base.code",
      2,
      { mode: "runOnceForAllItems", jsCode: PREPARE },
      true,
    ),
    make(
      "sign",
      "n8n-nodes-base.crypto",
      1,
      {
        action: "hmac",
        type: "SHA256",
        binaryData: false,
        value: "={{ $json.signing_input }}",
        dataPropertyName: "signature",
        encoding: "hex",
        secret:
          "={{ (() => { const key = $env.SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY; if (typeof key !== 'string' || key.length < 32) throw new Error('Chave privada de ingresso indisponivel.'); return key; })() }}",
      },
      true,
    ),
    make(
      "persist",
      "n8n-nodes-base.httpRequest",
      4.2,
      {
        method: "POST",
        url: apiOrigin + "/webhooks/instagram/n8n",
        sendHeaders: true,
        headerParameters: {
          parameters: [
            { name: "X-SocialMEI-Timestamp", value: `={{ ${prepared}.timestamp }}` },
            { name: "X-SocialMEI-Signature", value: "={{ 'sha256=' + $json.signature }}" },
            { name: "X-Hub-Signature-256", value: `={{ ${prepared}.meta_signature }}` },
          ],
        },
        sendBody: true,
        contentType: "raw",
        rawContentType: "application/json",
        body: `={{ ${prepared}.body_text }}`,
        options: {
          timeout: 10000,
          redirect: { redirect: { followRedirects: false } },
          response: { response: { responseFormat: "json", neverError: false } },
        },
      },
      true,
    ),
    make("ack", "n8n-nodes-base.respondToWebhook", 1.4, {
      respondWith: "text",
      responseBody: "EVENT_RECEIVED",
      options: { responseCode: 200 },
    }),
    make(
      "validate",
      "n8n-nodes-base.code",
      2,
      { mode: "runOnceForAllItems", jsCode: validate },
      true,
    ),
    make("fail", "n8n-nodes-base.respondToWebhook", 1.4, {
      respondWith: "text",
      responseBody: "INGRESS_UNAVAILABLE",
      options: { responseCode: 503 },
    }),
    make("resume", "n8n-nodes-base.code", 2, { mode: "runOnceForAllItems", jsCode: resume }),
  );
  candidate.connections[hook.name] = { main: [[edge(NAMES.prepare)]] };
  for (const [key, next] of [
    ["prepare", "sign"],
    ["sign", "persist"],
    ["persist", "validate"],
    ["validate", "ack"],
  ])
    candidate.connections[NAMES[key]] = { main: [[edge(NAMES[next])], [edge(NAMES.fail)]] };
  candidate.connections[NAMES.ack] = { main: [[edge(NAMES.resume)]] };
  candidate.connections[NAMES.resume] = old;
  // Credentials, existing nodes/expressions and webhook identity remain in this PRIVATE file.
  return {
    target_workflow_id: WORKFLOW,
    expected_published_version_id: publishedVersion,
    source_sha256: sourceSha,
    automatically_publish: false,
    candidate: {
      name: candidate.name,
      nodes: candidate.nodes,
      connections: candidate.connections,
      settings: candidate.settings || {},
    },
  };
}

export async function main(args) {
  const names = ["input", "output", "expected-sha256", "published-version", "api-origin"];
  const options = {};
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i]?.replace(/^--/, "");
    if (!names.includes(key) || !args[i + 1] || options[key])
      throw new Error("Argumentos invalidos.");
    options[key] = args[i + 1];
  }
  if (names.some((name) => !options[name])) throw new Error("Argumentos obrigatorios ausentes.");
  const bytes = await readFile(options.input);
  const hash = createHash("sha256").update(bytes).digest("hex");
  if (hash !== options["expected-sha256"]) throw new Error("Export diverge do hash aprovado.");
  const result = prepare(JSON.parse(bytes), {
    sourceSha: hash,
    publishedVersion: options["published-version"],
    apiOrigin: options["api-origin"],
  });
  await writeFile(options.output, JSON.stringify(result, null, 2) + "\n", {
    flag: "wx",
    mode: 0o600,
  });
  return { prepared: true, workflow_id: WORKFLOW, source_sha256: hash, production_changed: false };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main(process.argv.slice(2))
    .then((result) => console.log(JSON.stringify(result)))
    .catch(() => {
      console.error(
        "Preparacao recusada. Confira os argumentos e o export publicado privado; detalhes omitidos.",
      );
      process.exitCode = 1;
    });
