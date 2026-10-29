// Real V22 HTTPS/API/PostgreSQL proof. Refuses every non-loopback target.
const assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path");
const { randomUUID } = require("node:crypto");
const { chromium } = require("playwright");
const { waitForViewportFit, layoutSnapshot } = require("./v22-layout-ready.cjs");

async function run(config) {
  const target = new URL(config.origin);
  assert(
    target.protocol === "https:" && ["localhost", "127.0.0.1", "[::1]"].includes(target.hostname),
    "Only local disposable HTTPS is accepted",
  );
  const origin = target.origin,
    output = path.resolve(__dirname, "../test-results/profile-sync-real"),
    password = "Disposable-qa78-password-123!";
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
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) {
        external.push(url.origin);
        return route.abort();
      }
      return route.continue();
    });
    page.on("response", (response) => {
      const pathname = new URL(response.url()).pathname;
      if (["/api/v1/workspace-profile", "/api/v1/auth/preferences"].includes(pathname))
        statuses.push({
          path: pathname,
          method: response.request().method(),
          status: response.status(),
        });
    });
    return page;
  }
  async function ready(page) {
    await page.waitForFunction(() => !!window.SocialMEIV22?.identity);
    await page.evaluate(() => SocialMEIV22.ready);
    assert.equal(await page.locator("#app").getAttribute("hidden"), null);
  }
  const api = (page, url, method = "GET", value) =>
    page.evaluate(async ({ url, method, value }) => SocialMEIAuth.request(url, method, value), {
      url,
      method,
      value,
    });
  async function review(page, extraOffer = false) {
    await page.locator("#oNeg").waitFor();
    await page.waitForFunction(() => document.getElementById("oNeg").value.length > 0);
    await page.locator('[data-area="beleza"]').click();
    await page.locator('[data-tipo="servicos"]').click();
    await page.locator('[data-ob="prox"]').click();
    const cut = page.locator('[data-of="Corte e escova"]');
    if ((await cut.getAttribute("aria-pressed")) !== "true") await cut.click();
    if (extraOffer) {
      const extra = page.locator('[data-of="Manicure e pedicure"]');
      if ((await extra.getAttribute("aria-pressed")) !== "true") await extra.click();
    }
    for (let step = 0; step < 3; step++) await page.locator('[data-ob="prox"]').click();
    await page.locator('[data-ob="fim"]').waitFor();
  }
  async function register(page, email) {
    await page.goto(origin + "/frontend/entrada.html#/cadastro");
    await page.locator("#cNome").fill("Empreendedor sintético QA78");
    await page.locator("#cMail").fill(email);
    await page.locator("#cPass").fill(password);
    await page.locator("#cTermos").check();
    await page.locator("#fC [type=submit]").click();
    await page.waitForURL("**/entrada.html?setup=1#/comecar");
    await review(page);
    await page.locator('[data-ob="fim"]').click();
    await page.waitForURL("**/socialmei-app.html#/bemvindo");
    await ready(page);
  }
  async function edit(page) {
    const loaded = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/workspace-profile" &&
        response.request().method() === "GET",
    );
    await page.goto(origin + "/frontend/entrada.html?setup=1&qa78=" + randomUUID() + "#/comecar");
    await loaded;
    await page.locator("#obCard").waitFor();
    if (!(await page.locator("#oNeg").isVisible()))
      await page.locator('[data-ir="0"]').first().click();
    await review(page, true);
  }
  function profileResponse(response) {
    return (
      new URL(response.url()).pathname === "/api/v1/workspace-profile" &&
      response.request().method() === "PATCH"
    );
  }
  try {
    const a = await pageFor(),
      b = await pageFor(),
      other = await pageFor(),
      email = `qa78-${randomUUID()}@example.test`;
    await register(a, email);
    console.log("QA78: cadastro V22 e perfil persistidos na API");
    await b.goto(origin + "/frontend/entrada.html#/entrar");
    await b.locator("#eMailL").fill(email);
    await b.locator("#ePassL").fill(password);
    await b.locator("#fE [type=submit]").click();
    await b.waitForURL("**/socialmei-app.html#/inicio");
    await ready(b);
    const initial = await api(b, "/workspace-profile");
    assert.equal(initial.revision, 1);
    assert.equal(initial.profile.segment, "hairdresser");
    const sessionA = (await a.context().cookies()).find((cookie) => cookie.httpOnly),
      sessionB = (await b.context().cookies()).find((cookie) => cookie.httpOnly);
    assert(
      sessionA && sessionB && sessionA.value !== sessionB.value,
      "Independent authenticated sessions required",
    );
    console.log("QA78: duas sessões HttpOnly independentes no mesmo negócio");

    await edit(a);
    await api(b, "/workspace-profile", "PATCH", {
      schema_version: 1,
      expected_revision: initial.revision,
      profile: { ...initial.profile, activity: "Atualização da outra sessão" },
    });
    const conflict = a.waitForResponse(profileResponse);
    await a.locator('[data-ob="fim"]').click();
    assert.equal((await conflict).status(), 409);
    await a.locator(".toast").waitFor();
    assert.match(await a.locator("#obCard").textContent(), /Manicure e pedicure/);
    assert.match(a.url(), /entrada.html/);
    assert.equal(
      (await api(b, "/workspace-profile")).profile.activity,
      "Atualização da outra sessão",
    );
    await a.screenshot({ path: path.join(output, "conflict-preserved.png"), fullPage: true });
    console.log("QA78: conflito 409 preserva a revisão do onboarding V22");

    // Explicit reload gets the current revision; the user reviews before saving again.
    await edit(a);
    await a.route("**/api/v1/workspace-profile", (route) =>
      route.request().method() === "PATCH" ? route.abort("failed") : route.continue(),
    );
    const failed = a.waitForEvent(
      "requestfailed",
      (request) =>
        new URL(request.url()).pathname === "/api/v1/workspace-profile" &&
        request.method() === "PATCH",
    );
    await a.locator('[data-ob="fim"]').click();
    await failed;
    await a.locator(".toast").waitFor();
    assert.match(await a.locator("#obCard").textContent(), /Manicure e pedicure/);
    assert.match(a.url(), /entrada.html/);
    await a.screenshot({ path: path.join(output, "offline-preserved.png"), fullPage: true });
    await a.unroute("**/api/v1/workspace-profile");
    const saved = a.waitForResponse(profileResponse);
    await a.locator('[data-ob="fim"]').click();
    assert.equal((await saved).status(), 200);
    await a.waitForURL("**/socialmei-app.html#/bemvindo");
    await ready(a);
    await b.reload();
    await ready(b);
    const reloaded = await api(b, "/workspace-profile");
    assert(reloaded.profile.services.includes("Manicure e pedicure"));
    assert.equal(await b.evaluate(() => S.biz.seg), "Atualização da outra sessão");
    console.log("QA78: falha de rede preservada; outra sessão lê perfil após recarga");

    await a.goto(origin + "/frontend/socialmei-app.html#/config/aparencia");
    await ready(a);
    const themeSaved = a.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/auth/preferences" &&
        response.request().method() === "PATCH",
    );
    await a.locator('[data-a="tema:escuro"]').click();
    assert.equal((await themeSaved).status(), 200);
    await b.reload();
    await ready(b);
    assert.equal(await b.evaluate(() => S.theme), "escuro");

    // Notification fields are verified through the API, not legacy settings controls.
    const preferences = await api(a, "/auth/preferences");
    await api(a, "/auth/preferences", "PATCH", {
      schema_version: 1,
      expected_revision: preferences.revision,
      preferences: {
        ...preferences.preferences,
        notifications: {
          ...preferences.preferences.notifications,
          quietFrom: "22:00",
          quietTo: "07:00",
          message: false,
        },
      },
    });
    await b.reload();
    await ready(b);
    const notices = (await api(b, "/auth/preferences")).preferences.notifications;
    assert.equal(notices.quietFrom, "22:00");
    assert.equal(notices.message, false);
    await register(other, `qa78-other-${randomUUID()}@example.test`);
    assert.notEqual(
      (await api(a, "/workspace-profile")).profile.activity,
      (await api(other, "/workspace-profile")).profile.activity,
    );
    assert.equal((await api(other, "/auth/preferences")).preferences.theme, "auto");
    console.log("QA78: tema na UI, preferências pela API e outro workspace isolado");

    for (const width of [320, 390, 768, 1440])
      for (const theme of ["claro", "escuro"]) {
        await a.setViewportSize({ width, height: 1000 });
        await waitForViewportFit(a);
        await a.evaluate((theme) => {
          S.theme = theme;
          applyTheme();
          render();
        }, theme);
        try {
          await a.waitForFunction(
            () => Math.abs(document.body.getBoundingClientRect().width - innerWidth) <= 1,
            null,
            { timeout: 5000 },
          );
        } catch (error) {
          console.log("QA78: geometria não estabilizou", await layoutSnapshot(a));
          console.log(
            await a.evaluate(() => ({
              inlineWidth: document.body.style.width,
              computedWidth: getComputedStyle(document.body).width,
              minWidth: getComputedStyle(document.body).minWidth,
              transform: getComputedStyle(document.body).transform,
              transition: getComputedStyle(document.body).transition,
            })),
          );
          throw error;
        }
        const layout = await layoutSnapshot(a);
        assert.equal(layout.scrollWidth > layout.width + 1, false, JSON.stringify(layout));
        await a.screenshot({
          fullPage: true,
          path: path.join(output, `profile-${width}-${theme}.png`),
        });
      }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert(statuses.some((status) => status.status === 409));
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(
        {
          checks: [
            "Registro/login V22 e duas sessões HttpOnly independentes sobre API/PostgreSQL",
            "Perfil e tema recuperados pela UI após recarga",
            "409 e rede indisponível preservam revisão do onboarding V22",
            "Preferências de avisos verificadas pela API; outro negócio isolado",
            "320/390/768/1440 claro/escuro; sem requests externos",
          ],
          limitations: ["Não cobre os formulários e globals removidos do shell legado"],
          statuses,
          errors,
          external,
        },
        null,
        2,
      ),
    );
    console.log("QA78: prova real de sincronização V22 aprovada");
  } catch (error) {
    for (const [index, context] of contexts.entries()) {
      const page = context.pages()[0];
      if (page)
        await page.screenshot({ path: path.join(output, `failure-${index}.png`) }).catch(() => {});
    }
    throw error;
  } finally {
    await browser.close();
  }
}
if (require.main === module)
  run(JSON.parse(fs.readFileSync(process.env.PROFILE_SYNC_QA_CONFIG, "utf8"))).catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
module.exports = run;
