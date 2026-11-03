/* Display server-owned analysis of incoming messages; no analysis or transport here. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIProviderAnalysis) return;
  const sentiments = {
    positive: "positivo",
    negative: "negativo",
    neutral: "neutro",
    uncertain: "indefinido",
  };
  const confidences = { low: "baixa", medium: "média", high: "alta" };
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function valid(message) {
    const value = message.provider_analysis;
    return (
      Number.isSafeInteger(message.id) &&
      message.id > 0 &&
      (!message.direction || message.direction === "incoming") &&
      typeof message.text === "string" &&
      value &&
      !Array.isArray(value) &&
      typeof value === "object" &&
      Object.keys(value).sort().join(",") === "confidence,explanation,sentiment,source" &&
      value.source === "automation" &&
      Object.hasOwn(sentiments, value.sentiment) &&
      Object.hasOwn(confidences, value.confidence) &&
      typeof value.explanation === "string" &&
      value.explanation.trim().length > 0 &&
      value.explanation.length <= 500 &&
      !/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value.explanation)
    );
  }
  let panel;
  function mount() {
    const expanded = panel?.open;
    panel?.remove();
    panel = null;
    const match = /^#\/caixa\/(me-\d+)$/.exec(location.hash);
    const row = match && host.conversation(match[1]);
    if (!row || !["instagram", "waha"].includes(row.origin)) return;
    const thread = document.querySelector(".ct");
    if (!thread) return;
    const messages = (row.messages || []).filter(valid).slice(-10);
    if (!messages.length) return;
    panel = element("details");
    panel.className = "m sm";
    panel.dataset.providerAnalysis = "true";
    panel.open = expanded || false;
    panel.setAttribute("aria-label", "Análise automática das mensagens recebidas");
    panel.style.cssText =
      "margin:8px 16px;padding:8px 12px;border:1px solid var(--b);border-radius:10px;background:var(--w);color:var(--t);max-height:34vh;overflow:auto;flex-shrink:0;overflow-wrap:anywhere";
    const summary = element(
      "summary",
      `Análise automática · ${messages.length} ${messages.length === 1 ? "mensagem recebida" : "mensagens recebidas"}`,
    );
    summary.style.cssText =
      "min-height:44px;display:flex;align-items:center;cursor:pointer;font-weight:600";
    panel.append(summary);
    for (const message of messages) {
      const value = message.provider_analysis;
      const item = element("article");
      item.dataset.messageId = String(message.id);
      item.style.cssText = "padding:10px 0;border-top:1px solid var(--b)";
      const date = new Date(message.occurred_at);
      const time = Number.isNaN(date.getTime())
        ? "Mensagem recebida"
        : "Recebida em " + date.toLocaleString("pt-BR");
      const excerpt = message.text.length > 160 ? message.text.slice(0, 160) + "…" : message.text;
      item.append(
        element("p", time),
        element("blockquote", excerpt),
        element(
          "p",
          `Sentimento ${sentiments[value.sentiment]} · confiança ${confidences[value.confidence]} · fonte: automação`,
        ),
        element("p", value.explanation),
      );
      panel.append(item);
    }
    const messageList = thread.querySelector?.(".ms");
    if (messageList) thread.insertBefore(panel, messageList);
    else thread.append(panel);
  }
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      const result = render.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  window.SocialMEIProviderAnalysis = { refresh: mount };
  queueMicrotask(mount);
})();
