const assert = require("node:assert/strict");
module.exports = async function externalAudit(browser, origin) {
  const errors = [],
    writes = [];
  let states = 0;
  for (const remote of [false, true]) {
    const context = await browser.newContext({
      reducedMotion: "reduce",
      viewport: { width: 1440, height: 1000 },
    });
    try {
      const page = await context.newPage();
      page.on("pageerror", (e) => errors.push(e.message));
      await page.route("**/*", (route) => {
        const r = route.request(),
          u = new URL(r.url());
        if (u.origin !== origin) return route.abort();
        if (r.method() !== "GET") writes.push(r.method() + " " + u.pathname);
        if (remote && u.pathname === "/frontend/config.js")
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (u.pathname.startsWith("/api/v1/"))
          return route.fulfill({
            json:
              u.pathname === "/api/v1/auth/session"
                ? {
                    usuario: { id: 12, nome: "José da Silva", email: "qa@example.com" },
                    negocio: { id: 21, slug: "qa-audit", nome: "Negócio QA", configuracao: {} },
                    papel: "owner",
                    csrf_token: "a".repeat(64),
                  }
                : [],
          });
        return route.continue();
      });
      await page.goto(origin + "/frontend/socialmei-app.html");
      if (remote) await page.evaluate(() => SocialMEIAuth.ready);
      await page.evaluate(() => SocialMEIExperience.enterApp("Início"));
      await page.evaluate(() => {
        sessionData.conversas.push({
          id: 777,
          nome: "Contato QA isolado",
          canal: "whatsapp",
          status: "aberto",
          naoLidas: 4,
          mensagens: [
            { de: "cliente", texto: "Mensagem de QA, não é canal conectado", hora: "10:00" },
          ],
        });
        appData.clientes.push({
          id: 91001,
          nome: "Cliente QA privado",
          tags: ["Etiqueta QA privada"],
        });
        window.auditOriginal = JSON.stringify(
          sessionData.conversas.filter((c) => !c._socialmeiDemoSample),
        );
        window.auditBusiness = JSON.stringify(appData);
        SocialMEIDemoData.set(true);
        document.dispatchEvent(new CustomEvent("socialmei-demo-change"));
      });
      const data = await page.evaluate(() => ({
        expected: businessViewData().conversations.map((c) => c.nome),
        actual: businessViewConversations().map((c) => c.nome),
        count: conversationCounts(),
      }));
      assert.deepEqual(data.actual, data.expected);
      assert.equal(data.count.unreadMessages, 5);
      assert.equal(data.count.unreadConversations, 5);
      assert.equal(await page.locator('#nav [data-nav="Caixa Unificada"] em').textContent(), "5");
      assert(await page.locator("#nvBusinessSteps").isHidden());
      assert(await page.locator("#nvBusinessBar").isHidden());
      await page.evaluate(() => setView("Caixa Unificada"));
      assert.equal(await page.locator('[data-conversation="777"]').count(), 0);
      assert.equal(await page.locator("#conversationList [data-conversation]").count(), 6);
      assert.equal(await page.locator("#pendingCount").textContent(), "5 mensagens não lidas");
      assert(!(await page.locator("#tagFilter").innerText()).includes("Etiqueta QA privada"));
      const first = await page.evaluate(() => businessViewConversations()[0].id);
      assert.equal(
        Number(
          await page
            .locator("#conversationList [data-conversation]")
            .first()
            .getAttribute("data-conversation"),
        ),
        first,
        "A conversa mais recente e pendente deve aparecer antes da encerrada",
      );
      await page.locator(`[data-conversation="${first}"]`).click();
      assert.equal(await page.locator("#threadName").textContent(), "Lia (exemplo)");
      await page.evaluate(() => setView("Início"));
      assert.equal(await page.locator('#nav [data-nav="Caixa Unificada"] em').textContent(), "4");
      assert.match(
        await page.locator("#homePulseConversations").textContent(),
        /4 mensagens não lidas/,
      );
      for (const width of [320, 390, 768, 1024, 1440])
        for (const theme of ["light", "dark"]) {
          await page.setViewportSize({ width, height: 1000 });
          await page.evaluate((t) => SocialMEIThemes.select(t), theme);
          for (const view of [
            "Início",
            "Caixa Unificada",
            "Oportunidades",
            "Automações",
            "Relatórios",
            "Assistente",
            "Configurações",
          ]) {
            await page.evaluate((v) => setView(v), view);
            assert(
              await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
              view + " " + width,
            );
            assert(
              !/[()\uD800-\uDBFF]/u.test(
                await page
                  .locator(
                    ".client-analysis-avatar:visible,.avatar-initials:visible,#homeNow .av:visible",
                  )
                  .allTextContents()
                  .then((a) => a.join("")),
              ),
            );
            if (view === "Assistente")
              assert(
                !(await page.locator("#nvAiConversations").innerText()).includes(
                  "Contato QA isolado",
                ),
              );
            if (view === "Relatórios") {
              const unavailable = page
                .locator("#nvReportKpis small")
                .filter({ hasText: "Histórico anterior insuficiente" });
              if (await unavailable.count()) {
                assert.equal(await page.locator("#reportComparisonNote").count(), 1);
                assert(await page.locator("#reportComparisonNote").isVisible());
                for (const note of await unavailable.all()) assert(await note.isHidden());
              }
              if (width === 1440) {
                const sizes = await page
                  .locator("#nvReportKpis > *")
                  .evaluateAll((es) => es.map((e) => e.getBoundingClientRect().width));
                assert(Math.max(...sizes) - Math.min(...sizes) < 2);
              }
            }
            assert(await page.locator("#viewDemoNotice").isVisible());
            assert.match(await page.locator("#viewDemoNotice").innerText(), /leitura/);
            states++;
          }
        }
      await page.evaluate(() => setView("Relatórios"));
      const options = page.locator("#nvReportCompare").locator("xpath=ancestor::details[1]");
      if (!(await options.evaluate((e) => e.open))) await options.locator("summary").click();
      assert(
        await page
          .locator("#nvReportCompare")
          .evaluate((e) => e.closest("label").getBoundingClientRect().height >= 44),
      );
      const wasCompared = await page.locator("#nvReportCompare").isChecked();
      await page.locator("#nvReportCompare").focus();
      await page.keyboard.press("Space");
      assert.equal(await page.locator("#nvReportCompare").isChecked(), !wasCompared);
      await page.keyboard.press("Space");
      assert.equal(await page.locator("#nvReportCompare").isChecked(), wasCompared);
      await page.evaluate(() => setView("Vendas"));
      const create = page.locator('[data-create="venda"]').first();
      assert(await create.isDisabled());
      assert.equal(await create.getAttribute("aria-describedby"), "viewDemoDescription");
      await page.locator("#viewDemoNotice").focus();
      await page.keyboard.press("Enter");
      assert.match(
        await page.locator("#viewDemoDescription").innerText(),
        /cadastrar ou editar clientes/i,
      );
      await page.keyboard.press("Escape");
      await page.evaluate(() => {
        SocialMEIDemoData.set(false);
        document.dispatchEvent(new CustomEvent("socialmei-demo-change"));
        setView("Caixa Unificada");
      });
      assert.equal(await page.locator('#conversationList [data-conversation="777"]').count(), 1);
      assert.equal(await page.locator('#nav [data-nav="Caixa Unificada"] em').textContent(), "4");
      assert.equal(await page.locator('[data-filter-count="unread"]').textContent(), "1");
      assert.match(
        await page.locator('[data-quick-filter="unread"]').getAttribute("aria-label"),
        /1 conversa com mensagens não lidas/,
      );
      assert.equal(
        await page.evaluate(
          () =>
            JSON.stringify(sessionData.conversas.filter((c) => !c._socialmeiDemoSample)) ===
            window.auditOriginal,
        ),
        true,
      );
      assert.equal(
        await page.evaluate(() => JSON.stringify(appData) === window.auditBusiness),
        true,
      );
      assert.equal(
        await page.evaluate(() => sessionData.conversas.some((c) => c._socialmeiDemoSample)),
        false,
      );
    } finally {
      await context.close();
    }
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(writes, []);
  return `Auditoria externa: ${states} estados claro/escuro, elenco único, mensagens/conversas distintas, leitura e retorno aos dados originais em sessão local/remota; zero gravações.`;
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
