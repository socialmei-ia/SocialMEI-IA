/* Synthetic transport; real native inbox composer, review and receipt. */
const assert = require("node:assert/strict");
module.exports = async function (browser, origin) {
  for (const mode of ["disabled", "confirmed", "uncertain", "changed"])
    for (const width of [1440, 390])
      for (const theme of ["light", "dark"]) {
        const context = await browser.newContext({
            viewport: { width, height: 1000 },
            reducedMotion: "reduce",
          }),
          page = await context.newPage();
        const errors = [],
          external = [],
          writes = [];
        let jobs = [],
          runs = 0,
          approvedRevision = null;
        const identity = {
          usuario: { id: 91, nome: "Operador", email: "operator@example.test" },
          negocio: { id: 17, nome: "Negócio fictício", slug: "synthetic", configuracao: {} },
          papel: "owner",
          csrf_token: "a".repeat(64),
        };
        const incoming = {
          id: 1,
          revision: 1,
          channel: "instagram",
          origin: "instagram",
          contact_name: "Contato Instagram teste",
          messages: [
            { id: 11, text: "Gostaria de saber o prazo.", occurred_at: "2026-10-27T09:00:00Z" },
          ],
        };
        await page.addInitScript(() =>
          localStorage.setItem("socialmei-auth-browser-scope", "91:17"),
        );
        page.on("pageerror", (error) => errors.push(error.message));
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
          const p = url.pathname.replace("/api/v1", "");
          if (p === "/auth/session") return route.fulfill({ json: identity });
          if (p === "/auth/preferences")
            return route.fulfill({ json: { preferences: { theme }, revision: 0 } });
          if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
          if (p === "/message-enrichment/capabilities")
            return route.fulfill({
              json: { mode: "disabled", workspace_id: 17, instagram_inbox: true },
            });
          if (p === "/message-enrichment/conversations")
            return route.fulfill({ json: { workspace_id: 17, items: [incoming] } });
          if (p === "/integrations/readiness")
            return route.fulfill({
              json: {
                instagram: {
                  oauth_available: true,
                  reply_preparation_available: true,
                  incoming_available: true,
                  send_enabled: mode !== "disabled",
                },
              },
            });
          if (p === "/instagram/meta/status")
            return route.fulfill({ json: { status: "connected", credential_available: true } });
          if (p === "/instagram/direct/jobs" && request.method() === "GET")
            return route.fulfill({ json: { items: jobs } });
          if (p.startsWith("/instagram/direct/") && request.method() === "POST") {
            writes.push(p);
            assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
            assert.equal(request.headers()["x-socialmei-identity"], "91:17");
            if (p === "/instagram/direct/jobs") {
              assert.equal(request.postDataJSON().source_message_id, 11);
              jobs = [
                {
                  id: "11111111-1111-4111-8111-111111111111",
                  conversation_id: 1,
                  source_message_id: 11,
                  text: request.postDataJSON().text,
                  revision: 1,
                  status: "draft",
                  attempts: 0,
                  provider_message_id: null,
                  created_at: "2026-10-27T10:00:00Z",
                  updated_at: "2026-10-27T10:00:00Z",
                },
              ];
            } else if (p.endsWith("/approve")) {
              approvedRevision = request.postDataJSON().expected_revision;
              if (mode === "changed" && approvedRevision !== jobs[0].revision)
                return route.fulfill({
                  status: 409,
                  json: { detail: "Rascunho alterado; revise novamente." },
                });
              if (mode !== "changed") assert.equal(approvedRevision, 1);
              jobs[0].status = "approved";
            } else if (p.endsWith("/run")) {
              assert.equal(request.postDataJSON().expected_revision, 1);
              runs++;
              jobs[0].status = mode;
              jobs[0].attempts = 1;
              if (mode === "confirmed") jobs[0].provider_message_id = "synthetic-provider-message";
            } else throw Error("Unexpected mutation");
            return route.fulfill({ json: jobs[0] });
          }
          assert.equal(request.method(), "GET");
          return route.fulfill({ json: [] });
        });
        try {
          await page.goto(origin + "/frontend/socialmei-app.html#/caixa/me-1");
          await page.locator("[data-ig-prepare]").waitFor();
          await page.locator("#ta").fill("Prazo confirmado: cinco dias úteis.");
          await page.locator("[data-ig-prepare]").click();
          await page
            .getByText("Rascunho salvo no servidor. Nenhuma mensagem foi enviada.", { exact: true })
            .waitFor();
          await page.locator('[data-ig-reply][aria-busy="false"]').waitFor();
          const fs = require("node:fs"),
            path = require("node:path");
          const out = path.join(__dirname, "../test-results/instagram-direct");
          fs.mkdirSync(out, { recursive: true });
          if (mode === "disabled") {
            await page.locator("[data-ig-reply]").scrollIntoViewIfNeeded();
            await page.screenshot({
              path: path.join(out, `${width}-${theme}.png`),
              fullPage: true,
            });
          }
          assert.equal(writes.length, 1);
          assert.equal(runs, 0);
          await page.getByRole("button", { name: "Revisar resposta", exact: true }).click();
          const dialog = page.getByRole("dialog", { name: "Revisar Direct do Instagram" });
          await dialog.waitFor();
          const send = dialog.getByRole("button", {
            name: "Confirmar envio ao Instagram",
            exact: true,
          });
          if (mode === "disabled") {
            assert(await send.isDisabled());
            await page.keyboard.press("Escape");
            assert.equal(runs, 0);
          } else if (mode === "changed") {
            jobs = [{ ...jobs[0], text: "Texto alterado em outra sessão.", revision: 2 }];
            // Reproduce an asynchronous refresh while the original review stays open.
            await Promise.all([
              page.waitForResponse(
                (r) => r.url().endsWith("/instagram/direct/jobs") && r.request().method() === "GET",
              ),
              page.evaluate(() => {
                [...document.querySelectorAll("[data-ig-reply] button")]
                  .find((button) => button.textContent === "Consultar respostas")
                  .click();
              }),
            ]);
            await page.waitForFunction(() =>
              document
                .querySelector("[data-ig-reply] select")
                .textContent.includes("Texto alterado"),
            );
            assert(
              await dialog
                .getByText("Prazo confirmado: cinco dias úteis.", { exact: true })
                .isVisible(),
            );
            await send.click();
            await dialog.getByText(/Rascunho alterado; revise novamente/).waitFor();
            assert.equal(
              approvedRevision,
              1,
              "Approval must use exactly the revision displayed for review",
            );
            assert.equal(runs, 0, "A changed draft must never be dispatched");
            await dialog.getByRole("button", { name: "Fechar", exact: true }).click();
          } else {
            await send.click();
            await dialog
              .getByText(
                mode === "confirmed" ? "Confirmada pela Meta" : "Resultado incerto; não repetir",
                { exact: true },
              )
              .waitFor();
            assert(await send.isDisabled());
            assert.equal(runs, 1);
            await dialog.getByRole("button", { name: "Fechar", exact: true }).click();
            if (mode === "confirmed")
              await page
                .locator(".ct .ms .mg.o .bb", { hasText: "Prazo confirmado: cinco dias úteis." })
                .waitFor();
            await page.getByRole("button", { name: "Consultar respostas", exact: true }).click();
            assert.equal(runs, 1, "Reading state cannot send again");
          }
          assert.deepEqual(errors, []);
          assert.deepEqual(external, []);
        } finally {
          await context.close();
        }
      }
  return "Native Instagram Direct: draft, explicit review, sender disabled, receipt and uncertain/no-retry";
};
