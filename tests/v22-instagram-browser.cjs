/* Controlled account/provider responses. No live Meta requests or real messages. */
const assert = require("node:assert/strict");
module.exports = async function (browser, origin) {
  const fs = require("node:fs"),
    path = require("node:path");
  const output = path.join(__dirname, "../test-results/instagram-native");
  fs.mkdirSync(output, { recursive: true });
  for (const mode of [
    "disabled",
    "connect",
    "connect-frame",
    "connected",
    "forged-callback",
    "successful-callback",
    "failed-callback",
    "invalid-url",
    "member",
  ]) {
    const page = await browser.newPage({
      viewport: { width: 390, height: 1000 },
      reducedMotion: "reduce",
    });
    const errors = [],
      posts = [],
      external = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
    const state = "s".repeat(43);
    const identity = {
      usuario: { id: 91, nome: "Teste", email: "test@example.test" },
      negocio: { id: 17, nome: "Negócio de teste", slug: "teste", configuracao: {} },
      papel: mode === "member" ? "member" : "owner",
      csrf_token: "a".repeat(64),
    };
    await page.route("**/*", (route) => {
      const request = route.request(),
        url = new URL(request.url());
      if (url.origin !== origin) {
        external.push(url.hostname);
        if (url.hostname === "www.instagram.com" && ["connect", "connect-frame"].includes(mode))
          return route.fulfill({
            contentType: "text/html",
            body: "<h1>Autorização oficial simulada no teste</h1>",
          });
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
      assert.equal(request.headers()["x-socialmei-identity"], "91:17");
      if (p === "/auth/preferences")
        return route.fulfill({
          json: { schema_version: 1, revision: 0, preferences: { theme: "dark" } },
        });
      if (p === "/workspace-profile")
        return route.fulfill({ json: { schema_version: 1, revision: 0, profile: null } });
      if (p === "/message-enrichment/capabilities")
        return route.fulfill({ json: { mode: "disabled" } });
      if (p === "/integrations/readiness")
        return route.fulfill({
          json: {
            source: "server",
            instagram: {
              oauth_available: !["disabled", "forged-callback"].includes(mode),
              incoming_available: false,
              publishing_available: false,
            },
          },
        });
      if (p === "/instagram/meta/status")
        return route.fulfill({
          json: {
            status: ["connected", "successful-callback"].includes(mode)
              ? "connected"
              : "disconnected",
            credential_available: ["connected", "successful-callback"].includes(
              mode,
            ),
          },
        });
      if (p === "/instagram/meta/oauth/start") {
        assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
        posts.push(p);
        const authorization = new URL("https://www.instagram.com/oauth/authorize");
        authorization.search = new URLSearchParams({
          client_id: "12345",
          redirect_uri: origin + "/api/v1/instagram/meta/oauth/return",
          response_type: "code",
          scope:
            "instagram_business_basic,instagram_business_manage_messages,instagram_business_content_publish",
          state,
        }).toString();
        return route.fulfill({
          json: {
            state,
            authorization_url:
              mode === "invalid-url"
                ? "https://attacker.example/oauth/authorize"
                : authorization.href,
          },
        });
      }
      return route.fulfill({ json: [] });
    });
    try {
      await page.goto(
        origin +
          "/frontend/socialmei-app.html" +
          (["forged-callback", "successful-callback"].includes(mode)
            ? "#instagram=connected"
            : mode === "failed-callback"
              ? "#instagram=failed"
              : "#/config/integracoes"),
      );
      await page.waitForFunction(
        () => window.SocialMEIInstagram && SocialMEIInstagram.status.phase !== "loading",
      );
      const row = page
        .locator(".sw")
        .filter({ has: page.locator("b", { hasText: /^Instagram$/ }) });
      await row.waitFor();
      assert.equal(
        await page.evaluate(() => SocialMEIInstagram.status.connected),
        ["connected", "successful-callback"].includes(mode),
      );
      // Permissions beyond the explicitly supported contract are rejected.
      assert.equal(
        await page.evaluate(() => {
          const state = "s".repeat(43),
            url = new URL("https://www.instagram.com/oauth/authorize");
          url.search = new URLSearchParams({
            client_id: "12345",
            redirect_uri: location.origin + "/api/v1/instagram/meta/oauth/return",
            response_type: "code",
            scope: "instagram_business_basic,instagram_business_manage_insights",
            state,
          });
          try {
            SocialMEIInstagram.authorization({ state, authorization_url: url.href });
            return false;
          } catch {
            return true;
          }
        }),
        true,
      );
      if (
        ["forged-callback", "successful-callback", "failed-callback"].includes(
          mode,
        )
      ) {
        assert(page.url().endsWith("#/config/integracoes"));
        assert.equal(
          await page.locator(".e404").count(),
          0,
          "OAuth return never renders 404",
        );
        await page.getByRole("heading", { name: "Configurações" }).waitFor();
        assert.equal(
          await page
            .locator("dialog")
            .getByText(
              mode === "forged-callback"
                ? "Não configurado"
                : mode === "successful-callback"
                  ? "Conectado"
                  : "Não conectado",
              { exact: true },
            )
            .count(),
          1,
        );
      } else if (["connect", "connect-frame", "invalid-url", "member"].includes(mode)) {
        if (mode === "connect-frame") {
          await page.evaluate(() => go("/divul"));
          const frame = page.frameLocator("#v iframe");
          await frame.locator("#dock button").nth(3).click();
          await frame.getByRole("button", { name: "Conectar Instagram", exact: true }).click();
        } else await row.getByRole("button", { name: "Conectar Instagram", exact: true }).click();
        if (["connect", "connect-frame"].includes(mode)) {
          await page.waitForURL("https://www.instagram.com/oauth/authorize?**");
          assert.equal(new URL(page.url()).searchParams.get("state"), state);
          assert.equal(posts.length, 1);
        } else {
          await page
            .getByText(
              "Não foi possível iniciar a autorização. Confira a sessão e a configuração com o responsável.",
              { exact: true },
            )
            .waitFor();
          assert.equal(new URL(page.url()).origin, origin);
          assert.equal(posts.length, mode === "member" ? 0 : 1);
          assert.deepEqual(external, []);
        }
      } else {
        await page.evaluate(() => go("/divul"));
        const frame = page.frameLocator("#v iframe");
        await frame.locator("#dock button").nth(3).click();
        const card = frame
          .locator("#cg .cn")
          .filter({ has: frame.locator("b", { hasText: /^Instagram$/ }) });
        await card
          .getByText(mode === "connected" ? "Conectado" : "Não configurado", { exact: true })
          .waitFor();
        assert.equal(
          await page.evaluate(() => SocialMEIInstagram.status.connected),
          mode === "connected",
        );
        await card.locator("button[data-ig-action]").click();
        await page.locator("dialog[open]").waitFor();
        await page.keyboard.press("Escape");
        assert.equal(posts.length, 0);
        for (const width of [390, 1440])
          for (const theme of ["claro", "escuro"]) {
            await page.setViewportSize({ width, height: 1000 });
            await page.evaluate((t) => {
              S.theme = t;
              applyTheme();
            }, theme);
            await page.evaluate(() => document.fonts.ready);
            await page.waitForFunction(
              () =>
                Math.abs(
                  parseFloat(document.body.style.width) * Number(document.body.style.zoom || 1) -
                    innerWidth,
                ) < 0.1,
            );
            assert.equal(
              await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
              false,
            );
            await page.screenshot({
              path: path.join(output, `${mode}-${width}-${theme}.png`),
              fullPage: true,
              animations: "disabled",
            });
          }
        assert.equal(
          await frame.locator("body").evaluate(() => localStorage.getItem("smei4_c")),
          null,
          "Real controls never toggle a local simulated connection",
        );
      }
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  }
  return "Instagram native: disabled/configured/connected/member/forged, successful and failed callbacks/invalid URL passed; no real provider requests";
};
