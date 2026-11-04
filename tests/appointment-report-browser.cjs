// Aggregate UI contract with controlled transport; PostgreSQL tests cover actual bookings.
const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require("playwright");
async function run() {
  const browser = await chromium.launch();
  try {
    for (const width of [390, 1440])
      for (const dark of [false, true]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 } });
        await page.setContent(
          `<html style="--b:#888;--w:${dark ? "#202030" : "#fff"};--t:${dark ? "#fff" : "#111"};--m:#888;--pl:#acc"><body style="margin:8px;background:var(--w);color:var(--t)"><div id="v"></div></body></html>`,
        );
        await page.evaluate(() => {
          location.hash = "#/relatorios";
          window.render = () => {};
          window.mode = "error";
          window.seen = [];
          const identity = {
            usuario: { id: 1 },
            negocio: { id: 10, nome: "Negócio fictício" },
            papel: "owner",
          };
          window.SocialMEIAuth = { remote: true, current: identity };
          window.SocialMEIV22 = {
            remote: true,
            identity,
            request: async (route) => {
              seen.push(route);
              if (route.startsWith("/reporting/appointments")) {
                if (mode === "error") throw new Error("Agenda temporariamente indisponível.");
                if (mode === "delay")
                  await new Promise((resolve) => {
                    window.finish = resolve;
                  });
                return {
                  period: { start: "2026-11-01", end: "2026-11-30", timezone: "America/Recife" },
                  scheduled: { total: 3, pending: 1, done: 1, cancelled: 1 },
                  upcoming_pending: 1,
                  reschedule_events: 2,
                  services: [
                    { name: "<img src=x onerror=alert(1)>", pending: 1, done: 1, cancelled: 1 },
                  ],
                  description: "Estados registrados, sem presumir comparecimento.",
                  upcoming_description: "Pendentes futuros no período.",
                  reschedule_description: "Eventos pelo registro da alteração.",
                };
              }
              return {
                totals: { clientes: 0, itens_ativos: 0, estoque_baixo: 0 },
                sales_by_status: {},
                finance_by_type_and_status: [],
                attendance: [],
                period_days: 30,
                as_of: "2026-11-04",
                period: {
                  start: "2026-11-01",
                  end: "2026-11-30",
                  days: 30,
                  previous_start: "2026-10-02",
                  previous_end: "2026-10-31",
                },
                current: { count: 0, total: "0.00", average_ticket: "0.00" },
                previous: { count: 0, total: "0.00", average_ticket: "0.00" },
                change_total_percent: null,
                daily: [],
                products: [],
              };
            },
          };
        });
        await page.addScriptTag({
          path: path.join(__dirname, "../frontend/scripts/v22-knowledge-reporting.js"),
        });
        const panel = page.locator("[data-appointment-report]");
        await panel.getByText("Agenda temporariamente indisponível.", { exact: true }).waitFor();
        await panel.getByLabel("Agenda desde").fill("2026-11-01");
        await panel.getByLabel("Agenda até").fill("2026-11-30");
        await page.evaluate(() => {
          mode = "valid";
        });
        await panel
          .getByRole("button", { name: "Consultar agenda do período", exact: true })
          .click();
        await panel.getByText("Concluídos: 1", { exact: true }).waitFor();
        await panel.getByText("Cancelados: 1", { exact: true }).waitFor();
        await panel
          .getByText("Alterações de horário registradas no período: 2", { exact: true })
          .waitFor();
        assert.equal(await panel.locator("img").count(), 0);
        assert.match(await panel.innerText(), /America\/Recife/);
        await page.evaluate(() => {
          mode = "delay";
        });
        await panel
          .getByRole("button", { name: "Consultar agenda do período", exact: true })
          .click();
        await page.waitForFunction(() => !!window.finish);
        await page.evaluate(() => {
          SocialMEIV22.identity.negocio.id = 20;
          finish();
        });
        await page.waitForTimeout(50);
        assert.equal(await panel.locator("tbody tr").count(), 0);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        await page.close();
      }
    console.log(
      "Agenda report UI: statuses, reschedules, custom dates, errors/retry, escaping and stale workspace; desktop/mobile light/dark PASS (controlled API)",
    );
  } finally {
    await browser.close();
  }
}
if (require.main === module)
  run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
module.exports = run;
