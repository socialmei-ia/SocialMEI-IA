// Opt-in smoke test against the real disposable preview, never a remote host.
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
require("node:dns").setDefaultResultOrder("ipv4first");
const origin = "https://localhost:8443";
const output = path.resolve(__dirname, "../test-results/preview");

async function run() {
  const browser = await chromium.launch();
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
        headers: { Origin: origin },
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
      await page.evaluate(() => SocialMEIExperience.enterApp("Clientes"));
      await page.waitForFunction(() =>
        appData.clientes.some((c) => c.nome === "Cliente fictício do preview"),
      );
      await page.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
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
      await page.close();
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(
        {
          realBackend: true,
          origin,
          workspaces: 2,
          auth: true,
          csrf: true,
          persistentClient: true,
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
