const assert = require("node:assert/strict");

async function capturePendingInboxResize(page) {
  return page.evaluateHandle(() => {
    const nativeSetTimeout = window.setTimeout;
    let pendingResize;
    // Hold only this resize debounce so its completion can cross a user action.
    window.setTimeout = function (callback, delay, ...args) {
      if (delay === 120) {
        pendingResize = () => callback(...args);
        return nativeSetTimeout(() => {}, 0);
      }
      return nativeSetTimeout(callback, delay, ...args);
    };
    try {
      dispatchEvent(new Event("resize"));
    } finally {
      window.setTimeout = nativeSetTimeout;
    }
    if (!pendingResize) throw new Error("Inbox resize debounce was not captured");
    return pendingResize;
  });
}

module.exports = async function visualRefinementFlows(browser, origin, errors = []) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
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
  await page.clock.setFixedTime(new Date("2026-10-13T12:00:00Z"));
  try {
    await page.addInitScript((fixture) => {
      if (!localStorage.getItem("socialmei-app-data-v2"))
        localStorage.setItem("socialmei-app-data-v2", JSON.stringify(fixture));
    }, require("./fixtures/legacy-local-business.json"));
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
    await page.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
    );
    await page.locator(".overview-more summary").press("Enter");
    await page.waitForFunction(() => document.querySelector(".overview-more details")?.open);
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
    // The connection-state button must not be cropped by the toolbar at
    // intermediate widths; its complete message remains available to assistive tech.
    for (const width of [1440, 1100, 1024, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.evaluate(() => {
        setView("Caixa Unificada");
        setIntegrationStatus("Integração de mensagens não configurada", "disabled");
      });
      const layout = await page.evaluate(() => {
        const pill = document.getElementById("integrationPill");
        const label = document.getElementById("integrationStatus");
        const tools = document.querySelector("#inboxView .list-heading-tools");
        const actions = [...tools.querySelectorAll("button,select")];
        const heading = document.querySelector("#inboxView .list-heading").getBoundingClientRect();
        return {
          hidden: getComputedStyle(pill).display === "none",
          label: label.textContent,
          description: pill.getAttribute("aria-label"),
          textFits: label.scrollWidth <= label.clientWidth + 1,
          withinHeading: actions.every((element) => {
            const bounds = element.getBoundingClientRect();
            return (
              getComputedStyle(element).display === "none" ||
              (bounds.left >= heading.left - 1 && bounds.right <= heading.right + 1)
            );
          }),
        };
      });
      assert.equal(layout.label, "Não conectada");
      assert.equal(layout.description, "Integração de mensagens não configurada");
      assert.equal(layout.withinHeading, true, "Toolbar must fit at " + width + "px");
      if (width > 720) {
        assert.equal(layout.hidden, false);
        assert.equal(layout.textFits, true, "Connection button is clipped at " + width + "px");
      }
    }
    await page.setViewportSize({ width: 390, height: 900 });
    // Explicit fixture for focus and inbox interaction regression.
    await page.evaluate(() => {
      sessionData.conversas.push(structuredClone(legacySessionExamples.conversas[0]));
    });
    await page.evaluate(() => setView("Caixa Unificada"));
    const conversation = page.locator("#conversationList [data-conversation]").first();
    await conversation.click();
    await page.locator("#messageInput").fill("Rascunho preservado na navegação");
    const previousResize = await capturePendingInboxResize(page);
    await page.locator("#toggleDetailsBtn").click();
    assert.equal(await page.locator("#detailsPane").getAttribute("aria-modal"), "true");
    const missing = page.locator(".context-missing-fields summary");
    await missing.press("Enter");
    await page.waitForFunction(() => document.querySelector(".context-missing-fields")?.open);
    assert.equal(await page.locator(".context-missing-fields").getAttribute("open"), "");
    await page.evaluate(() => renderThread({ preserveScroll: true, refreshList: false }));
    assert.equal(await page.locator(".context-missing-fields").getAttribute("open"), "");
    const contextFocus = await page
      .locator(".context-missing-fields summary")
      .evaluate((element) => ({
        preserved: element === document.activeElement,
        activeTag: document.activeElement?.tagName,
        activeId: document.activeElement?.id,
        drawerOpen: document.getElementById("detailsPane").classList.contains("mobile-open"),
        inert: !!element.closest("[inert]"),
        documentState: document.readyState,
      }));
    assert.equal(
      contextFocus.preserved,
      true,
      "Inbox context focus: " + JSON.stringify(contextFocus),
    );
    await previousResize.evaluate((complete) => complete());
    await previousResize.dispose();
    assert.equal(
      await page
        .locator("#detailsPane")
        .evaluate((element) => element.classList.contains("mobile-open")),
      true,
      "A pending resize must not close a newly opened client drawer",
    );
    assert.equal(
      await missing.evaluate((element) => element === document.activeElement),
      true,
      "A pending resize must preserve focus in the newly opened client drawer",
    );
    await page.keyboard.press("Escape");
    assert.equal(
      await page
        .locator("#toggleDetailsBtn")
        .evaluate((element) => element === document.activeElement),
      true,
    );
    await page.locator("#toggleDetailsBtn").click();
    const currentResize = await capturePendingInboxResize(page);
    await currentResize.evaluate((complete) => complete());
    await currentResize.dispose();
    assert.equal(
      await page
        .locator("#detailsPane")
        .evaluate((element) => element.classList.contains("mobile-open")),
      false,
      "Resizing an already open client drawer must still close it",
    );
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
    const salesLayout = await page.evaluate(() => {
      const bottom = (selector) =>
        document.querySelector(selector)?.getBoundingClientRect().bottom ?? 0;
      return {
        workspace: bottom("#nvShell"),
        summary: bottom("#salesPremiumSummary"),
        filters: bottom("#salesSummary"),
        toolbar: bottom("#salesView .workspace-list-toolbar"),
        firstRow: document.querySelector("#salesTable tbody tr")?.getBoundingClientRect().top ?? 0,
      };
    });
    assert(
      salesLayout.firstRow < 760,
      `Vendas no mobile: topo=${salesLayout.firstRow}; workspace=${salesLayout.workspace}; resumo=${salesLayout.summary}; filtros=${salesLayout.filters}; busca=${salesLayout.toolbar}`,
    );
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
    await page.locator("[popovertarget=salesFilters]").first().click();
    await page.locator("#nvTitle").click();
    assert.equal(
      await page.locator("#salesFilters").evaluate((element) => element.matches(":popover-open")),
      false,
    );
    await page.locator("[popovertarget=salesFilters]").first().click();
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForFunction(
      () => !document.getElementById("salesFilters").hasAttribute("popover"),
    );
    assert.equal(await page.locator("#salesFilters").getAttribute("popover"), null);
    assert.equal(await page.locator("[data-nv-host=salesPaymentFilter] button").isVisible(), true);
    await page.setViewportSize({ width: 390, height: 900 });
    await page.waitForFunction(
      () => document.getElementById("salesFilters").getAttribute("popover") === "auto",
    );
    assert.equal(await page.locator("#salesFilters").getAttribute("popover"), "auto");
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
    await page.evaluate(() => setView("Produtos e Serviços"));
    await page.locator(".catalog-open-button").first().click();
    assert.equal(
      await page.locator("#recordModal").evaluate((element) => element.classList.contains("open")),
      true,
    );
    await page.keyboard.press("Escape");
    await page.locator("#nvPv").click();
    assert((await page.locator("#productsGrid table tbody tr").count()) > 0);
    await page.locator("#nvPv").click();
    await page.evaluate(() => setView("Financeiro"));
    assert.equal(
      await page.locator("#financeSummary .management-kpi").count(),
      5,
      "Preservar todos os indicadores financeiros",
    );
    const balance = await page.evaluate(() => operationalMetrics().balance);
    await page.locator("#financeSearch").fill("sem-lancamento-qa");
    await page.waitForFunction(() =>
      document
        .getElementById("financeTable")
        .textContent.includes("Nenhuma movimentação encontrada"),
    );
    assert.equal(
      await page.evaluate(() => operationalMetrics().balance),
      balance,
      "A busca não muda os cálculos",
    );
    await page.evaluate(() => {
      appData.financeiro[0].valor = 123456789012.34;
      renderFinance();
    });
    for (const amount of await page.locator("#financeSummary .management-kpi >b").all()) {
      const geometry = await amount.evaluate((element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        return {
          lines: range.getClientRects().length,
          textWidth: range.getBoundingClientRect().width,
          width: element.clientWidth,
        };
      });
      assert.equal(geometry.lines, 1, "Manter o valor monetário em uma linha");
      assert(
        geometry.textWidth <= geometry.width + 1,
        "Valores grandes devem usar a largura disponível",
      );
    }
    for (const [view, id] of [
      ["Clientes", "clientsMeta"],
      ["Vendas", "salesMeta"],
      ["Produtos e Serviços", "productsMeta"],
      ["Financeiro", "financeMeta"],
    ]) {
      await page.evaluate((name) => setView(name), view);
      const labels = await page.locator(`#${id} >span`).evaluateAll((elements) =>
        elements.map((element) => {
          const range = document.createRange();
          range.selectNodeContents(element);
          const { x, y, width, height } = range.getBoundingClientRect();
          return { x, y, width, height };
        }),
      );
      const [first, last] = labels;
      assert(
        last.y >= first.y + first.height || last.x >= first.x + first.width + 8,
        `${view}: origem e horário precisam ficar separados`,
      );
    }
    return "Refinamento: prioridades do Resumo, ação de venda, temas e Caixa com contexto, rascunho e filtros compactos de Clientes/Vendas";
  } finally {
    await page.close();
  }
};
