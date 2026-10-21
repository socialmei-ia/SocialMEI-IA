/* Public configuration for the isolated localhost preview; no secrets. */
const SOCIALMEI_CONFIG = Object.freeze({
  n8nMessagesUrl: null,
  n8nAuthHeader: null,
  auth: { mode: "remote", apiBaseUrl: "/api/v1" },
  clientes: { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "preview" },
  produtos: { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "preview" },
  vendas: { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "preview" },
  financeiro: { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "preview" },
  contentPreparation: { mode: "simulation" },
  instagramSimulation: { mode: "simulation" },
  instagramPublisher: { mode: "disabled" },
});
