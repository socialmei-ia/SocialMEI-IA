const test = require("node:test");
const assert = require("node:assert/strict");
const { prioritizeCustomers, GROUPS } = require("../prototypes/opportunities/priority-engine.js");
const { customers, referenceTime } = require("../prototypes/opportunities/priority-scenario.js");
const message = (text, at = "2026-10-16T11:00:00Z", id = "m1", author = "customer") => ({
  id,
  text,
  at,
  author,
});
const client = (id, texts) => ({
  id,
  name: id,
  messages: texts.map((text, i) => message(text, `2026-10-16T1${i}:00:00Z`, `m${i}`)),
});
const run = (data, reviews = {}) => prioritizeCustomers(data, { referenceTime, reviews });
test("eight distinct customers are analyzed and ordered with separate destinations", () => {
  const rows = run(customers);
  assert.equal(rows.length, 8);
  assert.deepEqual(
    rows.filter((r) => r.commercial).map((r) => r.id),
    ["ana", "bruno", "camila", "diego", "helena"],
  );
  assert.equal(rows.find((r) => r.id === "fernanda").group, "declined");
  assert.equal(rows.find((r) => r.id === "eduardo").group, "completed");
  assert.equal(rows.find((r) => r.id === "gabriela").group, "support");
  for (const row of rows) {
    assert(row.reasons.length && row.nextStep);
    assert(!("score" in row) && !("probability" in row));
    for (const analysis of row.analyses)
      for (const signal of analysis.result.signals)
        for (const evidence of signal.evidence)
          assert.equal(analysis.message.text.slice(evidence.start, evidence.end), evidence.text);
  }
});
test("later refusal supersedes a previous purchase, greeting does not resurrect it", () => {
  assert.equal(
    run([client("a", ["Quero comprar.", "Não quero comprar.", "Obrigado!"])])[0].group,
    "declined",
  );
});
test("purchase after refusal needs clarification instead of automatic promotion", () => {
  assert.equal(run([client("a", ["Não quero comprar.", "Quero comprar."])])[0].group, "clarify");
});
test("same-message conflict and uncertainty require clarification", () => {
  for (const text of ["Quero comprar, mas não quero comprar agora.", "Não sei se quero comprar."])
    assert.equal(run([client("a", [text])])[0].group, "clarify");
});
test("support, completed purchase and negated completion are distinct", () => {
  assert.equal(run([client("a", ["Já comprei. Minha entrega não chegou."])])[0].group, "support");
  assert.equal(run([client("a", ["Já comprei. Obrigado!"])])[0].group, "completed");
  assert.notEqual(
    run([client("a", ["Não finalizei a compra. Quanto custa?"])])[0].group,
    "completed",
  );
  assert.notEqual(
    run([client("a", ["Não preciso de suporte. Quanto custa?"])])[0].group,
    "support",
  );
  assert.equal(
    run([client("a", ["Não chegou meu pedido. Quero comprar outro."])])[0].group,
    "support",
  );
});
test("new purchase after a completed purchase or support is not silently assumed same opportunity", () => {
  assert.equal(
    run([client("a", ["Já comprei.", "Quero comprar outro perfume."])])[0].group,
    "clarify",
  );
  assert.equal(
    run([client("a", ["Preciso de suporte.", "Quero comprar outro perfume."])])[0].group,
    "clarify",
  );
});
test("seller messages cannot become customer intent", () => {
  const row = run([
    {
      id: "a",
      name: "A",
      messages: [
        message("Quero comprar.", undefined, "s", "mei"),
        message("Bom dia!", undefined, "c"),
      ],
    },
  ])[0];
  assert.equal(row.group, "unknown");
  assert.equal(row.analyses.length, 1);
});
test("message volume never increases priority", () => {
  const one = client("a", ["Quanto custa?"]),
    many = client("b", ["Quanto custa?"]);
  many.messages.unshift(
    ...Array.from({ length: 10 }, (_, i) => message("Bom dia!", "2026-10-16T09:00:00Z", `g${i}`)),
  );
  assert.deepEqual(
    run([many, one]).map((r) => r.id),
    ["a", "b"],
  );
});
test("signals across messages are not added to manufacture high intent", () => {
  const row = run([
    client("a", ["Quanto custa o 212 VIP?", "Tem pronta entrega?", "Consegue entregar hoje?"]),
  ])[0];
  assert.equal(row.group, "inquiry");
});
test("recency breaks ties, input order and names do not", () => {
  const a = { id: "a", name: "Z", messages: [message("Quanto custa?", "2026-10-16T10:00:00Z")] };
  const b = { id: "b", name: "A", messages: [message("Quanto custa?", "2026-10-16T11:00:00Z")] };
  assert.deepEqual(
    run([a, b]).map((r) => r.id),
    ["b", "a"],
  );
  assert.deepEqual(
    run([b, a]).map((r) => r.id),
    ["b", "a"],
  );
});
test("recent urgency only breaks ties inside the same group", () => {
  const a = client("a", ["Quanto custa?"]),
    b = client("b", ["Quanto custa? Preciso hoje."]),
    c = client("c", ["Quero comprar."]);
  assert.deepEqual(
    run([a, b, c]).map((r) => r.id),
    ["c", "b", "a"],
  );
  assert.equal(run([client("a", ["É urgente hoje!"])])[0].group, "unknown");
});
test("old intent and today wording require refreshing context; greeting is not a new signal", () => {
  const row = run([
    {
      id: "a",
      name: "A",
      messages: [
        message("Quero comprar hoje.", "2026-10-12T10:00:00Z", "old"),
        message("Olá!", "2026-10-16T11:00:00Z", "new"),
      ],
    },
  ])[0];
  assert.equal(row.group, "reconnect");
  assert.equal(row.urgent, false);
});
test("timestamps sort messages only when reliable and never invent recency", () => {
  const data = {
    id: "a",
    name: "A",
    messages: [
      message("Não quero comprar.", "2026-10-16T11:00:00Z", "late"),
      message("Quero comprar.", "2026-10-16T09:00:00Z", "early"),
    ],
  };
  assert.equal(run([data])[0].group, "declined");
  for (const at of [null, "not-a-date", "2030-01-01T12:00:00Z"]) {
    const row = run([{ id: "a", name: "A", messages: [message("Quero comprar hoje.", at)] }])[0];
    assert.equal(row.recency, null);
    assert.equal(row.urgent, false);
    assert(row.dateWarning);
  }
});
test("human review changes destination with attribution, preserving recommendation and other customers", () => {
  const before = run(customers);
  const after = run(customers, {
    ana: { group: "clarify", reason: "Confirmar o item com a pessoa." },
  });
  const ana = after.find((r) => r.id === "ana");
  assert.equal(ana.group, "clarify");
  assert.equal(ana.recommendation.group, "first");
  assert(ana.review.reason);
  assert.deepEqual(
    after.find((r) => r.id === "bruno"),
    before.find((r) => r.id === "bruno"),
  );
  assert.equal(run(customers).find((r) => r.id === "ana").group, "first");
  assert.throws(() => run(customers, { ana: { group: "first", reason: " " } }));
  assert.throws(() => run(customers, { ana: { group: "fake", reason: "motivo" } }));
  assert(Object.keys(GROUPS).length > 0);
});
test("identities are validated and input remains untouched", () => {
  const original = JSON.stringify(customers);
  run(customers);
  assert.equal(JSON.stringify(customers), original);
  assert.throws(() => run([client("a", ["Olá"]), client("a", ["Quero comprar"])]));
  assert.throws(() => run([{ id: "a", name: "A", messages: [message("Olá"), message("Oi")] }]));
  assert.throws(() => prioritizeCustomers(customers, { referenceTime: "invalid" }));
});

test("isolated item and urgency do not renew earlier purchase recency", () => {
  for (const text of ["212 VIP", "Hoje!"]) {
    const row = run([
      {
        id: "a",
        name: "A",
        messages: [
          message("Quero comprar.", "2026-10-12T10:00:00Z", "old"),
          message(text, "2026-10-16T11:00:00Z", "new"),
        ],
      },
    ])[0];
    assert.equal(row.group, "reconnect");
    assert.equal(row.decisiveMessageId, "old");
  }
});
test("completed purchase and new intent in the same message require context", () => {
  assert.equal(
    run([client("a", ["Já comprei o perfume, mas quero comprar outro."])])[0].group,
    "clarify",
  );
});
test("follow-up consultation does not erase purchase intent or an unresolved objection", () => {
  assert.equal(run([client("a", ["Quero comprar.", "Vocês aceitam Pix?"])])[0].group, "first");
  assert.equal(
    run([client("a", ["Está muito caro.", "Quanto custa o outro perfume?"])])[0].group,
    "clarify",
  );
});
test("negated post-sale requests are not automatically treated as support", () => {
  const row = run([client("a", ["Não quero devolução. Quanto custa outro perfume?"])])[0];
  assert.notEqual(row.group, "support");
});
test("urgency never outranks a stronger commercial group and missing dates lose recency tie-breaks", () => {
  const explicit = client("a", ["Quero comprar."]);
  const urgent = client("b", ["Quanto custa? Preciso hoje."]);
  const undated = { id: "c", name: "C", messages: [message("Quero comprar.", null)] };
  assert.deepEqual(
    run([urgent, undated, explicit]).map((row) => row.id),
    ["a", "c", "b"],
  );
});
test("negated urgency cannot promote a customer or erase explicit purchase intent", () => {
  const data = client("a", ["Quero comprar o perfume hoje, mas não é urgente."]);
  const row = run([data])[0];
  assert.equal(row.group, "first");
  assert.equal(row.urgent, false);
  assert.equal(row.analyses[0].result.category, "high");
  assert.equal(run([client("b", ["Quanto custa? Sem urgência."])])[0].urgent, false);
});
