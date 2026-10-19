/* Instagram publication pilot: handoff only, not an n8n API client. */
const SocialMEIInstagramPublisher = (() => {
  "use strict";

  const formatText = Object.freeze({
    feed: {
      label: "Feed",
      guide:
        "O fluxo externo declara até 10 fotos para carrossel ou posts separados. Vídeo no Feed não foi homologado; selecione as mídias novamente no n8n.",
    },
    story: {
      label: "Story",
      guide:
        "O fluxo externo aceita um arquivo (imagem ou vídeo) para Story. Ele não publica a legenda do Story; confira a conta antes de confirmar.",
    },
    reel: {
      label: "Reel",
      guide:
        "O fluxo externo precisa de um vídeo para Reel e aguarda o processamento da Meta. Confira o arquivo e a conta antes de confirmar.",
    },
  });

  function inspect(config, origin) {
    if (config?.mode !== "external-pilot")
      return { available: false, reason: "Integração não habilitada neste ambiente." };
    const validPath = /^\/form\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/;
    try {
      const site = new URL(origin);
      if (site.protocol !== "https:" || site.username || site.password)
        return { available: false, reason: "O piloto exige uma origem HTTPS." };
      if (config.formUrl != null) {
        if (typeof config.formUrl !== "string" || typeof config.approvedOrigin !== "string")
          return { available: false, reason: "Origem externa não aprovada." };
        const target = new URL(config.formUrl);
        const approved = new URL(config.approvedOrigin);
        if (
          target.protocol !== "https:" ||
          approved.protocol !== "https:" ||
          approved.href !== approved.origin + "/" ||
          target.origin !== approved.origin ||
          !validPath.test(target.pathname) ||
          target.search ||
          target.hash ||
          target.username ||
          target.password
        )
          return { available: false, reason: "Formulário externo não autorizado." };
        return { available: true, href: target.href };
      }
      if (typeof config.formPath !== "string" || !validPath.test(config.formPath))
        return { available: false, reason: "Caminho do formulário não validado." };
      const target = new URL(config.formPath, site);
      if (target.origin !== site.origin)
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
