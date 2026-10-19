const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function stabilization(browser, origin) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 1000 },
    hasTouch: true,
    reducedMotion: "reduce",
  });
  const page = await context.newPage(),
    errors = [],
    writes = [],
    measures = [];
  const output = path.resolve(__dirname, "../test-results/stabilization");
  fs.mkdirSync(output, { recursive: true });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => {
    const request = route.request();
    if (new URL(request.url()).origin !== origin) return route.abort();
    if (request.method() !== "GET") writes.push(request.method() + " " + request.url());
    return route.continue();
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    await page.evaluate(() => {
      SocialMEIDemoData.set(true);
      setView("Financeiro");
    });
    const original = await page.evaluate(() => JSON.stringify(appData));
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => {
          SocialMEIThemes.select(theme);
          setView("Financeiro");
        }, theme);
        const columns = page.locator("#financeMiniChart .management-chart-column");
        await columns.first().waitFor({ state: "visible" });
        const boxes = await columns.evaluateAll((nodes) =>
          nodes.map((node) => {
            const r = node.getBoundingClientRect();
            return { x: r.x, width: r.width, height: r.height };
          }),
        );
        assert(boxes.length > 1);
        assert(
          boxes.every((box) => box.width >= 44 && box.height >= 44),
          JSON.stringify({ width, boxes }),
        );
        for (let i = 1; i < boxes.length; i++)
          assert(boxes[i].x >= boxes[i - 1].x + boxes[i - 1].width - 0.5);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await columns.first().focus();
        await page.keyboard.press("End");
        const tip = page.locator(
          "#financeMiniChart > .management-chart > .management-chart-tooltip",
        );
        assert(await tip.isVisible());
        assert.equal(await tip.textContent(), await columns.last().getAttribute("aria-label"));
        const bounds = await tip.boundingBox();
        assert(bounds.x >= 0 && bounds.x + bounds.width <= width + 0.5);
        await page.keyboard.press("Home");
        assert(await columns.first().evaluate((node) => node === document.activeElement));
        await page.keyboard.press("ArrowRight");
        assert(await columns.nth(1).evaluate((node) => node === document.activeElement));
        await page.keyboard.press("Escape");
        assert(await tip.isHidden());
        await columns.first().tap();
        assert.equal(await columns.first().getAttribute("aria-pressed"), "true");
        assert(await tip.isVisible());
        await columns.first().tap();
        assert(await tip.isHidden());
        await columns.last().tap();
        await page.locator("#financeSummary").tap();
        assert(await tip.isHidden());
        const scroll = page.locator("#financeMiniChart .management-chart-scroll");
        assert.equal(
          await page.locator("#financeMiniChart .management-chart-scroll-hint").isVisible(),
          await scroll.evaluate((node) => node.scrollWidth > node.clientWidth + 1),
        );
        if ([390, 1440].includes(width))
          await page.screenshot({ path: path.join(output, `finance-${width}-${theme}.png`) });
        measures.push({ width, theme, minimumTarget: Math.min(...boxes.map((b) => b.width)) });
      }
    }
    assert.equal(await page.evaluate(() => JSON.stringify(appData)), original);
    assert.deepEqual(errors, []);
    assert.deepEqual(writes, []);
    fs.writeFileSync(path.join(output, "results.json"), JSON.stringify(measures, null, 2));
  } finally {
    await context.close();
  }
  return "Estabilização: gráficos financeiros e controles de Relatórios em cinco larguras/claro-escuro";
};
if (require.main === module)
  (async () => {
    const { chromium } = require("playwright");
    const browser = await chromium.launch({
      executablePath: process.env.CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
    });
    try {
      console.log(
        await module.exports(browser, process.env.TEST_ORIGIN || "http://127.0.0.1:5506"),
      );
    } finally {
      await browser.close();
    }
  })().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
