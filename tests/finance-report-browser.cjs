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
              return {
                workspace_id: mode === "foreign" ? 99 : 10,
                period: { start: "2026-11-01", end: "2026-11-30", timezone: "America/Recife" },
                paid: {
                  count: mode === "empty" ? 0 : 3,
                  incoming: "0.30",
                  outgoing: "0.40",
                  balance: "-0.10",
                },
                previous: { start: "2026-10-02", end: "2026-10-31", balance: "2.00" },
                balance_change: "-2.10",
                pending: { incoming: "3.00", outgoing: "4.00" },
                undated_paid_count: 1,
                daily: [
                  { date: "2026-11-01", incoming: "0.10", outgoing: "0.00", balance: "0.10" },
                ],
                description: "Não representa lucro nem saldo bancário.",
                pending_description: "Pendências por vencimento.",
              };
            },
          };
        });
        await page.addScriptTag({
          path: path.join(__dirname, "../frontend/scripts/v22-finance-reporting.js"),
        });
        const panel = page.locator("[data-finance-report]"),
          refresh = panel.getByRole("button", { name: "Atualizar financeiro", exact: true });
        await panel.getByText("Consulta temporariamente indisponível.", { exact: true }).waitFor();
        await page.evaluate(() => {
          mode = "valid";
        });
        await refresh.click();
        await panel
          .getByText("Saldo dos lançamentos pagos no período: R$ -0,10", { exact: true })
          .waitFor();
        await panel.getByText(/Atenção: 1 lançamento/).waitFor();
        assert.equal(await panel.locator("tbody tr").count(), 1);
        await panel.getByLabel("Financeiro desde").fill("2026-11-01");
        await panel.getByLabel("Financeiro até").fill("2026-11-30");
        await panel
          .getByRole("button", { name: "Consultar financeiro do período", exact: true })
          .click();
        await panel
          .getByText("Saldo dos lançamentos pagos no período: R$ -0,10", { exact: true })
          .waitFor();
        assert.match(await page.evaluate(() => calls.at(-1)), /start=2026-11-01&end=2026-11-30/);
        await page.evaluate(() => {
          mode = "empty";
        });
        await refresh.click();
        await panel
          .getByText("Nenhum pagamento registrado neste período.", { exact: true })
          .waitFor();
        await page.evaluate(() => {
          mode = "foreign";
        });
        await refresh.click();
        await panel
          .getByText("Indicadores financeiros não confirmados pelo servidor.", { exact: true })
          .waitFor();
        await page.evaluate(() => {
          mode = "delay";
        });
        await refresh.click();
        await page.waitForFunction(() => !!window.finish);
        assert.equal(await panel.getByLabel("Financeiro desde").isDisabled(), true);
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
    "Finance reports: signed totals, periods, warning, empty/error/retry, foreign/stale workspace, desktop/mobile light/dark PASS (controlled API)",
  );
}
if (require.main === module)
  run().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
module.exports = run;
