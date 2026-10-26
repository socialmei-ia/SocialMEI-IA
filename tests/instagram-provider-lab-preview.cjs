// Real disposable HTTPS + PostgreSQL only. No Meta, n8n or remote target option.
const assert = require("node:assert/strict");
const { randomUUID, createHmac } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const { revealContentControl } = require("./content-test-ui.cjs");
const origin = "https://127.0.0.1:8443";
const api = origin + "/api/v1/instagram/provider-lab";
const output = path.resolve(__dirname, "../test-results/instagram-provider-lab");
async function run() {
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  const contexts = [],
    errors = [],
    external = [];
  try {
    fs.mkdirSync(output, { recursive: true });
    for (let i = 0; i < 3; i++)
      contexts.push(await browser.newContext({ ignoreHTTPSErrors: true, reducedMotion: "reduce" }));
    assert.deepEqual(await (await contexts[0].request.get(origin + "/__preview")).json(), {
      environment: "local-disposable-preview",
      transport: "none",
    });
    const email = `ig-lab-${randomUUID()}@example.test`,
      password = `Local-only-${randomUUID()}`;
    const identities = [];
    for (let i = 0; i < 3; i++) {
      const login = i === 1;
      const response = await contexts[i].request.post(
        origin + "/api/v1/auth/" + (login ? "login" : "register"),
        {
          headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
          data: {
            email: i === 2 ? `ig-other-${randomUUID()}@example.test` : email,
            senha: password,
            ...(login ? {} : { nome: "MEI fictício laboratório" }),
          },
        },
      );
      assert.equal(response.status(), login ? 200 : 201, await response.text());
      identities.push(await response.json());
    }
    const headers = (i) => ({ Origin: origin, "X-SocialMEI-CSRF": identities[i].csrf_token });
    const post = async (i, route, data = {}, expected = 200) => {
      const r = await contexts[i].request.post(api + route, { headers: headers(i), data });
      assert.equal(r.status(), expected, await r.text());
      return r.json();
    };
    assert.equal(
      (await contexts[0].request.post(api + "/oauth/start", { data: {} })).status(),
      403,
    );
    assert.equal(
      (await (await contexts[0].request.get(api + "/status")).json()).status,
      "disconnected",
    );
    const start = await post(0, "/oauth/start");
    assert.equal(start.redirect, null);
    const callback = { state: start.state, code: start.fake_code };
    await post(1, "/oauth/callback", callback, 409);
    await post(2, "/oauth/callback", callback, 409);
    const connected = await post(0, "/oauth/callback", callback);
    await post(0, "/oauth/callback", callback, 409);
    assert.equal(connected.status, "connected");
    // Read only the disposable preview key, after the loopback marker and authenticated guards.
    const fixture = fs.readFileSync(path.resolve(__dirname, "../.preview/.env"), "utf8");
    const key = /^PREVIEW_TEST_KEY=([a-f0-9]{64})$/m.exec(fixture)?.[1];
    assert(key, "Generate the disposable preview environment first");
    const event = {
      event_id: randomUUID(),
      account_id: connected.account_id,
      contact_id: "synthetic:ig-browser-customer",
      contact_name: "Ana fictícia Instagram",
      message_id: randomUUID(),
      text: "Preciso de ajuda com meu pedido fictício.",
      occurred_at: "2026-10-22T13:00:00Z",
    };
    const send = async (value, signature, expected = 200) => {
      const raw = JSON.stringify(value);
      const r = await contexts[0].request.post(api + "/webhook", {
        data: raw,
        headers: {
          ...headers(0),
          "Content-Type": "application/json",
          "X-Hub-Signature-256":
            signature || "sha256=" + createHmac("sha256", key).update(raw).digest("hex"),
        },
      });
      assert.equal(r.status(), expected, await r.text());
      return r.json();
    };
    await send(event, "sha256=invalid", 403);
    const incoming = await send(event);
    assert.equal((await send(event)).replayed, true);
    await send({ ...event, text: "Evento conflitante" }, null, 409);
    await send({
      ...event,
      event_id: randomUUID(),
      message_id: randomUUID(),
      text: "Mensagem anterior fictícia.",
      occurred_at: "2026-10-21T13:00:00Z",
    });
    const foreignRows = await (
      await contexts[2].request.get(origin + "/api/v1/message-enrichment/conversations")
    ).json();
    assert.deepEqual(foreignRows.items, []);
    const page = await contexts[0].newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin === origin || ["blob:", "data:"].includes(url.protocol))
        return route.continue();
      external.push(url.origin);
      return route.abort();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () => window.SocialMEIV22?.identity && !document.getElementById("app").hidden,
    );
    await page.evaluate((id) => go("/caixa/me-" + id), incoming.conversation_id);
    assert.match(await page.locator(".ct .hd").innerText(), /Ana fictícia Instagram/);
    assert(await page.locator('[data-a^="salvar:"]').isDisabled());
    const messages = await page.evaluate(
      (id) => SocialMEIV22.thread("me-" + id),
      incoming.conversation_id,
    );
    assert.deepEqual(
      messages.map((message) => message[1]),
      ["Mensagem anterior fictícia.", event.text],
    );
    for (const width of [1440, 390])
      for (const theme of ["claro", "escuro"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((t) => {
          S.theme = t;
          applyTheme();
        }, theme);
        await page.evaluate(
          () =>
            new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
          false,
        );
        await page.screenshot({
          path: path.join(output, `inbox-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    await page.evaluate(() => go("/divul"));
    const editor = page.frameLocator("#v iframe");
    await editor.locator('.fmt[data-f="feed"]').click();
    await editor.locator("#d3 summary").click();
    await editor.locator("#leg").fill("Rascunho fictício revisado; nada será publicado.");
    await editor.locator("#file").setInputFiles({
      name: "fixture.png",
      mimeType: "image/png",
      buffer: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXioAAAAASUVORK5CYII=",
        "base64",
      ),
    });
    const snapshot = await editor.locator("body").evaluate(() => {
      const file = V22Frame.mediaManifest;
      return {
        format: document.querySelector('.fmt[aria-checked="true"]').dataset.f,
        caption: document.getElementById("leg").value,
        media: { name: file.name, mime: file.mime, size: file.size },
      };
    });
    const data = {
      account_id: connected.account_id,
      idempotency_key: randomUUID(),
      format: snapshot.format,
      caption: snapshot.caption,
      media: [snapshot.media],
    };
    const job = await post(0, "/publications", data, 201);
    assert.equal((await post(0, "/publications", data)).id, job.id);
    await post(0, `/publications/${job.id}/run`, {}, 409);
    await post(0, `/publications/${job.id}/approve`);
    assert.equal(
      (await post(0, `/publications/${job.id}/run`, { outcome: "failure" })).status,
      "failed",
    );
    const result = await post(0, `/publications/${job.id}/run`);
    assert.equal(result.status, "simulated-published");
    assert.equal(result.published, false);
    assert.equal(result.transport, "none");
    assert.equal(result.attempts, 2);
    await post(0, `/publications/${job.id}/run`, {}, 409);
    const future = await post(
      0,
      "/publications",
      {
        ...data,
        idempotency_key: randomUUID(),
        scheduled_for: new Date(Date.now() + 3600000).toISOString(),
      },
      201,
    );
    await post(0, `/publications/${future.id}/approve`);
    await post(0, `/publications/${future.id}/run`, {}, 409);
    assert.deepEqual(
      (await (await contexts[2].request.get(api + "/publications")).json()).items,
      [],
    );
    const disconnected = await post(0, "/connection/disconnect");
    assert.equal(disconnected.status, "disconnected");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(
        {
          realBackend: true,
          provider: "fake",
          transport: "none",
          published: false,
          sessions: 3,
          workspaces: 2,
          oauthSessionBinding: true,
          webhookSignature: true,
          dedupe: true,
          sourceTimeOrder: true,
          nativeInboxNoSend: true,
          editorSnapshot: true,
          approvalRetrySchedule: true,
          errors,
          external,
        },
        null,
        2,
      ),
    );
    console.log(
      "Instagram fake provider: HTTPS, OAuth/CSRF, signed events, native Inbox, two businesses and approved fake queue passed.",
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
