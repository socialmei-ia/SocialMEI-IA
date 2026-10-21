const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const { chromium } = require("playwright");
module.exports = async function chartsDemo(browser, origin) {
  const output = path.resolve(__dirname, "../test-results/charts-demo");
  fs.mkdirSync(output, { recursive: true });
  const errors = [],
    writes = [],
    layouts = [];
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (route) => {
    const req = route.request(),
      url = new URL(req.url());
    if (url.origin !== origin) return route.abort();
    if (req.method() !== "GET") writes.push(req.method() + " " + url.pathname);
    return route.continue();
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    assert.deepEqual(
      await page.evaluate(() => ({
        conversations: sessionData.conversas.length,
        notifications: sessionData.notificacoes.length,
        activity: sessionData.atividade.length,
      })),
      { conversations: 0, notifications: 0, activity: 0 },
    );
    const before = await page.evaluate(() => ({
      state: JSON.stringify(appData),
      local: localStorage.getItem("socialmei-app-data-v2"),
    }));
    await page.evaluate(() => setView("Configurações"));
    const toggle = page.locator("#viewDemoToggle");
    assert.equal(await toggle.getAttribute("aria-checked"), "false");
    await toggle.focus();
    await page.keyboard.press("Space");
    assert.equal(await toggle.getAttribute("aria-checked"), "true");
    assert.equal(await page.evaluate(() => SocialMEIDemoData.enabled()), true);
    assert.equal(
      await page.evaluate(() => businessViewConversations().length),
      await page.evaluate(() => businessViewData().conversations.length),
    );
    assert.equal(await page.evaluate(() => sessionData.notificacoes.length), 3);
    const sample = await page.evaluate(() => ({
      metrics: operationalMetrics({ from: "0000-01-01", to: "9999-12-31" }),
      data: businessViewData(),
    }));
    assert.equal(sample.metrics.revenue, sample.metrics.received);
    assert(sample.metrics.revenue > 0 && sample.metrics.revenue < 1000);
    assert.equal(sample.data.vendas.length, 8);
    await page.evaluate(() => setView("Relatórios"));
    const realScope = await page.evaluate(() => {
      SocialMEIDemoData.set(false);
      const s = SocialMEIReportUI.scope();
      SocialMEIDemoData.set(true);
      return s;
    });
    assert.notEqual(await page.evaluate(() => SocialMEIReportUI.scope()), realScope);
    const snapshot = await page.evaluate(() => SocialMEIReportUI.capture());
    assert(snapshot.source.includes("FICTÍCIOS"));
    const csv = await page.evaluate(() => SocialMEIReportData.csv(SocialMEIReportUI.capture()));
    assert(csv.includes("FICTÍCIOS"));
    assert.equal(snapshot.current.revenue, await page.evaluate(() => operationalMetrics().revenue));
    await page.evaluate(() => {
      window.print = () => {};
      SocialMEIReportUI.printCurrent();
    });
    assert(
      await page
        .locator("#reportPrintDocument")
        .textContent()
        .then((text) => text.includes("FICTÍCIOS")),
    );
    const pdfPath = path.join(output, "demonstration.pdf");
    const pdf = await page.pdf({ path: pdfPath, printBackground: true, preferCSSPageSize: true });
    assert.equal(pdf.subarray(0, 5).toString(), "%PDF-");
    const pdfText = require("node:child_process").execFileSync(
      "pdftotext",
      ["-layout", pdfPath, "-"],
      { encoding: "utf8" },
    );
    assert(pdfText.includes("FICTÍCIOS"));
    assert(
      pdfText.includes(
        await page.evaluate(() => formatCurrency(operationalMetrics().revenue).replace(/\s/g, " ")),
      ),
    );
    await page.evaluate(() => document.body.classList.remove("report-print-active"));
    for (const width of [320, 390, 768, 1024, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        for (const view of [
          "Início",
          "Visão Geral",
          "Vendas",
          "Clientes",
          "Financeiro",
          "Relatórios",
          "Oportunidades",
        ]) {
          await page.evaluate((view) => setView(view), view);
          await page.waitForTimeout(80);
          assert(await page.locator("#viewDemoNotice").isVisible());
          assert(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
            view + " " + width,
          );
          layouts.push({ width, theme, view, demo: true });
          if (
            ["Visão Geral", "Financeiro", "Relatórios"].includes(view) &&
            [390, 1440].includes(width)
          ) {
            await page.waitForTimeout(750);
            await page.screenshot({
              path: path.join(
                output,
                `${view === "Visão Geral" ? "overview" : view === "Financeiro" ? "finance" : "reports"}-${width}-${theme}.png`,
              ),
              fullPage: true,
            });
          }
        }
      }
    await page.evaluate(() => setView("Início"));
    assert((await page.locator("#homeNow").textContent()).includes("Lia (exemplo)"));
    await page.locator("[data-home-conversation]").click();
    assert.equal(await page.evaluate(() => currentView), "Oportunidades");
    await page.evaluate(() => setView("Financeiro"));
    assert(await page.locator("[data-create]:visible").first().isDisabled());
    await page.evaluate(() => {
      openCreate("venda");
    });
    assert.equal(
      await page.locator("#createModal").evaluate((e) => e.classList.contains("open")),
      false,
    );
    const chartPoint = page.locator("#financeMiniChart .management-chart-column").first();
    await page.keyboard.press("Tab");
    await chartPoint.focus();
    assert.equal(await chartPoint.evaluate((e) => e.matches(":focus")), true);
    const tip = page.locator("#financeMiniChart .management-chart-tooltip");
    await page.waitForFunction(() => {
      const tip = document.querySelector(
        "#financeMiniChart .management-chart-tooltip:not([hidden])",
      );
      return tip && getComputedStyle(tip).opacity === "1";
    });
    assert.equal(await tip.evaluate((e) => getComputedStyle(e).opacity), "1");
    await page.reload();
    assert.equal(await page.evaluate(() => SocialMEIDemoData.enabled()), true);
    await page.evaluate(() => setView("Configurações"));
    await page.locator("#viewDemoToggle").click();
    assert.equal(await page.evaluate(() => JSON.stringify(appData)), before.state);
    assert.equal(
      await page.evaluate(() => localStorage.getItem("socialmei-app-data-v2")),
      before.local,
    );
    await page.evaluate(() => setView("Vendas"));
    assert.equal(await page.locator("[data-create]:visible").first().isDisabled(), false);
    assert.equal(await page.evaluate(() => businessViewData() === appData), true);
    assert.equal(await page.evaluate(() => sessionData.conversas.length), 0);
    assert.equal(await page.evaluate(() => sessionData.notificacoes.length), 0);
    for (const width of [320, 390, 768, 1024, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        for (const view of ["Financeiro", "Relatórios"]) {
          await page.evaluate((view) => setView(view), view);
          assert.equal(await page.locator("#viewDemoNotice").isVisible(), false);
          assert.equal(await page.evaluate(() => businessViewData() === appData), true);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          layouts.push({ width, theme, view, demo: false });
        }
      }
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.evaluate(() => {
      SocialMEIDemoData.set(true);
      setView("Financeiro");
    });
    await page.waitForTimeout(100);
    assert.equal(
      await page.evaluate(() =>
        [...document.querySelectorAll(".management-bars i")].some((e) => e.getAnimations().length),
      ),
      false,
    );
    // Empty local account must recover exactly, not inherit the sample.
    await page.evaluate(() => {
      SocialMEIDemoData.set(false);
      for (const key of ["clientes", "produtos", "vendas", "financeiro"]) appData[key] = [];
      setView("Relatórios");
    });
    assert.equal(await page.evaluate(() => operationalMetrics().revenue), 0);
    assert.equal(await page.locator("#reportsView .rv2-trend").count(), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(writes, []);
    fs.writeFileSync(
      path.join(output, "results.json"),
      JSON.stringify({ layouts, errors, writes }, null, 2),
    );
  } finally {
    await context.close();
  }
  const remoteContext = await browser.newContext({ viewport: { width: 390, height: 1000 } });
  try {
    const profileAPI = require("./profile-sync-fixture.cjs")();
    let identity = { user: 1, workspace: 1 };
    const page = await remoteContext.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      const req = route.request(),
        url = new URL(req.url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname.endsWith("/config.js"))
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const source={mode:"remote",apiBaseUrl:"/api/v1",workspaceKey:"demo-qa"};const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"},clientes:source,produtos:source,vendas:source,financeiro:source};',
        });
      if (url.pathname === "/api/v1/auth/session")
        return route.fulfill({
          json: {
            usuario: {
              id: identity.user,
              nome: "Pessoa fictícia",
              email: "qa@example.invalid",
              telefone: "11999998888",
            },
            negocio: {
              id: identity.workspace,
              slug: "qa-" + identity.workspace,
              nome: "Negócio fictício",
              configuracao: {},
            },
            papel: "owner",
            csrf_token: "a".repeat(64),
          },
        });
      if (url.pathname === "/api/v1/auth/registration")
        return route.fulfill({ json: { mode: "open" } });
      const profileReply = profileAPI(route, {
        usuario: { id: identity.user },
        negocio: { id: identity.workspace, nome: "Negócio fictício" },
        papel: "owner",
      });
      if (profileReply) return profileReply;
      if (url.pathname.startsWith("/api/v1/")) {
        if (req.method() !== "GET") writes.push(req.method() + " " + url.pathname);
        const collection = url.pathname.slice(8);
        assert(["clientes", "produtos", "vendas", "financeiro"].includes(collection));
        return route.fulfill({
          json:
            collection === "vendas"
              ? [
                  {
                    id: 1,
                    versao: 1,
                    cliente: "Cliente autorizado",
                    item: "Item autorizado",
                    quantidade: 1,
                    valor: 47,
                    data: new Date().toISOString().slice(0, 10),
                    status: "Pago",
                    pagamento: "Pix",
                  },
                ]
              : [],
        });
      }
      return route.continue();
    });
    async function load() {
      await page.goto(origin + "/frontend/socialmei-app.html");
      await page.waitForFunction(
        () =>
          window.SocialMEIAuth?.current &&
          document.body.classList.contains("experience-app") &&
          SocialMEISales.connectionState === "ready",
      );
      await page.evaluate(() => setView("Configurações"));
    }
    await load();
    assert.equal(await page.evaluate(() => SocialMEIDemoData.enabled()), false);
    await page.locator("#viewDemoToggle").click();
    assert.equal(await page.evaluate(() => businessViewData().vendas.length), 8);
    assert.equal(await page.evaluate(() => appData.vendas[0].valor), 47);
    await page.evaluate(() => {
      setView("Relatórios");
      openCreate("venda");
    });
    assert.equal(
      await page.locator("#createModal").evaluate((el) => el.classList.contains("open")),
      false,
    );
    assert((await page.evaluate(() => SocialMEIReportUI.capture().source)).includes("FICTÍCIOS"));
    identity.workspace = 2;
    await load();
    assert.equal(await page.evaluate(() => SocialMEIDemoData.enabled()), false);
    assert.equal(await page.evaluate(() => businessViewData().vendas[0].valor), 47);
    identity.user = 2;
    identity.workspace = 1;
    await load();
    assert.equal(await page.evaluate(() => SocialMEIDemoData.enabled()), false);
    identity.user = 1;
    await load();
    assert.equal(await page.evaluate(() => SocialMEIDemoData.enabled()), true);
    await page.locator("#viewDemoToggle").click();
    assert.equal(await page.evaluate(() => businessViewData() === appData), true);
    assert.deepEqual(errors, []);
    assert.deepEqual(writes, []);
  } finally {
    await remoteContext.close();
  }
  return "Gráficos e demonstração: 90 estados em 5 larguras/2 temas, toggle por teclado, dados/CSV coerentes, fonte e histórico separados, persistência sem alterar registros, somente leitura e movimento reduzido";
};
if (require.main === module)
  (async () => {
    const browser = await chromium.launch({
      executablePath: process.env.CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
    });
    try {
      console.log(await module.exports(browser, "http://127.0.0.1:5500"));
    } finally {
      await browser.close();
    }
  })().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
