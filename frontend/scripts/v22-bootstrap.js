/* Execute the unchanged V22 application only after the server identity is known. */
(async () => {
  const auth = window.SocialMEIAuth;
  const detailsStyle = document.createElement("link");
  detailsStyle.rel = "stylesheet";
  detailsStyle.href = "styles/v22-client-details.css";
  document.head.appendChild(detailsStyle);
  await auth.ready;
  if (auth.remote && !auth.current) {
    if (!auth.problem && localStorage.getItem("socialmei-auth-browser-scope")) return;
    location.replace("/frontend/entrada.html" + (location.hash ? "#/entrar" : ""));
    return;
  }
  if (auth.remote && auth.current.papel === "report_viewer") {
    location.replace("/frontend/relatorios-leitura.html");
    return;
  }
  if (auth.remote) {
    if (location.pathname !== "/frontend/socialmei-app.html") {
      location.replace("/frontend/socialmei-app.html" + location.search + location.hash);
      return;
    }
    // The Meta callback marker is only a UI hint, never proof of a valid token.
    // Normalize it before the V22 router loads to avoid a transient 404.
    const instagramReturn = /^#instagram=(connected|failed)$/.exec(location.hash);
    if (instagramReturn) {
      window.__socialmeiInstagramCallbackOutcome = instagramReturn[1];
      history.replaceState(
        history.state,
        "",
        location.pathname + location.search + "#/config/integracoes",
      );
    }
    const prefix = `smei-v22-account:${auth.current.usuario.id}:${auth.current.negocio.id}:`;
    for (const method of ["getItem", "setItem", "removeItem"]) {
      const original = Storage.prototype[method];
      Storage.prototype[method] = function (key, ...args) {
        const mapped =
          this === localStorage &&
          /^smei(?:-|4_)/.test(String(key)) &&
          !String(key).startsWith("smei-v22-account:")
            ? prefix + key
            : key;
        return original.call(this, mapped, ...args);
      };
    }
  }
  document.getElementById("app").hidden = auth.remote;
  const original = document.getElementById("v22-native-source");
  const run = document.createElement("script");
  run.textContent = original.textContent;
  document.body.appendChild(run);
  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "scripts/v22-backend.js";
    script.onload = resolve;
    script.onerror = reject;
    document.body.appendChild(script);
  });
  await window.SocialMEIV22.ready;
  if (auth.remote) {
    const agenda = document.createElement("script");
    agenda.src = "scripts/v22-agenda.js";
    agenda.onload = () => {
      const appointments = document.createElement("script");
      appointments.src = "scripts/v22-appointments.js";
      appointments.onerror = () => console.warn("Agendamentos de serviços indisponíveis.");
      document.body.appendChild(appointments);
    };
    agenda.onerror = () => console.warn("Agenda compartilhada indisponível.");
    document.body.appendChild(agenda);
    const knowledge = document.createElement("script");
    knowledge.src = "scripts/v22-knowledge-reporting.js";
    knowledge.onerror = () => console.warn("Gestão de conhecimento indisponível.");
    document.body.appendChild(knowledge);
    const whatsapp = document.createElement("script");
    whatsapp.src = "scripts/v22-whatsapp-catalog.js";
    whatsapp.onerror = () => console.warn("Consulta de catálogo WhatsApp indisponível.");
    document.body.appendChild(whatsapp);
    const whatsappBot = document.createElement("script");
    whatsappBot.src = "scripts/v22-whatsapp-bot.js";
    whatsappBot.onerror = () => console.warn("Controle de atendimento WhatsApp indisponível.");
    document.body.appendChild(whatsappBot);
    const inboxCustomer = document.createElement("script");
    inboxCustomer.src = "scripts/v22-inbox-customer.js";
    inboxCustomer.onerror = () => console.warn("Vínculo da Caixa com o CRM indisponível.");
    document.body.appendChild(inboxCustomer);
    const whatsappReplies = document.createElement("script");
    whatsappReplies.src = "scripts/v22-whatsapp-replies.js";
    whatsappReplies.onerror = () => console.warn("Respostas WhatsApp indisponíveis.");
    document.body.appendChild(whatsappReplies);
    const whatsappReadiness = document.createElement("script");
    whatsappReadiness.src = "scripts/v22-whatsapp-readiness.js";
    whatsappReadiness.onerror = () => console.warn("Estado WhatsApp indisponível.");
    document.body.appendChild(whatsappReadiness);
    const providerAnalysis = document.createElement("script");
    providerAnalysis.src = "scripts/v22-provider-analysis.js";
    providerAnalysis.onerror = () => console.warn("Exibição da análise de mensagens indisponível.");
    document.body.appendChild(providerAnalysis);
    const collaborator = document.createElement("script");
    collaborator.src = "scripts/v22-report-access.js";
    collaborator.onerror = () => console.warn("Acesso aos relatórios indisponível.");
    document.body.appendChild(collaborator);
    const businesses = document.createElement("script");
    businesses.src = "scripts/v22-businesses.js";
    businesses.onerror = () => console.warn("Meus negócios indisponível.");
    document.body.appendChild(businesses);
    const exports = document.createElement("script");
    exports.src = "scripts/v22-business-export.js";
    exports.onerror = () => console.warn("Exportação indisponível.");
    document.body.appendChild(exports);
    const team = document.createElement("script");
    team.src = "scripts/v22-team-members.js";
    team.onerror = () => console.warn("Equipe indisponível.");
    document.body.appendChild(team);
    const saleHistory = document.createElement("script");
    saleHistory.src = "scripts/v22-sale-history.js";
    saleHistory.onerror = () => console.warn("Histórico das vendas indisponível.");
    document.body.appendChild(saleHistory);
    const customerReports = document.createElement("script");
    customerReports.src = "scripts/v22-customer-reporting.js";
    customerReports.onerror = () => console.warn("Indicadores de clientes indisponíveis.");
    document.body.appendChild(customerReports);
    const financeReports = document.createElement("script");
    financeReports.src = "scripts/v22-finance-reporting.js";
    financeReports.onerror = () => console.warn("Relatório financeiro indisponível.");
    document.body.appendChild(financeReports);
    const productReports = document.createElement("script");
    productReports.src = "scripts/v22-product-reporting.js";
    productReports.onerror = () => console.warn("Relatório de produtos indisponível.");
    document.body.appendChild(productReports);
    const workspaceAudit = document.createElement("script");
    workspaceAudit.src = "scripts/v22-workspace-audit.js";
    workspaceAudit.onerror = () => console.warn("Histórico do negócio indisponível.");
    document.body.appendChild(workspaceAudit);
    const businessStart = document.createElement("script");
    businessStart.src = "scripts/v22-business-start.js";
    businessStart.onerror = () => console.warn("Primeiros passos indisponíveis.");
    document.body.appendChild(businessStart);
  }
  if (auth.remote) {
    const instagram = document.createElement("script");
    instagram.src = "scripts/v22-instagram.js";
    instagram.onerror = () => console.warn("Controles Instagram indisponíveis.");
    instagram.onload = () => {
      const direct = document.createElement("script");
      direct.src = "scripts/v22-instagram-direct.js";
      direct.onerror = () => console.warn("Respostas Instagram indisponíveis.");
      document.body.appendChild(direct);
      const publishing = document.createElement("script");
      publishing.src = "scripts/v22-instagram-publisher.js";
      publishing.onerror = () => console.warn("Publicação Instagram indisponível.");
      document.body.appendChild(publishing);
      const media = document.createElement("script");
      media.src = "scripts/v22-instagram-media.js";
      media.onerror = () => console.warn("Consulta de publicações Instagram indisponível.");
      document.body.appendChild(media);
    };
    document.body.appendChild(instagram);
  }
  if (!auth.remote) {
    const profile = document.createElement("script");
    profile.src = "scripts/app-perfil.js";
    document.body.appendChild(profile);
  }
})().catch(() => {
  const app = document.getElementById("app");
  app.hidden = false;
  app.setAttribute("role", "alert");
  app.textContent =
    "Não foi possível carregar sua sessão. Atualize a página para tentar novamente.";
});
