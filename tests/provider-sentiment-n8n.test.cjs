const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const workflow = JSON.parse(fs.readFileSync(
  path.join(__dirname, "../n8n-workflows/equipe/02-sentimento-mensagens-verificadas.json"),
  "utf8",
));
const byName = new Map(workflow.nodes.map((node) => [node.name, node]));
const claimNode = byName.get("Validar lote");
const receiptNode = byName.get("Validar classificação");
const id = "11111111-2222-4333-8444-555555555555";

function claims(payload) {
  const input = { first() { return { json: payload }; } };
  return new Function("$input", claimNode.parameters.jsCode)(input);
}

function result(rows, items) {
  const lookup = () => ({ all: () => rows.map((json) => ({ json })) });
  const input = { all: () => items.map((json) => ({ json })) };
  return new Function("$", "$input", receiptNode.parameters.jsCode)(lookup, input);
}

test("export is inactive, no webhook or sends, and uses private bearer credentials only", () => {
  assert.equal(workflow.active, false);
  assert.equal(workflow.nodes.length, 6);
  assert.equal(workflow.nodes[0].type, "n8n-nodes-base.scheduleTrigger");
  assert.equal(workflow.settings.saveDataSuccessExecution, "none");
  assert.equal(workflow.settings.saveDataErrorExecution, "none");
  assert.deepEqual(workflow.pinData, {});
  const all = JSON.stringify(workflow);
  assert(!/api\/sendText|graph\.instagram\.com|sendMessage|twilio|authorization.*Bearer /i.test(all));
  assert(!/api_key|sk-proj-|gsk_/i.test(all));
  assert(!/webhook(?:Trigger)?/i.test(workflow.nodes.map((n) => n.type).join(" ")));
  const http = workflow.nodes.filter((node) => node.type === "n8n-nodes-base.httpRequest");
  assert.equal(http.length, 3);
  assert(http.every((node) =>
    node.parameters.authentication === "genericCredentialType" &&
    node.parameters.genericAuthType === "httpHeaderAuth" &&
    node.credentials === undefined
  ));
  assert.equal(http[0].parameters.method, "POST");
  assert.match(http[0].parameters.url, /\/claims$/);
  assert.match(http[1].parameters.url, /^https:\/\/api\.groq\.com\//);
  assert.equal(http[2].parameters.method, "POST");
  assert.match(http[2].parameters.url, /\/results$/);
  for (const [name, edges] of Object.entries(workflow.connections)) {
    assert(byName.has(name));
    for (const target of edges.main.flat()) assert(byName.has(target.node));
  }
});

test("claim validator accepts only a limited verified, send-disabled batch", () => {
  const item = { claim_id: id, message_id: 3, origin: "waha", text: "Vocês têm bolo?", attempt: 1 };
  const payload = { schema_version: 1, send_enabled: false, items: [item] };
  assert.equal(claims(payload)[0].json.claim_id, id);
  assert.equal(claims({ ...payload, items: [] }).length, 0);
  for (const bad of [
    { ...payload, send_enabled: true },
    { ...payload, schema_version: 2 },
    { ...payload, items: Array(11).fill(item) },
    { ...payload, items: [{ ...item, origin: "synthetic" }] },
    { ...payload, items: [{ ...item, text: "" }] },
    { ...payload, items: [{ ...item, claim_id: "not-a-claim" }] },
  ]) assert.throws(() => claims(bad));
});

test("AI JSON is validated, capped, paired with original claim and never treated as a reply", () => {
  const claim = { claim_id: id, message_id: 3, origin: "waha", text: "Estou insatisfeito" };
  const pred = (v) => ({ choices: [{ message: { content: JSON.stringify(v) } }] });
  const good = { sentiment: "negative", confidence: "medium", explanation: "Mensagem demonstra insatisfação." };
  const output = result([claim], [pred(good)]);
  assert.equal(output.length, 1);
  assert.equal(output[0].json.claim_id, id);
  assert.equal(output[0].json.sentiment, "negative");
  assert.equal(output[0].json.confidence, "medium");
  assert.equal(output[0].json.explanation, good.explanation);
  assert.deepEqual(Object.keys(output[0].json).sort(),
    ["claim_id", "confidence", "explanation", "sentiment"]);
  const bad = [
    { ...good, sentiment: "urgent-send" },
    { ...good, explanation: "" },
    { ...good, message: "send to client" },
    { ...good, confidence: "ultra" },
  ];
  for (const value of bad) assert.throws(() => result([claim], [pred(value)]));
  assert.throws(() => result([claim], [pred(good), pred(good)]));
  assert.throws(() => result([claim], [{ choices: [{ message: { content: "not json" } }] }]));
  assert.equal(result([claim], [pred({ ...good, explanation: "x".repeat(600) })])[0].json.explanation.length, 120);
});
