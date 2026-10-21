// Controlled same-origin account API only. Database/auth contracts run separately in Python.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function instagramIntegration(browser, origin) {
  const page = await browser.newPage({ reducedMotion: "reduce" });
  const profileAPI = require("./profile-sync-fixture.cjs")();
  const errors = [],
    external = [],
    writes = [],
    accounts = [],
    publications = [];
  let refuseNext = true,
    holdRefresh = false,
    releaseSubmit = null,
    holdSubmit = false;
  const delayedRefresh = [];
  const identity = {
    usuario: { id: 101, nome: "MEI fictício", email: "sandbox@example.test" },
    negocio: { id: 201, slug: "instagram-sandbox", nome: "Negócio fictício", configuracao: {} },
    papel: "owner",
    csrf_token: "a".repeat(64),
  };
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", async (route) => {
    const request = route.request(),
      url = new URL(request.url());
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
            instagramPublisher: { mode: "disabled" },
            instagramSimulation: { mode: "simulation" },
            clientes: { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "sandbox" },
          }) +
          ";",
      });
    if (!url.pathname.startsWith("/api/v1/")) return route.continue();
    if (request.method() !== "GET") {
      assert.equal(request.headers()["x-socialmei-csrf"], identity.csrf_token);
      assert.equal(request.headers()["content-type"], "application/json");
      writes.push({ path: url.pathname, body: request.postDataJSON() });
    }
    if (url.pathname === "/api/v1/auth/session") return route.fulfill({ json: identity });
    if (url.pathname === "/api/v1/auth/registration")
      return route.fulfill({ json: { mode: "open" } });
    if (["/api/v1/workspace-profile", "/api/v1/auth/preferences"].includes(url.pathname)) {
      assert.equal(request.method(), "GET");
      return profileAPI(route, identity);
    }
    const prefix = "/api/v1/instagram/simulation";
    if (
      holdRefresh &&
      request.method() === "GET" &&
      [prefix + "/accounts", prefix + "/publications"].includes(url.pathname)
    ) {
      const items = JSON.parse(
        JSON.stringify(url.pathname.endsWith("/accounts") ? accounts : publications),
      );
      await new Promise((resolve) =>
        delayedRefresh.push(async () => {
          await route.fulfill({ json: { items } });
          resolve();
        }),
      );
      return;
    }

    if (url.pathname === prefix + "/accounts") {
      if (request.method() === "POST")
        accounts.push({
          id: "00000000-0000-4000-8000-" + String(accounts.length + 1).padStart(12, "0"),
          label: request.postDataJSON().label,
        });
      return route.fulfill({
        status: request.method() === "POST" ? 201 : 200,
        json: request.method() === "POST" ? accounts.at(-1) : { items: accounts },
      });
    }
    if (url.pathname === prefix + "/publications") {
      if (request.method() === "GET") return route.fulfill({ json: { items: publications } });
      if (refuseNext) {
        refuseNext = false;
        return route.fulfill({ status: 503, json: { detail: "Falha simulada de teste" } });
      }
      if (holdSubmit) await new Promise((resolve) => (releaseSubmit = resolve));
      const body = request.postDataJSON();
      const prior = publications.find((p) => p.idempotency_key === body.idempotency_key);
      if (!prior)
        publications.push({
          ...body,
          id: "simulacao-ficticia",
          created_at: "2026-10-20T12:00:00Z",
          status: "simulated",
          published: false,
        });
      return route.fulfill({ status: prior ? 200 : 201, json: prior || publications.at(-1) });
    }
    assert.equal(request.method(), "GET", "No unrelated write may escape the simulation mocks");
    return route.fulfill({ json: [] });
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () => !!window.SocialMEIAuth?.current && document.body?.classList.contains("experience-app"),
    );
    await page.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
    await page.waitForFunction(() =>
      document
        .getElementById("instagramSimulationStatus")
        .textContent.includes("Simulação habilitada"),
    );
    assert(await page.locator("#instagramPublishPanel").isHidden());
    assert(await page.locator("#contentPublish").isDisabled());
    await page.locator("#instagramSimulationName").fill("Ateliê fictício");
    await page.locator("#instagramSimulationName").focus();
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.id), "instagramSimulationCreate");
    await page.keyboard.press("Enter");
    await page.waitForFunction(
      () => document.getElementById("instagramSimulationAccount").options.length === 1,
    );
    // With multiple accounts, the selected account must survive request and refresh.
    await page.locator("#instagramSimulationName").fill("Segundo negócio fictício");
    await page.locator("#instagramSimulationCreate").click();
    await page.waitForFunction(
      () => document.getElementById("instagramSimulationAccount").options.length === 2,
    );
    const secondAccountId = accounts[1].id;
    await page.locator("#instagramSimulationAccount").selectOption(secondAccountId);
    await page.locator("#contentCaption").fill("Conteúdo sintético, sem publicação.");
    const png = await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 800;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#2255bb";
      ctx.fillRect(0, 0, 640, 800);
      return canvas.toDataURL("image/png").split(",")[1];
    });
    await page.locator("#contentMedia").setInputFiles({
      name: "ficticio.png",
      mimeType: "image/png",
      buffer: Buffer.from(png, "base64"),
    });
    await page.locator("#contentPreviewStage img").waitFor();
    await page.locator("#instagramSimulationSubmit").click();
    await page.waitForFunction(() =>
      document
        .getElementById("instagramSimulationStatus")
        .textContent.includes("Falha simulada de teste"),
    );
    assert.equal(publications.length, 0);
    assert.equal(await page.locator("#instagramSimulationAccount").inputValue(), secondAccountId);
    // An unrelated store refresh must not replace a pending retry's idempotency key.
    await page.evaluate(() => document.dispatchEvent(new CustomEvent("socialmei-data-change")));
    await page.waitForFunction(() =>
      document
        .getElementById("instagramSimulationStatus")
        .textContent.includes("Simulação habilitada"),
    );
    assert.equal(await page.locator("#instagramSimulationAccount").inputValue(), secondAccountId);
    await page.locator("#instagramSimulationSubmit").focus();
    assert.equal(
      await page.evaluate(() => document.activeElement.id),
      "instagramSimulationSubmit",
      "Retry must retain keyboard focus before Enter",
    );
    holdSubmit = true;
    await page.keyboard.press("Enter");
    const submitDeadline = Date.now() + 5000;
    while (!releaseSubmit && Date.now() < submitDeadline)
      await new Promise((resolve) => setImmediate(resolve));
    assert(releaseSubmit, "The retry POST must be in flight");
    holdRefresh = true;
    await page.evaluate(async () => {
      document.dispatchEvent(new CustomEvent("socialmei-data-change"));
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    holdRefresh = false;
    holdSubmit = false;
    releaseSubmit();
    await page.waitForFunction(() =>
      document
        .getElementById("instagramSimulationStatus")
        .textContent.includes("nada foi publicado"),
    );
    await page.waitForFunction(
      () => document.querySelectorAll("#instagramSimulationHistory p").length === 1,
    );
    await Promise.all(delayedRefresh.splice(0).map((release) => release()));
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)));
    assert.match(
      await page.locator("#instagramSimulationStatus").textContent(),
      /nada foi publicado/,
    );
    assert.equal(await page.locator("#instagramSimulationHistory p").count(), 1);

    assert.equal(publications.length, 1);
    assert.equal(publications[0].published, false);
    assert.equal(publications[0].account_id, secondAccountId);
    assert.equal(publications[0].caption, "Conteúdo sintético, sem publicação.");
    const attempts = writes.filter((w) => w.path.endsWith("/publications"));
    assert.equal(attempts.length, 2);
    assert.equal(attempts[0].body.idempotency_key, attempts[1].body.idempotency_key);
    assert.deepEqual(Object.keys(attempts[1].body.media[0]).sort(), ["mime", "name", "size"]);
    await page.waitForFunction(
      () => document.querySelectorAll("#instagramSimulationHistory p").length === 1,
    );
    assert.equal(await page.locator("#instagramSimulationHistory p").count(), 1);
    assert.match(await page.locator("#instagramSimulationHistory").textContent(), /SIMULADO/);
    const output = path.resolve(__dirname, "../test-results/integration");
    fs.mkdirSync(output, { recursive: true });
    for (const width of [1440, 390])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
          false,
        );
        await page
          .locator("#instagramSimulationPanel")
          .screenshot({ path: path.join(output, `instagram-simulation-${width}-${theme}.png`) });
      }
    // A read started before the next submission must not roll back its result/history.
    holdRefresh = true;
    await page.evaluate(() => document.dispatchEvent(new CustomEvent("socialmei-data-change")));
    await page.waitForFunction(
      () => !document.getElementById("instagramSimulationSubmit").disabled,
    );
    const refreshDeadline = Date.now() + 5000;
    while (delayedRefresh.length < 2 && Date.now() < refreshDeadline)
      await new Promise((resolve) => setImmediate(resolve));
    assert.equal(delayedRefresh.length, 2, "The background refresh must be in flight");
    holdRefresh = false;
    await page.locator("#contentCaption").fill("Outro conteúdo sintético.");
    await page.locator("#instagramSimulationSubmit").click();
    // Only the background GETs are held; the POST and its subsequent history read run normally.
    await page.waitForFunction(
      () => document.querySelectorAll("#instagramSimulationHistory p").length === 2,
    );
    holdRefresh = false;
    await Promise.all(delayedRefresh.splice(0).map((release) => release()));
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)));
    assert.equal(
      await page.locator("#instagramSimulationHistory p").count(),
      2,
      "Late background reads must not overwrite the submitted history",
    );
    assert.match(
      await page.locator("#instagramSimulationStatus").textContent(),
      /nada foi publicado/,
    );

    assert.equal(publications.length, 2);
    assert.notEqual(publications[0].idempotency_key, publications[1].idempotency_key);
    await page.locator("#instagramSimulationAccount").selectOption(accounts[0].id);
    await page.locator("#instagramSimulationSubmit").click();
    await page.waitForFunction(
      () => document.querySelectorAll("#instagramSimulationHistory p").length === 3,
    );
    assert.equal(publications[2].account_id, accounts[0].id);
    assert.notEqual(publications[1].idempotency_key, publications[2].idempotency_key);
    identity.papel = "viewer";
    await page.reload();
    await page.waitForFunction(
      () => !!window.SocialMEIAuth?.current && document.body?.classList.contains("experience-app"),
    );
    await page.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
    await page.waitForFunction(
      () => document.getElementById("instagramSimulationAccount").options.length === 2,
    );
    assert(await page.locator("#instagramSimulationCreate").isDisabled());
    assert(
      await page.locator("#instagramSimulationSubmit").isDisabled(),
      "A viewer must not be offered a write action",
    );
    assert.match(await page.locator("#instagramSimulationStatus").textContent(), /somente leitura/);
    await page
      .locator("#instagramSimulationPanel")
      .screenshot({ path: path.join(output, "instagram-readonly.png") });
    assert.deepEqual(external, []);
    assert.deepEqual(errors, []);
    return "Instagram integrado: opt-in fictício, teclado, metadados, falha/repetição idempotente, histórico e desktop/mobile claro/escuro; sem transporte real";
  } catch (error) {
    const diagnostic = await page.evaluate(() => ({
      view: currentView,
      body: document.body.className,
      selectedAccount: document.getElementById("instagramSimulationAccount").value,
      active: document.activeElement.id || document.activeElement.tagName,
      status: document.getElementById("instagramSimulationStatus").textContent,
      disabled: document.getElementById("instagramSimulationSubmit").disabled,
      snapshot: !!SocialMEIContentStudio.simulationSnapshot(),
    }));
    console.error(
      "Instagram simulation diagnostic",
      JSON.stringify({
        ...diagnostic,
        writes: writes.map((w) => w.path),
        publications: publications.length,
        errors,
      }),
    );
    throw error;
  } finally {
    await page.close();
  }
};
