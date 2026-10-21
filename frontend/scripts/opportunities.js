/* Native Opportunities: read-only experimental analysis, never a transport or CRM writer. */
const SocialMEIOpportunities = (() => {
  let demoEnabled = false,
    reviews = {},
    rows = [];
  const byId = (id) => document.getElementById(id);
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const button = (text, attribute, value = "") => {
    const element = node("button", text, "management-button");
    element.type = "button";
    element.setAttribute(attribute, value);
    return element;
  };
  const remote = () =>
    !SocialMEIDemoData.enabled() && (SocialMEIAuth.remote || SocialMEIClients.remote);
  function findConversation(row) {
    if (SocialMEIDemoData.enabled()) return null;
    const source = opportunityDemoSnapshot.find(
      (conversation) => `demo-${conversation.id}` === row.id,
    );
    return (
      source &&
      sessionData.conversas.find(
        (conversation) =>
          conversation.id === source.id &&
          conversation.nome === source.nome &&
          conversation.canal === source.canal &&
          !conversation.mensagens.some((message) => message.remoteId),
      )
    );
  }
  function linkedClient(row) {
    if (SocialMEIDemoData.enabled()) return null;
    return SocialMEIOpportunityData.linkedClient(
      findConversation(row),
      appData.clientes,
      SocialMEIClients.remote,
    );
  }
  function postSale(row, group = row.group) {
    const result = row.analyses.find((entry) => entry.message.id === row.decisiveMessageId)?.result;
    return (
      group === "support" &&
      result?.signals.some((signal) => signal.id === "after_sales") &&
      !result.signals.some((signal) => signal.id === "support")
    );
  }
  function displayLabel(row, group = row.group) {
    return postSale(row, group) ? "Conferir pós-venda" : SocialMEIPriority.GROUPS[group].label;
  }
  function nextStep(row) {
    return postSale(row)
      ? "Confirme se a pessoa precisa de orientação sobre o pedido. Um relato de entrega não representa uma nova intenção de compra."
      : row.nextStep;
  }
  function briefReason(row) {
    if (row.review)
      return "Encaminhamento ajustado por revisão humana. Confira o motivo nos detalhes.";
    if (postSale(row))
      return "O texto se refere a um pedido existente; confirme o acompanhamento necessário.";
    const result = row.analyses.find((entry) => entry.message.id === row.decisiveMessageId)?.result;
    const topics = {
      price: "preço",
      availability: "disponibilidade",
      delivery: "entrega",
      payment: "pagamento",
      quote: "orçamento",
    };
    const found = Object.entries(topics)
      .filter(([id]) =>
        result?.signals.some((signal) => signal.id === id && signal.polarity === "positive"),
      )
      .map(([, text]) => text);
    if (row.group === "inquiry" && found.length)
      return "Consultou " + new Intl.ListFormat("pt-BR").format(found) + ".";
    if (row.group === "first") return "Indicou interesse explícito em compra ou contratação.";
    if (row.group === "support") return "Relatou um problema ou pediu suporte; confira o contexto.";
    if (row.group === "unknown") return "Ainda faltam sinais para entender a necessidade.";
    return row.reasons[0];
  }
  function refreshRows() {
    if (SocialMEIDemoData.enabled()) {
      rows = SocialMEIPriority.prioritizeCustomers(
        businessViewConversations().map((conversation) => ({
          id: `test-${conversation.id}`,
          name: conversation.nome,
          conversationId: null,
          messages: conversation.mensagens.map((message, index) => ({
            id: `test-message-${index}`,
            author: "customer",
            text: message.texto,
            at: message.data + "T00:00:00-03:00",
          })),
        })),
        { referenceTime: new Date().toISOString(), reviews },
      );
      return;
    }
    const customers = SocialMEIOpportunityData.read({
      enabled: demoEnabled,
      remote: remote(),
      snapshot: opportunityDemoSnapshot,
      conversations: sessionData.conversas,
    });
    if (demoEnabled && !remote()) customers.push(...SocialMEIClientAnalysis.demoCustomers());
    rows = SocialMEIPriority.prioritizeCustomers(customers, {
      referenceTime: new Date().toISOString(),
      reviews,
    });
  }
  let profileScope;
  let identity,
    activeTab = "analysis",
    chanceFilter = "all",
    alertFilter = "open",
    levels = {},
    resolved = {};
  const levelsLabel = SocialMEIClientAnalysis.LEVELS;
  const status = (text) => {
    byId("clientAnalysisStatus").textContent = text;
  };
  function syncIdentity() {
    let next;
    try {
      profileScope ||= SocialMEIBusinessProfile.browserRepository();
      next = profileScope.scope();
    } catch {
      next = null;
    }
    if (identity !== next) {
      identity = next;
      demoEnabled = false;
      reviews = {};
      levels = {};
      resolved = {};
      rows = [];
      activeTab = "analysis";
      chanceFilter = "all";
      alertFilter = "open";
      clearAnalysis();
      byId("opportunityAnalysisStatus").textContent = "";
      if (byId("opportunityModal").classList.contains("open")) closeModal("opportunityModal");
    }
  }
  function presentation(row) {
    return SocialMEIClientAnalysis.present(row, levels[row.id]);
  }
  function filters(entries, attribute, selected) {
    const group = node("div", undefined, "client-analysis-filters");
    group.setAttribute("role", "group");
    group.setAttribute(
      "aria-label",
      attribute === "data-analysis-level" ? "Filtrar interesse" : "Filtrar alertas",
    );
    for (const [value, label, count] of entries) {
      const control = button(label + " · " + count, attribute, value);
      control.setAttribute("aria-pressed", String(value === selected));
      group.append(control);
    }
    return group;
  }
  function renderTabs() {
    const counts = { analysis: 0, chance: 0, attention: 0 };
    rows.forEach((row) => {
      const p = presentation(row);
      if (p.lane in counts && !(p.lane === "attention" && resolved[row.id])) counts[p.lane]++;
    });
    document.querySelectorAll("[data-analysis-tab]").forEach((tab) => {
      const selected = tab.dataset.analysisTab === activeTab;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      tab.querySelector("[data-analysis-count]").textContent = counts[tab.dataset.analysisTab];
      if (tab.dataset.analysisTab === "analysis") {
        tab.dataset.pending = String(counts.analysis > 0);
        tab.setAttribute("aria-label", `Em análise · ${counts.analysis} aguardando classificação`);
      }
    });
    byId("clientAnalysisTabs").style.setProperty(
      "--client-tab",
      ["analysis", "chance", "attention"].indexOf(activeTab),
    );
    byId("opportunityQueue").setAttribute("aria-labelledby", "clientTab-" + activeTab);
  }
  function evidence(row) {
    const list = node("div", undefined, "client-analysis-evidence");
    list.append(node("h4", "Mensagens e evidências"));
    row.analyses.forEach(({ message, result }) => {
      list.append(node("blockquote", message.text));
      result.signals.forEach((signal) => list.append(node("p", signal.label, "management-note")));
    });
    return list;
  }
  function customerCard(row, p) {
    const card = node("article", undefined, "client-analysis-card");
    card.dataset.nativeOpportunity = row.id;
    card.dataset.lane = p.lane;
    const head = node("div", undefined, "client-analysis-person");
    const initials = initialsFromName(row.name);
    const avatar = node("span", initials, "client-analysis-avatar");
    avatar.setAttribute("aria-hidden", "true");
    const title = node("div");
    const heading = node("h3", row.name);
    heading.tabIndex = -1;
    title.append(
      heading,
      node(
        "span",
        SocialMEIDemoData.enabled() ? "Conversa recente" : "Sem data confirmada",
        "management-note",
      ),
    );
    head.append(avatar, title);
    const label =
      p.lane === "analysis"
        ? "Aguardando classificação"
        : p.lane === "chance"
          ? levelsLabel[p.level]
          : p.lane === "excluded"
            ? displayLabel(row)
            : { critical: "Crítica", high: "Alta", normal: "Normal" }[p.priority];
    head.append(
      node(
        "span",
        label,
        "client-analysis-badge " +
          (p.lane === "chance" ? p.level : p.lane === "attention" ? p.priority : ""),
      ),
    );
    card.append(head);
    if (p.lane === "analysis") {
      const known = node("div", undefined, "client-analysis-grid");
      const left = node("div");
      left.append(node("h4", "O que já sabemos"), node("p", p.known));
      const right = node("div");
      right.append(node("h4", "O que falta saber"));
      const list = node("ul");
      p.missing.slice(0, 1).forEach((text) => list.append(node("li", text)));
      right.append(list);
      if (p.missing.length > 1)
        right.append(
          node("p", `Mais ${p.missing.length - 1} pontos em Ver conversa.`, "management-note"),
        );
      known.append(left, right);
      const next = node("section", undefined, "client-analysis-next");
      next.append(
        node("h4", "Pergunta sugerida"),
        node("blockquote", p.question),
        button("Copiar pergunta", "data-analysis-copy", row.id),
      );
      card.append(known, next);
    } else {
      card.append(node("p", briefReason(row), "client-analysis-reason"));
      if (p.lane === "chance") {
        const interest = node("div", undefined, "client-analysis-interest");
        interest.setAttribute("role", "img");
        interest.setAttribute(
          "aria-label",
          "Interesse " + levelsLabel[p.level] + ": nível qualitativo, sem probabilidade de compra",
        );
        for (let i = 0; i < 3; i++)
          interest.append(
            node("i", undefined, i < { quente: 3, morno: 2, frio: 1 }[p.level] ? "on" : ""),
          );
        card.append(
          interest,
          node(
            "p",
            p.manual
              ? "Classificação manual · apenas nesta sessão"
              : "Recomendação heurística · confirme com o cliente",
            "management-note",
          ),
        );
      }
      const detail = node("details", undefined, "client-analysis-expand");
      detail.append(
        node(
          "summary",
          p.lane === "attention" ? "Motivo, evidências e resposta" : "Por que esse resultado?",
        ),
        evidence(row),
      );
      const reasons = node("ul");
      row.reasons.forEach((reason) => reasons.append(node("li", reason)));
      detail.append(reasons, node("h4", "Próximo passo sugerido"), node("p", nextStep(row)));
      if (p.lane === "attention") {
        detail.append(
          node("h4", "Resposta sugerida · revise antes de usar"),
          node("blockquote", p.response),
          button("Copiar resposta", "data-analysis-copy", row.id),
        );
      }
      card.append(detail);
      if (p.lane === "attention") {
        card.dataset.priority = p.priority;
        card.append(
          node(
            "p",
            resolved[row.id] ? "Resolvido na análise" : "Aguardando sua revisão",
            "management-note",
          ),
          button(
            resolved[row.id] ? "Reabrir" : "Marcar como resolvido",
            "data-analysis-resolve",
            row.id,
          ),
        );
      }
      if (p.manual)
        card.append(button("Restaurar análise automática", "data-analysis-reset", row.id));
    }
    if (["analysis", "chance"].includes(p.lane)) {
      const choice = node("details", undefined, "client-analysis-choice");
      choice.append(
        node(
          "summary",
          p.lane === "analysis" ? "Já sei o que ele quer" : "Revisar nível de interesse",
        ),
        node(
          "p",
          "Frio: interesse inicial. Morno: interesse concreto a confirmar. Quente: sinais claros de compra ou contratação. Não são certezas de venda.",
          "management-note",
        ),
      );
      const actions = node("div", undefined, "native-opportunity-actions");
      for (const [level, text] of Object.entries(levelsLabel)) {
        const control = button(text, "data-analysis-classify", row.id);
        control.dataset.analysisValue = level;
        control.setAttribute("aria-pressed", String(p.lane === "chance" && p.level === level));
        actions.append(control);
      }
      choice.append(
        actions,
        node(
          "p",
          "Sua revisão vale só nesta sessão; não sincroniza entre dispositivos.",
          "management-note",
        ),
      );
      card.append(choice);
    }
    const actions = node("div", undefined, "native-opportunity-actions");
    actions.append(button("Ver conversa e revisar", "data-opportunity-open", row.id));
    card.append(actions);
    return card;
  }
  function render() {
    syncIdentity();
    refreshRows();
    document.dispatchEvent(new CustomEvent("socialmei-opportunity-demo-change"));
    const source = byId("opportunitySource"),
      queue = byId("opportunityQueue");
    source.replaceChildren();
    queue.replaceChildren();
    if ((!demoEnabled && !SocialMEIDemoData.enabled()) || remote()) {
      rows = [];
      renderTabs();
      const empty = node("div", undefined, "native-opportunity-empty");
      empty.append(
        node("h3", "Ainda não há conversas disponíveis para esta análise"),
        node(
          "p",
          "Precisamos de conversas vinculadas aos clientes do seu negócio. Confira os canais em Configurações. A integração com esta análise ainda está em preparação.",
          "management-note",
        ),
        button("Ver integrações", "data-opportunity-integrations"),
      );
      if (!remote())
        empty.append(button("Explorar demonstração fictícia", "data-opportunity-demo"));
      queue.append(empty);
      return;
    }
    const menu = node("details", undefined, "opportunity-options");
    menu.append(node("summary", "Opções da análise"));
    const actions = node("div", undefined, "opportunity-options-panel");
    actions.append(
      node(
        "p",
        "Recomendações heurísticas. Revise a conversa antes de decidir.",
        "management-note",
      ),
      button("Reanalisar exemplos", "data-opportunity-refresh"),
      button("Encerrar demonstração", "data-opportunity-stop"),
    );
    menu.append(actions);
    source.append(menu);
    document.dispatchEvent(new CustomEvent("socialmei-opportunity-demo-change"));
    renderTabs();
    let items = rows.filter((row) => presentation(row).lane === activeTab);
    if (activeTab === "analysis") {
      const pending = node("section", undefined, "client-analysis-pending");
      pending.setAttribute("aria-labelledby", "clientAnalysisPendingTitle");
      const title = node("h3", `${items.length} aguardando classificação`);
      title.id = "clientAnalysisPendingTitle";
      pending.append(title, node("p", "Confira a conversa para classificar.", "management-note"));
      queue.append(pending);
    } else if (activeTab === "chance") {
      const all = items;
      queue.append(
        node(
          "p",
          "Frio → Morno → Quente são níveis de interesse, não probabilidades. Na fila, os sinais mais fortes aparecem primeiro; confira os motivos antes de agir.",
          "client-analysis-intro",
        ),
        filters(
          [
            ["all", "Todos", all.length],
            ...Object.entries(levelsLabel).map(([key, label]) => [
              key,
              label,
              all.filter((r) => presentation(r).level === key).length,
            ]),
          ],
          "data-analysis-level",
          chanceFilter,
        ),
      );
      items = all.filter(
        (row) => chanceFilter === "all" || presentation(row).level === chanceFilter,
      );
      items.sort(
        (a, b) =>
          ["quente", "morno", "frio"].indexOf(presentation(a).level) -
          ["quente", "morno", "frio"].indexOf(presentation(b).level),
      );
    } else if (activeTab === "attention") {
      const all = items;
      queue.append(
        node(
          "p",
          "Suporte e situações urgentes têm prioridade própria. Resolução é apenas uma marca nesta sessão, sem alterar atendimentos reais.",
          "client-analysis-intro",
        ),
        filters(
          [
            ["open", "Abertos", all.filter((r) => !resolved[r.id]).length],
            ["resolved", "Resolvidos", all.filter((r) => resolved[r.id]).length],
          ],
          "data-analysis-alert",
          alertFilter,
        ),
      );
      items = all.filter((r) => (alertFilter === "resolved" ? resolved[r.id] : !resolved[r.id]));
      items.sort(
        (a, b) =>
          ["critical", "high", "normal"].indexOf(presentation(a).priority) -
          ["critical", "high", "normal"].indexOf(presentation(b).priority),
      );
    }
    const list = node("div", undefined, "client-analysis-list");
    list.dataset.count = String(items.length);
    items.forEach((row) => list.append(customerCard(row, presentation(row))));
    if (!items.length)
      list.append(node("p", "Nenhum cliente neste filtro.", "native-opportunity-empty"));
    queue.append(list);
    if (activeTab === "chance") {
      const outside = rows.filter((row) => presentation(row).lane === "excluded");
      const detail = node("details", undefined, "client-analysis-excluded");
      detail.append(
        node("summary", "Fora da fila comercial · " + outside.length),
        node(
          "p",
          "Recusas, compras concluídas e pós-venda não são novas oportunidades. Respeite a decisão e confira o contexto.",
          "management-note",
        ),
      );
      outside.forEach((row) => detail.append(customerCard(row, presentation(row))));
      queue.append(detail);
    }
  }
  function signalPanel(result) {
    const panel = node("div", undefined, "native-opportunity-signals");
    panel.append(node("h4", result.label), node("p", result.explanation));
    for (const signal of result.signals) {
      panel.append(
        node(
          "p",
          signal.label +
            " · " +
            {
              positive: "indício comercial",
              negative: "recusa",
              ambiguous: "contexto ou ressalva",
            }[signal.polarity],
          "management-note",
        ),
      );
      signal.evidence.forEach((evidence) => panel.append(node("blockquote", evidence.text)));
    }
    if (!result.signals.length)
      panel.append(
        node(
          "p",
          "Nenhum sinal coberto pelas regras foi reconhecido. Isso não significa desinteresse.",
        ),
      );
    const limits = node("details");
    limits.append(
      node("summary", "Critério, informações faltantes e limitações"),
      node("p", result.rule),
    );
    const list = node("ul");
    [...result.missingInformation, ...result.limitations].forEach((text) =>
      list.append(node("li", text)),
    );
    limits.append(list);
    panel.append(limits);
    return panel;
  }
  function detail(id) {
    const row = rows.find((row) => row.id === id);
    if (!row) return false;
    byId("opportunityModalTitle").textContent = row.name;
    const body = byId("opportunityDetail");
    body.replaceChildren();
    body.dataset.row = id;
    body.append(
      node("p", "Mensagens fictícias", "pill draft"),
      node("h4", displayLabel(row)),
      node("p", "Recomendação automática: " + displayLabel(row, row.recommendation.group)),
    );
    if (levels[id]) body.append(node("p", "Classificação manual: " + levelsLabel[levels[id]]));
    if (row.review) body.append(node("p", "Revisão humana: " + row.review.reason));
    const reasons = node("ul");
    row.reasons.forEach((reason) => reasons.append(node("li", reason)));
    body.append(reasons, node("h4", "Próximo passo prudente"), node("p", nextStep(row)));
    const actions = node("div", undefined, "native-opportunity-actions");
    if (findConversation(row))
      actions.append(button("Abrir na Caixa Unificada", "data-opportunity-conversation", id));
    const client = linkedClient(row);
    if (client)
      actions.append(button("Consultar cliente vinculado", "data-opportunity-client", id));
    else
      body.append(
        node(
          "p",
          "Nenhum cadastro vinculado disponível para consulta. Confira o vínculo do cliente na Caixa Unificada.",
          "management-note",
        ),
      );
    body.append(actions, node("h4", "Mensagens e evidências"));
    row.analyses.forEach(({ message, result }) => {
      const section = node("section", undefined, "native-opportunity-message");
      section.append(node("blockquote", message.text), signalPanel(result));
      body.append(section);
    });
    body.append(
      node("h4", "Revisão humana nesta sessão"),
      node(
        "p",
        "Altera somente esta recomendação em memória. Não salva no CRM, não modifica conversas e não envia respostas.",
        "management-note",
      ),
    );
    const form = node("form");
    form.id = "opportunityReviewForm";
    const label = node("label", "Encaminhamento");
    label.htmlFor = "opportunityReviewGroup";
    const select = node("select");
    select.id = "opportunityReviewGroup";
    Object.entries(SocialMEIPriority.GROUPS).forEach(([value, group]) => {
      const option = node("option", group.label);
      option.value = value;
      select.append(option);
    });
    select.value = row.group;
    const reasonLabel = node("label", "Motivo da revisão");
    reasonLabel.htmlFor = "opportunityReviewReason";
    const reason = node("textarea");
    reason.id = "opportunityReviewReason";
    reason.required = true;
    reason.maxLength = 300;
    reason.rows = 2;
    reason.value = row.review?.reason || "";
    const submit = node("button", "Aplicar revisão", "management-button pr");
    submit.type = "submit";
    const restore = button("Voltar à recomendação", "data-opportunity-restore", id);
    restore.disabled = !row.review;
    form.append(label, select, reasonLabel, reason, submit, restore);
    body.append(form);
    const status = node("p", undefined, "management-note");
    status.id = "opportunityReviewStatus";
    status.setAttribute("role", "status");
    body.append(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!reason.value.trim()) {
        status.textContent = "Informe o motivo da revisão.";
        return;
      }
      reviews[id] = { group: select.value, reason: reason.value.trim() };
      render();
      if (!detail(id)) {
        closeModal("opportunityModal");
        return;
      }
      byId("opportunityReviewStatus").textContent =
        "Revisão aplicada apenas nesta sessão. A lista foi reordenada.";
      byId("opportunityModalTitle").focus();
      body.scrollTop = 0;
    });
    let opener = document.querySelector(`[data-opportunity-open="${CSS.escape(id)}"]`);
    if (!opener?.getClientRects().length || opener.closest("details:not([open])"))
      opener = document.querySelector(`[data-analysis-tab="${activeTab}"]`);
    if (byId("opportunityModal").classList.contains("open"))
      byId("opportunityModal")._returnFocus = opener;
    return true;
  }
  function clearAnalysis() {
    byId("opportunityText").value = "";
    byId("opportunityAnalysis").replaceChildren();
    byId("opportunityAnalysis").hidden = true;
    byId("opportunityAnalysisStatus").textContent = "Texto e análise descartados desta página.";
  }
  document.addEventListener("click", async (event) => {
    const action = event.target.closest(
      "[data-opportunity-demo],[data-opportunity-stop],[data-opportunity-refresh],[data-opportunity-integrations],[data-opportunity-open],[data-opportunity-restore],[data-opportunity-conversation],[data-opportunity-client],[data-opportunity-clear]",
    );
    if (!action) return;
    syncIdentity();
    if (action.hasAttribute("data-opportunity-demo")) {
      if (remote()) return;
      demoEnabled = true;
      render();
      byId("clientTab-" + activeTab).focus();
    }
    if (action.hasAttribute("data-opportunity-stop")) {
      demoEnabled = false;
      if (SocialMEIDemoData.enabled()) {
        SocialMEIDemoData.set(false);
        document.dispatchEvent(new CustomEvent("socialmei-demo-change"));
      }
      reviews = {};
      levels = {};
      resolved = {};
      clearAnalysis();
      render();
      byId("clientTab-" + activeTab).focus();
      document.dispatchEvent(new CustomEvent("socialmei-opportunity-demo-change"));
    }
    if (action.hasAttribute("data-opportunity-refresh")) {
      render();
      document.querySelector(".opportunity-options > summary")?.focus();
      toast("Análise atualizada", "Exemplos reanalisados com as regras locais.", "info");
    }
    if (action.hasAttribute("data-opportunity-clear")) clearAnalysis();
    if (action.hasAttribute("data-opportunity-integrations")) {
      selectedSettingsTab = "integracoes";
      setView("Configurações");
    }
    if (action.hasAttribute("data-opportunity-open")) {
      refreshRows();
      if (detail(action.dataset.opportunityOpen)) openModal("opportunityModal");
      else {
        render();
        toast("Exemplo indisponível", "A conversa mudou e não pode ser usada como demonstração.");
      }
    }
    if (action.hasAttribute("data-opportunity-restore")) {
      const id = action.dataset.opportunityRestore;
      delete reviews[id];
      render();
      if (!detail(id)) {
        closeModal("opportunityModal");
        return;
      }
      byId("opportunityReviewStatus").textContent = "Recomendação automática restaurada.";
      byId("opportunityModalTitle").focus();
    }
    if (
      action.hasAttribute("data-opportunity-conversation") ||
      action.hasAttribute("data-opportunity-client")
    ) {
      const row = rows.find(
        (row) =>
          row.id === (action.dataset.opportunityConversation || action.dataset.opportunityClient),
      );
      if (!row) return;
      const conversation = findConversation(row),
        client = linkedClient(row);
      await closeModal("opportunityModal");
      if (action.hasAttribute("data-opportunity-client")) {
        if (client) openClient(client);
        else toast("Vínculo indisponível", "Confira o cadastro do cliente.");
      } else if (conversation) {
        setView("Caixa Unificada", { preserveConversation: true });
        selectConversation(conversation.id);
      } else toast("Conversa indisponível", "A conversa não está mais disponível na Caixa.");
    }
  });
  byId("clientAnalysisTabs").addEventListener("keydown", (event) => {
    const tabs = [...document.querySelectorAll("[data-analysis-tab]")];
    const index = tabs.indexOf(event.target);
    if (index < 0) return;
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % 3
        : event.key === "ArrowLeft"
          ? (index + 2) % 3
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? 2
              : null;
    if (next === null) return;
    event.preventDefault();
    tabs[next].click();
    tabs[next].focus();
  });
  document.addEventListener("click", async (event) => {
    const action = event.target.closest(
      "[data-analysis-tab],[data-analysis-level],[data-analysis-alert],[data-analysis-classify],[data-analysis-copy],[data-analysis-resolve],[data-analysis-reset]",
    );
    if (!action) return;
    syncIdentity();
    refreshRows();
    const focus = (selector) => {
      render();
      document.querySelector(selector)?.focus();
    };
    if (action.hasAttribute("data-analysis-tab")) {
      activeTab = action.dataset.analysisTab;
      focus(`[data-analysis-tab="${activeTab}"]`);
      return;
    }
    if (action.hasAttribute("data-analysis-level")) {
      chanceFilter = action.dataset.analysisLevel;
      focus(`[data-analysis-level="${chanceFilter}"]`);
      return;
    }
    if (action.hasAttribute("data-analysis-alert")) {
      alertFilter = action.dataset.analysisAlert;
      focus(`[data-analysis-alert="${alertFilter}"]`);
      return;
    }
    const id =
      action.dataset.analysisClassify ||
      action.dataset.analysisCopy ||
      action.dataset.analysisResolve ||
      action.dataset.analysisReset;
    const row = rows.find((r) => r.id === id);
    if (!row || remote() || (!demoEnabled && !SocialMEIDemoData.enabled())) return;
    const p = presentation(row);
    if (
      action.hasAttribute("data-analysis-classify") &&
      ["analysis", "chance"].includes(p.lane) &&
      Object.hasOwn(levelsLabel, action.dataset.analysisValue)
    ) {
      levels[id] = action.dataset.analysisValue;
      activeTab = "chance";
      chanceFilter = "all";
      focus(`[data-native-opportunity="${CSS.escape(id)}"] h3`);
      status(
        row.name +
          ": " +
          levelsLabel[levels[id]] +
          ". Classificação manual aplicada só nesta sessão, sem sincronização entre dispositivos.",
      );
    }
    if (action.hasAttribute("data-analysis-reset")) {
      delete levels[id];
      activeTab = presentation(row).lane;
      chanceFilter = "all";
      focus(`[data-native-opportunity="${CSS.escape(id)}"] h3`);
      status(
        row.name +
          ": classificação automática restaurada." +
          (activeTab === "analysis" ? " Aguardando classificação." : ""),
      );
    }
    if (action.hasAttribute("data-analysis-resolve") && p.lane === "attention") {
      resolved[id] = !resolved[id];
      focus(`[data-analysis-alert="${alertFilter}"]`);
      status(
        resolved[id]
          ? "Alerta marcado como resolvido apenas nesta sessão."
          : "Alerta reaberto apenas nesta sessão.",
      );
    }
    if (action.hasAttribute("data-analysis-copy")) {
      try {
        if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
        await navigator.clipboard.writeText(p.lane === "analysis" ? p.question : p.response);
        status("Texto copiado. Revise antes de usar; nenhuma mensagem foi enviada.");
      } catch {
        status("Não foi possível copiar. Selecione o texto e copie manualmente.");
      }
    }
  });
  byId("opportunityText").value = "";
  byId("opportunityAnalyzeForm").addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      const result = SocialMEIIntent.analyzeMessage(byId("opportunityText").value);
      const host = byId("opportunityAnalysis");
      host.replaceChildren(
        signalPanel(result),
        node("h4", "Próximo passo sugerido"),
        node("p", result.nextStep),
      );
      host.hidden = false;
      host.querySelector("h4").tabIndex = -1;
      host.querySelector("h4").focus();
      byId("opportunityAnalysisStatus").textContent =
        "Análise local concluída. Nenhum texto foi enviado ou salvo.";
    } catch (error) {
      byId("opportunityAnalysis").hidden = true;
      byId("opportunityAnalysisStatus").textContent = error.message;
    }
  });
  byId("opportunityText").addEventListener("input", () => {
    byId("opportunityAnalysis").hidden = true;
    byId("opportunityAnalysisStatus").textContent =
      "Texto alterado. Analise novamente para obter uma recomendação atual.";
  });
  function resetDemo() {
    demoEnabled = false;
    reviews = {};
    levels = {};
    resolved = {};
    rows = [];
  }
  return Object.freeze({ render, demoActive: () => demoEnabled, resetDemo });
})();
function renderOpportunities() {
  SocialMEIOpportunities.render();
}
