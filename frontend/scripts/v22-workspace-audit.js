/* Existing workspace-bound audit only; account-wide security events stay private. */
(() => {
  const host = window.SocialMEIV22,
    auth = window.SocialMEIAuth;
  if (!host?.remote || !auth?.remote || window.SocialMEIWorkspaceAudit) return;
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
      !["owner", "admin"].includes(auth.current.papel) ||
      !location.hash.startsWith("#/config/conta") ||
      view.querySelector("[data-workspace-audit]")
    )
      return;
    const owner = scope(),
      section = el("section");
    section.dataset.workspaceAudit = "true";
    section.style.cssText =
      "margin:20px 0;padding:20px;border:1px solid var(--b);border-radius:16px;background:var(--w);color:var(--t)";
    section.append(el("h2", "Histórico de acessos, exportações e perfil do negócio"));
    const form = el("form"),
      dates = [];
    form.style.cssText = "display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin:14px 0";
    for (const title of ["Histórico desde", "Histórico até"]) {
      const label = el("label", title),
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
    const label = el("label", "Tipo de histórico"),
      kind = el("select");
    label.style.cssText = "display:grid;gap:6px;max-width:100%";
    kind.style.cssText = "padding:10px;background:var(--w);color:var(--t);max-width:100%";
    for (const [value, title] of [
      ["all", "Todos disponíveis"],
      ["team", "Equipe"],
      ["exports", "Exportações CSV"],
      ["settings", "Perfil e horários"],
    ]) {
      const option = el("option", title);
      option.value = value;
      kind.append(option);
    }
    label.append(kind);
    form.append(label);
    const filter = el("button", "Consultar histórico"),
      more = el("button", "Carregar eventos anteriores");
    filter.type = "submit";
    more.type = "button";
    filter.className = more.className = "btn o";
    more.hidden = true;
    form.append(filter);
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
      location.hash.startsWith("#/config/conta") &&
      scope() === owner &&
      revision === id;
    async function load(custom, append = false) {
      const id = ++revision;
      filter.disabled = more.disabled = kind.disabled = true;
      dates.forEach((n) => {
        n.disabled = true;
      });
      message.textContent = "Consultando histórico persistido…";
      if (!append) {
        content.replaceChildren();
        next = null;
        items = [];
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
        if (append) query.set("before", next);
        const data = await host.request("/audit/workspace?" + query);
        if (!alive(id)) return;
        if (
          data.workspace_id !== auth.current.negocio.id ||
          data.kind !== query.get("kind") ||
          !Array.isArray(data.items) ||
          data.items.length > 50 ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.start) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.end)
        )
          throw Error("Histórico não confirmado pelo servidor.");
        let previous = Number(query.get("before") || Number.MAX_SAFE_INTEGER);
        for (const item of data.items) {
          if (
            !Number.isSafeInteger(item.id) ||
            item.id < 1 ||
            item.id >= previous ||
            typeof item.action !== "string" ||
            !["team", "exports", "settings"].includes(item.kind) ||
            ![item.actor, item.target].every((n) => n === null || typeof n === "string") ||
            !Number.isFinite(Date.parse(item.at))
          )
            throw Error("Evento não confirmado pelo servidor.");
          previous = item.id;
        }
        if (
          data.next_before !== null &&
          (!Number.isSafeInteger(data.next_before) ||
            !data.items.length ||
            data.next_before !== previous)
        )
          throw Error("Paginação não confirmada pelo servidor.");
        dates[0].value = data.period.start;
        dates[1].value = data.period.end;
        query.delete("before");
        query.set("start", data.period.start);
        query.set("end", data.period.end);
        activeQuery = query.toString();
        next = data.next_before;
        items = append ? items.concat(data.items) : data.items;
        content.replaceChildren();
        if (!items.length) content.append(el("p", "Nenhum evento disponível neste período."));
        else {
          const table = el("table"),
            head = el("tr"),
            body = el("tbody");
          table.style.cssText = "width:100%;table-layout:fixed;overflow-wrap:anywhere";
          table.append(el("caption", "Operações registradas pelo servidor"));
          for (const title of ["Data", "Responsável", "Operação", "Conta afetada"])
            head.append(el("th", title));
          const th = el("thead");
          th.append(head);
          table.append(th);
          for (const item of items) {
            const row = el("tr");
            for (const value of [
              new Date(item.at).toLocaleString("pt-BR", { timeZone: data.period.timezone }),
              item.actor || "Não registrado",
              item.action,
              item.target || "—",
            ])
              row.append(el("td", value));
            body.append(row);
          }
          table.append(body);
          content.append(table);
        }
        content.append(el("p", data.description));
        more.hidden = next === null;
        message.textContent = "Histórico consultado · fuso: " + data.period.timezone;
      } catch (error) {
        if (alive(id)) {
          message.textContent = error.message || "Não foi possível consultar o histórico.";
          if (!append) content.replaceChildren();
        }
      } finally {
        if (alive(id)) {
          filter.disabled = more.disabled = kind.disabled = false;
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
    kind.onchange = () => load(!!dates[0].value && !!dates[1].value);
    more.onclick = () => {
      if (next !== null) load(true, true);
    };
    load(false);
  }
  window.SocialMEIWorkspaceAudit = { refresh: mount };
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
