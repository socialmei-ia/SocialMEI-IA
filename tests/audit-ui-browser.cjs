const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const viewports = [
  [1920, 1080],
  [1440, 900],
  [1366, 768],
  [1280, 720],
  [1024, 768],
  [768, 1024],
  [430, 932],
  [390, 844],
  [360, 800],
];
const resultDirectory = path.resolve(__dirname, "../test-results/audit-ui");

async function auditedUiFlows(browser, origin) {
  fs.mkdirSync(resultDirectory, { recursive: true });
  const phase = process.env.AUDIT_UI_PHASE || "after";
  const report = { phase, tools: [], charts: [], failures: [], pageErrors: [], consoleErrors: [] };
  const page = await browser.newPage({ reducedMotion: "reduce" });
  const check = (condition, description) => {
    if (!condition) report.failures.push(description);
  };
  page.on("pageerror", (error) => report.pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning")
      report.consoleErrors.push(message.text());
  });
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    if (phase === "before") {
      const baselineFile = {
        "/frontend/styles/socialmei.css": "frontend/styles/socialmei.css",
        "/frontend/scripts/business-views.js": "frontend/scripts/business-views.js",
      }[url.pathname];
      if (baselineFile)
        return route.fulfill({
          contentType: baselineFile.endsWith(".css") ? "text/css" : "application/javascript",
          body: execFileSync(
            "git",
            ["show", "65be4880a41bec5903b7c3c896ff14da74c4f1d7:" + baselineFile],
            { cwd: path.resolve(__dirname, ".."), encoding: "utf8" },
          ),
        });
    }
    if (url.pathname.endsWith("/config.js"))
      return route.fulfill({
        contentType: "application/javascript",
        body: 'const SOCIALMEI_CONFIG=Object.freeze({n8nMessagesUrl:null,clientes:{mode:"local",apiBaseUrl:"",workspaceKey:""}});',
      });
    return route.continue();
  });
  try {
    await page.clock.setFixedTime(new Date("2026-10-12T15:00:00Z"));
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Início"));
    await page.evaluate(() => document.fonts.ready);

    for (const [width, height] of viewports) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(160);
      for (const mode of ["light", "dark", "auto-light", "auto-dark"]) {
        const theme = mode.endsWith("dark") ? "dark" : "light";
        await page.emulateMedia({ colorScheme: theme });
        await page.evaluate((mode) => setTheme(mode.startsWith("auto") ? "auto" : mode), mode);
        await page.evaluate(() => setView("Início"));
        await page.locator("#utilityTools summary").click();
        check(
          await page.locator("#utilityTools").evaluate((e) => e.open),
          `${width} ${mode}: mouse opens tools`,
        );
        const tools = await page.evaluate(() => {
          const menu = document.querySelector(".utility-menu");
          const menuStyle = getComputedStyle(menu);
          const available =
            menu.clientWidth -
            parseFloat(menuStyle.paddingLeft) -
            parseFloat(menuStyle.paddingRight);
          const buttons = ["globalSearchBtn", "themeBtn", "bell"].map((id) => {
            const e = document.getElementById(id),
              rect = e.getBoundingClientRect();
            const icon = e.querySelector("svg").getBoundingClientRect();
            const dot = e.querySelector(".notify-dot")?.getBoundingClientRect();
            const style = getComputedStyle(e);
            const contentRight =
              rect.right - parseFloat(style.paddingRight) - parseFloat(style.borderRightWidth);
            return {
              id,
              width: rect.width,
              height: rect.height,
              iconWidth: icon.width,
              indicatorAtEnd: !dot || Math.abs(dot.right - contentRight) < 1,
            };
          });
          return { available, buttons, theme: document.documentElement.dataset.theme };
        });
        report.tools.push({ width, height, mode, ...tools });
        check(tools.theme === theme, `${width} ${mode}: effective theme`);
        for (const button of tools.buttons) {
          check(
            Math.abs(button.width - tools.available) < 1,
            `${width} ${mode}: ${button.id} full width`,
          );
          check(
            button.height <= 48 && button.height >= 44,
            `${width} ${mode}: ${button.id} one-line height`,
          );
          check(button.iconWidth >= 16, `${width} ${mode}: ${button.id} icon not compressed`);
          check(button.indicatorAtEnd, `${width} ${mode}: ${button.id} indicator alignment`);
        }
        if (width === 1440 && !mode.startsWith("auto"))
          await page
            .locator(".utility-menu")
            .screenshot({ path: path.join(resultDirectory, `${phase}-tools-${mode}.png`) });
        await page.keyboard.press("Escape");
        check(
          !(await page.locator("#utilityTools").evaluate((e) => e.open)),
          `${width} ${mode}: Escape closes tools`,
        );
        await page.locator("#utilityTools summary").focus();
        await page.keyboard.press("Enter");
        check(
          await page.locator("#utilityTools").evaluate((e) => e.open),
          `${width} ${mode}: Enter opens tools`,
        );
        await page.keyboard.press("Tab");
        check(
          await page.evaluate(() => document.activeElement.id === "globalSearchBtn"),
          `${width} ${mode}: Tab reaches search`,
        );
        await page.keyboard.press("Escape");
      }

      if (process.env.AUDIT_UI_ONLY === "tools") continue;
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => setTheme(theme), theme);
        for (const period of ["Hoje", "7 dias", "30 dias", "12 meses"]) {
          for (const amounts of ["ordinary", "large"]) {
            await page.evaluate(
              ({ period, amounts }) => {
                selectedPeriod = period;
                selectedReportTab = "Resumo";
                areMoneyValuesHidden = false;
                const range = periodRange();
                const days =
                  Math.round(
                    (new Date(range.to + "T12:00:00Z") - new Date(range.from + "T12:00:00Z")) /
                      864e5,
                  ) + 1;
                appData.vendas = Array.from({ length: 7 }, (_, i) => ({
                  id: 9000 + i,
                  cliente: "Cliente QA",
                  item: "Item QA",
                  quantidade: 1,
                  data: dateShift(range.from, Math.floor((i * (days - 1)) / 6)),
                  valor:
                    i === 0
                      ? 0
                      : i === 1
                        ? 0.01
                        : amounts === "large"
                          ? 9999999999999.99
                          : 1234.56 * i,
                  status: "Pago",
                  pagamento: "Pix",
                }));
                appData.financeiro = [];
                setView("Relatórios");
                renderReports();
              },
              { period, amounts },
            );
            const chart = page.locator("#resultChapter .management-chart");
            const columns = chart.locator(".management-chart-column");
            const count = await columns.count();
            for (let index = 0; index < count; index++) {
              const column = columns.nth(index);
              await column.focus();
              const label = await column.getAttribute("aria-label");
              const geometry = await column.evaluate((e) => {
                const tooltip = e.querySelector(".management-chart-tooltip");
                const r = tooltip.getBoundingClientRect();
                const chart = e.closest(".management-chart").getBoundingClientRect();
                return {
                  scrollWidth: document.documentElement.scrollWidth,
                  clientWidth: document.documentElement.clientWidth,
                  left: r.left,
                  right: r.right,
                  chartLeft: chart.left,
                  chartRight: chart.right,
                  visible: Number(getComputedStyle(tooltip).opacity) === 1,
                  tooltipHeight: r.height,
                };
              });
              const context = `${width} ${theme} ${period} ${amounts} column ${index}`;
              check(geometry.scrollWidth <= geometry.clientWidth, `${context}: no global overflow`);
              check(
                geometry.left >= geometry.chartLeft - 1 &&
                  geometry.right <= geometry.chartRight + 1,
                `${context}: tooltip within chart`,
              );
              check(
                geometry.visible && geometry.tooltipHeight > 0,
                `${context}: keyboard tooltip visible`,
              );
              check(
                label?.includes("faturamento") && /R\$/.test(label),
                `${context}: accessible value label`,
              );
              await column.hover();
              check(
                await column
                  .locator(".management-chart-tooltip")
                  .evaluate((e) => Number(getComputedStyle(e).opacity) === 1),
                `${context}: hover tooltip visible`,
              );
              if (
                [360, 390].includes(width) &&
                period === "7 dias" &&
                amounts === "ordinary" &&
                index === count - 1
              )
                await page.locator("#resultChapter").screenshot({
                  path: path.join(resultDirectory, `${phase}-reports-${width}-${theme}.png`),
                });
              report.charts.push({ width, height, theme, period, amounts, index, ...geometry });
            }
          }
        }
      }
    }
    check(
      await page.evaluate(() => document.getAnimations().length === 0),
      "reduced motion has no running animation",
    );
    check(report.pageErrors.length === 0, "zero pageerror");
    check(report.consoleErrors.length === 0, "zero relevant console errors/warnings");
  } finally {
    await page.close();
    fs.writeFileSync(
      path.join(resultDirectory, `${phase}-summary.json`),
      JSON.stringify(report, null, 2),
    );
  }
  assert.deepEqual(
    report.failures,
    [],
    `Audited UI regressions: ${report.failures.length} failed checks. See ${phase}-summary.json.`,
  );
  return `A01/A02: ${report.tools.length} tool states and ${report.charts.length} chart columns, nine resolutions, themes, keyboard and tooltips`;
}

module.exports = auditedUiFlows;

if (require.main === module) {
  const root = path.resolve(__dirname, "..");
  const server = http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
    const file = path.resolve(root, "." + pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
      return response.writeHead(404).end();
    response.setHeader(
      "Content-Type",
      {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".png": "image/png",
        ".woff2": "font/woff2",
      }[path.extname(file)] || "application/octet-stream",
    );
    fs.createReadStream(file).pipe(response);
  });
  (async () => {
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { chromium } = require("playwright");
    let browser;
    try {
      browser = await chromium.launch(
        process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
      );
      console.log(await auditedUiFlows(browser, `http://127.0.0.1:${server.address().port}`));
    } finally {
      await browser?.close();
      await new Promise((resolve) => server.close(resolve));
    }
  })().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
