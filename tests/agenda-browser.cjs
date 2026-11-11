// Controlled transport, real account bootstrap and reminder controls.
const assert = require("node:assert/strict");
module.exports = async function (browser, origin) {
  for (const width of [390, 1440])
    for (const role of ["owner", "viewer"]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage(),
        errors = [],
        posts = [];
      const identity = {
        usuario: { id: 91, nome: "Teste", email: "teste@example.test" },
        negocio: { id: 17, nome: "Agenda fictícia", slug: "fixture", configuracao: {} },
        papel: role,
        csrf_token: "a".repeat(64),
      };
      let rows = [],
        failedRead = false;
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      await page.route("**/*", (route) => {
        const request = route.request(),
          url = new URL(request.url()),
          p = url.pathname.replace("/api/v1", "");
        if (url.origin !== origin) return route.abort();
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        if (p === "/auth/session") return route.fulfill({ json: identity });
        if (p === "/auth/preferences")
          return route.fulfill({
            json: { preferences: { theme: width === 390 ? "dark" : "light" }, revision: 0 },
          });
        if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (p === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled" } });
        if (p === "/clientes")
          return route.fulfill({
            json: [
              { id: 11, nome: "Cliente igual", email: "um@example.test", tags: [] },
              { id: 12, nome: "Cliente igual", email: "dois@example.test", tags: [] },
            ],
          });
        if (p === "/agenda" && request.method() === "GET") {
          if (!failedRead) {
            failedRead = true;
            return route.fulfill({
              status: 503,
              json: { detail: "Agenda temporariamente indisponível." },
            });
          }
          return route.fulfill({ json: { items: rows, truncated: false } });
        }
        if (p === "/agenda" && request.method() === "POST") {
          assert.equal(role, "owner");
          const data = request.postDataJSON();
          posts.push(data);
          assert.equal(request.headers()["x-socialmei-identity"], "91:17");
          assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
          if (!rows.length) {
            rows = [{ ...data, id: data.operation_id, status: "pending", revision: 1 }];
            return route.abort("connectionreset");
          }
          assert.deepEqual(
            data,
            posts[0],
            "Lost response must replay the original request and UUID",
          );
          if (width === 1440 && posts.length === 2)
            return route.fulfill({
              status: 201,
              json: { ...rows[0], id: "33333333-3333-4333-8333-333333333333" },
            });
          return route.fulfill({ status: 201, json: rows[0] });
        }
        if (p.startsWith("/agenda/") && request.method() === "PATCH") {
          const data = request.postDataJSON();
          assert.equal(data.expected_revision, rows[0].revision);
          rows[0] = { ...rows[0], status: data.status, revision: rows[0].revision + 1 };
          return route.fulfill({ json: rows[0] });
        }
        assert.equal(request.method(), "GET", p);
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/agenda");
        await page.getByText("Agenda temporariamente indisponível.", { exact: true }).waitFor();
        assert(await page.getByRole("button", { name: "Novo lembrete", exact: true }).isDisabled());
        await page.getByRole("button", { name: "Consultar agenda", exact: true }).click();
        await page.getByText("Nenhum lembrete neste período.", { exact: true }).waitFor();
        if (role === "viewer") {
          assert(
            await page.getByRole("button", { name: "Novo lembrete", exact: true }).isDisabled(),
          );
          assert.equal(posts.length, 0);
          assert.deepEqual(errors, []);
          continue;
        }
        await page.getByRole("button", { name: "Novo lembrete", exact: true }).click();
        await page.getByLabel("O que lembrar", { exact: false }).fill("Revisar orçamento de teste");
        await page.locator("#f_agenda_date").fill("2026-11-02");
        await page.locator("#f_agenda_time").fill("14:30");
        await page.locator("#f_agenda_client").selectOption("12");
        await page.getByRole("button", { name: "Salvar lembrete", exact: true }).click();
        await page.getByText(/Feche esta janela e use Retomar lembrete pendente/).waitFor();
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: "Retomar lembrete pendente", exact: true }).click();
        await page
          .locator("dialog[open]")
          .getByRole("heading", { name: "Retomar lembrete pendente", exact: true })
          .waitFor();
        assert.equal(
          await page.locator("#f_agenda_title").inputValue(),
          "Revisar orçamento de teste",
        );
        assert(await page.locator("#f_agenda_title").isDisabled());
        await page
          .getByRole("button", { name: "Confirmar registro original", exact: true })
          .click();
        if (width === 1440) {
          await page.getByText(/Resposta inválida. Retome o pedido original/).waitFor();
          assert(
            await page.evaluate(() => !!localStorage.getItem("socialmei-agenda-pending-v1:91:17")),
          );
          await page.keyboard.press("Escape");
          await page
            .getByRole("button", { name: "Retomar lembrete pendente", exact: true })
            .click();
          await page
            .getByRole("button", { name: "Confirmar registro original", exact: true })
            .click();
        }
        await page.getByText("Lembrete salvo no negócio.", { exact: true }).waitFor();
        assert.equal(rows.length, 1);
        assert.equal(posts.length, width === 1440 ? 3 : 2);
        assert.equal(posts[0].cliente_id, 12);
        await page.reload();
        const checkbox = page.getByRole("checkbox", {
          name: "Marcar como feito: Revisar orçamento de teste",
          exact: true,
        });
        await checkbox.click();
        await page
          .getByRole("checkbox", {
            name: "Marcar como feito: Revisar orçamento de teste",
            checked: true,
          })
          .waitFor();
        assert.equal(rows[0].status, "done");
        page.once("dialog", (dialog) => dialog.accept());
        await page.locator(".agi").getByRole("button", { name: "Cancelar", exact: true }).click();
        await page.getByText("Nenhum lembrete neste período.", { exact: true }).waitFor();
        assert.equal(rows[0].status, "cancelled");
        await page.evaluate(() => {
          const original = Storage.prototype.getItem;
          window.__restoreAgendaStorage = () => (Storage.prototype.getItem = original);
          Storage.prototype.getItem = function (key) {
            if (String(key).startsWith("socialmei-agenda-pending-v1:"))
              throw new DOMException("Unavailable", "SecurityError");
            return original.call(this, key);
          };
          window.render();
        });
        await page.getByText(/O navegador não permite preservar operações/).waitFor();
        assert(await page.getByRole("button", { name: "Novo lembrete", exact: true }).isDisabled());
        await page.evaluate(() => window.__restoreAgendaStorage());
        await page.getByRole("button", { name: "Consultar agenda", exact: true }).click();
        await page.getByText("Nenhum lembrete neste período.", { exact: true }).waitFor();
        assert.equal(
          await page.evaluate(() => !!localStorage.getItem("socialmei-agenda-pending-v1:91:17")),
          false,
        );
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        assert.deepEqual(errors, []);
      } finally {
        await context.close();
      }
    }
  console.log(
    "Agenda: outage recovery, durable creation replay, client IDs, reload, completion, cancellation and read-only role passed at two widths.",
  );
};
