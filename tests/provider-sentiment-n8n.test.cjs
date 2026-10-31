const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const workflow = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "../n8n-workflows/experimental/provider-sentiment-worker.json"),
    "utf8",
  ),
);
const byName = new Map(workflow.nodes.map((node) => [node.name, node]));
const claimNode = byName.get("Individualizar classificacoes");
const resultNode = byName.get("Validar classificacao");
const claimId = "11111111-2222-4333-8444-555555555555";

function claims(payload) {
  const input = { first() { return { json: payload }; } };
  return new Function("$input", claimNode.parameters.jsCode)(input);
}
function result(job, modelResponse) {
  const lookup = () => ({ item: { json: job } });
  return new Function("$", "$json", resultNode.parameters.jsCode)(lookup, modelResponse);
}

test("existing n8n sentiment workflow stays uniquely tracked, inactive and independently gated", () => {
  assert.equal(workflow.active, false);
  assert.equal(workflow.nodes.length, 8);
  assert.equal(workflow.nodes[0].type, "n8n-nodes-base.scheduleTrigger");
  assert.match(byName.get("Piloto protegido").parameters.jsCode, /const ENABLED = false;/);
  assert.equal(workflow.settings.saveDataSuccessExecution, "none");
  assert.equal(workflow.settings.saveDataErrorExecution, "none");
  assert.equal(workflow.settings.saveManualExecutions, false);
  assert.equal(
    byName.get("Groq — credencial privada").type,
    "@n8n/n8n-nodes-langchain.lmChatGroq",
  );
  assert.equal(workflow.nodes.filter((node) => node.type === "n8n-nodes-base.httpRequest").length, 2);
  for (const node of workflow.nodes) {
    assert.equal(node.credentials, undefined);
    if (node.type === "n8n-nodes-base.httpRequest") {
      assert.equal(node.parameters.authentication, "genericCredentialType");
      assert.equal(node.parameters.genericAuthType, "httpHeaderAuth");
      assert.equal(node.parameters.method, "POST");
      assert(
        /\/internal\/message-enrichment\/provider\/(claims|results)$/.test(
          node.parameters.url,
        ),
      );
    }
    for (const edges of Object.values(workflow.connections[node.name] || {}))
      for (const target of edges.flat()) assert(byName.has(target.node));
  }
  const urls = workflow.nodes.map((node) => node.parameters.url || "");
  assert(!urls.some((url) => /sendText|graph.instagram|messages\//i.test(url)));
});

test("claim validation checks the version, provider ownership and send-disabled gate", () => {
  const job = { claim_id: claimId, message_id: 3, origin: "waha", text: "Qual o preço?", attempt: 1 };
  const payload = { schema_version: 1, send_enabled: false, items: [job] };
  assert.equal(claims(payload)[0].json.claim_id, claimId);
  assert.equal(claims(payload)[0].json.text, job.text);
  assert.equal(claims({ ...payload, items: [] }).length, 0);
  for (const invalid of [
    { ...payload, send_enabled: true },
    { ...payload, schema_version: 2 },
    { ...payload, items: Array(11).fill(job) },
    { ...payload, items: [{ ...job, origin: "synthetic" }] },
    { ...payload, items: [{ ...job, claim_id: "wrong" }] },
    { ...payload, items: [{ ...job, text: "" }] },
    { ...payload, items: [{ ...job, attempt: 4 }] },
  ]) assert.throws(() => claims(invalid));
});

test("AI response is strict, bounded, and only recorded against the original claim", () => {
  const task = { claim_id: claimId, text: "Estou insatisfeito" };
  const good = {
    sentiment: "negative",
    confidence: "medium",
    explanation: "Cliente demonstra insatisfação.",
  };
  const output = result(task, { output: JSON.stringify(good) });
  assert.deepEqual(output.json, { claim_id: claimId, ...good });
  for (const invalid of [
    { ...good, sentiment: "send-now" },
    { ...good, confidence: "extreme" },
    { ...good, explanation: "" },
    { ...good, suggested_reply: "Enviar ao cliente" },
  ]) assert.throws(() => result(task, { output: JSON.stringify(invalid) }));
  assert.throws(() => result(task, { output: "not json" }));
  assert.equal(
    result(task, { output: JSON.stringify({ ...good, explanation: "x".repeat(600) }) }).json
      .explanation.length,
    120,
  );
  assert.equal(resultNode.parameters.mode, "runOnceForEachItem");
});
