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
      await page.evaluate(() => go("/negocio/clientes"));
      await page.getByRole("button", { name: "Novo cliente", exact: true }).click();
      const customerName = "Cliente ficticio negocio " + owners.length;
      await page.locator("#f_n").fill(customerName);
      await page.locator("dialog button[type=submit]").click();
      await page.locator("dialog[open]").waitFor({ state: "hidden" });
      await page.getByText(customerName, { exact: true }).first().waitFor();
      const clients = await (await ctx.request.get(origin + "/api/v1/clientes")).json();
      assert.equal(clients.length, 1);
      await page.evaluate(() => go("/caixa"));
      const conversations = await (
        await ctx.request.get(origin + "/api/v1/message-enrichment/conversations")
      ).json();
      assert.equal(conversations.items.length, 0);
      owners.push({ ctx, page, identity, workspace: identity.negocio.id, customer: clients[0] });
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
    const first = owners[0],
      second = owners[1];
    const firstHeaders = {
      Origin: origin,
      "X-SocialMEI-Client": "browser",
      "X-SocialMEI-Identity": `${first.identity.usuario.id}:${first.workspace}`,
      "X-SocialMEI-CSRF": first.identity.csrf_token,
    };
    const path = origin + `/api/v1/message-enrichment/conversations/${a.items[0].id}/customer`;
    const before = await (await first.ctx.request.get(path)).json();
    const forbidden = await first.ctx.request.patch(path, {
      headers: firstHeaders,
      data: { expected_revision: before.revision, cliente_id: second.customer.id },
    });
    assert.equal(forbidden.status(), 404);
    await first.page.getByRole("button", { name: "Associar cliente do CRM", exact: true }).click();
    await first.page.locator("#f_inbox_customer").selectOption(String(first.customer.id));
    await first.page.getByRole("button", { name: "Salvar vínculo", exact: true }).click();
    await first.page.locator("dialog[open]").waitFor({ state: "hidden" });
    await first.page.reload();
    await first.page
      .locator("[data-inbox-customer]")
      .getByText("Cliente: " + first.customer.nome, { exact: true })
      .waitFor();
    assert.equal(await first.page.locator(".ct .hd b").first().textContent(), "+5581990001234");
    assert.equal((await (await first.ctx.request.get(path)).json()).cliente_id, first.customer.id);
    await first.page.getByRole("button", { name: "Alterar cliente do CRM", exact: true }).click();
    await first.page.locator("#f_inbox_customer").selectOption("");
    const extra = await fixture({
      ...base,
      workspace_id: first.workspace,
      mid: mid + "-second",
      text: "Segunda mensagem ficticia",
    });
    assert.equal(extra.processed, 1);
    await first.page.getByRole("button", { name: "Salvar vínculo", exact: true }).click();
    await first.page
      .getByText(
        "A conversa ou o cliente mudou. Feche e atualize o vínculo antes de salvar novamente.",
        { exact: true },
      )
      .waitFor();
    await first.page.keyboard.press("Escape");
    await first.page.getByRole("button", { name: "Atualizar vínculo CRM", exact: true }).click();
    await first.page.getByRole("button", { name: "Alterar cliente do CRM", exact: true }).click();
    await first.page.locator("#f_inbox_customer").selectOption("");
    await first.page.getByRole("button", { name: "Salvar vínculo", exact: true }).click();
    await first.page.locator("dialog[open]").waitFor({ state: "hidden" });
    assert.equal((await (await first.ctx.request.get(path)).json()).cliente_id, null);
    await first.page.locator("#ta").fill("Rascunho ficticio de atendimento humano; nao enviar.");
    await first.page
      .getByRole("button", { name: "Preparar resposta no servidor", exact: true })
      .click();
    await first.page
      .locator("[data-wa-replies] select option")
      .filter({ hasText: "Rascunho" })
      .waitFor({ state: "attached" });
    const drafts = await (
      await first.ctx.request.get(
        origin + `/api/v1/whatsapp/replies?conversation_id=${a.items[0].id}`,
      )
    ).json();
    assert.equal(drafts.send_enabled, false);
    assert.equal(drafts.items.length, 1);
    assert.equal(drafts.items[0].status, "draft");
    assert.equal(await first.page.locator("[data-wa-send]").isDisabled(), true);
    const human = await (
      await first.ctx.request.get(
        origin + `/api/v1/whatsapp/bot/conversations/${a.items[0].id}/status`,
      )
    ).json();
    assert.equal(human.state, "human");
    assert.equal(human.enabled, false);
    assert.equal(
      (
        await second.ctx.request.get(origin + "/api/v1/whatsapp/replies/" + drafts.items[0].id)
      ).status(),
      404,
    );
    await first.page.reload();
    await first.page
      .locator("[data-wa-replies] select option")
      .filter({ hasText: "Rascunho" })
      .waitFor({ state: "attached" });
    assert.equal(await first.page.locator("[data-wa-send]").isDisabled(), true);
    for (const owner of owners) {
      await owner.page.reload();
      const rows = await (
        await owner.ctx.request.get(origin + "/api/v1/message-enrichment/conversations")
      ).json();
      assert.equal(rows.items.length, 1);
      assert.equal(rows.items[0].messages.length, owner === first ? 2 : 1);
      assert.equal(
        (await owner.ctx.request.get(origin + "/internal/waha/local/webhook")).status(),
        404,
      );
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "WA isolated E2E passed: signed receiving, inbox/CRM, dedup/isolation, durable human draft and bot pause with dispatch disabled; no WAHA/provider/send.",
    );
  } finally {
    for (const ctx of contexts) await ctx.close();
  }
};
