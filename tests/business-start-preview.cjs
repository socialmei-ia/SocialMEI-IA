// Real setup wizard and PostgreSQL, restricted to the disposable loopback preview.
const assert = require("node:assert/strict"),
  { randomUUID } = require("node:crypto"),
  { chromium } = require("playwright");
const fs = require("node:fs"),
  path = require("node:path");
const { waitForViewportFit } = require("./v22-layout-ready.cjs");
async function run() {
  const origin = process.env.SOCIALMEI_TEST_PREVIEW_ORIGIN || "https://127.0.0.1:8443";
  assert.match(origin, /^https:\/\/127\.0\.0\.1:[1-9][0-9]{3,4}$/);
  const browser = await chromium.launch(),
    context = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 390, height: 1000 },
      reducedMotion: "reduce",
    });
  const errors = [],
    external = [];
  try {
    assert.equal(
      (await (await context.request.get(origin + "/__preview")).json()).environment,
      "local-disposable-preview",
    );
    const registration = await context.request.post(origin + "/api/v1/auth/register", {
      headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
      data: {
        nome: "Responsável fictício do guia",
        email: `start-${randomUUID()}@example.test`,
        senha: "Disposable-Guide-123!",
      },
    });
    assert.equal(registration.status(), 201);
    const original = await registration.json(),
      page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await context.route("**/*", (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push("blocked");
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html#/config/conta");
    await page.locator("[data-businesses]").waitFor();
    const request = (route, method = "GET", data) =>
      page.evaluate(([r, m, d]) => SocialMEIAuth.request(r, m, d), [route, method, data]);
    const ids = {};
    for (const name of ["SorriaOdonto", "She Style"])
      ids[name] = (
        await request("/auth/workspaces", "POST", {
          nome: name,
          segmento: "Demonstração fictícia",
          idempotency_key: randomUUID(),
        })
      ).negocio.id;
    await page.reload();
    await page.locator("[data-businesses]").waitFor();
    async function select(name) {
      await page.goto(origin + "/frontend/socialmei-app.html#/config/conta");
      await page
        .locator("[data-businesses]")
        .getByRole("button", { name: "Acessar " + name, exact: true })
        .click();
      await page.waitForFunction(
        (id) => window.SocialMEIAuth?.current?.negocio.id === id,
        ids[name],
      );
      await page.goto(origin + "/frontend/socialmei-app.html#/inicio");
      await page
        .locator("[data-business-start]")
        .getByText("Perfil do negócio salvo — Pendente", { exact: true })
        .waitFor();
      assert.equal((await request("/auth/me")).usuario.id, original.usuario.id);
    }
    async function configure(name, area, type, routine) {
      await page
        .locator("[data-business-start]")
        .getByRole("link", { name: "Configurar negócio", exact: true })
        .click();
      await page.waitForURL("**/entrada.html?setup=1#/comecar");
      await page.locator("#oNeg").waitFor();
      assert.equal(await page.locator("#oNeg").inputValue(), name);
      assert.equal(await page.locator("#oNome").inputValue(), "Responsável fictício do guia");
      await page.locator(`[data-area="${area}"]`).click();
      await page.locator(`[data-tipo="${type}"]`).click();
      await page.locator("[data-ob=prox]").click();
      await page.locator("[data-of]").first().click();
      await page.locator("[data-ob=prox]").click();
      await page.locator(`[data-ro="${routine}"]`).click();
      await page.locator("[data-ob=prox]").click();
      await page.locator("[data-ob=prox]").click();
      await page.getByText(/a configuração deste negócio será salva na sua conta/).waitFor();
      assert.equal(await page.getByText(/salvamos este perfil só neste navegador/).count(), 0);
      await page.locator("[data-ob=fim]").click();
      await page.waitForURL("**/socialmei-app.html#/bemvindo");
      await page
        .locator("[data-business-start]")
        .getByText("Perfil do negócio salvo — Registrado", { exact: true })
        .waitFor();
    }
    await select("SorriaOdonto");
    await configure("SorriaOdonto", "saude", "servicos", "Agendar atendimentos");
    let state = await request("/onboarding/status");
    assert.deepEqual(state.offers, ["services"]);
    assert.equal(state.counts.services, 0, "Profile offers must not fabricate catalogue services");
    const customer = await request("/clientes", "POST", { nome: "Cliente Teste Sorria 01" });
    const service = await request("/produtos", "POST", {
      nome: "Avaliação odontológica",
      tipo: "Serviço",
      preco: 80,
      duracao_minutos: 30,
    });
    const resource = await request("/agenda/resources", "POST", {
      operation_id: randomUUID(),
      nome: "Consultório Teste 01",
    });
    await request("/agenda/appointments", "POST", {
      operation_id: randomUUID(),
      cliente_id: customer.id,
      servico_id: service.id,
      resource_id: resource.id,
      scheduled_for: new Date(Date.now() + 3 * 86400000).toISOString(),
    });
    await page.reload();
    await page
      .locator("[data-business-start]")
      .getByText("5 de 5 passos essenciais registrados neste negócio.", { exact: true })
      .waitFor();
    await waitForViewportFit(page);
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
      false,
    );
    fs.mkdirSync(path.join(__dirname, "../test-results/business-start"), { recursive: true });
    await page.screenshot({
      path: path.join(__dirname, "../test-results/business-start/sorria-390.png"),
      fullPage: true,
    });
    await select("She Style");
    state = await request("/onboarding/status");
    assert.ok(Object.values(state.counts).every((value) => value === 0));
    await configure("She Style", "moda", "produtos", "Controlar estoque");
    const product = await request("/produtos", "POST", {
      nome: "Blusa Teste She Style",
      preco: "59.90",
      estoque: 5,
      categoria: "Roupas femininas",
    });
    await request("/vendas", "POST", {
      operation_id: randomUUID(),
      produto_id: product.id,
      quantidade: 1,
      preco: "59.90",
      data: new Date().toISOString().slice(0, 10),
    });
    state = await request("/onboarding/status");
    assert.deepEqual(state.offers, ["products"]);
    assert.equal(state.counts.products, 1);
    assert.equal(state.counts.valid_sales, 1);
    await page.reload();
    const guide = page.locator("[data-business-start]");
    await guide
      .getByText("3 de 3 passos essenciais registrados neste negócio.", { exact: true })
      .waitFor();
    assert.equal(await guide.getByRole("link", { name: "Abrir agenda", exact: true }).count(), 0);
    assert.equal((await request("/produtos/" + product.id)).estoque, 4);
    assert.deepEqual(await request("/clientes"), []);
    assert.deepEqual((await request("/agenda/appointments")).items, []);
    assert.equal((await request("/workspace-profile")).profile.offers[0], "products");
    await waitForViewportFit(page);
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
      false,
    );
    await page.screenshot({
      path: path.join(__dirname, "../test-results/business-start/she-390.png"),
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "Real setup guide: one account/two businesses, existing five-step wizard saved in PG, profile offers do not fabricate records, service/resource/booking and product/sale/stock persist after reload, correct per-business guidance and mobile layout PASS",
    );
  } finally {
    await context.close();
    await browser.close();
  }
}
if (require.main === module)
  run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
module.exports = run;
