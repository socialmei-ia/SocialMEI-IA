const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path"),
  http = require("node:http"),
  { execFileSync } = require("node:child_process"),
  { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function reportsV2(browser, origin) {
  const profileAPI = require("./profile-sync-fixture.cjs")();
  const output = path.join(root, "test-results/reports-v2");
  fs.mkdirSync(output, { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "no-preference",
    acceptDownloads: true,
  });
  const errors = [],
    external = [],
    writes = [],
    profileWrites = [];
  let identity = { user: 1, workspace: 1 },
    failFinance = false,
    configScope = "qa";
  const sales = [
    { id: 31, produto_id: 21, quantidade: 2, valor: 60, data: "2026-10-10" },
    { id: 32, produto_id: 22, quantidade: 3, valor: 90, data: "2026-10-11" },
    { id: 33, produto_id: 21, quantidade: 1, valor: 30, data: "2026-10-12", status: "Pendente" },
    { id: 34, produto_id: 21, quantidade: 1, valor: 30, data: "2026-09-10" },
    { id: 35, produto_id: 21, quantidade: 1, valor: 10, data: "2026-08-01" },
  ].map((row) => ({
    versao: 1,
    cliente_id: 11,
    cliente: "=2+2",
    item: row.produto_id === 21 ? "Perfume sintético" : "Ajuste sintético",
    status: "Pago",
    pagamento: "Pix",
    ...row,
  }));
  const clients = [{ id: 11, versao: 1, nome: "=2+2", tags: [], criadoEm: "2026-08-01T12:00:00Z" }];
  const products = [
    {
      id: 21,
      versao: 1,
      nome: "Perfume sintético",
      tipo: "Produto",
      preco: 30,
      custo: 10,
      estoque: 10,
      minimo: 1,
      status: "Ativo",
    },
    {
      id: 22,
      versao: 1,
      nome: "Ajuste sintético",
      tipo: "Serviço",
      preco: 30,
      custo: 10,
      estoque: null,
      minimo: null,
      status: "Ativo",
    },
  ];
  const finance = [
    { id: 41, descricao: "Receita do período", tipo: "receita", valor: 50, status: "pago" },
    { id: 42, descricao: ' \t=CMD("x")', tipo: "despesa", valor: 20, status: "pago" },
    { id: 43, descricao: "Em aberto", tipo: "receita", valor: 100, status: "aberto" },
  ].map((row) => ({ versao: 1, pessoa: "", vencimento: "2026-10-10", ...row }));
  let page;
  const settled = async () =>
    page.waitForFunction(
      () => document.getElementById("nvReportKpis").getAttribute("aria-busy") === "false",
    );
  const close = async () => {
    await page.keyboard.press("Escape");
    await page.locator("#reportGenerateModal.open").waitFor({ state: "hidden" });
  };
  const capture = async (name, width, theme) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate((t) => SocialMEIThemes.select(t), theme);
    await settled();
    await page.evaluate(() => window.scrollTo(0, 0));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    if (overflow) {
      console.log(
        "OVERFLOW",
        await page.evaluate(() =>
          [...document.querySelectorAll("#reportsView *")]
            .filter(
              (el) =>
                el.getClientRects().length && el.getBoundingClientRect().right > innerWidth + 1,
            )
            .map((el) => [
              el.tagName,
              el.id,
              el.className?.baseVal ?? el.className,
              Math.round(el.getBoundingClientRect().width),
              Math.round(el.getBoundingClientRect().right),
            ])
            .slice(0, 16),
        ),
      );
      await page.screenshot({ path: path.join(output, "overflow.png"), fullPage: true });
    }
    assert(!overflow, `${name}-${width}-${theme} overflow`);
    await page.screenshot({
      path: path.join(output, `${name}-${width}-${theme}.png`),
      fullPage: !name.includes("modal"),
      animations: "disabled",
    });
  };
  const generate = async (type = "geral") => {
    await page.locator("[data-report-generate]").click();
    await page.locator("#reportGenerateType").selectOption(type);
    await page.locator("#reportGenerateForm [type=submit]").click();
    await page.waitForFunction(() =>
      ["Relatório pronto", "Não foi possível concluir"].includes(
        document.getElementById("reportGenerateTitle").textContent,
      ),
    );
  };
  const downloadText = async (locator) => {
    const pending = page.waitForEvent("download");
    await locator.click();
    const file = await pending;
    assert(file.suggestedFilename().endsWith(".csv"));
    return fs.readFileSync(await file.path(), "utf8");
  };
  const custom = async () => {
    const disclosure = page.locator("#reportsView .report-period-options");
    if (!(await disclosure.evaluate((el) => el.open))) await disclosure.locator("summary").click();
    await page.locator('[data-nv-report-period="Personalizado"]').click();
    await page.locator("#mobileDateFrom").fill("2026-10-01");
    await page.locator("#mobileDateTo").fill("2026-10-31");
    await page.locator("#periodModal [type=submit]").click();
    await page.locator("#periodModal.open").waitFor({ state: "hidden" });
    await settled();
  };
  try {
    page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.clock.setFixedTime(new Date("2026-10-17T12:00:00Z"));
    await page.route("**/*", (route) => {
      const req = route.request(),
        url = new URL(req.url());
      if (url.origin !== origin) {
        external.push(url.href);
        return route.abort();
      }
      if (url.pathname.endsWith("/config.js"))
        return route.fulfill({
          contentType: "text/javascript",
          body:
            'const source={mode:"remote",apiBaseUrl:"/api/v1",workspaceKey:' +
            JSON.stringify(configScope) +
            '};const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"},clientes:source,produtos:source,vendas:source,financeiro:source};',
        });
      if (url.pathname === "/api/v1/auth/session")
        return route.fulfill({
          json: identity
            ? {
                usuario: {
                  id: identity.user,
                  nome: "Pessoa sintética",
                  email: `u${identity.user}@example.com`,
                  telefone: "11999998888",
                },
                negocio: {
                  id: identity.workspace,
                  slug: `mei-${identity.workspace}`,
                  nome: "Perfumaria sintética",
                  configuracao: {},
                },
                papel: "owner",
                csrf_token: "a".repeat(64),
              }
            : null,
        });
      if (url.pathname === "/api/v1/auth/registration")
        return route.fulfill({ json: { mode: "open" } });
      if (["/api/v1/workspace-profile", "/api/v1/auth/preferences"].includes(url.pathname)) {
        if (url.pathname === "/api/v1/auth/preferences") assert.equal(req.method(), "GET");
        else if (req.method() !== "GET") {
          assert.equal(req.method(), "PATCH");
          profileWrites.push(url.pathname);
        }
        return profileAPI(
          route,
          identity
            ? {
                usuario: { id: identity.user },
                negocio: { id: identity.workspace, nome: "Perfumaria sintética" },
                papel: "owner",
              }
            : null,
        );
      }
      if (url.pathname.startsWith("/api/v1/")) {
        if (req.method() !== "GET") writes.push(req.method() + " " + url.pathname);
        if (url.pathname === "/api/v1/financeiro" && failFinance)
          return route.fulfill({
            status: 503,
            json: { detail: "Financeiro indisponível no teste" },
          });
        const datasets = {
          clientes: clients,
          produtos: products,
          vendas: sales,
          financeiro: finance,
        };
        const rows = datasets[url.pathname.slice("/api/v1/".length)];
        assert(rows, url.pathname);
        return route.fulfill({
          json: identity?.user === 1 && identity?.workspace === 1 ? rows : [],
        });
      }
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app") &&
        SocialMEISales.connectionState === "ready" &&
        SocialMEIFinance.connectionState === "ready",
    );
    await page.evaluate(() =>
      SocialMEIBusinessProfile.browserRepository().save({
        businessName: "Perfumaria sintética",
        segment: "perfume",
        offers: ["products"],
        productCategories: ["Perfumes"],
        capabilities: { inventory: true },
        modules: ["products", "sales", "finance"],
        completed: true,
      }),
    );
    await page.locator('#nav [data-nav="Relatórios"]').click();
    await custom();
    assert.equal(await page.evaluate(() => operationalMetrics().revenue), 150);
    assert.equal(await page.evaluate(() => operationalMetrics().balance), 30);
    assert.match(await page.locator("#reportProfileContext").textContent(), /Perfumaria/);
    assert.match(await page.locator("#nvReportKpis").textContent(), /400/);
    assert.match(await page.locator("#reportsGrid").textContent(), /Ajuste sintético/);
    assert.match(await page.locator("#reportsGrid").textContent(), /Pago não significa entregue/);
    const point = page.locator("#resultChapter .rv2-point").first();
    await point.focus();
    assert(await page.locator("#resultChapter .rv2-chart-tooltip").isVisible());
    await page.keyboard.press("Enter");
    assert.match(
      await page.locator("#resultChapter .rv2-chart-readout").textContent(),
      /faturamento/,
    );
    await page.evaluate(() => renderReports());
    assert.equal(
      await page.evaluate(
        () =>
          document.getAnimations().filter((a) => a.effect?.target?.classList?.contains("rv2-line"))
            .length,
      ),
      0,
      "unchanged series must not replay",
    );
    // Normal motion, interrupted updates and current filter labels must remain synchronized.
    await page.locator('[data-report-quick="7 dias"]').click();
    assert.equal(await page.locator("#nvReportKpis").getAttribute("aria-busy"), "true");
    await page.evaluate(() => {
      for (const value of ["30 dias", "3 meses", "7 dias", "30 dias"])
        document.querySelector(`[data-report-quick="${value}"]`).click();
    });
    await settled();
    assert.equal(await page.evaluate(() => selectedPeriod), "30 dias");
    assert.match(await page.locator("#reportsPeriodLabel").textContent(), /2026/);
    assert.equal(
      await page
        .locator('[data-report-quick="30 dias"]')
        .evaluate((el) => el === document.activeElement),
      true,
    );
    await custom();
    // Current records without sufficiently old dates cannot establish comparison coverage.
    await page.evaluate(() => {
      window.olderReportSales = appData.vendas;
      appData.vendas = appData.vendas.filter((s) => s.data >= "2026-09-01");
      renderReports();
    });
    await settled();
    assert.match(
      await page.locator("#nvReportKpis").textContent(),
      /Histórico anterior insuficiente/,
    );
    await page.evaluate(() => {
      appData.vendas = olderReportSales;
      renderReports();
    });
    await settled();
    await page.evaluate(() => {
      window.quantityReportSales = appData.vendas;
      appData.vendas = appData.vendas.map((row, index) =>
        index === 0 ? { ...row, quantidade: null } : row,
      );
      renderReports();
    });
    await page.locator("#reportProductsDetails summary").click();
    assert.match(await page.locator("#reportProductsDetails").textContent(), /Não informada/);
    await page.evaluate(() => {
      appData.vendas = quantityReportSales;
      renderReports();
    });
    await page.locator("#reportProductsDetails summary").click();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await settled();
    for (const width of [320, 360, 390, 768, 1024, 1440])
      for (const theme of ["light", "dark"]) {
        await capture("dashboard", width, theme);
        assert.equal(await page.locator("#nvReportTabs [role=tab]:visible").count(), 5);
        const boxes = await page.locator("#nvReportTabs button").evaluateAll((items) =>
          items.map((item) => ({
            left: item.getBoundingClientRect().left,
            right: item.getBoundingClientRect().right,
            width: item.getBoundingClientRect().width,
            height: item.getBoundingClientRect().height,
          })),
        );
        assert(
          boxes.every(
            (box) => box.left >= 0 && box.right <= width + 1 && box.width >= 65 && box.height >= 44,
          ),
        );
      }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator("[data-report-generate]").click();
    for (const width of [390, 1440])
      for (const theme of ["light", "dark"]) await capture("generate-modal", width, theme);
    // Slow only the test's paint boundary so the genuine local stages can be observed.
    await page.evaluate(() => {
      window.reportOriginalRAF = requestAnimationFrame;
      window.requestAnimationFrame = (callback) =>
        reportOriginalRAF((time) => setTimeout(() => callback(time), 25));
    });
    await page.locator("#reportGenerateForm [type=submit]").click();
    await page.locator("#reportGenerateBody progress").waitFor();
    assert.equal(await page.locator("#reportGenerateBody li").count(), 3);
    await page.waitForFunction(
      () => document.getElementById("reportGenerateTitle").textContent === "Relatório pronto",
    );
    await page.evaluate(() => {
      window.requestAnimationFrame = reportOriginalRAF;
    });
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 1);
    assert.equal(
      await page.locator("#reportGenerateTitle").evaluate((el) => el === document.activeElement),
      true,
    );
    for (const width of [390, 1440])
      for (const theme of ["light", "dark"]) await capture("ready-modal", width, theme);
    const csv = await downloadText(page.locator("#reportGenerateModal [data-report-action=csv]"));
    assert(csv.includes('"Faturamento · vendas pagas";"150";"30"'));
    assert(csv.includes('"Saldo realizado";"30"'));
    assert(csv.includes('"\'=2+2"'));
    assert(csv.includes('"\' \t=CMD(""x"")"'));
    await page.evaluate(() => {
      window.print = () => {
        window.reportPrintRequested = true;
      };
    });
    await page.locator("#reportGenerateModal [data-report-action=print]").click();
    assert.equal(await page.evaluate(() => window.reportPrintRequested), true);
    const pdfPath = path.join(output, "report-valid.pdf");
    const pdf = await page.pdf({ path: pdfPath, printBackground: true, preferCSSPageSize: true });
    assert(pdf.subarray(0, 5).toString() === "%PDF-");
    const pdfText = execFileSync("pdftotext", ["-layout", pdfPath, "-"], { encoding: "utf8" });
    assert(pdfText.includes("Perfumaria sintética"));
    assert(pdfText.includes("150,00"));
    assert(pdfText.includes("30,00"));
    assert(!pdfText.includes("Relatórios gerados"));
    assert(pdfText.includes("sem soma duplicada"));
    fs.writeFileSync(path.join(output, "report-valid.txt"), pdfText);
    fs.writeFileSync(path.join(output, "report-valid.csv"), csv);
    await page.evaluate(() => document.body.classList.remove("report-print-active"));
    await close();
    assert.equal(
      await page.locator("[data-report-generate]").evaluate((el) => el === document.activeElement),
      true,
    );
    await page.locator("#reportHistorySearch").fill("não existe");
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 0);
    await page.locator("#reportHistorySearch").fill("");
    await page.locator("#reportHistoryStatus").selectOption("error");
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 0);
    await page.locator("#reportHistoryStatus").selectOption("all");
    // Downloads are immutable even after changing the live data and period.
    await page.evaluate(() => {
      appData.vendas[0].valor = 999;
      renderReports();
    });
    await settled();
    assert.equal(
      await downloadText(page.locator("#reportHistoryList [data-report-action=csv]").first()),
      csv,
    );
    await page.reload();
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current &&
        document.body.classList.contains("experience-app") &&
        SocialMEISales.connectionState === "ready",
    );
    await settled();
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 1);
    for (const width of [390, 1440])
      for (const theme of ["light", "dark"]) await capture("history", width, theme);
    await page.locator("#reportHistoryList [data-report-action=details]").click();
    assert.match(await page.locator("#reportGenerateBody").textContent(), /150,00/);
    await close();
    // Export errors and local quota failures must not announce persistence or success.
    await page.evaluate(() => {
      window.originalReportURL = URL.createObjectURL;
      URL.createObjectURL = () => {
        throw Error("Falha de arquivo no teste");
      };
    });
    await page.locator("#exportCsv").click();
    await page.waitForFunction(() => document.body.innerText.includes("Falha de arquivo no teste"));
    await page.evaluate(() => {
      URL.createObjectURL = originalReportURL;
    });
    await page.evaluate(() => {
      window.originalReportSet = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key.startsWith("socialmei-report-history-v1:")) throw Error("quota");
        return originalReportSet.call(this, key, value);
      };
    });
    await generate();
    assert.match(await page.locator("#reportGenerateBody").textContent(), /Gerado, mas não salvo/);
    await close();
    await page.evaluate(() => {
      Storage.prototype.setItem = originalReportSet;
    });
    await page.reload();
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current &&
        document.body.classList.contains("experience-app") &&
        SocialMEIFinance.connectionState === "ready",
    );
    await settled();
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 1);
    failFinance = true;
    await page.evaluate(() => SocialMEIFinance.refresh());
    await page.getByRole("tab", { name: "Financeiro", exact: true }).click();
    assert.match(await page.locator("#reportsGrid").textContent(), /indisponível/);
    assert.equal(await page.locator("#reportsGrid .management-chart").count(), 0);
    await generate();
    assert.match(await page.locator("#reportGenerateTitle").textContent(), /Não foi possível/);
    assert.match(await page.locator("#reportGenerateBody").textContent(), /fonte necessária/);
    await close();
    await page.locator("#reportHistoryStatus").selectOption("error");
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 1);
    assert(await page.locator("#reportHistoryList [data-report-action=csv]").isDisabled());
    await page.locator("#reportHistoryStatus").selectOption("all");
    for (const width of [390, 1440])
      for (const theme of ["light", "dark"]) await capture("source-error", width, theme);
    // Vendas can still be generated when only Financeiro is unavailable.
    await generate("vendas");
    assert.match(await page.locator("#reportGenerateTitle").textContent(), /Relatório pronto/);
    await close();
    failFinance = false;
    for (const changed of [
      { user: 2, workspace: 1 },
      { user: 1, workspace: 2 },
    ]) {
      identity = changed;
      await page.reload();
      await page.waitForFunction(
        (expected) =>
          window.SocialMEIAuth?.current?.usuario.id === expected.user &&
          SocialMEIAuth.current.negocio.id === expected.workspace &&
          document.body.classList.contains("experience-app") &&
          SocialMEISales.connectionState === "ready",
        changed,
      );
      await page.evaluate(() => setView("Relatórios"));
      await settled();
      assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 0);
      assert.equal(await page.evaluate(() => operationalMetrics().revenue), 0);
      assert.equal(await page.locator("#reportsGrid .management-chart").count(), 0);
      if (changed.user === 2)
        for (const width of [390, 1440])
          for (const theme of ["light", "dark"]) await capture("empty", width, theme);
    }
    identity = { user: 1, workspace: 1 };
    await page.reload();
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 1 &&
        SocialMEIAuth.current.negocio.id === 1 &&
        document.body.classList.contains("experience-app") &&
        SocialMEISales.connectionState === "ready",
    );
    await page.evaluate(() => setView("Relatórios"));
    await settled();
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 3);
    configScope = "different-contract";
    await page.reload();
    await page.waitForFunction(
      () => window.SocialMEIAuth?.current && document.body.classList.contains("experience-app"),
    );
    await page.evaluate(() => setView("Relatórios"));
    await settled();
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 0);
    identity = null;
    await page.reload();
    await page.locator("[data-xp-screen=landing].is-active").waitFor();
    assert.equal(await page.evaluate(() => SocialMEIReportUI.scope()), null);
    assert.deepEqual(profileWrites, ["/api/v1/workspace-profile"]);
    assert.deepEqual(writes, []);
    assert.deepEqual(external, []);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
  // Local records are distinct from the optional sample; report history is never preloaded.
  const local = await browser.newContext({ reducedMotion: "reduce" });
  try {
    const localPage = await local.newPage();
    localPage.on("pageerror", (error) => errors.push(error.message));
    await localPage.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    await localPage.goto(origin + "/frontend/socialmei-app.html");
    await localPage.locator('[data-xp-go="app"]').first().click();
    await localPage.evaluate(() => setView("Relatórios"));
    assert.equal(await localPage.locator("#reportHistoryList .rv2-history-row").count(), 0);
    assert.match(
      await localPage.locator("#reportsDataSourceStatus").textContent(),
      /Registros deste navegador/,
    );
    assert.equal(await localPage.locator("#viewDemoNotice").isVisible(), false);
    await localPage.locator("[data-report-generate]").click();
    await localPage.locator("#reportGenerateForm [type=submit]").click();
    await localPage.waitForFunction(
      () => document.getElementById("reportGenerateTitle").textContent === "Relatório pronto",
    );
    assert.match(
      await localPage.locator("#reportGenerateBody").textContent(),
      /Demonstração local/,
    );
    assert.deepEqual(errors, []);
  } finally {
    await local.close();
  }
  return "Relatórios V2: fontes legítimas, comparação, animações sem replay, filtros rápidos, 12 layouts, CSV/PDF iguais ao snapshot, histórico isolado/imutável, geração local, quota/arquivo/API com falha, conta vazia e modo demonstrativo";
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
