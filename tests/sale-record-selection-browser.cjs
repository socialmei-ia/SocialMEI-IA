const assert = require("node:assert/strict");
module.exports = async function (browser, origin) {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    const writes = [],
      errors = [];
    const identity = {
      usuario: { id: 91, nome: "Teste", email: "style@example.test" },
      negocio: { id: 17, slug: "style-test", nome: "She Style", configuracao: {} },
      papel: "owner",
      csrf_token: "a".repeat(64),
    };
    page.on("pageerror", (e) => errors.push(e.message));
    await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
    await page.route("**/*", (route) => {
      const req = route.request(),
        url = new URL(req.url());
      assert.equal(url.origin, origin, "No external requests");
      if (url.pathname.endsWith("/config.js"))
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
        });
      if (!url.pathname.startsWith("/api/v1/")) return route.continue();
      const path = url.pathname.replace("/api/v1", "");
      if (path === "/auth/session") return route.fulfill({ json: identity });
      assert.equal(req.headers()["x-socialmei-identity"], "91:17");
      if (path === "/auth/preferences")
        return route.fulfill({ json: { preferences: {}, revision: 0 } });
      if (path === "/workspace-profile")
        return route.fulfill({ json: { profile: null, revision: 0 } });
      if (path === "/message-enrichment/capabilities")
        return route.fulfill({ json: { mode: "disabled" } });
      if (path === "/clientes")
        return route.fulfill({
          json: [
            { id: 21, nome: "Cliente repetido" },
            { id: 22, nome: "Cliente repetido" },
          ],
        });
      if (path === "/produtos")
        return route.fulfill({
          json: [
            { id: 7, nome: "Blusa", tipo: "Produto", preco: 80, estoque: 5, versao: 1 },
            { id: 8, nome: "Blusa", tipo: "Produto", preco: 90, estoque: 5, versao: 1 },
          ],
        });
      if (path === "/vendas" && req.method() === "POST") {
        assert.equal(req.headers()["x-socialmei-csrf"], "a".repeat(64));
        const payload = req.postDataJSON();
        writes.push(payload);
        return route.fulfill({
          status: 201,
          json: { ...payload, id: 1, cliente: "Sem cliente", item: "Blusa", valor: 160, versao: 1 },
        });
      }
      assert.equal(req.method(), "GET", "No unrelated writes");
      return route.fulfill({ json: [] });
    });
    try {
      await page.goto(origin + "/frontend/socialmei-app.html#/negocio/vendas");
      await page.getByRole("button", { name: "Nova venda", exact: true }).click();
      assert.equal(await page.locator("#f_c").inputValue(), "");
      assert.equal(await page.locator('#f_p option[value="8"]').count(), 1);
      assert.match(await page.locator('#f_p option[value="8"]').innerText(), /#8/);
      assert.match(await page.locator('#f_c option[value="22"]').innerText(), /#22/);
      await page.locator("#f_p").evaluate((select) => {
        select.add(new Option("Cadastro indisponível", "999"));
        select.value = "999";
      });
      await page.locator("dialog button[type=submit]").click();
      await page
        .getByText("Selecione um cadastro disponível neste negócio. Atualize se a lista mudou.", {
          exact: true,
        })
        .waitFor();
      assert.equal(writes.length, 0, "Unknown record cannot be submitted");
      await page.locator("#f_c").selectOption("22");
      await page.locator("#f_p").selectOption("8");
      await page.locator("#f_q").fill("2");
      await page.locator("dialog button[type=submit]").click();
      await page.locator("dialog[open]").waitFor({ state: "hidden" });
      assert.equal(writes.length, 1);
      assert.equal(writes[0].cliente_id, 22);
      assert.equal(writes[0].produto_id, 8);
      assert.equal(writes[0].preco, 90);
      assert.equal(writes[0].quantidade, 2);
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  }
  return "Sale with duplicate names: selected customer/product IDs, authenticated write at desktop/mobile passed (controlled transport)";
};
