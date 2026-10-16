const test = require("node:test");
const assert = require("node:assert/strict");
const { prioritizeCustomers } = require("../prototypes/opportunities/priority-engine.js");
const { referenceTime, scenarios, customers } = require("./fixtures/commercial-evaluation.cjs");
const rows = prioritizeCustomers(customers, { referenceTime });
for (const scenario of scenarios)
  test(`${scenario.id} ${scenario.segment}: ${scenario.case}`, () => {
    const row = rows.find((row) => row.id === scenario.id);
    assert.equal(
      row.analyses.at(-1).result.category,
      scenario.category,
      "Classificação da última mensagem",
    );
    assert.equal(row.group, scenario.group, "Encaminhamento da conversa");
    assert.match(row.reasons.join(" "), scenario.reason, "Motivo deve explicar o encaminhamento");
    assert.match(row.nextStep, scenario.step, "Recomendação adequada ao contexto");
    assert(!/\d+\s*%/.test(row.reasons.join(" ") + row.nextStep));
    for (const { message, result } of row.analyses)
      for (const signal of result.signals)
        for (const evidence of signal.evidence)
          assert.equal(
            message.text.slice(evidence.start, evidence.end),
            evidence.text,
            "Evidência literal e pertencente ao cliente",
          );
    if (["support", "completed", "declined"].includes(scenario.group))
      assert.equal(row.commercial, false);
  });
test("queue uses group, urgency and recency, not segment or number of messages", () => {
  const commercial = rows.filter((row) => row.commercial).map((row) => row.id);
  assert.deepEqual(commercial, ["a1", "b1", "m1", "p1", "c1", "a3", "c2", "b2", "m4", "p2", "a4"]);
  const outcomes = rows.filter((row) => !row.commercial).map((row) => row.id);
  assert.deepEqual(outcomes, ["a2", "c4", "b4", "m2", "p4", "m3", "c3", "b3", "p3"]);
  const reversed = prioritizeCustomers([...customers].reverse(), { referenceTime });
  assert.deepEqual(
    reversed.map((row) => row.id),
    rows.map((row) => row.id),
  );
});
test("complaint corrections do not capture negated defects, hypothetical defects or unrelated expiry", () => {
  for (const text of [
    "O leite que comprei não está vencido. Quero comprar outro.",
    "Meu corte não ficou torto. Quero agendar novamente.",
    "A barra não ficou torta. Quanto custa ajustar outra?",
    "Se a barra ficar torta, posso voltar?",
    "O orçamento está vencido. Quero contratar o serviço.",
    "Quero contratar um serviço de ajuste de barra.",
  ]) {
    const row = prioritizeCustomers(
      [
        {
          id: "contrast",
          name: "Cliente fictício",
          messages: [{ id: "m", author: "customer", text, at: referenceTime }],
        },
      ],
      { referenceTime },
    )[0];
    assert.notEqual(row.group, "support", text);
    assert(!row.analyses[0].result.signals.some((signal) => signal.id === "support"), text);
  }
});
