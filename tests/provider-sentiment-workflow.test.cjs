const test = require("node:test");
const assert = require("node:assert/strict");
const workflow = require("../n8n-workflows/experimental/provider-sentiment-worker.json");

test("workflow sentiment stays inactive, needs operator enablement", () => {
  assert.equal(workflow.active, false);
  const gate = workflow.nodes.find((n) => n.name === "Piloto protegido");
  assert.match(gate.parameters.jsCode, /ENABLED = false/);
  assert.equal(gate.type, "n8n-nodes-base.code");
});

test("sentiment workflow only calls the internal API; never sends messages", () => {
  const requests = workflow.nodes.filter((node) => node.type === "n8n-nodes-base.httpRequest");
  assert.equal(requests.length, 2);
  const paths = requests.map((node) => new URL(node.parameters.url).pathname).sort();
  assert.deepEqual(paths, [
    "/internal/message-enrichment/provider/claims",
    "/internal/message-enrichment/provider/results",
  ]);
  for (const node of requests) {
    assert.equal(node.parameters.authentication, "genericCredentialType");
    assert.equal(node.parameters.genericAuthType, "httpHeaderAuth");
    assert.equal(node.retryOnFail, false);
    assert.equal(node.credentials, undefined);
  }
});

test("the AI output is validated and claim identity is taken from the task", () => {
  const validate = workflow.nodes.find((node) => node.name === "Validar classificacao");
  assert.equal(validate.parameters.mode, "runOnceForEachItem");
  assert.match(validate.parameters.jsCode, /Individualizar classificacoes/);
  assert.match(validate.parameters.jsCode, /JSON\.parse\(raw\)/);
  assert.match(validate.parameters.jsCode, /claim_id:task\.claim_id/);
  for (const node of workflow.nodes) {
    if (node.type === "n8n-nodes-base.code")
      assert.doesNotThrow(() => new Function(node.parameters.jsCode));
  }
});
