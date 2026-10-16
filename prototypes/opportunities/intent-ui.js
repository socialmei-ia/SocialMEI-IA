(function () {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const engine = window.SocialMEIIntent;
  const samples = window.SocialMEITapiocaScenario?.active
    ? window.SocialMEITapiocaScenario.customers.map((customer) => [
        customer.name,
        customer.messages.at(-1).text,
      ])
    : [
        [
          "Produto, preço e entrega",
          "Quanto custa o 212 VIP? Tem pronta entrega? Consegue entregar hoje?",
        ],
        [
          "Decisão explícita",
          'Quero comprar o produto "Sabonete Flor do Campo". Vocês aceitam Pix?',
        ],
        ["Só preço", "Quanto custa?"],
        ["Produto e estoque", "Tem o iPhone 15 em estoque?"],
        ["Pesquisa sem compromisso", "Só estou pesquisando. Quanto custa o 212 VIP?"],
        ["Elogio, sem pedido", "Amei seu atendimento, parabéns!"],
        ["Urgência, sem contexto", "Preciso disso hoje, é urgente!"],
        ["Recusa", "Não quero comprar o 212 VIP."],
        ["Desistência", "Desisti. Pode cancelar."],
        ["Sinais conflitantes", "Quero comprar, mas não quero comprar agora."],
        ["Condição ou objeção", "Quero comprar a camisa, mas está muito caro."],
        ["Pós-venda", "Minha entrega não chegou. Quero saber o prazo de entrega."],
      ];
  byId("intent-message").value = "";
  let current = null;
  let comparisons = [];
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  samples.forEach(([title], index) => {
    const option = element("option", title);
    option.value = String(index);
    byId("intent-example").append(option);
  });
  function list(id, items) {
    const node = byId(id);
    node.replaceChildren(...items.map((item) => element("li", item)));
  }
  function stale() {
    current = null;
    byId("intent-result").hidden = true;
    byId("intent-status").textContent =
      "Texto alterado. Clique em Analisar intenção para obter um novo resultado.";
  }
  function renderResult(snapshot) {
    const result = snapshot.result;
    const node = byId("intent-result");
    node.hidden = false;
    node.dataset.category = result.category;
    byId("intent-result-title").textContent = result.label;
    byId("intent-explanation").textContent = result.explanation;
    byId("intent-next-step").textContent = result.nextStep;
    byId("intent-rule").textContent = result.rule;
    list("intent-missing", result.missingInformation);
    list("intent-limitations", result.limitations);
    byId("intent-signals").replaceChildren();
    if (!result.signals.length)
      byId("intent-signals").append(
        element(
          "p",
          "Nenhum sinal coberto pelas regras foi encontrado. Isso não significa baixa intenção.",
          "muted",
        ),
      );
    for (const signal of result.signals) {
      const item = element("article", undefined, "intent-signal");
      const heading = element("div", undefined, "intent-signal-heading");
      heading.append(
        element("strong", signal.label),
        element(
          "span",
          { positive: "Indício comercial", negative: "Recusa", ambiguous: "Contexto ou ressalva" }[
            signal.polarity
          ],
          "polarity",
        ),
      );
      item.append(heading);
      signal.evidence.forEach((evidence) =>
        item.append(element("blockquote", evidence.text, "intent-evidence")),
      );
      byId("intent-signals").append(item);
    }
    byId("intent-status").textContent =
      `Análise local concluída: ${result.label}. ${result.signals.length} tipos de sinal encontrados. Resultado provisório, sem garantia de venda.`;
  }
  function analyze() {
    try {
      const text = byId("intent-message").value;
      current = { text, result: engine.analyzeMessage(text) };
      renderResult(current);
      byId("intent-result-title").focus();
    } catch (error) {
      current = null;
      byId("intent-result").hidden = true;
      byId("intent-status").textContent =
        error instanceof RangeError
          ? error.message
          : "Não foi possível analisar este texto localmente. Nenhum texto foi enviado.";
    }
  }
  byId("intent-form").addEventListener("submit", (event) => {
    event.preventDefault();
    analyze();
  });
  byId("intent-message").addEventListener("input", () => {
    byId("intent-example").value = "";
    stale();
  });
  byId("intent-example").addEventListener("change", (event) => {
    if (event.target.value === "") return;
    byId("intent-message").value = samples[Number(event.target.value)][1];
    stale();
    byId("intent-message").focus();
  });
  function renderComparisons() {
    byId("intent-comparisons").hidden = !comparisons.length;
    const host = byId("intent-comparison-list");
    host.replaceChildren();
    comparisons.forEach((snapshot, index) => {
      const card = element("article", undefined, "intent-comparison");
      card.append(
        element("p", `Mensagem ${index + 1}`, "eyebrow"),
        element("blockquote", snapshot.text || "Mensagem vazia", "intent-evidence"),
        element("h3", snapshot.result.label),
        element("p", snapshot.result.explanation),
      );
      const signals = element("ul");
      snapshot.result.signals.forEach((signal) => signals.append(element("li", signal.label)));
      card.append(signals);
      const button = element("button", "Reanalisar esta mensagem");
      button.type = "button";
      button.addEventListener("click", () => {
        byId("intent-message").value = snapshot.text;
        byId("intent-example").value = "";
        analyze();
      });
      card.append(button);
      host.append(card);
    });
  }
  byId("compare-intent").addEventListener("click", () => {
    if (!current) return;
    if (comparisons.some((item) => item.text === current.text)) {
      byId("intent-status").textContent = "Esta mensagem já está na comparação.";
      return;
    }
    if (comparisons.length === 3) {
      byId("intent-status").textContent =
        "A comparação comporta três mensagens. Apague as comparações para iniciar outra seleção.";
      return;
    }
    comparisons.push(current);
    renderComparisons();
    byId("intent-status").textContent =
      "Análise guardada para comparação apenas na memória desta página.";
  });
  byId("clear-comparisons").addEventListener("click", () => {
    comparisons = [];
    renderComparisons();
    byId("intent-status").textContent = "Comparações apagadas da sessão.";
    byId("intent-message").focus();
  });
  byId("clear-intent").addEventListener("click", () => {
    current = null;
    comparisons = [];
    byId("intent-message").value = "";
    byId("intent-example").value = "";
    byId("intent-result").hidden = true;
    renderComparisons();
    byId("intent-status").textContent =
      "Sessão limpa. Textos e comparações descartados desta prévia.";
    byId("intent-message").focus();
  });
  function showContext(panel) {
    if (!current) return;
    const result = current.result;
    byId("intent-context-title").textContent =
      panel === "conversation" ? "Caixa Unificada · prévia" : "Cliente 360 · prévia";
    const content = byId("intent-context-content");
    content.replaceChildren();
    content.append(
      element(
        "p",
        window.SocialMEITapiocaScenario?.active
          ? window.SocialMEITapiocaScenario.customers.find(
              (customer) => customer.messages.at(-1).text === current.text,
            )?.name || "Mensagem avulsa · cliente não identificado"
          : "Cliente de demonstração",
        "eyebrow",
      ),
      element("h3", result.label),
      element("p", result.explanation),
    );
    if (panel === "client")
      content.append(
        element(
          "p",
          `${comparisons.length} mensagens guardadas para comparação nesta sessão. Não é um histórico do CRM.`,
          "muted",
        ),
      );
    content.append(
      element("blockquote", current.text || "Mensagem vazia", "intent-context-message"),
    );
    const signals = element("ul");
    result.signals.forEach((signal) => {
      const item = element("li", signal.label);
      item.append(element("blockquote", signal.evidence[0].text, "intent-evidence"));
      signals.append(item);
    });
    content.append(
      signals,
      element("h3", "Próximo passo sugerido"),
      element("p", result.nextStep),
      element(
        "p",
        "Nenhuma resposta, tarefa, oportunidade ou alteração no cliente real foi criada.",
        "muted",
      ),
    );
    document
      .querySelectorAll("#intent-context [data-intent-context]")
      .forEach((button) =>
        button.setAttribute("aria-pressed", String(button.dataset.intentContext === panel)),
      );
    if (!byId("intent-context").open) byId("intent-context").showModal();
  }
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-intent-context]");
    if (button) showContext(button.dataset.intentContext);
  });
})();
