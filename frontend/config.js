/* PUBLIC CONFIGURATION */
// Apenas configuração pública. Segredos devem permanecer no servidor/n8n.
const SOCIALMEI_CONFIG = Object.freeze({
  // Experimental branch: no automatic connection to a live message endpoint.
  n8nMessagesUrl: null,
  n8nAuthHeader: null,
  // Desabilitado por padrão. Handoff externo somente para piloto isolado da equipe.
  instagramPublisher: { mode: "disabled", formPath: "/form/instagram-post" },
  // Ativar somente em desenvolvimento/staging com API e workspace conferidos.
  clientes: { mode: "local", apiBaseUrl: "", workspaceKey: "" },
});
