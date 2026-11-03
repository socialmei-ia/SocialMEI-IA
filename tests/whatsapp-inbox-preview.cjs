// Real local API, HMAC verification, PostgreSQL and visible inbox. No provider exists here.
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
module.exports = async function (browser, origin, fixture) {
  assert.match(origin, /^https:\/\/127\.0\.0\.1:[1-9][0-9]{3,4}$/);
  assert.equal(typeof fixture, "function");
  const contexts = [],
    owners = [],
    errors = [],
    external = [];
  try {
    for (const width of [1440, 390]) {
      const ctx = await browser.newContext({
        ignoreHTTPSErrors: true,
        viewport: { width, height: 1000 },
      });
      contexts.push(ctx);
      const marker = await ctx.request.get(origin + "/__preview");
      assert.equal((await marker.json()).environment, "local-disposable-preview");
      let ready = false;
      for (let attempt = 0; attempt < 30; attempt++) {
        if ((await ctx.request.get(origin + "/health/db")).status() === 200) {
          ready = true;
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      assert(ready, "Disposable API/database must be ready before registering fixtures");
      const registered = await ctx.request.post(origin + "/api/v1/auth/register", {
        headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
        data: {
          nome: "WA local ficticio",
          email: `wa-local-${randomUUID()}@example.test`,
          senha: "Fictitious-Local-123!",
        },
      });
      assert.equal(registered.status(), 201);
      const identity = await registered.json(),
        page = await ctx.newPage();
      page.on("pageerror", (e) => errors.push(e.message));
      await page.route("**/*", (route) => {
        if (new URL(route.request().url()).origin !== origin) {
          external.push("external-request");
          return route.abort();
        }
        return route.continue();
      });
      await page.goto(origin + "/frontend/socialmei-app.html#/caixa");
      await page.waitForFunction(
        () => window.SocialMEIV22?.identity && !document.getElementById("app").hidden,
      );
      const conversations = await (
        await ctx.request.get(origin + "/api/v1/message-enrichment/conversations")
      ).json();
      assert.equal(conversations.items.length, 0);
      owners.push({ ctx, page, identity, workspace: identity.negocio.id });
    }
    const setup = await fixture({ action: "setup", workspaces: owners.map((o) => o.workspace) });
    assert.equal(setup.setup, true);
    for (const owner of owners) {
      const readiness = await (
        await owner.ctx.request.get(origin + "/api/v1/integrations/readiness")
      ).json();
      assert.equal(readiness.whatsapp.receiving_configured, true);
      assert.equal(readiness.whatsapp.sending_available, false);
      assert.equal(
        readiness.whatsapp.session_live_verified,
        false,
        "A synthetic fixture must never claim a live session",
      );
    }
    const timestamp_ms = Date.now(),
      mid = "same-mid-" + randomUUID();
    const base = {
      action: "emit",
      timestamp_ms,
      mid,
      text: "Mensagem ficticia negocio A",
      sender: "5581990001234@c.us",
    };
    assert.equal(
      (await fixture({ ...base, workspace_id: owners[0].workspace, tamper: true })).status,
      403,
    );
    assert.equal(
      (
        await fixture({
          ...base,
          workspace_id: owners[0].workspace,
          forged_workspace: owners[1].workspace,
        })
      ).status,
      422,
    );
    for (const owner of owners)
      assert.equal(
        (
          await (
            await owner.ctx.request.get(origin + "/api/v1/message-enrichment/conversations")
          ).json()
        ).items.length,
        0,
      );
    let navigationCount = 0;
    owners[0].page.on("request", (request) => {
      if (request.isNavigationRequest() && request.resourceType() === "document") navigationCount++;
    });
    const received = await fixture({ ...base, workspace_id: owners[0].workspace });
    assert.equal(received.status, 200);
    assert.equal(received.processed, 1);
    // Polling must discover the new conversation without a reload or manual refresh.
    await owners[0].page.waitForFunction(
      () => C.some((c) => String(c[0]).startsWith("me-")),
      {},
      { timeout: 15000 },
    );
    const a = await (
      await owners[0].ctx.request.get(origin + "/api/v1/message-enrichment/conversations")
    ).json();
    assert.equal(a.items.length, 1);
    await owners[0].page.evaluate((id) => go("/caixa/me-" + id), a.items[0].id);
    await owners[0].page.locator(".ct .ms .bb", { hasText: base.text }).waitFor();
    assert.equal(await owners[0].page.locator(".ct .hd b").first().textContent(), "+5581990001234");
    assert.equal(navigationCount, 0);
    assert.equal(
      (await fixture({ ...base, workspace_id: owners[0].workspace, event: "message.any" }))
        .duplicates,
      1,
    );
    assert.equal(
      (
        await (
          await owners[1].ctx.request.get(origin + "/api/v1/message-enrichment/conversations")
        ).json()
      ).items.length,
      0,
    );
    const other = await fixture({
      ...base,
      workspace_id: owners[1].workspace,
      text: "Mensagem ficticia negocio B",
    });
    assert.equal(other.processed, 1, "Same provider MID on another account is independent");
    await owners[1].page.waitForFunction(
      () => C.some((c) => String(c[0]).startsWith("me-")),
      {},
      { timeout: 15000 },
    );
    const b = await (
      await owners[1].ctx.request.get(origin + "/api/v1/message-enrichment/conversations")
    ).json();
    assert.equal(b.items.length, 1);
    assert.notEqual(a.items[0].account_ref, b.items[0].account_ref);
    await owners[1].page.evaluate((id) => go("/caixa/me-" + id), b.items[0].id);
    await owners[1].page
      .locator(".ct .ms .bb", { hasText: "Mensagem ficticia negocio B" })
      .waitFor();
    assert.equal(await owners[1].page.getByText(base.text, { exact: true }).count(), 0);
    for (const owner of owners) {
      await owner.page.reload();
      const rows = await (
        await owner.ctx.request.get(origin + "/api/v1/message-enrichment/conversations")
      ).json();
      assert.equal(rows.items.length, 1);
      assert.equal(rows.items[0].messages.length, 1);
      assert.equal(
        (await owner.ctx.request.get(origin + "/internal/waha/local/webhook")).status(),
        404,
      );
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "WA isolated E2E passed: signed private HTTP, tamper/scope rejection, real persistence, polling without reload, dedup and two-account/workspace inbox isolation; no WAHA/provider/send.",
    );
  } finally {
    for (const ctx of contexts) await ctx.close();
  }
};
