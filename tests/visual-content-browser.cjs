const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async (browser, origin) => {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
    reducedMotion: "reduce",
  });
  const errors = [];
  const output = path.resolve(__dirname, "../test-results/visual-content");
  fs.mkdirSync(output, { recursive: true });
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    // V8 is visible in the public demo, but CRM writes still require authenticated backend.
    await page.evaluate(() => setView("Oportunidades"));
    assert(await page.locator("#op8Summary").isVisible());
    assert(await page.locator("#op8Create").isDisabled());
    await page.evaluate(() => setView("Início"));
    await page.locator("#contentStudioOpen").click();
    await page.locator("#contentTitle").fill("Rascunho de demonstração visual");
    assert(await page.locator("#dv4ProgressBar").isVisible());
    assert(Number(await page.locator("#dv4ProgressBar").getAttribute("aria-valuenow")) > 0);
    // The daily idea must not silently overwrite a user's existing draft.
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.getByRole("button", { name: "Usar ideia" }).click();
    assert.equal(
      await page.locator("#contentTitle").inputValue(),
      "Rascunho de demonstração visual",
    );
    await page.locator("#contentSave").click();
    await page.locator("#contentWorkspace-create").focus();
    await page.keyboard.press("End");
    assert(
      await page
        .locator("#contentWorkspace-connections")
        .evaluate((node) => document.activeElement === node),
    );
    await page.keyboard.press("Home");
    assert(await page.locator("#contentCreatePanel").isVisible());
    await page.locator("#contentFormat-story").click();
    let stage = await page.locator("#contentPreviewStage").boundingBox();
    assert(Math.abs(stage.width / stage.height - 9 / 16) < 0.01, "Story must retain 9:16 preview");
    await page.locator("#contentFormat-feed").click();
    stage = await page.locator("#contentPreviewStage").boundingBox();
    assert(Math.abs(stage.width / stage.height - 4 / 5) < 0.01, "Feed must retain 4:5 preview");
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1100 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => SocialMEIThemes.select(theme, { persist: false }), theme);
        const contrast = await page.locator("#contentNew").evaluate((button) => {
          const hex = (color) =>
            "#" +
            color
              .match(/[\d.]+/g)
              .slice(0, 3)
              .map((value) => Math.round(Number(value)).toString(16).padStart(2, "0"))
              .join("");
          const style = getComputedStyle(button);
          return SocialMEIThemes.contrast(hex(style.color), hex(style.backgroundColor));
        });
        assert(contrast >= 4.5, `primary action contrast ${theme}: ${contrast}`);
        for (const tab of ["create", "drafts", "agenda", "connections"]) {
          await page.locator("#contentWorkspace-" + tab).click();
          assert(
            await page
              .locator("#contentStudioView")
              .evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
            `overflow ${width} ${theme} ${tab}`,
          );
          for (const control of await page.locator("#contentStudioView [role=tab]").all()) {
            if (!(await control.isVisible())) continue;
            const box = await control.boundingBox();
            assert(box.height >= 44, `touch target ${width} ${tab}`);
          }
          if (width <= 390) {
            const boxes = await page
              .locator(".content-workspace-tabs > button")
              .evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().toJSON()));
            for (let a = 0; a < boxes.length; a++) {
              for (let b = a + 1; b < boxes.length; b++) {
                const first = boxes[a],
                  second = boxes[b];
                const overlap =
                  Math.min(first.right, second.right) - Math.max(first.left, second.left) > 1 &&
                  Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top) > 1;
                assert(!overlap, `overlapping navigation tabs at ${width}px`);
              }
            }
          }
          if ([390, 768, 1440].includes(width)) {
            await page.screenshot({
              path: path.join(output, `${tab}-${width}-${theme}.png`),
              fullPage: true,
            });
          }
        }
      }
    }
    await page.locator("#contentWorkspace-create").click();
    assert.equal(
      await page.locator("#contentTitle").inputValue(),
      "Rascunho de demonstração visual",
    );
    assert.deepEqual(errors, []);
    return {
      visualContent:
        "4 tabs × 5 sizes × 2 themes; keyboard; format ratios; draft retained; screenshots PASS",
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
    } finally {
      await browser?.close();
      server.close();
    }
  })().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
}
