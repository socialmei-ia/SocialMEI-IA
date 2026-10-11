/* PUBLIC CONFIGURATION */
// Apenas configuração pública. Segredos devem permanecer no servidor/n8n.
const SOCIALMEI_CONFIG = Object.freeze({
  n8nMessagesUrl:
    "https://socialmei.54-94-213-7.sslip.io/webhook/5f82c1c2-99de-43f4-9578-42f3aa901fcf",
  n8nAuthHeader: null,
  // Ativar somente em desenvolvimento/staging com API e workspace conferidos.
  clientes: { mode: "local", apiBaseUrl: "", workspaceKey: "" },
});
