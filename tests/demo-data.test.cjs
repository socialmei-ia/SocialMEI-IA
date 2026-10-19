const { test } = require("node:test");
const assert = require("node:assert/strict");
const demo = require("../frontend/scripts/demo-data.js");
test("small synthetic data is internally coherent, immutable and independent of the calendar", () => {
  for (const day of ["2026-10-19", "2027-01-01", "2028-03-01"]) {
    const d = demo.dataset(day);
    assert.equal(d.clientes.length, 6);
    assert.equal(d.vendas.length, 8);
    assert(d.vendas.every((v) => v.valor <= 180 && d.clientes.some((c) => c.id === v.cliente_id)));
    const paid = d.vendas.filter((v) => v.status === "Pago").reduce((n, v) => n + v.valor, 0);
    const received = d.financeiro
      .filter((v) => v.tipo === "receita")
      .reduce((n, v) => n + v.valor, 0);
    assert.equal(paid, received);
    assert(paid < 1000);
    assert.equal(d.conversations.length, 6);
    assert(d.conversations.every((c) => d.clientes.some((client) => client.id === c.clientId)));
    assert(Object.isFrozen(d.vendas[0]));
    assert.notEqual(demo.dataset(day).clientes, d.clientes);
    assert(d.vendas.some((v) => v.data === day));
    assert(!d.vendas.some((v) => v.data === day.slice(0, 8) + "99"));
  }
});
test("demo opt-in is isolated by identity, disabled by default, durable only as preference", () => {
  const values = new Map();
  let scope = "user:1:workspace:1";
  const repo = demo.preference(
    { getItem: (k) => values.get(k), setItem: (k, v) => values.set(k, v) },
    () => scope,
  );
  assert.equal(repo.enabled(), false);
  repo.set(true);
  assert.equal(repo.enabled(), true);
  assert.deepEqual([...values.values()], ["true"]);
  scope = "user:1:workspace:2";
  assert.equal(repo.enabled(), false);
  repo.set(true);
  repo.set(false);
  assert.equal(repo.enabled(), false);
  scope = "user:2:workspace:1";
  assert.equal(repo.enabled(), false);
  scope = "user:1:workspace:1";
  assert.equal(repo.enabled(), true);
  scope = null;
  assert.equal(repo.enabled(), false);
  assert.throws(() => repo.set(true));
});
test("unavailable storage fails closed and cannot claim successful activation", () => {
  const repo = demo.preference(
    {
      getItem() {
        throw Error("blocked");
      },
      setItem() {
        throw Error("quota");
      },
    },
    () => "scope",
  );
  assert.equal(repo.enabled(), false);
  assert.throws(() => repo.set(true), /quota/);
});
test("shared sample keeps support and refusal out of the sales queue without inventing probability", () => {
  const priority = require("../frontend/scripts/priority-engine.js");
  const presentation = require("../frontend/scripts/client-analysis.js");
  const sample = demo.dataset("2026-10-19");
  const rows = priority.prioritizeCustomers(
    sample.conversations.map((conversation) => ({
      id: String(conversation.id),
      name: conversation.nome,
      messages: conversation.mensagens.map((message, index) => ({
        id: String(index),
        author: "customer",
        text: message.texto,
        at: message.data + "T00:00:00-03:00",
      })),
    })),
    { referenceTime: "2026-10-19T15:00:00Z" },
  );
  const forName = (name) => rows.find((row) => row.name.startsWith(name));
  assert.equal(presentation.present(forName("Lia")).level, "quente");
  assert.equal(presentation.present(forName("Bruno")).lane, "chance");
  assert.equal(presentation.present(forName("Ana")).lane, "attention");
  assert.equal(presentation.present(forName("Paulo")).lane, "attention");
  assert.equal(presentation.present(forName("Leo")).lane, "excluded");
  assert(rows.every((row) => !Object.hasOwn(row, "probability")));
});
