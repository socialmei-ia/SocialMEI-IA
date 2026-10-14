const assert = require("node:assert/strict");

module.exports = async function visualRefinementFlows(browser, origin, errors = []) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
  );
  await page.clock.setFixedTime(new Date("2026-10-13T12:00:00Z"));
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Visão Geral"));
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => {
          setTheme(theme);
          setView("Visão Geral");
        }, theme);
        const order = await page.evaluate(() => ({
          attention: document.getElementById("attentionList").getBoundingClientRect().top,
          metrics: document.getElementById("kp").getBoundingClientRect().top,
          count: document.getElementById("overviewAttentionCount").textContent,
          overflow: document.documentElement.scrollWidth > innerWidth + 1,
        }));
        assert(order.attention < order.metrics, "As prioridades devem preceder os indicadores");
        assert.match(order.count, /cuidados|Em dia/);
        assert.equal(order.overflow, false);
      }
    }
    await page.locator(".overview-more summary").focus();
    await page.keyboard.press("Enter");
    const salesAction = page.locator("#attentionList [data-record-open=sales]").first();
    await salesAction.click();
    assert.equal(
      await page.locator("#recordModal").evaluate((element) => element.classList.contains("open")),
      true,
    );
    await page.keyboard.press("Escape");
    assert.equal(
      await page.locator("#recordModal").evaluate((element) => element.classList.contains("open")),
      false,
    );
    await page.evaluate(() => setView("Caixa Unificada"));
    const conversation = page.locator("#conversationList [data-conversation]").first();
    await conversation.click();
    await page.locator("#messageInput").fill("Rascunho preservado na navegação");
    await page.locator("#toggleDetailsBtn").click();
    assert.equal(await page.locator("#detailsPane").getAttribute("aria-modal"), "true");
    const missing = page.locator(".context-missing-fields summary");
    await missing.focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator(".context-missing-fields").getAttribute("open"), "");
    await page.keyboard.press("Escape");
    assert.equal(
      await page
        .locator("#toggleDetailsBtn")
        .evaluate((element) => element === document.activeElement),
      true,
    );
    await page.locator("#mobileBack").click();
    await page.locator("#conversationList [data-conversation]").first().click();
    assert.equal(
      await page.locator("#messageInput").inputValue(),
      "Rascunho preservado na navegação",
    );
    return "Refinamento: prioridades do Resumo, ação de venda, temas e Caixa com contexto e rascunho preservado";
  } finally {
    await page.close();
  }
};
