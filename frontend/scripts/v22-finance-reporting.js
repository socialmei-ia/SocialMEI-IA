/* Recorded financial flows; never a bank balance or profit estimate. */
(() => {
  const host = window.SocialMEIV22,
    auth = window.SocialMEIAuth;
  if (!host?.remote || !auth?.remote || window.SocialMEIFinanceReports) return;
  const el = (tag, text) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = String(text);
    return n;
  };
  const scope = () => auth.current && `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  const money = (value) => {
    if (typeof value !== "string" || !/^-?\d+\.\d{2}$/.test(value))
      throw Error("Valores financeiros não confirmados pelo servidor.");
    const [integer, fraction] = value.split(".");
    return "R$ " + integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + fraction;
  };
  function mount() {
    const view = document.getElementById("v");
    if (
      !view ||
      !scope() ||
      !location.hash.startsWith("#/relatorios") ||
      view.querySelector("[data-finance-report]")
    )
      return;
    const owner = scope(),
      section = el("section");
    section.dataset.financeReport = "true";
    section.className = "sm-data";
    section.style.cssText =
      "margin:20px 0;padding:20px;border:1px solid var(--b);border-radius:16px;background:var(--w);color:var(--t)";
    section.append(el("h2", "Financeiro registrado"));
    const form = el("form"),
      dates = [];
    form.style.cssText = "display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:14px 0";
    for (const text of ["Financeiro desde", "Financeiro até"]) {
      const label = el("label", text),
        input = el("input");
      label.style.cssText = "display:grid;gap:6px;max-width:100%";
      input.type = "date";
      input.required = true;
      input.style.cssText =
        "padding:10px;background:var(--w);color:var(--t);border:1px solid var(--b);border-radius:8px;max-width:100%;box-sizing:border-box";
      label.append(input);
      form.append(label);
      dates.push(input);
    }
    const filter = el("button", "Consultar financeiro do período"),
      refresh = el("button", "Atualizar financeiro");
    filter.type = "submit";
    refresh.type = "button";
    filter.className = refresh.className = "btn o";
    form.append(filter, refresh);
    const message = el("p"),
      content = el("div");
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    section.append(form, message, content);
    view.append(section);
    let revision = 0;
    const alive = (id) =>
      section.isConnected &&
      location.hash.startsWith("#/relatorios") &&
      scope() === owner &&
      revision === id;
    async function load(custom) {
      const id = ++revision;
      filter.disabled = refresh.disabled = true;
      dates.forEach((n) => {
        n.disabled = true;
      });
      message.textContent = "Consultando lançamentos persistidos…";
      content.replaceChildren();
      try {
        const query = custom
          ? "?" + new URLSearchParams({ start: dates[0].value, end: dates[1].value })
          : "";
        const data = await host.request("/reporting/finance" + query);
        if (!alive(id)) return;
        if (
          data.workspace_id !== auth.current.negocio.id ||
          !Array.isArray(data.daily) ||
          data.daily.length > 366 ||
          !Number.isSafeInteger(data.undated_paid_count) ||
          data.undated_paid_count < 0 ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.start) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.end)
        )
          throw Error("Indicadores financeiros não confirmados pelo servidor.");
        dates[0].value = data.period.start;
        dates[1].value = data.period.end;
        const list = el("ul");
        for (const [label, value] of [
          ["Entradas registradas como pagas", data.paid.incoming],
          ["Saídas registradas como pagas", data.paid.outgoing],
          ["Saldo dos lançamentos pagos no período", data.paid.balance],
          ["Saldo do período anterior", data.previous.balance],
          ["Variação do saldo entre os períodos", data.balance_change],
          ["A receber por vencimento", data.pending.incoming],
          ["A pagar por vencimento", data.pending.outgoing],
        ])
          list.append(el("li", label + ": " + money(value)));
        content.append(
          list,
          el("p", "Comparação: " + data.previous.start + " a " + data.previous.end),
        );
        if (data.undated_paid_count)
          content.append(
            el(
              "p",
              `Atenção: ${data.undated_paid_count} lançamento(s) pago(s) com vencimento neste período não têm data de pagamento e não entram no saldo.`,
            ),
          );
        if (!data.paid.count) content.append(el("p", "Nenhum pagamento registrado neste período."));
        else {
          const table = el("table"),
            head = el("tr"),
            body = el("tbody");
          table.style.cssText = "width:100%;table-layout:fixed;overflow-wrap:anywhere";
          table.append(el("caption", "Evolução diária pela data de pagamento"));
          for (const label of ["Data", "Entradas", "Saídas", "Saldo"]) head.append(el("th", label));
          const th = el("thead");
          th.append(head);
          table.append(th);
          for (const item of data.daily) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(item.date)) throw Error("Data financeira inválida.");
            const row = el("tr");
            for (const value of [
              item.date.split("-").reverse().join("/"),
              money(item.incoming),
              money(item.outgoing),
              money(item.balance),
            ])
              row.append(el("td", value));
            body.append(row);
          }
          table.append(body);
          content.append(table);
        }
        content.append(el("p", data.description), el("p", data.pending_description));
        message.textContent = "Financeiro consultado · fuso: " + data.period.timezone;
      } catch (error) {
        if (alive(id)) {
          content.replaceChildren();
          message.textContent = error.message || "Não foi possível consultar o financeiro.";
        }
      } finally {
        if (alive(id)) {
          filter.disabled = refresh.disabled = false;
          dates.forEach((n) => {
            n.disabled = false;
          });
        }
      }
    }
    form.onsubmit = (e) => {
      e.preventDefault();
      if (form.reportValidity()) load(true);
    };
    refresh.onclick = () => load(!!dates[0].value && !!dates[1].value);
    load(false);
  }
  window.SocialMEIFinanceReports = { refresh: mount };
  const previous = window.render;
  if (typeof previous === "function")
    window.render = function (...args) {
      const result = previous.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  queueMicrotask(mount);
})();
