// Isolated aggregate UI; PostgreSQL tests validate actual sales and permissions.
const assert = require("node:assert/strict"),
  path = require("node:path"),
  fs = require("node:fs");
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
          const identity = { usuario: { id: 1 }, negocio: { id: 10 }, papel: "owner" };
          window.SocialMEIAuth = { remote: true, current: identity };
          window.SocialMEIV22 = {
            remote: true,
            identity,
            request: async (route) => {
              calls.push(route);
              if (mode === "error") throw Error("Consulta temporariamente indisponível.");
              if (mode === "delay")
                await new Promise((resolve) => {
                  window.finish = resolve;
                });
              return {
                workspace_id: mode === "foreign" ? 99 : 10,
                period: { start: "2026-11-01", end: "2026-11-30", timezone: "America/Recife" },
                new_customers: 1,
                buyers: 2,
                repeat_buyers: 1,
                returning_buyers: 1,
                identification_available: mode !== "viewer",
                customers:
                  mode === "viewer"
                    ? []
                    : [
                        {
                          id: 1,
                          name: "<img src=x onerror=alert(1)>",
                          purchases: 2,
                          total: "0.30",
                        },
                      ],
                description: "Vendas registradas, não recebimentos.",
                repeat_description: "Duas compras no período.",
                returning_description: "Uma compra anterior ao período.",
              };
            },
          };
        });
        await page.addScriptTag({
          path: path.join(__dirname, "../frontend/scripts/v22-customer-reporting.js"),
        });
        const panel = page.locator("[data-customer-report]");
        await panel.getByText("Consulta temporariamente indisponível.", { exact: true }).waitFor();
        await page.evaluate(() => {
          mode = "valid";
        });
        await panel.getByRole("button", { name: "Atualizar clientes", exact: true }).click();
        await panel.getByText("Clientes com compras no período: 2", { exact: true }).waitFor();
        await panel.getByText("R$ 0,30", { exact: true }).waitFor();
        assert.equal(await panel.locator("img").count(), 0);
        await panel.getByLabel("Clientes desde").fill("2026-11-01");
        await panel.getByLabel("Clientes até").fill("2026-11-30");
        await panel
          .getByRole("button", { name: "Consultar clientes do período", exact: true })
          .click();
        await panel.getByText("R$ 0,30", { exact: true }).waitFor();
        assert.match(await page.evaluate(() => calls.at(-1)), /start=2026-11-01&end=2026-11-30/);
        await page.evaluate(() => {
          mode = "viewer";
        });
        await panel.getByRole("button", { name: "Atualizar clientes", exact: true }).click();
        await panel
          .getByText("Seu acesso permite indicadores agregados, sem identificação de clientes.", {
            exact: true,
          })
          .waitFor();
        assert.equal(await panel.locator("tbody tr").count(), 0);
        await page.evaluate(() => {
          mode = "foreign";
        });
        await panel.getByRole("button", { name: "Atualizar clientes", exact: true }).click();
        await panel
          .getByText("Indicadores de clientes não confirmados pelo servidor.", { exact: true })
          .waitFor();
        await page.evaluate(() => {
          mode = "delay";
        });
        await panel.getByRole("button", { name: "Atualizar clientes", exact: true }).click();
        await page.waitForFunction(() => !!window.finish);
        assert.equal(await panel.getByLabel("Clientes desde").isDisabled(), true);
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
        fs.mkdirSync(path.join(__dirname, "../test-results/customer-report"), { recursive: true });
        await page.screenshot({
          path: path.join(
            __dirname,
            `../test-results/customer-report/${width}-${dark ? "dark" : "light"}.png`,
          ),
          fullPage: true,
        });
        await page.close();
      }
  } finally {
    await browser.close();
  }
  console.log(
    "Customer reports: periods, purchase counts, privacy, decimal rendering, error/retry, stale/foreign workspace, desktop/mobile light/dark PASS (controlled API)",
  );
}
if (require.main === module)
  run().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
module.exports = run;
