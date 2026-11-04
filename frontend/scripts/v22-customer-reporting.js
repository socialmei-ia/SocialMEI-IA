/* Customer purchase indicators from the authenticated business only. */
(() => {
  const host = window.SocialMEIV22,
    auth = window.SocialMEIAuth;
  if (!host?.remote || !auth?.remote || window.SocialMEICustomerReports) return;
  const el = (tag, text) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = String(text);
    return n;
  };
  const scope = () => auth.current && `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  function mount() {
    const view = document.getElementById("v");
    if (
      !view ||
      !scope() ||
      !location.hash.startsWith("#/relatorios") ||
      view.querySelector("[data-customer-report]")
    )
      return;
    const owner = scope(),
      section = el("section");
    section.dataset.customerReport = "true";
    section.className = "sm-data";
    section.style.cssText =
      "margin:20px 0;padding:20px;border:1px solid var(--b);border-radius:16px;background:var(--w);color:var(--t)";
    section.append(el("h2", "Clientes e compras"));
    const form = el("form"),
      dates = [];
    form.style.cssText = "display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:14px 0";
    for (const text of ["Clientes desde", "Clientes até"]) {
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
    const filter = el("button", "Consultar clientes do período"),
      refresh = el("button", "Atualizar clientes");
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
      message.textContent = "Consultando clientes e vendas salvas…";
      content.replaceChildren();
      try {
        const query = custom
          ? "?" + new URLSearchParams({ start: dates[0].value, end: dates[1].value })
          : "";
        const data = await host.request("/reporting/customers" + query);
        if (!alive(id)) return;
        if (
          data.workspace_id !== auth.current.negocio.id ||
          ![data.new_customers, data.buyers, data.repeat_buyers, data.returning_buyers].every(
            (n) => Number.isSafeInteger(n) && n >= 0,
          ) ||
          typeof data.identification_available !== "boolean" ||
          !Array.isArray(data.customers) ||
          data.customers.length > 10 ||
          (!data.identification_available && data.customers.length) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.start) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.end)
        )
          throw Error("Indicadores de clientes não confirmados pelo servidor.");
        dates[0].value = data.period.start;
        dates[1].value = data.period.end;
        const list = el("ul");
        for (const [title, value] of [
          ["Clientes cadastrados no período", data.new_customers],
          ["Clientes com compras no período", data.buyers],
          ["Recorrentes dentro do período", data.repeat_buyers],
          ["Voltaram após uma compra anterior", data.returning_buyers],
        ])
          list.append(el("li", title + ": " + value));
        content.append(list);
        if (!data.identification_available)
          content.append(
            el("p", "Seu acesso permite indicadores agregados, sem identificação de clientes."),
          );
        else if (!data.customers.length)
          content.append(el("p", "Nenhum cliente com compra válida neste período."));
        else {
          const table = el("table"),
            head = el("tr"),
            body = el("tbody");
          table.style.cssText = "width:100%;table-layout:fixed;overflow-wrap:anywhere";
          table.append(el("caption", "Até dez clientes por frequência de compra"));
          for (const label of ["Cliente", "Compras", "Vendas registradas"])
            head.append(el("th", label));
          const th = el("thead");
          th.append(head);
          table.append(th);
          for (const item of data.customers) {
            if (
              typeof item.name !== "string" ||
              !Number.isSafeInteger(item.purchases) ||
              item.purchases < 1 ||
              !/^\d+\.\d{2}$/.test(item.total)
            )
              throw Error("Indicadores de clientes não confirmados pelo servidor.");
            const row = el("tr"),
              [integer, fraction] = item.total.split(".");
            for (const value of [
              item.name,
              item.purchases,
              "R$ " + integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + fraction,
            ])
              row.append(el("td", value));
            body.append(row);
          }
          table.append(body);
          content.append(table);
        }
        for (const text of [data.description, data.repeat_description, data.returning_description])
          content.append(el("p", text));
        message.textContent = "Clientes e compras consultados · fuso: " + data.period.timezone;
      } catch (error) {
        if (alive(id)) {
          content.replaceChildren();
          message.textContent = error.message || "Não foi possível consultar os clientes.";
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
  window.SocialMEICustomerReports = { refresh: mount };
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
