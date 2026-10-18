const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const output = path.join(root, "test-results/reports-v21");
fs.mkdirSync(output, { recursive: true });
const server = http.createServer((req, res) => {
  let pathname = decodeURIComponent(new URL(req.url, "http://local").pathname);
  if (pathname.endsWith("/")) pathname += "index.html";
  const file = path.resolve(root, "." + pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
    return res.writeHead(404).end();
  res.setHeader(
    "Content-Type",
    { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2" }[
      path.extname(file)
    ] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(res);
});

(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
    args: ["--no-sandbox"],
  });
  const errors = [],
    requests = [],
    checks = [],
    layouts = [],
    contrast = [],
    performanceChecks = [];
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin || url.pathname.startsWith("/api/")) {
      requests.push(url.pathname);
      return route.abort();
    }
    return route.continue();
  });
  await page.clock.setFixedTime(new Date("2026-10-18T15:00:00Z"));
  const url = origin + "/experimental/reports-v21/";
  const settle = () =>
    page.waitForFunction(
      () =>
        document.documentElement.dataset.previewReady === "true" &&
        document.querySelector("#nvReportKpis").getAttribute("aria-busy") === "false" &&
        !window.REPORTS_PREVIEW.animating,
    );
  const shot = async (name, fullPage = true) => {
    await page.evaluate(() =>
      Promise.all(
        document
          .getAnimations()
          .filter((a) => a.effect?.getTiming().iterations !== Infinity)
          .map((a) => a.finished.catch(() => {})),
      ),
    );
    await page.screenshot({
      path: path.join(output, name + ".png"),
      fullPage,
      animations: "disabled",
    });
  };
  try {
    // Real origin data must survive both boot and prototype writes unchanged.
    await page.goto(origin + "/experimental/reports-v21/index.html?seed-check");
    await settle();
    await page.goto(origin + "/frontend/config.js");
    await page.evaluate(() =>
      localStorage.setItem("socialmei-report-history-v1:sentinel", "DO-NOT-TOUCH"),
    );
    await page.goto(url);
    await settle();
    assert.deepEqual(
      await page.evaluate(() => {
        const { onlySynthetic, storage, network } = window.REPORTS_PREVIEW;
        return { onlySynthetic, storage, network };
      }),
      { onlySynthetic: true, storage: "memory", network: "blocked" },
    );
    const baseline = await page.evaluate(() => SocialMEIReportUI.capture());
    assert.equal(baseline.current.revenue, 3045);
    assert.equal(baseline.current.count, 30);
    assert.equal(baseline.current.balance, 1560);
    assert.equal(
      baseline.sales.some((r) => r.id === 99999),
      false,
    );
    checks.push("Motor nativo: totais determinísticos, financeiro separado e excluídos ignorados");

    for (const width of [320, 390, 768, 1024, 1440]) {
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        await settle();
        await page.evaluate(() => window.scrollTo(0, 0));
        const layout = await page.evaluate(() => ({
          width: innerWidth,
          overflow: document.documentElement.scrollWidth > innerWidth,
          graphTop: document.querySelector("#resultChapter").getBoundingClientRect().top,
          tabs: [...document.querySelectorAll("#nvReportTabs button")].map((b) => ({
            label: b.textContent.trim(),
            width: b.getBoundingClientRect().width,
            right: b.getBoundingClientRect().right,
          })),
          kpis: [...document.querySelectorAll("#nvReportKpis b")].map((b) => ({
            text: b.textContent,
            clipped: b.scrollWidth > b.clientWidth + 1,
          })),
        }));
        assert(!layout.overflow, `overflow ${width}/${theme}`);
        assert(
          layout.tabs.every((t) => t.width >= 44 && t.right <= width),
          `abas legíveis ${width}/${theme}`,
        );
        assert(
          layout.kpis.every((k) => !k.clipped),
          `indicadores ${width}/${theme}`,
        );
        assert.equal(await page.locator("#nvReportTabs button").count(), 5);
        layouts.push({ ...layout, theme });
        await shot(`after-${width}-${theme}`);
      }
    }
    checks.push("10 layouts: 320/390/768/1024/1440 × claro/escuro, abas e valores sem corte");

    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.evaluate(() => SocialMEIThemes.select("light"));
    await page.evaluate(() => {
      for (const name of ["7 dias", "3 meses", "Este mês", "30 dias"])
        document.querySelector(`[data-report-quick="${name}"]`).click();
    });
    await settle();
    assert.equal(
      await page.evaluate(() => SocialMEIReportUI.capture().current.revenue),
      baseline.current.revenue,
    );
    const pathBeforeTheme = await page.locator(".rv2-line").first().getAttribute("d");
    await page.locator("#previewTheme").click();
    assert.equal(await page.locator(".rv2-line").first().getAttribute("d"), pathBeforeTheme);
    checks.push("Filtros rápidos concorrentes, valor final correto e tema sem redesenho da linha");

    for (const tab of ["Vendas", "Clientes", "Atendimento", "Financeiro", "Resumo"]) {
      await page.locator(`[data-nv-report-tab="${tab}"]`).click();
      assert.equal(
        await page
          .locator(`#nvReportTabs [aria-selected="true"]`)
          .textContent()
          .then((s) => s.trim()),
        tab,
      );
      assert(await page.locator("#reportsGrid").innerText());
    }
    const point = page.locator(".rv2-point").first();
    await point.focus();
    await page.keyboard.press("Enter");
    assert(await page.locator(".rv2-chart-tooltip").first().isVisible());
    await page.keyboard.press("Escape");
    assert(!(await page.locator(".rv2-chart-tooltip").first().isVisible()));
    checks.push("Cinco visões e tooltip por teclado com Escape");

    await page.locator(".report-period-options summary").click();
    await page.locator('[data-nv-report-period="Personalizado"]').click();
    await page.locator("#mobileDateFrom").fill("2026-10-01");
    await page.locator("#mobileDateTo").fill("2026-10-18");
    await page.locator("#mobilePeriodForm [type=submit]").click();
    await page.locator("#periodModal.open").waitFor({ state: "hidden" });
    await settle();
    assert.equal(await page.evaluate(() => periodRange().from), "2026-10-01");
    await page.locator('[data-report-quick="30 dias"]').click();
    await settle();
    checks.push("Intervalo personalizado nativo preservado");

    await page.locator("[data-report-generate]").click();
    assert(await page.locator("#app").evaluate((n) => n.inert));
    await page.keyboard.press("Tab");
    assert(
      await page
        .locator("#reportGenerateModal")
        .evaluate((n) => n.contains(document.activeElement)),
    );
    await page.keyboard.press("Shift+Tab");
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        await shot(`generate-${width}-${theme}`, false);
      }
    }
    await page.locator("#reportGenerateForm [type=submit]").click();
    await page.waitForFunction(
      () => document.querySelector("#reportGenerateTitle").textContent === "Relatório pronto",
    );
    const download = page.waitForEvent("download");
    await page.locator("#reportGenerateModal [data-report-action=csv]").click();
    const csv = fs.readFileSync(await (await download).path(), "utf8");
    assert(csv.includes("3045"));
    assert(!csv.includes("999999"));
    fs.writeFileSync(path.join(output, "sample.csv"), csv);
    await page.evaluate(() => {
      window.print = () => {};
    });
    await page.locator("#reportGenerateModal [data-report-action=print]").click();
    const pdfFile = path.join(output, "sample.pdf");
    await page.pdf({ path: pdfFile, format: "A4", printBackground: true });
    assert.equal(fs.readFileSync(pdfFile).subarray(0, 5).toString(), "%PDF-");
    const pdfText = execFileSync("pdftotext", [pdfFile, "-"], { encoding: "utf8" });
    assert(pdfText.includes("3.045,00"));
    assert(pdfText.includes("Ateliê Aurora"));
    await page.evaluate(() => document.body.classList.remove("report-print-active"));
    checks.push(
      "Geração por operações reais, CSV e PDF do mesmo snapshot, acentos e valores conferidos",
    );
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        await shot(`ready-${width}-${theme}`, false);
      }
    }
    await page.keyboard.press("Escape");
    await page.locator("#reportGenerateModal.open").waitFor({ state: "hidden" });
    assert(
      await page.locator("[data-report-generate]").evaluate((n) => n === document.activeElement),
    );
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 1);
    await page.locator("#reportHistorySearch").fill("inexistente");
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 0);
    await page.locator("#reportHistorySearch").fill("");
    await page.locator('[data-report-quick="7 dias"]').click();
    await page.locator("#reportHistoryList [data-report-action=details]").click();
    assert((await page.locator("#reportGenerateBody").innerText()).includes("3.045,00"));
    await page.keyboard.press("Escape");
    await page.locator("#reportGenerateModal.open").waitFor({ state: "hidden" });
    checks.push("Histórico pesquisável, cópia imutável e retorno de foco");
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        await page.locator(".rv2-history").scrollIntoViewIfNeeded();
        await shot(`history-${width}-${theme}`, false);
      }
    }

    await page.locator("[data-report-generate]").click();
    await page.evaluate(() => {
      document.querySelector("#reportGenerateForm").requestSubmit();
      closeModal("reportGenerateModal");
    });
    await page.locator("#reportGenerateModal.open").waitFor({ state: "hidden" });
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 1);
    assert.match(await page.locator("#previewFeedback").textContent(), /cancelada/);
    checks.push("Cancelamento impede salvar e permite nova geração");

    await page.locator("[data-report-generate]").click();
    await page.evaluate(() => {
      window.savedCSV = SocialMEIReportData.csv;
      SocialMEIReportData.csv = () => {
        throw Error("Falha sintética de exportação");
      };
    });
    await page.locator("#reportGenerateForm [type=submit]").click();
    await page.waitForFunction(
      () =>
        document.querySelector("#reportGenerateTitle").textContent === "Não foi possível concluir",
    );
    assert((await page.locator("#reportGenerateBody").textContent()).includes("Falha sintética"));
    await page.evaluate(() => {
      SocialMEIReportData.csv = window.savedCSV;
    });
    await page.keyboard.press("Escape");
    await page.locator("#reportGenerateModal.open").waitFor({ state: "hidden" });
    assert(
      (await page.locator('#reportHistoryList [data-report-action="csv"]').last().isDisabled()) ||
        (await page.locator('#reportHistoryList [data-report-action="csv"]').first().isDisabled()),
    );
    checks.push("Falha de CSV identificada e relatório com erro sem exportação");

    for (const state of ["empty", "error", "loading", "sample"]) {
      await page.locator("#previewState").selectOption(state);
      await settle();
      if (state === "empty")
        assert.equal(await page.evaluate(() => operationalMetrics().revenue), 0);
      if (["error", "loading"].includes(state))
        assert.equal(await page.locator("#nvReportKpis b").first().textContent(), "—");
      if (["empty", "error"].includes(state))
        for (const width of [1440, 390]) {
          await page.setViewportSize({ width, height: 1000 });
          for (const theme of ["light", "dark"]) {
            await page.evaluate((t) => SocialMEIThemes.select(t), theme);
            await shot(`${state}-${width}-${theme}`);
          }
        }
    }
    checks.push("Cenários vazio/erro/carregamento com fonte indisponível sem valores antigos");

    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.locator('[data-report-quick="30 dias"]').click();
    await settle();
    assert.equal(
      await page
        .locator("#reportsView")
        .evaluate(
          (n) => n.getAnimations({ subtree: true }).filter((a) => a.playState === "running").length,
        ),
      0,
    );
    checks.push("Movimento reduzido respeitado");

    for (const theme of ["light", "dark"]) {
      await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
      const ratios = await page.evaluate(() => {
        const rgb = (value) => (value.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
        const luminance = (value) =>
          rgb(value)
            .map((v) => {
              v /= 255;
              return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
            })
            .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
        return [
          "#previewFeedback",
          "[data-report-generate]",
          "#nvReportKpis .management-kpi > span",
          "#nvReportKpis .management-kpi > b",
          "#nvReportTabs [aria-selected=true]",
        ].map((selector) => {
          const node = document.querySelector(selector);
          let ancestor = node,
            background = "rgba(0, 0, 0, 0)";
          while (ancestor && background === "rgba(0, 0, 0, 0)") {
            background = getComputedStyle(ancestor).backgroundColor;
            ancestor = ancestor.parentElement;
          }
          const a = luminance(getComputedStyle(node).color),
            b = luminance(background);
          return { selector, ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) };
        });
      });
      assert(
        ratios.every((r) => r.ratio >= 4.5),
        "contraste " + theme + JSON.stringify(ratios),
      );
      contrast.push({ theme, ratios });
    }
    checks.push("Contraste de textos e ações principais ≥ 4,5:1 nos dois temas");
    await page.emulateMedia({ reducedMotion: "no-preference" });
    const cdp = await context.newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    for (const period of ["7 dias", "3 meses", "30 dias"]) {
      const start = Date.now();
      await page.locator(`[data-report-quick="${period}"]`).click();
      await settle();
      const duration = Date.now() - start;
      assert(duration < 5000, "Atualização travada sob CPU 4×");
      performanceChecks.push({ period, cpuThrottle: 4, milliseconds: duration });
    }
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
    checks.push("Troca de filtros exercitada sob limitação de CPU 4×");

    for (const width of [1440, 390])
      for (const theme of ["light", "dark"]) {
        await page.goto(url + `?view=before&theme=${theme}`);
        await settle();
        await page.setViewportSize({ width, height: 1000 });
        await settle();
        assert.equal(
          await page.evaluate(() => SocialMEIReportUI.capture().current.revenue),
          baseline.current.revenue,
        );
        await shot(`before-${width}-${theme}`);
      }
    await page.goto(url);
    await settle();
    assert.equal(await page.locator("#reportHistoryList .rv2-history-row").count(), 0);
    await page.goto(origin + "/frontend/config.js");
    assert.equal(
      await page.evaluate(() => localStorage.getItem("socialmei-report-history-v1:sentinel")),
      "DO-NOT-TOUCH",
    );
    checks.push(
      "Antes/depois com os mesmos dados; memória descartada no reload; armazenamento real intocado",
    );
    const standalone = path.join(root, "work/reports-v21/SocialMEI-Relatorios-V2.1.html");
    execFileSync(process.execPath, [
      path.join(root, "experimental/reports-v21/build-preview.cjs"),
      standalone,
    ]);
    const offline = await browser.newPage({
      viewport: { width: 390, height: 844 },
      reducedMotion: "reduce",
      acceptDownloads: true,
    });
    offline.on("pageerror", (e) => errors.push("offline: " + e.message));
    await offline.route("**/*", (route) => {
      if (route.request().url() !== origin + "/work/reports-v21/SocialMEI-Relatorios-V2.1.html") {
        requests.push("offline: " + route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    // The managed browser blocks file:// by policy. Serve the single artifact;
    // every additional resource request remains blocked by this route.
    await offline.goto(origin + "/work/reports-v21/SocialMEI-Relatorios-V2.1.html");
    await offline.waitForFunction(() => document.documentElement.dataset.previewReady === "true");
    await offline.locator("[data-report-generate]").click();
    await offline.locator("#reportGenerateForm [type=submit]").click();
    await offline.waitForFunction(
      () => document.querySelector("#reportGenerateTitle").textContent === "Relatório pronto",
    );
    await offline.close();
    checks.push(
      "HTML portátil autocontido gera relatório sem recursos adicionais; validado via HTTP local (file:// bloqueado pela política do navegador de QA)",
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(requests, []);
    fs.writeFileSync(
      path.join(output, "results.json"),
      JSON.stringify(
        { checks, layouts, contrast, performanceChecks, errors, blockedRequests: requests },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ result: "PASS", checks, layouts: layouts.length }, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
})().catch((error) => {
  console.error(error);
  server.close();
  process.exitCode = 1;
});
