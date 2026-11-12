const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");

async function validate(browser, origin) {
  let journeys = 0;
  for (const width of [390, 768, 1440]) {
    for (const dark of [false, true]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const errors = [],
        external = [],
        writes = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("request", (request) => {
        if (new URL(request.url()).origin !== origin) external.push(request.url());
        if (request.method() !== "GET") writes.push(request.method());
      });
      await page.goto(origin + "/docs/prototypes/public-booking/index.html");
      if (dark) await page.getByRole("button", { name: "Tema escuro" }).click();
      await page.getByText("Explorar a demonstração", { exact: true }).click();
      await page.selectOption("#business", width === 768 ? "brilho" : "bella");
      for (const scenario of ["normal", "occupied", "empty", "error"]) {
        await page.selectOption("#scenario", scenario);
        await page.locator('input[name="selection"]').first().check();
        await page.getByRole("button", { name: "Continuar", exact: true }).click();
        await page.locator('input[name="selection"]').first().check();
        await page.getByRole("button", { name: "Continuar", exact: true }).click();
        if (scenario === "empty" || scenario === "error") {
          assert.ok(await page.locator("#next").isDisabled());
          await page
            .getByRole("button", {
              name: scenario === "empty" ? "Explorar outro período" : "Tentar novamente",
            })
            .click();
          await page.locator('input[name="selection"]').first().waitFor();
        }
        await page.locator('input[name="selection"]').first().check();
        await page.getByRole("button", { name: "Continuar", exact: true }).click();
        await page.fill("#booking-name", "Pessoa Teste");
        await page.fill("#booking-contact", "pessoa@example.test");
        await page.getByRole("button", { name: "Continuar", exact: true }).click();
        assert.match(await page.locator("#step-content").innerText(), /Pessoa Teste/);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        if (scenario === "normal") {
          const output = path.resolve(__dirname, "../test-results/public-booking-prototype");
          fs.mkdirSync(output, { recursive: true });
          await page.screenshot({
            path: path.join(output, `${width}-${dark ? "dark" : "light"}.png`),
            fullPage: true,
          });
          await page.locator("#next").focus();
          assert.equal(
            await page.locator("#next").evaluate((node) => node === document.activeElement),
            true,
          );
        }
        await page.getByRole("button", { name: "Simular solicitação" }).click();
        if (scenario === "occupied") {
          assert.match(await page.locator("#feedback").innerText(), /indisponível/);
          assert.equal(await page.locator('input[name="selection"][value="09:00"]').count(), 0);
          await page.locator('input[name="selection"]').first().check();
          await page.getByRole("button", { name: "Continuar", exact: true }).click();
          assert.equal(await page.inputValue("#booking-name"), "Pessoa Teste");
          await page.getByRole("button", { name: "Continuar", exact: true }).click();
          await page.getByRole("button", { name: "Simular solicitação" }).click();
        }
        assert.equal(await page.locator("#step-title").innerText(), "Simulação concluída");
        assert.match(
          await page.locator("#step-description").innerText(),
          /Nenhuma reserva foi criada/,
        );
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.getByRole("button", { name: "Recomeçar" }).click();
        journeys++;
      }
      const stored = await page.evaluate(() => ({
        local: localStorage.length,
        session: sessionStorage.length,
      }));
      assert.deepEqual(stored, { local: 0, session: 0 });
      assert.deepEqual(errors, []);
      assert.deepEqual(external, []);
      assert.deepEqual(writes, []);
      await page.close();
    }
  }
  return { publicBookingPrototypeJourneys: journeys, apiWrites: 0 };
}

module.exports = validate;

if (require.main === module) {
  const { chromium } = require("playwright");
  const root = path.resolve(__dirname, "..");
  const server = http.createServer((req, res) => {
    const file = path.resolve(root, "." + new URL(req.url, "http://localhost").pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
      return res.writeHead(404).end();
    res.setHeader(
      "Content-Type",
      { ".html": "text/html", ".css": "text/css", ".js": "text/javascript" }[path.extname(file)] ||
        "application/octet-stream",
    );
    fs.createReadStream(file).pipe(res);
  });
  (async () => {
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const browser = await chromium.launch(
      process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
    );
    try {
      console.log(await validate(browser, `http://127.0.0.1:${server.address().port}`));
    } finally {
      await browser.close();
      server.close();
    }
  })().catch((error) => {
    console.error(error);
    server.close();
    process.exitCode = 1;
  });
}
