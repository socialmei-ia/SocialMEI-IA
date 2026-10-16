(function (root, factory) {
  const api = factory(
    typeof module === "object" && module.exports
      ? require("./intent-engine.js")
      : root.SocialMEIIntent,
  );
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIPriority = api;
})(globalThis, function (intent) {
  "use strict";
  const GROUPS = Object.freeze({
    first: Object.freeze({
      label: "Acompanhar primeiro",
      commercial: true,
      order: 0,
      nextStep:
        "Responda ao pedido e confira preço, estoque e prazo. Confirme se a pessoa quer avançar, sem prometer disponibilidade.",
    }),
    inquiry: Object.freeze({
      label: "Responder consulta",
      commercial: true,
      order: 1,
      nextStep:
        "Responda à consulta comercial e confirme produto, quantidade e necessidade antes de propor uma compra.",
    }),
    clarify: Object.freeze({
      label: "Esclarecer decisão",
      commercial: true,
      order: 2,
      nextStep:
        "Esclareça a dúvida ou os trechos conflitantes, sem presumir decisão nem pressionar. Confirme se há uma nova compra ou apenas pós-venda.",
    }),
    reconnect: Object.freeze({
      label: "Retomar contexto",
      commercial: true,
      order: 3,
      nextStep:
        "Confirme se a necessidade ainda existe e se o prazo mudou. Não trate uma urgência antiga como atual.",
    }),
    unknown: Object.freeze({
      label: "Entender necessidade",
      commercial: true,
      order: 4,
      nextStep: "Pergunte como pode ajudar. Ausência de sinais não significa desinteresse.",
    }),
    support: Object.freeze({
      label: "Encaminhar ao suporte",
      commercial: false,
      order: 0,
      nextStep:
        "Acolha o problema e confira o pedido antes de informar solução ou prazo. Priorize o atendimento, sem oferta automática.",
    }),
    completed: Object.freeze({
      label: "Compra relatada como concluída",
      commercial: false,
      order: 1,
      nextStep:
        "Confirme o registro da compra e ofereça orientação de pós-venda. O relato não comprova pagamento nem representa nova oportunidade.",
    }),
    declined: Object.freeze({
      label: "Respeitar desistência",
      commercial: false,
      order: 2,
      nextStep:
        "Respeite a recusa e encerre a abordagem comercial. Confirme eventual cancelamento antes de agir.",
    }),
  });
  const day = 86400000;
  const has = (result, id) => result.signals.some((s) => s.id === id);
  const positive = (result, id) =>
    result.signals.some((s) => s.id === id && s.polarity === "positive");
  function timestamp(value, reference) {
    if (
      typeof value !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value)
    )
      return null;
    const date = Date.parse(value);
    return Number.isFinite(date) &&
      date <= reference &&
      new Date(date).toISOString().replace(".000Z", "Z") === value.replace(".000Z", "Z")
      ? date
      : null;
  }
  function recommend(analyses) {
    let decisive = null,
      group = "unknown",
      priorRefusal = false,
      priorAfterSales = false,
      priorDoubt = false;
    const contextReasons = [];
    for (const entry of analyses) {
      const result = entry.result;
      if (!result.signals.length) continue;
      const substantive =
        ["high", "initial", "declined", "conflicting", "unclear", "exploratory"].includes(
          result.category,
        ) || ["support", "completed", "after_sales"].some((id) => has(result, id));
      if (!substantive && decisive) continue;
      if (result.category === "initial" && group === "first" && !positive(result, "quote"))
        continue;
      decisive = entry;
      if (has(result, "reported")) group = "clarify";
      else if (has(result, "support")) {
        group = "support";
        priorAfterSales = true;
      } else if (has(result, "completed")) {
        group = positive(result, "purchase") ? "clarify" : "completed";
        priorAfterSales = true;
        if (group === "clarify")
          contextReasons.push(
            "Compra anterior e novo interesse no mesmo texto; confirme o contexto.",
          );
      } else if (result.category === "declined") {
        group = "declined";
        priorRefusal = true;
      } else if (["conflicting", "unclear", "exploratory"].includes(result.category)) {
        group = "clarify";
        priorDoubt = true;
      } else if (["high", "initial"].includes(result.category)) {
        if (priorRefusal || priorAfterSales || priorDoubt) {
          group = "clarify";
          contextReasons.push(
            "Há recusa, ressalva ou pós-venda anterior nesta conversa; confirme a mudança de contexto.",
          );
        } else
          group = result.category === "high" || positive(result, "quote") ? "first" : "inquiry";
      } else if (has(result, "after_sales")) {
        group = "support";
        priorAfterSales = true;
      }
      // A greeting, isolated item or urgency must not erase an established decision.
      else if (group === "unknown") group = "unknown";
    }
    // Recency belongs to the last substantive decision, not a later greeting or isolated signal.
    return { decisive, group, contextReasons: [...new Set(contextReasons)] };
  }
  function prioritizeCustomers(customers, { referenceTime, reviews = {} } = {}) {
    const reference = Date.parse(referenceTime);
    if (!Number.isFinite(reference)) throw new TypeError("Informe a data de referência fictícia.");
    if (!Array.isArray(customers)) throw new TypeError("Informe os clientes.");
    const ids = new Set();
    const rows = customers.map((customer) => {
      if (
        !customer.id ||
        typeof customer.id !== "string" ||
        ids.has(customer.id) ||
        typeof customer.name !== "string" ||
        !Array.isArray(customer.messages)
      )
        throw new TypeError("Cliente inválido ou repetido.");
      ids.add(customer.id);
      const messageIds = new Set();
      for (const message of customer.messages) {
        if (
          !message.id ||
          messageIds.has(message.id) ||
          !["customer", "mei"].includes(message.author)
        )
          throw new TypeError("Mensagem sem identidade única ou autoria válida.");
        messageIds.add(message.id);
      }
      const customerMessages = customer.messages.filter((m) => m.author === "customer");
      const datesReliable =
        customerMessages.length > 0 &&
        customerMessages.every((m) => timestamp(m.at, reference) !== null);
      const ordered = datesReliable
        ? [...customerMessages].sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
        : customerMessages;
      const analyses = ordered.map((message) => ({
        message: { ...message },
        result: intent.analyzeMessage(message.text),
      }));
      const recommendation = recommend(analyses);
      let { group, decisive } = recommendation;
      const recency = datesReliable && decisive ? timestamp(decisive.message.at, reference) : null;
      const stale = recency !== null && reference - recency > day;
      const urgent =
        !!decisive &&
        !stale &&
        recency !== null &&
        has(decisive.result, "urgency") &&
        !has(decisive.result, "negated_urgency") &&
        ["first", "inquiry"].includes(group);
      const reasons = [];
      if (decisive) {
        if (group === "support")
          reasons.push(
            "Pós-venda ou problema relatado; precisa de atendimento, fora da fila de novas vendas.",
          );
        else if (group === "completed")
          reasons.push("A pessoa relata uma compra concluída; não contar como nova oportunidade.");
        else if (group === "declined")
          reasons.push(
            "A última decisão comercial reconhecida é uma recusa; sinais anteriores não a anulam.",
          );
        else if (group === "first" && positive(decisive.result, "quote"))
          reasons.push(
            "Pedido de orçamento reconhecido; prepare uma resposta, sem presumir fechamento.",
          );
        else if (!recommendation.contextReasons.length) reasons.push(decisive.result.explanation);
        reasons.push(...recommendation.contextReasons);
      } else reasons.push("Sem sinais comerciais reconhecidos; é preciso entender a necessidade.");
      if (stale && ["first", "inquiry"].includes(group)) {
        group = "reconnect";
        reasons.unshift(
          "Sinal comercial com mais de 24 horas na referência fictícia; confirmar contexto e prazo.",
        );
      }
      if (urgent)
        reasons.push(
          "Prazo ou urgência em sinal comercial das últimas 24 horas; desempata apenas dentro do grupo.",
        );
      const dateWarning = !datesReliable;
      if (dateWarning)
        reasons.push(
          "Datas ausentes, inválidas ou futuras: ordem da conversa informada, sem desempate por recência.",
        );
      const base = { group, label: GROUPS[group].label, nextStep: GROUPS[group].nextStep };
      const review = Object.hasOwn(reviews, customer.id) ? reviews[customer.id] : null;
      if (
        review &&
        (!Object.hasOwn(GROUPS, review.group) ||
          typeof review.reason !== "string" ||
          !review.reason.trim() ||
          review.reason.length > 300)
      )
        throw new TypeError("Revisão exige encaminhamento válido e motivo de até 300 caracteres.");
      if (review) group = review.group;
      const effective = GROUPS[group];
      return {
        id: customer.id,
        name: customer.name,
        interest: customer.interest || "",
        group,
        label: effective.label,
        commercial: effective.commercial,
        reasons,
        nextStep: effective.nextStep,
        analyses,
        decisiveMessageId: decisive?.message.id ?? null,
        recency,
        dateWarning,
        urgent: urgent && ["first", "inquiry"].includes(group),
        recommendation: base,
        review: review ? { group: review.group, reason: review.reason.trim() } : null,
      };
    });
    return rows.sort(
      (a, b) =>
        Number(b.commercial) - Number(a.commercial) ||
        GROUPS[a.group].order - GROUPS[b.group].order ||
        Number(b.urgent) - Number(a.urgent) ||
        (b.recency ?? -Infinity) - (a.recency ?? -Infinity) ||
        (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
    );
  }
  return Object.freeze({ prioritizeCustomers, GROUPS });
});
