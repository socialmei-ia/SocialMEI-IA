const assert = require("node:assert/strict");

module.exports = async (browser, origin) => {
  for (const width of [390, 1440]) {
    for (const role of ["owner", "viewer"]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      const errors = [];
      let hidden = true;
      const identity = {
        usuario: { id: 91, nome: "Teste", email: "teste@example.test" },
        negocio: { id: 17, nome: "Fixture", slug: "fixture", configuracao: {} },
        papel: role,
        csrf_token: "a".repeat(64),
      };
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      await page.route("**/*", (route) => {
        const req = route.request();
        const url = new URL(req.url());
        if (url.origin !== origin) return route.abort();
        if (url.pathname === "/frontend/config.js")
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        const path = url.pathname.slice("/api/v1".length);
        if (path === "/auth/session") return route.fulfill({ json: identity });
        if (path === "/auth/preferences") return route.fulfill({ json: { preferences: {} } });
        if (path === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (path === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled", waha_inbox: true } });
        if (path === "/message-enrichment/conversations")
          return route.fulfill({ json: { workspace_id: 17, items: [] } });
        if (path === "/message-enrichment/hidden-conversations") {
          assert.equal(req.headers()["x-socialmei-identity"], "91:17");
          return route.fulfill({ json: { workspace_id: 17, items: hidden ? [{ id: 2, contact_name: "Contato oculto" }] : [] } });
        }
        if (path === "/message-enrichment/conversations/2/restore") {
          assert.equal(role, "owner");
          assert.equal(req.method(), "POST");
          assert.equal(req.headers()["x-socialmei-identity"], "91:17");
          assert.equal(req.headers()["x-socialmei-csrf"], "a".repeat(64));
          hidden = false;
          return route.fulfill({ json: { hidden: false, conversation_id: 2 } });
        }
        assert.equal(req.method(), "GET");
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/caixa");
        await page.getByRole("button", { name: "Conversas ocultas", exact: true }).click();
        const dialog = page.locator("dialog[open]");
        await dialog.getByText("Contato oculto", { exact: true }).waitFor();
        const restore = dialog.getByRole("button", { name: "Restaurar", exact: true });
        if (role === "owner") {
          await restore.click();
          await dialog.getByText(/Conversa restaurada/).waitFor();
          assert.equal(hidden, false);
        } else {
          assert.equal(await restore.count(), 0);
          assert.equal(hidden, true);
        }
        await dialog.getByRole("button", { name: "Fechar", exact: true }).click();
        assert.deepEqual(errors, []);
      } finally {
        await context.close();
      }
    }
  }
};
