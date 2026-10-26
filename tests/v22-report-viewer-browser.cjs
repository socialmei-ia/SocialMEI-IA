/* Report-only users never hydrate the CRM or receive customer records. */
const assert = require("node:assert/strict");

module.exports = async function (browser, origin) {
  const page = await browser.newPage({
    viewport: { width: 390, height: 820 },
    reducedMotion: "reduce",
  });
  const identity = {
    usuario: { id: 41, nome: "Relator", email: "relator@example.test" },
    negocio: { id: 29, slug: "private", nome: "Loja", configuracao: {} },
    papel: "report_viewer",
    csrf_token: "a".repeat(64),
  };
  const paths = [];
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem("socialmei-auth-browser-scope", "41:29");
  });
  await page.route("**/*", (route) => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === "/frontend/config.js") return route.fulfill({
      contentType: "text/javascript",
      body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
    });
    if (!url.pathname.startsWith("/api/v1/")) return route.continue();
    paths.push(url.pathname);
    switch (url.pathname) {
      case "/api/v1/auth/session":
        return route.fulfill({ json: identity });
      case "/api/v1/auth/workspaces":
        return route.fulfill({ json: {
          active_workspace_id: 29,
          items: [{ id: 29, nome: "Loja", role: "report_viewer" }],
        } });
      case "/api/v1/reporting/overview":
        return route.fulfill({ json: {
          period_days: 30,
          totals: { clientes: 8, itens_ativos: 12, estoque_baixo: 1 },
          sales_by_status: { Pago: { quantidade: 2, valor: "75.00" } },
          finance_by_type_and_status: [],
        } });
      default:
        throw Error("Report-only user attempted unrelated API: " + url.pathname);
    }
  });
  try {
    await page.goto(origin + "/frontend/relatorios-leitura.html");
    await page.getByRole("heading", { name: "Relatórios do negócio" }).waitFor();
    await page.getByText("8", { exact: true }).waitFor();
    await page.getByText(/Vendas Pago: 2/).waitFor();
    assert(!paths.some((p) => /clientes|financeiro|knowledge/.test(p)));
    assert.equal(await page.getByText(/somente leitura/i).count() > 0, true);
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
  }
};
