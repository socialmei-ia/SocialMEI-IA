/* WAHA receiving readiness for the authenticated V22 integration screen.
   A registered channel is not proof of a live WAHA session or outbound sending. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIWhatsAppReadiness) return;

  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  let owner = scope();
  let phase = "loading";
  let receiving = false;
  let receiptPhase = "loading";
  let receipt = null;
  let pending = null;

  function setLabel(element, value) {
    if (!element) return;
    if (element.matches(".st2")) {
      const text = [...element.childNodes].find((node) => node.nodeType === Node.TEXT_NODE);
      if (text) text.textContent = value;
      else element.appendChild(element.ownerDocument.createTextNode(value));
    } else {
      element.textContent = value;
    }
  }

  function paint() {
    if (scope() !== owner) {
      owner = scope();
      phase = "loading";
      receiving = false;
      receiptPhase = "loading";
      receipt = null;
    }
    const label =
      phase === "loading"
        ? "Consultando…"
        : phase === "error"
          ? "Estado não verificado"
          : receiving
            ? "Recebimento configurado"
            : "Não configurado";

    for (const row of document.querySelectorAll(".sw, #cg .cn")) {
      if (row.querySelector("b")?.textContent.trim() !== "WhatsApp") continue;
      const badge = row.querySelector(".st2, .chip");
      // The catalog panel can verify that a channel is registered without
      // proving that the WAHA receiver is working. Preserve that narrower
      // evidence when the separate readiness endpoint cannot be verified.
      const catalogLabel = badge
        ? [...badge.childNodes]
            .filter((child) => child.nodeType === Node.TEXT_NODE)
            .map((child) => child.textContent.trim())
            .find((value) => value === "Canal cadastrado" || value === "Aguardando canal")
        : null;
      const preserveCatalogLabel = !!catalogLabel && !(phase === "ready" && receiving);
      if (!preserveCatalogLabel) setLabel(badge, label);
      if (badge) {
        badge.classList.remove("s-g", "s-ok", "c-ok", "c-mu", "c-er");
        badge.classList.add(
          badge.matches(".st2")
            ? receiving && phase === "ready"
              ? "s-ok"
              : "s-g"
            : receiving && phase === "ready"
              ? "c-ok"
              : "c-mu",
        );
        badge.title =
          receiving && phase === "ready"
            ? "Canal de recebimento registrado. Sessão WAHA e envio não verificados por esta tela."
            : preserveCatalogLabel
              ? "O cadastro do canal é conhecido; a recepção WAHA não foi verificada por esta consulta."
              : "Não foi possível confirmar um canal de recebimento autorizado.";
      }
      if (row.matches(".cn")) {
        const description = row.querySelector("p");
        if (description)
          description.textContent =
            receiving && phase === "ready"
              ? "Recebimento cadastrado no servidor. A sessão atual e as respostas automáticas ainda precisam de verificação."
              : "O recebimento real ainda não foi confirmado para este negócio.";
      }
      if (
        row.matches(".cn") ||
        (row.matches(".sw") && location.hash.startsWith("#/config/integracoes"))
      )
        paintReceipt(row);
      const button = row.querySelector("button");
      if (button && button.disabled) {
        button.textContent = "Gerenciado pela equipe";
        if (button.style) {
          button.style.whiteSpace = "normal";
          button.style.height = "auto";
          button.style.minHeight = "44px";
          button.style.maxWidth = "120px";
        }
        button.title =
          "A conexão WhatsApp depende de provisionamento seguro; este botão não inicia pareamento.";
      }
    }
  }

  function paintReceipt(row) {
    let panel = row.matches(".sw")
      ? row.nextElementSibling?.matches("[data-wa-receiving]") && row.nextElementSibling
      : row.querySelector("[data-wa-receiving]");
    if (!panel) {
      panel = document.createElement("section");
      panel.dataset.waReceiving = "true";
      panel.style.cssText = "margin-top:12px;display:grid;gap:8px;min-width:0";
      const title = document.createElement("strong");
      title.textContent = "Recebimento na Caixa";
      const status = document.createElement("p");
      status.dataset.waReceivingStatus = "true";
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      const caveat = document.createElement("p");
      caveat.textContent =
        "Histórico salvo neste negócio. Não comprova sessão WAHA ativa agora, entrega ou envio de respostas.";
      const update = document.createElement("button");
      update.type = "button";
      update.className = "btn o";
      update.textContent = "Atualizar recebimento";
      update.onclick = refresh;
      const inbox = document.createElement("a");
      inbox.href = "#/caixa";
      inbox.textContent = "Abrir Caixa Unificada";
      panel.append(title, status, caveat, update, inbox);
      if (row.matches(".sw")) row.after(panel);
      else row.append(panel);
    }
    const status = panel.querySelector("[data-wa-receiving-status]");
    if (receiptPhase === "loading") status.textContent = "Consultando mensagens persistidas…";
    else if (receiptPhase === "error")
      status.textContent = "Recebimento não verificado. Não foi possível consultar o histórico.";
    else if (!receipt.message_count)
      status.textContent = "Nenhuma mensagem WhatsApp recebida e persistida neste negócio.";
    else
      status.textContent =
        receipt.message_count +
        " mensagem(ns) recebida(s) em " +
        receipt.conversation_count +
        " conversa(s). Última gravação: " +
        new Date(receipt.last_persisted_at).toLocaleString("pt-BR") +
        ".";
    panel.setAttribute("aria-busy", String(receiptPhase === "loading"));
    panel.querySelector("button").disabled = receiptPhase === "loading";
  }

  async function loadReceipt(expectedScope) {
    try {
      const result = await host.request("/whatsapp/receiving-status");
      if (scope() !== expectedScope) return;
      if (
        result?.source !== "postgresql" ||
        result?.workspace_id !== host.identity.negocio.id ||
        !Number.isSafeInteger(result.message_count) ||
        result.message_count < 0 ||
        !Number.isSafeInteger(result.conversation_count) ||
        result.conversation_count < 0 ||
        result.conversation_count > result.message_count ||
        result.historical_receiving_confirmed !== result.message_count > 0 ||
        result.session_live_verified !== false ||
        result.sending_available !== false ||
        (result.message_count > 0 && !Number.isFinite(Date.parse(result.last_persisted_at))) ||
        (result.message_count === 0 && result.last_persisted_at !== null)
      )
        throw Error("Histórico inválido");
      receipt = result;
      receiptPhase = "ready";
    } catch {
      if (scope() === expectedScope) {
        receipt = null;
        receiptPhase = "error";
      }
    }
  }

  async function refresh() {
    if (pending) return pending;
    const previousOwner = scope();
    phase = "loading";
    receiptPhase = "loading";
    paint();
    pending = (async () => {
      const receiptRequest = loadReceipt(previousOwner);
      try {
        const response = await host.request("/integrations/readiness");
        const status = response?.whatsapp;
        if (
          response?.source !== "server" ||
          typeof status?.configured !== "boolean" ||
          typeof status?.receiving_configured !== "boolean" ||
          status?.sending_available !== false
        )
          throw Error("WAHA readiness inválida");
        if (scope() !== previousOwner) return;
        receiving = status.configured && status.receiving_configured;
        phase = "ready";
      } catch {
        if (scope() === previousOwner) {
          receiving = false;
          phase = "error";
        }
      } finally {
        await receiptRequest;
        pending = null;
        paint();
      }
    })();
    return pending;
  }

  const priorRender = render;
  render = () => {
    priorRender();
    paint();
  };
  window.addEventListener("hashchange", () => {
    paint();
    if (location.hash.startsWith("#/config/integracoes")) refresh();
  });
  window.SocialMEIWhatsAppReadiness = { refresh };
  paint();
  refresh();
})();
