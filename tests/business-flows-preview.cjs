// Real browser + API + disposable PostgreSQL. Never accepts a public/production origin.
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
async function run(browser, origin, { sorriaWidth = 1440, styleWidth = 390 } = {}) {
  assert.match(origin, /^https:\/\/127\.0\.0\.1:[1-9][0-9]{3,4}$/);
  const contexts = [],
    errors = [],
    external = [];
  async function account(name, width) {
    const ctx = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width, height: 1000 },
      timezoneId: "America/Fortaleza",
    });
    contexts.push(ctx);
    const marker = await ctx.request.get(origin + "/__preview");
    assert.equal((await marker.json()).environment, "local-disposable-preview");
    const response = await ctx.request.post(origin + "/api/v1/auth/register", {
      headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
      data: {
        nome: name + " fictício",
        email: `business-${randomUUID()}@example.test`,
        senha: "Fictitious-Local-123!",
      },
    });
    assert.equal(response.status(), 201, "Disposable registration must succeed");
    const identity = await response.json();
    const headers = {
      Origin: origin,
      "X-SocialMEI-Client": "browser",
      "X-SocialMEI-Identity": `${identity.usuario.id}:${identity.negocio.id}`,
      "X-SocialMEI-CSRF": identity.csrf_token,
    };
    assert.equal(
      (
        await ctx.request.patch(origin + "/api/v1/auth/profile", {
          headers,
          data: { nome_negocio: name },
        })
      ).status(),
      200,
    );
    const page = await ctx.newPage();
    page.on("response", async (response) => {
      if (response.url() === origin + "/api/v1/vendas" && response.status() >= 400)
        console.log("Disposable sale rejection", response.status(), (await response.json()).detail);
    });
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push("external-request");
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html#/negocio/clientes");
    await page.waitForFunction(
      () => window.SocialMEIV22?.identity && !document.getElementById("app").hidden,
    );
    await page.getByRole("button", { name: "Novo cliente", exact: true }).click();
    await page.locator("#f_n").fill("Cliente fictício " + name);
    await page.locator("dialog button[type=submit]").click();
    await page.locator("dialog[open]").waitFor({ state: "hidden" });
    await page
      .getByText("Cliente fictício " + name, { exact: true })
      .first()
      .waitFor();
    return { ctx, page, headers, identity };
  }
  try {
    const sorria = await account("SorriaOdonto", sorriaWidth),
      style = await account("She Style", styleWidth);
    const p = sorria.page;
    await p.evaluate(() => go("/agenda"));
    await p.getByText("Nenhum agendamento neste período.", { exact: true }).waitFor();
    await p.getByRole("button", { name: "Cadastrar serviço", exact: true }).click();
    await p.locator("#f_booking_service").fill("Consulta fictícia");
    await p.locator("#f_booking_duration").fill("45");
    await p.locator("#f_booking_price").fill("80");
    await p.locator("dialog button[type=submit]").click();
    await p.locator("dialog[open]").waitFor({ state: "hidden" });
    await p.getByRole("button", { name: "Cadastrar profissional/recurso", exact: true }).click();
    await p.locator("#f_booking_resource").fill("Profissional fictício");
    await p.locator("dialog button[type=submit]").click();
    await p.locator("dialog[open]").waitFor({ state: "hidden" });
    await p.getByRole("button", { name: "Novo agendamento", exact: true }).click();
    const date = new Date();
    date.setDate(date.getDate() + 2);
    const day = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    await p.locator("#f_booking_start").fill(day + "T14:00");
    await p.getByRole("button", { name: "Confirmar agendamento", exact: true }).click();
    await p.locator("dialog[open]").waitFor({ state: "hidden" });
    await p.reload();
    await p.locator("[data-appointments] article").waitFor();
    assert.match(
      await p.locator("[data-appointments] article").innerText(),
      /Cliente fictício SorriaOdonto/,
    );
    const bookings = await (
      await sorria.ctx.request.get(origin + "/api/v1/agenda/appointments")
    ).json();
    assert.equal(bookings.items.length, 1);
    assert.equal(bookings.items[0].duration_minutes, 45);
    assert.equal(new Date(bookings.items[0].scheduled_for).toISOString(), day + "T17:00:00.000Z");
    await p.getByRole("button", { name: "Novo agendamento", exact: true }).click();
    await p.locator("#f_booking_start").fill(day + "T14:15");
    await p.getByRole("button", { name: "Confirmar agendamento", exact: true }).click();
    await p
      .getByText("Horário indisponível para este recurso. Escolha outro horário.", { exact: true })
      .waitFor();
    assert.equal(
      (await (await sorria.ctx.request.get(origin + "/api/v1/agenda/appointments")).json()).items
        .length,
      1,
    );
    await p.keyboard.press("Escape");
    await p.getByRole("button", { name: "Reagendar", exact: true }).click();
    await p.locator("#f_booking_start").fill(day + "T15:00");
    await p.locator("dialog button[type=submit]").click();
    await p.locator("dialog[open]").waitFor({ state: "hidden" });
    await p.getByRole("button", { name: "Cancelar agendamento", exact: true }).click();
    await p.getByRole("button", { name: "Confirmar cancelamento", exact: true }).click();
    await p.locator("dialog[open]").waitFor({ state: "hidden" });
    const q = style.page;
    await p.getByRole("button", { name: "Configurar profissional/recurso", exact: true }).click();
    await p.locator("#f_booking_active").uncheck();
    await p.locator("dialog button[type=submit]").click();
    await p.locator("dialog[open]").waitFor({ state: "hidden" });
    const resources = await (
      await sorria.ctx.request.get(origin + "/api/v1/agenda/resources")
    ).json();
    assert.equal(resources.items[0].ativo, false);
    await q.evaluate(() => go("/negocio/produtos"));
    await q.getByRole("button", { name: "Novo produto", exact: true }).click();
    await q.locator("#f_n").fill("Blusa fictícia");
    await q.locator("#f_c").fill("Moda");
    await q.locator("#f_d").fill("Produto exclusivamente fictício");
    await q.locator("#f_p").fill("80,00");
    await q.locator("#f_e").fill("5");
    await q.locator("dialog button[type=submit]").click();
    await q.locator("dialog[open]").waitFor({ state: "hidden" });
    await q.locator("tr[data-a='prod:0']").waitFor();
    await q.evaluate(() => go("/negocio/vendas"));
    await q.getByRole("button", { name: "Nova venda", exact: true }).click();
    await q.locator("#f_c").selectOption({ label: "Cliente fictício She Style" });
    await q.locator("#f_q").fill("2");
    await q.locator("dialog button[type=submit]").click();
    await q.locator("dialog[open]").waitFor({ state: "hidden" });
    await q.reload();
    await q.waitForFunction(
      () => window.SocialMEIV22?.identity && !document.getElementById("app").hidden,
    );
    const products = await (await style.ctx.request.get(origin + "/api/v1/produtos")).json();
    const sales = await (await style.ctx.request.get(origin + "/api/v1/vendas")).json();
    assert.equal(products.length, 1);
    assert.equal(products[0].estoque, 3);
    assert.equal(products[0].categoria, "Moda");
    assert.equal(sales.length, 1);
    assert.equal(sales[0].quantidade, 2);
    assert.equal(sales[0].valor, 160);
    assert.ok(sales[0].cliente_id, "Explicit customer selection persists");
    await q.getByRole("button", { name: "Nova venda", exact: true }).click();
    await q.locator("#f_q").fill("1");
    await q.locator("dialog button[type=submit]").click();
    await q.locator("dialog[open]").waitFor({ state: "hidden" });
    await q.reload();
    await q.waitForFunction(() => window.SocialMEIV22?.ready);
    await q.evaluate(() => window.SocialMEIV22.ready);
    await q.getByRole("button", { name: "Nova venda", exact: true }).waitFor();
    const optionalSales = await (await style.ctx.request.get(origin + "/api/v1/vendas")).json();
    assert.equal(optionalSales.length, 2);
    assert.equal(optionalSales.find((sale) => sale.cliente_id === null).cliente, "Sem cliente");
    await q.getByRole("button", { name: "Nova venda", exact: true }).click();
    await q.locator("#f_q").fill("4");
    await q.locator("dialog button[type=submit]").click();
    await q
      .getByText("Estoque insuficiente ou estorno acima do limite. Nenhuma alteração foi salva.", {
        exact: true,
      })
      .waitFor();
    await q.keyboard.press("Escape");
    assert.equal(
      (await (await style.ctx.request.get(origin + "/api/v1/produtos")).json())[0].estoque,
      2,
    );
    assert.equal((await (await style.ctx.request.get(origin + "/api/v1/vendas")).json()).length, 2);
    assert.equal(
      (await sorria.ctx.request.get(origin + "/api/v1/produtos/" + products[0].id)).status(),
      404,
    );
    assert.equal(
      (
        await style.ctx.request.get(
          origin + "/api/v1/agenda/appointments/" + bookings.items[0].id + "/history",
        )
      ).status(),
      404,
    );
    const history = await (
      await sorria.ctx.request.get(
        origin + "/api/v1/agenda/appointments/" + bookings.items[0].id + "/history",
      )
    ).json();
    assert.equal(history.items.length, 3);
    assert.equal(history.items[2].status, "cancelled");
    assert.equal(
      (await (await sorria.ctx.request.get(origin + "/api/v1/vendas")).json()).length,
      0,
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    for (const page of [p, q])
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
        false,
      );
    console.log(
      "Real isolated E2E passed: two accounts/workspaces, Sorria client/service/booking/reload/reschedule/cancel/history; She Style product/customer/sale/stock/reload; cross-workspace404.",
    );
  } finally {
    for (const c of contexts) await c.close();
  }
}
module.exports = run;
if (require.main === module) {
  const { chromium } = require("playwright");
  (async () => {
    const browser = await chromium.launch();
    try {
      await run(browser, process.env.SOCIALMEI_TEST_PREVIEW_ORIGIN || "https://127.0.0.1:8645");
    } finally {
      await browser.close();
    }
  })().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
