const { test } = require("node:test");
const assert = require("node:assert/strict");
const model = require("../frontend/scripts/business-profile.js");
const base = { businessName: "Negócio sintético", completed: true };
test("barber tools prioritize chosen services; future modules never receive invented routes", () => {
  const tools = model.contextualTools({
    ...base,
    segment: "barber",
    offers: ["services"],
    capabilities: { appointments: true, deliveries: true, orders: true },
    modules: ["clients", "services", "appointments", "orders", "deliveries", "sales"],
  });
  assert.deepEqual(
    tools.active.map((item) => item.id),
    ["services", "clients", "sales"],
  );
  assert.deepEqual(
    tools.future.map((item) => item.id),
    ["appointments", "orders", "deliveries"],
  );
  assert(tools.active.every((item) => item.view));
  assert(tools.future.every((item) => !item.view));
});
test("perfume and mixed businesses use capabilities, without hiding essential modules", () => {
  const profile = {
    ...base,
    segment: "barber",
    offers: ["products", "services"],
    capabilities: { inventory: true },
    modules: ["products", "services", "inventory", "sales"],
  };
  assert.deepEqual(
    model.contextualTools(profile).active.map((item) => item.id),
    ["services", "products", "inventory", "sales"],
  );
  assert.deepEqual(model.contextualTools({ ...profile, modules: [] }).active, []);
});
test("selected offerings override segment suggestions; service names and product categories remain distinct", () => {
  const suggestions = model.catalogSuggestions({
    ...base,
    segment: "barber",
    offers: ["products", "services"],
    services: ["Corte masculino", "Barba"],
    productCategories: ["Perfumes"],
  });
  assert.deepEqual(
    suggestions.map((item) => [item.kind, item.name]),
    [
      ["Serviço", "Corte masculino"],
      ["Serviço", "Barba"],
      ["Produto", ""],
    ],
  );
  assert.equal(suggestions[2].label, "Perfumes");
  assert(suggestions.every((item) => item.preco === undefined && item.estoque === undefined));
});
test("service suggestions deduplicate accents/whitespace and ignore already registered services, not physical products", () => {
  const profile = {
    ...base,
    segment: "tailoring",
    offers: ["services"],
    services: [" Reparação ", "REPARACAO", "Ajustes"],
  };
  const suggestions = model.catalogSuggestions(profile, [
    { nome: "reparacao", tipo: "Serviço" },
    { nome: "Ajustes", tipo: "Produto" },
  ]);
  assert.deepEqual(
    suggestions.map((item) => item.label),
    ["Ajustes"],
  );
});
test("ignored suggestions survive normalization and can be restored, including long labels", () => {
  const profile = { ...base, segment: "other", offers: ["services"], services: ["x".repeat(120)] };
  const item = model.catalogSuggestions(profile)[0];
  profile.ignoredSuggestions = [item.id];
  assert.equal(model.catalogSuggestions(model.normalize(profile)).length, 0);
  profile.ignoredSuggestions = [];
  assert.equal(model.catalogSuggestions(profile).length, 1);
});
test("segment fallbacks stay configurable and absent profiles are safe", () => {
  const suggestions = model.catalogSuggestions({
    ...base,
    segment: "tailoring",
    offers: ["services"],
  });
  assert(suggestions.some((item) => item.name === "Ajustes"));
  assert.equal(model.catalogSuggestions(null).length, 0);
  assert.deepEqual(model.contextualTools(null), { active: [], future: [] });
});
