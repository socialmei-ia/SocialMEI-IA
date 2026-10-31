/* Synthetic same-origin inbox responses; real V22 shell and six-second polling. */
const assert = require("node:assert/strict");
module.exports = async function (browser, origin) {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({
      viewport: { width, height: 1000 },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const errors = [],
      external = [];
    let enabled = true;
    let reads = 0,
      documents = 0;
    const identity = {
      usuario: { id: 91, nome: "Conta de teste", email: "synthetic@example.test" },
      negocio: { id: 17, nome: "Negócio fictício", slug: "synthetic", configuracao: {} },
      papel: "owner",
      csrf_token: "a".repeat(64),
    };
    const message = (id, text) => ({ id, text, occurred_at: "2026-10-26T10:00:00Z" });
    let items = [
      {
        id: 1,
        revision: 1,
        channel: "instagram",
        origin: "instagram",
        contact_name: "Contato Direct A",
        messages: [message(11, "Mensagem inicial")],
      },
    ];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
    await page.clock.install();
    await page.route("**/*", (route) => {
      const request = route.request(),
        url = new URL(request.url());
      if (url.origin !== origin) {
        external.push(url.hostname);
        return route.abort();
      }
      if (request.isNavigationRequest() && request.resourceType() === "document") documents++;
      if (url.pathname.endsWith("/config.js"))
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
        });
      if (!url.pathname.startsWith("/api/v1/")) return route.continue();
      const p = url.pathname.replace("/api/v1", "");
      if (p === "/auth/session") return route.fulfill({ json: identity });
      assert.equal(request.method(), "GET", "Polling must never send messages or write data");
      if (p === "/auth/preferences")
        return route.fulfill({ json: { preferences: {}, revision: 0 } });
      if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
      if (p === "/message-enrichment/capabilities")
        return route.fulfill({
          json: {
            mode: "disabled",
            workspace_id: 17,
            instagram_inbox: enabled,
            waha_inbox: enabled,
          },
        });
      if (p === "/message-enrichment/conversations") {
        reads++;
        return route.fulfill({ json: { workspace_id: 17, items } });
      }
      return route.fulfill({ json: [] });
    });
    try {
      await page.goto(origin + "/frontend/socialmei-app.html#/caixa/me-1");
      await page.waitForFunction(
        () => window.SocialMEIV22?.identity && !document.getElementById("app").hidden,
      );
      await page.locator(".ct .ms .bb", { hasText: "Mensagem inicial" }).waitFor();
      assert.match(await page.locator(".ct .hd").innerText(), /Instagram · recebido no servidor/);
      assert.match(await page.locator(".ct .hd .wn").innerText(), /Envio indisponível/);
      assert(!/exemplo local|Canal não conectado/.test(await page.locator(".ct .hd").innerText()));
      assert.equal(reads, 1);
      assert.equal(await page.evaluate(() => SocialMEIV22.identity.papel), "owner");
      const documentCount = documents;
      items = [
        {
          ...items[0],
          revision: 2,
          messages: [...items[0].messages, message(12, "Nova mensagem via polling")],
        },
        {
          id: 2,
          revision: 1,
          channel: "instagram",
          origin: "instagram",
          contact_name: "Contato Direct B",
          messages: [message(21, "Outra conversa recebida")],
        },
      ];
      await page.clock.fastForward(6001);
      await page.locator(".ct .ms .bb", { hasText: "Nova mensagem via polling" }).waitFor();
      assert.equal(reads, 2);
      assert.equal(documents, documentCount, "A new webhook message must not reload the document");
      assert.equal(
        await page.evaluate(() => H),
        "/caixa/me-1",
        "The current thread stays selected",
      );
      assert.equal(await page.locator(".ct .ms .bb").count(), 2);
      assert.equal(await page.locator(".ct .hd b").first().textContent(), "Contato Direct A");
      assert.equal(
        await page.evaluate(() => C.length),
        2,
        "New conversations also arrive through polling",
      );
      items.push({
        id: 3,
        revision: 1,
        channel: "whatsapp",
        origin: "waha",
        contact_name: "Contato do WhatsApp",
        messages: [message(31, "Mensagem WhatsApp sintetica")],
      });
      await page.clock.fastForward(6001);
      await page.evaluate(() => go("/caixa/me-3"));
      await page.locator(".ct .hd b").first().filter({ hasText: "Contato do WhatsApp" }).waitFor();
      items = items.map((row) =>
        row.id === 3 ? { ...row, revision: 2, contact_name: "+5511990001234" } : row,
      );
      await page.clock.fastForward(6001);
      await page.waitForFunction(
        () => document.querySelector(".ct .hd b")?.textContent === "+5511990001234",
      );
      assert.equal(
        await page.locator(".ct .ms .bb").count(),
        1,
        "Resolving identity never creates another message",
      );
      assert.equal(documents, documentCount, "A verified contact label updates without reloading");
      await page.evaluate(() => go("/caixa"));
      await page.getByRole("link", { name: "Contato Direct B", exact: true }).waitFor();
      assert.match(await page.locator("#v").innerText(), /Recebimento habilitado no servidor/);
      assert(!/Demonstração local|Canal não conectado/.test(await page.locator("#v").innerText()));
      enabled = false;
      await page.clock.fastForward(6001);
      await page.getByText("Recebimento não habilitado", { exact: true }).waitFor();
      assert.equal(await page.locator('.rw[href^="#/caixa/me-"]').count(), 0);
      assert(
        !/Demonstração local|Recebimento habilitado no servidor/.test(
          await page.locator("#v").innerText(),
        ),
      );
      assert.deepEqual(errors, []);
      assert.deepEqual(external, []);
    } finally {
      await context.close();
    }
  }
  return "V22 inbox: Direct updates without reload, selected thread preserved at desktop/mobile widths";
};
