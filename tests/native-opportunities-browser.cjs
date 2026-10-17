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
    const navigate = async () => {
      if (await page.evaluate(() => innerWidth <= 900)) await page.locator("#mb").click();
      await page.locator('#nav [data-nav="Oportunidades"]').click();
      assert(
        await page.locator("#opportunitiesView").evaluate((el) => el.classList.contains("active")),
      );
    };
    await navigate();
    assert.equal(await page.locator("[data-opportunity-open]").count(), 0);
    await page.locator("[data-opportunity-integrations]").click();
    assert.equal(await page.evaluate(() => currentView), "Configurações");
    assert.equal(await page.evaluate(() => selectedSettingsTab), "integracoes");
    await navigate();
    let layouts = 0;
    for (const width of [320, 390, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((value) => SocialMEIThemes.select(value), theme);
        await page
          .locator("[data-opportunity-stop]")
          .isVisible()
          .then(async (visible) => {
            if (visible) await page.locator("[data-opportunity-stop]").click();
          });
        assert.equal(await page.locator("[data-opportunity-open]").count(), 0);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        if (width !== 320)
          await page.screenshot({
            path: path.join(output, `empty-${width}-${theme}.png`),
            fullPage: true,
          });
        await page.locator("[data-opportunity-demo]").click();
        assert.equal(await page.locator("[data-opportunity-open]").count(), 4);
        const firstOpportunity = page.locator(".native-opportunity-list > li").first();
        const restingBackground = await firstOpportunity.evaluate(
          (element) => getComputedStyle(element).backgroundColor,
        );
        await firstOpportunity.locator("[data-opportunity-open]").focus();
        const focusedBackground = await firstOpportunity.evaluate(
          (element) => getComputedStyle(element).backgroundColor,
        );
        assert.notEqual(
          focusedBackground,
          restingBackground,
          "A linha de Oportunidades deve responder visualmente ao foco.",
        );
        assert(
          (await page.locator("#opportunitySource").textContent()).includes("mensagens fictícias"),
        );
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        if (width !== 320)
          await page.screenshot({
            path: path.join(output, `queue-${width}-${theme}.png`),
            fullPage: true,
          });
        await page.locator("#opportunityText").fill("Quero contratar a troca de tela hoje.");
        await page.locator('#opportunityAnalyzeForm [type="submit"]').click();
        assert.equal(
          await page.locator("#opportunityAnalysis h4").first().textContent(),
          "Intenção elevada",
        );
        assert.equal(await page.locator("#opportunityAnalysis img").count(), 0);
        if (width !== 320)
          await page
            .locator(".native-opportunity-analysis")
            .screenshot({ path: path.join(output, `analysis-${width}-${theme}.png`) });
        await page.locator("#opportunityText").fill("Não quero comprar.");
        assert(await page.locator("#opportunityAnalysis").isHidden());
        await page.locator('#opportunityAnalyzeForm [type="submit"]').click();
        assert.equal(
          await page.locator("#opportunityAnalysis h4").first().textContent(),
          "Recusa ou desistência",
        );
        const before = await page.evaluate(() =>
          JSON.stringify({ data: appData, conversations: sessionData.conversas }),
        );
        await page.locator('[data-opportunity-open="demo-3"]').click();
        assert(
          await page.locator("#opportunityModal").evaluate((el) => el.classList.contains("open")),
        );
        const evidence = await page.locator("#opportunityDetail blockquote").allTextContents();
        for (const quote of evidence)
          assert(
            (
              await page.evaluate(() =>
                opportunityDemoSnapshot
                  .find((c) => c.id === 3)
                  .mensagens.map((m) => m.texto)
                  .join("\n"),
              )
            ).includes(quote),
          );
        await page.locator("#opportunityReviewGroup").selectOption("declined");
        await page
          .locator("#opportunityReviewReason")
          .fill("Revisão humana de teste, sem alteração na conversa.");
        await page.locator('#opportunityReviewForm [type="submit"]').click();
        assert(
          (await page.locator("#opportunityDetail").textContent()).includes(
            "Recomendação automática: Responder consulta",
          ),
        );
        assert(
          (await page.locator("#opportunityDetail").textContent()).includes("Revisão humana:"),
        );
        if (width !== 320)
          await page
            .locator("#opportunityModal .modal")
            .screenshot({ path: path.join(output, `review-${width}-${theme}.png`) });
        assert.equal(
          await page.evaluate(() =>
            JSON.stringify({ data: appData, conversations: sessionData.conversas }),
          ),
          before,
        );
        await page.keyboard.press("Escape");
        await page.waitForFunction(
          () => !document.getElementById("opportunityModal").classList.contains("open"),
        );
        assert(
          await page
            .locator('[data-opportunity-open="demo-3"]')
            .evaluate((el) => document.activeElement === el),
        );
        assert(
          (await page.locator('[data-native-opportunity="demo-3"]').textContent()).includes(
            "Respeitar desistência",
          ),
        );
        layouts++;
      }
    await page.locator('[data-opportunity-open="demo-4"]').click();
    assert((await page.locator("#opportunityDetail").textContent()).includes("Conferir pós-venda"));
    assert(!(await page.locator("#opportunityDetail").textContent()).includes("Acolha o problema"));
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.getElementById("opportunityModal").classList.contains("open"),
    );
    await page.locator('[data-opportunity-open="demo-3"]').click();
    await page.locator("[data-opportunity-conversation]").click();
    await page.waitForFunction(
      () => currentView === "Caixa Unificada" && activeConversationId === 3,
    );
    await navigate();
    await page.evaluate(() =>
      sessionData.conversas
        .find((c) => c.id === 3)
        .mensagens.push({
          de: "cliente",
          texto: "Mensagem remota sintética",
          remoteId: "controlled-remote",
        }),
    );
    await page.locator('[data-opportunity-open="demo-3"]').click();
    assert(
      !(await page.locator("#opportunityModal").evaluate((el) => el.classList.contains("open"))),
    );
    assert.equal(await page.locator('[data-opportunity-open="demo-3"]').count(), 0);
    await page.evaluate(() => {
      sessionData.conversas.find((c) => c.id === 3).mensagens.pop();
      renderOpportunities();
    });
    // An explicit existing local CRM link opens the application's actual client drawer.
    await page.evaluate(() => {
      const c = sessionData.conversas.find((c) => c.id === 3);
      c.clientId = appData.clientes[0].id;
    });
    await page.locator('[data-opportunity-open="demo-3"]').click();
    await page.locator("[data-opportunity-client]").click();
    await page.waitForFunction(() =>
      document.getElementById("clientModal").classList.contains("open"),
    );
    assert.equal(
      await page.locator("#clientModalTitle").textContent(),
      await page.evaluate(() => appData.clientes[0].nome),
    );
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.getElementById("clientModal").classList.contains("open"),
    );
    await page
      .locator("#opportunityText")
      .fill('<img src=x onerror="window.opportunityInjection=true"> Quanto custa?');
    await page.locator('#opportunityAnalyzeForm [type="submit"]').click();
    assert.equal(await page.locator("#opportunityAnalysis img").count(), 0);
    assert(!(await page.evaluate(() => window.opportunityInjection)));
    await page.reload();
    await page.evaluate(() => SocialMEIExperience.enterApp("Oportunidades"));
    assert.equal(await page.locator("[data-opportunity-open]").count(), 0);
    assert.equal(await page.locator("#opportunityText").inputValue(), "");
    assert(
      !requests.some((url) => url.includes("/prototypes/")),
      "Native app must not load prototype pages or scripts",
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
    return `Oportunidades nativa: ${layouts} layouts, menu real, vazio, análise/negação, evidências, revisão sem persistência, Caixa, cliente, foco, XSS, reset e conta remota controlada sem dados inventados passaram.`;
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
