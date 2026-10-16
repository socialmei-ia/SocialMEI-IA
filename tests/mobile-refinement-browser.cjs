const assert = require("node:assert/strict");
module.exports = async function mobileRefinementFlows(browser, origin) {
  const errors = [];
  const page = await browser.newPage({ reducedMotion: "reduce" });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === "/frontend/config.js")
      return route.fulfill({
        contentType: "text/javascript",
        body: "const SOCIALMEI_CONFIG={n8nMessagesUrl:null};",
      });
    return route.continue();
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Automações"));
    for (const width of [320, 360, 390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => {
          setTheme(theme);
          setView("Automações");
        }, theme);
        const row = page.locator("#automationList tbody tr").first();
        if (width < 720) {
          const fields = await page.locator("#automationList tbody td").evaluateAll((cells) =>
            cells.map((cell) => {
              const style = getComputedStyle(cell),
                before = getComputedStyle(cell, "::before");
              const rect = cell.getBoundingClientRect();
              return {
                label: cell.dataset.l,
                width: rect.width,
                height: rect.height,
                whiteSpace: before.whiteSpace,
                contentWidth:
                  cell.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
              };
            }),
          );
          for (const field of fields) {
            assert(
              field.width >= 220,
              `${width}/${theme}: ${field.label} comprimido em ${field.width}px`,
            );
            assert(
              field.height < 110,
              `${width}/${theme}: ${field.label} fragmentado em ${field.height}px de altura`,
            );
            if (!["Rotina", "Ações"].includes(field.label))
              assert.equal(
                field.whiteSpace,
                "nowrap",
                `${field.label}: rótulo deve permanecer inteiro`,
              );
          }
          const name = await row.locator("[data-rule-focus]").boundingBox();
          assert(
            name.width > 150 && name.height >= 44,
            "Nome da rotina deve ter área legível e clicável",
          );
        } else {
          assert(await page.locator("#automationList thead").isVisible());
        }
        assert(
          !/\bAtiva\b/.test(await row.textContent()),
          "Habilitação não deve parecer execução externa",
        );
        const toggle = row.locator("[data-rule-toggle]");
        const id = await toggle.getAttribute("data-rule-toggle");
        const initial = await toggle.getAttribute("aria-checked");
        await toggle.click();
        assert.equal(
          await page.locator(`[data-rule-toggle="${id}"]`).getAttribute("aria-checked"),
          String(initial !== "true"),
        );
        await page.locator(`[data-rule-toggle="${id}"]`).click();
        await row.locator("[data-rule-edit]").click();
        assert(await page.locator("#automationModal.open").isVisible());
        await page.keyboard.press("Escape");
        await page.evaluate(() => setView("Relatórios"));
        const tabs = await page.locator("#nvReportTabs button").evaluateAll((buttons) =>
          buttons.map((button) => {
            const rect = button.getBoundingClientRect();
            return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
          }),
        );
        assert.equal(tabs.length, 5);
        for (const tab of tabs)
          assert(
            tab.left >= 0 && tab.right <= width,
            `${width}/${theme}: aba parcialmente fora da tela`,
          );
        await page.getByRole("tab", { name: "Financeiro", exact: true }).focus();
        await page.keyboard.press("Home");
        assert.equal(
          await page
            .getByRole("tab", { name: "Resumo", exact: true })
            .getAttribute("aria-selected"),
          "true",
        );
        await page.locator(".report-period-options summary").click();
        assert.equal(await page.locator("#nvReportPeriods button").count(), 8);
        await page.locator('[data-nv-report-period="7 dias"]').click();
        assert.equal(await page.locator("#reportPeriodChoice").textContent(), "7 dias");
        await page.locator("#nvReportCompare").uncheck();
        await page.locator("#nvReportCompare").check();
        await page.locator(".report-period-options summary").click();
        await page.locator("#reportsView [data-nv-hide]").click();
        await page.locator("#reportsView [data-nv-hide]").click();
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      }
    }
    await page.goto(origin + "/prototypes/onboarding/index.html");
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.locator("#other").check();
    await page.locator("#next").click();
    assert(await page.locator("#products").isChecked());
    assert(await page.locator("#services").isChecked());
    assert(!(await page.locator("#stock").isChecked()));
    await page.locator("#next").click();
    const config = JSON.parse(await page.locator("#config-preview").textContent());
    assert.equal(config.businessProfile, "other");
    assert.equal(config.demo, true);
    assert.equal(config.integrationsEnabled, false);
    assert.equal(await page.locator(".steps li").count(), 3);
    assert.deepEqual(errors, []);
    return "Automações e Relatórios: oito layouts com rótulos legíveis, ações/edição, cinco abas visíveis, períodos, comparação, privacidade e teclado";
  } finally {
    await page.close();
  }
};
