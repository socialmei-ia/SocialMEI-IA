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
          location.hash = "#/config/conta";
          window.render = () => {};
          window.mode = "error";
          window.calls = [];
          window.SocialMEIAuth = {
            remote: true,
            current: { usuario: { id: 1 }, negocio: { id: 10 }, papel: "owner" },
          };
          window.SocialMEIV22 = {
            remote: true,
            request: async (route) => {
              calls.push(route);
              if (mode === "error") throw Error("Consulta indisponível.");
              if (mode === "delay")
                await new Promise((resolve) => {
                  window.finish = resolve;
                });
              const query = new URLSearchParams(route.split("?")[1]),
                second = query.has("before");
              return {
                workspace_id: mode === "foreign" ? 99 : 10,
                kind: query.get("kind"),
                period: { start: "2026-11-01", end: "2026-11-30", timezone: "America/Recife" },
                items:
                  mode === "empty"
                    ? []
                    : [
                        {
                          id: second ? 1 : 2,
                          at: "2026-11-04T03:30:00Z",
                          kind: "exports",
                          action: "CSV de produtos gerado",
                          actor: second ? null : "<img src=x onerror=alert(1)>",
                          target: null,
                        },
                      ],
                next_before: mode === "empty" || second ? null : 2,
                description: "Somente acessos da equipe e geração de CSV. Não comprova download.",
              };
            },
          };
        });
        await page.addScriptTag({
          path: path.join(__dirname, "../frontend/scripts/v22-workspace-audit.js"),
        });
        const panel = page.locator("[data-workspace-audit]"),
          filter = panel.getByRole("button", { name: "Consultar histórico", exact: true }),
          more = panel.getByRole("button", { name: "Carregar eventos anteriores", exact: true });
        await panel.getByText("Consulta indisponível.", { exact: true }).waitFor();
        await page.evaluate(() => {
          mode = "valid";
        });
        await panel.getByLabel("Histórico desde").fill("2026-11-01");
        await panel.getByLabel("Histórico até").fill("2026-11-30");
        await filter.click();
        await panel.getByText("CSV de produtos gerado", { exact: true }).waitFor();
        assert.equal(await panel.locator("img").count(), 0);
        assert.match(await panel.locator("tbody").innerText(), /00:30/);
        await more.click();
        await panel.getByText("Não registrado", { exact: true }).waitFor();
        assert.equal(await panel.locator("tbody tr").count(), 2);
        assert.equal(await more.isVisible(), false);
        assert.match(await page.evaluate(() => calls.at(-1)), /before=2/);
        await page.evaluate(() => {
          mode = "empty";
        });
        await panel.getByLabel("Tipo de histórico").selectOption("team");
        await panel.getByText("Nenhum evento disponível neste período.", { exact: true }).waitFor();
        await page.evaluate(() => {
          mode = "foreign";
        });
        await filter.click();
        await panel.getByText("Histórico não confirmado pelo servidor.", { exact: true }).waitFor();
        await page.evaluate(() => {
          mode = "delay";
        });
        await filter.click();
        await page.waitForFunction(() => !!window.finish);
        assert.equal(await panel.getByLabel("Histórico desde").isDisabled(), true);
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
    "Workspace audit: periods, pagination, current names, timezone, safe text, errors, stale/foreign workspace, desktop/mobile light/dark PASS (controlled API)",
  );
}
if (require.main === module)
  run().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
module.exports = run;
