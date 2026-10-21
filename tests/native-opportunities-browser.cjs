const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function nativeOpportunities(browser, origin) {
  const output = path.join(root, "test-results/native-opportunities");
  fs.mkdirSync(output, { recursive: true });
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const errors = [],
    external = [],
    requests = [];
  try {
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => requests.push(request.url()));
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) {
        external.push(url.href);
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    await page.waitForFunction(() => document.body.classList.contains("experience-app"));
    // Exercise the legacy inbox-linked analysis using an explicit test fixture:
    // user sessions no longer receive four fictional conversations by default.
    await page.evaluate(() => {
      sessionData.conversas.push(...structuredClone(opportunityDemoSnapshot));
    });
    const navigate = async () => {
      if (await page.evaluate(() => innerWidth <= 900)) await page.locator("#mb").click();
      await page.locator('#nav [data-nav="Oportunidades"]').click();
      assert(
        await page.locator("#opportunitiesView").evaluate((el) => el.classList.contains("active")),
      );
    };
    await navigate();
    assert.equal(await page.locator("#salesCalculator").count(), 0);
    assert.equal(await page.locator("[data-opportunity-open]").count(), 0);
    await page.locator("[data-opportunity-integrations]").click();
    assert.equal(await page.evaluate(() => selectedSettingsTab), "integracoes");
    await navigate();
    async function stopDemo() {
      const menu = page.locator(".opportunity-options");
      if ((await menu.count()) && !(await menu.evaluate((el) => el.open)))
        await menu.locator("summary").click();
      await page.locator("[data-opportunity-stop]").click();
    }
    let layouts = 0;
    const tab = async (id) => {
      await page.locator(`[data-analysis-tab="${id}"]`).click();
    };
    for (const width of [320, 390, 768, 1024, 1280, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((value) => SocialMEIThemes.select(value), theme);
        if (await page.locator("[data-opportunity-stop]").count()) await stopDemo();
        await page.screenshot({
          path: path.join(output, `empty-${width}-${theme}.png`),
          fullPage: true,
        });
        await page.locator("[data-opportunity-demo]").click();
        for (const id of ["analysis", "chance", "attention"]) {
          await tab(id);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          const tabState = await page
            .locator(`[data-analysis-tab="${id}"]`)
            .getAttribute("aria-selected");
          assert.equal(tabState, "true");
          await page.screenshot({
            path: path.join(output, `${id}-${width}-${theme}.png`),
            fullPage: true,
          });
        }
        layouts++;
      }
    await page.locator(".native-opportunity-analysis > summary").click();
    for (let cycle = 0; cycle < 4; cycle++) {
      for (let clear = 0; clear < 3; clear++)
        await page.locator("[data-opportunity-clear]").click();
      await tab("attention");
      await page.locator('[data-analysis-alert="open"]').click();
      assert.equal(await page.locator(".client-analysis-list .client-analysis-card").count(), 3);
      await page.locator('[data-analysis-resolve="analysis-demo-critical"]').click();
      assert.equal(await page.locator(".client-analysis-list .client-analysis-card").count(), 2);
      await page.locator('[data-analysis-alert="resolved"]').click();
      assert.equal(await page.locator(".client-analysis-list .client-analysis-card").count(), 1);
      await page.locator('[data-analysis-resolve="analysis-demo-critical"]').click();
      assert.equal(await page.locator(".client-analysis-list .client-analysis-card").count(), 0);
      await stopDemo();
      await page.locator("[data-opportunity-demo]").click();
    }
    await page.locator(".native-opportunity-analysis > summary").click();
    await tab("chance");
    assert.deepEqual(
      await page
        .locator("[data-analysis-level]")
        .evaluateAll((els) => els.map((el) => el.dataset.analysisLevel)),
      ["all", "frio", "morno", "quente"],
    );
    await tab("analysis");
    assert.equal(
      await page
        .locator('[data-analysis-tab="analysis"]')
        .evaluate((el) => getComputedStyle(el).backgroundColor === "rgba(0, 0, 0, 0)"),
      false,
    );
    const before = await page.evaluate(() =>
      JSON.stringify({ data: appData, conversations: sessionData.conversas }),
    );
    await tab("analysis");
    const lia = page.locator('[data-native-opportunity="analysis-demo-welcome"]');
    await lia.locator(".client-analysis-choice summary").click();
    await lia.locator('[data-analysis-value="frio"]').click();
    assert.equal(
      await page.locator('[data-analysis-tab="chance"]').getAttribute("aria-selected"),
      "true",
    );
    await page.locator('[data-analysis-level="frio"]').click();
    assert.equal(await page.locator(".client-analysis-list .client-analysis-card").count(), 1);
    await page.locator('[data-analysis-level="quente"]').click();
    assert.equal(await page.locator(".client-analysis-list .quente").count(), 1);
    for (const filter of ["morno", "all"])
      await page.locator(`[data-analysis-level="${filter}"]`).click();
    await page
      .locator('[data-native-opportunity="analysis-demo-purchase"] .client-analysis-expand summary')
      .click();
    assert(
      await page
        .locator('[data-native-opportunity="analysis-demo-purchase"] blockquote')
        .isVisible(),
    );
    await page
      .locator('[data-native-opportunity="analysis-demo-welcome"] [data-analysis-reset]')
      .click();
    await page.locator('[data-analysis-level="frio"]').click();
    assert.equal(await page.locator(".client-analysis-list .client-analysis-card").count(), 0);
    await tab("attention");
    await page.locator('[data-analysis-alert="open"]').click();
    assert.deepEqual(
      await page
        .locator(".client-analysis-list [data-priority]")
        .evaluateAll((els) => els.map((e) => e.dataset.priority)),
      ["critical", "high", "normal"],
    );
    const ana = page.locator('[data-native-opportunity="analysis-demo-critical"]');
    await ana.locator("summary").click();
    await page.evaluate(() => {
      navigator.clipboard.writeText = async (text) => {
        window.copiedAnalysis = text;
      };
    });
    await ana.locator("[data-analysis-copy]").click();
    assert.match(await page.evaluate(() => window.copiedAnalysis), /Recebi sua mensagem/);
    await page.evaluate(() => {
      navigator.clipboard.writeText = async () => {
        throw Error("denied");
      };
    });
    await ana.locator("[data-analysis-copy]").click();
    assert.match(
      await page.locator("#clientAnalysisStatus").textContent(),
      /Não foi possível copiar/,
    );
    await ana.locator("[data-analysis-resolve]").click();
    assert.equal(await page.locator(".client-analysis-list .client-analysis-card").count(), 2);
    await page.locator('[data-analysis-alert="resolved"]').click();
    assert.equal(await page.locator(".client-analysis-list .client-analysis-card").count(), 1);
    await page.locator("[data-analysis-resolve]").click();
    await page.locator('[data-analysis-alert="open"]').click();
    assert.equal(await page.locator(".client-analysis-list .client-analysis-card").count(), 3);
    await tab("chance");
    await page.locator('[data-analysis-level="all"]').click();
    await page.locator('[data-opportunity-open="demo-3"]').click();
    const quotes = await page.locator("#opportunityDetail blockquote").allTextContents();
    const originals = await page.evaluate(() =>
      opportunityDemoSnapshot
        .find((c) => c.id === 3)
        .mensagens.map((m) => m.texto)
        .join("\n"),
    );
    quotes.forEach((q) => assert(originals.includes(q)));
    await page.locator("#opportunityReviewGroup").selectOption("declined");
    await page.locator("#opportunityReviewReason").fill("Recusa confirmada em revisão humana.");
    await page.locator('#opportunityReviewForm [type="submit"]').click();
    assert.match(await page.locator("#opportunityDetail").textContent(), /Revisão humana:/);
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.getElementById("opportunityModal").classList.contains("open"),
    );
    assert.equal(
      await page
        .locator('[data-analysis-tab="chance"]')
        .evaluate((el) => document.activeElement === el),
      true,
    );
    await page.locator(".client-analysis-excluded > summary").click();
    await page.locator('[data-opportunity-open="demo-3"]').click();
    await page.locator("[data-opportunity-restore]").click();
    assert.equal(
      await page.evaluate(() =>
        JSON.stringify({ data: appData, conversations: sessionData.conversas }),
      ),
      before,
    );
    await page.locator("[data-opportunity-conversation]").click();
    await page.waitForFunction(
      () => currentView === "Caixa Unificada" && activeConversationId === 3,
    );
    await navigate();

    await tab("analysis");
    await page.locator('[data-analysis-tab="analysis"]').focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(
      await page
        .locator('[data-analysis-tab="chance"]')
        .evaluate((el) => el === document.activeElement),
      true,
    );
    await page.keyboard.press("End");
    assert.equal(
      await page.locator('[data-analysis-tab="attention"]').getAttribute("aria-selected"),
      "true",
    );
    await page.keyboard.press("Home");
    assert.equal(
      await page.locator('[data-analysis-tab="analysis"]').getAttribute("aria-selected"),
      "true",
    );
    await page.locator(".native-opportunity-analysis > summary").click();
    await page
      .locator("#opportunityText")
      .fill('<img src=x onerror="window.opportunityInjection=true"> Não quero comprar.');
    await page.locator('#opportunityAnalyzeForm [type="submit"]').click();
    assert.equal(await page.locator("#opportunityAnalysis img").count(), 0);
    assert(!(await page.evaluate(() => window.opportunityInjection)));
    assert.match(await page.locator("#opportunityAnalysis h4").first().textContent(), /Recusa/);
    await page.locator("#opportunityText").fill("Quero contratar troca de tela.");
    assert(await page.locator("#opportunityAnalysis").isHidden());
    await page.evaluate(() =>
      sessionStorage.setItem("socialmei-business-demo-identity", "other-test"),
    );
    await navigate();
    assert.equal(await page.locator("[data-opportunity-open]").count(), 0);
    assert.equal(await page.locator("#opportunityText").inputValue(), "");
    await page.reload();
    await page.evaluate(() => SocialMEIExperience.enterApp("Oportunidades"));
    assert.equal(await page.locator("[data-opportunity-open]").count(), 0);
    assert(
      !requests.some((url) => url.includes("sales-calculator") || url.includes("/prototypes/")),
    );
    const accountContext = await browser.newContext({ reducedMotion: "reduce" });
    try {
      const account = await accountContext.newPage();
      const writes = [];
      account.on("pageerror", (error) => errors.push(error.message));
      await account.route("**/*", (route) => {
        const request = route.request(),
          url = new URL(request.url());
        if (url.origin !== origin) {
          external.push(url.href);
          return route.abort();
        }
        if (url.pathname === "/frontend/config.js")
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"},clientes:{mode:"remote",apiBaseUrl:"/api/v1",workspaceKey:"controlled-test"}};',
          });
        if (url.pathname.startsWith("/api/v1/")) {
          if (request.method() !== "GET") writes.push(url.pathname);
          const value =
            url.pathname === "/api/v1/auth/session"
              ? {
                  usuario: {
                    id: 12,
                    nome: "Conta de teste",
                    email: "teste@example.com",
                    administrador_plataforma: false,
                  },
                  negocio: {
                    id: 21,
                    slug: "controlled-test",
                    nome: "Negócio de teste",
                    configuracao: {},
                  },
                  papel: "owner",
                  csrf_token: "a".repeat(64),
                }
              : url.pathname === "/api/v1/auth/registration"
                ? { mode: "open" }
                : [];
          return route.fulfill({ json: value });
        }
        return route.continue();
      });
      await account.goto(origin + "/frontend/socialmei-app.html");
      await account.waitForFunction(
        () => typeof SocialMEIAuth !== "undefined" && SocialMEIAuth.current,
      );
      // Wait for authenticated bootstrap before navigating; it now loads the scoped profile.
      await account.waitForFunction(() => document.body?.classList.contains("experience-app"));
      await account.evaluate(() => SocialMEIExperience.enterApp("Oportunidades"));
      assert.equal(await account.evaluate(() => sessionData.conversas.length), 0);
      assert.equal(await account.locator("[data-opportunity-demo]").count(), 0);
      for (const width of [390, 1440])
        for (const theme of ["light", "dark"]) {
          await account.setViewportSize({ width, height: 1000 });
          await account.evaluate((value) => SocialMEIThemes.select(value), theme);
          assert.equal(await account.locator("[data-opportunity-open]").count(), 0);
          assert(await account.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          await account.screenshot({
            path: path.join(output, `account-empty-${width}-${theme}.png`),
            fullPage: true,
          });
        }
      await account.evaluate(() => {
        mergeRemoteMessage({
          id: "synthetic-remote",
          cliente: "Contato sintético",
          canal: "whatsapp",
          mensagem: "Texto sintético sem identidade compatível para priorização",
          horario: "2026-10-16T12:00:00Z",
        });
        renderOpportunities();
      });
      assert.equal(await account.locator("[data-opportunity-open]").count(), 0);
      assert(
        !(await account.locator("#opportunitiesView").textContent()).includes(
          "Texto sintético sem identidade",
        ),
      );
      await account.locator(".native-opportunity-analysis > summary").click();
      await account.locator("#opportunityText").fill("Quero comprar.");
      await account.locator('#opportunityAnalyzeForm [type="submit"]').click();
      assert.equal(
        await account.locator("#opportunityAnalysis h4").first().textContent(),
        "Intenção elevada",
      );
      assert.deepEqual(writes, []);
    } finally {
      await accountContext.close();
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    return `Análise de Clientes V2: ${layouts} layouts, três abas, filtros, classificação humana, evidências, alertas/resolução/reabertura, clipboard/falha, Caixa, foco, teclado, XSS, isolamento e conta remota vazia passaram.`;
  } finally {
    await context.close();
  }
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
