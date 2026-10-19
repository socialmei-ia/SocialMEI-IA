/* Instagram publication pilot: handoff only, not an n8n API client. */
const SocialMEIInstagramPublisher = (() => {
  "use strict";

  const formatText = Object.freeze({
    feed: {
      label: "Feed",
      guide:
        "O formulário externo permite selecionar várias fotos e escolher entre carrossel ou publicações separadas. Confira essa opção nele.",
    },
    story: {
      label: "Story",
      guide:
        "O formulário externo aceita um arquivo para Story. Confira o formato e o destino antes de confirmar.",
    },
    reel: {
      label: "Reel",
      guide:
        "O formulário externo aceita um arquivo para Reel. Verifique o vídeo e as opções disponíveis antes de confirmar.",
    },
  });

  function inspect(config, origin) {
    if (config?.mode !== "external-pilot")
      return { available: false, reason: "Integração não habilitada neste ambiente." };
    if (
      typeof config.formPath !== "string" ||
      !/^\/form\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(config.formPath)
    )
      return { available: false, reason: "Caminho do formulário não validado." };
    try {
      const target = new URL(config.formPath, origin);
      if (target.protocol !== "https:" || target.origin !== new URL(origin).origin)
        return { available: false, reason: "Formulário fora da origem HTTPS autorizada." };
      return { available: true, href: target.href };
    } catch {
      return { available: false, reason: "Configuração do formulário inválida." };
    }
  }

  function guide(format) {
    return formatText[format] || formatText.feed;
  }

  function init() {
    const byId = (id) => document.getElementById(id),
      start = byId("instagramPublishStart"),
      status = byId("instagramPublishStatus"),
      badge = byId("instagramPublishState"),
      format = byId("instagramPublishFormat"),
      details = byId("instagramPublishGuide"),
      external = byId("instagramPublishExternal");
    if (!start || !status || !external) return;

    const connection = inspect(SOCIALMEI_CONFIG.instagramPublisher, location.origin);
    let confirmedScope = null;
    function currentScope() {
      return SocialMEIBusinessProfile.browserRepository().scope();
    }
    function render() {
      const selected =
        document.querySelector('.content-formats [data-content-format][aria-selected="true"]')
          ?.dataset.contentFormat || "feed";
      const selectedGuide = guide(selected);
      format.textContent = selectedGuide.label;
      details.textContent = selectedGuide.guide;
      const ready = connection.available && Boolean(currentScope());
      start.disabled = !ready;
      start.textContent = connection.available
        ? "Continuar no formulário"
        : "Publicação em configuração";
      badge.textContent = connection.available ? "Piloto externo" : "Integração pendente";
      status.textContent = connection.available
        ? ready
          ? "A próxima etapa acontece no n8n. O texto e os arquivos não são transferidos automaticamente."
          : "Entre em uma sessão válida para abrir o formulário deste negócio."
        : "O fluxo de publicação não está habilitado neste ambiente. Rascunhos e prévia continuam disponíveis.";
      external.href = ready ? connection.href : "#";
    }
    start.addEventListener("click", () => {
      if (!connection.available) return;
      confirmedScope = currentScope();
      if (!confirmedScope) return render();
      external.href = connection.href;
      openModal("instagramPublishModal");
    });
    external.addEventListener("click", (event) => {
      if (!connection.available || !confirmedScope || currentScope() !== confirmedScope) {
        event.preventDefault();
        confirmedScope = null;
        closeModal("instagramPublishModal");
        render();
        status.textContent = "A sessão mudou. Reabra o formulário após conferir seu negócio.";
        return;
      }
      confirmedScope = null;
      closeModal("instagramPublishModal");
      status.textContent =
        "Formulário externo aberto. Confira nele a confirmação da operação: abrir a página não publica conteúdo.";
    });
    document.querySelector(".content-formats")?.addEventListener("click", render);
    document.addEventListener("socialmei-view-change", () => {
      if (currentView !== "Divulgação") {
        confirmedScope = null;
        if (byId("instagramPublishModal").classList.contains("open"))
          closeModal("instagramPublishModal");
      } else render();
    });
    document.addEventListener("socialmei-data-change", () => {
      if (confirmedScope && currentScope() !== confirmedScope) {
        confirmedScope = null;
        if (byId("instagramPublishModal").classList.contains("open"))
          closeModal("instagramPublishModal");
      }
      render();
    });
    render();
  }

  if (typeof document !== "undefined") init();
  return Object.freeze({ inspect, guide });
})();
if (typeof module !== "undefined" && module.exports) module.exports = SocialMEIInstagramPublisher;
