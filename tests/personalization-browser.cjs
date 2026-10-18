const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function personalization(browser, origin) {
  const output = path.join(root, "test-results/personalization");
  fs.mkdirSync(output, { recursive: true });
  const errors = [],
    external = [];
  const context = await browser.newContext({
    reducedMotion: "reduce",
    viewport: { width: 1440, height: 1000 },
  });
  const profiles = {
    barber: {
      segment: "barber",
      offers: ["services"],
      services: ["Corte masculino", "Barba", "Sobrancelha"],
      capabilities: { appointments: true },
      modules: ["services", "clients", "sales", "appointments", "opportunities"],
    },
    perfume: {
      segment: "perfume",
      offers: ["products"],
      productCategories: ["Perfumes", "Cosméticos"],
      capabilities: { inventory: true, deliveries: true },
      modules: ["products", "inventory", "sales", "finance", "deliveries"],
    },
    tailoring: {
      segment: "tailoring",
      offers: ["services"],
      services: ["Ajustes", "Confecção sob encomenda"],
      capabilities: { orders: true, deliveries: true },
      modules: ["services", "clients", "orders", "deliveries", "finance"],
    },
    mixed: {
      segment: "barber",
      offers: ["products", "services"],
      services: ["Barba"],
      productCategories: ["Perfumes"],
      capabilities: { inventory: true },
      modules: ["products", "services", "inventory", "sales"],
    },
  };
  const capture = async (page, name) => {
    for (const width of [320, 390, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
          `${name}-${width}-${theme} overflow`,
        );
        if (width !== 320)
          await page.screenshot({
            path: path.join(output, `${name}-${width}-${theme}.png`),
            fullPage: !name.endsWith("form"),
          });
      }
  };
  try {
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    await page.waitForFunction(() => document.body.classList.contains("experience-app"));
    assert(await page.locator("#homeProfileShortcuts [data-profile-configure]").isVisible());
    const initial = await page.evaluate(() => JSON.stringify(appData));
    const applyProfile = async (profile) =>
      page.evaluate((profile) => {
        const assertSaved = SocialMEIBusinessProfile.browserRepository().save({
          ...profile,
          businessName: "MEI sintético",
          completed: true,
        });
        if (!assertSaved) throw Error("Fixture profile could not be saved");
        document.dispatchEvent(new CustomEvent("socialmei-business-profile-change"));
        setView("Início");
      }, profile);
    for (const [id, profile] of Object.entries(profiles)) {
      await applyProfile(profile);
      assert.match(await page.locator("#homeProfileContext").textContent(), /serviços|produtos/);
      assert(await page.locator("#homeDefaultShortcuts").isHidden());
      if (profile.offers.includes("services"))
        assert(await page.locator('[data-profile-route="services"]').isVisible());
      if (profile.offers.includes("products"))
        assert(await page.locator('[data-profile-route="products"]').isVisible());
      assert.equal(
        await page
          .locator(
            '[data-profile-route="appointments"],[data-profile-route="deliveries"],[data-profile-route="orders"]',
          )
          .count(),
        0,
      );
      if (id === "barber")
        assert.match(
          await page.locator("#homeProfileLimits").textContent(),
          /Agenda: ainda sem módulo operacional/,
        );
      if (id === "tailoring")
        assert.match(
          await page.locator("#homeProfileLimits").textContent(),
          /Encomendas, Entregas/,
        );
      await capture(page, "home-" + id);
      await page
        .locator(
          `[data-profile-route="${profile.offers.includes("services") ? "services" : "products"}"]`,
        )
        .click();
      assert.equal(await page.evaluate(() => currentView), "Produtos e Serviços");
      if (id === "mixed")
        await page.evaluate(() => {
          document.getElementById("productsTypeFilter").value = "all";
          renderProducts();
        });
      assert.match(
        await page.locator("#catalogProfileSuggestions").textContent(),
        new RegExp(profile.services?.[0] || profile.productCategories[0]),
      );
      await capture(page, "catalog-" + id);
    }
    assert.equal(
      await page.evaluate(() => JSON.stringify(appData)),
      initial,
      "presentation must not create records",
    );
    await applyProfile(profiles.barber);
    await page.locator('[data-profile-route="services"]').click();
    const use = page.locator('[data-profile-suggest="Serviço:corte masculino"]');
    await use.focus();
    await page.keyboard.press("Enter");
    await page.locator("#createModal.open").waitFor();
    assert.equal(await page.locator("#f_nome").inputValue(), "Corte masculino");
    assert.equal(await page.locator("#f_tipo").inputValue(), "Serviço");
    assert.equal(await page.locator("#f_preco").inputValue(), "");
    assert(await page.locator("#f_estoque").isDisabled());
    assert(await page.locator("#f_estoque").isHidden());
    await capture(page, "service-form");
    await page.keyboard.press("Escape");
    await page.locator("#createModal.open").waitFor({ state: "hidden" });
    assert.equal(await page.evaluate(() => JSON.stringify(appData)), initial);
    assert(await use.evaluate((el) => el === document.activeElement));
    await use.click();
    await page.locator("#f_preco").fill("35");
    await page.locator("#createSubmit").click();
    await page.locator("#createModal.open").waitFor({ state: "hidden" });
    const saved = await page.evaluate(() =>
      appData.produtos.find((item) => item.nome === "Corte masculino"),
    );
    assert.equal(saved.tipo, "Serviço");
    assert.equal(saved.preco, 35);
    assert.equal(saved.estoque, null);
    assert.equal(await page.locator('[data-profile-suggest="Serviço:corte masculino"]').count(), 0);
    await page.reload();
    await page.waitForFunction(() => document.body.classList.contains("experience-app"));
    assert.equal(
      await page.evaluate(
        () => appData.produtos.find((item) => item.nome === "Corte masculino").preco,
      ),
      35,
    );
    // Ignoring is a preference, supports recovery and never edits catalog records.
    await page.locator('[data-profile-ignore="Serviço:barba"]').click();
    assert.equal(await page.locator('[data-profile-suggest="Serviço:barba"]').count(), 0);
    await page.reload();
    await page.waitForFunction(() => document.body.classList.contains("experience-app"));
    assert.equal(await page.locator('[data-profile-suggest="Serviço:barba"]').count(), 0);
    await page.locator("[data-profile-restore]").click();
    assert(await page.locator('[data-profile-suggest="Serviço:barba"]').isVisible());
    await applyProfile(profiles.perfume);
    await page.locator('[data-profile-route="products"]').click();
    await page.locator('[data-profile-suggest="Produto:perfumes"]').click();
    assert.equal(
      await page.locator("#f_nome").inputValue(),
      "",
      "a category must not become an invented product name",
    );
    assert.equal(await page.locator("#f_tipo").inputValue(), "Produto");
    assert.match(
      await page.locator("#profileSuggestionNote").textContent(),
      /Categoria sugerida: Perfumes/,
    );
    assert(await page.locator("#f_estoque").isVisible());
    await capture(page, "product-form");
    await page.locator("#f_nome").fill("Perfume teste escolhido");
    await page.locator("#f_preco").fill("89.90");
    await page.locator("#f_estoque").fill("4");
    await page.locator("#f_minimo").fill("1");
    await page.locator("#createSubmit").click();
    await page.locator("#createModal.open").waitFor({ state: "hidden" });
    const product = await page.evaluate(() =>
      appData.produtos.find((item) => item.nome === "Perfume teste escolhido"),
    );
    assert.equal(product.tipo, "Produto");
    assert.equal(product.estoque, 4);
    assert.equal(product.preco, 89.9);
    await page.locator("[data-profile-custom]").click();
    assert.equal(await page.locator("#profileSuggestionNote").count(), 0);
    assert.equal(await page.locator("#f_nome").inputValue(), "");
    await page.keyboard.press("Escape");
    // Existing profile editor updates Home and catalog without another account/signup.
    await page.evaluate(() => setView("Início"));
    await page.locator("#homeProfileShortcuts [data-profile-configure]").click();
    await page.locator("[data-business-profile-edit]").click();
    await page.locator("#businessSegmentAlternative").evaluate((el) => (el.open = true));
    await page.locator("#obSegment").selectOption("tailoring");
    assert(
      await page.locator('input[name="businessOffer"][value="products"]').isChecked(),
      "specialty changes preserve the existing product offering",
    );
    // A service-only business is now an explicit choice, not a destructive segment default.
    await page.locator('input[name="businessOffer"][value="services"]').check();
    await page.locator('input[name="businessOffer"][value="products"]').uncheck();
    for (const step of [3, 4, 5, 6]) {
      await page.locator("[data-onboard-next]").click();
      await page.locator(`[data-onboard-panel="${step}"].is-active`).waitFor();
    }
    await page.locator("[data-onboard-next]").click();
    await page.waitForFunction(() => document.body.classList.contains("experience-app"));
    await page.evaluate(() => setView("Início"));
    assert.match(await page.locator("#homeProfileContext").textContent(), /Costura e confecção/);
    assert.equal(await page.locator('[data-profile-route="products"]').count(), 0);
    await page.evaluate(() => setView("Produtos e Serviços"));
    await page.locator("#productsTypeFilter").selectOption("all", { force: true });
    assert.match(await page.locator("#catalogProfileSuggestions").textContent(), /Ajustes/);
    assert(
      !(await page
        .locator("#catalogProfileSuggestions")
        .textContent()
        .then((text) => text.includes("Categoria de produtos"))),
    );
    // In-place foreign identity invalidates controls rendered under the previous demo scope.
    const stale = page.locator('[data-profile-suggest="Serviço:ajustes"]');
    await page.evaluate(() =>
      sessionStorage.setItem("socialmei-business-demo-identity", "different@example.com"),
    );
    await stale.click();
    assert.equal(await page.locator("#createModal.open").count(), 0);
    assert.equal(await page.locator("[data-profile-suggest]").count(), 0);
    await page.evaluate(() => setView("Início"));
    assert(await page.locator("#homeDefaultShortcuts").isVisible());
    await capture(page, "no-profile");
  } finally {
    await context.close();
  }
  const remote = await browser.newContext({ reducedMotion: "reduce" });
  try {
    const page = await remote.newPage();
    let rejectWrite = true;
    const writes = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      const request = route.request(),
        url = new URL(request.url());
      if (url.origin !== origin) {
        external.push(url.href);
        return route.abort();
      }
      if (url.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"},clientes:{mode:"local"},produtos:{mode:"remote",apiBaseUrl:"/api/v1",workspaceKey:"test"}};',
        });
      if (url.pathname === "/api/v1/auth/session")
        return route.fulfill({
          json: {
            usuario: { id: 1, nome: "Pessoa sintética", email: "test@example.com" },
            negocio: { id: 1, slug: "test", nome: "Negócio sintético", configuracao: {} },
            csrf_token: "a".repeat(64),
            papel: "owner",
          },
        });
      if (url.pathname === "/api/v1/produtos") return route.fulfill({ json: [] });
      if (url.pathname === "/api/v1/produtos/importacoes/confirmar") {
        writes.push(request.postDataJSON());
        return route.fulfill({
          status: rejectWrite ? 422 : 500,
          json: { detail: "Cadastro rejeitado no teste controlado" },
        });
      }
      if (url.pathname.startsWith("/api/"))
        return route.fulfill({ status: 501, json: { detail: "Contrato não usado no teste" } });
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () => window.SocialMEIAuth?.current && document.body.classList.contains("experience-app"),
    );
    assert.deepEqual(
      await page.evaluate(() => [
        appData.clientes.length,
        appData.produtos.length,
        appData.vendas.length,
        appData.financeiro.length,
      ]),
      [0, 0, 0, 0],
    );
    assert.match(await page.locator("#homePulseFinance").textContent(), /Ainda sem lançamentos/);
    assert.equal(await page.locator(".home-sale-row").count(), 0);
    assert.equal(await page.evaluate(() => sessionData.conversas.length), 0);
    await capture(page, "remote-empty");
    await page.evaluate((profile) => {
      SocialMEIBusinessProfile.browserRepository().save({
        ...profile,
        businessName: "Negócio sintético",
        completed: true,
      });
      document.dispatchEvent(new CustomEvent("socialmei-business-profile-change"));
      setView("Início");
    }, profiles.barber);
    assert.match(await page.locator("#homeNow").textContent(), /Apresente o que você faz/);
    await capture(page, "remote-profile");
    await page.locator('[data-profile-route="services"]').click();
    assert.equal(writes.length, 0);
    await page.locator('[data-profile-suggest="Serviço:barba"]').click();
    assert.equal(writes.length, 0);
    await page.keyboard.press("Escape");
    assert.equal(writes.length, 0);
    await page.locator('[data-profile-suggest="Serviço:barba"]').click();
    await page.locator("#f_preco").fill("25");
    await page.locator("#createSubmit").click();
    await page.waitForFunction(() =>
      document.body.innerText.includes("Cadastro rejeitado no teste controlado"),
    );
    assert.equal(writes.length, 1);
    assert.equal(writes[0].itens[0].produto.tipo, "Serviço");
    assert.equal(writes[0].itens[0].produto.estoque, null);
    assert.equal(
      await page.evaluate(() => appData.produtos.length),
      0,
      "failed remote write must not create a local record",
    );
    assert(await page.locator("#createModal.open").isVisible());
  } finally {
    await remote.close();
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  return "Personalização: quatro perfis, Home/atalhos, sugestões nativas, cancelar/confirmar, recuperar/ignorar/restaurar, edição, identidade, conta remota vazia e recusa sem fallback; 320/390/1440 claro/escuro";
};

if (require.main === module) {
  const server = http.createServer((request, response) => {
    const file = path.resolve(root, "." + new URL(request.url, "http://local").pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404).end();
      return;
    }
    response.setHeader(
      "Content-Type",
      {
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
        ".woff2": "font/woff2",
      }[path.extname(file)] || "application/octet-stream",
    );
    fs.createReadStream(file).pipe(response);
  });
  (async () => {
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    let browser;
    try {
      browser = await chromium.launch(
        process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
      );
      console.log(await module.exports(browser, `http://127.0.0.1:${server.address().port}`));
    } finally {
      await browser?.close();
      server.close();
    }
  })().catch((error) => {
    console.error(error);
    server.close();
    process.exitCode = 1;
  });
}
