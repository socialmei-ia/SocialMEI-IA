const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = "n8n-workflows/experimental/whatsapp-bot-persisted-inputs.json";
const workflow = fs.existsSync(path)
  ? JSON.parse(fs.readFileSync(path, "utf8"))
  : { nodes: [], connections: {}, settings: {} };
const find = (name) => workflow.nodes.find((n) => n.name === name);
function code(name, json, enabled = false, configured = false) {
  const node = find(name);
  assert.ok(node, "Missing guarded reference adapter");
  let source = node.parameters.jsCode;
  if (enabled) source = source.replace("const ENABLED = false;", "const ENABLED = true;");
  if (configured) source = source.replace("REVIEW_REQUIRED", "syntheticPlanner01");
  return vm.runInNewContext("(function(){" + source + "})()", { $json: json });
}
test("reference poller is inactive and rejects activation without a reviewed planner", () => {
  assert.equal(workflow.active, false);
  assert.throws(() => code("Piloto protegido", {}), /desativado/);
  assert.throws(() => code("Piloto protegido", {}, true), /planner/);
  assert.equal(
    code("Piloto protegido", {}, true, true)[0].json.planner_workflow_id,
    "syntheticPlanner01",
  );
  const next = workflow.connections["Piloto protegido"].main[0][0].node;
  assert.equal(next, "Consultar referencias persistidas");
  const get = find(next);
  assert.equal(get.parameters.method, "GET");
  assert.equal(get.parameters.url, "http://team-api:8000/internal/whatsapp/bot/sources");
  assert.equal(get.parameters.genericAuthType, "httpHeaderAuth");
  assert.equal(get.credentials, undefined);
});
test("adapter forwards only validated persisted references and deduplicates its batch", () => {
  const source = { instance: "socialmei-equipe-piloto", external_message_id: "opaque-id" };
  const out = code("Separar referencias", {
    sources: [source, source, { ...source, external_message_id: "another" }],
  });
  assert.equal(out.length, 2);
  assert.equal(JSON.stringify(out[0].json), JSON.stringify(source));
  assert.equal(code("Separar referencias", { sources: [] }).length, 0);
  for (const payload of [
    {},
    { sources: null },
    { sources: Array(51).fill(source) },
    { sources: [{ ...source, text: "forged" }] },
    { sources: [{ ...source, instance: "foreign/path" }] },
    { sources: [{ ...source, external_message_id: "bad id" }] },
    { sources: [null] },
  ])
    assert.throws(() => code("Separar referencias", payload), /Referencia/);
});
test("each reference invokes the planner separately with no retry and no sender in the poller", () => {
  const execute = find("Executar planner uma mensagem");
  assert.ok(execute);
  assert.equal(execute.type, "n8n-nodes-base.executeWorkflow");
  assert.equal(execute.parameters.source, "database");
  assert.equal(execute.parameters.mode, "each");
  assert.equal(execute.parameters.options.waitForSubWorkflow, true);
  assert.equal(execute.retryOnFail, false);
  assert.equal(execute.parameters.workflowInputs, undefined);
  assert.equal(execute.parameters.workflowId.__rl, true);
  assert.equal(
    workflow.nodes.some((n) => /webhook|waha/i.test(n.type)),
    false,
  );
  assert.equal(workflow.nodes.filter((n) => n.type.endsWith(".httpRequest")).length, 1);
  for (const node of workflow.nodes) assert.notEqual(node.retryOnFail, true);
  assert.equal(workflow.settings.saveDataSuccessExecution, "none");
  assert.equal(workflow.settings.saveDataErrorExecution, "none");
  assert.equal(workflow.settings.saveManualExecutions, false);
  assert.equal(workflow.settings.saveExecutionProgress, false);
  assert.deepEqual(find("Consultar a cada 15 segundos").parameters.rule.interval, [
    { field: "seconds", secondsInterval: 15 },
  ]);
});
