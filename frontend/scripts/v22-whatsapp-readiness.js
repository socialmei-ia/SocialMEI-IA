/* WAHA receiving readiness for the authenticated V22 integration screen.
   A registered channel is not proof of a live WAHA session or outbound sending. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIWhatsAppReadiness) return;

  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  let owner = scope();
  let phase = "loading";
  let receiving = false;
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
    }
    const label =
      phase === "loading" ? "Consultando…" :
      phase === "error" ? "Estado não verificado" :
      receiving ? "Recebimento configurado" : "Não configurado";

    for (const row of document.querySelectorAll(".sw, #cg .cn")) {
      if (row.querySelector("b")?.textContent.trim() !== "WhatsApp") continue;
      const badge = row.querySelector(".st2, .chip");
      setLabel(badge, label);
      if (badge) {
        badge.classList.remove("s-g", "s-ok", "c-ok", "c-mu", "c-er");
        badge.classList.add(
          badge.matches(".st2")
            ? receiving && phase === "ready" ? "s-ok" : "s-g"
            : receiving && phase === "ready" ? "c-ok" : "c-mu",
        );
        badge.title = receiving && phase === "ready"
          ? "Canal de recebimento registrado. Sessão WAHA e envio não verificados por esta tela."
          : "Não foi possível confirmar um canal de recebimento autorizado.";
      }
      if (row.matches(".cn")) {
        const description = row.querySelector("p");
        if (description) description.textContent =
          receiving && phase === "ready"
            ? "Recebimento cadastrado no servidor. A sessão atual e as respostas automáticas ainda precisam de verificação."
            : "O recebimento real ainda não foi confirmado para este negócio.";
      }
      const button = row.querySelector("button");
      if (button && button.disabled) {
        button.textContent = "Gerenciado pela equipe";
        button.title = "A conexão WhatsApp depende de provisionamento seguro; este botão não inicia pareamento.";
      }
    }
  }

  async function refresh() {
    if (pending) return pending;
    const previousOwner = scope();
    phase = "loading";
    paint();
    pending = (async () => {
      try {
        const response = await host.request("/integrations/readiness");
        const status = response?.whatsapp;
        if (
          response?.source !== "server" ||
          typeof status?.configured !== "boolean" ||
          typeof status?.receiving_configured !== "boolean" ||
          status?.sending_available !== false
        ) throw Error("WAHA readiness inválida");
        if (scope() !== previousOwner) return;
        receiving = status.configured && status.receiving_configured;
        phase = "ready";
      } catch {
        if (scope() === previousOwner) {
          receiving = false;
          phase = "error";
        }
      } finally {
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
