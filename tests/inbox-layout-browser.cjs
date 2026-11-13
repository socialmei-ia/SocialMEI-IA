const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage(),
    errors = [],
    writes = [],
    external = [];
  const identity = {
    usuario: { id: 91, nome: "Teste", email: "test@example.test" },
    negocio: { id: 17, nome: "Teste", slug: "test", configuracao: {} },
    papel: "owner",
    csrf_token: "a".repeat(64),
  };
  const messages = [
    { id: 1, text: "Olá, quero um orçamento.", occurred_at: "2026-11-12T12:00:00Z" },
    { id: 2, text: "Posso retirar amanhã?", occurred_at: "2026-11-12T12:01:00Z" },
    { id: 3, text: "Outro dia", occurred_at: "2026-11-13T12:01:00Z" },
  ];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
  await page.route("**/*", (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname.replace("/api/v1", "");
    if (url.origin !== origin) {
      external.push(url.origin);
      return route.abort();
    }
    if (url.pathname.endsWith("/config.js"))
      return route.fulfill({
        contentType: "text/javascript",
        body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
      });
    if (!url.pathname.startsWith("/api/v1/")) return route.continue();
    if (req.method() !== "GET") writes.push(path);
    if (path === "/auth/session") return route.fulfill({ json: identity });
    if (path === "/auth/preferences")
      return route.fulfill({ json: { preferences: {}, revision: 0 } });
    if (path === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
    if (path === "/message-enrichment/capabilities")
      return route.fulfill({ json: { mode: "disabled", waha_inbox: true } });
    if (path === "/message-enrichment/conversations")
      return route.fulfill({
        json: {
          workspace_id: 17,
          items: [
            {
              id: 1,
              revision: 1,
              channel: "whatsapp",
              origin: "waha",
              contact_name: "Contato de teste",
              account_ref: "waha:test",
              messages,
            },
          ],
        },
      });
    if (path === "/message-enrichment/conversations/1/customer")
      return route.fulfill({
        json: { conversation_id: 1, revision: 0, cliente_id: null, customer: null },
      });
    return route.fulfill({ json: [] });
  });
  async function ready() {
    await page.locator(".ct .bb", { hasText: messages[0].text }).waitFor();
    if (!(await page.evaluate(() => !!window.SocialMEIInboxLayout)))
      await page.addScriptTag({ url: origin + "/frontend/scripts/v22-inbox-layout.js" });
    await page.locator(".inbox-layout-settings").waitFor();
  }
  try {
    await page.goto(origin + "/frontend/socialmei-app.html#/caixa/me-1");
    await ready();
    assert.equal(
      await page.locator(".inbox-message-grouped").count(),
      1,
      "Grouping respects day boundaries",
    );
    await page.locator(".inbox-layout-settings summary").click();
    const slider = page.getByRole("slider", { name: "Largura: Conversas", exact: true });
    await slider.focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(await slider.inputValue(), "25");
    assert.equal(
      await page.evaluate(() => localStorage.getItem("socialmei-inbox-layout:91:17")),
      '{"list":25,"context":23}',
    );
    await page.reload();
    await ready();
    await page.locator(".inbox-layout-settings summary").click();
    assert.equal(await slider.inputValue(), "25");
    await page.getByRole("button", { name: "Restaurar larguras" }).click();
    assert.equal(await slider.inputValue(), "24");
    assert.equal(
      await page.evaluate(() => localStorage.getItem("socialmei-inbox-layout:91:17")),
      null,
    );
    const screenshots = require("node:path").resolve(__dirname, "../test-results/inbox-layout");
    require("node:fs").mkdirSync(screenshots, { recursive: true });
    for (const width of [1440, 1280, 1024, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await require("./v22-layout-ready.cjs").waitForViewportFit(page);
      if (width <= 900 && (await page.locator(".cxback").isVisible())) {
        await page.locator(".cxback").click();
        await require("./v22-layout-ready.cjs").waitForViewportFit(page);
      }
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => {
          document.documentElement.dataset.theme = theme;
        }, theme);
        const overflow = await page.evaluate(() =>
          [...document.querySelectorAll("body *")]
            .filter((el) => el.getBoundingClientRect().right > innerWidth + 1)
            .slice(0, 12)
            .map(
              (el) =>
                `${el.tagName}.${el.className}: ${Math.round(el.getBoundingClientRect().right)}`,
            ),
        );
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
          `${width}/${theme} overflow: ${overflow.join(", ")}`,
        );
        assert(
          await page.getByRole("link", { name: "Voltar para a caixa", exact: true }).isVisible(),
        );
        if (width === 390) {
          const bot = page.locator("[data-wa-bot]");
          await bot.waitFor();
          const compact = await bot.boundingBox();
          const history = await page.locator(".ct .ms").boundingBox();
          await page.locator(".cv").evaluate((el) => el.classList.remove("inbox-layout"));
          const baseline = await bot.boundingBox();
          await page.locator(".cv").evaluate((el) => el.classList.add("inbox-layout"));
          assert(
            compact.height < baseline.height - 30,
            "Compact human panel releases reading space",
          );
          assert(history.height >= 160, "History retains a usable reading area");
          assert.equal(await bot.getByRole("button").count(), 3);
          for (const button of await bot.getByRole("button").all()) {
            assert(await button.isVisible());
            assert((await button.boundingBox()).height >= 44);
          }
          const refresh = bot.getByRole("button", { name: "Atualizar atendimento", exact: true });
          await page.keyboard.press("Tab");
          await refresh.focus();
          assert(await refresh.evaluate((el) => el.matches(":focus-visible")));
          assert.equal(await refresh.evaluate((el) => getComputedStyle(el).outlineStyle), "solid");
        }
        await page.screenshot({
          path: require("node:path").join(screenshots, `${width}-${theme}.png`),
        });
      }
    }
    assert.deepEqual(writes, [], "Presentation controls never write to the API");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
  } finally {
    await context.close();
  }
  return "Inbox layout: keyboard sizing, account-scoped persistence/reset, grouping/day boundary and responsive themes passed (controlled API).";
};
