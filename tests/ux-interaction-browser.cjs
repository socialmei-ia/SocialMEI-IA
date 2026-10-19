const assert = require("node:assert/strict");
module.exports = async function uxInteractions(browser, origin) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage(),
    errors = [],
    writes = [],
    layouts = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.clock.setFixedTime(new Date("2026-10-19T15:00:00Z"));
  await page.route("**/*", (route) => {
    const req = route.request(),
      url = new URL(req.url());
    if (url.origin !== origin) return route.abort();
    if (req.method() !== "GET") writes.push(req.method() + " " + url.pathname);
    return route.continue();
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    const brand = page.locator('#sb .logo[data-nav="Início"]');
    assert.equal(await brand.getAttribute("type"), "button");
    await page.evaluate(() => setView("Vendas"));
    await brand.locator(".logo-mark").click();
    assert.equal(await page.evaluate(() => currentView), "Início");
    await page.evaluate(() => setView("Clientes"));
    await brand.locator(".logo-text").click();
    assert.equal(await page.evaluate(() => currentView), "Início");
    await page.evaluate(() => setView("Financeiro"));
    await brand.focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.evaluate(() => currentView), "Início");
    // The independent compact-sidebar control still works.
    await page.locator("#sbCollapse").click();
    assert(await page.locator("#app").evaluate((e) => e.classList.contains("sb-mini")));
    await page.locator("#sbCollapse").click();
    assert.equal(await page.evaluate(() => currentView), "Início");
    const original = await page.evaluate(() => JSON.stringify(appData));
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
    for (const mode of [false, true]) {
      await page.evaluate((mode) => {
        SocialMEIDemoData.set(mode);
        document.dispatchEvent(new CustomEvent("socialmei-demo-change"));
      }, mode);
      for (const width of [320, 390, 768, 1024, 1440])
        for (const theme of ["light", "dark"]) {
          await page.setViewportSize({ width, height: 1000 });
          await page.evaluate((t) => SocialMEIThemes.select(t), theme);
          for (const view of views) {
            await page.evaluate((v) => setView(v), view);
            const trigger = page.locator("#contextHelpButton");
            assert(await trigger.isVisible(), view + " " + width);
            assert.equal(await trigger.count(), 1);
            assert(
              await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
              view + " " + width,
            );
            assert(
              await page.locator(".hd").evaluate((e) => e.getBoundingClientRect().height <= 90),
              "Cabeçalho compacto: " + view + " " + width,
            );
            const heading = page.locator(".hd-title h1");
            if (await heading.isVisible()) {
              assert(
                await heading.evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
                "Cabeçalho legível: " + view + " " + width,
              );
            }
            await trigger.focus();
            await page.keyboard.press("Enter");
            await page.waitForFunction(() => document.activeElement?.closest("#contextHelpModal"));
            assert.equal(await page.locator("#contextHelpTitle").textContent(), "Ajuda · " + view);
            assert(await page.locator("#app").evaluate((e) => e.inert));
            assert(await page.locator("#contextHelpIntro").textContent());
            const modalBox = await page.locator("#contextHelpModal .modal").boundingBox();
            assert(modalBox.x >= 0 && modalBox.x + modalBox.width <= width + 1);
            const topic = page
              .locator(
                "#contextHelpSections summary, #contextHelpSources > :not([hidden]) > summary",
              )
              .first();
            const wasOpen = await topic.evaluate((e) => e.parentElement.open);
            await topic.focus();
            await page.keyboard.press("Enter");
            assert.equal(
              await topic.evaluate((e) => e.parentElement.open),
              !wasOpen,
              JSON.stringify({ view, width, theme, mode }),
            );
            const geometry = await topic.evaluate((e) => ({
              display: getComputedStyle(e).display,
              gap: parseFloat(getComputedStyle(e).gap),
              height: e.getBoundingClientRect().height,
            }));
            assert.equal(geometry.display, "flex");
            assert(geometry.gap >= 12 && geometry.height >= 44);
            await page.keyboard.press("Escape");
            await page.waitForFunction(
              () => !document.getElementById("contextHelpModal").classList.contains("open"),
            );
            assert(await trigger.evaluate((e) => e === document.activeElement));
            layouts.push({ view, width, theme, demo: mode });
          }
        }
    }
    assert.equal(await page.evaluate(() => JSON.stringify(appData)), original);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.evaluate(() => setView("Oportunidades"));
    await page.locator("#contextHelpButton").click();
    assert.equal(await page.locator("#contextHelpSources .native-opportunity-criteria").count(), 1);
    assert.equal(await page.locator("#opportunitiesView .native-opportunity-criteria").count(), 0);
    await page.locator(".native-opportunity-criteria >summary").click();
    assert.match(
      await page.locator(".native-opportunity-criteria").innerText(),
      /24 horas é experimental/,
    );
    // Native focus trap works in both directions.
    const close = page.locator('[data-close-modal="contextHelpModal"]').first(),
      last = page.locator('[data-close-modal="contextHelpModal"]').last();
    await close.focus();
    await page.keyboard.press("Shift+Tab");
    assert(await last.evaluate((e) => e === document.activeElement));
    await page.keyboard.press("Tab");
    assert(await close.evaluate((e) => e === document.activeElement));
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.getElementById("contextHelpModal").classList.contains("open"),
    );
    // One, none and twenty synthetic conversations must produce intentional layouts.
    await page.evaluate(() => {
      window.uxOriginalConversations = businessViewConversations;
      window.uxFixture = [];
      businessViewConversations = () => window.uxFixture;
    });
    for (const count of [0, 1, 20])
      for (const width of [320, 390, 768, 1024, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((count) => {
          window.uxFixture = Array.from({ length: count }, (_, i) => ({
            id: 700 + i,
            nome: "Pessoa QA " + i,
            canal: "whatsapp",
            status: "aberto",
            naoLidas: 1,
            mensagens: [{ de: "cliente", texto: "Oi, tenho uma dúvida.", data: "2026-10-19" }],
          }));
          setView("Oportunidades");
        }, count);
        assert.equal(
          await page.locator(".client-analysis-list >.client-analysis-card").count(),
          count,
        );
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        if (count === 1 && width === 1440) {
          const sizes = await page.evaluate(() => {
            const r = (s) => document.querySelector(s).getBoundingClientRect();
            return {
              list: r(".client-analysis-list").width,
              card: r(".client-analysis-card").width,
              height: r(".client-analysis-card").height,
            };
          });
          assert(Math.abs(sizes.list - sizes.card) < 2, JSON.stringify(sizes));
          assert(sizes.height < 520, JSON.stringify(sizes));
        }
      }
    await page.evaluate(() => {
      window.uxOriginalData = businessViewData;
    });
    for (const count of [0, 1, 20])
      for (const width of [320, 390, 768, 1024, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((count) => {
          const sample = structuredClone(appData);
          sample.vendas = Array.from({ length: count }, (_, i) => ({
            id: 900 + i,
            cliente_id: 700 + i,
            cliente: "Pessoa QA " + i,
            valor: 100,
            data: "2026-10-19",
            status: "Pago",
            item: "Serviço QA",
            quantidade: 1,
            pagamento: "Pix",
          }));
          window.uxFixture = Array.from({ length: count }, (_, i) => ({
            id: 700 + i,
            nome: "Pessoa QA " + i,
            canal: "whatsapp",
            status: "aberto",
            naoLidas: 1,
            mensagens: [{ de: "cliente", texto: "Mensagem sintética de QA", data: "2026-10-19" }],
          }));
          businessViewData = () => sample;
          setView("Início");
        }, count);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        assert.equal(
          await page.locator("#homeRecentSales .home-sale-row").count(),
          Math.min(count, 3),
        );
        if (width === 1440) {
          const geometry = await page.evaluate(() => ({
            conversation: document.getElementById("homeNow").getBoundingClientRect().height,
            priorities: document.querySelector(".home-operations").getBoundingClientRect().top,
          }));
          assert(geometry.conversation < 380, JSON.stringify(geometry));
          assert(geometry.priorities < 820, JSON.stringify(geometry));
        }
      }
    await page.evaluate(() => {
      businessViewConversations = window.uxOriginalConversations;
      businessViewData = window.uxOriginalData;
      setView("Caixa Unificada");
    });
    const id = await page.evaluate(
      () => sessionData.conversas.find((c) => c._socialmeiDemoSample).id,
    );
    await page.locator(`[data-conversation="${id}"]`).click();
    await page.locator("#messageInput").fill("Rascunho de QA preservado pela logo");
    await brand.click();
    await page.evaluate(() => setView("Caixa Unificada"));
    await page.locator(`[data-conversation="${id}"]`).click();
    assert.equal(
      await page.locator("#messageInput").inputValue(),
      "Rascunho de QA preservado pela logo",
    );
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.locator("#mb").click();
    await brand.focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.evaluate(() => currentView), "Início");
    assert.equal(await page.locator("#sb").evaluate((e) => e.classList.contains("open")), false);
    // Normal motion and rapid dismissal/reopening use the existing modal epochs.
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.locator("#contextHelpButton").click();
    await page.evaluate(() => {
      closeModal("contextHelpModal");
      openModal("contextHelpModal");
    });
    await page.waitForTimeout(350);
    assert(await page.locator("#contextHelpModal").evaluate((e) => e.classList.contains("open")));
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.getElementById("contextHelpModal").classList.contains("open"),
    );
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.locator("#contextHelpButton").click();
    await page.locator("#contextHelpSections summary").first().click();
    assert.equal(await page.evaluate(() => document.getAnimations().length), 0);
    await page.keyboard.press("Escape");
    assert.deepEqual(errors, []);
    assert.deepEqual(writes, []);
    return `UX: ${layouts.length} estados de ajuda, 30 layouts com 0/1/20 clientes e vendas, logo por símbolo/nome/teclado, sidebar independente, rascunho preservado, foco/Escape/Tab, movimento reduzido e zero gravações externas.`;
  } finally {
    await context.close();
  }
};
if (require.main === module) {
  const { chromium } = require("playwright");
  (async () => {
    const b = await chromium.launch({
      executablePath: process.env.CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
    });
    try {
      console.log(await module.exports(b, process.argv[2] || "http://127.0.0.1:5506"));
    } finally {
      await b.close();
    }
  })().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
}
