// Controlled receipt evidence only; no WAHA session, customer data or provider I/O.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function (browser, origin) {
  const out = path.join(__dirname, "../test-results/whatsapp-receiving");
  fs.mkdirSync(out, { recursive: true });
  for (const width of [390, 1440])
    for (const theme of ["light", "dark"]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage();
      const errors = [],
        writes = [],
        external = [];
      let mode = "empty",
        reads = 0;
      const identity = {
        usuario: { id: 91, nome: "Teste", email: "fixture@example.test" },
        negocio: { id: 17, slug: "fixture", nome: "Negócio fictício", configuracao: {} },
        papel: "owner",
        csrf_token: "a".repeat(64),
      };
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/*", (route) => {
        const request = route.request(),
          url = new URL(request.url());
        if (url.origin !== origin) {
          external.push(url.hostname);
          return route.abort();
        }
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        const endpoint = url.pathname.replace("/api/v1", "");
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
        if (endpoint === "/instagram/meta/status")
          return route.fulfill({ json: { status: "disconnected" } });
        if (endpoint === "/integrations/readiness")
          return route.fulfill({
            json: {
              source: "server",
              whatsapp: { configured: true, receiving_configured: true, sending_available: false },
              instagram: { oauth_available: false },
            },
          });
        if (endpoint === "/whatsapp/receiving-status") {
          reads++;
          if (mode === "error")
            return route.fulfill({ status: 503, json: { detail: "private-canary-never-display" } });
          return route.fulfill({
            json: {
              source: "postgresql",
              workspace_id: mode === "foreign" ? 18 : 17,
              message_count: mode === "empty" ? 0 : 8,
              conversation_count: mode === "empty" ? 0 : 2,
              last_persisted_at: mode === "empty" ? null : "2026-11-04T10:00:00Z",
              historical_receiving_confirmed: mode !== "empty",
              session_live_verified: false,
              sending_available: false,
              observed_at: "2026-11-04T10:01:00Z",
            },
          });
        }
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/config/integracoes");
        const panel = page.locator("[data-wa-receiving]");
        await panel
          .getByText("Nenhuma mensagem WhatsApp recebida e persistida neste negócio.", {
            exact: true,
          })
          .waitFor();
        assert((await panel.innerText()).includes("Não comprova sessão WAHA ativa agora"));
        mode = "history";
        await panel.getByRole("button", { name: "Atualizar recebimento", exact: true }).click();
        await panel.getByText(/8 mensagem\(ns\).*2 conversa\(s\)/).waitFor();
        assert.equal(
          await panel.getByRole("link", { name: "Abrir Caixa Unificada" }).getAttribute("href"),
          "#/caixa",
        );
        mode = "error";
        await panel.getByRole("button", { name: "Atualizar recebimento", exact: true }).click();
        await panel
          .getByText("Recebimento não verificado. Não foi possível consultar o histórico.", {
            exact: true,
          })
          .waitFor();
        assert(!(await page.locator("body").innerText()).includes("private-canary-never-display"));
        mode = "foreign";
        await panel.getByRole("button", { name: "Atualizar recebimento", exact: true }).click();
        await panel
          .getByRole("button", { name: "Atualizar recebimento", exact: true })
          .waitFor({ state: "visible" });
        await page.waitForFunction(
          () =>
            document.querySelector("[data-wa-receiving]")?.getAttribute("aria-busy") === "false",
        );
        assert(!(await panel.innerText()).includes("8 mensagem"));
        mode = "history";
        await page.reload();
        await panel.getByText(/8 mensagem\(ns\).*2 conversa\(s\)/).waitFor();
        await panel.scrollIntoViewIfNeeded();
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        await page.screenshot({ path: path.join(out, `${width}-${theme}.png`), fullPage: true });
        assert(reads >= 5);
        assert.deepEqual(writes, []);
        assert.deepEqual(external, []);
        assert.deepEqual(errors, []);
      } catch (error) {
        await page.screenshot({
          path: path.join(out, `failure-${width}-${theme}.png`),
          fullPage: true,
        });
        throw error;
      } finally {
        await context.close();
      }
    }
  return "WhatsApp receipt evidence: empty, historical, unavailable, foreign-scope rejection, refresh/reload, no writes/transports, mobile/desktop light/dark passed (synthetic API).";
};
