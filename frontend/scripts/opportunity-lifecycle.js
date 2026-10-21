/* Persisted commercial follow-up, independent of demonstration analysis. */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  const api = SocialMEIOpportunityLifecycle;
  const auth = SocialMEIAuth;
  const host = document.createElement("section");
  host.id = "opportunityLifecycle";
  host.className = "management-stack";
  host.hidden = !auth.remote;
  host.setAttribute("aria-label", "Acompanhamento comercial");
  const parent = document.querySelector("#opportunitiesView .management-stack");
  if (!parent) return;
  parent.querySelector("header").after(host);
  const node = (tag, text) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const button = (text, action) => {
    const element = node("button", text);
    element.type = "button";
    element.className = "management-button";
    element.addEventListener("click", action);
    return element;
  };
  const heading = node("h3", "Acompanhamento comercial");
  heading.tabIndex = -1;
  const explanation = node(
    "p",
    "Frio, Morno e Quente indicam interesse. Venda realizada e Não avançou encerram a oportunidade e saem dos contadores de interesse. Sem resposta continua em andamento.",
  );
  const status = node("p");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const refresh = button("Atualizar oportunidades", () => run(() => store.reload()));
  const form = node("form");
  form.className = "content-preparation-fields";
  form.id = "opportunityCreateForm";
  const label = (text, input, target) => {
    const wrapper = node("label", text);
    wrapper.append(input);
    target.append(wrapper);
    return input;
  };
  const clients = label("Cliente", node("select"), form);
  clients.id = "opportunityClient";
  clients.required = true;
  const title = label("O que o cliente procura?", node("input"), form);
  title.id = "opportunityTitle";
  title.required = true;
  title.maxLength = 160;
  const interest = label("Interesse", node("select"), form);
  interest.id = "opportunityInterest";
  for (const [value, text] of Object.entries(api.INTEREST)) {
    const option = node("option", text);
    option.value = value;
    interest.append(option);
  }
  const create = node("button", "Criar oportunidade");
  create.type = "submit";
  create.className = "management-button";
  form.append(create);
  const filters = node("div");
  filters.className = "opportunity-controls";
  filters.setAttribute("role", "group");
  filters.setAttribute("aria-label", "Filtrar oportunidades");
  const list = node("div");
  list.id = "commercialOpportunityList";
  list.className = "management-stack";
  host.append(
    heading,
    explanation,
    status,
    refresh,
    form,
    filters,
    list,
    node(
      "p",
      "Mostrando até 100 oportunidades recentes deste negócio. Fechar uma oportunidade não altera pagamentos nem estoque.",
    ),
  );
  let selected = "open",
    scope = "",
    loaded = false;
  const store = api.createStore({
    identity: () => auth.current,
    headers: () => ({ "X-SocialMEI-Client": "browser", ...auth.headers() }),
    origin: location.origin,
    fetch: (...args) => fetch(...args),
    change: controls,
  });
  function controls() {
    const state = store.snapshot();
    const writable =
      auth.remote &&
      state.ready &&
      !state.busy &&
      ["owner", "admin", "member"].includes(state.role);
    form.querySelectorAll("input,select,button").forEach((element) => {
      element.disabled = !writable;
    });
    list.querySelectorAll("[data-write]").forEach((element) => {
      element.disabled = !writable;
    });
    refresh.disabled = !auth.remote || !auth.current || state.busy;
  }
  async function run(action, success) {
    const keepFocus = host.contains(document.activeElement);
    try {
      await action();
      if (success) success();
      status.textContent = "Alterações consultadas e salvas no negócio atual.";
      render();
      if (keepFocus) heading.focus();
    } catch (error) {
      status.textContent =
        error.message + " Seus campos foram preservados. Atualize se houver conflito.";
      controls();
    }
  }
  function writeButton(text, action) {
    const result = button(text, action);
    result.dataset.write = "";
    return result;
  }
  function render() {
    const state = store.snapshot();
    filters.replaceChildren();
    for (const [value, text] of Object.entries({
      open: "Em andamento",
      ...api.INTEREST,
      won: "Venda realizada",
      lost: "Não avançou",
    })) {
      const item = button(`${text} (${state.totals[value]})`, () => {
        selected = value;
        render();
      });
      item.setAttribute("aria-pressed", String(selected === value));
      filters.append(item);
    }
    list.replaceChildren();
    const rows = state.items.filter((row) =>
      selected in api.INTEREST
        ? row.outcome === "open" && row.interest_level === selected
        : row.outcome === selected,
    );
    if (!rows.length) list.append(node("p", "Nenhuma oportunidade neste filtro."));
    for (const row of rows) {
      const card = node("article");
      card.className = "management-card";
      card.dataset.commercialOpportunity = row.id;
      card.append(
        node("h4", row.client_name + " · " + row.title),
        node("p", `${api.INTEREST[row.interest_level]} · ${api.OUTCOME[row.outcome]}`),
      );
      if (row.outcome_reason)
        card.append(node("p", api.REASONS[row.outcome_reason] || row.outcome_reason));
      if (row.outcome_note) card.append(node("p", row.outcome_note));
      if (row.sale_id)
        card.append(
          node("p", `Venda vinculada: ${row.sale_id}. O vínculo não confirma pagamento.`),
        );
      if (row.sale_unavailable || row.sale_status === "cancelada")
        card.append(
          node(
            "p",
            "A venda vinculada foi cancelada ou está indisponível. Confira Vendas; o histórico comercial foi preservado.",
          ),
        );
      const details = node("details"),
        summary = node("summary", "Atualizar acompanhamento");
      details.append(summary);
      if (row.outcome === "open") {
        const level = label("Interesse", node("select"), details);
        for (const [value, text] of Object.entries(api.INTEREST)) {
          const option = node("option", text);
          option.value = value;
          level.append(option);
        }
        level.value = row.interest_level;
        details.append(
          writeButton("Salvar interesse", () =>
            run(() => store.update(row, { interest_level: level.value })),
          ),
        );
        const reason = label("Motivo de não avançar", node("select"), details);
        for (const [value, text] of Object.entries(api.REASONS).filter(
          ([value]) => value !== "sale_completed",
        )) {
          const option = node("option", text);
          option.value = value;
          reason.append(option);
        }
        const note = label("Observação (opcional)", node("textarea"), details);
        note.maxLength = 1000;
        details.append(
          writeButton("Venda realizada", () =>
            run(() => store.close(row, "won", "sale_completed", note.value)),
          ),
          writeButton("Não avançou", () =>
            run(() => store.close(row, "lost", reason.value, note.value)),
          ),
        );
      } else {
        const reason = label("Motivo para reabrir", node("input"), details);
        reason.maxLength = 300;
        details.append(
          writeButton("Reabrir oportunidade", () => {
            if (!reason.value.trim()) {
              status.textContent = "Informe por que deseja reabrir.";
              reason.focus();
              return;
            }
            run(() => store.reopen(row, reason.value.trim()));
          }),
        );
      }
      const sale = label("Venda já registrada para este cliente", node("select"), details);
      const placeholder = node("option", "Selecione uma venda ativa");
      placeholder.value = "";
      sale.append(placeholder);
      if (SocialMEISales.connectionState === "ready")
        for (const value of appData.vendas.filter(
          (item) =>
            item.cliente_id === row.client_id &&
            !item.excluida &&
            ["Pendente", "Pago"].includes(item.status),
        )) {
          const option = node(
            "option",
            `Venda ${value.id} · ${value.item || "Item"} · ${value.status}`,
          );
          option.value = value.id;
          sale.append(option);
        }
      details.append(
        node(
          "p",
          "Registre a venda em Vendas antes de vinculá-la. Uma venda só pode ser vinculada a uma oportunidade.",
        ),
      );
      details.append(
        writeButton("Vincular venda existente", () => {
          const value = Number(sale.value);
          if (!Number.isSafeInteger(value) || value < 1) {
            status.textContent =
              "Selecione uma venda ativa deste cliente. Se ela acabou de ser criada, atualize as oportunidades.";
            sale.focus();
            return;
          }
          run(() => store.linkSale(row, value));
        }),
      );
      card.append(details);
      const history = node("div");
      history.setAttribute("role", "status");
      card.append(
        button("Ver histórico", async () => {
          try {
            const events = await store.history(row.id);
            history.replaceChildren();
            for (const event of events)
              history.append(
                node(
                  "p",
                  `${event.created_at || ""} · ${{ create: "Criação", edit: "Interesse alterado", close: "Encerramento", reopen: "Reabertura", sale: "Venda vinculada" }[event.action] || "Atualização"} · Responsável ${event.actor_id || "indisponível"} · ${api.REASONS[event.reason] || event.reason || ""} · ${api.OUTCOME[event.current?.outcome] || ""} · ${api.INTEREST[event.current?.interest_level] || ""} · Revisão ${event.current?.revision || ""}`,
                ),
              );
            if (!events.length) history.append(node("p", "Sem eventos disponíveis."));
          } catch (error) {
            history.textContent = error.message;
          }
        }),
        history,
      );
      list.append(card);
    }
    controls();
  }
  function syncClients() {
    const previous = clients.value;
    clients.replaceChildren();
    const empty = node("option", "Selecione um cliente cadastrado");
    empty.value = "";
    clients.append(empty);
    if (SocialMEIClients.connectionState === "ready")
      for (const row of appData.clientes) {
        const option = node("option", row.nome);
        option.value = row.id;
        clients.append(option);
      }
    clients.value = previous;
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const client_id = Number(clients.value);
    if (!client_id || !title.value.trim()) return;
    run(
      () => store.create({ client_id, title: title.value.trim(), interest_level: interest.value }),
      () => {
        title.value = "";
      },
    );
  });
  function sync() {
    const current = store.snapshot();
    if (scope !== current.scope) {
      scope = current.scope;
      loaded = false;
      form.reset();
      render();
    }
    syncClients();
    controls();
    if (currentView === "Oportunidades" && auth.remote && auth.current && !loaded) {
      loaded = true;
      run(() => store.reload());
    }
    if (!auth.remote || !auth.current)
      status.textContent =
        "O acompanhamento compartilhado exige entrar na versão com backend. A análise demonstrativa abaixo continua separada.";
  }
  document.addEventListener("socialmei-view-change", sync);
  document.addEventListener("socialmei-data-change", sync);
  auth.ready.then(sync);
  render();
});
