const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function intentBrowserFlows(browser, origin) {
  console.log(await require("./priority-browser.cjs")(browser, origin));
  const output = path.join(root, "test-results/purchase-intent");
  fs.mkdirSync(output, { recursive: true });
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const errors = [],
    external = [],
    requests = [];
  try {
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) =>
      requests.push({ method: request.method(), url: request.url() }),
    );
    await page.route("**/*", (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(origin + "/prototypes/opportunities/index.html");
    await page.evaluate(() => document.fonts.ready);
    assert(await page.locator("#intent-result").isHidden());
    await page.locator("#intent-example").selectOption("0");
    assert(
      await page.locator("#intent-result").isHidden(),
      "Carregar exemplo não deve exibir resultado pré-fabricado",
    );
    let layouts = 0;
    for (const width of [320, 360, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        if ((await page.locator("html").getAttribute("data-theme")) !== theme)
          await page.locator("#theme").click();
        await page.locator("#intent-example").selectOption("0");
        await page.locator("#analyze-intent").click();
        assert.equal(await page.locator("#intent-result-title").textContent(), "Intenção elevada");
        const source = await page.locator("#intent-message").inputValue();
        const evidence = await page.locator("#intent-signals blockquote").allTextContents();
        assert(evidence.length >= 4);
        for (const excerpt of evidence) assert(source.includes(excerpt));
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
          `${width}/${theme}: overflow`,
        );
        if ([390, 1440].includes(width)) {
          await page.screenshot({
            path: path.join(output, `analysis-${width}-${theme}.png`),
            fullPage: true,
          });
          await page
            .locator("#intent-result")
            .screenshot({ path: path.join(output, `result-${width}-${theme}.png`) });
        }
        layouts++;
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator("#clear-intent").click();
    const fresh = "Quero contratar o serviço de limpeza de sofá.";
    await page.locator("#intent-message").fill(fresh);
    await page.locator("#analyze-intent").click();
    assert.equal(await page.locator("#intent-result-title").textContent(), "Intenção elevada");
    await page.locator("#compare-intent").click();
    await page.locator("#intent-message").fill("Não quero contratar o serviço de limpeza de sofá.");
    assert(
      await page.locator("#intent-result").isHidden(),
      "Editar deve invalidar resultado anterior",
    );
    await page.locator("#analyze-intent").click();
    assert.equal(await page.locator("#intent-result-title").textContent(), "Recusa ou desistência");
    await page.locator("#compare-intent").click();
    assert.equal(await page.locator(".intent-comparison").count(), 2);
    const labels = await page.locator(".intent-comparison h3").allTextContents();
    assert.deepEqual(labels, ["Intenção elevada", "Recusa ou desistência"]);
    await page.screenshot({ path: path.join(output, "comparison-1440-dark.png"), fullPage: true });
    await page.locator("#intent-message").fill("Bom dia!");
    await page.locator("#analyze-intent").click();
    await page.locator("#compare-intent").click();
    await page.locator("#intent-message").fill("Quanto custa para trocar a fechadura?");
    await page.locator("#analyze-intent").click();
    await page.locator("#compare-intent").click();
    assert.equal(await page.locator(".intent-comparison").count(), 3);
    assert((await page.locator("#intent-status").textContent()).includes("três mensagens"));
    await page.locator(".intent-comparison button").first().click();
    assert.equal(await page.locator("#intent-message").inputValue(), fresh);
    await page.locator('[data-intent-context="conversation"]').first().click();
    assert(await page.locator("#intent-context").isVisible());
    assert((await page.locator("#intent-context-content").textContent()).includes(fresh));
    await page.locator('#intent-context [data-intent-context="client"]').click();
    assert(
      (await page.locator("#intent-context-content").textContent()).includes(
        "Não é um histórico do CRM",
      ),
    );
    await page.screenshot({
      path: path.join(output, "client-context-1440-dark.png"),
      fullPage: true,
    });
    await page.keyboard.press("Escape");
    assert(await page.locator("#intent-context").isHidden());
    await page
      .locator("#intent-message")
      .fill('<img src=x onerror="window.intentInjection=true"> Quanto custa?');
    await page.locator("#analyze-intent").click();
    assert.equal(await page.locator("#intent-result img").count(), 0);
    assert(!(await page.evaluate(() => window.intentInjection)));
    assert.equal(
      await page.locator("#intent-result-title").textContent(),
      "Interesse comercial inicial",
    );
    await page.locator("#clear-intent").click();
    assert.equal(await page.locator(".intent-comparison").count(), 0);
    await page.locator("#analyze-intent").click();
    assert.equal(
      await page.locator("#intent-result-title").textContent(),
      "Informações insuficientes",
    );
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.screenshot({ path: path.join(output, "empty-390-dark.png"), fullPage: true });
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    await page.reload();
    assert(await page.locator("#intent-result").isHidden());
    assert.equal(await page.locator("#intent-message").inputValue(), "");
    await page.locator("#intent-message").focus();
    await page.keyboard.type("Quero comprar um perfume.");
    await page.locator("#analyze-intent").focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#intent-result-title").textContent(), "Intenção elevada");
    assert(
      await page.locator("#intent-result-title").evaluate((el) => el === document.activeElement),
    );
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert(
      requests.every((request) => request.method === "GET" && new URL(request.url).search === ""),
      "Texto não pode sair em query ou corpo de requisição",
    );
    return `Intenção local: ${layouts} layouts, texto novo, negação, evidências, comparação, contexto, vazio, teclado e isolamento passaram.`;
  } finally {
    await context.close();
  }
};
if (require.main === module) {
  const server = http.createServer((request, response) => {
    const file = path.resolve(root, "." + new URL(request.url, "http://local").pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404).end();
      return;
    }
    response.setHeader(
      "Content-Type",
      {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "text/javascript",
        ".woff2": "font/woff2",
      }[path.extname(file)] || "application/octet-stream",
    );
    fs.createReadStream(file).pipe(response);
  });
  (async () => {
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    let browser;
    try {
      browser = await chromium.launch(
        process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
      );
      console.log(await module.exports(browser, `http://127.0.0.1:${server.address().port}`));
    } finally {
      await browser?.close();
      server.close();
    }
  })().catch((error) => {
    console.error(error);
    server.close();
    process.exitCode = 1;
  });
}
