const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function contentPreparation(browser, origin) {
  const output = path.resolve(__dirname, "../test-results/content-preparation");
  fs.mkdirSync(output, { recursive: true });
  const errors = [],
    external = [],
    writes = [];
  const local = await browser.newPage({ reducedMotion: "reduce" });
  const remote = await browser.newPage({ reducedMotion: "reduce" });
  const profileAPI = require("./profile-sync-fixture.cjs")();
  const identity = {
    usuario: { id: 101, nome: "Pessoa fictícia", email: "fixture@example.test" },
    negocio: { id: 201, slug: "content-fixture", nome: "Negócio fictício", configuracao: {} },
    papel: "owner",
    csrf_token: "a".repeat(64),
  };
  const prefix = "/api/v1/content/preparation";
  const accounts = [
    { id: "00000000-0000-4000-8000-000000000001", label: "Conta fictícia A" },
    { id: "00000000-0000-4000-8000-000000000002", label: "Conta fictícia B" },
  ];
  const jobs = [];
  let failCreate = true,
    offline = false,
    wrongWorkspace = false,
    nextConflict = false;
  try {
    for (const page of [local, remote]) page.on("pageerror", (e) => errors.push(e.message));
    await local.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) {
        external.push(url.origin);
        return route.abort();
      }
      assert.equal(
        route.request().method(),
        "GET",
        "Default local preparation must never call a provider or write API",
      );
      return route.continue();
    });
    await local.goto(origin + "/frontend/socialmei-app.html");
    await local.locator('[data-xp-go="app"]').first().click();
    await local.evaluate(() => setView("Divulgação"));
    assert(await local.locator("#preparationSchedule").isDisabled());
    const flowOrder = await local.evaluate(() => {
      const ids = [
        "preparationTopic",
        "preparationCaptions",
        "contentTitle",
        "contentCaption",
        "contentMedia",
        "preparationReviewed",
        "preparationSchedule",
      ];
      return ids.every(
        (id, i) =>
          !i ||
          !!(
            document
              .getElementById(ids[i - 1])
              .compareDocumentPosition(document.getElementById(id)) &
            Node.DOCUMENT_POSITION_FOLLOWING
          ),
      );
    });
    assert(
      flowOrder,
      "Native flow must keep idea → caption → media → review → schedule in DOM/keyboard order",
    );
    await local.locator("#preparationTopic").fill("Corte masculino");
    await local.locator("#preparationCaptions").focus();
    await local.keyboard.press("Enter");
    assert.equal(await local.locator("#preparationAlternatives > div").count(), 3);
    await local.locator("#preparationAlternatives button").first().click();
    assert((await local.locator("#contentCaption").inputValue()).includes("Corte masculino"));
    assert.equal(await local.evaluate(() => document.activeElement.id), "contentCaption");
    assert((await local.locator("#preparationStatus").textContent()).includes("sem IA externa"));
    for (const width of [390, 1440])
      for (const theme of ["light", "dark"]) {
        await local.setViewportSize({ width, height: 1000 });
        await local.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        await local.locator("#contentPreparationHeading").scrollIntoViewIfNeeded();
        const geometry = await local.evaluate(() => ({
          w: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth,
        }));
        assert(geometry.scroll <= geometry.w + 1, `No horizontal overflow ${width}/${theme}`);
        await local.screenshot({
          path: path.join(output, `preparation-${width}-${theme}.png`),
          fullPage: true,
        });
        await local.screenshot({
          path: path.join(output, `preparation-${width}-${theme}-viewport.png`),
        });
      }
    await remote.route("**/*", async (route) => {
      const req = route.request(),
        url = new URL(req.url()),
        method = req.method();
      if (url.origin !== origin) {
        external.push(url.origin);
        return route.abort();
      }
      if (url.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "application/javascript",
          body:
            "const SOCIALMEI_CONFIG=" +
            JSON.stringify({
              n8nMessagesUrl: null,
              auth: { mode: "remote", apiBaseUrl: "/api/v1" },
              contentPreparation: { mode: "simulation" },
              clientes: { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "fixture" },
            }) +
            ";",
        });
      if (!url.pathname.startsWith("/api/v1/")) return route.continue();
      if (url.pathname === "/api/v1/auth/session") return route.fulfill({ json: identity });
      if (url.pathname === "/api/v1/auth/registration")
        return route.fulfill({ json: { mode: "open" } });
      if (["/api/v1/workspace-profile", "/api/v1/auth/preferences"].includes(url.pathname))
        return profileAPI(route, identity);
      if (!url.pathname.startsWith(prefix)) {
        assert.equal(method, "GET");
        return route.fulfill({ json: [] });
      }
      if (method !== "GET") {
        assert.equal(req.headers()["x-socialmei-csrf"], identity.csrf_token);
        writes.push({ path: url.pathname, body: req.postDataJSON() });
      }
      if (offline) return route.fulfill({ status: 503, json: { detail: "Fixture offline" } });
      const envelope = { workspace_id: wrongWorkspace ? 999 : identity.negocio.id };
      if (url.pathname === prefix + "/status")
        return route.fulfill({
          json: { ...envelope, mode: "simulation", transport: "none", published: false },
        });
      if (url.pathname === prefix + "/accounts")
        return route.fulfill({ json: { ...envelope, items: accounts } });
      if (url.pathname === prefix + "/jobs" && method === "GET")
        return route.fulfill({ json: { ...envelope, items: jobs } });
      if (url.pathname === prefix + "/jobs" && method === "POST") {
        if (failCreate) {
          failCreate = false;
          return route.fulfill({
            status: 503,
            json: { detail: "Resposta temporariamente indisponível" },
          });
        }
        const body = req.postDataJSON();
        const old = jobs.find((j) => j.idempotency_key === body.idempotency_key);
        const row = old || {
          ...body,
          ...envelope,
          id: "00000000-0000-4000-8000-000000000011",
          revision: 1,
          attempts: 0,
          published: false,
          created_at: new Date().toISOString(),
          events: [{ status: body.status }],
        };
        if (!old) jobs.push(row);
        return route.fulfill({ status: old ? 200 : 201, json: row });
      }
      const job = jobs.find((j) => url.pathname.startsWith(prefix + "/jobs/" + j.id));
      if (job) {
        const body = method === "GET" ? null : req.postDataJSON();
        if (method === "GET") return route.fulfill({ json: { ...job, ...envelope } });
        if (nextConflict || body.revision !== job.revision) {
          nextConflict = false;
          return route.fulfill({
            status: 409,
            json: { detail: "Preparação mudou. Atualize o histórico." },
          });
        }
        if (url.pathname.endsWith("/cancel")) job.status = "cancelled";
        else Object.assign(job, body);
        job.revision++;
        job.events.push({ status: job.status });
        return route.fulfill({ json: { ...job, ...envelope } });
      }
      assert.fail("Unexpected preparation request: " + method + " " + url.pathname);
    });
    await remote.goto(origin + "/frontend/socialmei-app.html");
    await remote.waitForFunction(
      () => !!SocialMEIAuth.current && document.body.classList.contains("experience-app"),
    );
    await remote.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
    await remote.waitForFunction(() => !document.getElementById("preparationSave").disabled);
    await remote.locator("#contentTitle").fill("Conteúdo fictício");
    await remote.locator("#contentCaption").fill("Legenda revisável");
    await remote.locator("#preparationSave").click();
    await remote.waitForFunction(() =>
      document.getElementById("preparationStatus").textContent.includes("temporariamente"),
    );
    assert.equal(jobs.length, 0);
    await remote.locator("#preparationSave").click();
    await remote.waitForFunction(() =>
      document.getElementById("preparationHistory").textContent.includes("Conteúdo fictício"),
    );
    assert.equal(
      writes[0].body.idempotency_key,
      writes[1].body.idempotency_key,
      "Lost response keeps operation key",
    );
    await remote.locator("#preparationAccount").selectOption(accounts[1].id);
    const png = await remote.evaluate(() => {
      const c = document.createElement("canvas");
      c.width = 20;
      c.height = 20;
      return c.toDataURL("image/png").split(",")[1];
    });
    await remote.locator("#contentMedia").setInputFiles({
      name: "fixture.png",
      mimeType: "image/png",
      buffer: Buffer.from(png, "base64"),
    });
    await remote.locator("#contentPreviewStage img").waitFor();
    await remote.locator("#preparationWhen").fill("2026-12-01T10:30");
    await remote.locator("#preparationReviewed").check();
    await remote.locator("#preparationSchedule").click();
    await remote.waitForFunction(() =>
      document.getElementById("preparationStatus").textContent.includes("Agendado"),
    );
    assert.equal(jobs.length, 1);
    assert.equal(jobs[0].account_id, accounts[1].id);
    assert.equal(jobs[0].status, "scheduled");
    assert.equal(jobs[0].scheduled_for, "2026-12-01T13:30:00.000Z");
    assert.equal(await remote.locator("#preparationAccount").inputValue(), accounts[1].id);
    nextConflict = true;
    await remote.locator("#contentCaption").fill("Alteração em outra sessão");
    await remote.locator("#preparationSave").click();
    await remote.waitForFunction(() =>
      document.getElementById("preparationStatus").textContent.includes("preparação mudou"),
    );
    assert.equal(jobs[0].status, "scheduled");
    await remote.locator("#contentWorkspace-agenda").click();
    await remote.locator('[data-preparation-action="cancel"]').click();
    await remote.waitForFunction(() =>
      document.getElementById("preparationHistory").textContent.includes("Cancelado"),
    );
    assert.equal(jobs[0].status, "cancelled");
    offline = true;
    await remote.locator("#preparationRefresh").click();
    await remote.waitForFunction(() =>
      document
        .getElementById("preparationStatus")
        .textContent.includes("temporariamente indisponível"),
    );
    assert(await remote.locator("#preparationSave").isDisabled());
    offline = false;
    wrongWorkspace = true;
    await remote.locator("#preparationRefresh").click();
    await remote.waitForFunction(() =>
      document.getElementById("preparationStatus").textContent.includes("não pertence"),
    );
    assert.equal(await remote.locator("#preparationHistory li").count(), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    return {
      contentPreparation:
        "local fixture captions, explicit remote simulation, scoped jobs, idempotency, CAS, cancel, offline, workspace response fencing, desktop/mobile light/dark PASS",
    };
  } finally {
    await local.close();
    await remote.close();
  }
};
