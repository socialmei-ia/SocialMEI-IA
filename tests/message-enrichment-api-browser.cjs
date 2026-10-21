// Optional proof on real disposable HTTPS/FastAPI/PostgreSQL. Never targets a remote server.
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path"),
  { randomUUID } = require("node:crypto"),
  { chromium } = require("playwright");
async function run(config) {
  const target = new URL(config.origin);
  assert(
    target.protocol === "https:" && ["localhost", "127.0.0.1", "[::1]"].includes(target.hostname),
  );
  const origin = target.origin,
    output = path.resolve(__dirname, "../test-results/enrichment-real");
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
      viewport: { width: 1440, height: 1000 },
      reducedMotion: "reduce",
    });
    contexts.push(context);
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (route) => {
      const u = new URL(route.request().url());
      if (u.origin !== origin) {
        external.push(u.origin);
        return route.abort();
      }
      return route.continue();
    });
    page.on("response", (r) => {
      const u = new URL(r.url());
      if (u.pathname.startsWith("/api/v1/message-enrichment"))
        statuses.push({ path: u.pathname, method: r.request().method(), status: r.status() });
    });
    await page.goto(origin + "/");
    await page.waitForFunction(() => !!window.SocialMEIAuth && !!window.SocialMEIMessageEnrichment);
    return page;
  }
  async function account(page, email, register) {
    const status = await page.evaluate(
      async ({ email, register }) => {
        const r = await fetch("/api/v1/auth/" + (register ? "register" : "login"), {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-SocialMEI-Client": "browser" },
          body: JSON.stringify({
            email,
            senha: "Disposable-qa81-only-123!",
            ...(register ? { nome: "Empreendedor fictício QA81" } : {}),
          }),
        });
        return { status: r.status, detail: r.ok ? "" : (await r.json()).detail };
      },
      { email, register },
    );
    assert.equal(status.status, register ? 201 : 200, String(status.detail));
    await page.reload();
    await page.waitForFunction(
      () =>
        document.body?.classList.contains("experience-app") &&
        !!SocialMEIAuth.current &&
        !!window.SocialMEIMessageEnrichment,
    );
    await page.evaluate(() => setView("Caixa Unificada"));
    await page.locator("#enrichmentLab > summary").click();
    await page.waitForFunction(() => SocialMEIMessageEnrichment.state().status === "ready");
  }
  async function message(page, contact = "synthetic:contato-a") {
    if (!(await page.locator("#enrichmentLab").evaluate((e) => e.open)))
      await page.locator("#enrichmentLab > summary").click();
    await page.locator('#enrichmentSyntheticForm [name="name"]').fill("Mesmo nome fictício");
    await page.locator('#enrichmentSyntheticForm [name="contact"]').selectOption(contact);
    await page
      .locator("#enrichmentText")
      .fill("O atendimento foi ruim e houve atraso. Preciso de ajuda.");
    await page.locator('#enrichmentSyntheticForm [type="submit"]').click();
    await page.waitForFunction(
      () =>
        !document.getElementById("enrichmentLab").open && !SocialMEIMessageEnrichment.state().busy,
    );
    await page.locator("#enrichmentAnalyze").waitFor();
  }
  async function openFirst(page) {
    await page.evaluate(async () => {
      await SocialMEIMessageEnrichment.refresh();
      const rows = SocialMEIMessageEnrichment.state().rows;
      await selectConversation(
        -(rows.find((r) => r.messages.some((m) => m.enrichment)) || rows[0]).id,
      );
    });
  }
  try {
    const a = await pageFor(),
      b = await pageFor(),
      other = await pageFor(),
      email = `qa81-${randomUUID()}@example.test`;
    await account(a, email, true);
    await account(b, email, false);
    const otherEmail = `qa81-${randomUUID()}@example.test`;
    await account(other, otherEmail, true);
    const cookie = async (p) => (await p.context().cookies()).find((c) => c.httpOnly)?.value;
    assert(
      (await cookie(a)) && (await cookie(a)) !== (await cookie(b)),
      "Two independent authenticated sessions required",
    );
    await a.locator("#enrichmentDocumentForm").evaluate((f) => (f.parentElement.open = true));
    await a
      .locator('#enrichmentDocumentForm [name="title"]')
      .fill("Orientação fictícia de atendimento");
    await a
      .locator('#enrichmentDocumentForm [name="content"]')
      .fill("Atendimento: avaliar o ocorrido antes de confirmar qualquer preço ou prazo.");
    await a.locator('#enrichmentDocumentForm [type="submit"]').click();
    await a.waitForFunction(() => SocialMEIMessageEnrichment.state().documents.length === 1);
    await message(a);
    await a.locator("#enrichmentAnalyze").click();
    await a.locator("#enrichmentReply").waitFor();
    assert.match(await a.locator("#enrichmentExplanation").textContent(), /Negativo/);
    assert.equal(
      await a.evaluate(
        () => SocialMEIMessageEnrichment.state().rows[0].messages[0].enrichment.citations.length,
      ),
      1,
    );
    await openFirst(b);
    await a.locator("#enrichmentReply").fill("Rascunho preservado da sessão A.");
    await b.locator("#enrichmentReply").fill("Revisão confirmada na sessão B.");
    await b.locator('[data-enrichment-decision="approved"]').click();
    await b.waitForFunction(
      () => SocialMEIMessageEnrichment.state().rows[0].messages[0].enrichment.status === "approved",
    );
    await a.locator('[data-enrichment-decision="approved"]').click();
    await a.waitForFunction(() =>
      SocialMEIMessageEnrichment.state().problem.includes("Outra sessão"),
    );
    assert.equal(
      await a.locator("#enrichmentReply").inputValue(),
      "Rascunho preservado da sessão A.",
    );
    await a
      .getByRole("button", { name: "Carregar revisão salva e descartar meu rascunho" })
      .click();
    await a.waitForFunction(
      () => document.getElementById("enrichmentReply").value === "Revisão confirmada na sessão B.",
    );
    assert(await a.locator('[data-enrichment-decision="approved"]').isDisabled());
    await a.locator("#enrichmentAnalyze").click();
    await a.waitForFunction(
      () =>
        SocialMEIMessageEnrichment.state().rows[0].messages[0].enrichment.status ===
          "pending_review" && !SocialMEIMessageEnrichment.state().busy,
    );
    await a.route("**/api/v1/message-enrichment/jobs/*/review", (route) => route.abort("failed"));
    await a.locator("#enrichmentReply").fill("Texto preservado sem conexão.");
    await a.locator('[data-enrichment-decision="approved"]').click();
    await a.waitForFunction(() => SocialMEIMessageEnrichment.state().problem.includes("conexão"));
    assert.equal(await a.locator("#enrichmentReply").inputValue(), "Texto preservado sem conexão.");
    await a.unroute("**/api/v1/message-enrichment/jobs/*/review");
    await a.locator('[data-enrichment-decision="approved"]').click();
    await a.waitForFunction(
      () =>
        SocialMEIMessageEnrichment.state().rows[0].messages[0].enrichment.suggested_reply ===
        "Texto preservado sem conexão.",
    );
    await openFirst(b);
    assert.equal(await b.locator("#enrichmentReply").inputValue(), "Texto preservado sem conexão.");
    await message(a, "synthetic:contato-b");
    assert.equal(await a.evaluate(() => SocialMEIMessageEnrichment.state().rows.length), 2);
    await message(other);
    assert.equal(await other.evaluate(() => SocialMEIMessageEnrichment.state().rows.length), 1);
    assert.equal(
      await other.evaluate(() => SocialMEIMessageEnrichment.state().documents.length),
      0,
    );
    const forbiddenId = await other.evaluate(() => SocialMEIMessageEnrichment.state().rows[0].id);
    assert.equal(
      await a.evaluate(async (id) => {
        try {
          await SocialMEIAuth.request(`/message-enrichment/conversations/${id}/enrichments`);
          return 200;
        } catch (e) {
          return e.status;
        }
      }, forbiddenId),
      404,
    );
    await openFirst(a);
    for (const width of [320, 390, 768, 1440])
      for (const theme of ["light", "dark"]) {
        await a.setViewportSize({ width, height: 1000 });
        await a.evaluate((t) => SocialMEIThemes.select(t, { persist: false }), theme);
        await a.locator("#enrichmentReply").scrollIntoViewIfNeeded();
        assert(await a.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await a.screenshot({ path: path.join(output, `inbox-${width}-${theme}.png`) });
      }
    await a.locator("#enrichmentLab > summary").click();
    await a.locator("#enrichmentDocumentList button").click();
    await a.waitForFunction(() => SocialMEIMessageEnrichment.state().documents.length === 0);
    assert.equal(await a.locator("#enrichmentReply").inputValue(), "");
    const sibling = await a.context().newPage();
    sibling.on("pageerror", (e) => errors.push(e.message));
    await sibling.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    await sibling.goto(origin + "/");
    await sibling.waitForFunction(() => !!window.SocialMEIAuth?.current);
    const switched = await sibling.evaluate(async (email) => {
      const r = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-SocialMEI-Client": "browser" },
        body: JSON.stringify({ email, senha: "Disposable-qa81-only-123!" }),
      });
      return r.status;
    }, otherEmail);
    assert.equal(switched, 200);
    await sibling.reload();
    await a.waitForFunction(() => SocialMEIMessageEnrichment.state().scope === null);
    assert.equal(
      await a.evaluate(() => sessionData.conversas.filter((c) => c._enrichmentSynthetic).length),
      0,
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(
        {
          checks: [
            "Duas sessões reais do mesmo negócio",
            "Dois negócios e contatos com mesmo nome sem mistura",
            "RAG isolado, remoção invalida rascunho",
            "CAS409 e offline preservam texto",
            "Revisão persistida sem envio",
            "8 layouts e nenhum erro JavaScript",
          ],
          statuses,
          errors,
          external,
        },
        null,
        2,
      ),
    );
    console.log(
      "QA81: Caixa nativa, duas sessões reais, isolamento/RAG/CAS/offline aprovados; nenhum transporte externo",
    );
  } catch (error) {
    for (const [i, c] of contexts.entries())
      if (c.pages()[0])
        await c
          .pages()[0]
          .screenshot({ path: path.join(output, `failure-${i}.png`) })
          .catch(() => {});
    throw error;
  } finally {
    await browser.close();
  }
}
if (require.main === module)
  run(JSON.parse(fs.readFileSync(process.env.MESSAGE_ENRICHMENT_QA_CONFIG, "utf8"))).catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
module.exports = run;
