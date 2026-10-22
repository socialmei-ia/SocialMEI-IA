// Optional real HTTPS/API/PostgreSQL proof. Refuses any non-loopback target.
const assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path");
const { randomUUID } = require("node:crypto");
const { chromium } = require("playwright");
async function run(config) {
  const target = new URL(config.origin);
  assert(
    target.protocol === "https:" && ["localhost", "127.0.0.1", "[::1]"].includes(target.hostname),
  );
  const origin = target.origin,
    output = path.resolve(__dirname, "../test-results/profile-sync-real");
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  const contexts = [],
    errors = [],
    external = [],
    statuses = [];
  async function pageFor() {
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      httpCredentials: config.httpCredentials,
      reducedMotion: "reduce",
      locale: "pt-BR",
      viewport: { width: 1440, height: 1000 },
    });
    contexts.push(context);
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) {
        external.push(url.origin);
        return route.abort();
      }
      return route.continue();
    });
    page.on("response", (r) => {
      const p = new URL(r.url()).pathname;
      if (["/api/v1/workspace-profile", "/api/v1/auth/preferences"].includes(p))
        statuses.push({ path: p, method: r.request().method(), status: r.status() });
    });
    return page;
  }
  const ready = (page) =>
    page.waitForFunction(
      () =>
        !!window.SocialMEIAuth?.current &&
        !!window.SocialMEIProfileSync &&
        SocialMEIProfileSync.state().profileState === "ready" &&
        SocialMEIProfileSync.state().preferencesState === "ready",
    );
  const api = (page, url) => page.evaluate(async (url) => SocialMEIAuth.request(url), url);
  async function register(page, email) {
    await page.goto(origin + "/");
    await page.locator('[data-auth-tab="register"]').click();
    await page.locator("#registerName").fill("Empreendedor sintético QA78");
    await page.locator("#registerEmail").fill(email);
    await page.locator("#registerPhone").fill("11988776655");
    await page.locator("#registerPassword").fill("Disposable-qa78-password-123!");
    await page.locator("#xpRegisterForm [type=submit]").click();
    await page.locator(".contact-confirmation button[value=confirm]").click();
    await ready(page);
    await page.locator("[data-onboard-next]").click();
    await page.locator("#businessSegmentAlternative").evaluate((e) => (e.open = true));
    await page.locator("#obSegment").selectOption("barber");
    for (const step of [3, 4, 5, 6]) {
      await page.locator("[data-onboard-next]").click();
      await page.locator(`[data-onboard-panel="${step}"].is-active`).waitFor();
    }
    await page.locator("[data-onboard-next]").click();
    await page.waitForFunction(() => document.body?.classList.contains("experience-app"));
  }
  async function profileEditor(page, activity) {
    await page.evaluate(() => {
      selectedSettingsTab = "perfil";
      setView("Configurações");
    });
    await page.locator("[data-business-profile-edit]").click();
    await page.locator("#businessSegmentAlternative").evaluate((e) => (e.open = true));
    await page.locator("#obSegment").selectOption("other");
    await page.locator("#obActivity").fill(activity);
    for (const step of [3, 4, 5, 6]) {
      await page.locator("[data-onboard-next]").click();
      await page.locator(`[data-onboard-panel="${step}"].is-active`).waitFor();
    }
  }
  try {
    const a = await pageFor(),
      b = await pageFor(),
      other = await pageFor();
    const email = `qa78-${randomUUID()}@example.test`;
    await register(a, email);
    console.log("QA78: cadastro e perfil na API");
    await b.goto(origin + "/");
    await b.locator('[data-auth-tab="login"]').click();
    await b.locator("#loginEmail").fill(email);
    await b.locator("#loginPassword").fill("Disposable-qa78-password-123!");
    await b.locator("#xpLoginForm [type=submit]").click();
    await ready(b);
    assert.equal((await api(b, "/workspace-profile")).revision, 1);
    assert.equal(
      await b.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile.segment),
      "barber",
    );
    const cookiesA = await a.context().cookies(),
      cookiesB = await b.context().cookies();
    const sessionA = cookiesA.find((c) => c.httpOnly),
      sessionB = cookiesB.find((c) => c.httpOnly);
    assert(
      sessionA && sessionB && sessionA.value !== sessionB.value,
      "Independent authenticated sessions required",
    );
    await profileEditor(a, "Edição preservada do aparelho A");
    await b.evaluate(async () => {
      const repo = SocialMEIBusinessProfile.browserRepository(),
        p = repo.read();
      await repo.save(
        { ...p.profile, activity: "Outra sessão atualizou" },
        repo.scope(),
        p.revision,
      );
    });
    await a.locator("[data-onboard-next]").click();
    await a.locator("#businessProfileConflict").waitFor({ state: "visible" });
    assert.match(await a.locator("#obValidation").textContent(), /Outra sessão/);
    assert.equal(await a.locator("#obActivity").inputValue(), "Edição preservada do aparelho A");
    assert.equal((await api(a, "/workspace-profile")).profile.activity, "Outra sessão atualizou");
    assert.equal(await a.locator(".onboarding-footer #businessProfileConflict").count(), 0);
    assert.equal(await a.locator('[data-onboard-panel="6"] #businessProfileConflict').count(), 1);
    assert(
      await a.locator("#businessProfileConflict").evaluate((e) => e === document.activeElement),
    );
    await a.screenshot({ path: path.join(output, "conflict-preserved.png"), fullPage: true });
    await a.setViewportSize({ width: 390, height: 900 });
    await a.locator("#businessProfileConflict").scrollIntoViewIfNeeded();
    assert(await a.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert(
      await a
        .locator(".onboarding-footer")
        .evaluate((e) => e.getBoundingClientRect().height < innerHeight / 2),
    );
    await a.screenshot({ path: path.join(output, "conflict-390.png"), fullPage: true });
    await a.setViewportSize({ width: 1440, height: 1000 });
    await a.locator("[data-business-reload]").click();
    assert.equal(await a.locator("#obActivity").inputValue(), "Outra sessão atualizou");
    await a.locator("#businessSegmentAlternative").evaluate((e) => (e.open = true));
    await a.locator("#obSegment").selectOption("other");
    await a.locator("#obActivity").fill("Resposta sem conexão");
    for (const step of [3, 4, 5, 6]) {
      await a.locator("[data-onboard-next]").click();
      await a.locator(`[data-onboard-panel="${step}"].is-active`).waitFor();
    }
    await a.route("**/api/v1/workspace-profile", (route) =>
      route.request().method() === "PATCH" ? route.abort("failed") : route.continue(),
    );
    await a.locator("[data-onboard-next]").click();
    await a.waitForFunction(() =>
      document.getElementById("obValidation").textContent.includes("conexão"),
    );
    assert.equal(await a.locator("#obActivity").inputValue(), "Resposta sem conexão");
    await a.unroute("**/api/v1/workspace-profile");
    await a.locator("[data-onboard-next]").click();
    await a.waitForFunction(() => document.body?.classList.contains("experience-app"));
    await b.reload();
    await ready(b);
    assert.equal((await api(b, "/workspace-profile")).profile.activity, "Resposta sem conexão");
    console.log("QA78: duas sessões, conflito sem perda e recuperação de conexão");
    await a.evaluate(() => {
      selectedSettingsTab = "aparencia";
      setView("Configurações");
    });
    await a.locator('#settingsPanel [data-theme-apply="dark"]').click();
    await a.waitForFunction(
      () =>
        SocialMEIProfileSync.state().preferences.theme === "dark" &&
        SocialMEIProfileSync.state().preferencesState === "ready",
    );
    await b.reload();
    await ready(b);
    assert.equal(await b.evaluate(() => SocialMEIThemes.active), "dark");
    await a.evaluate(() => {
      selectedSettingsTab = "notificacoes";
      setView("Configurações");
    });
    await a.locator("#nvPref-quietFrom").fill("22:00");
    await a.locator("#nvPref-quietTo").fill("07:00");
    await a.locator('[data-nv-notification="message"]').click();
    await a.locator("#nvSettingsPrimary").click();
    await a.waitForFunction(() =>
      document.getElementById("nvSettingsFeedback").textContent.includes("salvas na conta"),
    );
    await b.reload();
    await ready(b);
    assert.equal(await b.evaluate(() => appData.prefs.notifications.quietFrom), "22:00");
    assert.equal(await b.evaluate(() => appData.prefs.notifications.message), false);
    await register(other, `qa78-other-${randomUUID()}@example.test`);
    assert.notEqual(
      (await api(a, "/workspace-profile")).profile.activity,
      (await api(other, "/workspace-profile")).profile.activity,
    );
    assert.equal((await api(other, "/auth/preferences")).preferences.theme, "auto");
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
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert(statuses.some((s) => s.status === 409));
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(
        {
          checks: [
            "Duas sessões autenticadas independentes sobre API/PostgreSQL reais",
            "Perfil e tema/avisos recuperados após recarga",
            "409 e rede indisponível preservam respostas",
            "Outro negócio isolado; nenhum dado real",
            "320/390/768/1440 claro/escuro",
          ],
          statuses,
          errors,
          external,
        },
        null,
        2,
      ),
    );
    console.log("QA78: prova real de sincronização aprovada");
  } catch (error) {
    for (const [i, c] of contexts.entries()) {
      const p = c.pages()[0];
      if (p) await p.screenshot({ path: path.join(output, `failure-${i}.png`) }).catch(() => {});
    }
    throw error;
  } finally {
    await browser.close();
  }
}
if (require.main === module)
  run(JSON.parse(fs.readFileSync(process.env.PROFILE_SYNC_QA_CONFIG, "utf8"))).catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
module.exports = run;
