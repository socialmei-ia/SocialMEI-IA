/* Native settings with synthetic scoped credentials. No WAHA/n8n network requests. */
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
module.exports = async function (browser, origin) {
  const out = path.join(__dirname, "../test-results/whatsapp-catalog");
  fs.mkdirSync(out, { recursive: true });
  for (const width of [1440, 390])
    for (const theme of ["light", "dark"]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage();
      const errors = [],
        external = [],
        writes = [];
      let provisioned = false;
      const token = "synthetic-whatsapp-credential-" + "x".repeat(40);
      const identity = {
        usuario: { id: 91, nome: "Conta de teste", email: "synthetic@example.test" },
        negocio: { id: 17, nome: "Negócio fictício", slug: "synthetic", configuracao: {} },
        papel: "owner",
        csrf_token: "a".repeat(64),
      };
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      page.on("pageerror", (e) => errors.push(e.message));
      await page.route("**/*", (route) => {
        const req = route.request(),
          url = new URL(req.url());
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
        const p = url.pathname.replace("/api/v1", "");
        if (p === "/auth/session") return route.fulfill({ json: identity });
        if (req.method() !== "GET") {
          writes.push(p);
          assert.equal(req.headers()["x-socialmei-csrf"], "a".repeat(64));
          assert.equal(req.headers()["x-socialmei-identity"], "91:17");
          if (p === "/whatsapp/catalog/access" && req.method() === "POST") {
            assert.deepEqual(req.postDataJSON(), { channel_id: 44 });
            provisioned = true;
            return route.fulfill({ json: { token_once: token, instance: "synthetic" } });
          }
          if (p === "/whatsapp/catalog/access/44" && req.method() === "DELETE") {
            provisioned = false;
            return route.fulfill({ status: 204 });
          }
          throw Error("Unexpected mutation " + p);
        }
        if (p === "/auth/preferences")
          return route.fulfill({ json: { preferences: { theme }, revision: 0 } });
        if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (p === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled" } });
        if (p === "/integrations/readiness")
          return route.fulfill({ json: { instagram: { oauth_available: false } } });
        if (p === "/instagram/meta/status")
          return route.fulfill({ json: { status: "disconnected", credential_available: false } });
        if (p === "/auth/workspaces")
          return route.fulfill({ json: { active_workspace_id: 17, items: [] } });
        if (p === "/whatsapp/catalog/access")
          return route.fulfill({
            json: {
              enabled: false,
              channels: [
                {
                  channel_id: 44,
                  instance: "synthetic",
                  name: "Atendimento da loja",
                  active: true,
                  enabled: provisioned,
                  credential_configured: provisioned,
                  provider_state: null,
                },
              ],
            },
          });
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/config/integracoes");
        const panel = page.locator("[data-wa-catalog]");
        await panel.getByText(/Consulta técnica desativada/).waitFor();
        assert.match(
          await page
            .locator(".sw")
            .filter({ has: page.locator("b", { hasText: "WhatsApp" }) })
            .innerText(),
          /Canal cadastrado/,
        );
        await page.getByRole("button", { name: "Ver catálogo", exact: true }).click();
        await panel.scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(out, `${width}-${theme}.png`), fullPage: true });
        await panel.getByRole("button", { name: "Gerar credencial", exact: true }).click();
        const dialog = page.getByRole("dialog", { name: "Credencial de consulta WhatsApp" });
        await dialog.waitFor();
        assert.equal(await dialog.locator("input").inputValue(), token);
        assert.equal(await dialog.locator("input").getAttribute("type"), "password");
        assert.equal(writes.length, 1);
        await page.keyboard.press("Escape");
        await dialog.waitFor({ state: "detached" });
        assert(
          !(await page
            .locator("body")
            .innerHTML()
            .then((v) => v.includes(token))),
        );
        const saved = await page.evaluate(() =>
          JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]),
        );
        assert(!saved.includes(token));
        await panel.getByRole("button", { name: "Revogar acesso", exact: true }).waitFor();
        page.once("dialog", (d) => d.accept());
        await panel.getByRole("button", { name: "Revogar acesso", exact: true }).click();
        await panel.getByRole("button", { name: "Gerar credencial", exact: true }).waitFor();
        assert.deepEqual(writes, ["/whatsapp/catalog/access", "/whatsapp/catalog/access/44"]);
        assert.deepEqual(errors, []);
        assert.deepEqual(external, []);
      } finally {
        await context.close();
      }
    }
  return "WhatsApp catalog: native management, one-time credential cleared, revoke and 2 widths × 2 themes (synthetic API)";
};
