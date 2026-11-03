// Controlled API transport; real V22 DOM, dialogs and session bootstrap.
const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  for (const width of [390, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage(),
      errors = [],
      posts = [];
    let products = [],
      resources = [],
      rows = [],
      lost = true;
    const identity = {
      usuario: { id: 91, nome: "Teste", email: "teste@example.test" },
      negocio: { id: 17, nome: "Sorria fictícia", slug: "fixture", configuracao: {} },
      papel: "owner",
      csrf_token: "a".repeat(64),
    };
    page.on("pageerror", (e) => errors.push(e.message));
    await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
    await page.route("**/*", async (route) => {
      const request = route.request(),
        url = new URL(request.url()),
        p = url.pathname.replace("/api/v1", ""),
        method = request.method();
      if (url.origin !== origin) return route.abort();
      if (url.pathname.endsWith("/config.js"))
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
        });
      if (!url.pathname.startsWith("/api/v1/")) return route.continue();
      const data = method === "GET" ? null : request.postDataJSON();
      if (p === "/auth/session") return route.fulfill({ json: identity });
      if (p === "/auth/preferences")
        return route.fulfill({ json: { preferences: { theme: "light" }, revision: 0 } });
      if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
      if (p === "/message-enrichment/capabilities")
        return route.fulfill({ json: { mode: "disabled" } });
      if (p === "/clientes")
        return route.fulfill({ json: [{ id: 11, nome: "Cliente fictício", tags: [] }] });
      if (p === "/produtos") {
        if (method === "POST") {
          assert.equal(data.tipo, "Serviço");
          assert.equal(data.duracao_minutos, 45);
          products.push({ ...data, id: 21, versao: 1 });
          return route.fulfill({ status: 201, json: products[0] });
        }
        return route.fulfill({ json: products });
      }
      if (p === "/agenda/resources") {
        if (method === "POST") {
          resources.push({ id: data.operation_id, nome: data.nome, ativo: true, revision: 1 });
          return route.fulfill({ status: 201, json: resources[0] });
        }
        return route.fulfill({ json: { items: resources } });
      }
      if (p === "/agenda") return route.fulfill({ json: { items: [], truncated: false } });
      if (p === "/agenda/availability") return route.fulfill({ json: { available: true } });
      if (p === "/agenda/appointments") {
        if (method === "GET") return route.fulfill({ json: { items: rows, truncated: false } });
        assert.equal(request.headers()["x-socialmei-identity"], "91:17");
        posts.push(data);
        if (!rows.length)
          rows = [
            {
              ...data,
              id: data.operation_id,
              title: "Consulta",
              service_name: "Consulta",
              client_name: "Cliente fictício",
              resource_name: "Profissional fictício",
              ends_at: new Date(Date.parse(data.scheduled_for) + 45 * 60000).toISOString(),
              status: "pending",
              revision: 1,
            },
          ];
        if (lost) {
          lost = false;
          return route.abort("connectionreset");
        }
        assert.deepEqual(data, posts[0]);
        return route.fulfill({ status: 201, json: rows[0] });
      }
      if (p.endsWith("/history"))
        return route.fulfill({
          json: {
            items: [
              {
                revision: rows[0].revision,
                scheduled_for: rows[0].scheduled_for,
                ends_at: rows[0].ends_at,
                status: rows[0].status,
                recorded_at: new Date().toISOString(),
              },
            ],
          },
        });
      if (p.startsWith("/agenda/appointments/") && method === "PATCH") {
        assert.equal(data.expected_revision, rows[0].revision);
        rows[0] = { ...rows[0], ...data, revision: rows[0].revision + 1 };
        return route.fulfill({ json: rows[0] });
      }
      assert.equal(method, "GET", p);
      return route.fulfill({ json: [] });
    });
    try {
      await page.goto(origin + "/frontend/socialmei-app.html#/agenda");
      await page.getByText("Nenhum agendamento neste período.", { exact: true }).waitFor();
      await page.getByRole("button", { name: "Cadastrar serviço", exact: true }).click();
      await page.locator("#f_booking_service").fill("Consulta");
      await page.locator("#f_booking_duration").fill("45");
      await page
        .locator("dialog[open]")
        .getByRole("button", { name: "Salvar", exact: true })
        .click();
      await page.locator("dialog[open]").waitFor({ state: "hidden" });
      await page
        .getByRole("button", { name: "Cadastrar profissional/recurso", exact: true })
        .click();
      await page.locator("#f_booking_resource").fill("Profissional fictício");
      await page
        .locator("dialog[open]")
        .getByRole("button", { name: "Salvar", exact: true })
        .click();
      await page.locator("dialog[open]").waitFor({ state: "hidden" });
      await page.getByRole("button", { name: "Novo agendamento", exact: true }).click();
      await page.locator("#f_booking_start").fill("2026-11-10T14:00");
      await page.getByRole("button", { name: "Confirmar agendamento", exact: true }).click();
      await page.locator("dialog[open] [role=status]").filter({ hasText: /./ }).waitFor();
      await page.keyboard.press("Escape");
      await page.getByRole("button", { name: "Novo agendamento", exact: true }).click();
      await page.getByRole("button", { name: "Conferir pedido original", exact: true }).click();
      await page.locator("dialog[open]").waitFor({ state: "hidden" });
      assert.equal(rows.length, 1);
      assert.equal(posts.length, 2);
      await page.reload();
      await page.locator("[data-appointments] article").waitFor();
      await page.getByRole("button", { name: "Reagendar", exact: true }).click();
      await page.locator("#f_booking_start").fill("2026-11-10T15:00");
      await page
        .locator("dialog[open]")
        .getByRole("button", { name: "Confirmar", exact: true })
        .click();
      await page.locator("dialog[open]").waitFor({ state: "hidden" });
      assert.equal(rows[0].revision, 2);
      await page.getByRole("button", { name: "Cancelar agendamento", exact: true }).click();
      await page.getByRole("button", { name: "Confirmar cancelamento", exact: true }).click();
      await page.locator("dialog[open]").waitFor({ state: "hidden" });
      await page.getByRole("button", { name: "Histórico", exact: true }).click();
      await page.getByText(/revisão 3: Cancelado/).waitFor();
      await page.getByRole("button", { name: "Fechar", exact: true }).click();
      const resourcesBefore = resources.length;
      await page
        .getByRole("button", { name: "Cadastrar profissional/recurso", exact: true })
        .click();
      await page.locator("#f_booking_resource").fill("Formulário antigo");
      await page.evaluate(() => {
        const host = window.SocialMEIV22,
          old = host.identity;
        Object.defineProperty(host, "identity", {
          configurable: true,
          get: () => ({ ...old, negocio: { ...old.negocio, id: 18 } }),
        });
      });
      await page
        .locator("dialog[open]")
        .getByRole("button", { name: "Salvar", exact: true })
        .click();
      await page.locator("dialog[open]").waitFor({ state: "hidden" });
      assert.equal(resources.length, resourcesBefore, "Old workspace form must not write");
      assert.deepEqual(errors, []);
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
        false,
      );
    } finally {
      await context.close();
    }
  }
  console.log(
    "Appointments: service/resource, booking replay, reload, reschedule, cancellation/history at mobile and desktop passed (controlled transport).",
  );
};
