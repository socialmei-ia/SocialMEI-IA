// Financial regression restricted to the disposable loopback HTTPS/PostgreSQL preview.
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const { chromium } = require("playwright");
async function run() {
  const origin = process.env.SOCIALMEI_TEST_PREVIEW_ORIGIN || "https://127.0.0.1:8443";
  assert.match(origin, /^https:\/\/127\.0\.0\.1:[1-9][0-9]{3,4}$/);
  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  try {
    assert.equal(
      (await (await context.request.get(origin + "/__preview")).json()).environment,
      "local-disposable-preview",
    );
    const response = await context.request.post(origin + "/api/v1/auth/register", {
      headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
      data: {
        nome: "Teste seleção por registro",
        email: `sale-record-${randomUUID()}@example.test`,
        senha: "Disposable-Sale-123!",
      },
    });
    assert.equal(response.status(), 201);
    const page = await context.newPage(),
      errors = [],
      external = [];
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
    const customers = [];
    for (let i = 0; i < 2; i++)
      customers.push(await request("/clientes", "POST", { nome: "Cliente Teste Homônimo" }));
    const products = [];
    for (const price of [80, 90])
      products.push(
        await request("/produtos", "POST", {
          nome: "Blusa Teste Homônima",
          preco: price,
          estoque: 5,
        }),
      );
    await page.reload();
    await page.waitForFunction(() => !!window.SocialMEIV22?.ready);
    await page.evaluate(() => SocialMEIV22.ready);
    await page.goto(origin + "/frontend/socialmei-app.html#/negocio/vendas");
    await page.getByRole("button", { name: "Nova venda", exact: true }).click();
    await page.locator("#f_c").selectOption(String(customers[1].id));
    await page.locator("#f_p").selectOption(String(products[1].id));
    await page.locator("dialog button[type=submit]").click();
    await page.locator("dialog[open]").waitFor({ state: "hidden" });
    await page.reload();
    await page.waitForFunction(() => !!window.SocialMEIV22?.identity);
    const sales = await request("/vendas");
    assert.equal(sales.length, 1);
    assert.equal(sales[0].cliente_id, customers[1].id);
    assert.equal(sales[0].produto_id, products[1].id);
    assert.equal(Number(sales[0].valor), 90);
    const stock = await request("/produtos");
    assert.equal(stock.find((p) => p.id === products[1].id).estoque, 4);
    assert.equal(stock.find((p) => p.id === products[0].id).estoque, 5);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "Real PostgreSQL sale: duplicate names, selected customer/product IDs, price90, only chosen stock5→4, reload persistence PASS",
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
