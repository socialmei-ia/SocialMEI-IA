const assert = require("node:assert/strict");

module.exports = async function visualMotionFlows(browser, origin, errors = []) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "no-preference",
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === "/frontend/config.js")
      return route.fulfill({
        contentType: "text/javascript",
        body: "const SOCIALMEI_CONFIG = {n8nMessagesUrl:null};",
      });
    return route.continue();
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Relatórios"));
    await page.locator(".report-period-options >summary").click();
    await page.locator('[data-nv-report-period="7 dias"]').click();
    const duration = await page
      .locator("#reportPeriodIndicator")
      .evaluate((element) => getComputedStyle(element).transitionDuration);
    assert(
      duration.split(",").every((value) => parseFloat(value) === 0.24),
      "O indicador V2.1 deve usar a transição aprovada de 240ms",
    );
    assert.equal(
      await page.locator("#reportsGrid").evaluate((element) => element.getAnimations().length),
      0,
      "A página inteira não deve piscar ao atualizar o período",
    );
    assert.equal(
      await page
        .locator('[data-report-quick="7 dias"]')
        .evaluate(
          (element) =>
            element === document.activeElement && element.getAttribute("aria-pressed") === "true",
        ),
      true,
    );
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.locator('[data-report-quick="30 dias"]').click();
    assert.equal(
      await page.locator("#reportsGrid").evaluate((element) => element.getAnimations().length),
      0,
    );
    await page.locator(".skip-link").focus();
    assert.equal(
      await page.locator(".skip-link").evaluate((element) => getComputedStyle(element).clipPath),
      "none",
    );
    await page.keyboard.press("Enter");
    assert.equal(
      await page.locator("#mainContent").evaluate((element) => element === document.activeElement),
      true,
    );
    return "Motion: indicador V2.1 em 240ms, sem fade da página, foco preservado, reduced motion e skip link";
  } finally {
    await page.close();
  }
};
