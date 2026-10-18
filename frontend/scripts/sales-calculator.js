/* Manual sales forecasting: pure calculations; no CRM writes or requests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.SocialMEISalesCalculator = api;
    api.mount();
  }
})(globalThis, function () {
  "use strict";
  const INITIAL_RATES = Object.freeze([20, 40, 60]);
  const asNumber = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const asMoney = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  let rootEl = null;
  function integer(value, name) {
    if (!Number.isSafeInteger(value) || value < 0 || value > 1000000)
      throw new RangeError(name + " deve ser inteiro de 0 a 1.000.000.");
  }
  function calculate(input) {
    if (!input) throw new TypeError("Informe as hipóteses.");
    const { count, ticket, closed = null, rates } = input;
    integer(count, "Oportunidades");
    if (typeof ticket !== "number" || !Number.isFinite(ticket) || ticket < 0 || ticket > 1000000000)
      throw new RangeError("Ticket médio inválido.");
    if (closed !== null) {
      integer(closed, "Fechamentos");
      if (closed > count) throw new RangeError("Fechamentos excedem oportunidades.");
    }
    if (
      !Array.isArray(rates) ||
      rates.length !== 3 ||
      rates.some(
        (rate) => typeof rate !== "number" || !Number.isFinite(rate) || rate < 0 || rate > 100,
      )
    )
      throw new RangeError("Taxas inválidas.");
    const values = rates.map((rate) => {
      const expectedSales = (count * rate) / 100;
      const grossRevenue = Math.round(expectedSales * ticket * 100) / 100;
      return { rate, expectedSales, grossRevenue };
    });
    return {
      scenarios: values.map((scenario) => ({
        ...scenario,
        difference: Math.round((scenario.grossRevenue - values[1].grossRevenue) * 100) / 100,
      })),
      closedRevenue: closed === null ? null : Math.round(closed * ticket * 100) / 100,
    };
  }
  function mount() {
    rootEl = document.getElementById("salesCalculator");
    if (!rootEl) return;
    const el = (id) => document.getElementById(id);
    const put = (id, value) => {
      el(id).textContent = value;
    };
    const read = (id) => {
      const node = el(id);
      return node.value.trim() === "" ? null : node.validity.badInput ? NaN : Number(node.value);
    };
    const draw = () => {
      const count = read("salesCalcCount");
      const ticket = read("salesCalcTicket");
      const closed = read("salesCalcClosed");
      const rates = INITIAL_RATES.map((_, i) => Number(el("salesCalcRate" + i).value));
      rates.forEach((rate, i) => put("salesCalcRateLabel" + i, rate + "%"));
      const problems = {
        salesCalcCount:
          count !== null && (!Number.isSafeInteger(count) || count < 0 || count > 1000000)
            ? "Informe um inteiro entre 0 e 1.000.000."
            : "",
        salesCalcTicket:
          ticket !== null && (!Number.isFinite(ticket) || ticket < 0 || ticket > 1000000000)
            ? "Informe um ticket de R$ 0 a R$ 1 bilhão."
            : "",
        salesCalcClosed:
          closed !== null &&
          (!Number.isSafeInteger(closed) ||
            closed < 0 ||
            closed > 1000000 ||
            (Number.isSafeInteger(count) && closed > count))
            ? "Informe um número válido, até o total de oportunidades."
            : "",
      };
      Object.entries(problems).forEach(([id, problem]) => {
        put(id + "Error", problem);
        el(id).setAttribute("aria-invalid", String(Boolean(problem)));
      });
      let result = null;
      const missing = count === null || ticket === null;
      const invalid = Object.values(problems).some(Boolean);
      if (!missing && !invalid) result = calculate({ count, ticket, closed, rates });
      const max = result ? Math.max(1, ...result.scenarios.map((item) => item.grossRevenue)) : 1;
      INITIAL_RATES.forEach((_, i) => {
        const s = result && result.scenarios[i];
        put("salesCalcSales" + i, s ? asNumber.format(s.expectedSales) : "—");
        put("salesCalcRevenue" + i, s ? asMoney.format(s.grossRevenue) : "—");
        put(
          "salesCalcDelta" + i,
          i === 1
            ? "Cenário de referência"
            : s
              ? (s.difference >= 0 ? "+ " : "− ") +
                asMoney.format(Math.abs(s.difference)) +
                " em relação ao intermediário"
              : "—",
        );
        el("salesCalcBar" + i).style.width = s ? (s.grossRevenue / max) * 100 + "%" : "0%";
      });
      put(
        "salesCalcClosedRevenue",
        result && result.closedRevenue !== null ? asMoney.format(result.closedRevenue) : "—",
      );
      put(
        "salesCalcStatus",
        invalid
          ? "Corrija os campos para atualizar a simulação."
          : missing
            ? "Preencha oportunidades e ticket médio para calcular."
            : "Simulação atualizada. Nenhum dado foi salvo ou enviado.",
      );
    };
    rootEl._salesCalcDraw = draw;
    rootEl.addEventListener("input", (event) => {
      if (event.target.matches("input")) draw();
    });
    el("salesCalcReset").addEventListener("click", reset);
    draw();
  }
  function reset() {
    if (!rootEl) return;
    ["salesCalcCount", "salesCalcTicket", "salesCalcClosed"].forEach((id) => {
      document.getElementById(id).value = "";
    });
    INITIAL_RATES.forEach((rate, i) => {
      document.getElementById("salesCalcRate" + i).value = String(rate);
    });
    rootEl._salesCalcDraw();
  }
  return Object.freeze({ calculate, mount, reset, INITIAL_RATES });
});
