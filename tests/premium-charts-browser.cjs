const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function premiumCharts(browser, origin) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
    hasTouch: true,
  });
  const page = await context.newPage(),
    errors = [],
    writes = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.clock.setFixedTime(new Date("2026-10-18T15:00:00Z"));
  const sales = Array.from({ length: 45 }, (_, i) => ({
    id: 100 + i,
    versao: 1,
    cliente_id: 1,
    cliente: "Pessoa de QA",
    item: "Serviço de QA",
    quantidade: 1,
    valor: [0, 75, 15, 220, 40, 90, 10][i % 7],
    data: new Date(Date.UTC(2026, 9, 18 - i)).toISOString().slice(0, 10),
    status: "Pago",
    pagamento: "Pix",
  }));
  const finance = sales.map((sale, i) => ({
    id: 500 + i,
    versao: 1,
    tipo: i % 3 ? "receita" : "despesa",
    descricao: "Registro de QA",
    pessoa: "",
    valor: i % 3 ? 100 : 30,
    vencimento: sale.data,
    status: "pago",
  }));
  await page.route("**/*", (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (request.method() !== "GET") writes.push(request.method() + " " + url.pathname);
    if (url.pathname.endsWith("/config.js"))
      return route.fulfill({
        contentType: "text/javascript",
        body: 'const source={mode:"remote",apiBaseUrl:"/api/v1",workspaceKey:"premium-charts-qa"};const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"},clientes:source,produtos:source,vendas:source,financeiro:source};',
      });
    if (url.pathname === "/api/v1/auth/session")
      return route.fulfill({
        json: {
          usuario: {
            id: 1,
            nome: "Pessoa de QA",
            email: "qa@example.invalid",
            telefone: "11999998888",
          },
          negocio: { id: 1, slug: "charts-qa", nome: "Negócio de QA", configuracao: {} },
          papel: "owner",
          csrf_token: "a".repeat(64),
        },
      });
    if (url.pathname === "/api/v1/auth/registration")
      return route.fulfill({ json: { mode: "open" } });
    if (url.pathname.startsWith("/api/v1/"))
      return route.fulfill({
        json:
          {
            clientes: [{ id: 1, versao: 1, nome: "Pessoa de QA", tags: [] }],
            produtos: [],
            vendas: sales,
            financeiro: finance,
          }[url.pathname.slice(8)] || [],
      });
    return route.continue();
  });
  const output = path.join(root, "test-results/premium-charts");
  fs.mkdirSync(output, { recursive: true });
  const settle = () =>
    page.waitForFunction(
      () =>
        !document.querySelector('#reportsView [data-motion-state="updating"]') &&
        document.querySelector("#nvReportKpis")?.getAttribute("aria-busy") === "false",
    );
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current &&
        document.body.classList.contains("experience-app") &&
        SocialMEISales.connectionState === "ready" &&
        SocialMEIFinance.connectionState === "ready",
    );
    await page.evaluate(() => setView("Relatórios"));
    await page.locator('[data-report-quick="30 dias"]').click();
    await settle();
    const source = await page.evaluate(() => JSON.stringify(appData));
    const csv = await page.evaluate(() => SocialMEIReportData.csv(SocialMEIReportUI.capture()));
    const chart = page.locator("#resultChapter .rv2-trend");
    assert.match(await chart.locator(".rv2-line").getAttribute("d"), / C/);
    // Native focus and keyboard values remain usable while the line morphs.
    await chart.locator(".rv2-point").first().focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(
      await chart.locator('.rv2-point[data-active="true"]').getAttribute("data-index"),
      "1",
    );
    assert(await chart.locator(".rv2-chart-tooltip").isVisible());
    assert.equal(
      await chart.locator(".rv2-chart-tooltip").textContent(),
      await chart.locator('.rv2-point[data-active="true"]').getAttribute("aria-label"),
    );
    await page.keyboard.press("Escape");
    assert(await chart.locator(".rv2-chart-tooltip").isHidden());
    await page.keyboard.press("End");
    assert.equal(
      await chart.locator('.rv2-point[data-active="true"]').getAttribute("data-index"),
      String((await chart.locator(".rv2-point").count()) - 1),
    );
    await page.evaluate(() => renderReports());
    assert(
      await chart
        .locator(".rv2-point")
        .last()
        .evaluate((node) => node === document.activeElement),
    );
    await page.locator('[data-report-quick="7 dias"]').click();
    await page.waitForTimeout(65);
    const interrupted = await page.evaluate(() => {
      const current = document.querySelector("#resultChapter .rv2-trend");
      const old = [...current.querySelectorAll(".rv2-point circle")].map((point) => [
        Number(point.getAttribute("cx")),
        Number(point.getAttribute("cy")),
      ]);
      selectedPeriod = "30 dias";
      renderReports();
      const next = document.querySelector("#resultChapter .rv2-trend");
      const actual = [...next.querySelectorAll(".rv2-point circle")].map((point) => [
        Number(point.getAttribute("cx")),
        Number(point.getAttribute("cy")),
      ]);
      const error = Math.max(
        ...actual.flatMap((point, i) => {
          const position = actual.length === 1 ? 0 : (i / (actual.length - 1)) * (old.length - 1);
          const low = Math.floor(position),
            high = Math.min(old.length - 1, low + 1);
          return point.map((value, axis) =>
            Math.abs(
              value - (old[low][axis] + (old[high][axis] - old[low][axis]) * (position - low)),
            ),
          );
        }),
      );
      return { error, updating: next.dataset.motionState };
    });
    assert(interrupted.error < 0.01, JSON.stringify(interrupted));
    assert.equal(interrupted.updating, "updating");
    // Repeated discovery does not restart or freeze the current transition.
    await page.evaluate(() => {
      SocialMEIReportMotion.update();
      SocialMEIReportMotion.update();
    });
    await settle();
    assert(
      await page.evaluate(() =>
        [...document.querySelectorAll("#reportsView .rv2-line")].every(
          (line) =>
            line.getAttribute("d") === SocialMEIReportMotion.draw(JSON.parse(line.dataset.points)),
        ),
      ),
    );
    const replay = await page.evaluate(() => {
      renderReports();
      SocialMEIReportMotion.update();
      return document
        .querySelector("#resultChapter .rv2-trend")
        .getAnimations({ subtree: true })
        .filter((animation) =>
          animation.effect
            ?.getKeyframes()
            .some((keyframe) => keyframe.strokeDashoffset !== undefined),
        ).length;
    });
    assert.equal(replay, 0, "The same series must not replay its line reveal");
    await chart.locator(".rv2-point").first().hover();
    assert(await chart.locator(".rv2-chart-tooltip").isVisible());
    await page.screenshot({
      path: path.join(output, "report-tooltip-desktop.png"),
      animations: "disabled",
    });
    await page.evaluate(() => SocialMEIThemes.select("dark"));
    await chart.locator(".rv2-point").first().focus();
    assert(await chart.locator(".rv2-chart-tooltip").isVisible());
    await page.screenshot({
      path: path.join(output, "report-tooltip-desktop-dark.png"),
      animations: "disabled",
    });
    await page.evaluate(() => SocialMEIThemes.select("light"));
    // A source change starts with its own geometry; it never morphs real values into demo values.
    const sourceSwap = await page.evaluate(() => {
      SocialMEIDemoData.set(true);
      renderReports();
      const demo = document.querySelector("#resultChapter .rv2-trend");
      const demoSettled = demo?.dataset.motionState !== "updating";
      SocialMEIDemoData.set(false);
      renderReports();
      const real = document.querySelector("#resultChapter .rv2-trend");
      return demoSettled && real?.dataset.motionState !== "updating";
    });
    assert(sourceSwap);
    await settle();
    // Native bar renderer, controlled values, real animation frames and rectangles.
    const mountBars = (value) =>
      page.evaluate((value) => {
        let host = document.getElementById("premiumChartFixture");
        if (!host) {
          host = document.createElement("section");
          host.id = "premiumChartFixture";
          document.getElementById("mainContent").append(host);
        }
        host.innerHTML = renderManagementChart({
          source: "sales",
          labels: ["A", "B"],
          r: [value, 100],
          d: [0, 0],
        });
        SocialMEIChartRefinement.update();
      }, value);
    await mountBars(100);
    await page.waitForTimeout(450);
    await mountBars(10);
    await page.waitForTimeout(65);
    const bars = await page.evaluate(() => {
      const host = document.getElementById("premiumChartFixture"),
        old = host.querySelector("i").getBoundingClientRect().height;
      host.innerHTML = renderManagementChart({
        source: "sales",
        labels: ["A", "B"],
        r: [70, 100],
        d: [0, 0],
      });
      SocialMEIChartRefinement.update();
      const current = host.querySelector("i").getBoundingClientRect().height;
      return { old, current, transform: host.querySelector("i").style.transform };
    });
    assert(Math.abs(bars.old - bars.current) < 0.1, JSON.stringify(bars));
    assert.match(bars.transform, /scaleY/);
    await page.waitForTimeout(450);
    const sameBars = await page.evaluate(() => {
      const host = document.getElementById("premiumChartFixture");
      host.innerHTML = renderManagementChart({
        source: "sales",
        labels: ["A", "B"],
        r: [70, 100],
        d: [0, 0],
      });
      SocialMEIChartRefinement.update();
      return host.querySelector("i").style.transform;
    });
    assert.equal(sameBars, "");
    await page.locator("#premiumChartFixture .management-chart-column").first().focus();
    await mountBars(70);
    assert(
      await page
        .locator("#premiumChartFixture .management-chart-column")
        .first()
        .evaluate((node) => node === document.activeElement),
    );
    await mountBars(0);
    await page.waitForTimeout(450);
    assert.equal(
      await page
        .locator("#premiumChartFixture i")
        .first()
        .evaluate((node) => node.getBoundingClientRect().height),
      0,
    );
    await mountBars(100);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.waitForFunction(
      () => document.querySelector("#premiumChartFixture i").style.transform === "",
    );
    // Horizontal native status segments use the same interruption principle.
    await page.emulateMedia({ reducedMotion: "no-preference" });
    const mountSegment = (value) =>
      page.evaluate((value) => {
        let host = document.getElementById("premiumSegmentFixture");
        if (!host) {
          host = document.createElement("div");
          host.id = "premiumSegmentFixture";
          host.className = "rv2-stacked";
          host.style.width = "300px";
          document.getElementById("reportsView").append(host);
        }
        host.innerHTML = `<span data-report-bar="qa-segment" data-value="${value}" style="width:${value}%;background:var(--brand-primary)"></span>`;
        SocialMEIReportMotion.updateBars();
      }, value);
    await mountSegment(90);
    await page.waitForTimeout(450);
    await mountSegment(10);
    await page.waitForTimeout(65);
    const segmentError = await page.evaluate(() => {
      const host = document.getElementById("premiumSegmentFixture"),
        previous = host.firstElementChild.getBoundingClientRect().width;
      host.innerHTML =
        '<span data-report-bar="qa-segment" data-value="70" style="width:70%;background:var(--brand-primary)"></span>';
      SocialMEIReportMotion.updateBars();
      return Math.abs(previous - host.firstElementChild.getBoundingClientRect().width);
    });
    assert(segmentError < 0.1);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.locator('[data-report-quick="7 dias"]').click();
    await settle();
    assert.equal(
      await page.evaluate(
        () =>
          document
            .querySelector("#reportsView")
            .getAnimations({ subtree: true })
            .filter((animation) => animation.playState === "running").length,
      ),
      0,
    );
    await chart
      .locator(".rv2-point")
      .first()
      .dispatchEvent("pointerenter", { pointerType: "touch" });
    await chart.locator(".rv2-point").first().tap();
    assert(await chart.locator(".rv2-chart-tooltip").isVisible());
    await page.screenshot({
      path: path.join(output, "report-tooltip-mobile-reduced.png"),
      animations: "disabled",
    });
    const tipBox = await chart.locator(".rv2-chart-tooltip").boundingBox();
    assert(tipBox.x >= 0 && tipBox.x + tipBox.width <= 390);
    await chart.locator(".rv2-point").first().tap();
    assert(
      await chart.locator(".rv2-chart-tooltip").isHidden(),
      "A second touch dismisses the tooltip",
    );
    await chart.locator(".rv2-point").first().tap();
    await page.locator("#reportsView h2").first().tap();
    assert(
      await chart.locator(".rv2-chart-tooltip").isHidden(),
      "An outside touch dismisses the tooltip",
    );
    await page.locator('[data-nv-report-tab="Financeiro"]').click();
    const financeChart = page.locator('#reportsView .rv2-trend[data-source="finance"]');
    await financeChart.locator(".rv2-point").first().tap();
    assert.equal(await financeChart.locator(".rv2-line").count(), 2);
    assert.equal(await financeChart.locator('.rv2-secondary-point[data-active="true"]').count(), 1);
    assert.match(await financeChart.locator(".rv2-chart-tooltip").textContent(), /entrou.*saiu/);
    await page.screenshot({
      path: path.join(output, "finance-two-series-mobile.png"),
      animations: "disabled",
    });
    await page.locator('[data-nv-report-tab="Resumo"]').click();
    await page.locator('[data-report-quick="30 dias"]').click();
    await settle();
    assert.equal(await page.evaluate(() => JSON.stringify(appData)), source);
    assert.equal(
      await page.evaluate(() => SocialMEIReportData.csv(SocialMEIReportUI.capture())),
      csv,
    );
    assert.deepEqual(writes, []);
    assert.deepEqual(errors, []);
    const result = {
      chromium: browser.version(),
      monotone: true,
      rapidMorphError: interrupted.error,
      rapidBarError: Math.abs(bars.old - bars.current),
      rapidSegmentError: segmentError,
      keyboardFocus: true,
      touchDismiss: true,
      secondaryFinancePoints: true,
      isolatedSourceGeometry: sourceSwap,
      reducedMotion: true,
      sourceAndCsvUnchanged: true,
      errors,
      writes,
    };
    fs.writeFileSync(path.join(output, "results.json"), JSON.stringify(result, null, 2));
    return result;
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
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
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
