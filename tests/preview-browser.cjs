// Opt-in smoke test against the real disposable preview, never a remote host.
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const origin = "https://127.0.0.1:8443";
const output = path.resolve(__dirname, "../test-results/preview");

async function run() {
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  const contexts = [];
  const errors = [];
  try {
    fs.mkdirSync(output, { recursive: true });
    for (let i = 0; i < 2; i++) {
      const context = await browser.newContext({ ignoreHTTPSErrors: true });
      contexts.push(context);
      const marker = await context.request.get(origin + "/__preview");
      assert.deepEqual(await marker.json(), {
        environment: "local-disposable-preview",
        transport: "none",
      });
      const anonymous = await context.request.get(origin + "/api/v1/clientes");
      assert.equal(anonymous.status(), 401);
      const register = await context.request.post(origin + "/api/v1/auth/register", {
        headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
        data: {
          nome: "Pessoa fictícia " + i,
          email: `preview-${randomUUID()}@example.test`,
          senha: "Preview-only-" + randomUUID(),
        },
      });
      assert.equal(register.status(), 201, await register.text());
      const identity = await register.json();
      assert(identity.csrf_token);
      context.previewIdentity = identity;
    }
    const first = contexts[0];
    const headers = { Origin: origin, "X-SocialMEI-CSRF": first.previewIdentity.csrf_token };
    const created = await first.request.post(origin + "/api/v1/clientes", {
      headers,
      data: { nome: "Cliente fictício do preview" },
    });
    assert.equal(created.status(), 201, await created.text());
    const client = await created.json();
    const forbidden = await first.request.post(origin + "/api/v1/clientes", {
      data: { nome: "Não deve ser gravado" },
    });
    assert.equal(forbidden.status(), 403);
    const foreign = await contexts[1].request.get(origin + "/api/v1/clientes/" + client.id);
    assert.equal(foreign.status(), 404);
    const empty = await contexts[1].request.get(origin + "/api/v1/clientes");
    assert.deepEqual(await empty.json(), []);
    const base = origin + "/api/v1/content/preparation";
    const status = await first.request.get(base + "/status");
    assert.equal(status.status(), 200);
    const capability = await status.json();
    assert.equal(capability.mode, "simulation");
    assert.equal(capability.transport, "none");
    assert.equal(capability.published, false);
    const captions = await first.request.post(base + "/captions", {
      headers,
      data: { topic: "Oferta fictícia" },
    });
    assert.equal((await captions.json()).generated_by_ai, false);
    const images = await first.request.post(base + "/images", {
      headers,
      data: { brief: "Imagem fictícia" },
    });
    assert.equal(images.status(), 503);
    const accountResponse = await first.request.post(base + "/accounts", {
      headers,
      data: { label: "Conta fictícia do preview" },
    });
    assert.equal(accountResponse.status(), 201, await accountResponse.text());
    const account = await accountResponse.json();
    const payload = {
      idempotency_key: randomUUID(),
      account_id: account.id,
      title: "Agendamento fictício",
      format: "feed",
      caption: "Teste sem publicação",
      media: [{ name: "fixture.png", mime: "image/png", size: 100 }],
      status: "scheduled",
      reviewed: true,
      scheduled_for: new Date(Date.now() + 120000).toISOString(),
      timezone: "America/Fortaleza",
    };
    const scheduled = await first.request.post(base + "/jobs", { headers, data: payload });
    assert.equal(scheduled.status(), 201, await scheduled.text());
    const job = await scheduled.json();
    assert.equal(job.status, "scheduled");
    const replay = await first.request.post(base + "/jobs", { headers, data: payload });
    assert.equal((await replay.json()).id, job.id);
    assert.equal((await contexts[1].request.get(base + "/jobs/" + job.id)).status(), 404);
    const cancel = await first.request.post(base + "/jobs/" + job.id + "/cancel", {
      headers,
      data: { revision: job.revision },
    });
    assert.equal(cancel.status(), 200);
    assert.equal((await cancel.json()).status, "cancelled");
    assert.equal((await first.request.get(origin + "/internal/channel-ingress")).status(), 404);
    for (const width of [1440, 390]) {
      const page = await first.newPage();
      page.on("pageerror", (e) => errors.push(e.message));
      await page.setViewportSize({ width, height: 900 });
      await page.route("**/*", (route) =>
        new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
      );
      await page.goto(origin + "/");
      await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
      // Startup restores the view after profile/preferences; navigate only after both have settled.
      await page.evaluate(async () => {
        await SocialMEIAuth.ready;
        await SocialMEIProfileSync.ready;
      });
      await page.evaluate(() => SocialMEIExperience.enterApp("Clientes"));
      await page.waitForFunction(() =>
        appData.clientes.some((c) => c.nome === "Cliente fictício do preview"),
      );
      if (width === 1440) {
        await page.evaluate(() => setView("Oportunidades"));
        await page.waitForFunction(() => !document.getElementById("opportunityTitle").disabled);
        await page.locator("#opportunityClient").selectOption(String(client.id));
        await page.locator("#opportunityTitle").fill("Interesse fictício do preview");
        await page.locator("#opportunityInterest").selectOption("hot");
        const creation = page.waitForResponse(
          (response) =>
            response.url() === origin + "/api/v1/opportunities" &&
            response.request().method() === "POST",
        );
        await page.locator('#opportunityCreateForm button[type="submit"]').click();
        const createdResponse = await creation;
        assert.equal(createdResponse.status(), 201, await createdResponse.text());
        const opportunity = await createdResponse.json();
        const card = page.locator('[data-commercial-opportunity="' + opportunity.id + '"]');
        await card.waitFor();
        const lifecycle = page.locator("#opportunityLifecycle");
        assert.equal(
          await lifecycle.getByRole("button", { name: "Quente (1)", exact: true }).count(),
          1,
        );
        await card.getByText("Atualizar acompanhamento", { exact: true }).click();
        await card.getByLabel("Motivo de não avançar").selectOption("other_supplier");
        await card.getByRole("button", { name: "Não avançou", exact: true }).click();
        await page.waitForFunction(() =>
          document
            .querySelector("#opportunityLifecycle .opportunity-controls")
            .textContent.includes("Quente (0)"),
        );
        await lifecycle.getByRole("button", { name: "Não avançou (1)", exact: true }).click();
        assert.match(await card.textContent(), /Comprou em outro lugar/);
        await card.getByText("Atualizar acompanhamento", { exact: true }).click();
        await card.getByRole("button", { name: "Reabrir oportunidade", exact: true }).click();
        assert.match(
          await lifecycle.locator('[role="status"]').first().textContent(),
          /Informe por que/,
        );
        await card.getByLabel("Motivo para reabrir").fill("Cliente voltou a conversar no teste");
        await card.getByRole("button", { name: "Reabrir oportunidade", exact: true }).click();
        await page.waitForFunction(() =>
          document
            .querySelector("#opportunityLifecycle .opportunity-controls")
            .textContent.includes("Quente (1)"),
        );
        await lifecycle.getByRole("button", { name: "Em andamento (1)", exact: true }).click();
        await card.getByText("Atualizar acompanhamento", { exact: true }).click();
        await card.getByRole("button", { name: "Venda realizada", exact: true }).click();
        await lifecycle.getByRole("button", { name: "Venda realizada (1)", exact: true }).click();
        await card.waitFor();
        assert.equal(
          await lifecycle.getByRole("button", { name: "Quente (0)", exact: true }).count(),
          1,
        );
        await card.getByRole("button", { name: "Ver histórico", exact: true }).click();
        await page.waitForFunction(
          (id) =>
            document
              .querySelector('[data-commercial-opportunity="' + id + '"] [role="status"]')
              .textContent.trim().length > 0,
          opportunity.id,
        );
        const historyResponse = await first.request.get(
          origin + "/api/v1/opportunities/" + opportunity.id + "/history",
        );
        assert.equal(historyResponse.status(), 200);
        const history = (await historyResponse.json()).items;
        assert.deepEqual(
          history.map((event) => event.action),
          ["close", "reopen", "close", "create"],
        );
        assert.equal(history[1].reason, "Cliente voltou a conversar no teste");
        assert.equal(history[2].reason, "other_supplier");
        assert.equal(
          (
            await contexts[1].request.get(
              origin + "/api/v1/opportunities/" + opportunity.id + "/history",
            )
          ).status(),
          404,
        );
        await page.reload();
        await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
        // Startup restores the view after profile/preferences; navigate only after both have settled.
        await page.evaluate(async () => {
          await SocialMEIAuth.ready;
          await SocialMEIProfileSync.ready;
        });
        await page.evaluate(() => SocialMEIExperience.enterApp("Oportunidades"));
        await page
          .locator("#opportunityLifecycle")
          .getByRole("button", { name: "Venda realizada (1)", exact: true })
          .click();
        await card.waitFor();
        assert.match(await card.textContent(), /Venda realizada/);
        await page.evaluate(() => setView("Divulgação"));
        await page.locator("#contentWorkspace-connections").click();
        await page.waitForFunction(() => !document.getElementById("integrationSetupSave").disabled);
        await page.locator("#integrationUsername").fill("preview.negocio");
        await page.locator("#integrationAccountType").selectOption("business");
        await page.locator("#integrationMetaStatus").selectOption("exists");
        await page.locator("#integrationParticipants").fill("participante.teste");
        await page.locator("#integrationSetupSave").click();
        await page.waitForFunction(() =>
          document
            .getElementById("integrationSetupStatus")
            .textContent.includes("Preparação salva"),
        );
        const setupUrl = origin + "/api/v1/integrations/setup";
        const setup = await (await first.request.get(setupUrl)).json();
        assert.equal(setup.instagram.username, "preview.negocio");
        assert.equal(setup.connected, false);
        assert.equal(setup.transport, "none");
        const update = await first.request.put(setupUrl, {
          headers,
          data: {
            expected_revision: setup.revision,
            instagram: { ...setup.instagram, username: "preview.atualizado" },
          },
        });
        assert.equal(update.status(), 200, await update.text());
        await page.locator("#integrationUsername").fill("edicao.preservada");
        await page.locator("#integrationSetupSave").click();
        await page.waitForFunction(() =>
          document.getElementById("integrationSetupStatus").textContent.includes("outra sessão"),
        );
        assert.equal(await page.locator("#integrationUsername").inputValue(), "edicao.preservada");
        const foreignSetup = await (await contexts[1].request.get(setupUrl)).json();
        assert.equal(foreignSetup.instagram.username, "");
        assert.equal(foreignSetup.revision, 0);
        await page.reload();
        await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
        // Startup restores the view after profile/preferences; navigate only after both have settled.
        await page.evaluate(async () => {
          await SocialMEIAuth.ready;
          await SocialMEIProfileSync.ready;
        });
        await page.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
        await page.locator("#contentWorkspace-connections").click();
        await page.waitForFunction(
          () => document.getElementById("integrationUsername").value === "preview.atualizado",
        );
        assert.match(await page.locator("#integrationSetupStatus").textContent(), /Não conectado/);
      }
      await page.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
      await page.locator("#contentWorkspace-agenda").click();
      await page.waitForFunction(() =>
        document.getElementById("preparationHistory").textContent.includes("Agendamento fictício"),
      );
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
        false,
      );
      await page.screenshot({ path: path.join(output, `divulgacao-${width}.png`), fullPage: true });
      await page.reload();
      await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
      // Startup restores the view after profile/preferences; navigate only after both have settled.
      await page.evaluate(async () => {
        await SocialMEIAuth.ready;
        await SocialMEIProfileSync.ready;
      });
      await page.close();
    }
    const multichannelReplies = await require("./reply-preparation-preview.cjs")(
      first,
      contexts[1],
      origin,
      headers,
    );
    const visualOpportunities = await require("./visual-opportunities-preview.cjs")(
      first,
      origin,
      client,
      headers,
    );
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(
        {
          realBackend: true,
          multichannelReplies,
          visualOpportunities,
          origin,
          workspaces: 2,
          auth: true,
          csrf: true,
          persistentClient: true,
          opportunityLifecyclePersistent: true,
          integrationSetupPersistentCAS: true,
          scheduledReplayCancelled: true,
          externalTransport: "none",
          viewports: [1440, 390],
          errors,
        },
        null,
        2,
      ),
    );
    console.log(
      "Preview real: auth, CSRF, dois negócios, persistência, fila simulada, recarga e desktop/mobile aprovados.",
    );
  } finally {
    for (const context of contexts) await context.close();
    await browser.close();
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
