// A paint-delayed chart refresh must not leave the next keyboard event on body.
const assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path");
module.exports = async function chartFocus(browser, origin) {
  const page = await browser.newPage({
    reducedMotion: "reduce",
    viewport: { width: 390, height: 960 },
  });
  await page.route("**/*", (r) =>
    new URL(r.request().url()).origin === origin ? r.continue() : r.abort(),
  );
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => {
      SocialMEIExperience.enterApp("Financeiro");
      SocialMEIDemoData.set(true);
      setView("Financeiro");
    });
    const columns = page.locator("#financeMiniChart .management-chart-column");
    await columns.first().focus();
    await page.evaluate(() => {
      window.qaOriginalRAF = requestAnimationFrame;
      window.qaDeferredFrames = [];
      window.requestAnimationFrame = (callback) => {
        qaDeferredFrames.push(callback);
        return qaDeferredFrames.length;
      };
      renderFinance();
    });
    await page.keyboard.press("End");
    assert.equal(
      await columns.last().evaluate((e) => e === document.activeElement),
      true,
      "Chart focus must survive replacement before the next paint",
    );
    const tip = page.locator("#financeMiniChart > .management-chart > .management-chart-tooltip");
    assert(await tip.isVisible());
    assert.equal(await tip.textContent(), await columns.last().getAttribute("aria-label"));
    const output = path.resolve(__dirname, "../test-results/functional-audit");
    fs.mkdirSync(output, { recursive: true });
    await page.screenshot({ path: path.join(output, "chart-focus-390.png") });
    await page.keyboard.press("Escape");
    assert(await tip.isHidden());
    return "Financeiro: foco e End preservados quando a atualização precede o próximo frame";
  } finally {
    await page
      .evaluate(() => {
        if (window.qaOriginalRAF) {
          window.requestAnimationFrame = qaOriginalRAF;
          for (const cb of qaDeferredFrames) qaOriginalRAF(cb);
        }
      })
      .catch(() => {});
    await page.close();
  }
};
