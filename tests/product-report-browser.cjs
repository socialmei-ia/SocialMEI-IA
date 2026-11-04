const assert = require("node:assert/strict"),
  path = require("node:path");
const { chromium } = require("playwright");
async function run() {
  const browser = await chromium.launch();
  try {
    for (const width of [390, 1440])
      for (const dark of [false, true]) {
        const page = await browser.newPage({ viewport: { width, height: 950 } });
        await page.setContent(
          `<html style="--b:#888;--w:${dark ? "#202030" : "#fff"};--t:${dark ? "#fff" : "#111"}"><body style="margin:8px;background:var(--w);color:var(--t)"><div id="v"></div></body></html>`,
        );
        await page.evaluate(() => {
          location.hash = "#/relatorios";
          window.render = () => {};
          window.mode = "error";
          window.calls = [];
          window.SocialMEIAuth = {
            remote: true,
            current: { usuario: { id: 1 }, negocio: { id: 10 } },
          };
          window.SocialMEIV22 = {
            remote: true,
            request: async (route) => {
              calls.push(route);
              if (mode === "error") throw Error("Consulta temporariamente indisponível.");
              if (mode === "delay")
                await new Promise((resolve) => {
                  window.finish = resolve;
                });
              const query = new URLSearchParams(route.split("?")[1]);
              const second = query.has("after");
              return {
                workspace_id: mode === "foreign" ? 99 : 10,
                kind: query.get("kind"),
                period: { start: "2026-11-01", end: "2026-11-30", timezone: "America/Recife" },
                totals: { active_products: 3, low_stock: 2, no_sales: 1 },
                products:
                  mode === "empty"
                    ? []
                    : [
                        {
                          id: second ? 2 : 1,
                          name: second ? "Segundo produto" : "<img src=x onerror=alert(1)>",
                          category: "Teste",
                          price: "59.90",
                          stock: 0,
                          minimum: 2,
                        },
                      ],
                next_after: mode === "empty" || second ? null : 1,
                description: "Estoque atual, não histórico.",
                sales_description: "Sem vendas válidas no período.",
              };
            },
          };
        });
        await page.addScriptTag({
          path: path.join(__dirname, "../frontend/scripts/v22-product-reporting.js"),
        });
        const panel = page.locator("[data-product-report]"),
          refresh = panel.getByRole("button", { name: "Atualizar produtos", exact: true }),
          more = panel.getByRole("button", { name: "Carregar mais produtos", exact: true });
        await panel.getByText("Consulta temporariamente indisponível.", { exact: true }).waitFor();
        await page.evaluate(() => {
          mode = "valid";
        });
        await refresh.click();
        await panel.getByText("R$ 59,90", { exact: true }).waitFor();
        assert.equal(await panel.locator("img").count(), 0);
        await page.evaluate(() => {
          mode = "error";
        });
        await more.click();
        await panel.getByText("Consulta temporariamente indisponível.", { exact: true }).waitFor();
        assert.equal(await panel.locator("tbody tr").count(), 1);
        await page.evaluate(() => {
          mode = "valid";
        });
        await more.click();
        await panel.getByText("Segundo produto", { exact: true }).waitFor();
        assert.equal(await panel.locator("tbody tr").count(), 2);
        assert.equal(await more.isVisible(), false);
        assert.match(await page.evaluate(() => calls.at(-1)), /after=1/);
        await panel.getByLabel("Lista de produtos").selectOption("no_sales");
        await panel.getByText("R$ 59,90", { exact: true }).waitFor();
        assert.equal(await panel.locator("tbody tr").count(), 1);
        assert.match(await page.evaluate(() => calls.at(-1)), /kind=no_sales/);
        await panel.getByLabel("Produtos desde").fill("2026-11-01");
        await panel.getByLabel("Produtos até").fill("2026-11-30");
        await panel.getByRole("button", { name: "Consultar produtos", exact: true }).click();
        await panel.getByText("R$ 59,90", { exact: true }).waitFor();
        assert.match(await page.evaluate(() => calls.at(-1)), /start=2026-11-01&end=2026-11-30/);
        await page.evaluate(() => {
          mode = "empty";
        });
        await refresh.click();
        await panel.getByText("Nenhum produto nesta lista.", { exact: true }).waitFor();
        await page.evaluate(() => {
          mode = "foreign";
        });
        await refresh.click();
        await panel
          .getByText("Indicadores de produtos não confirmados pelo servidor.", { exact: true })
          .waitFor();
        await page.evaluate(() => {
          mode = "delay";
        });
        await refresh.click();
        await page.waitForFunction(() => !!window.finish);
        assert.equal(await panel.getByLabel("Produtos desde").isDisabled(), true);
        await page.evaluate(() => {
          SocialMEIAuth.current.negocio.id = 20;
          finish();
        });
        await page.waitForTimeout(40);
        assert.equal(await panel.locator("tbody tr").count(), 0);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        await page.close();
      }
  } finally {
    await browser.close();
  }
  console.log(
    "Product reports: catalogue stock, period filter, keyset pagination/retry, safe text, empty/error, foreign/stale workspace, desktop/mobile light/dark PASS (controlled API)",
  );
}
if (require.main === module)
  run().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
module.exports = run;
