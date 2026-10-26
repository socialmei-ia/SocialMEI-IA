/* Synthetic provider receipts with real native V22 controls; never calls Meta. */
const assert = require("node:assert/strict");
const clickFrame = require("./native-frame-pointer.cjs");
const fs = require("node:fs"),
  path = require("node:path");
module.exports = async function (browser, origin) {
  const output = path.join(__dirname, "../test-results/instagram-publisher");
  fs.mkdirSync(output, { recursive: true });
  for (const width of [1440, 390])
    for (const theme of ["light", "dark"]) {
      const page = await browser.newPage({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const errors = [],
        external = [],
        writes = [];
      let holdAccount = false,
        releaseAccount,
        published = false,
        hold = false,
        release;
      const requestId = [];
      const identity = {
        usuario: { id: 91, nome: "Teste", email: "test@example.test" },
        negocio: { id: 17, slug: "teste", nome: "Negócio fictício", configuracao: {} },
        papel: "owner",
        csrf_token: "a".repeat(64),
      };
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      page.on("pageerror", (e) => errors.push(e.message));
      await page.route("**/*", async (route) => {
        const req = route.request(),
          url = new URL(req.url());
        if (url.origin !== origin) {
          external.push(url.hostname);
          return route.abort();
        }
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        const p = url.pathname.replace("/api/v1", "");
        if (p === "/auth/session") return route.fulfill({ json: identity });
        if (req.method() !== "GET") {
          assert.equal(req.headers()["x-socialmei-csrf"], identity.csrf_token);
          writes.push({ path: p, body: req.postDataJSON() });
        }
        if (p === "/integrations/readiness")
          return route.fulfill({
            json: {
              source: "server",
              instagram: {
                oauth_available: true,
                incoming_available: false,
                publishing_available: true,
              },
            },
          });
        if (p === "/auth/preferences")
          return route.fulfill({ json: { preferences: {}, revision: 0 } });
        if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (p === "/instagram/meta/status")
          return route.fulfill({ json: { status: "connected", credential_available: true } });
        if (p === "/instagram/publishing/status")
          return route.fulfill({
            json: { available: true, connected: true, upload_available: true },
          });
        if (p === "/instagram/publishing/account") {
          if (holdAccount) await new Promise((resolve) => (releaseAccount = resolve));
          return route.fulfill({
            json: {
              username: "synthetic_profile",
              connection_id: "00000000-0000-4000-8000-000000000001",
            },
          });
        }
        if (p === "/instagram/publishing/upload") {
          assert(req.postDataJSON().image_base64.length > 10);
          return route.fulfill({ json: { media_id: "00000000-0000-4000-8000-000000000002" } });
        }
        if (p === "/instagram/publishing/image") {
          requestId.push(req.postDataJSON().request_id);
          if (hold) await new Promise((resolve) => (release = resolve));
          published = true;
          return route.fulfill({
            json: {
              id: "00000000-0000-4000-8000-000000000003",
              request_id: requestId[0],
              status: "published",
              media_id: "10002",
            },
          });
        }
        if (p === "/instagram/publishing/recent")
          return route.fulfill({
            json: {
              items: published
                ? [
                    {
                      id: "00000000-0000-4000-8000-000000000003",
                      request_id: requestId[0],
                      status: "published",
                      media_id: "10002",
                    },
                  ]
                : [],
            },
          });
        return route.fulfill({ json: [] });
      });
      const show = async () => {
        await page.goto(origin + "/frontend/socialmei-app.html#/config/integracoes");
        await page.waitForFunction(() => window.SocialMEIInstagramPublisher);
        await page.evaluate((t) => {
          S.theme = t === "light" ? "claro" : "escuro";
          applyTheme();
        }, theme);
        await page.evaluate(() => go("/divul"));
        const frame = page.frameLocator("#v iframe");
        await clickFrame(page, frame.locator("#k3"));
        await clickFrame(page, frame.locator("[data-instagram-publish]"));
        await page.getByText("Publicar no perfil @synthetic_profile", { exact: true }).waitFor();
      };
      try {
        await show();
        const dialog = page.getByRole("dialog", { name: "Publicar foto no Instagram" });
        const png = Buffer.from(
          await page.evaluate(() => {
            const c = document.createElement("canvas");
            c.width = c.height = 800;
            return c.toDataURL("image/png").split(",")[1];
          }),
          "base64",
        );
        await dialog
          .getByLabel("Selecionar foto")
          .setInputFiles({ name: "example.png", mimeType: "image/png", buffer: png });
        await dialog.getByLabel("Legenda").fill("Foto de teste sem publicação externa");
        await dialog.locator("img").waitFor();
        const size = await dialog.boundingBox();
        assert(size.x >= 0 && size.x + size.width <= width + 1);
        await page.screenshot({ path: path.join(output, `${width}-${theme}.png`) });
        hold = true;
        await dialog.getByRole("button", { name: "Confirmar publicação" }).click();
        await page.waitForFunction(
          () => document.querySelector('.ig-publish [type="submit"]').disabled,
        );
        await dialog
          .locator("form")
          .evaluate((form) =>
            form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
          );
        for (let i = 0; i < 100 && !release; i++) await page.waitForTimeout(20);
        assert(release, "The image publication must reach the provider fixture");
        release();
        await dialog.getByText("Publicado no Instagram! ID: 10002", { exact: true }).waitFor();
        assert.equal(requestId.length, 1, "Double-click must not create another publication");
        assert.equal(writes.filter((x) => x.path.endsWith("/upload")).length, 1);
        assert.equal(
          writes.find((x) => x.path.endsWith("/image")).body.connection_id,
          "00000000-0000-4000-8000-000000000001",
        );
        await page.reload();
        await page.waitForFunction(() => window.SocialMEIInstagramPublisher);
        const frame = page.frameLocator("#v iframe");
        await clickFrame(page, frame.locator("#k3"));
        await clickFrame(page, frame.locator("[data-instagram-publish]"));
        await page.getByText("Publicado no Instagram! ID: 10002", { exact: true }).waitFor();
        assert.equal(requestId.length, 1, "Reload resumes receipt lookup without sending");
        await page.getByRole("button", { name: "Preparar outra foto" }).click();
        await page.getByRole("button", { name: "Fechar", exact: true }).click();
        holdAccount = true;
        await clickFrame(page, frame.locator("[data-instagram-publish]"));
        await page.getByText("Confirmando o perfil…", { exact: true }).waitFor();
        assert(
          await page.getByRole("button", { name: "Confirmar publicação" }).isDisabled(),
          "A previous account cannot authorize a pending account lookup",
        );
        for (let i = 0; i < 100 && !releaseAccount; i++) await page.waitForTimeout(20);
        assert(releaseAccount);
        releaseAccount();
        await page.getByText("Publicar no perfil @synthetic_profile", { exact: true }).waitFor();
        assert(await page.getByRole("button", { name: "Confirmar publicação" }).isEnabled());
        assert.deepEqual(errors, []);
        assert.deepEqual(external, []);
      } catch (error) {
        await page.screenshot({ path: path.join(output, `failure-${width}-${theme}.png`) });
        throw error;
      } finally {
        await page.close();
      }
    }
  console.log(
    "Instagram publisher: local upload, preview, CSRF, duplicate click, reload receipt, 2 widths × 2 themes passed (synthetic provider).",
  );
};
