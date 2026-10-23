const { revealContentControl, contentDock } = require("./content-test-ui.cjs");
const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  const page = await browser.newPage({
      viewport: { width: 1280, height: 900 },
      reducedMotion: "reduce",
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    await page.route("**/*", (r) =>
      new URL(r.request().url()).origin === origin ? r.continue() : r.abort(),
    );
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    await page.locator("#contentStudioOpen").click();
    assert.equal(await page.evaluate(() => currentView), "Divulgação");
    assert.equal(await page.locator("#contentStudioOpen").getAttribute("aria-current"), "page");
    await revealContentControl(page, "#contentTitle");
    await page.locator("#contentTitle").fill("Conteúdo preservado");
    await revealContentControl(page, "#contentSave");
    await page.locator("#contentSave").click();
    await contentDock(page, "drafts");
    await page.locator('[data-content-action="edit"]').click();
    assert(await page.locator("#contentCreatePanel").isVisible());
    assert.equal(await page.locator("#contentTitle").inputValue(), "Conteúdo preservado");
    await page.locator("#contentWorkspace-create").focus();
    await page.keyboard.press("End");
    assert(await page.locator("#contentConnectionsPanel").isVisible());
    assert(await page.locator("#integrationSetupSave").isDisabled());
    assert.match(await page.locator("#integrationSetupPanel").textContent(), /Não conectado/);
    for (const width of [320, 390, 1280])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 900 });
        await page.evaluate((theme) => (document.documentElement.dataset.theme = theme), theme);
        if (width < 900) {
          await page.locator("#mb").click();
          await page.locator("#contentStudioOpen").click();
        }
        await contentDock(page, "agenda");
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
          true,
        );
        assert(await page.locator("#exactV4-strip").isVisible());
        assert.equal(await page.locator("#exactV4-strip .dy").count(), 14);
        await page.locator("#exactV4-strip .dy").nth(1).click();
        assert.equal(
          await page.locator("#contentAgendaDay").inputValue(),
          await page.locator("#exactV4-strip .dy").nth(1).getAttribute("data-d"),
        );
      }
    assert.deepEqual(errors, []);
    return {
      contentWorkspace:
        "sidebar, tabs/keyboard, draft editing, local connections readonly, mobile/light/dark PASS",
    };
  } finally {
    await page.close();
  }
};
if (require.main === module) {
  const fs = require("node:fs"),
    path = require("node:path"),
    http = require("node:http"),
    { chromium } = require("playwright");
  const root = path.resolve(__dirname, "..");
  const server = http.createServer((req, res) => {
    const file = path.join(root, new URL(req.url, "http://localhost").pathname);
    if (!fs.existsSync(file)) {
      res.writeHead(404).end();
      return;
    }
    res.setHeader(
      "Content-Type",
      file.endsWith(".js")
        ? "application/javascript"
        : file.endsWith(".css")
          ? "text/css"
          : file.endsWith(".html")
            ? "text/html"
            : "application/octet-stream",
    );
    fs.createReadStream(file).pipe(res);
  });
  (async () => {
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    let browser;
    try {
      browser = await chromium.launch(
        process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
      );
      console.log(await module.exports(browser, "http://127.0.0.1:" + server.address().port));
      console.log(
        await require("./integration-setup-browser.cjs")(
          browser,
          "http://127.0.0.1:" + server.address().port,
        ),
      );
    } finally {
      await browser?.close();
      server.close();
    }
  })().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
}
