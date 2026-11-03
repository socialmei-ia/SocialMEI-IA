/* PUBLIC CONFIGURATION */
// Apenas configuração pública. Segredos devem permanecer no servidor/n8n.
const SOCIALMEI_CONFIG = Object.freeze({
  // Experimental branch: no automatic connection to a live message endpoint.
  n8nMessagesUrl: null,
  n8nAuthHeader: null,
  // Desabilitado por padrão. Handoff externo somente para piloto isolado da equipe.
  instagramPublisher: { mode: "disabled", formPath: "/form/instagram-post" },
  // Ativar somente no staging com auth remota e backend em modo simulation.
  instagramSimulation: { mode: "disabled" },
  // Piloto externo opcional: somente após confirmar a instância, a conta e o responsável.
  // Ex.: { mode: "external-pilot", formUrl: "https://SUA-INSTANCIA/form/instagram-post",
  //        approvedOrigin: "https://SUA-INSTANCIA" }. Nunca incluir tokens ou credenciais.
  // Ativar somente em desenvolvimento/staging com API e workspace conferidos.
  clientes: { mode: "local", apiBaseUrl: "", workspaceKey: "" },
  // Optional identifiers for the PUBLIC informational page (/sobre.html).
  // Do not enable until the owner has configured GA4/Clarity, privacy settings
  // and the explicit opt-in banner. Never add CRM/customer identifiers here.
  siteMetrics: {
    enabled: false,
    ga4MeasurementId: "",
    clarityProjectId: "",
  },
});
