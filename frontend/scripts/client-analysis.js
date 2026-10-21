(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIClientAnalysis = api;
})(globalThis, function () {
  "use strict";
  const LEVELS = Object.freeze({ frio: "Frio", morno: "Morno", quente: "Quente" });
  // Additional examples stay in the opt-in demonstration, never in the CRM or Inbox.
  function demoCustomers() {
    return [
      ["welcome", "Lia Andrade", "Olá, bom dia!"],
      ["purchase", "Bruno Alves", "Quero contratar a troca de tela. Qual o valor?"],
      ["doubt", "Bia Santos", "Talvez compre o perfume, ainda não decidi."],
      ["refusal", "Davi Melo", "Não quero comprar. Escolhi outro fornecedor."],
      ["critical", "Ana Costa", "Preciso de ajuda urgente, meu produto veio quebrado."],
      ["high", "Paulo Lima", "Preciso de suporte para uma cobrança indevida."],
      ["normal", "Iara Reis", "Preciso de ajuda para acompanhar meu pedido."],
      ["completed", "Leo Dias", "Já comprei. Obrigado!"],
    ].map(([id, name, text]) => ({
      id: "analysis-demo-" + id,
      name,
      messages: [{ id: "message-1", author: "customer", text, at: null }],
    }));
  }
  function present(row, levelReview) {
    const results = row.analyses.map((a) => a.result);
    const signals = results.flatMap((result) => result.signals);
    const decisiveSignals =
      row.analyses.find((a) => a.message.id === row.decisiveMessageId)?.result.signals || [];
    const support = row.group === "support" && signals.some((s) => s.id === "support");
    const urgent =
      decisiveSignals.some((s) => s.id === "urgency") &&
      !decisiveSignals.some((s) => s.id === "negated_urgency");
    const excluded =
      ["completed", "declined"].includes(row.group) || (row.group === "support" && !support);
    let lane = support
      ? "attention"
      : excluded
        ? "excluded"
        : ["first", "inquiry"].includes(row.group)
          ? "chance"
          : "analysis";
    let level = row.group === "first" ? "quente" : "morno";
    if (!support && !excluded && Object.hasOwn(LEVELS, levelReview || "")) {
      lane = "chance";
      level = levelReview;
    }
    const missing = [...new Set(results.flatMap((result) => result.missingInformation))];
    return {
      lane,
      level,
      manual: !!levelReview && lane === "chance",
      priority:
        urgent && support
          ? "critical"
          : support &&
              signals.some((s) =>
                /quebrad|indevida|reembolso/i.test(s.evidence.map((e) => e.text).join(" ")),
              )
            ? "high"
            : "normal",
      known: row.analyses.at(-1)?.message.text || "Ainda não há informação suficiente.",
      missing: missing.length ? missing : ["O que a pessoa precisa e qual próximo passo deseja"],
      question:
        row.group === "clarify"
          ? "Tem alguma dúvida ou condição que você gostaria de esclarecer antes de decidir?"
          : "Como posso ajudar? Você quer mais informações ou combinar um próximo passo?",
      response:
        "Recebi sua mensagem. Pode me contar mais sobre o que aconteceu? Vou conferir as informações antes de orientar o próximo passo.",
    };
  }
  return Object.freeze({ LEVELS, demoCustomers, present });
});
