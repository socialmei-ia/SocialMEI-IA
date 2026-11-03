/* Real V22 UI, controlled same-origin transport; no provider or production calls. */
const assert = require("node:assert/strict");
module.exports = async function (browser, origin) {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({
      viewport: { width, height: 1000 },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const errors = [],
      external = [],
      writes = [];
    let products = [];
    const identity = {
      usuario: { id: 91, nome: "Conta fictícia", email: "style@example.test" },
      negocio: { id: 17, slug: "style-test", nome: "She Style fictícia", configuracao: {} },
      papel: "owner",
      csrf_token: "a".repeat(64),
    };
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
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
      const path = url.pathname.replace("/api/v1", "");
      if (path === "/auth/session") return route.fulfill({ json: identity });
      assert.equal(req.headers()["x-socialmei-identity"], "91:17");
      if (path === "/auth/preferences")
        return route.fulfill({ json: { preferences: {}, revision: 0 } });
      if (path === "/workspace-profile")
        return route.fulfill({ json: { profile: null, revision: 0 } });
      if (path === "/message-enrichment/capabilities")
        return route.fulfill({ json: { mode: "disabled" } });
      if (path === "/produtos" && req.method() === "GET") return route.fulfill({ json: products });
      if (path === "/produtos" && req.method() === "POST") {
        assert.equal(req.headers()["x-socialmei-csrf"], "a".repeat(64));
        const packet = req.postDataJSON();
        writes.push(packet);
        products = [{ ...packet, id: 1, versao: 1 }];
        return route.fulfill({ status: 201, json: products[0] });
      }
      if (path === "/produtos/1" && req.method() === "PATCH") {
        assert.equal(req.headers()["x-socialmei-csrf"], "a".repeat(64));
        const packet = req.postDataJSON();
        writes.push(packet);
        assert.equal(packet.expected_version, products[0].versao);
        const { expected_version, ...fields } = packet;
        products = [{ ...products[0], ...fields, versao: expected_version + 1 }];
        return route.fulfill({ json: products[0] });
      }
      assert.equal(req.method(), "GET", "No unrelated write is allowed");
      return route.fulfill({ json: [] });
    });
    try {
      await page.goto(origin + "/frontend/socialmei-app.html#/negocio/produtos");
      await page.waitForFunction(
        () => window.SocialMEIV22?.identity && !document.getElementById("app").hidden,
      );
      await page.getByRole("button", { name: "Novo produto", exact: true }).click();
      await page.locator("#f_n").fill("Blusa fictícia");
      assert.equal(await page.locator("#f_c").isDisabled(), false);
      assert.equal(await page.locator("#f_d").isDisabled(), false);
      await page.locator("#f_c").fill("Roupas");
      await page.locator("#f_d").fill("Tecido fictício");
      await page.locator("#f_p").fill("80,00");
      await page.locator("#f_e").fill("5");
      await page.locator("dialog button[type=submit]").click();
      await page.locator("dialog").waitFor({ state: "hidden" });
      assert.equal(writes.length, 1);
      assert.equal(writes[0].categoria, "Roupas");
      assert.equal(writes[0].descricao, "Tecido fictício");
      await page.reload();
      await page.locator("tr[data-a='prod:0']").waitFor();
      await page.locator("tr[data-a='prod:0']").click();
      await page.getByRole("button", { name: "Editar produto", exact: true }).click();
      assert.equal(await page.locator("#f_c").inputValue(), "Roupas");
      assert.equal(await page.locator("#f_d").inputValue(), "Tecido fictício");
      await page.locator("#f_c").fill("Moda");
      await page.locator("#f_d").fill("");
      await page.locator("#f_a").uncheck();
      await page.locator("dialog button[type=submit]").click();
      await page.locator("dialog").waitFor({ state: "hidden" });
      await page.reload();
      await page.locator("tr[data-a='prod:0']").waitFor();
      await page.locator("tr[data-a='prod:0']").click();
      await page.getByRole("button", { name: "Editar produto", exact: true }).click();
      assert.equal(await page.locator("#f_c").inputValue(), "Moda");
      assert.equal(await page.locator("#f_d").inputValue(), "");
      assert.equal(await page.locator("#f_a").isChecked(), false);
      assert.equal(await page.locator("#f_e").inputValue(), "5");
      await page.keyboard.press("Escape");
      assert.equal(writes.length, 2);
      assert.deepEqual(errors, []);
      assert.deepEqual(external, []);
    } finally {
      await context.close();
    }
  }
  return "Catalog details create/edit/reload/deactivation verified at 1440 and 390px with controlled transport";
};
