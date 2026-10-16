(function () {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const engine = window.SocialMEIPriority;
  const scenario = window.SocialMEIPriorityScenario;
  let customers = structuredClone(scenario.customers),
    reviews = {},
    rows = [],
    selectedId = null,
    sequence = 0;
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const date = (value) =>
    new Intl.DateTimeFormat("pt-BR", {
      timeZone: "UTC",
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value)) + " UTC";
  const firstSentence = (text) => text.split(". ")[0].replace(/\.$/, "") + ".";
  function briefReason(row) {
    if (row.review) return row.review.reason;
    const result = row.analyses.find((entry) => entry.message.id === row.decisiveMessageId)?.result;
    const has = (id) =>
      result?.signals.some((signal) => signal.id === id && signal.polarity === "positive");
    if (["first", "inquiry"].includes(row.group)) {
      if (has("purchase")) return "Expressou vontade de comprar ou contratar.";
      if (has("quote")) return "Pediu um orçamento; prepare uma resposta.";
      const topics = {
        price: "preço",
        availability: "disponibilidade",
        delivery: "entrega",
        payment: "pagamento",
      };
      const found = Object.entries(topics)
        .filter(([id]) => has(id))
        .map(([, label]) => label);
      if (found.length) return "Consultou " + new Intl.ListFormat("pt-BR").format(found) + ".";
    }
    if (row.group === "clarify") {
      if (result?.category === "conflicting")
        return "Há sinais comerciais e recusa no mesmo texto.";
      if (result?.category === "exploratory")
        return "Está pesquisando, sem confirmar decisão de compra.";
      return "Há dúvida ou mudança de contexto a esclarecer.";
    }
    return {
      reconnect: "Interesse antigo; confirme se a necessidade continua.",
      support: "Relatou um problema ou pedido de suporte.",
      completed: "Relatou uma compra já concluída.",
      declined: "A recusa reconhecida pede encerrar a abordagem.",
      unknown: "Ainda faltam sinais para entender a necessidade.",
    }[row.group];
  }
  for (const [id, group] of Object.entries(engine.GROUPS)) {
    const option = node("option", group.label);
    option.value = id;
    byId("priority-review-group").append(option);
  }
  function renderList() {
    rows = engine.prioritizeCustomers(customers, {
      referenceTime: scenario.referenceTime,
      reviews,
    });
    const commercial = rows.filter((row) => row.commercial),
      other = rows.filter((row) => !row.commercial);
    byId("commercial-count").textContent = String(commercial.length);
    byId("other-count").textContent = String(other.length);
    for (const [host, items] of [
      ["commercial-priorities", commercial],
      ["other-priorities", other],
    ]) {
      byId(host).replaceChildren();
      items.forEach((row, index) => {
        const card = node("li", undefined, "priority-card");
        card.dataset.customerId = row.id;
        const person = node("div", undefined, "priority-person");
        if (row.commercial)
          person.append(node("span", String(index + 1).padStart(2, "0"), "priority-position"));
        const identity = node("div");
        identity.append(node("h4", row.name), node("p", row.interest, "muted"));
        person.append(identity);
        const reason = node("div");
        reason.append(node("span", row.label, "badge"));
        if (row.review) reason.append(node("span", "Revisão humana", "badge review-badge"));
        reason.append(node("p", briefReason(row)));
        reason.append(
          node(
            "p",
            row.recency === null
              ? "Sinal sem data confiável"
              : "Sinal: " + date(row.recency) + (row.urgent ? " · prazo recente" : ""),
            "priority-time",
          ),
        );
        const step = node("div", undefined, "priority-step");
        step.append(
          node("span", "PRÓXIMO PASSO", "priority-step-label"),
          node("p", firstSentence(row.nextStep)),
        );
        const open = node("button", "Ver conversa");
        open.type = "button";
        open.setAttribute("aria-label", "Ver conversa de " + row.name);
        open.addEventListener("click", () => openCustomer(row.id));
        card.append(person, reason, step, open);
        byId(host).append(card);
      });
      if (!items.length)
        byId(host).append(node("li", "Nenhum cliente neste encaminhamento.", "empty"));
    }
  }
  function renderDetail() {
    const row = rows.find((item) => item.id === selectedId);
    byId("priority-detail-title").textContent = row.name;
    const summary = byId("priority-detail-summary");
    summary.replaceChildren();
    summary.append(
      node("h3", row.label),
      node("p", "Recomendação automática: " + row.recommendation.label),
    );
    if (row.review)
      summary.append(
        node("p", "Revisão humana nesta sessão: " + row.review.reason, "priority-review-notice"),
      );
    const reasons = node("ul");
    row.reasons.forEach((reason) => reasons.append(node("li", reason)));
    summary.append(reasons);
    const next = node("div", undefined, "intent-next");
    next.append(node("h3", "Próximo passo prudente"), node("p", row.nextStep));
    summary.append(next);
    summary.append(
      node(
        "p",
        "Recomendação por regras locais, sem certeza de venda. O volume da conversa não aumenta a prioridade. Relatos de compra não comprovam pagamento.",
        "muted",
      ),
    );
    const conversation = byId("priority-conversation");
    conversation.replaceChildren();
    row.analyses.forEach(({ message, result }) => {
      const article = node("article", undefined, "priority-message");
      article.dataset.messageId = message.id;
      const time = node(
        "time",
        row.dateWarning
          ? (message.at || "Data não informada") + " · ordem informada, sem recência"
          : date(message.at),
      );
      if (!row.dateWarning) time.dateTime = message.at;
      article.append(time);
      if (message.id === row.decisiveMessageId)
        article.append(node("p", "Sinal decisivo para esta recomendação", "badge"));
      article.append(
        node("blockquote", message.text, "intent-evidence priority-source"),
        node("h4", result.label),
        node("p", result.explanation, "muted"),
      );
      const quotes = node("div", undefined, "priority-quotes");
      for (const signal of result.signals) {
        quotes.append(
          node(
            "p",
            signal.label +
              " · " +
              {
                positive: "indício comercial",
                negative: "recusa",
                ambiguous: "contexto ou ressalva",
              }[signal.polarity],
          ),
        );
        signal.evidence.forEach((evidence) =>
          quotes.append(node("blockquote", evidence.text, "intent-evidence")),
        );
      }
      if (!result.signals.length)
        quotes.append(
          node("p", "Nenhum sinal coberto pelas regras. Isso não significa desinteresse."),
        );
      article.append(quotes);
      conversation.append(article);
    });
    byId("priority-review-group").value = row.group;
    byId("priority-review-reason").value = row.review?.reason || "";
    byId("priority-remove-review").disabled = !row.review;
  }
  function openCustomer(id) {
    selectedId = id;
    renderDetail();
    byId("priority-message-form").reset();
    byId("priority-detail-status").textContent = "";
    byId("priority-detail").showModal();
    byId("priority-detail-title").focus();
  }
  byId("priority-review-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const reason = byId("priority-review-reason").value.trim();
    if (!reason) {
      byId("priority-detail-status").textContent = "Informe um motivo para revisar.";
      return;
    }
    reviews[selectedId] = { group: byId("priority-review-group").value, reason };
    renderList();
    renderDetail();
    byId("priority-detail-status").textContent =
      "Revisão aplicada apenas nesta sessão. Lista reordenada; a recomendação automática continua visível.";
    byId("priority-detail-title").focus();
  });
  byId("priority-remove-review").addEventListener("click", () => {
    delete reviews[selectedId];
    renderList();
    renderDetail();
    byId("priority-detail-status").textContent =
      "Revisão removida. Encaminhamento automático restaurado.";
    byId("priority-detail-title").focus();
  });
  byId("priority-message-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = byId("priority-message").value.trim();
    if (!text) {
      byId("priority-detail-status").textContent = "Escreva uma mensagem fictícia.";
      return;
    }
    customers
      .find((customer) => customer.id === selectedId)
      .messages.push({
        id: `local-${++sequence}`,
        author: "customer",
        text,
        at: scenario.referenceTime,
      });
    delete reviews[selectedId];
    renderList();
    renderDetail();
    byId("priority-message-form").reset();
    byId("priority-detail-status").textContent =
      "Mensagem fictícia analisada. Lista atualizada; eventual revisão anterior deste cliente foi descartada.";
    byId("priority-detail-title").focus();
  });
  byId("reanalyze-customers").addEventListener("click", () => {
    renderList();
    byId("priority-status").textContent =
      "Oito clientes reanalisados localmente. Revisões humanas preservadas; nenhum envio externo.";
  });
  byId("reset-customers").addEventListener("click", () => {
    customers = structuredClone(scenario.customers);
    reviews = {};
    sequence = 0;
    renderList();
    byId("priority-status").textContent =
      "Cenário original restaurado. Mensagens acrescentadas e revisões descartadas.";
  });
  byId("priority-detail").addEventListener("close", () => {
    document.querySelector(`[data-customer-id="${CSS.escape(selectedId)}"] button`)?.focus();
  });
  renderList();
})();
