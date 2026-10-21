const test = require("node:test");
const assert = require("node:assert/strict");
const model = require("../frontend/scripts/content-preparation-store.js");
test("caption fixture never invents price or availability", () => {
  const result = model.captionAlternatives({
    topic: "Barba",
    offering: "Serviço",
    business: "Barbearia",
    objective: "informar",
    tone: "simples",
  });
  assert.equal(result.source, "template_fixture");
  assert.equal(result.generated_by_ai, false);
  assert.equal(result.alternatives.length, 3);
  assert(!JSON.stringify(result).includes("R$"));
});
test("dates use explicit IANA zone and reject DST gaps and ambiguity", () => {
  assert.equal(
    model.zonedInstant("2026-11-01T10:30", "America/Fortaleza"),
    "2026-11-01T13:30:00.000Z",
  );
  assert.throws(() => model.zonedInstant("2026-03-08T02:30", "America/New_York"));
  assert.throws(() => model.zonedInstant("2026-11-01T01:30", "America/New_York"));
  assert.throws(() => model.zonedInstant("2026-02-30T10:30", "America/Fortaleza"));
});
test("shared scheduling requires explicit simulation opt-in and authenticated remote mode", () => {
  assert.equal(model.enabled(undefined, true), false);
  assert.equal(model.enabled({ mode: "simulation" }, false), false);
  assert.equal(model.enabled({ mode: "simulation" }, true), true);
});
