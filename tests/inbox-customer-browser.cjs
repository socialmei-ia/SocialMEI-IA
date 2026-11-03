// Real V22 DOM with controlled transport. Associations use IDs, never ambiguous names.
const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  for (const width of [390, 1440])
    for (const role of ["owner", "viewer"]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } }),
        page = await context.newPage(),
        errors = [],
        writes = [];
      const identity = {
        usuario: { id: 91, nome: "Ficticio", email: "teste@example.test" },
        negocio: { id: 17, nome: "Fixture", slug: "fixture", configuracao: {} },
        papel: role,
        csrf_token: "a".repeat(64),
      };
      const clients = [
        { id: 11, nome: "Nome repetido", email: "um@example.test" },
        { id: 12, nome: "Nome repetido", email: "dois@example.test" },
      ];
      let linked = { conversation_id: 1, revision: 1, cliente_id: null, customer: null },
        conflict = false;
      page.on("pageerror", (e) => errors.push(e.message));
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      await page.route("**/*", (route) => {
        const request = route.request(),
          url = new URL(request.url()),
          p = url.pathname.replace("/api/v1", "");
        if (url.origin !== origin) return route.abort();
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        if (p === "/auth/session") return route.fulfill({ json: identity });
        if (p === "/auth/preferences")
          return route.fulfill({ json: { preferences: {}, revision: 0 } });
        if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (p === "/clientes") return route.fulfill({ json: clients });
        if (p === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled", waha_inbox: true } });
        if (p === "/message-enrichment/conversations")
          return route.fulfill({
            json: {
              workspace_id: 17,
              items: [
                {
                  id: 1,
                  revision: linked.revision,
                  channel: "whatsapp",
                  origin: "waha",
                  contact_name: "+5581990001234",
                  account_ref: "waha:111@c.us",
                  messages: [
                    { id: 1, text: "Mensagem ficticia", occurred_at: "2026-11-01T12:00:00Z" },
                  ],
                },
              ],
            },
          });
        if (p === "/message-enrichment/conversations/1/customer") {
          if (request.method() === "GET") return route.fulfill({ json: linked });
          assert.equal(role, "owner");
          assert.equal(request.headers()["x-socialmei-identity"], "91:17");
          assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
          const payload = request.postDataJSON();
          writes.push(payload);
          assert.equal(payload.expected_revision, linked.revision);
          if (conflict) {
            conflict = false;
            linked = { ...linked, revision: linked.revision + 1 };
            return route.fulfill({ status: 409, json: { detail: "A conversa mudou." } });
          }
          linked = {
            ...linked,
            revision: linked.revision + (payload.cliente_id === linked.cliente_id ? 0 : 1),
            cliente_id: payload.cliente_id,
            customer: clients.find((c) => c.id === payload.cliente_id) || null,
          };
          return route.fulfill({ json: linked });
        }
        assert.equal(request.method(), "GET", p);
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/caixa/me-1");
        const panel = page.locator("[data-inbox-customer]");
        await panel
          .getByText("Esta conversa ainda não está associada a um cliente do CRM.", { exact: true })
          .waitFor();
        const associate = panel.getByRole("button", {
          name: "Associar cliente do CRM",
          exact: true,
        });
        if (role === "viewer") {
          assert(await associate.isDisabled());
          assert.deepEqual(errors, []);
          continue;
        }
        await associate.click();
        await page.locator("#f_inbox_customer").selectOption("12");
        await page.getByRole("button", { name: "Salvar vínculo", exact: true }).click();
        await page.locator("dialog[open]").waitFor({ state: "hidden" });
        assert.equal(writes[0].cliente_id, 12);
        await panel.getByText("Cliente: Nome repetido", { exact: true }).waitFor();
        assert.equal(
          await page.locator(".ct .hd b").first().textContent(),
          "+5581990001234",
          "Linking must not replace sender label",
        );
        await page.reload();
        await page
          .locator("[data-inbox-customer]")
          .getByText("Cliente: Nome repetido", { exact: true })
          .waitFor();
        await page.getByRole("button", { name: "Alterar cliente do CRM", exact: true }).click();
        conflict = true;
        await page.locator("#f_inbox_customer").selectOption("11");
        await page.getByRole("button", { name: "Salvar vínculo", exact: true }).click();
        await page
          .getByText(
            "A conversa ou o cliente mudou. Feche e atualize o vínculo antes de salvar novamente.",
            { exact: true },
          )
          .waitFor();
        assert.equal(linked.cliente_id, 12);
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: "Atualizar vínculo CRM", exact: true }).click();
        await page.getByRole("button", { name: "Alterar cliente do CRM", exact: true }).click();
        await page.locator("#f_inbox_customer").selectOption("");
        await page.getByRole("button", { name: "Salvar vínculo", exact: true }).click();
        await page.locator("dialog[open]").waitFor({ state: "hidden" });
        assert.equal(linked.cliente_id, null);
        await page.getByRole("button", { name: "Associar cliente do CRM", exact: true }).click();
        await page.locator("#f_inbox_customer").selectOption("11");
        const count = writes.length;
        await page.evaluate((width) => {
          const host = window.SocialMEIV22,
            old = host.identity,
            next = { ...old, negocio: { ...old.negocio, id: width === 390 ? 18 : old.negocio.id } };
          Object.defineProperty(host, "identity", { configurable: true, get: () => next });
        }, width);
        await page.getByRole("button", { name: "Salvar vínculo", exact: true }).click();
        await page.locator("dialog[open]").waitFor({ state: "hidden" });
        assert.equal(
          writes.length,
          count,
          "Forms from another workspace or session must not write",
        );
        assert.deepEqual(errors, []);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
      } finally {
        await context.close();
      }
    }
  console.log(
    "Inbox CRM link: ID selection, reload, conflict, unlink, sender preservation, viewer and stale session/workspace guards passed at mobile/desktop (controlled transport).",
  );
};
