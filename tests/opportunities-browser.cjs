const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");

async function run() {
  const root = path.resolve(__dirname, "..");
  const directory = path.join(root, "test-results/opportunities");
  fs.mkdirSync(directory, { recursive: true });
  const server = http.createServer((request, response) => {
    if (request.url !== "/opportunities.html") {
      response.writeHead(404).end();
      return;
    }
    response.setHeader("Content-Type", "text/html; charset=utf-8");
    fs.createReadStream(path.join(root, "prototypes/opportunities.html")).pipe(response);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  let states = 0;
  const errors = [];
  try {
    for (const width of [1440, 1366, 1024, 768, 390, 360]) {
      for (const theme of ["light", "dark"]) {
        for (const reducedMotion of ["reduce", "no-preference"]) {
          const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion });
          page.on("pageerror", (error) => errors.push(error.message));
          const requests = [];
          page.on("request", (request) => requests.push(request.url()));
          await page.route("**/*", (route) =>
            new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
          );
          await page.goto(origin + "/opportunities.html");
          if (theme === "dark")
            await page.getByRole("button", { name: "Usar tema escuro" }).click();
          await page.waitForFunction(
            () => document.querySelectorAll("[data-opportunity]").length === 6,
          );
          assert.equal(await page.locator("html").getAttribute("data-theme"), theme);
          assert.equal(await page.locator("#resultCount").textContent(), "6 pessoas");
          assert(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
            `${width}: page overflow`,
          );
          await page.getByRole("button", { name: "Quentes", exact: true }).click();
          assert.equal(await page.locator("[data-opportunity]").count(), 2);
          await page.getByRole("button", { name: "Mornas", exact: true }).click();
          assert.equal(await page.locator("[data-opportunity]").count(), 2);
          await page.getByRole("button", { name: "Frias", exact: true }).click();
          assert.equal(await page.locator("[data-opportunity]").count(), 2);
          await page.getByRole("button", { name: "Todas", exact: true }).click();
          await page.getByRole("searchbox").fill("hidratacao");
          assert.equal(await page.locator("[data-opportunity]").count(), 1);
          assert.match(await page.locator("[data-opportunity]").textContent(), /Juliana/);
          await page.getByRole("searchbox").fill("not-an-existing-person");
          assert.equal(await page.locator("[data-opportunity]").count(), 0);
          await page.getByRole("button", { name: "Limpar filtros" }).click();
          assert.equal(await page.locator("[data-opportunity]").count(), 6);
          await page.getByRole("button", { name: "Quadro", exact: true }).click();
          await page.getByRole("button", { name: "Ver detalhes de Ana Paula" }).click();
          await page.getByRole("dialog", { name: "Ana Paula" }).waitFor();
          assert.match(await page.locator(".evaluation").textContent(), /82%/);
          assert(
            await page
              .locator("#detailDialog")
              .evaluate((element) => element.scrollWidth <= element.clientWidth),
          );
          await page.locator("#stageSelect").selectOption("Proposta enviada");
          assert.match(await page.locator(".evaluation").textContent(), /82%/);
          // O diálogo nativo mantém o teclado no contexto aberto.
          for (let i = 0; i < 5; i++) {
            await page.keyboard.press("Tab");
            assert(
              await page.evaluate(
                () =>
                  document.querySelector("#detailDialog").contains(document.activeElement) ||
                  document.activeElement === document.body,
              ),
            );
          }
          if ([1440, 390].includes(width) && reducedMotion === "reduce")
            await page.screenshot({ path: path.join(directory, `${width}-${theme}-detail.png`) });
          await page.keyboard.press("Escape");
          assert.equal(
            await page.locator("#detailDialog").evaluate((element) => element.open),
            false,
          );
          await page.waitForFunction(() => document.activeElement.dataset.opportunity === "ana");
          assert.equal(
            await page.evaluate(() => document.activeElement.dataset.opportunity),
            "ana",
          );
          assert(
            await page
              .getByRole("region", { name: "Proposta enviada", exact: true })
              .getByRole("button", { name: "Ver detalhes de Ana Paula" })
              .count(),
          );
          await page.getByRole("button", { name: /Reiniciar demonstração/ }).click();
          assert(
            await page
              .getByRole("region", { name: "Em conversa", exact: true })
              .getByRole("button", { name: "Ver detalhes de Ana Paula" })
              .count(),
          );
          await page.getByRole("button", { name: "Lista", exact: true }).click();
          await page.locator("#status").evaluate((element) => {
            element.hidden = true;
          });
          if ([1440, 390].includes(width) && reducedMotion === "reduce")
            await page.screenshot({
              path: path.join(directory, `${width}-${theme}.png`),
              fullPage: true,
            });
          if (reducedMotion === "reduce") {
            assert.equal(
              await page
                .locator(".metric")
                .first()
                .evaluate((element) => getComputedStyle(element).animationName),
              "none",
            );
          }
          assert(
            requests.every((url) => url === origin + "/opportunities.html"),
            "Prototype contacted another resource",
          );
          states++;
          await page.close();
        }
      }
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(directory, "summary.json"),
      JSON.stringify(
        { states, errors, network: "one local HTML only", integration: false },
        null,
        2,
      ),
    );
    console.log(
      `Oportunidades: ${states} estados, busca/filtros/quadro/detalhes/etapas/teclado e isolamento passaram.`,
    );
  } finally {
    await browser.close();
    server.close();
  }
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
