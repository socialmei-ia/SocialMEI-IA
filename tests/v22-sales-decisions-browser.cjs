// Real application DOM with controlled synthetic aggregates, never production data.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

module.exports = async (browser, origin) => {
  for (const width of [390, 1440])
    for (const theme of ["light", "dark"]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage();
      const errors = [],
        queries = [];
      let delayed;
      const identity = {
        usuario: { id: 91, nome: "Pessoa fictícia", email: "fixture@example.test" },
        negocio: { id: 17, slug: "fixture", nome: "Negócio fictício", configuracao: {} },
        papel: "owner",
        csrf_token: "a".repeat(64),
      };
      const report = (empty = false) => ({
        period: {
          start: empty ? "2026-10-01" : "2026-11-01",
          end: empty ? "2026-10-31" : "2026-11-03",
          days: empty ? 31 : 3,
          previous_start: "2026-10-29",
          previous_end: "2026-10-31",
          timezone: "America/Fortaleza",
        },
        current: {
          count: empty ? 0 : 2,
          total: empty ? "0.00" : "119.80",
          average_ticket: empty ? "0.00" : "59.90",
        },
        previous: { count: 0, total: "0.00", average_ticket: "0.00" },
        change_total_percent: null,
        daily: [{ date: "2026-11-01", count: empty ? 0 : 2, total: empty ? "0.00" : "119.80" }],
        products: empty
          ? []
          : [
              {
                product_id: 31,
                name: "<img src=x onerror=alert(1)>",
                quantity: "2",
                sales_count: 2,
                total: "119.80",
              },
            ],
        description:
          "Vendas pagas e pendentes. Não representa receita recebida nem saldo bancário.",
      });
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
        const endpoint = url.pathname.slice(7);
        if (endpoint === "/auth/session") return route.fulfill({ json: identity });
        if (endpoint === "/auth/preferences")
          return route.fulfill({ json: { revision: 0, preferences: { theme } } });
        if (endpoint === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (endpoint === "/reporting/access") return route.fulfill({ json: { items: [] } });
        if (endpoint === "/auth/workspaces")
          return route.fulfill({
            json: {
              active_workspace_id: 17,
              items: [{ id: 17, nome: "Negócio fictício", role: "owner" }],
            },
          });
        if (endpoint === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled" } });
        if (endpoint === "/reporting/overview")
          return route.fulfill({
            json: { period_days: 30, totals: { clientes: 0, itens_ativos: 0, estoque_baixo: 0 } },
          });
        if (endpoint === "/reporting/sales") {
          assert.equal(request.headers()["x-socialmei-identity"], "91:17");
          queries.push(url.search);
          if (url.searchParams.get("start") === "2026-11-10")
            return route.fulfill({
              status: 503,
              json: { detail: "Fonte temporariamente indisponível." },
            });
          if (url.searchParams.get("start") === "2026-12-01") {
            delayed = () => route.fulfill({ json: report() });
            return;
          }
          return route.fulfill({ json: report(url.searchParams.get("start") === "2026-10-01") });
        }
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/relatorios");
        const panel = page.locator("[data-sm-sales-decisions]");
        await panel.getByText(/Fuso: America\/Fortaleza/).waitFor();
        assert.match(await panel.innerText(), /R\$ 119,80/);
        assert.match(await panel.innerText(), /Ticket médio/);
        assert.match(await panel.innerText(), /R\$ 59,90/);
        assert.match(await panel.innerText(), /Sem base percentual/);
        assert.equal(
          await panel.locator("img").count(),
          0,
          "Historical item names must be text, never markup",
        );
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        fs.mkdirSync(path.join(__dirname, "../test-results/sales-decisions"), { recursive: true });
        await panel
          .getByRole("heading", { name: "Vendas registradas", exact: true })
          .scrollIntoViewIfNeeded();
        await page.screenshot({
          path: path.join(__dirname, `../test-results/sales-decisions/${width}-${theme}.png`),
          fullPage: true,
        });
        await panel
          .getByText("10 itens com maior valor registrado", { exact: true })
          .scrollIntoViewIfNeeded();
        await page.screenshot({
          path: path.join(
            __dirname,
            `../test-results/sales-decisions/${width}-${theme}-ranking.png`,
          ),
          fullPage: true,
        });
        const start = panel.getByLabel("De", { exact: true }),
          end = panel.getByLabel("Até", { exact: true });
        await start.fill("2026-10-01");
        await end.fill("2026-10-31");
        await panel.getByRole("button", { name: "Consultar vendas do período" }).click();
        await panel.getByText("Nenhuma venda válida no período selecionado.").waitFor();
        assert.equal(await panel.getByText("R$ 119,80", { exact: true }).count(), 0);
        assert.match(queries.at(-1), /start=2026-10-01&end=2026-10-31/);
        await start.fill("2026-11-10");
        await end.fill("2026-11-11");
        await panel.getByRole("button", { name: "Consultar vendas do período" }).click();
        await panel.getByText("Fonte temporariamente indisponível.").waitFor();
        assert.equal(await panel.locator("table").count(), 0, "Error cannot show stale aggregates");
        const beforeInvalid = queries.length;
        await start.fill("2026-11-12");
        await end.fill("2026-11-11");
        await panel.getByRole("button", { name: "Consultar vendas do período" }).click();
        await panel.getByText("Informe as duas datas, em ordem cronológica.").waitFor();
        assert.equal(queries.length, beforeInvalid);
        await start.fill("2026-12-01");
        await end.fill("2026-12-03");
        await panel.getByRole("button", { name: "Consultar vendas do período" }).click();
        await page.waitForFunction(
          () =>
            document.querySelector("[data-sm-sales-decisions]")?.getAttribute("aria-busy") ===
            "true",
        );
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        fs.mkdirSync(path.join(__dirname, "../test-results/sales-decisions"), { recursive: true });
        await page.screenshot({
          path: path.join(
            __dirname,
            `../test-results/sales-decisions/${width}-${theme}-loading.png`,
          ),
          fullPage: true,
        });
        await page.evaluate(() => {
          location.hash = "#/config/conta";
        });
        await page.locator("[data-businesses]").waitFor();
        await delayed();
        assert.equal(await page.locator("[data-sm-sales-decisions]").count(), 0);
        assert.deepEqual(errors, []);
      } finally {
        await context.close();
      }
    }
  console.log(
    "Sales decisions: custom periods, persisted-report contract, decimal display, empty/error/loading, escaped item names and stale navigation at mobile/desktop/light/dark passed (controlled transport).",
  );
};
