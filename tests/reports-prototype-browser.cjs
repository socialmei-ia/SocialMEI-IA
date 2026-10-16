const { chromium } = require("playwright");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "..");
const output = path.join(root, "test-results/reports-prototype");
fs.mkdirSync(output, { recursive: true });
const server = http.createServer((req, res) => {
  const file = path.join(root, new URL(req.url, "http://local").pathname);
  if (!fs.existsSync(file)) {
    res.writeHead(404).end();
    return;
  }
  res.setHeader(
    "Content-Type",
    file.endsWith(".css")
      ? "text/css"
      : file.endsWith(".js")
        ? "text/javascript"
        : file.endsWith(".woff2")
          ? "font/woff2"
          : "text/html",
  );
  fs.createReadStream(file).pipe(res);
});
(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}),
  });
  try {
    const page = await browser.newPage({ reducedMotion: "reduce" });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const external = [];
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.hostname === "127.0.0.1") return route.continue();
      external.push(url.origin);
      return route.abort();
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/prototypes/reports/index.html`);
    await page.evaluate(() => document.fonts.ready);
    let states = 0;
    for (const width of [320, 360, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((t) => (document.documentElement.dataset.theme = t), theme);
        for (const state of ["ready", "empty", "loading", "error"]) {
          await page.selectOption("#scenario", state);
          assert(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
            `${width}/${theme}/${state}: overflow`,
          );
          assert.equal(
            await page.locator("[data-value=orders]").textContent(),
            state === "ready" ? "32" : state === "empty" ? "0" : "—",
          );
          states++;
        }
        await page.selectOption("#scenario", "ready");
        if ([390, 1440].includes(width))
          await page.screenshot({
            path: `${output}/reports-${width}-${theme}.png`,
            fullPage: true,
          });
      }
    }
    await page.selectOption("#period", "week");
    assert.equal(await page.locator("[data-value=sales]").textContent(), "R$ 4.500,00");
    await page.locator("#privacy").click();
    assert.equal(await page.locator("[data-value=sales]").textContent(), "••••");
    assert.equal(await page.locator("#chart-table tr").count(), 0);
    assert(await page.locator("#chart").isHidden());
    await page.locator("#privacy").click();
    await page.locator("#chart-details summary").click();
    assert(await page.locator("table").isVisible());
    await page.locator("#theme").focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#theme").getAttribute("aria-pressed"), "false");
    await page.locator("#compare").check();
    assert.equal(await page.locator(".variation").count(), 4);
    for (const view of ["sales", "clients", "service", "finance"]) {
      await page.locator(`[data-report-view="${view}"]`).click();
      assert(await page.locator("#view-detail table").isVisible());
      await page.locator("#privacy").click();
      assert.equal(await page.locator("#view-detail table").count(), 0);
      assert(await page.locator("#export-report").isDisabled());
      await page.locator("#privacy").click();
    }
    await page.locator('[data-report-view="summary"]').click();
    const downloadPromise = page.waitForEvent("download");
    await page.locator("#export-report").click();
    const download = await downloadPromise;
    const csv = fs.readFileSync(await download.path(), "utf8");
    assert(csv.includes("Dados fictícios"));
    assert(csv.includes("900,00"));
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.locator("#copy-report").click();
    await page.waitForFunction(() =>
      document.querySelector("#export-status").textContent.includes("copiado"),
    );
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    assert(copied.includes("FICTÍCIO") && copied.includes("4.500,00"));
    await page.evaluate(() => {
      window.print = () => {
        window.prototypePrintRequested = true;
      };
    });
    await page.locator("#print-report").click();
    assert(await page.evaluate(() => window.prototypePrintRequested));
    await page.emulateMedia({ media: "print" });
    assert(await page.locator(".exports").isHidden());
    assert(await page.locator("#print-period").isVisible());
    assert(
      (await page.locator("#print-period").textContent()).includes("10 a 16 de outubro de 2026"),
    );
    assert.deepEqual(external, []);
    assert.deepEqual(errors, []);
    console.log(
      `${states} estados sem overflow; períodos, comparação, cinco visões, privacidade, CSV, clipboard, impressão e teclado passaram; sem erros JS. Capturas: ${output}`,
    );
  } finally {
    await browser.close();
    server.close();
  }
})().catch((e) => {
  console.error(e);
  server.close();
  process.exitCode = 1;
});
