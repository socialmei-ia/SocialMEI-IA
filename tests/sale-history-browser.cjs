// Native Vendas with controlled API snapshots; no real account or financial transport.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function (browser, origin) {
  const out = path.join(__dirname, "../test-results/sale-history");
  fs.mkdirSync(out, { recursive: true });
  const cursor = "11111111-1111-4111-8111-111111111111";
  for (const width of [390, 1440])
    for (const theme of ["light", "dark"]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage(),
        errors = [],
        writes = [],
        requests = [];
      let mode = "error",
        delayed = null;
      const identity = {
        usuario: { id: 91, nome: "Fictício", email: "fixture@example.test" },
        negocio: { id: 17, slug: "fixture", nome: "Loja fictícia", configuracao: {} },
        papel: "owner",
        csrf_token: "a".repeat(64),
      };
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/*", async (route) => {
        const request = route.request(),
          url = new URL(request.url()),
          endpoint = url.pathname.replace("/api/v1", "");
        if (url.origin !== origin) throw Error("External transport forbidden");
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        if (request.method() !== "GET") {
          writes.push(endpoint);
          return route.fulfill({ status: 503, json: { detail: "not permitted" } });
        }
        if (endpoint === "/auth/session") return route.fulfill({ json: identity });
        if (endpoint === "/auth/preferences")
          return route.fulfill({ json: { preferences: { theme }, revision: 0 } });
        if (endpoint === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (endpoint === "/auth/workspaces")
          return route.fulfill({ json: { active_workspace_id: 17, items: [] } });
        if (endpoint === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled" } });
        if (endpoint === "/vendas")
          return route.fulfill({
            json: [
              {
                id: 7,
                item: "Produto fictício",
                cliente: "Sem cliente",
                data: "2026-11-04",
                quantidade: 1,
                valor: 59.9,
                status: "Pendente",
              },
            ],
          });
        if (endpoint === "/vendas/7/history") {
          requests.push(url.search);
          if (mode === "error")
            return route.fulfill({
              status: 503,
              json: { detail: "Histórico indisponível. Tente novamente." },
            });
          if (mode === "delay")
            await new Promise((resolve) => {
              delayed = resolve;
            });
          const old = url.searchParams.has("before");
          return route.fulfill({
            json: {
              workspace_id: mode === "foreign" ? 18 : 17,
              sale_id: 7,
              timezone: "America/Fortaleza",
              actor_recorded: false,
              deleted: false,
              items:
                mode === "empty"
                  ? []
                  : [
                      {
                        id: cursor,
                        recorded_at: "2026-11-04T12:00:00Z",
                        revision: old ? 1 : 3,
                        status: old ? "Pendente" : "Pago",
                        quantity: 1,
                        total: "59.90",
                        stock_applied: true,
                        deleted: false,
                      },
                    ],
              next_cursor: !old && mode !== "empty" ? cursor : null,
            },
          });
        }
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/negocio/vendas");
        const button = page.getByRole("button", { name: "Histórico da venda 7", exact: true });
        await button.click();
        let dialog = page.getByRole("dialog", { name: "Histórico da venda 7", exact: true });
        await dialog
          .getByText("Histórico indisponível. Tente novamente.", { exact: true })
          .waitFor();
        mode = "empty";
        await dialog
          .getByRole("button", { name: "Tentar consultar novamente", exact: true })
          .click();
        await dialog.getByText(/Nenhuma operação registrada/).waitFor();
        await dialog.getByRole("button", { name: "Fechar histórico", exact: true }).click();
        mode = "ready";
        await button.click();
        dialog = page.getByRole("dialog", { name: "Histórico da venda 7", exact: true });
        await dialog.getByText("Versão 3 · Pago", { exact: true }).waitFor();
        assert((await dialog.innerText()).includes("09:00:00"));
        assert((await dialog.innerText()).includes("America/Fortaleza"));
        assert((await dialog.innerText()).includes("Autor não registrado neste histórico."));
        assert((await dialog.innerText()).includes("Estoque aplicado nesta versão: Sim"));
        await dialog
          .getByRole("button", { name: "Carregar registros anteriores", exact: true })
          .click();
        await dialog.getByText("Versão 1 · Pendente", { exact: true }).waitFor();
        assert.equal(await dialog.locator("li").count(), 2);
        assert(requests.some((query) => query.includes("before=" + cursor)));
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        await page.screenshot({ path: path.join(out, `${width}-${theme}.png`), fullPage: true });
        await page.keyboard.press("Escape");
        mode = "foreign";
        await button.click();
        dialog = page.getByRole("dialog", { name: "Histórico da venda 7", exact: true });
        await dialog
          .getByText("Histórico não confirmado pelo servidor.", { exact: true })
          .waitFor();
        assert.equal(await dialog.locator("li").count(), 0);
        await dialog.getByRole("button", { name: "Fechar histórico", exact: true }).click();
        mode = "delay";
        await button.click();
        for (let i = 0; i < 30 && !delayed; i++) await page.waitForTimeout(10);
        assert(delayed);
        await page.evaluate(() => {
          SocialMEIAuth.current.negocio.id = 18;
        });
        delayed();
        await page.waitForTimeout(50);
        assert.equal(await page.locator("dialog li").count(), 0);
        assert.deepEqual(errors, []);
        assert.deepEqual(writes, []);
      } finally {
        await context.close();
      }
    }
  return "Sale history: persisted snapshot contract, pagination, business timezone, empty/error/retry, stale/foreign workspace rejection and mobile/desktop light/dark PASS (controlled API).";
};
