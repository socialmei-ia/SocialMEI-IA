/* Synthetic analysis metadata in the real V22 shell. No model/provider traffic. */
const assert = require("node:assert/strict");
module.exports = async function (browser, origin) {
  for (const width of [1440, 390])
    for (const theme of ["light", "dark"]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage();
      const errors = [],
        external = [];
      let metadata = null;
      const identity = {
        usuario: { id: 91, nome: "Conta sintética", email: "synthetic@example.test" },
        negocio: { id: 17, nome: "Loja sintética", slug: "synthetic", configuracao: {} },
        papel: "owner",
        csrf_token: "a".repeat(64),
      };
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      await page.clock.install();
      await page.route("**/*", (route) => {
        const request = route.request(),
          url = new URL(request.url());
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
        assert.equal(request.method(), "GET", "Displaying analysis never writes or sends");
        const path = url.pathname.replace("/api/v1", "");
        if (path === "/auth/session") return route.fulfill({ json: identity });
        if (path === "/auth/preferences")
          return route.fulfill({ json: { preferences: { theme }, revision: 0 } });
        if (path === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (path === "/message-enrichment/capabilities")
          return route.fulfill({
            json: {
              mode: "disabled",
              workspace_id: 17,
              instagram_inbox: true,
              provider_sentiment: true,
            },
          });
        if (path === "/message-enrichment/conversations")
          return route.fulfill({
            json: {
              workspace_id: 17,
              items: [
                {
                  id: 3,
                  revision: 1,
                  channel: "instagram",
                  origin: "instagram",
                  contact_name: "Contato sintético",
                  account_ref: "instagram:test",
                  contact_ref: "instagram:contact",
                  messages: [
                    {
                      id: 11,
                      text: "Mensagem recebida para análise",
                      occurred_at: "2026-10-30T10:00:00Z",
                      provider_analysis: metadata,
                    },
                  ],
                },
              ],
            },
          });
        if (path === "/integrations/readiness")
          return route.fulfill({ json: { instagram: { oauth_available: false } } });
        if (path === "/instagram/meta/status")
          return route.fulfill({ json: { status: "disconnected", credential_available: false } });
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/caixa/me-3");
        await page.locator(".ct .ms .bb", { hasText: "Mensagem recebida para análise" }).waitFor();
        await page.waitForFunction(() => !!window.SocialMEIProviderAnalysis);
        assert.equal(await page.locator("[data-provider-analysis]").count(), 0);
        await page.evaluate(() => {
          window.SocialMEIInstagramDirect = {
            confirmed: () => [
              {
                id: "direct-receipt",
                direction: "outgoing",
                occurred_at: "2026-10-30T09:00:00Z",
                text: "Saída sintética intercalada",
              },
            ],
          };
          window.render();
        });
        metadata = {
          source: "automation",
          sentiment: "positive",
          confidence: "low",
          explanation: "<img src=x onerror=alert(1)>",
        };
        await page.clock.fastForward(6001);
        const panel = page.locator("[data-provider-analysis]");
        await panel.waitFor();
        await panel.locator("summary").click();
        assert.match(await panel.innerText(), /Sentimento positivo/);
        assert.match(await panel.innerText(), /fonte: automação/);
        assert.match(await panel.innerText(), /<img src=x onerror=alert\(1\)>/);
        assert.doesNotMatch(await panel.innerText(), /Saída sintética/);
        assert.equal(await panel.locator("img").count(), 0);
        assert.equal(await panel.locator("[data-message-id='11']").count(), 1);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
          false,
        );
        const focused = panel.locator("summary");
        await focused.focus();
        await page.keyboard.press("Enter");
        assert.equal(await panel.evaluate((n) => n.open), false);
        metadata = { ...metadata, sentiment: "negative", explanation: "Resultado atualizado" };
        await page.clock.fastForward(6001);
        await panel.locator("summary").click();
        await panel.getByText(/Sentimento negativo/).waitFor();
        metadata = null;
        await page.clock.fastForward(6001);
        await page.waitForFunction(() => !document.querySelector("[data-provider-analysis]"));
        metadata = {
          source: "automation",
          sentiment: "neutral",
          confidence: "medium",
          explanation: "Novo resultado",
        };
        await page.clock.fastForward(6001);
        await panel.waitFor();
        await page.evaluate(() => {
          SocialMEIV22.identity.negocio.id = 18;
          window.render();
        });
        await page.waitForFunction(() => !document.querySelector("[data-provider-analysis]"));
        assert.deepEqual(errors, []);
        assert.deepEqual(external, []);
      } finally {
        await context.close();
      }
    }
  return "V22 provider analysis: late/change/revocation, safe text, incoming identity, workspace switch; 2 widths x 2 themes";
};
