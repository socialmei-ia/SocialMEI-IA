const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function reportsNative(browser, origin) {
  const output = path.join(root, "test-results/reports-v21-native");
  fs.mkdirSync(output, { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  const errors = [],
    layouts = [],
    writes = [],
    external = [];
  const clients = ["Ana Lima", "Bruno Alves", "Carla Reis", "Davi Melo"].map((nome, i) => ({
    id: i + 1,
    versao: 1,
    nome,
    tags: [],
    criadoEm: "2026-06-01",
  }));
  const products = [
    {
      id: 101,
      versao: 1,
      nome: "Ajuste de vestido",
      tipo: "Serviço",
      preco: 90,
      custo: 0,
      estoque: null,
      minimo: null,
      status: "Ativo",
    },
    {
      id: 102,
      versao: 1,
      nome: "Ecobag artesanal",
      tipo: "Produto",
      preco: 65,
      custo: 0,
      estoque: 0,
      minimo: 0,
      status: "Ativo",
    },
  ];
  const sales = [],
    finance = [];
  for (let i = 0; i < 80; i++) {
    const date = new Date(Date.UTC(2026, 9, 18 - i)).toISOString().slice(0, 10);
    const product = products[i % 2],
      client = clients[i % 4];
    sales.push({
      id: 1000 + i,
      versao: 1,
      cliente_id: client.id,
      cliente: client.nome,
      produto_id: product.id,
      item: product.nome,
      quantidade: 1,
      valor: product.preco,
      data: date,
      status: i % 13 === 0 ? "Pendente" : "Pago",
      pagamento: "Pix",
    });
    finance.push({
      id: 2000 + i,
      versao: 1,
      tipo: i % 3 ? "receita" : "despesa",
      descricao: "Lançamento fictício de QA",
      pessoa: "",
      valor: i % 3 ? 80 : 30,
      vencimento: date,
      status: "pago",
    });
  }
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  await page.clock.setFixedTime(new Date("2026-10-18T15:00:00Z"));
  await page.route("**/*", (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (url.origin !== origin) {
      external.push(url.href);
      return route.abort();
    }
    if (url.pathname.endsWith("/config.js"))
      return route.fulfill({
        contentType: "text/javascript",
        body: 'const source={mode:"remote",apiBaseUrl:"/api/v1",workspaceKey:"native-v21-qa"};const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"},clientes:source,produtos:source,vendas:source,financeiro:source};',
      });
    if (url.pathname === "/api/v1/auth/session")
      return route.fulfill({
        json: {
          usuario: {
            id: 1,
            nome: "Pessoa fictícia",
            email: "qa@example.invalid",
            telefone: "11999998888",
          },
          negocio: { id: 1, slug: "qa-v21", nome: "Ateliê Aurora · fictício", configuracao: {} },
          papel: "owner",
          csrf_token: "a".repeat(64),
        },
      });
    if (url.pathname === "/api/v1/auth/registration")
      return route.fulfill({ json: { mode: "open" } });
    if (url.pathname.startsWith("/api/v1/")) {
      if (request.method() !== "GET") writes.push(request.method() + " " + url.pathname);
      const data = { clientes: clients, produtos: products, vendas: sales, financeiro: finance }[
        url.pathname.slice(8)
      ];
      assert(data, "Rota inesperada: " + url.pathname);
      return route.fulfill({ json: data });
    }
    return route.continue();
  });
  const settle = () =>
    page.waitForFunction(
      () =>
        document.querySelector("#nvReportKpis").getAttribute("aria-busy") === "false" &&
        !document.querySelector('#reportsView [data-motion-state="updating"]'),
    );
  const capture = async (name, width, theme) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
    await settle();
    await page.evaluate(() =>
      Promise.all(
        document
          .getAnimations()
          .filter((a) => a.effect?.getTiming().iterations !== Infinity)
          .map((a) => a.finished.catch(() => {})),
      ),
    );
    await page.screenshot({
      path: path.join(output, `${name}-${width}-${theme}.png`),
      fullPage: !["generate", "ready"].includes(name),
      animations: "disabled",
    });
  };
  const close = async () => {
    await page.keyboard.press("Escape");
    await page.locator("#reportGenerateModal.open").waitFor({ state: "hidden" });
  };
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current &&
        document.body.classList.contains("experience-app") &&
        SocialMEISales.connectionState === "ready" &&
        SocialMEIFinance.connectionState === "ready",
    );
    await page.evaluate(() =>
      SocialMEIBusinessProfile.browserRepository().save({
        businessName: "Ateliê Aurora · fictício",
        segment: "tailoring",
        offers: ["products", "services"],
        completed: true,
      }),
    );
    await page.locator('#nav [data-nav="Relatórios"]').click();
    await page.locator('[data-report-quick="30 dias"]').click();
    await settle();
    assert.equal(
      await page.locator("#resultChapter .v21-chart-total").count(),
      0,
      "Não repetir o faturamento como segundo KPI",
    );
    assert.equal(await page.evaluate(() => window.REPORTS_PREVIEW), undefined);
    assert(!(await page.content()).includes("experimental/reports-v21/sandbox.js"));
    await page.locator('[data-report-quick="7 dias"]').click();
    await page.evaluate(() => SocialMEIReportMotion.update());
    await settle();
    assert(
      await page.evaluate(() => {
        const chart = document.querySelector("#resultChapter .rv2-trend");
        const expected = new DOMParser()
          .parseFromString(SocialMEIReportUI.trend(JSON.parse(chart.dataset.series)), "text/html")
          .querySelector(".rv2-line")
          .getAttribute("d");
        const numbers = (value) => value.match(/-?\d+(?:\.\d+)?/g).map(Number);
        const target = numbers(expected),
          actual = numbers(chart.querySelector(".rv2-line").getAttribute("d"));
        return (
          target.length === actual.length &&
          target.every((value, i) => Math.abs(value - actual[i]) < 0.11)
        );
      }),
      "Atualização repetida não pode congelar o gráfico no período anterior",
    );
    await page.locator('[data-report-quick="30 dias"]').click();
    await settle();
    for (const width of [1440, 768, 390, 320])
      for (const theme of ["light", "dark"]) {
        await capture("dashboard", width, theme);
        const layout = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth > innerWidth,
          tabs: [...document.querySelectorAll("#nvReportTabs button")].map(
            (n) => n.getBoundingClientRect().height,
          ),
          clippedValues: [...document.querySelectorAll("#nvReportKpis b")].some(
            (n) => n.scrollWidth > n.clientWidth + 1,
          ),
          noteSize: getComputedStyle(document.querySelector("#resultChapter > .management-note"))
            .fontSize,
        }));
        assert(
          !layout.overflow && !layout.clippedValues,
          JSON.stringify({ width, theme, ...layout }),
        );
        assert(layout.tabs.every((h) => h >= 44));
        if (width <= 390) assert(parseFloat(layout.noteSize) >= 14);
        layouts.push({ width, theme, ...layout });
      }
    // Re-enter through the real mobile menu, not an isolated preview route.
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.evaluate(() => setView("Início"));
    await page.locator("#mb").click();
    await page.locator('#nav [data-nav="Relatórios"]').click();
    assert(await page.locator("#reportsView").isVisible());
    await page.locator(".report-period-options summary").click();
    await page.locator("#nvReportCompare").uncheck();
    assert.equal(await page.evaluate(() => SocialMEIReportUI.capture().comparisonEnabled), false);
    await page.locator("#nvReportCompare").check();
    await page.locator("#reportsView [data-nv-hide]").click();
    assert.match(await page.locator("#nvReportKpis b").first().textContent(), /••••/);
    await page.locator("#reportsView [data-nv-hide]").click();
    await settle();
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.locator("[data-report-generate]").click();
      for (const theme of ["light", "dark"]) {
        await capture("generate", width, theme);
        assert.equal(
          await page.locator("#reportGeneratePeriod option:checked").textContent(),
          "Período selecionado",
        );
        assert.match(
          await page.locator("#reportGenerateRange").textContent(),
          /19\/09\/2026.*18\/10\/2026/,
        );
        assert.equal(
          await page.locator("#reportGeneratePeriod").getAttribute("aria-describedby"),
          "reportGenerateRange",
        );
      }
      await close();
    }
    await page.locator("[data-report-generate]").click();
    await page.locator("#reportGenerateForm [type=submit]").click();
    await page.waitForFunction(
      () => document.querySelector("#reportGenerateTitle").textContent === "Relatório pronto",
    );
    assert.match(
      await page.locator("#reportGenerateBody").textContent(),
      /19\/09\/2026.*18\/10\/2026/,
    );
    const stored = await page.evaluate(
      () => SocialMEIReportData.history(localStorage, SocialMEIReportUI.scope).read().records[0],
    );
    assert(stored.title.includes("2026-09-19"), "Formato persistido preservado");
    assert.equal(stored.snapshot.range.from, "2026-09-19");
    await page.locator("#reportGenerateModal [data-report-action=print]").evaluate((button) => {
      window.print = () => {};
      button.click();
    });
    assert.match(
      await page.locator("#reportPrintDocument").textContent(),
      /19\/09\/2026.*18\/10\/2026/,
    );
    await page.evaluate(() => document.body.classList.remove("report-print-active"));
    const snapshot = JSON.stringify(stored.snapshot);
    for (const width of [1440, 768, 390])
      for (const theme of ["light", "dark"]) await capture("ready", width, theme);
    await close();
    assert.match(
      await page.locator("#reportHistoryList .rv2-history-row b").textContent(),
      /19\/09\/2026.*18\/10\/2026/,
    );
    for (const width of [1440, 768, 390])
      for (const theme of ["light", "dark"]) {
        await page.locator(".rv2-history").scrollIntoViewIfNeeded();
        await capture("history", width, theme);
      }
    await page.locator("#reportHistorySearch").fill("19/09/2026");
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 1);
    await page.locator("#reportHistorySearch").fill("2026-09-19");
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 1);
    await page.locator("#reportHistorySearch").fill("");
    await page.evaluate(() => {
      appData.vendas[0].valor = 999999;
    });
    assert.equal(
      await page.evaluate(() =>
        JSON.stringify(
          SocialMEIReportData.history(localStorage, SocialMEIReportUI.scope).read().records[0]
            .snapshot,
        ),
      ),
      snapshot,
    );
    await page.locator("[data-report-generate]").click();
    await page.evaluate(() => {
      document.querySelector("#reportGenerateForm").requestSubmit();
      closeModal("reportGenerateModal");
    });
    await page.locator("#reportGenerateModal.open").waitFor({ state: "hidden" });
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 1);
    assert((await page.locator("#toastZone").textContent()).includes("Geração cancelada"));
    await page.locator("[data-report-generate]").click();
    await page.keyboard.press("Tab");
    assert(
      await page
        .locator("#reportGenerateModal")
        .evaluate((n) => n.contains(document.activeElement)),
    );
    await page.keyboard.press("Shift+Tab");
    assert(await page.locator("#app").evaluate((n) => n.inert));
    await close();
    assert(
      await page.locator("[data-report-generate]").evaluate((n) => n === document.activeElement),
    );
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.locator('[data-report-quick="7 dias"]').click();
    await settle();
    assert.equal(
      await page
        .locator("#reportsView")
        .evaluate(
          (n) => n.getAnimations({ subtree: true }).filter((a) => a.playState === "running").length,
        ),
      0,
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert.deepEqual(writes, []);
    fs.writeFileSync(
      path.join(output, "results.json"),
      JSON.stringify(
        {
          layouts,
          datePresentation: "pt-BR; persisted ISO unchanged",
          snapshotsUnchanged: true,
          cancellation: "no saved copy",
          errors,
          external,
          writes,
        },
        null,
        2,
      ),
    );
    return "Relatórios V2.1 nativos: navegação oficial, 8 layouts, datas BR/ISO preservado, seletor mobile, histórico, cancelamento, teclado/foco e movimento reduzido";
  } finally {
    await context.close();
  }
};
if (require.main === module) {
  const server = http.createServer((request, response) => {
    const file = path.resolve(root, "." + new URL(request.url, "http://local").pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
      return response.writeHead(404).end();
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
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    let browser;
    try {
      browser = await chromium.launch({
        executablePath: process.env.CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
        args: ["--no-sandbox"],
      });
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
