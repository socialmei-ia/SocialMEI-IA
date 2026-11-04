// Focused UI test with controlled transport; backend persistence has PostgreSQL tests.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
async function run() {
  const browser = await chromium.launch();
  try {
    for (const width of [390, 1440])
      for (const theme of ["light", "dark"]) {
        const page = await browser.newPage({ viewport: { width, height: 900 } });
        await page.setContent(
          `<html style="--b:#999;--w:${theme === "dark" ? "#202030" : "#fff"};--t:${theme === "dark" ? "#fff" : "#111"}"><body style="margin:8px;background:var(--w);color:var(--t)"><div id="v"></div></body></html>`,
        );
        await page.evaluate(() => {
          location.hash = "#/negocio/clientes";
          window.calls = [];
          window.failExport = true;
          window.SocialMEIAuth = {
            remote: true,
            current: { usuario: { id: 1 }, negocio: { id: 10 }, papel: "owner" },
            request: async (...args) => {
              calls.push(args);
              if (failExport)
                throw new Error("Não foi possível conectar ao servidor. Tente novamente.");
              if (window.delayExport)
                await new Promise((resolve) => {
                  window.finishExport = resolve;
                });
              return {
                filename: "socialmei-clientes-todos.csv",
                row_count: 1,
                csv: '\ufeff"ID";"Nome"\r\n"1";"Cliente fictício"\r\n',
              };
            },
          };
        });
        await page.addScriptTag({
          path: path.join(__dirname, "../frontend/scripts/v22-business-export.js"),
        });
        const panel = page.locator("[data-business-export]");
        await panel.waitFor();
        await panel.getByRole("button", { name: "Exportar CSV", exact: true }).click();
        await panel.getByText(/Não foi possível conectar/).waitFor();
        await page.evaluate(() => {
          failExport = false;
        });
        const download = page.waitForEvent("download");
        await panel.getByRole("button", { name: "Exportar CSV", exact: true }).click();
        const file = await download;
        assert.equal(file.suggestedFilename(), "socialmei-clientes-todos.csv");
        assert.match(fs.readFileSync(await file.path(), "utf8"), /Cliente fictício/);
        await panel.getByText(/1 registro\(s\) exportado/).waitFor();
        await panel.getByLabel("Exportar desde").fill("2026-11-01");
        const count = await page.evaluate(() => calls.length);
        await panel.getByRole("button", { name: "Exportar CSV", exact: true }).click();
        await panel.getByText(/Informe início e fim/).waitFor();
        assert.equal(await page.evaluate(() => calls.length), count);
        await panel.getByLabel("Exportar até").fill("2026-11-04");
        await page.evaluate(() => {
          delayExport = true;
        });
        await panel.getByRole("button", { name: "Exportar CSV", exact: true }).click();
        await page.waitForFunction(() => !!window.finishExport);
        await page.evaluate(() => {
          SocialMEIAuth.current.negocio.id = 20;
          finishExport();
        });
        await page.waitForTimeout(60);
        assert.match(await panel.locator("[role=status]").innerText(), /Preparando/);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        fs.mkdirSync(path.join(__dirname, "../test-results/business-export"), { recursive: true });
        await page.screenshot({
          path: path.join(__dirname, `../test-results/business-export/${width}-${theme}.png`),
          fullPage: true,
        });
        await page.close();
      }
    console.log(
      "CSV UI: download, error/retry, validation, stale workspace guard, mobile/desktop and light/dark PASS (controlled transport)",
    );
  } finally {
    await browser.close();
  }
}
module.exports = run;
if (require.main === module)
  run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
