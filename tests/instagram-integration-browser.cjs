// Controlled same-origin account API only. Database/auth contracts run separately in Python.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function instagramIntegration(browser, origin) {
  const page = await browser.newPage({ reducedMotion: "reduce" });
  const errors = [],
    external = [],
    writes = [],
    accounts = [],
    publications = [];
  let refuseNext = true;
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
    const prefix = "/api/v1/instagram/simulation";
    if (url.pathname === prefix + "/accounts") {
      if (request.method() === "POST")
        accounts.push({
          id: "00000000-0000-4000-8000-000000000001",
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
    await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
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
    // An unrelated store refresh must not replace a pending retry's idempotency key.
    await page.evaluate(() => document.dispatchEvent(new CustomEvent("socialmei-data-change")));
    await page.waitForFunction(() =>
      document
        .getElementById("instagramSimulationStatus")
        .textContent.includes("Simulação habilitada"),
    );
    await page.locator("#instagramSimulationSubmit").focus();
    await page.keyboard.press("Enter");
    await page.waitForFunction(() =>
      document
        .getElementById("instagramSimulationStatus")
        .textContent.includes("nada foi publicado"),
    );
    assert.equal(publications.length, 1);
    assert.equal(publications[0].published, false);
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
    await page.locator("#contentCaption").fill("Outro conteúdo sintético.");
    await page.locator("#instagramSimulationSubmit").click();
    await page.waitForFunction(
      () => document.querySelectorAll("#instagramSimulationHistory p").length === 2,
    );
    assert.equal(publications.length, 2);
    assert.notEqual(publications[0].idempotency_key, publications[1].idempotency_key);
    assert.deepEqual(external, []);
    assert.deepEqual(errors, []);
    return "Instagram integrado: opt-in fictício, teclado, metadados, falha/repetição idempotente, histórico e desktop/mobile claro/escuro; sem transporte real";
  } finally {
    await page.close();
  }
};
