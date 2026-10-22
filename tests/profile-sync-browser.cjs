const assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path");
const model = require("../frontend/scripts/business-profile.js");
module.exports = async (browser, origin) => {
  const api = require("./profile-sync-fixture.cjs")();
  const identity = {
    usuario: { id: 41, nome: "Pessoa fictícia", email: "perfil@example.test" },
    negocio: { id: 51, slug: "perfil-qa", nome: "Negócio oficial", configuracao: {} },
    papel: "owner",
    csrf_token: "a".repeat(64),
  };
  const legacy = model.normalize({
    businessName: "Nome anterior local",
    segment: "barber",
    offers: ["services"],
    services: ["Barba"],
    modules: ["services", "clients"],
    completed: true,
  });
  const key = "socialmei-business-profile-v1:" + encodeURIComponent("account:41:workspace:51"),
    raw = JSON.stringify({ version: 1, scope: "account:41:workspace:51", profile: legacy });
  const writes = [],
    errors = [],
    external = [],
    contexts = [];
  let unavailable = false;
  const output = path.resolve(__dirname, "../test-results/profile-sync");
  fs.mkdirSync(output, { recursive: true });
  async function pageFor(seed = false) {
    const context = await browser.newContext({
      reducedMotion: "reduce",
      viewport: { width: 1440, height: 1000 },
    });
    contexts.push(context);
    if (seed)
      await context.addInitScript(
        ({ key, raw }) => {
          if (localStorage.getItem("qa78-seeded")) return;
          localStorage.setItem("qa78-seeded", "true");
          localStorage.setItem("socialmei-auth-browser-scope", "41:51");
          localStorage.setItem(key, raw);
          localStorage.setItem("socialmei-active-theme", "dark");
          localStorage.setItem(
            "socialmei-app-data-v2",
            JSON.stringify({ prefs: { notificacoes: false, notifications: { message: false } } }),
          );
        },
        { key, raw },
      );
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (route) => {
      const req = route.request(),
        u = new URL(req.url());
      if (u.origin !== origin) {
        external.push(u.origin);
        return route.abort();
      }
      if (u.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
        });
      if (u.pathname === "/api/v1/auth/session") return route.fulfill({ json: identity });
      if (["/api/v1/workspace-profile", "/api/v1/auth/preferences"].includes(u.pathname)) {
        if (req.method() !== "GET") writes.push({ path: u.pathname, body: req.postDataJSON() });
        if (unavailable)
          return route.fulfill({ status: 503, json: { detail: "Indisponível no teste" } });
        return api(route, identity);
      }
      if (u.pathname.startsWith("/api/")) return route.fulfill({ json: [] });
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () => window.SocialMEIAuth?.current && document.body?.classList.contains("experience-app"),
    );
    await page.evaluate(() => SocialMEIProfileSync.ready);
    return page;
  }
  const settings = (page) =>
    page.evaluate(() => {
      selectedSettingsTab = "perfil";
      setView("Configurações");
    });
  try {
    const a = await pageFor(true);
    assert.equal(
      await a.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
      null,
    );
    assert.equal(await a.evaluate((key) => localStorage.getItem(key), key), raw);
    assert.equal(writes.length, 0);
    await settings(a);
    await a.locator("details:has([data-sync-import-profile]) summary").click();
    await a.evaluate(() => renderSettings());
    assert.equal(
      await a
        .locator("details:has([data-sync-import-profile])")
        .evaluate((details) => details.open),
      true,
      "Refreshing settings must preserve the expanded local-profile import",
    );
    assert.equal(
      await a
        .locator("details:has([data-sync-import-profile]) summary")
        .evaluate((summary) => summary === document.activeElement),
      true,
      "Refreshing settings must preserve focus on the local-profile import summary",
    );
    await a.locator("[data-sync-import-profile]").click();
    await a.locator('[data-onboard-panel="6"].is-active').waitFor();
    assert.equal(writes.length, 0);
    await a.locator("[data-business-cancel]").click();
    await a.waitForFunction(() => document.body?.classList.contains("experience-app"));
    assert.equal(writes.length, 0);
    assert.equal(
      await a
        .locator("details:has([data-sync-import-profile])")
        .evaluate((details) => details.open),
      true,
      "Canceling import must return to the expanded local-profile disclosure",
    );
    await a.locator("details:has([data-sync-import-profile]) summary").click();
    assert.equal(
      await a
        .locator("details:has([data-sync-import-profile])")
        .evaluate((details) => details.open),
      false,
    );
    await a.locator("details:has([data-sync-import-profile]) summary").click();
    assert.equal(
      await a
        .locator("details:has([data-sync-import-profile])")
        .evaluate((details) => details.open),
      true,
    );
    // The return from onboarding may finish while remote profile status is settling.
    // Wait for an actionable profile, then verify focus both before and after rerender.
    await a.waitForFunction(() => {
      const action = document.querySelector("#settingsPanel [data-sync-import-profile]");
      const state = SocialMEIProfileSync.state();
      return (
        currentView === "Configurações" &&
        selectedSettingsTab === "perfil" &&
        state.profileRevision !== null &&
        action &&
        !action.disabled &&
        action.closest("details")?.open
      );
    });
    await a.locator("[data-sync-import-profile]").focus();
    const initialFocus = await a.locator("[data-sync-import-profile]").evaluate((button) => ({
      focused: button === document.activeElement,
      disabled: button.disabled,
      disclosureOpen: button.closest("details")?.open,
    }));
    assert.equal(
      initialFocus.focused,
      true,
      "Import action must receive focus before the settings refresh: " +
        JSON.stringify(initialFocus),
    );
    await a.evaluate(() => renderSettings());
    const restoredFocus = await a.locator("[data-sync-import-profile]").evaluate((button) => ({
      focused: button === document.activeElement,
      disabled: button.disabled,
      disclosureOpen: button.closest("details")?.open,
    }));
    assert.equal(
      restoredFocus.focused,
      true,
      "Refreshing settings must preserve focus on the local-profile import action: " +
        JSON.stringify(restoredFocus),
    );
    await a.locator("[data-sync-import-profile]").click();
    await a.locator("[data-onboard-next]").click();
    await a.waitForFunction(() => document.body?.classList.contains("experience-app"));
    assert.equal(writes.length, 1);
    assert.equal(writes[0].path, "/api/v1/workspace-profile");
    assert.equal(await a.evaluate((key) => localStorage.getItem(key), key), raw);
    const b = await pageFor();
    assert.equal(
      await b.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile.segment),
      "barber",
    );
    assert.equal(
      await b.evaluate(
        () => SocialMEIBusinessProfile.browserRepository().read().profile.businessName,
      ),
      "Negócio oficial",
    );
    await settings(a);
    await a.locator("[data-sync-import-review] summary").click();
    await a.locator("[data-sync-import-cancel]").click();
    assert.equal(writes.length, 1);
    await a.locator("[data-sync-import-review] summary").click();
    await a.locator("[data-sync-import-preferences]").click();
    await a.waitForFunction(
      () => SocialMEIProfileSync.state().preferences.notificationsEnabled === false,
    );
    assert.equal(writes.length, 2);
    // A conflict summary belongs to the scrollable review, never the fixed action footer.
    await settings(a);
    assert.equal(
      await a
        .locator("details:has([data-sync-import-profile])")
        .evaluate((details) => details.open),
      true,
    );
    await a.locator("details:has([data-sync-import-profile]) summary").click();
    assert.equal(
      await a
        .locator("details:has([data-sync-import-profile])")
        .evaluate((details) => details.open),
      false,
    );
    await a.locator("details:has([data-sync-import-profile]) summary").click();
    assert.equal(
      await a
        .locator("details:has([data-sync-import-profile])")
        .evaluate((details) => details.open),
      true,
    );
    await a.locator("[data-sync-import-profile]").click();
    await b.evaluate(async () => {
      const repo = SocialMEIBusinessProfile.browserRepository(),
        saved = repo.read();
      await repo.save(
        { ...saved.profile, activity: "Perfil alterado em outra sessão" },
        repo.scope(),
        saved.revision,
      );
    });
    await a.setViewportSize({ width: 390, height: 900 });
    await a.locator("[data-onboard-next]").click();
    await a.locator("#businessProfileConflict").waitFor({ state: "visible" });
    assert.equal(await a.locator(".onboarding-footer #businessProfileConflict").count(), 0);
    assert(
      await a.locator("#businessProfileConflict").evaluate((e) => e === document.activeElement),
    );
    await a.setViewportSize({ width: 390, height: 900 });
    assert(
      await a
        .locator(".onboarding-footer")
        .evaluate((e) => e.getBoundingClientRect().height < innerHeight / 2),
    );
    assert(await a.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert(
      await a.locator("[data-business-reload]").evaluate((button) => {
        const box = button.getBoundingClientRect(),
          footer = document.querySelector(".onboarding-footer").getBoundingClientRect();
        return box.top >= 0 && box.bottom <= footer.top;
      }),
    );
    await a.screenshot({ path: path.join(output, "conflict-390.png") });
    await a.locator("[data-business-reload]").click();
    await a.locator("[data-business-cancel]").click();
    await a.waitForFunction(() => document.body?.classList.contains("experience-app"));

    await b.evaluate(() => {
      selectedSettingsTab = "aparencia";
      setView("Configurações");
    });
    await b.locator('#settingsPanel [data-theme-apply="light"]').click();
    await b.waitForFunction(() => SocialMEIProfileSync.state().preferencesState === "conflict");
    assert.equal(await b.evaluate(() => SocialMEIProfileSync.state().pending.theme), "light");
    await b.locator("[data-sync-use-preferences]").click();
    await b.waitForFunction(() => SocialMEIProfileSync.state().preferencesState === "ready");
    assert.equal(await b.evaluate(() => SocialMEIThemes.active), "dark");
    assert.equal(await b.evaluate(() => appData.prefs.notificacoes), false);
    // Opening a notification form locks its revision, even if a later GET refreshes the cache.
    await b.evaluate(() => {
      selectedSettingsTab = "notificacoes";
      setView("Configurações");
    });
    await a.evaluate(async () => SocialMEIProfileSync.updatePreferences({ theme: "auto" }));
    await b.evaluate(async () => SocialMEIProfileSync.refresh("preferences"));
    await b.locator("#nvPref-quietFrom").fill("23:00");
    await b.locator("#nvPref-quietTo").fill("06:00");
    await b.locator("#nvSettingsPrimary").click();
    await b.waitForFunction(() => SocialMEIProfileSync.state().preferencesState === "conflict");
    assert.equal(await b.locator("#nvPref-quietFrom").inputValue(), "23:00");
    await b.locator("[data-sync-use-preferences]").click();
    await b.waitForFunction(() => SocialMEIProfileSync.state().preferencesState === "ready");
    assert.equal(await b.locator("#nvPref-quietFrom").inputValue(), "");
    // Repeated saves in the same form advance only that form's confirmed revision.
    await b.locator("#nvPref-quietFrom").fill("22:00");
    await b.locator("#nvPref-quietTo").fill("06:00");
    await b.locator("#nvSettingsPrimary").click();
    await b.waitForFunction(() => SocialMEIProfileSync.state().preferencesState !== "saving");
    assert.equal(await b.evaluate(() => SocialMEIProfileSync.state().preferencesState), "ready");
    await b.locator("#nvPref-quietTo").fill("07:00");
    await b.locator("#nvSettingsPrimary").click();
    await b.waitForFunction(() => SocialMEIProfileSync.state().preferencesState !== "saving");
    assert.equal(await b.evaluate(() => SocialMEIProfileSync.state().preferencesState), "ready");
    for (const width of [320, 390, 768, 1440])
      for (const theme of ["light", "dark"]) {
        await a.setViewportSize({ width, height: 1000 });
        await a.evaluate((theme) => {
          SocialMEIThemes.select(theme, { persist: false });
          selectedSettingsTab = "perfil";
          setView("Configurações");
        }, theme);
        assert(await a.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await a.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
        await a.screenshot({
          fullPage: true,
          path: path.join(output, `profile-${width}-${theme}.png`),
        });
      }
    await a.locator("[data-sync-refresh]").focus();
    await a.keyboard.press("Tab");
    assert(await a.evaluate(() => !!document.activeElement.closest("#settingsPanel")));
    identity.papel = "viewer";
    await b.reload();
    await b.evaluate(() => SocialMEIProfileSync.ready);
    await settings(b);
    assert(await b.locator("[data-business-profile-edit]").isDisabled());
    assert.match(await b.locator("#profileSyncStatus").textContent(), /somente responsáveis/i);
    identity.papel = "owner";
    identity.negocio = { id: 99, slug: "outro", nome: "Outro negócio", configuracao: {} };
    await b.reload();
    await b.waitForFunction(
      () =>
        typeof SocialMEIAuth !== "undefined" &&
        SocialMEIAuth.current?.negocio.id === 99 &&
        document.body?.classList.contains("experience-app"),
    );
    await b.evaluate(() => SocialMEIProfileSync.ready);
    assert.equal(
      await b.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
      null,
    );
    assert.equal(await b.evaluate(() => SocialMEIProfileSync.state().preferences.theme), "auto");
    unavailable = true;
    await a.reload();
    await a.waitForFunction(() => document.body?.classList.contains("experience-app"));
    await a.evaluate(() => SocialMEIProfileSync.ready);
    await settings(a);
    assert(await a.locator("[data-business-profile-edit]").isDisabled());
    assert.match(await a.locator("#profileSyncStatus").textContent(), /preservados/);
    await a.screenshot({ path: path.join(output, "unavailable.png") });
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    return "Perfil sincronizado: importação revisada/cancelada, legado preservado, duas sessões, preferências com conflito e revisão do formulário, viewer, troca de workspace, API indisponível e oito layouts";
  } finally {
    for (const context of contexts) await context.close();
  }
};
