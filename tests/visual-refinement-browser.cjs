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
    await page.evaluate(() => setView("Clientes"));
    const firstCustomer = page.locator("#clientsTable tbody tr").first();
    assert((await firstCustomer.boundingBox()).y < 720, "A lista precisa aparecer cedo no celular");
    await page.locator("[popovertarget=clientsFilters]").first().focus();
    await page.keyboard.press("Enter");
    assert.equal(
      await page.locator("#clientsFilters").evaluate((element) => element.matches(":popover-open")),
      true,
    );
    const statusFilter = page.locator("[data-nv-host=clientsStatusFilter] button");
    await statusFilter.focus();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#clientsStatusFilter").inputValue(), "Ativo");
    assert.match(
      await page.locator(".business-filter-trigger[popovertarget=clientsFilters]").innerText(),
      /1/,
    );
    await page.locator("#clientsFilters .business-filter-done").click();
    assert.equal(
      await page.locator("#clientsFilters").evaluate((element) => element.matches(":popover-open")),
      false,
    );
    await page.evaluate(() => setView("Vendas"));
    assert((await page.locator("#salesTable tbody tr").first().boundingBox()).y < 760);
    for (const table of ["clientsTable", "salesTable"]) {
      await page.evaluate(
        (name) => setView(name),
        table === "clientsTable" ? "Clientes" : "Vendas",
      );
      const cells = await page
        .locator(`#${table} tbody tr`)
        .first()
        .locator("td")
        .evaluateAll((elements) =>
          elements.map((element) => {
            const { x, y, width, height } = element.getBoundingClientRect();
            return { x, y, width, height };
          }),
        );
      for (let i = 0; i < cells.length; i++)
        for (let j = i + 1; j < cells.length; j++) {
          const a = cells[i],
            b = cells[j];
          assert(
            !(
              a.x < b.x + b.width - 1 &&
              a.x + a.width > b.x + 1 &&
              a.y < b.y + b.height - 1 &&
              a.y + a.height > b.y + 1
            ),
            `${table}: campos ${i}/${j} sobrepostos`,
          );
        }
    }
    await page.locator("[popovertarget=salesFilters]").first().click();
    await page.keyboard.press("Escape");
    assert.equal(
      await page.locator("#salesFilters").evaluate((element) => element.matches(":popover-open")),
      false,
    );
    assert.equal(
      await page
        .locator(".business-filter-trigger[popovertarget=salesFilters]")
        .evaluate((element) => element === document.activeElement),
      true,
    );
    await page.locator("#salesSearch").fill("nenhum-resultado-qa");
    await page.waitForFunction(() =>
      document.getElementById("salesTable").textContent.includes("Nenhuma venda encontrada"),
    );
    assert.match(await page.locator("#salesTable").innerText(), /Nenhuma venda encontrada/);
    await page.locator("#salesSearch").fill("");
    await page.waitForFunction(() => document.querySelector("#salesTable tbody tr"));
    assert((await page.locator("#salesTable tbody tr").count()) > 0);
    await page.evaluate(() => setView("Assistente"));
    if (!(await page.locator("[data-ai-conversation]").first().isVisible()))
      await page.locator("[data-as-back]").click();
    await page.locator("[data-ai-conversation]").first().click();
    await page.locator("[data-ai-intent=reply]").click();
    await page.locator("[data-ai-prepare]").first().click();
    await page.waitForFunction(() => document.querySelector("#asDraftPanel"));
    assert(
      (await page.locator(".assistant-draft-text").boundingBox()).width >= 300,
      "O rascunho deve aproveitar a largura do celular",
    );
    assert.equal(
      await page
        .locator("#asDraftHeading")
        .evaluate((element) => element === document.activeElement),
      true,
    );
    const draft = await page.locator(".assistant-draft-text").innerText();
    assert(draft.length > 10);
    const messageCount = await page.evaluate(() => sessionData.conversas[0].mensagens.length);
    await page.locator("[data-ai-insert]").click();
    assert.equal(
      await page.locator(".page-view.active").getAttribute("data-view"),
      "Caixa Unificada",
    );
    assert.equal(
      await page.locator("#messageInput").inputValue(),
      "Rascunho preservado na navegação\n\n" + draft,
    );
    assert.equal(
      await page.evaluate(() => sessionData.conversas[0].mensagens.length),
      messageCount,
    );
    await page.evaluate(() => setView("Automações"));
    const libraryTop = (await page.locator("#automationLibrary").boundingBox()).y;
    assert(libraryTop < (await page.locator("#automationFeature").boundingBox()).y);
    assert.equal(await page.locator("#nvRuleModelsDisclosure").getAttribute("open"), null);
    await page.locator("#nvRuleSearch").fill("sem-rotina-qa");
    await page.waitForFunction(() => !document.querySelector("#automationList tbody tr"));
    await page.locator("#nvRuleSearch").fill("");
    await page.waitForFunction(() => document.querySelector("#automationList tbody tr"));
    await page.locator("#nvRuleModelsDisclosure >summary").focus();
    await page.keyboard.press("Enter");
    await page.locator("[data-rule-model]").first().click();
    assert.equal(
      await page
        .locator("#automationModal")
        .evaluate((element) => element.classList.contains("open")),
      true,
    );
    await page.keyboard.press("Escape");
    await page.locator("#automationFeature [data-rule-test]").click();
    assert.match(await page.locator("#nvManagementDrawerTitle").innerText(), /simulado/);
    await page.keyboard.press("Escape");
    return "Refinamento: prioridades do Resumo, ação de venda, temas e Caixa com contexto, rascunho e filtros compactos de Clientes/Vendas";
  } finally {
    await page.close();
  }
};
