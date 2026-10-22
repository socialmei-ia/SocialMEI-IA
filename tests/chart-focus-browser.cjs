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
    await columns.first().click();
    await columns.first().click();
    assert(await tip.isHidden());
    await page.evaluate(() => {
      renderFinance();
      SocialMEIChartRefinement.update();
    });
    assert(await tip.isHidden(), "A same-data redraw must not reopen a dismissed tooltip");
    await columns.first().click();
    assert.equal(await columns.first().getAttribute("aria-pressed"), "true");
    await page.evaluate(() => {
      renderFinance();
      SocialMEIChartRefinement.update();
    });
    assert.equal(
      await columns.first().getAttribute("aria-pressed"),
      "true",
      "A chart refresh must preserve the pinned point before the second click",
    );
    await columns.first().click();
    assert(await tip.isHidden(), "Second click must dismiss the tooltip after chart replacement");
    await page.mouse.move(0, 0);
    await columns.first().focus();
    await page.keyboard.press("Escape");
    await columns.nth(1).hover();
    assert(
      await tip.isVisible(),
      "A fresh pointer movement after keyboard Escape must show the tooltip",
    );
    return "Financeiro: foco/End e ponto fixado preservados na substituição; segundo clique fecha tooltip";
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
