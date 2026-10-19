const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path"),
  http = require("node:http"),
  { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function premiumExperience(browser, origin) {
  const out = path.join(root, "test-results/premium-experience");
  fs.mkdirSync(out, { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  const errors = [],
    writes = [],
    layouts = [];
  let page;
  try {
    page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await page.clock.setFixedTime(new Date("2026-10-19T15:00:00Z"));
    await page.route("**/*", (route) => {
      const req = route.request(),
        u = new URL(req.url());
      if (u.origin !== origin) return route.abort();
      if (req.method() !== "GET") writes.push(req.method() + " " + u.pathname);
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    assert.equal(
      await page.evaluate(() => sessionData.conversas.some((c) => c._socialmeiDemoSample)),
      false,
    );
    await page.evaluate(() => {
      appData.clientes = [{ id: 701, nome: "Registro preservado QA", status: "Ativo", tags: [] }];
      saveAppData();
      setView("Configurações");
    });
    const before = await page.evaluate(() => ({
      data: JSON.stringify(appData),
      saved: localStorage.getItem("socialmei-app-data-v2"),
    }));
    const toggle = page.locator("#viewDemoToggle");
    await toggle.focus();
    await page.keyboard.press("Space");
    assert.equal(await toggle.getAttribute("aria-checked"), "true");
    assert.equal(
      await page
        .locator("#toastZone .toast")
        .filter({ hasText: "Dados de teste ativados" })
        .count(),
      1,
    );
    assert.equal(await page.locator("#toastZone .toast").last().getAttribute("role"), "status");
    assert.equal(await page.locator(".view-demo-notice").count(), 0);
    await page.locator("#viewDemoNotice").focus();
    await page.keyboard.press("Enter");
    assert(await page.locator("#viewDemoControl").evaluate((e) => e.open));
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("#viewDemoControl").evaluate((e) => e.open), false);
    assert(await page.locator("#viewDemoNotice").evaluate((e) => e === document.activeElement));
    const views = [
      "Início",
      "Caixa Unificada",
      "Oportunidades",
      "Visão Geral",
      "Vendas",
      "Clientes",
      "Produtos e Serviços",
      "Financeiro",
      "Relatórios",
      "Automações",
      "Assistente",
      "Divulgação",
      "Configurações",
    ];
    await page.emulateMedia({ reducedMotion: "reduce" });
    for (const width of [320, 390, 768, 1024, 1280, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        for (const view of views) {
          await page.evaluate((view) => setView(view), view);
          await page.waitForTimeout(12);
          const layout = await page.evaluate(() => {
            const badge = document.getElementById("viewDemoNotice").getBoundingClientRect(),
              header = document.querySelector(".hd").getBoundingClientRect();
            return {
              overflow: document.documentElement.scrollWidth > innerWidth,
              badgeWidth: badge.width,
              badgeHeight: badge.height,
              headerHeight: header.height,
              badges: document.querySelectorAll("#viewDemoNotice").length,
            };
          });
          assert.equal(layout.overflow, false, view + " " + width);
          assert.equal(layout.badges, 1);
          assert(layout.badgeWidth <= 150);
          assert(layout.headerHeight <= 90);
          assert(
            await page.locator("#viewDemoNotice").isVisible(),
            JSON.stringify({
              view,
              width,
              theme,
              layout,
              active: await page.evaluate(() => SocialMEIDemoData.enabled()),
            }),
          );
          if (view === "Oportunidades") {
            const positions = await page.evaluate(() => ({
              tab: document.getElementById("clientAnalysisTabs").getBoundingClientRect().top,
              card: document.querySelector(".client-analysis-card")?.getBoundingClientRect().top,
            }));
            assert(positions.tab < (width <= 390 ? 330 : 300), JSON.stringify(positions));
            assert(positions.card < (width <= 390 ? 460 : 450), JSON.stringify(positions));
            assert.equal(await page.locator("#opportunitiesView .management-demo").count(), 0);
          }
          layouts.push({ view, width, theme, mode: "on", ...layout });
        }
      }
    // The inbox replaces its title when opening a thread. Its one shared badge must survive.
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.evaluate(() => setView("Caixa Unificada"));
    await page.locator("#conversationList [data-conversation]").first().click();
    assert(await page.locator("#viewDemoNotice").isVisible());
    assert.equal(await page.locator("#viewDemoControl").count(), 1);
    await page.waitForFunction(() => document.querySelector("[data-edit-profile]")?.disabled);
    assert(await page.locator("[data-edit-profile]").isDisabled());
    assert.equal(
      await page.evaluate(async () => await ensureContextClient(getConversation())),
      null,
    );
    await page.evaluate(() => openProfileEditor());
    // A direct form submission must also stop before creating/updating a real record.
    await page.evaluate(() =>
      document
        .getElementById("inboxModalForm")
        .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
    );
    assert.equal(await page.evaluate(() => JSON.stringify(appData)), before.data);
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.waitForTimeout(30);
    assert(await page.locator(".hd #viewDemoNotice").isVisible());
    await page.evaluate(() => setView("Oportunidades"));
    await page.locator(".opportunity-options > summary").click();
    await page.locator("[data-opportunity-refresh]").click();
    await page.locator("[data-opportunity-open]").first().click();
    assert(await page.locator("#opportunityModal").evaluate((e) => e.classList.contains("open")));
    await page.keyboard.press("Escape");
    // The global shortcut opens the native settings and focuses the actual switch.
    await page.locator("#viewDemoNotice").click();
    await page.locator("[data-demo-settings]").click();
    assert.equal(await page.evaluate(() => currentView), "Configurações");
    assert(await toggle.evaluate((e) => e === document.activeElement));
    await toggle.click();
    assert.equal(await page.locator("#viewDemoNotice").isVisible(), false);
    assert.equal(
      await page.evaluate(() => sessionData.conversas.some((c) => c._socialmeiDemoSample)),
      false,
    );
    assert.equal(await page.evaluate(() => JSON.stringify(appData)), before.data);
    assert.equal(
      await page.evaluate(() => localStorage.getItem("socialmei-app-data-v2")),
      before.saved,
    );
    assert.equal(
      await page
        .locator("#toastZone .toast")
        .filter({ hasText: "Dados de teste desativados" })
        .count(),
      1,
    );
    for (const width of [320, 390, 768, 1024, 1280, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        for (const view of views) {
          await page.evaluate((view) => setView(view), view);
          assert.equal(await page.locator("#viewDemoNotice").isVisible(), false);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          layouts.push({ view, width, theme, mode: "off" });
        }
      }
    // An explicitly isolated analysis demonstration still identifies its origin globally.
    await page.evaluate(() => setView("Oportunidades"));
    await page.locator("[data-opportunity-demo]").click();
    assert(await page.locator("#viewDemoNotice").isVisible());
    await page.locator("#viewDemoNotice").click();
    assert(
      (await page.locator("#viewDemoDescription").textContent()).includes("apenas na análise"),
    );
    await page.locator("#viewDemoExit").click();
    assert.equal(await page.locator("#viewDemoNotice").isVisible(), false);
    // Counter visuals preserve final DOM text/accessible value and the source snapshot.
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.evaluate(() => {
      SocialMEIDemoData.set(true);
      document.dispatchEvent(new CustomEvent("socialmei-demo-change"));
      setView("Financeiro");
    });
    await page.waitForTimeout(60);
    const metric = page.locator("#financeSummary .management-kpi > b").first(),
      label = await metric.textContent();
    assert(label.includes("R$"));
    assert(!Number.isNaN(await page.evaluate(() => operationalMetrics().revenue)));
    await page.waitForTimeout(650);
    assert.equal(await metric.textContent(), label);
    assert.equal(
      await page.evaluate(async () => {
        const node = document.createElement("span");
        document.body.append(node);
        const first = SocialMEIMotion.animate(node, [{ opacity: 0 }, { opacity: 1 }], 80);
        const second = SocialMEIMotion.animate(
          node,
          [{ transform: "translateY(2px)" }, { transform: "none" }],
          80,
        );
        await Promise.all([first, second]);
        const remaining = node.style.willChange;
        node.remove();
        return remaining;
      }),
      "",
      "Interrupted motion must release its will-change hint",
    );
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.evaluate(() => setView("Visão Geral"));
    await page.waitForTimeout(100);
    assert.equal(await page.locator(".premium-counting").count(), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(writes, []);
    fs.writeFileSync(
      path.join(out, "results.json"),
      JSON.stringify({ layouts, errors, writes }, null, 2),
    );
  } finally {
    await context.close();
  }
  return `Experiência premium: ${layouts.length} estados, seis larguras/claro-escuro, indicador único, avisos compactos, toast/teclado/foco, modo desligado preservado e demonstração isolada identificada.`;
};
if (require.main === module) {
  const server = http.createServer((req, res) => {
    const name = path.resolve(
      root,
      "." + decodeURIComponent(new URL(req.url, "http://localhost").pathname),
    );
    if (!name.startsWith(root + path.sep) || !fs.existsSync(name) || !fs.statSync(name).isFile())
      return res.writeHead(404).end();
    res.setHeader(
      "Content-Type",
      {
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
        ".woff2": "font/woff2",
      }[path.extname(name)] || "application/octet-stream",
    );
    fs.createReadStream(name).pipe(res);
  });
  (async () => {
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    const b = await chromium.launch({
      executablePath: process.env.CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
    });
    try {
      console.log(await module.exports(b, `http://127.0.0.1:${server.address().port}`));
    } finally {
      await b.close();
      server.close();
    }
  })().catch((e) => {
    console.error(e);
    server.close();
    process.exitCode = 1;
  });
}
