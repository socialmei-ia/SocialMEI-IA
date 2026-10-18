const { test } = require("node:test");
const assert = require("node:assert/strict");
const model = require("../frontend/scripts/client-analysis.js");
const engine = require("../frontend/scripts/priority-engine.js");
const analyze = (text) =>
  engine.prioritizeCustomers(
    [{ id: "test", name: "Teste", messages: [{ id: "m", author: "customer", text, at: null }] }],
    { referenceTime: "2026-10-18T12:00:00Z" },
  )[0];
test("greetings and doubts remain in analysis, purchase and inquiry have qualitative interest", () => {
  for (const text of ["Oi!", "Talvez compre, ainda não decidi."])
    assert.equal(model.present(analyze(text)).lane, "analysis");
  assert.equal(model.present(analyze("Quero contratar a troca de tela.")).level, "quente");
  assert.equal(model.present(analyze("Quanto custa o perfume?")).level, "morno");
});
test("refusal and completed purchases cannot be turned into sales by a level override", () => {
  for (const text of ["Não quero comprar.", "Já comprei.", "Recebi meu pedido, adorei!"]) {
    assert.equal(model.present(analyze(text), "quente").lane, "excluded");
  }
});
test("support stays separate even with purchase signals or manual interest", () => {
  for (const text of [
    "Preciso de ajuda, meu produto veio quebrado. Quero comprar outro.",
    "Preciso de suporte.",
  ]) {
    assert.equal(model.present(analyze(text), "quente").lane, "attention");
  }
});
test("urgency in support has priority, negation does not create critical priority", () => {
  assert.equal(
    model.present(analyze("Preciso de ajuda urgente, veio quebrado.")).priority,
    "critical",
  );
  assert.equal(model.present(analyze("Preciso de suporte, mas não é urgente.")).priority, "normal");
  assert.equal(
    model.present(analyze("Preciso de suporte para uma cobrança indevida.")).priority,
    "high",
  );
});
test("human level is explicit without changing recommendation or creating probability", () => {
  const row = analyze("Bom dia!");
  const original = JSON.stringify(row);
  assert.equal(model.present(row, "frio").lane, "chance");
  assert.equal(model.present(row, "frio").manual, true);
  assert.equal(model.present(row, "inventado").lane, "analysis");
  assert.equal(JSON.stringify(row), original);
  assert.equal("probability" in model.present(row), false);
});
test("demo objects are independent and cover all three lanes and exclusions", () => {
  const customers = model.demoCustomers();
  customers[0].messages[0].text = "changed";
  assert.notEqual(model.demoCustomers()[0].messages[0].text, "changed");
  const lanes = engine
    .prioritizeCustomers(model.demoCustomers(), { referenceTime: "2026-10-18T12:00:00Z" })
    .map((r) => model.present(r).lane);
  for (const lane of ["analysis", "chance", "attention", "excluded"]) assert(lanes.includes(lane));
});

test("old urgency is not reused for a later support request", () => {
  const row = engine.prioritizeCustomers(
    [
      {
        id: "x",
        name: "Teste",
        messages: [
          { id: "a", author: "customer", text: "Quero comprar hoje!", at: null },
          { id: "b", author: "customer", text: "Preciso de suporte.", at: null },
        ],
      },
    ],
    { referenceTime: "2026-10-18T12:00:00Z" },
  )[0];
  assert.equal(model.present(row).priority, "normal");
  assert.equal(model.present(analyze("É urgente!")).lane, "analysis");
});

test("clearing analysis repeatedly clears UI without installing any event handler", () => {
  const fs = require("node:fs"),
    vm = require("node:vm");
  const source = fs.readFileSync(
    require("node:path").join(__dirname, "../frontend/scripts/opportunities.js"),
    "utf8",
  );
  const start = source.indexOf("  function clearAnalysis() {");
  const end = source.indexOf('\n  document.addEventListener("click"', start);
  const elements = new Map();
  let registrations = 0;
  const byId = (id) => {
    if (!elements.has(id))
      elements.set(id, {
        value: "old",
        hidden: false,
        textContent: "old",
        children: [1],
        replaceChildren() {
          this.children = [];
        },
        addEventListener() {
          registrations++;
        },
      });
    return elements.get(id);
  };
  const clear = vm.runInNewContext("(" + source.slice(start, end).trim() + ")", {
    byId,
    document: {
      addEventListener() {
        registrations++;
      },
    },
  });
  for (let i = 0; i < 8; i++) clear();
  assert.equal(registrations, 0, "clearAnalysis must not re-register click/keydown handlers");
  assert.equal(byId("opportunityText").value, "");
  assert.equal(byId("opportunityAnalysis").hidden, true);
});
