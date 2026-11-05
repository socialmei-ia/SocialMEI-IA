const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  for (const width of [390, 1440])
    for (const dark of [false, true]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        colorScheme: dark ? "dark" : "light",
      });
      const page = await context.newPage(),
        calls = [],
        errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      await page.route("**/*", (route) => {
        const request = route.request(),
          url = new URL(request.url());
        if (url.origin !== origin) return route.abort();
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        calls.push({ path: url.pathname, method: request.method() });
        if (url.pathname.endsWith("/auth/session"))
          return route.fulfill({
            json: {
              usuario: { id: 91, nome: "Leitor fictício", email: "viewer@example.test" },
              negocio: { id: 17, nome: "Empresa fictícia", slug: "viewer", configuracao: {} },
              papel: "report_viewer",
              csrf_token: "a".repeat(64),
            },
          });
        if (url.pathname.endsWith("/auth/workspaces"))
          return route.fulfill({
            json: {
              active_workspace_id: 17,
              items: [{ id: 17, nome: "Empresa fictícia", role: "report_viewer" }],
            },
          });
        const period = { start: "2026-11-01", end: "2026-11-30", timezone: "America/Recife" };
        if (url.pathname.endsWith("/reporting/overview"))
          return route.fulfill({
            json: {
              totals: { clientes: 1, itens_ativos: 1, estoque_baixo: 1 },
              sales_by_status: {},
              finance_by_type_and_status: [],
            },
          });
        if (url.pathname.endsWith("/reporting/customers"))
          return route.fulfill({
            json: {
              workspace_id: 17,
              period,
              new_customers: 1,
              buyers: 1,
              repeat_buyers: 0,
              returning_buyers: 0,
              identification_available: false,
              customers: [],
              description: "Vendas válidas.",
              repeat_description: "Duas compras no período.",
              returning_description: "Compra anterior.",
            },
          });
        if (url.pathname.endsWith("/reporting/finance"))
          return route.fulfill({
            json: {
              workspace_id: 17,
              period,
              paid: { count: 1, incoming: "59.90", outgoing: "0.00", balance: "59.90" },
              previous: { start: "2026-10-02", end: "2026-10-31", balance: "0.00" },
              balance_change: "59.90",
              pending: { incoming: "0.00", outgoing: "0.00" },
              undated_paid_count: 0,
              daily: [
                { date: "2026-11-01", incoming: "59.90", outgoing: "0.00", balance: "59.90" },
              ],
              description: "Não é lucro ou saldo bancário.",
              pending_description: "Pendências por vencimento.",
            },
          });
        if (url.pathname.endsWith("/reporting/products"))
          return route.fulfill({
            json: {
              workspace_id: 17,
              kind: url.searchParams.get("kind"),
              period,
              totals: { active_products: 1, low_stock: 1, no_sales: 0 },
              products: [
                {
                  id: 1,
                  name: "Produto fictício",
                  category: "Teste",
                  price: "59.90",
                  stock: 1,
                  minimum: 2,
                },
              ],
              next_after: null,
              description: "Estoque atual.",
              sales_description: "Sem vendas no período.",
            },
          });
        return route.fulfill({
          status: 403,
          json: { detail: "Não autorizado nesta sessão de leitura." },
        });
      });
      try {
        await page.goto(origin + "/frontend/relatorios-leitura.html");
        await page
          .getByText("Indicadores atualizados; valores agregados sem dados individuais.", {
            exact: true,
          })
          .waitFor();
        await page.locator("[data-customer-report]").waitFor();
        assert.equal(
          await page.locator("[data-customer-report]").count(),
          1,
          "Report-only users need the permitted customer panel",
        );
        await page
          .getByText("Seu acesso permite indicadores agregados, sem identificação de clientes.", {
            exact: true,
          })
          .waitFor();
        await page
          .locator("[data-finance-report]")
          .getByText("Entradas registradas como pagas: R$ 59,90", { exact: true })
          .waitFor();
        await page
          .locator("[data-product-report]")
          .getByText("Produto fictício", { exact: true })
          .waitFor();
        assert.equal(
          await page.getByRole("button", { name: "Adicionar negócio", exact: true }).count(),
          0,
        );
        assert.equal(
          await page.getByRole("button", { name: "Novo cliente", exact: true }).count(),
          0,
        );
        assert.ok(
          calls.every((r) => r.method === "GET"),
          "Detailed panels must never write",
        );
        assert.ok(
          calls.every((r) => /\/auth\/|\/reporting\//.test(r.path)),
          "No raw CRM or message endpoints",
        );
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        assert.deepEqual(errors, []);
      } finally {
        await context.close();
      }
    }
  console.log(
    "Report-only decision panels: actual restricted entry, aggregate privacy, GET-only transport, mobile/desktop and light/dark PASS (controlled API)",
  );
};
