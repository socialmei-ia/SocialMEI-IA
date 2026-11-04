/* Catalogue decisions use current stock, never inferred historical inventory. */
(() => {
  const host = window.SocialMEIV22,
    auth = window.SocialMEIAuth;
  if (!host?.remote || !auth?.remote || window.SocialMEIProductReports) return;
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
      view.querySelector("[data-product-report]")
    )
      return;
    const owner = scope(),
      section = el("section");
    section.dataset.productReport = "true";
    section.className = "sm-data";
    section.style.cssText =
      "margin:20px 0;padding:20px;border:1px solid var(--b);border-radius:16px;background:var(--w);color:var(--t)";
    section.append(el("h2", "Produtos que precisam de atenção"));
    const form = el("form"),
      dates = [];
    form.style.cssText = "display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:14px 0";
    for (const text of ["Produtos desde", "Produtos até"]) {
      const label = el("label", text),
        input = el("input");
      input.type = "date";
      input.required = true;
      label.style.cssText = "display:grid;gap:6px;max-width:100%";
      input.style.cssText =
        "padding:10px;background:var(--w);color:var(--t);border:1px solid var(--b);border-radius:8px;max-width:100%;box-sizing:border-box";
      label.append(input);
      form.append(label);
      dates.push(input);
    }
    const label = el("label", "Lista de produtos"),
      kind = el("select");
    label.style.cssText = "display:grid;gap:6px;max-width:100%";
    kind.style.cssText = "padding:10px;background:var(--w);color:var(--t);max-width:100%";
    for (const [value, text] of [
      ["low_stock", "Estoque baixo agora"],
      ["no_sales", "Sem vendas no período"],
    ]) {
      const option = el("option", text);
      option.value = value;
      kind.append(option);
    }
    label.append(kind);
    form.append(label);
    const filter = el("button", "Consultar produtos"),
      refresh = el("button", "Atualizar produtos"),
      more = el("button", "Carregar mais produtos");
    filter.type = "submit";
    refresh.type = more.type = "button";
    filter.className = refresh.className = more.className = "btn o";
    form.append(filter, refresh);
    more.hidden = true;
    const message = el("p"),
      content = el("div");
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    section.append(form, message, content, more);
    view.append(section);
    let revision = 0,
      next = null,
      items = [],
      activeQuery = null;
    const alive = (id) =>
      section.isConnected &&
      location.hash.startsWith("#/relatorios") &&
      scope() === owner &&
      revision === id;
    async function load(custom, append = false) {
      const id = ++revision;
      filter.disabled = refresh.disabled = more.disabled = kind.disabled = true;
      dates.forEach((n) => {
        n.disabled = true;
      });
      message.textContent = "Consultando catálogo persistido…";
      if (!append) {
        content.replaceChildren();
        items = [];
        next = null;
        more.hidden = true;
      }
      try {
        const query = append
          ? new URLSearchParams(activeQuery)
          : new URLSearchParams({ kind: kind.value });
        if (custom && !append) {
          query.set("start", dates[0].value);
          query.set("end", dates[1].value);
        }
        if (append) query.set("after", next);
        const data = await host.request("/reporting/products?" + query);
        if (!alive(id)) return;
        if (
          data.workspace_id !== auth.current.negocio.id ||
          data.kind !== query.get("kind") ||
          !Array.isArray(data.products) ||
          data.products.length > 50 ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.start) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.end) ||
          ![data.totals?.active_products, data.totals?.low_stock, data.totals?.no_sales].every(
            (n) => Number.isSafeInteger(n) && n >= 0,
          ) ||
          !(
            data.next_after === null ||
            (Number.isSafeInteger(data.next_after) &&
              data.next_after > Number(query.get("after") || 0))
          )
        )
          throw Error("Indicadores de produtos não confirmados pelo servidor.");
        let previous = Number(query.get("after") || 0);
        for (const p of data.products) {
          if (
            !Number.isSafeInteger(p.id) ||
            p.id <= previous ||
            typeof p.name !== "string" ||
            typeof p.category !== "string" ||
            ![p.stock, p.minimum].every((n) => Number.isSafeInteger(n) && n >= 0) ||
            !/^\d+\.\d{2}$/.test(p.price)
          )
            throw Error("Produto não confirmado pelo servidor.");
          previous = p.id;
        }
        if (data.next_after !== null && data.next_after !== previous)
          throw Error("Paginação não confirmada pelo servidor.");
        dates[0].value = data.period.start;
        dates[1].value = data.period.end;
        query.delete("after");
        query.set("start", data.period.start);
        query.set("end", data.period.end);
        activeQuery = query.toString();
        next = data.next_after;
        items = append ? items.concat(data.products) : data.products;
        content.replaceChildren();
        content.append(
          el(
            "p",
            `Produtos ativos: ${data.totals.active_products} · Estoque baixo atual: ${data.totals.low_stock} · Sem vendas no período: ${data.totals.no_sales}`,
          ),
        );
        if (!items.length) content.append(el("p", "Nenhum produto nesta lista."));
        else {
          const table = el("table"),
            head = el("tr"),
            body = el("tbody");
          table.style.cssText = "width:100%;table-layout:fixed;overflow-wrap:anywhere";
          table.append(
            el(
              "caption",
              data.kind === "low_stock" ? "Estoque baixo atual" : "Sem vendas no período",
            ),
          );
          for (const text of ["Produto", "Categoria", "Preço atual", "Estoque atual", "Mínimo"])
            head.append(el("th", text));
          const th = el("thead");
          th.append(head);
          table.append(th);
          for (const p of items) {
            const row = el("tr"),
              [integer, fraction] = p.price.split(".");
            for (const value of [
              p.name,
              p.category || "Sem categoria",
              "R$ " + integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + fraction,
              p.stock,
              p.minimum,
            ])
              row.append(el("td", value));
            body.append(row);
          }
          table.append(body);
          content.append(table);
        }
        content.append(el("p", data.description), el("p", data.sales_description));
        more.hidden = next === null;
        message.textContent = "Catálogo consultado · fuso: " + data.period.timezone;
      } catch (error) {
        if (alive(id)) {
          message.textContent = error.message || "Não foi possível consultar os produtos.";
          if (!append) content.replaceChildren();
        }
      } finally {
        if (alive(id)) {
          filter.disabled = refresh.disabled = more.disabled = kind.disabled = false;
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
    kind.onchange = () => load(!!dates[0].value && !!dates[1].value);
    more.onclick = () => {
      if (next !== null) load(true, true);
    };
    load(false);
  }
  window.SocialMEIProductReports = { refresh: mount };
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
