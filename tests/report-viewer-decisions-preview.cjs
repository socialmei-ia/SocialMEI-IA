// Official account APIs + real disposable PostgreSQL; never accepts a public origin.
const assert = require("node:assert/strict"),
  { randomUUID } = require("node:crypto"),
  { chromium } = require("playwright");
async function run() {
  const origin = process.env.SOCIALMEI_TEST_PREVIEW_ORIGIN || "https://127.0.0.1:8443";
  assert.match(origin, /^https:\/\/127\.0\.0\.1:[1-9][0-9]{3,4}$/);
  const browser = await chromium.launch(),
    contexts = [];
  async function account(label) {
    const ctx = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 390, height: 1000 },
    });
    contexts.push(ctx);
    assert.equal(
      (await (await ctx.request.get(origin + "/__preview")).json()).environment,
      "local-disposable-preview",
    );
    const response = await ctx.request.post(origin + "/api/v1/auth/register", {
      headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
      data: {
        nome: label,
        email: `read-${randomUUID()}@example.test`,
        senha: "Disposable-Read-123!",
      },
    });
    assert.equal(response.status(), 201);
    return { ctx, identity: await response.json() };
  }
  async function request(account, route, method = "GET", data) {
    const identity = account.identity;
    const response = await account.ctx.request.fetch(origin + "/api/v1" + route, {
      method,
      headers: {
        Origin: origin,
        "X-SocialMEI-Client": "browser",
        "X-SocialMEI-CSRF": identity.csrf_token,
        "X-SocialMEI-Identity": `${identity.usuario.id}:${identity.negocio.id}`,
      },
      data,
    });
    assert.ok(response.ok(), `Disposable ${method} ${route}: ${response.status()}`);
    return response.status() === 204 ? null : response.json();
  }
  try {
    const owner = await account("Responsável fictício"),
      reader = await account("Leitor fictício");
    const day = (await request(owner, "/reporting/customers")).period.end;
    const customer = await request(owner, "/clientes", "POST", {
      nome: "Cliente Restrito Fictício",
    });
    const product = await request(owner, "/produtos", "POST", {
      nome: "Produto público do negócio fictício",
      preco: "59.90",
      estoque: 3,
      minimo: 2,
    });
    await request(owner, "/vendas", "POST", {
      operation_id: randomUUID(),
      cliente_id: customer.id,
      produto_id: product.id,
      quantidade: 1,
      preco: "59.90",
      data: day,
    });
    await request(owner, "/financeiro", "POST", {
      operation_id: randomUUID(),
      descricao: "Recebimento fictício privado",
      tipo: "receita",
      valor: "59.90",
      vencimento: day,
      status: "pago",
    });
    await request(owner, "/team/members", "POST", {
      email: reader.identity.usuario.email,
      role: "report_viewer",
    });
    reader.identity = await request(reader, "/auth/workspaces/switch", "POST", {
      workspace_id: owner.identity.negocio.id,
    });
    assert.equal(reader.identity.papel, "report_viewer");
    assert.equal((await reader.ctx.request.get(origin + "/api/v1/clientes")).status(), 403);
    assert.equal((await reader.ctx.request.get(origin + "/api/v1/financeiro")).status(), 403);
    const raw = await request(reader, "/reporting/customers");
    assert.deepEqual(raw.customers, []);
    assert.equal(raw.identification_available, false);
    const page = await reader.ctx.newPage(),
      errors = [],
      external = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push("blocked");
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html#/relatorios");
    await page.waitForURL(/\/relatorios-leitura\.html/);
    await page
      .locator("[data-customer-report]")
      .getByText("Clientes com compras no período: 1", { exact: true })
      .waitFor();
    await page
      .locator("[data-finance-report]")
      .getByText("Entradas registradas como pagas: R$ 59,90", { exact: true })
      .waitFor();
    await page
      .locator("[data-product-report]")
      .getByText("Produto público do negócio fictício", { exact: true })
      .waitFor();
    assert.equal(await page.getByText("Cliente Restrito Fictício", { exact: true }).count(), 0);
    assert.equal(await page.getByText("Recebimento fictício privado", { exact: true }).count(), 0);
    const denied = await reader.ctx.request.post(origin + "/api/v1/clientes", {
      headers: {
        Origin: origin,
        "X-SocialMEI-Client": "browser",
        "X-SocialMEI-CSRF": reader.identity.csrf_token,
        "X-SocialMEI-Identity": `${reader.identity.usuario.id}:${reader.identity.negocio.id}`,
      },
      data: { nome: "Não deve ser criado" },
    });
    assert.equal(denied.status(), 403);
    await page.reload();
    await page
      .locator("[data-finance-report]")
      .getByText("Entradas registradas como pagas: R$ 59,90", { exact: true })
      .waitFor();
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    await request(reader, "/auth/logout", "POST", {});
    assert.equal(
      (await reader.ctx.request.get(origin + "/api/v1/reporting/finance")).status(),
      401,
    );
    console.log(
      "Real PostgreSQL/report-only browser: official grant and switch, persisted sale/receipt, permitted aggregates, no customer/private entry text, raw CRM and writes403, reload and logout401 PASS",
    );
  } finally {
    for (const ctx of contexts) await ctx.close();
    await browser.close();
  }
}
if (require.main === module)
  run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
module.exports = run;
