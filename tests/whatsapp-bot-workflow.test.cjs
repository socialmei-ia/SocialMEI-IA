const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const workflow = JSON.parse(
  fs.readFileSync("n8n-workflows/experimental/whatsapp-bot-planner.json", "utf8"),
);
const find = (name) => workflow.nodes.find((n) => n.name === name);
function code(name, json, enabled = false) {
  let source = find(name).parameters.jsCode;
  if (enabled) source = source.replace("const ENABLED = false;", "const ENABLED = true;");
  return vm.runInNewContext("(function(){" + source + "})()", {
    $json: json,
    $input: { all: () => [{ json }] },
  });
}
test("WhatsApp workflow is inactive, private and has no retry after reserving a send", () => {
  assert.equal(workflow.active, false);
  assert.equal(
    workflow.nodes.some((n) => n.type.endsWith(".webhook")),
    false,
  );
  assert.equal(workflow.settings.saveDataSuccessExecution, "none");
  assert.equal(workflow.settings.saveDataErrorExecution, "none");
  for (const n of workflow.nodes.filter((n) => n.type.endsWith(".httpRequest"))) {
    assert.equal(n.retryOnFail, false);
    assert.equal(n.parameters.genericAuthType, "httpHeaderAuth");
    assert.equal(n.credentials, undefined);
  }
  assert.equal(workflow.connections["Reserva exclusiva"].main[1].length, 0);
  assert.throws(() => code("Ativacao e entrada", {}), /desativado/);
});
test("WhatsApp workflow accepts references only, never caller-selected text or destination", () => {
  const out = code(
    "Ativacao e entrada",
    { instance: "trusted-a", external_message_id: "message-id", chatId: "forged", text: "forged" },
    true,
  );
  assert.equal(
    JSON.stringify(out[0].json),
    JSON.stringify({ instance: "trusted-a", external_message_id: "message-id" }),
  );
  assert.throws(
    () => code("Ativacao e entrada", { instance: "bad/path", external_message_id: "id" }, true),
    /invalida/,
  );
});
test("WhatsApp delivery guard blocks arbitrary provider routes and unclaimed sends", () => {
  const delivery = {
    path: "/api/sendText",
    body: { session: "default", chatId: "222@c.us", text: "hello" },
  };
  assert.equal(
    code("Conferir destino", { dispatch_allowed: true, delivery })[0].json.chatId,
    "222@c.us",
  );
  for (const json of [
    { dispatch_allowed: false, delivery },
    { dispatch_allowed: true, delivery: { ...delivery, path: "/api/sendImage" } },
    {
      dispatch_allowed: true,
      delivery: { ...delivery, body: { ...delivery.body, chatId: "123@g.us" } },
    },
  ])
    assert.throws(() => code("Conferir destino", json), /bloqueado/);
});
test("WhatsApp receipt never guesses success without provider identity", () => {
  for (const id of [undefined, "bad id", 123])
    assert.equal(code("Validar recibo", { id })[0].json.status, "uncertain");
  assert.equal(code("Validar recibo", { id: "true_222@c.us_123" })[0].json.status, "confirmed");
});
