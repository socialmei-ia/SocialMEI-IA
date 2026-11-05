/* Reuse pure GET panels in the restricted page, without loading the CRM runtime. */
window.SocialMEIReportDetailsReady = (async () => {
  const auth = window.SocialMEIAuth;
  if (!auth) return;
  await auth.ready;
  if (!auth.remote || auth.current?.papel !== "report_viewer") return;
  const view = document.getElementById("v"),
    message = document.getElementById("report-details-status");
  if (!view || !message) return;
  history.replaceState(history.state, "", location.pathname + location.search + "#/relatorios");
  window.SocialMEIV22 = Object.freeze({
    remote: true,
    get identity() {
      return auth.current;
    },
    request(route) {
      // No caller can use this adapter for mutations or arbitrary endpoints.
      if (!/^\/reporting\/(customers|finance|products)(?:\?|$)/.test(route))
        return Promise.reject(Error("Consulta não disponível neste painel."));
      return auth.request(route);
    },
  });
  message.textContent = "Carregando indicadores detalhados…";
  for (const name of [
    "v22-customer-reporting.js",
    "v22-finance-reporting.js",
    "v22-product-reporting.js",
  ]) {
    await new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "scripts/" + name;
      script.onload = resolve;
      script.onerror = reject;
      document.body.append(script);
    });
  }
  message.textContent = "";
})().catch(() => {
  const message = document.getElementById("report-details-status");
  if (message)
    message.textContent =
      "Não foi possível carregar os indicadores detalhados. Atualize a página para tentar novamente.";
});
