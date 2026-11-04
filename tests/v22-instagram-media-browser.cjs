/* Native account gallery; provider requests/images are synthetic and intercepted. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { waitForViewportFit, layoutSnapshot } = require("./v22-layout-ready.cjs");
module.exports = async (browser, origin) => {
  let cases = 0;
  for (const mode of ["pages", "empty", "error", "unsafe", "close", "scope"])
    for (const width of [390, 1440]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage(),
        errors = [],
        external = [];
      let requests = 0,
        release = null;
      const identity = {
        usuario: { id: 91, nome: "Operador", email: "operator@example.test" },
        negocio: { id: 17, nome: "Conta fictícia", slug: "synthetic", configuracao: {} },
        papel: "owner",
        csrf_token: "a".repeat(64),
      };
      const item = {
        id: "123",
        caption: "Legenda <script>window.galleryInjection=true</script>",
        media_type: "IMAGE",
        media_url: "https://scontent.cdninstagram.com/synthetic.jpg",
        thumbnail_url: null,
        permalink: "https://www.instagram.com/p/synthetic/",
        timestamp: "2026-10-31T10:00:00Z",
      };
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      await page.route("**/*", async (route) => {
        const request = route.request(),
          url = new URL(request.url());
        if (url.hostname === "scontent.cdninstagram.com")
          return route.fulfill({
            contentType: "image/svg+xml",
            body: '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="#777"/></svg>',
          });
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
        assert.equal(request.method(), "GET", "Gallery never sends or publishes");
        const path = url.pathname.replace("/api/v1", "");
        if (path === "/auth/session") return route.fulfill({ json: identity });
        if (path === "/auth/preferences")
          return route.fulfill({
            json: { preferences: { theme: width === 390 ? "dark" : "light" }, revision: 0 },
          });
        if (path === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (path === "/whatsapp/catalog/access") return route.fulfill({ json: { channels: [] } });
        if (path === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled" } });
        if (path === "/integrations/readiness")
          return route.fulfill({
            json: { source: "server", instagram: { oauth_available: false } },
          });
        if (path === "/instagram/media") {
          requests++;
          assert.equal(request.headers()["x-socialmei-identity"], "91:17");
          if (["close", "scope"].includes(mode))
            await new Promise((resolve) => {
              release = resolve;
            });
          if (mode === "error")
            return route.fulfill({
              status: 503,
              json: { detail: "Consulta indisponível; verifique a conexão Instagram." },
            });
          if (mode === "empty") return route.fulfill({ json: { items: [], next_cursor: null } });
          if (mode === "unsafe")
            return route.fulfill({
              json: {
                items: [
                  {
                    ...item,
                    media_url: "javascript:alert(1)",
                    permalink: "https://example.test/private?access_token=secret",
                  },
                ],
                next_cursor: null,
              },
            });
          if (requests > 1) {
            assert.equal(url.searchParams.get("after"), "opaque+/=");
            return route.fulfill({
              json: {
                items: [
                  item,
                  {
                    ...item,
                    id: "124",
                    caption: null,
                    media_type: "VIDEO",
                    media_url: null,
                    thumbnail_url: null,
                    timestamp: null,
                  },
                ],
                next_cursor: null,
              },
            });
          }
          return route.fulfill({
            json: { items: [item], next_cursor: mode === "pages" ? "opaque+/=" : null },
          });
        }
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/config/integracoes");
        const button = page.locator("[data-ig-media-open]").first();
        await button.waitFor();
        assert.equal(requests, 0, "No provider call before the user opens the gallery");
        await button.click();
        const box = page.locator("[data-ig-media-dialog]");
        await box.waitFor();
        if (["close", "scope"].includes(mode)) {
          await page.waitForFunction(() =>
            document.querySelector('[data-ig-media-dialog][aria-busy="true"]'),
          );
          if (mode === "scope")
            await page.evaluate(() => {
              SocialMEIAuth.current.negocio.id = 18;
              window.render();
            });
          else await page.keyboard.press("Escape");
          while (!release) await new Promise((resolve) => setTimeout(resolve, 10));
          release();
          await page.waitForTimeout(100);
          assert.equal(await box.count(), 0);
        } else {
          await page.locator('[data-ig-media-dialog][aria-busy="false"]').waitFor();
          if (mode === "pages") {
            assert.equal(await box.locator("article").count(), 1);
            await box.getByRole("button", { name: "Carregar mais", exact: true }).click();
            await box
              .getByText("2 publicações carregadas da conta conectada.", { exact: true })
              .waitFor();
            assert.equal(await box.locator("article").count(), 2);
            assert.equal(
              await box.getByRole("button", { name: "Carregar mais", exact: true }).isVisible(),
              false,
            );
            assert.equal(await box.locator("img").getAttribute("referrerpolicy"), "no-referrer");
            const output = path.join(__dirname, "../test-results/instagram-account-media");
            fs.mkdirSync(output, { recursive: true });
            await page.screenshot({
              path: path.join(output, `gallery-${width}.png`),
              fullPage: true,
              animations: "disabled",
            });
          } else if (mode === "empty")
            await box
              .getByText("Nenhuma publicação retornada pela Meta.", { exact: true })
              .waitFor();
          else if (mode === "error") {
            await box
              .getByText("Consulta indisponível; verifique a conexão Instagram.", { exact: true })
              .waitFor();
            assert.equal(await box.locator("article").count(), 0);
            await box.getByRole("button", { name: "Consultar novamente", exact: true }).click();
            await page.waitForFunction(() =>
              document.querySelector('[data-ig-media-dialog][aria-busy="false"]'),
            );
            assert.equal(requests, 2);
          } else {
            assert.equal(await box.locator("img,a").count(), 0);
            assert.equal(await page.evaluate(() => window.galleryInjection), undefined);
          }
          assert.equal(
            await box.evaluate((node) => node.scrollWidth <= node.clientWidth + 1),
            true,
          );
          await box.getByRole("button", { name: "Fechar", exact: true }).click();
        }
        await waitForViewportFit(page);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
          true,
          JSON.stringify(await layoutSnapshot(page)),
        );
        assert.deepEqual(errors, []);
        assert.deepEqual(external, []);
        cases++;
      } finally {
        if (release) release();
        await context.close();
      }
    }
  return { cases, real_provider_requests: 0, publication_writes: 0 };
};
