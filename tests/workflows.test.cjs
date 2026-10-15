const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const workflow = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "../n8n-workflows/producao/01-caixa-unificada-api-postgresql.json"),
    "utf8",
  ),
);
const code = workflow.nodes.find((node) => node.type === "n8n-nodes-base.code").parameters.jsCode;

function normalize(body) {
  return vm.runInNewContext(`(function () { ${code}\n })()`, { $json: { body } })[0].json;
}

test("English workflow variables preserve the Portuguese JSON and SQL parameter contracts", () => {
  const payload = {
    cliente: "  João MEI  ",
    canal: "Instagram",
    mensagem: " Olá ",
    telefone: "81999990000",
    horario: "2026-10-10T12:00:00Z",
  };
  const result = normalize(payload);
  assert.equal(result.cliente, "João MEI");
  assert.equal(result.canal, "instagram");
  assert.equal(result.mensagem, "Olá");
  assert.equal(result.clienteKey, payload.telefone);
  assert.equal(result.conversaKey, "instagram:" + payload.telefone);
  assert.equal(result.horario, payload.horario.replace("Z", ".000Z"));
  assert.deepEqual(Object.keys(result), [
    "cliente",
    "canal",
    "mensagem",
    "telefone",
    "email",
    "clienteKey",
    "conversaKey",
    "horario",
  ]);
  const sql = workflow.nodes.find((node) => node.name === "Persistir no PostgreSQL");
  assert(sql.parameters.options.queryReplacement.includes("$json.clienteKey"));
});

test("normalization handles explicit IDs, fallback identifiers and invalid dates", () => {
  assert.equal(normalize({ cliente_id: "a", telefone: "b", conversa_id: "c" }).clienteKey, "a");
  assert.equal(normalize({ cliente_id: "a", conversa_id: "c" }).conversaKey, "c");
  const fallback = normalize({ cliente: "João & Cia", horario: "invalid" });
  assert.equal(fallback.clienteKey, "whatsapp:joao-cia");
  assert.equal(fallback.mensagem, "");
  assert(!Number.isNaN(Date.parse(fallback.horario)));
});

test("Python HTTP smoke export stays manual, internal and bounded", () => {
  const example = JSON.parse(
    fs.readFileSync(path.join(__dirname, "../n8n-workflows/examples/process-text.json"), "utf8"),
  );
  const [trigger, request] = example.nodes;
  assert.equal(example.active, false);
  assert.equal(trigger.type, "n8n-nodes-base.manualTrigger");
  assert.equal(request.parameters.url, "http://python-api:8000/processar");
  assert.equal(request.parameters.options.timeout, 15000);
  assert.equal(typeof JSON.parse(request.parameters.jsonBody).texto, "string");
  assert.equal(example.connections[trigger.name].main[0][0].node, request.name);
  assert.equal(example.nodes.length, 2);
});
