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
  const remote = () => SocialMEIAuth.remote || SocialMEIClients.remote;
  function findConversation(row) {
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
    if (row.group === "unknown") return "Ainda faltam sinais para entender a necessidade.";
    return row.reasons[0];
  }
  function refreshRows() {
    const customers = SocialMEIOpportunityData.read({
      enabled: demoEnabled,
      remote: remote(),
      snapshot: opportunityDemoSnapshot,
      conversations: sessionData.conversas,
    });
    rows = SocialMEIPriority.prioritizeCustomers(customers, {
      referenceTime: new Date().toISOString(),
      reviews,
    });
  }
  function render() {
    refreshRows();
    const source = byId("opportunitySource"),
      queue = byId("opportunityQueue");
    source.replaceChildren();
    queue.replaceChildren();
    if (!demoEnabled || remote()) {
      const empty = node("div", undefined, "management-card native-opportunity-empty");
      empty.append(
        node("h3", "Ainda não há conversas disponíveis para esta análise"),
        node(
          "p",
          "Para identificar oportunidades, precisamos de conversas vinculadas aos clientes do seu negócio. Confira os canais em Configurações. A integração com esta aba ainda está em preparação.",
          "management-note",
        ),
      );
      empty.append(button("Ver integrações", "data-opportunity-integrations"));
      if (!remote() && opportunityDemoSnapshot.length)
        empty.append(button("Explorar conversas fictícias da Caixa", "data-opportunity-demo"));
      source.append(empty);
      return;
    }
    const note = node("div", undefined, "management-demo");
    note.append(
      node("span", "Demonstração · mensagens fictícias", "pill draft"),
      node(
        "span",
        "Análise dos exemplos da Caixa. Nenhuma mensagem ou recomendação desta demonstração representa uma oportunidade real.",
      ),
    );
    const actions = node("div", undefined, "native-opportunity-actions");
    actions.append(
      button("Reanalisar exemplos", "data-opportunity-refresh"),
      button("Encerrar demonstração", "data-opportunity-stop"),
    );
    source.append(note, actions);
    if (!rows.length) {
      queue.append(
        node("p", "As conversas fictícias não estão mais disponíveis na Caixa.", "management-note"),
      );
      return;
    }
    for (const commercial of [true, false]) {
      queue.append(
        node("h3", commercial ? "Acompanhamento comercial" : "Atendimento, pós-venda e recusas"),
      );
      const list = node(commercial ? "ol" : "ul", undefined, "native-opportunity-list");
      const items = rows.filter((row) => row.commercial === commercial);
      for (const [index, row] of items.entries()) {
        const card = node("li");
        card.dataset.nativeOpportunity = row.id;
        const title = node("div", undefined, "native-opportunity-person");
        if (commercial)
          title.append(
            node("span", String(index + 1).padStart(2, "0"), "native-opportunity-position"),
          );
        title.append(node("strong", row.name));
        const why = node("div", undefined, "native-opportunity-why");
        why.append(node("span", displayLabel(row), "pill"), node("p", briefReason(row)));
        card.append(title, button("Ver evidências", "data-opportunity-open", row.id), why);
        list.append(card);
      }
      if (!items.length)
        list.append(node("li", "Nenhum exemplo neste encaminhamento.", "management-note"));
      queue.append(list);
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
    if (row.review) body.append(node("p", "Revisão humana: " + row.review.reason));
    const reasons = node("ul");
    row.reasons.forEach((reason) => reasons.append(node("li", reason)));
    body.append(reasons, node("h4", "Próximo passo prudente"), node("p", nextStep(row)));
    const actions = node("div", undefined, "native-opportunity-actions");
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
    const opener = document.querySelector(`[data-opportunity-open="${CSS.escape(id)}"]`);
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
    if (action.hasAttribute("data-opportunity-demo")) {
      if (remote()) return;
      demoEnabled = true;
      render();
    }
    if (action.hasAttribute("data-opportunity-stop")) {
      demoEnabled = false;
      reviews = {};
      clearAnalysis();
      render();
    }
    if (action.hasAttribute("data-opportunity-refresh")) render();
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
  return Object.freeze({ render });
})();
function renderOpportunities() {
  SocialMEIOpportunities.render();
}
