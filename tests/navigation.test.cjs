const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");

function navigationContext() {
  const messages = [];
  const calls = [];
  const fields = new Map([
    ["dateFrom", { value: "" }],
    ["dateTo", { value: "" }],
    ["customBox", { classList: { add() {}, remove() {} } }],
  ]);
  const context = vm.createContext({
    localStorage: { getItem: () => null },
    $: (id) => fields.get(id),
    selectedPeriod: "Este mês",
    customRange: null,
    currentView: "Visão Geral",
    window: { SocialMEIMotion: { reduced: true } },
    toast: (...message) => messages.push(message),
    updatePeriodLabel: () => calls.push("label"),
    closeDropdowns: () => calls.push("close"),
    renderCurrentView: () => calls.push("render"),
    showLoading: () => calls.push("loading"),
    hideLoading: () => calls.push("ready"),
    wait: async (duration) => calls.push(duration),
  });
  vm.runInContext(fs.readFileSync("frontend/scripts/navigation.js", "utf8"), context);
  // Renderers depend on the app shell; this fixture exercises period selection only.
  context.updatePeriodLabel = () => calls.push("label");
  return { context, fields, messages, calls };
}

test("custom periods reject missing or reversed dates without changing the selection", () => {
  const { context, fields, messages, calls } = navigationContext();
  context.applyCustomPeriod();
  assert.deepEqual(messages[0], ["Selecione as duas datas", "Informe a data inicial e a final."]);
  fields.get("dateFrom").value = "2026-10-14";
  fields.get("dateTo").value = "2026-10-13";
  context.applyCustomPeriod();
  assert.equal(messages[1][0], "Período inválido");
  assert.equal(context.selectedPeriod, "Este mês");
  assert.equal(context.customRange, null);
  assert.deepEqual(calls, []);
});

test("custom periods include both endpoints and refresh after updating the label", () => {
  const { context, fields, calls } = navigationContext();
  fields.get("dateFrom").value = "2026-10-13";
  fields.get("dateTo").value = "2026-10-14";
  context.applyCustomPeriod();
  assert.equal(context.selectedPeriod, "Personalizado");
  assert.equal(context.customRange.days, 2);
  assert.equal(context.customRange.from, "2026-10-13");
  assert.equal(context.customRange.to, "2026-10-14");
  assert.deepEqual(calls, ["label", "close", "render"]);
});

test("preset periods clear custom ranges and keep the reduced-motion loading sequence", async () => {
  const { context, calls } = navigationContext();
  context.customRange = { days: 2 };
  await context.selectPeriod("7 dias");
  assert.equal(context.selectedPeriod, "7 dias");
  assert.equal(context.customRange, null);
  assert.deepEqual(calls, ["label", "close", "loading", 0, "ready"]);
});
