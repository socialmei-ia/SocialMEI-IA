// Owner-approved V25 entry composition, local demonstration only.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function (browser, origin) {
  const out = path.join(__dirname, "../test-results/v25-entry");
  fs.mkdirSync(out, { recursive: true });
  for (const width of [1440, 768, 390])
    for (const theme of ["light", "dark"]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        colorScheme: theme,
      });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await page.route("**/*", (route) => {
        const url = new URL(route.request().url());
        if (url.origin !== origin) return route.abort();
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"local"}};',
          });
        return route.continue();
      });
      try {
        await page.goto(origin + "/frontend/entrada.html");
        const combo = page.locator(".rs-b");
        await combo.waitFor();
        await combo.focus();
        await page.keyboard.press("ArrowDown");
        await page.keyboard.press("ArrowDown");
        await page.keyboard.press("Enter");
        assert.equal(await combo.getAttribute("aria-expanded"), "false");
        assert.equal(
          await combo.locator(".rs-v").innerText(),
          await page.locator("#ramo option:checked").innerText(),
        );
        for (const route of ["", "entrar", "recuperar"]) {
          await page.goto(origin + "/frontend/entrada.html#/" + route);
          await page.evaluate(() => document.fonts.ready);
          if (route) await page.locator(route === "entrar" ? "#eMailL" : "#rMail").waitFor();
          assert(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
            "V25 entry must fit viewport",
          );
          await page.evaluate(
            () =>
              new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          await page.screenshot({
            animations: "disabled",
            path: path.join(out, `${route || "landing"}-${width}-${theme}.png`),
            fullPage: true,
          });
        }
        assert.deepEqual(errors, []);
      } finally {
        await context.close();
      }
    }
  console.log(
    "V25 entry: original selector, keyboard, landing/login/recovery at 3 widths and 2 themes passed.",
  );
};
