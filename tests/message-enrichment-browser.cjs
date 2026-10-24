const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
module.exports = async (browser, origin) => {
  const api = require("./message-enrichment-fixture.cjs")(),
    profile = require("./profile-sync-fixture.cjs")();
  const contexts = [],
    errors = [],
    external = [],
    writes = [];
  const output = path.resolve(__dirname, "../test-results/message-enrichment");
  fs.mkdirSync(output, { recursive: true });
  const owner = {
    usuario: { id: 1, nome: "MEI fictício", email: "sintetico@example.test" },
    negocio: { id: 1, nome: "Negócio fictício A", slug: "synthetic-a", configuracao: {} },
    papel: "owner",
    csrf_token: "a".repeat(64),
  };
  let offlineReview = false,
    offlineRead = false,
    providerMode = false;
  const providerRow = {
    id: 9001,
    origin: "instagram",
    channel: "instagram",
    account_ref: "instagram:987654321",
    contact_ref: "instagram:123456789",
    contact_name: "Contato do Instagram",
    revision: 1,
    messages: [
      {
        id: 9002,
        external_message_id: "provider-mid-" + "m".repeat(140),
        text: "  Mensagem Instagram <img src=x onerror=alert(1)>\n",
        occurred_at: "2026-10-23T15:40:00.123Z",
        revision: 1,
        enrichment: null,
      },
    ],
  };
  async function pageFor(identity) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: "reduce",
    });
    contexts.push(context);
    const page = await context.newPage();
    page.on("pageerror", (e) => {
      errors.push(e.message);
      console.error(e.stack);
    });
    await page.route("**/*", (route) => {
      const req = route.request(),
        url = new URL(req.url());
      if (url.origin !== origin) {
        external.push(url.origin);
        return route.abort();
      }
      if (url.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
        });
      if (url.pathname === "/api/v1/auth/session") return route.fulfill({ json: identity });
      if (["/api/v1/workspace-profile", "/api/v1/auth/preferences"].includes(url.pathname))
        return profile(route, identity);
      if (
        providerMode &&
        req.method() === "GET" &&
        url.pathname.startsWith("/api/v1/message-enrichment")
      ) {
        if (url.pathname.endsWith("/capabilities"))
          return route.fulfill({
            json: {
              schema_version: 1,
              mode: "disabled",
              transport: "none",
              workspace_id: identity.negocio.id,
              instagram_inbox: true,
            },
          });
        if (url.pathname.endsWith("/conversations"))
          return route.fulfill({
            json: {
              workspace_id: identity.negocio.id,
              items: identity.negocio.id === 1 ? [providerRow] : [],
            },
          });
      }
      if (url.pathname.startsWith("/api/v1/message-enrichment")) {
        if (req.method() !== "GET")
          writes.push({
            path: url.pathname,
            method: req.method(),
            body: req.method() === "DELETE" ? null : req.postDataJSON(),
          });
        if (offlineReview && url.pathname.endsWith("/review")) return route.abort("failed");
        if (offlineRead && req.method() === "GET" && url.pathname.endsWith("/conversations"))
          return route.abort("failed");
        return api(route, identity);
      }
      if (url.pathname.startsWith("/api/")) return route.fulfill({ json: [] });
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () =>
        document.body?.classList.contains("experience-app") && window.SocialMEIMessageEnrichment,
    );
    await page.evaluate(() => setView("Caixa Unificada"));
    await page.locator("#enrichmentLab > summary").click();
    await page.waitForFunction(() => SocialMEIMessageEnrichment.state().status === "ready");
    return page;
  }
  async function add(page, contact = "synthetic:contato-a", account = "synthetic:conta-a") {
    if (!(await page.locator("#enrichmentLab").evaluate((el) => el.open)))
      await page.locator("#enrichmentLab > summary").click();
    await page.locator('#enrichmentSyntheticForm [name="name"]').fill("Mesmo nome fictício");
    await page.locator('#enrichmentSyntheticForm [name="contact"]').selectOption(contact);
    await page.locator('#enrichmentSyntheticForm [name="account"]').selectOption(account);
    await page.locator("#enrichmentText").fill("Não gostei do atendimento, preciso de ajuda.");
    await page.locator('#enrichmentSyntheticForm [type="submit"]').click();
    await page.waitForFunction(
      () =>
        !document.getElementById("enrichmentLab").open && !SocialMEIMessageEnrichment.state().busy,
    );
    await page.locator("#enrichmentAnalyze").waitFor();
  }
  try {
    const a = await pageFor(owner),
      b = await pageFor(owner),
      other = await pageFor({
        ...owner,
        usuario: { ...owner.usuario, id: 2 },
        negocio: { ...owner.negocio, id: 2 },
      });
    assert.equal(await a.evaluate(() => SocialMEIMessageEnrichment.state().rows.length), 0);
    await a.locator("#enrichmentDocumentForm").evaluate((form) => (form.parentElement.open = true));
    await a.locator('#enrichmentDocumentForm [name="title"]').fill("Orientação fictícia");
    await a
      .locator('#enrichmentDocumentForm [name="content"]')
      .fill("Avalie o atendimento antes de confirmar valores ou prazos.");
    await a.locator('#enrichmentDocumentForm [type="submit"]').click();
    await a.waitForFunction(() => SocialMEIMessageEnrichment.state().documents.length === 1);
    await add(a);
    assert(await a.locator("#composerZone").isHidden());
    assert(!(await a.locator("#threadMeta").textContent()).includes("Recebido via n8n"));
    await a.locator("#enrichmentAnalyze").click();
    await a.locator("#enrichmentReply").waitFor();
    assert.match(await a.locator("#enrichmentExplanation").textContent(), /Negativo/);
    await a.locator("#enrichmentReply").fill("Rascunho humano preservado.");
    offlineReview = true;
    await a.locator('[data-enrichment-decision="approved"]').click();
    await a.waitForFunction(() => SocialMEIMessageEnrichment.state().problem.includes("conexão"));
    assert.equal(await a.locator("#enrichmentReply").inputValue(), "Rascunho humano preservado.");
    offlineReview = false;
    await b.evaluate(() => SocialMEIMessageEnrichment.refresh());
    await b.evaluate(async () =>
      selectConversation(-SocialMEIMessageEnrichment.state().rows[0].id),
    );
    await b.locator("#enrichmentReply").fill("Revisão de outra sessão.");
    await b.locator('[data-enrichment-decision="approved"]').click();
    await b.waitForFunction(
      () => SocialMEIMessageEnrichment.state().rows[0].messages[0].enrichment.status === "approved",
    );
    await a.locator('[data-enrichment-decision="approved"]').click();
    await a.waitForFunction(() =>
      SocialMEIMessageEnrichment.state().problem.includes("Outra sessão"),
    );
    assert.equal(await a.locator("#enrichmentReply").inputValue(), "Rascunho humano preservado.");
    offlineRead = true;
    await a
      .getByRole("button", { name: "Carregar revisão salva e descartar meu rascunho" })
      .click();
    await a.waitForFunction(() => SocialMEIMessageEnrichment.state().status === "error");
    assert.equal(await a.locator("#enrichmentReply").inputValue(), "Rascunho humano preservado.");
    offlineRead = false;
    await a
      .getByRole("button", { name: "Carregar revisão salva e descartar meu rascunho" })
      .click();
    await a.waitForFunction(
      () => document.getElementById("enrichmentReply").value === "Revisão de outra sessão.",
    );
    assert(await a.locator('[data-enrichment-decision="approved"]').isDisabled());
    await a.locator("#enrichmentAnalyze").click();
    await a.waitForFunction(
      () =>
        SocialMEIMessageEnrichment.state().rows[0].messages[0].enrichment.status ===
          "pending_review" && !SocialMEIMessageEnrichment.state().busy,
    );
    await a.locator('[data-enrichment-decision="rejected"]').click();
    await a.waitForFunction(
      () => SocialMEIMessageEnrichment.state().rows[0].messages[0].enrichment.status === "rejected",
    );
    await add(a, "synthetic:contato-b");
    await add(a, "synthetic:contato-a", "synthetic:conta-b");
    assert.equal(await a.evaluate(() => SocialMEIMessageEnrichment.state().rows.length), 3);
    await other.evaluate(() => SocialMEIMessageEnrichment.refresh());
    assert.equal(await other.evaluate(() => SocialMEIMessageEnrichment.state().rows.length), 0);
    assert.equal(
      await other.evaluate(() => SocialMEIMessageEnrichment.state().documents.length),
      0,
    );
    await a.evaluate(async () =>
      selectConversation(-SocialMEIMessageEnrichment.state().rows[0].id),
    );
    for (const width of [320, 390, 768, 1440])
      for (const theme of ["light", "dark"]) {
        await a.setViewportSize({ width, height: 1000 });
        await a.evaluate((theme) => SocialMEIThemes.select(theme, { persist: false }), theme);
        assert(await a.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await a.locator("#enrichmentReply").scrollIntoViewIfNeeded();
        await a.screenshot({
          path: path.join(output, `inbox-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    await a.locator("#enrichmentReply").focus();
    await a.keyboard.press("Tab");
    assert(await a.evaluate(() => document.activeElement.closest("#enrichmentReview")));
    await a.locator("#enrichmentLab > summary").click();
    await a.locator("#enrichmentDocumentList button").click();
    await a.waitForFunction(() => SocialMEIMessageEnrichment.state().documents.length === 0);
    assert.equal(await a.locator("#enrichmentReply").inputValue(), "");
    assert(await a.locator("#enrichmentReply").isDisabled());
    const viewer = await pageFor({ ...owner, papel: "viewer" });
    await viewer.evaluate(async () =>
      selectConversation(-SocialMEIMessageEnrichment.state().rows[0].id),
    );
    assert(await viewer.locator("#enrichmentAnalyze").isDisabled());
    assert(await viewer.locator('#enrichmentSyntheticForm [type="submit"]').isDisabled());
    // Another tab changes the verified browser account while this tab still has its old identity.
    const sibling = await a.context().newPage();
    await sibling.route("**/*", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: "<!doctype html><title>Sessão de teste</title>",
      }),
    );
    await sibling.goto(origin + "/qa81-session-scope");
    await sibling.evaluate(() => localStorage.setItem("socialmei-auth-browser-scope", "2:2"));
    await a.waitForFunction(() => SocialMEIMessageEnrichment.state().scope === null);
    assert.equal(
      await a.evaluate(() => sessionData.conversas.filter((c) => c._enrichmentSynthetic).length),
      0,
    );
    assert.equal(await a.locator("#enrichmentReply").count(), 0);
    providerMode = true;
    const provider = await pageFor(owner);
    await provider.evaluate(async () => selectConversation(-9001));
    assert.equal(await provider.evaluate(() => getConversation()._enrichmentSynthetic), false);
    assert.equal(await provider.evaluate(() => getConversation()._enrichmentOrigin), "instagram");
    assert.match(await provider.locator("#threadMeta").textContent(), /Instagram/);
    assert(!/Fictício|n8n/.test(await provider.locator("#threadMeta").textContent()));
    assert(await provider.locator("#composerZone").isHidden());
    assert(await provider.locator("#threadStatus").isDisabled());
    assert.equal(await provider.locator("#enrichmentReview").count(), 0);
    assert(
      await provider
        .locator("#messages")
        .textContent()
        .then((text) => text.includes("<img src=x onerror=alert(1)>")),
    );
    const original = await provider.evaluate(() => getConversation().mensagens.length);
    await provider.evaluate(() => sendCurrentMessage("Não enviar"));
    assert.equal(await provider.evaluate(() => getConversation().mensagens.length), original);
    const providerOther = await pageFor({
      ...owner,
      usuario: { ...owner.usuario, id: 2 },
      negocio: { ...owner.negocio, id: 2 },
    });
    assert.equal(
      await providerOther.evaluate(() => SocialMEIMessageEnrichment.state().rows.length),
      0,
    );
    await provider.evaluate(() => SocialMEIMessageEnrichment.refresh());
    assert.equal(
      await provider.evaluate(
        () => sessionData.conversas.filter((c) => c._enrichmentOrigin === "instagram").length,
      ),
      1,
    );
    assert(!writes.some((r) => /send|waha|webhook|publish/.test(r.path)));
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    return "Caixa/enriquecimento: três identidades de mesmo nome, duas sessões, revisão/409/offline, documentos removidos, viewer, teclado e oito layouts; nenhum envio ou transporte externo";
  } finally {
    await Promise.all(contexts.map((c) => c.close()));
  }
};
