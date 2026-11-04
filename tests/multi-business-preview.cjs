// Real account API and PostgreSQL behind the disposable loopback HTTPS preview.
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
async function run() {
  const origin = process.env.SOCIALMEI_TEST_PREVIEW_ORIGIN || "https://127.0.0.1:8443";
  assert.match(origin, /^https:\/\/127\.0\.0\.1:[1-9][0-9]{3,4}$/);
  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const errors = [];
  const external = [];
  const email = `multi-${randomUUID()}@example.test`;
  const password = "Disposable-only-Multi-123!";
  try {
    assert.equal(
      (await (await context.request.get(origin + "/__preview")).json()).environment,
      "local-disposable-preview",
    );
    const registration = await context.request.post(origin + "/api/v1/auth/register", {
      headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
      data: { nome: "Responsável fictício", email, senha: password },
    });
    assert.equal(registration.status(), 201);
    const original = await registration.json();
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await context.route("**/*", (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push("external-request");
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html#/config/conta");
    const panel = page.locator("[data-businesses]");
    await panel.waitFor();
    for (const [name, segment] of [
      ["SorriaOdonto", "Serviços odontológicos"],
      ["She Style", "Moda feminina"],
    ]) {
      await panel.getByRole("button", { name: "Adicionar negócio", exact: true }).click();
      await panel.getByLabel("Nome do negócio", { exact: true }).fill(name);
      await panel.getByLabel("Segmento do negócio", { exact: true }).fill(segment);
      await panel.getByRole("button", { name: "Criar negócio", exact: true }).click();
      await panel.getByRole("button", { name: "Acessar " + name, exact: true }).waitFor();
    }
    const request = (route, method = "GET", data) =>
      page.evaluate(([r, m, d]) => SocialMEIAuth.request(r, m, d), [route, method, data]);
    const listed = await request("/auth/workspaces");
    assert.equal(listed.items.length, 3);
    assert.ok(listed.items.every((item) => item.role === "owner"));
    const sorria = listed.items.find((item) => item.nome === "SorriaOdonto").id;
    const she = listed.items.find((item) => item.nome === "She Style").id;
    assert.notEqual(sorria, she);
    async function switchTo(name, id) {
      await page.goto(origin + "/frontend/socialmei-app.html#/config/conta");
      await page
        .locator("[data-businesses]")
        .getByRole("button", { name: "Acessar " + name, exact: true })
        .click();
      await page.waitForFunction((id) => SocialMEIAuth.current?.negocio.id === id, id);
      assert.equal(
        await page.evaluate(() => SocialMEIAuth.current.usuario.id),
        original.usuario.id,
      );
      await page.locator("[data-business-menu]").waitFor();
    }
    await switchTo("SorriaOdonto", sorria);
    const customer = await request("/clientes", "POST", { nome: "Cliente Teste Sorria 01" });
    const service = await request("/produtos", "POST", {
      nome: "Avaliação odontológica",
      tipo: "Serviço",
      preco: 80,
      duracao_minutos: 30,
    });
    const resource = await request("/agenda/resources", "POST", {
      nome: "Consultório Teste 01",
      operation_id: randomUUID(),
    });
    const booking = await request("/agenda/appointments", "POST", {
      operation_id: randomUUID(),
      cliente_id: customer.id,
      servico_id: service.id,
      resource_id: resource.id,
      scheduled_for: new Date(Date.now() + 86400000 * 3).toISOString(),
    });
    await request("/auth/profile", "PATCH", { configuracao_negocio: { horario: "Sorria demo" } });
    await page.reload();
    await page.locator("[data-businesses]").waitFor();
    assert.equal(
      (await request("/clientes")).some((item) => item.id === customer.id),
      true,
    );
    assert.equal(
      (await request("/agenda/appointments")).items.some((item) => item.id === booking.id),
      true,
    );
    await switchTo("She Style", she);
    assert.equal(
      (await request("/clientes")).some((item) => item.id === customer.id),
      false,
    );
    const product = await request("/produtos", "POST", {
      nome: "Blusa Teste She Style",
      tipo: "Produto",
      preco: "59.90",
      estoque: 5,
    });
    assert.notEqual((await request("/auth/me")).negocio.configuracao.horario, "Sorria demo");
    for (const route of ["/agenda/appointments", "/message-enrichment/conversations", "/vendas"]) {
      const value = await request(route);
      assert.equal((Array.isArray(value) ? value : value.items).length, 0);
    }
    const sale = await request("/vendas", "POST", {
      operation_id: randomUUID(),
      produto_id: product.id,
      quantidade: 1,
      preco: "59.90",
      data: new Date().toISOString().slice(0, 10),
    });
    assert.equal(sale.valor, 59.9);
    await page.reload();
    await panel.waitFor();
    assert.equal((await request("/produtos")).find((item) => item.id === product.id).estoque, 4);
    assert.equal((await request("/vendas")).length, 1);
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.locator("[data-business-menu]").waitFor({ state: "visible" });
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
        false,
      );
      fs.mkdirSync(path.join(__dirname, "../test-results/multi-business"), { recursive: true });
      await page.screenshot({
        path: path.join(__dirname, `../test-results/multi-business/businesses-${width}.png`),
        fullPage: true,
      });
    }
    const second = await context.newPage();
    await second.goto(origin + "/frontend/socialmei-app.html#/config/conta");
    await second.locator("[data-businesses]").waitFor();
    await switchTo("SorriaOdonto", sorria);
    await second.waitForFunction((id) => SocialMEIAuth.current?.negocio.id === id, sorria);
    assert.equal(
      (await request("/produtos")).some((item) => item.id === product.id),
      false,
    );
    assert.equal((await request("/vendas")).length, 0);
    assert.equal(
      (await request("/agenda/appointments")).items.some((item) => item.id === booking.id),
      true,
    );
    const cross = await page.evaluate(async (id) => {
      try {
        await SocialMEIAuth.request("/produtos/" + id);
        return 200;
      } catch (error) {
        return error.status;
      }
    }, product.id);
    assert.equal(cross, 404);
    assert.equal(
      await page.evaluate(async () => {
        try {
          await SocialMEIAuth.request("/auth/workspaces/switch", "POST", {
            workspace_id: 2147483647,
          });
          return 200;
        } catch (error) {
          return error.status;
        }
      }),
      403,
    );
    await page.evaluate(() => SocialMEIAuth.logout());
    await page.waitForURL(/entrada\.html/);
    assert.equal(await (await context.request.get(origin + "/api/v1/auth/session")).json(), null);
    const login = await context.request.post(origin + "/api/v1/auth/login", {
      headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
      data: { email, senha: password },
    });
    assert.equal(login.status(), 200);
    assert.equal((await login.json()).usuario.id, original.usuario.id);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "Multi-business real PostgreSQL/browser: one registration, two owner workspaces, selector, reload, isolated CRM/catalog/settings/empty agenda/sales/inbox, cross-workspace404, cross-tab switch, logout/login, desktop/mobile PASS.",
    );
  } finally {
    await browser.close();
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
