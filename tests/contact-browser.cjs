const assert = require("node:assert/strict");
module.exports = async function contactFlows(browser, origin, errors = []) {
  for (const width of [1440, 390]) {
    for (const theme of ["light", "dark"]) {
      const page = await browser.newPage({
        viewport: { width, height: 900 },
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
      try {
        await page.goto(origin + "/frontend/socialmei-app.html");
        await page.evaluate((theme) => {
          setTheme(theme);
          SocialMEIExperience.enterApp("Caixa Unificada");
        }, theme);
        await page.evaluate(() => openNewConversation());
        await page.locator("#inbox_f_nome").fill("Contato QA");
        await page.locator("#inbox_f_contato").fill("32132132131");
        await page.locator("#inboxModalSubmit").click();
        assert.equal(
          await page.locator("#inbox_f_contato").evaluate((input) => input.validity.valid),
          false,
        );
        assert.equal(
          await page.evaluate(() => sessionData.conversas.some((c) => c.nome === "Contato QA")),
          false,
        );
        await page.locator("#inbox_f_contato").fill("@maria.loja");
        await page.locator("#inboxModalSubmit").click();
        assert.equal(
          await page.locator("#inbox_f_contato").evaluate((input) => input.validity.valid),
          false,
        );
        await page.locator("#inbox_f_contato").fill("+55 (81) 98765-4321");
        await page.locator("#inbox_f_canal").selectOption("Instagram");
        assert.equal(await page.locator("#inbox_f_contato").inputValue(), "");
        assert.equal(await page.locator("#inbox_f_contato").getAttribute("type"), "text");
        await page.locator("#inbox_f_contato").fill("11987654321");
        await page.locator("#inboxModalSubmit").click();
        assert.equal(
          await page.locator("#inbox_f_contato").evaluate((input) => input.validity.valid),
          false,
        );
        await page.locator("#inbox_f_contato").fill("@maria.loja");
        await page.locator("#inbox_f_canal").selectOption("WhatsApp");
        assert.equal(await page.locator("#inbox_f_contato").inputValue(), "+55 (81) 98765-4321");
        await page.locator("#inbox_f_canal").selectOption("Instagram");
        assert.equal(await page.locator("#inbox_f_contato").inputValue(), "@maria.loja");
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        await page.locator("#inboxModalSubmit").click();
        await page.waitForFunction(() =>
          sessionData.conversas.some((c) => c.nome === "Contato QA"),
        );
        const clientId = await page.evaluate(() => getConversation().clientId);
        await page.evaluate(() => openDeleteConversation(getConversation()));
        await page.locator("#inboxModalForm [data-close-modal]").click();
        assert.equal(
          await page.evaluate(() => sessionData.conversas.some((c) => c.nome === "Contato QA")),
          true,
        );
        const rollback = await page.evaluate(() => {
          const originalSave = socialmeiStorageSet;
          socialmeiStorageSet = () => false;
          try {
            return {
              removed: removeLocalConversation(getConversation()),
              exists: sessionData.conversas.some((c) => c.nome === "Contato QA"),
              persisted: inboxLocalState.localConversations.some((c) => c.nome === "Contato QA"),
            };
          } finally {
            socialmeiStorageSet = originalSave;
          }
        });
        assert.deepEqual(rollback, { removed: false, exists: true, persisted: true });
        await page.evaluate(() => openDeleteConversation(getConversation()));
        await page.locator("#inboxModalSubmit").click();
        assert.equal(
          await page.evaluate(() => sessionData.conversas.some((c) => c.nome === "Contato QA")),
          false,
        );
        assert.equal(
          await page.evaluate((id) => appData.clientes.some((c) => c.id === id), clientId),
          true,
        );
        await page.reload();
        await page.evaluate(() => SocialMEIExperience.enterApp("Caixa Unificada"));
        assert.equal(
          await page.evaluate(() => sessionData.conversas.some((c) => c.nome === "Contato QA")),
          false,
        );
        // Um contato demo removido também não reaparece após recarregar.
        await page.evaluate(() => {
          const c = sessionData.conversas[0];
          window.deletedDemoName = c.nome;
          selectConversation(c.id);
        });
        const demoName = await page.evaluate(() => window.deletedDemoName);
        await page.evaluate(() => openDeleteConversation(getConversation()));
        await page.locator("#inboxModalSubmit").click();
        await page.reload();
        await page.evaluate(() => SocialMEIExperience.enterApp("Caixa Unificada"));
        assert.equal(
          await page.evaluate(
            (name) => sessionData.conversas.some((c) => c.nome === name),
            demoName,
          ),
          false,
        );
      } finally {
        await page.close();
      }
    }
  }
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    reducedMotion: "reduce",
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
  );
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator("[data-start-signup]").first().click();
    await page.locator("#registerName").fill("Maria QA");
    await page.locator("#registerEmail").fill("maria@example.com");
    await page.locator("#registerPassword").fill("Valid-password-123!");
    await page.locator("#registerPhone").fill("texto11987654321");
    await page.locator("#xpRegisterForm [type=submit]").click();
    assert.equal(await page.locator("#registerPhone").inputValue(), "");
    assert.equal(await page.locator(".contact-confirmation").count(), 0);
    const livePhone = page.locator("#registerPhone");
    await livePhone.fill("");
    await livePhone.pressSequentially("819876543211111abc");
    assert.equal(await livePhone.inputValue(), "(81) 98765-4321");
    await livePhone.press("Backspace");
    await livePhone.press("1");
    assert.equal(await livePhone.inputValue(), "(81) 98765-4321");
    await livePhone.fill("+5581987654321");
    assert.equal(await livePhone.inputValue(), "+55 (81) 98765-4321");
    await livePhone.pressSequentially("000");
    assert.equal(await livePhone.inputValue(), "+55 (81) 98765-4321");
    await livePhone.fill("+141555526711234");
    assert.equal(await livePhone.inputValue(), "+141555526711234");
    await livePhone.press("5");
    assert.equal(await livePhone.inputValue(), "+141555526711234");
    await livePhone.fill("1231232133");
    assert.equal(await livePhone.inputValue(), "(12) 3123-2133");
    await livePhone.pressSequentially("999");
    assert.equal(await livePhone.inputValue(), "(12) 3123-2133");
    await livePhone.fill("");
    const pastePhone = async (text) =>
      livePhone.evaluate((input, text) => {
        const clipboardData = new DataTransfer();
        clipboardData.setData("text/plain", text);
        input.setSelectionRange(0, input.value.length);
        input.dispatchEvent(
          new ClipboardEvent("paste", { clipboardData, bubbles: true, cancelable: true }),
        );
      }, text);
    await pastePhone("819876543211234");
    assert.equal(await livePhone.inputValue(), "");
    await pastePhone("nome11987654321");
    assert.equal(await livePhone.inputValue(), "");
    await pastePhone("+55 (81) 98765-4321");
    assert.equal(await livePhone.inputValue(), "+55 (81) 98765-4321");
    await livePhone.fill("11987654321");
    await page.locator("#xpRegisterForm [type=submit]").click();
    await page.locator(".contact-confirmation[open]").waitFor();
    assert.equal(
      await page.locator(".contact-confirmation-number").innerText(),
      "+55 (11) 98765-4321",
    );
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
      false,
    );
    assert.equal(await page.evaluate(() => document.getAnimations().length), 0);
    await page.keyboard.press("Escape");
    await page.locator(".contact-confirmation").waitFor({ state: "detached" });
    await page.waitForFunction(() => document.activeElement.id === "registerPhone");
    assert.equal(await page.locator("#registerPhone").inputValue(), "(11) 98765-4321");
    await page.locator("#xpRegisterForm [type=submit]").click();
    await page.locator(".contact-confirmation button[value=confirm]").click();
    await page.locator("[data-xp-screen=onboarding].is-active").waitFor();
  } finally {
    await page.close();
  }
  return "Contatos: telefone/Instagram, confirmação do cadastro, exclusão local persistente e cliente preservado, desktop/mobile e claro/escuro";
};
