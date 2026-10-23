const { revealContentControl, contentDock } = require("./content-test-ui.cjs");
const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  const page = await browser.newPage({ reducedMotion: "reduce" }),
    errors = [],
    writes = [];
  const identity = {
    usuario: { id: 101, nome: "Pessoa teste", email: "teste@example.test" },
    negocio: { id: 201, slug: "test", nome: "Negócio fictício", configuracao: {} },
    papel: "owner",
    csrf_token: "a".repeat(64),
  };
  let data = {
      workspace_id: 201,
      revision: 0,
      instagram: {
        username: "",
        account_type: "unknown",
        meta_app_status: "unknown",
        test_participants: [],
        reply_mode: "review",
      },
      connected: false,
      transport: "none",
      readiness: { blockers: ["OAuth não configurado"] },
    },
    fail = false,
    offline = false;
  const profile = require("./profile-sync-fixture.cjs")();
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    await page.route("**/*", (route) => {
      const req = route.request(),
        url = new URL(req.url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "application/javascript",
          body:
            "const SOCIALMEI_CONFIG=" +
            JSON.stringify({
              n8nMessagesUrl: null,
              auth: { mode: "remote", apiBaseUrl: "/api/v1" },
            }) +
            ";",
        });
      if (!url.pathname.startsWith("/api/v1/")) return route.continue();
      if (url.pathname === "/api/v1/auth/session") return route.fulfill({ json: identity });
      if (url.pathname === "/api/v1/auth/registration")
        return route.fulfill({ json: { mode: "open" } });
      if (["/api/v1/workspace-profile", "/api/v1/auth/preferences"].includes(url.pathname))
        return profile(route, identity);
      if (url.pathname === "/api/v1/integrations/setup") {
        if (offline) return route.fulfill({ status: 503, json: { detail: "Technical offline" } });
        if (req.method() === "PUT") {
          const body = req.postDataJSON();
          writes.push(body);
          assert.equal(req.headers()["x-socialmei-csrf"], identity.csrf_token);
          if (fail)
            return route.fulfill({
              status: 409,
              json: { detail: "Preparação mudou. Atualize antes de salvar." },
            });
          assert.equal(body.expected_revision, data.revision);
          data = { ...data, revision: data.revision + 1, instagram: body.instagram };
        }
        return route.fulfill({ json: data });
      }
      return route.fulfill({ json: [] });
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () => !!SocialMEIAuth.current && document.body.classList.contains("experience-app"),
    );
    await page.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
    await contentDock(page, "connections");
    await page.waitForFunction(() => !document.getElementById("integrationSetupSave").disabled);
    await revealContentControl(page, "#integrationUsername");
    await page.locator("#integrationUsername").fill("@negocio.teste");
    await revealContentControl(page, "#integrationAccountType");
    await page.locator("#integrationAccountType").selectOption("business");
    await revealContentControl(page, "#integrationSetupSave");
    await page.locator("#integrationSetupSave").click();
    await page.waitForFunction(() =>
      document.getElementById("integrationSetupStatus").textContent.includes("Preparação salva"),
    );
    assert.equal(writes[0].instagram.username, "negocio.teste");
    assert.equal(writes[0].expected_revision, 0);
    assert.equal(data.connected, false);
    await page.reload();
    await page.waitForFunction(() => !!SocialMEIAuth.current);
    await page.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
    await contentDock(page, "connections");
    await page.waitForFunction(
      () => document.getElementById("integrationUsername").value === "negocio.teste",
    );
    fail = true;
    await revealContentControl(page, "#integrationUsername");
    await page.locator("#integrationUsername").fill("edicao.preservada");
    await revealContentControl(page, "#integrationSetupSave");
    await page.locator("#integrationSetupSave").click();
    await page.waitForFunction(() =>
      document.getElementById("integrationSetupStatus").textContent.includes("preparação mudou"),
    );
    assert.equal(await page.locator("#integrationUsername").inputValue(), "edicao.preservada");
    offline = true;
    await revealContentControl(page, "#integrationSetupRefresh");
    await page.locator("#integrationSetupRefresh").click();
    await page.waitForFunction(() =>
      document
        .getElementById("integrationSetupStatus")
        .textContent.includes("temporariamente indisponível"),
    );
    assert.equal(await page.locator("#integrationUsername").inputValue(), "edicao.preservada");
    assert.equal(
      data.instagram.username,
      "negocio.teste",
      "Failed request must not save edited input",
    );
    assert.equal(data.revision, 1);
    assert.equal(
      await page.evaluate(() =>
        Object.keys(localStorage).some((key) => /integration.*setup/i.test(key)),
      ),
      false,
      "Remote failure must not create a local setup copy",
    );
    await page.evaluate(() => {
      SocialMEIAuth.current.papel = "viewer";
      document.dispatchEvent(new Event("socialmei-data-change"));
    });
    // Role-only changes must also reapply read-only controls.
    assert(await page.locator("#integrationSetupSave").isDisabled());
    assert(await page.locator("#integrationUsername").isDisabled());
    assert.deepEqual(errors, []);
    return {
      integrationSetup:
        "public account preparation persisted/reloaded, CAS conflict preserves input, viewer readonly, no transport PASS",
    };
  } finally {
    await page.close();
  }
};
