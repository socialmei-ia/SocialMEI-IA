// Issue #76: official app, empty/local sample states, no external transport.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function functionalAudit(browser, origin) {
  const context = await browser.newContext({ reducedMotion: "reduce", locale: "pt-BR" });
  const page = await context.newPage(),
    errors = [],
    external = [],
    writes = [],
    states = [];
  const output = path.resolve(__dirname, "../test-results/functional-audit");
  fs.mkdirSync(output, { recursive: true });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (route) => {
    const req = route.request(),
      url = new URL(req.url());
    if (url.origin !== origin) {
      external.push(url.origin);
      return route.abort();
    }
    if (req.method() !== "GET") writes.push({ path: url.pathname, method: req.method() });
    return route.continue();
  });
  const views = [
    "Início",
    "Clientes",
    "Produtos e Serviços",
    "Vendas",
    "Financeiro",
    "Caixa Unificada",
    "Relatórios",
    "Divulgação",
    "Automações",
    "Configurações",
  ];
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Início"));
    assert.deepEqual(
      await page.evaluate(() => [
        appData.clientes.length,
        appData.produtos.length,
        appData.vendas.length,
        appData.financeiro.length,
      ]),
      [0, 0, 0, 0],
    );
    const original = await page.evaluate(() => JSON.stringify(appData));
    for (const sample of [false, true]) {
      await page.evaluate((sample) => SocialMEIDemoData.set(sample), sample);
      for (const width of [320, 390, 768, 1440]) {
        await page.setViewportSize({ width, height: 960 });
        for (const theme of ["light", "dark"]) {
          await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
          for (const [index, view] of views.entries()) {
            await page.evaluate((view) => setView(view), view);
            await page.evaluate(
              () =>
                new Promise((resolve) =>
                  requestAnimationFrame(() => requestAnimationFrame(resolve)),
                ),
            );
            assert.equal(await page.locator(".page-view.active").getAttribute("data-view"), view);
            assert(
              await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
              `${view} ${width} ${theme} sample=${sample}`,
            );
            if (view === "Divulgação") {
              assert(await page.locator("#contentPublish").isDisabled());
              assert(await page.locator("#instagramPublishPanel").isHidden());
              assert(await page.locator("#instagramSimulationPanel").isHidden());
            }
            if (sample)
              await page.screenshot({ path: path.join(output, `${index}-${width}-${theme}.png`) });
            states.push({ view, width, theme, sample });
          }
        }
      }
    }
    await page.evaluate(() => {
      SocialMEIDemoData.set(false);
      setView("Clientes");
    });
    await page.evaluate(() => openCreate("cliente"));
    await page.locator("#f_nome").focus();
    await page.keyboard.press("Tab");
    assert(await page.evaluate(() => !!document.activeElement.closest("#createModal")));
    await page.keyboard.press("Shift+Tab");
    assert.equal(await page.evaluate(() => document.activeElement.id), "f_nome");
    await page.keyboard.press("Enter");
    assert(await page.locator("#createModal").evaluate((e) => e.classList.contains("open")));
    assert.equal(await page.evaluate(() => appData.clientes.length), 0);
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.getElementById("createModal").classList.contains("open"),
    );
    assert.equal(
      await page.evaluate(() => JSON.stringify(appData)),
      original,
      "Navigation/sample/cancel must not create commercial records",
    );
    assert.deepEqual(writes, []);
    assert.deepEqual(external, []);
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(output, "matrix.json"),
      JSON.stringify({ states, errors, external, writes }, null, 2),
    );
    return `${states.length} estados funcionais (#76): vazio/amostra, dez áreas, quatro larguras, claro/escuro, teclado e cancelamento sem gravação`;
  } finally {
    await context.close();
  }
};
