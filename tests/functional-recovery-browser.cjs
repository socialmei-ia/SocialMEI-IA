// Real UI with controlled transport. No provider or customer data is used.
const assert = require("node:assert/strict");

module.exports = async function (browser, origin) {
  const identity = {
    usuario: { id: 91, nome: "Auditoria", email: "audit@example.test" },
    negocio: { id: 17, slug: "audit", nome: "Negócio de teste", configuracao: {} },
    papel: "owner",
    csrf_token: "a".repeat(64),
  };
  const key = "socialmei-v22-operation:91:17";
  const initial = {
    path: "/financeiro/7/excluir",
    method: "POST",
    payload: { expected_version: 1 },
  };
  const operationId = "11111111-1111-4111-8111-111111111111";
  const pending = {
    signature: JSON.stringify(initial),
    packet: { ...initial.payload, operation_id: operationId },
  };
  for (const outcome of [
    "confirmed",
    "unavailable",
    "conflict",
    "invalid",
    "replaced",
    "switched",
    "replaced_during",
  ])
    for (const width of [390, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      const writes = [],
        errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await page.addInitScript(
        ({ key, pending, outcome }) => {
          localStorage.setItem("socialmei-auth-browser-scope", "91:17");
          if (!sessionStorage.getItem("audit-initialized")) {
            const saved = structuredClone(pending);
            if (outcome === "invalid") {
              saved.signature = JSON.stringify({
                path: "/auth/logout",
                method: "POST",
                payload: {},
              });
            }
            localStorage.setItem(key, JSON.stringify(saved));
            sessionStorage.setItem("audit-initialized", "true");
          }
        },
        { key, pending, outcome },
      );
      await page.route("**/*", async (route) => {
        const request = route.request(),
          url = new URL(request.url());
        if (url.origin !== origin) return route.abort();
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        const p = url.pathname.replace("/api/v1", "");
        if (p === "/auth/session") return route.fulfill({ json: identity });
        if (p === "/auth/preferences")
          return route.fulfill({ json: { preferences: { theme: "auto" }, revision: 0 } });
        if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (p === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled" } });
        if (request.method() !== "GET") {
          writes.push({ path: p, body: request.postDataJSON() });
          assert.equal(p, initial.path);
          assert.equal(request.headers()["x-socialmei-identity"], "91:17");
          if (outcome === "unavailable") return route.abort("connectionreset");
          if (outcome === "conflict")
            return route.fulfill({
              status: 409,
              json: { detail: "A versão mudou; confira o lançamento." },
            });
          if (outcome === "replaced_during")
            await page.evaluate(
              ({ key, pending }) => {
                pending.packet.operation_id = "22222222-2222-4222-8222-222222222222";
                localStorage.setItem(key, JSON.stringify(pending));
              },
              { key, pending },
            );
          return route.fulfill({ json: { id: 7, versao: 2, excluida: true } });
        }
        if (p === "/financeiro")
          return route.fulfill({
            json: [
              {
                id: 7,
                versao: 2,
                descricao: "Lançamento alterado",
                tipo: "receita",
                status: "pago",
                valor: 10,
                vencimento: "2026-10-30",
                data_pagamento: "2026-10-30",
              },
            ],
          });
        return route.fulfill({ json: [] });
      });
      try {
        await page.clock.setFixedTime(new Date("2026-11-01T12:00:00Z"));
        await page.goto(origin + "/frontend/socialmei-app.html#/negocio/financeiro");
        await page.getByRole("button", { name: "Conferir operação pendente", exact: true }).click();
        if (outcome === "invalid") {
          await page.getByText(/Não foi possível ler a operação pendente/).waitFor();
          assert.equal(writes.length, 0);
        } else {
          if (outcome === "replaced")
            await page.evaluate(
              ({ key, pending }) => {
                pending.packet.operation_id = "22222222-2222-4222-8222-222222222222";
                localStorage.setItem(key, JSON.stringify(pending));
              },
              { key, pending },
            );
          if (outcome === "switched") {
            // Let lazy bootstrap reads finish before deliberately making the
            // in-memory identity stale. Otherwise an unrelated GET correctly
            // reloads the page before this test can exercise the dialog guard.
            await page.waitForLoadState("networkidle");
            await page.evaluate(() => {
              SocialMEIV22.identity.negocio.id = 18;
            });
          }
          await page
            .getByRole("button", { name: "Confirmar consulta da operação", exact: true })
            .click();
          if (["replaced", "switched"].includes(outcome)) {
            await page
              .getByText(
                "A sessão ou a operação pendente mudou. Confira novamente antes de continuar.",
                { exact: true },
              )
              .waitFor();
            assert.equal(writes.length, 0);
            assert(await page.evaluate((key) => !!localStorage.getItem(key), key));
            continue;
          }
          await page.waitForFunction(
            ({ key, retained }) => !!localStorage.getItem(key) === retained,
            { key, retained: ["unavailable", "replaced_during"].includes(outcome) },
          );
          if (outcome === "unavailable") {
            await page
              .locator("dialog[open] button", { hasText: "Confirmar consulta" })
              .waitFor({ state: "visible" });
            await page.waitForFunction(
              () =>
                ![...document.querySelectorAll("dialog[open] button")].find(
                  (b) => b.textContent === "Confirmar consulta da operação",
                ).disabled,
            );
          }
          if (outcome === "replaced_during")
            await page.getByText("Operação confirmada no servidor.", { exact: true }).waitFor();
          if (outcome === "confirmed") {
            await page.getByText("Operação confirmada no servidor.", { exact: true }).waitFor();
            assert.equal(await page.locator("[data-operation-recovery]").count(), 0);
          }
          assert.equal(writes.length, 1);
          assert.deepEqual(
            writes[0].body,
            pending.packet,
            "Recovery must use the original version and UUID",
          );
          if (outcome === "replaced_during")
            assert.equal(
              await page.evaluate(
                (key) => JSON.parse(localStorage.getItem(key)).packet.operation_id,
                key,
              ),
              "22222222-2222-4222-8222-222222222222",
            );
        }
        assert.deepEqual(errors, []);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
      } finally {
        await context.close();
      }
    }

  const context = await browser.newContext({ viewport: { width: 390, height: 1000 } });
  const page = await context.newPage();
  let available = false,
    writes = 0;
  await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
  await page.route("**/*", (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname.endsWith("/config.js"))
      return route.fulfill({
        contentType: "text/javascript",
        body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
      });
    if (!url.pathname.startsWith("/api/v1/")) return route.continue();
    const p = url.pathname.replace("/api/v1", "");
    if (request.method() !== "GET") writes++;
    if (p === "/auth/session") return route.fulfill({ json: identity });
    if (p === "/auth/preferences")
      return route.fulfill({ json: { preferences: { theme: "light" }, revision: 0 } });
    if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
    if (p === "/message-enrichment/capabilities")
      return route.fulfill({ json: { mode: "disabled", workspace_id: 17, instagram_inbox: true } });
    if (p === "/message-enrichment/conversations")
      return route.fulfill({
        json: {
          workspace_id: 17,
          items: [
            {
              id: 1,
              revision: 1,
              origin: "instagram",
              channel: "instagram",
              contact_name: "Contato de teste",
              messages: [{ id: 11, text: "Olá", occurred_at: "2026-10-31T09:00:00Z" }],
            },
          ],
        },
      });
    if (p === "/integrations/readiness")
      return available
        ? route.fulfill({
            json: {
              instagram: {
                reply_preparation_available: true,
                incoming_available: true,
                send_enabled: false,
              },
            },
          })
        : route.fulfill({ status: 503, json: { detail: "Falha transitória" } });
    if (p === "/instagram/meta/status")
      return route.fulfill({ json: { status: "connected", credential_available: true } });
    if (p === "/instagram/direct/jobs") return route.fulfill({ json: { items: [] } });
    return route.fulfill({ json: [] });
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html#/caixa/me-1");
    const retry = page.getByRole("button", { name: "Consultar conexão novamente", exact: true });
    await retry.click();
    await page.getByRole("button", { name: "Consultar conexão novamente", exact: true }).waitFor();
    available = true;
    await page.getByRole("button", { name: "Consultar conexão novamente", exact: true }).click();
    await page.locator("[data-ig-prepare]").waitFor();
    assert.equal(await page.locator("[data-ig-reply-unavailable]").count(), 0);
    assert.equal(writes, 0, "Retrying connection must never send or prepare a message");
  } finally {
    await context.close();
  }
  console.log("Functional recovery: 14 pending-operation scenarios and Instagram retry passed.");
};
