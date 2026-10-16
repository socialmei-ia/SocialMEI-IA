const assert = require("node:assert/strict");
const test = require("node:test");
const { analyzeMessage, MAX_LENGTH } = require("../prototypes/opportunities/intent-engine.js");
const cases = [
  ["explicit purchase", "Quero comprar o 212 VIP.", "high", ["purchase", "specific_item"]],
  [
    "requested combination",
    "Quanto custa o 212 VIP? Tem pronta entrega? Consegue entregar hoje?",
    "high",
    ["price", "availability", "delivery", "urgency", "specific_item"],
  ],
  ["short price question", "Preço?", "initial", ["price"]],
  ["business model is not an item", "Como funciona o modelo de negócio?", "insufficient", []],
  ["isolated price", "Quanto custa?", "initial", ["price"]],
  ["item and stock", "Tem o iPhone 15 em estoque?", "initial", ["availability", "specific_item"]],
  ["urgency alone", "Preciso disso hoje, é urgente!", "insufficient", ["urgency"]],
  ["implicit availability", "Tem o 212 VIP?", "initial", ["availability", "specific_item"]],
  ["not interested", "Não estou interessado nesse perfume.", "declined", ["decline"]],
  ["neutral greeting", "Bom dia, tudo bem?", "insufficient", []],
  ["positive sentiment", "Amei seu atendimento, parabéns!", "insufficient", []],
  ["positive product sentiment", "Adorei esse perfume!", "insufficient", ["item"]],
  [
    "negative sentiment with purchase",
    "Estou irritado, mas quero comprar o iPhone 16.",
    "high",
    ["purchase"],
  ],
  ["negation", "Não quero comprar o 212 VIP.", "declined", ["decline"]],
  ["negation without accent", "NAO QUERO COMPRAR.", "declined", ["decline"]],
  ["negated future", "Não vou comprar agora.", "declined", ["decline"]],
  ["abandonment", "Desisti. Pode cancelar.", "declined", ["decline"]],
  [
    "explicit conflict",
    "Quero comprar, mas não quero comprar agora.",
    "conflicting",
    ["purchase", "decline"],
  ],
  [
    "refusal and a price question",
    "Não quero comprar esse. Quanto custa o Malbec?",
    "conflicting",
    ["decline", "price"],
  ],
  [
    "exploration",
    "Só estou pesquisando. Quanto custa o 212 VIP?",
    "exploratory",
    ["exploration", "price"],
  ],
  ["uncertainty", "Não sei se quero comprar esse perfume.", "unclear", ["uncertainty"]],
  [
    "conditional",
    "Se baixar o preço, quero comprar o 212 VIP.",
    "unclear",
    ["condition", "purchase"],
  ],
  [
    "objection",
    "Quero comprar a camisa, mas está muito caro.",
    "unclear",
    ["objection", "purchase"],
  ],
  ["quote request", "Pode fazer um orçamento para troca de tela?", "initial", ["quote", "item"]],
  [
    "quantity",
    "Quanto custa para levar 3 unidades desse perfume?",
    "initial",
    ["price", "quantity"],
  ],
  ["payment", "Vocês aceitam Pix?", "initial", ["payment"]],
  ["delivery question", "Consegue entregar amanhã?", "initial", ["delivery"]],
  [
    "post-sale context",
    "Minha entrega não chegou. Quero saber o prazo de entrega.",
    "insufficient",
    ["after_sales"],
  ],
  ["reported speech", 'Ele disse "quero comprar o 212 VIP".', "unclear", ["reported"]],
  ["negated withdrawal", "Não desisti, só estou pesquisando.", "exploratory", ["exploration"]],
  [
    "negation of limitation",
    "Não só quero comprar, também preciso de 2 unidades.",
    "high",
    ["purchase", "quantity"],
  ],
  ["negated delivery", "Não preciso de entrega. Quanto custa o perfume?", "initial", ["price"]],
  ["non-commercial closing", "Quero fechar a janela do navegador.", "insufficient", []],
  ["empty", "", "insufficient", []],
  ["whitespace", " \n\t ", "insufficient", []],
  ["HTML is just text", '<img src=x onerror="alert(1)">', "insufficient", []],
  [
    "arbitrary named model",
    'Quero comprar o produto "Sabonete Flor do Campo".',
    "high",
    ["purchase", "specific_item"],
  ],
  [
    "unknown model still explicit",
    "Quero comprar o modelo XZ-927.",
    "high",
    ["purchase", "specific_item"],
  ],
];
for (const [name, message, category, ids] of cases) {
  test(name, () => {
    const result = analyzeMessage(message);
    assert.equal(result.category, category);
    for (const id of ids)
      assert(
        result.signals.some((signal) => signal.id === id),
        `Missing ${id}`,
      );
    assert(result.label && result.explanation && result.nextStep && result.rule);
    assert(Array.isArray(result.missingInformation) && result.limitations.length > 0);
    assert(!("score" in result) && !("probability" in result));
    for (const signal of result.signals) {
      assert(["positive", "negative", "ambiguous"].includes(signal.polarity));
      assert(signal.evidence.length > 0);
      for (const evidence of signal.evidence) {
        assert.equal(message.slice(evidence.start, evidence.end), evidence.text);
        assert(
          evidence.start >= 0 && evidence.end <= message.length && evidence.end > evidence.start,
        );
      }
    }
  });
}
test("negated purchases never become affirmative evidence", () => {
  for (const text of [
    "Não quero comprar.",
    "Nunca vou comprar isso.",
    "Nem pretendo contratar esse serviço.",
    "Não desejo mais comprar.",
  ]) {
    const result = analyzeMessage(text);
    assert.notEqual(result.category, "high");
    assert(!result.signals.some((s) => s.id === "purchase" && s.polarity === "positive"));
  }
});
test("decomposed accents and emoji retain exact evidence offsets", () => {
  const text = "🙂 NA\u0303O quero comprar. Quanto custa o 212 VIP?";
  const result = analyzeMessage(text);
  assert.equal(result.category, "conflicting");
  for (const signal of result.signals)
    for (const e of signal.evidence) assert.equal(text.slice(e.start, e.end), e.text);
});
test("deterministic outputs and no retained history", () => {
  const first = analyzeMessage(cases[1][1]);
  analyzeMessage("Não quero comprar.");
  assert.deepEqual(analyzeMessage(cases[1][1]), first);
});
test("length and type limits are explicit", () => {
  assert.throws(() => analyzeMessage(null), TypeError);
  assert.throws(() => analyzeMessage("a".repeat(MAX_LENGTH + 1)), RangeError);
  assert.equal(analyzeMessage("a".repeat(MAX_LENGTH)).category, "insufficient");
});
