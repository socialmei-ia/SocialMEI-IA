/* Native inbox with synthetic API and provider receipts. No external network. */
const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  let cases = 0;
  for (const mode of [
    "disabled",
    "confirmed",
    "uncertain",
    "lost-create",
    "lost-create-reload",
    "lost-send",
    "storage-blocked",
    "viewer",
  ])
    for (const width of [390, 1440]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage(),
        errors = [],
        external = [],
        creates = [],
        sends = [];
      let jobs = [],
        lostCreate = false;
      const identity = {
        usuario: { id: 91, nome: "Operador", email: "operator@example.test" },
        negocio: { id: 17, nome: "Negócio fictício", slug: "synthetic", configuracao: {} },
        papel: mode === "viewer" ? "viewer" : "owner",
        csrf_token: "a".repeat(64),
      };
      const incoming = {
        id: 1,
        revision: 1,
        channel: "whatsapp",
        origin: "waha",
        contact_name: "Contato autorizado fictício",
        messages: [{ id: 11, text: "Qual o preço?", occurred_at: "2026-10-31T09:00:00Z" }],
      };
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      if (mode === "storage-blocked")
        await page.addInitScript(() => {
          const write = Storage.prototype.setItem;
          Storage.prototype.setItem = function (key, value) {
            if (String(key).startsWith("socialmei-whatsapp-reply-pending-v1:"))
              throw Error("Armazenamento indisponível");
            return write.call(this, key, value);
          };
        });
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/*", async (route) => {
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
        const path = url.pathname.replace("/api/v1", "");
        if (path === "/auth/session") return route.fulfill({ json: identity });
        if (path === "/auth/preferences")
          return route.fulfill({
            json: { preferences: { theme: width === 390 ? "dark" : "light" }, revision: 0 },
          });
        if (path === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (path === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled", workspace_id: 17, waha_inbox: true } });
        if (path === "/message-enrichment/conversations")
          return route.fulfill({ json: { workspace_id: 17, items: [incoming] } });
        if (path === "/whatsapp/replies" && request.method() === "GET") {
          assert.equal(url.searchParams.get("conversation_id"), "1");
          return route.fulfill({ json: { items: jobs, send_enabled: mode !== "disabled" } });
        }
        if (path === "/whatsapp/replies" && request.method() === "POST") {
          assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
          assert.equal(request.headers()["x-socialmei-identity"], "91:17");
          const payload = request.postDataJSON();
          assert.deepEqual(Object.keys(payload).sort(), [
            "operation_id",
            "source_message_id",
            "text",
          ]);
          assert.equal(payload.source_message_id, 11);
          creates.push(payload);
          if (!jobs.length)
            jobs = [
              {
                id: payload.operation_id,
                source_message_id: 11,
                conversation_id: 1,
                text: payload.text,
                status: "draft",
                provider_message_id: null,
                created_at: "2026-10-31T10:00:00Z",
                finished_at: null,
              },
            ];
          if (mode.startsWith("lost-create") && !lostCreate) {
            lostCreate = true;
            return route.abort();
          }
          return route.fulfill({ status: 201, json: jobs[0] });
        }
        if (path.endsWith("/send") && request.method() === "POST") {
          assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
          assert.deepEqual(request.postDataJSON(), {});
          sends.push(path);
          jobs[0] = {
            ...jobs[0],
            status: mode === "uncertain" ? "uncertain" : "confirmed",
            provider_message_id: mode === "uncertain" ? null : "synthetic-waha-receipt",
            finished_at: "2026-10-31T10:01:00Z",
          };
          if (mode === "lost-send") return route.abort();
          return route.fulfill({ json: jobs[0] });
        }
        assert.equal(request.method(), "GET", "unexpected write: " + path);
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/caixa/me-1");
        await page.locator('[data-wa-replies][aria-busy="false"]').waitFor();
        if (mode === "viewer") {
          assert.equal(await page.locator("#ta").isDisabled(), true);
          assert.equal(await page.locator("[data-wa-prepare]").isDisabled(), true);
          assert.equal(creates.length, 0);
        } else {
          await page.locator("#ta").fill("O produto custa R$ 25. <script>teste</script>");
          await page.locator("[data-wa-prepare]").click();
          if (mode === "storage-blocked") {
            await page.getByText("Armazenamento indisponível", { exact: true }).waitFor();
            assert.equal(creates.length, 0);
            assert.equal(sends.length, 0);
            assert.deepEqual(errors, []);
            assert.deepEqual(external, []);
            cases++;
            continue;
          }
          if (mode === "lost-create-reload") {
            await page.getByText(/A mesma operação será usada/).waitFor();
            await page.reload();
            await page.locator('[data-wa-replies][aria-busy="false"]').waitFor();
            assert.equal(await page.locator("#ta").inputValue(), jobs[0].text);
            assert.equal(await page.locator("[data-wa-prepare]").isDisabled(), true);
            assert.equal(creates.length, 1);
          }
          if (mode === "lost-create") {
            await page.getByText(/A mesma operação será usada/).waitFor();
            await page.locator("[data-wa-prepare]").click();
            assert.equal(creates.length, 2);
            assert.deepEqual(creates[0], creates[1]);
          }
          if (mode !== "lost-create-reload")
            await page
              .getByText(
                "Rascunho salvo no servidor e bot pausado. Nenhuma mensagem foi enviada.",
                {
                  exact: true,
                },
              )
              .waitFor();
          if (mode === "disabled")
            assert.equal(await page.locator("[data-wa-send]").isDisabled(), true);
          else {
            page.once("dialog", (dialog) => dialog.accept());
            await page.locator("[data-wa-send]").click();
            if (mode === "lost-send") {
              await page.getByText(/O envio não será repetido automaticamente/).waitFor();
              assert.equal(await page.locator("[data-wa-send]").isDisabled(), true);
              await page.getByRole("button", { name: "Consultar respostas", exact: true }).click();
            }
            await page.locator('[data-wa-replies][aria-busy="false"]').waitFor();
            await page.reload();
            await page.locator('[data-wa-replies][aria-busy="false"]').waitFor();
            await page.getByLabel("Respostas WhatsApp registradas").selectOption(jobs[0].id);
            assert.equal(await page.locator("[data-wa-send]").isDisabled(), true);
            assert.equal(sends.length, 1);
            if (mode !== "uncertain")
              await page
                .locator(".ct .ms .m.sm")
                .filter({ hasText: "Aceita pelo WAHA; entrega não verificada" })
                .waitFor();
          }
          assert.equal(
            await page
              .locator("script")
              .filter({ hasText: /^teste$/ })
              .count(),
            0,
          );
        }
        assert.deepEqual(errors, []);
        assert.deepEqual(external, []);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
          true,
        );
        cases++;
      } finally {
        await context.close();
      }
    }
  return { cases, external_messages_sent: 0, provider: "synthetic" };
};
