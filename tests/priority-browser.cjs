const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function priorityBrowserFlows(browser, origin) {
  const output = path.join(root, "test-results/customer-priority");
  fs.mkdirSync(output, { recursive: true });
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const errors = [],
    requests = [],
    external = [];
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
    const order = () =>
      page
        .locator("#commercial-priorities .priority-card")
        .evaluateAll((cards) => cards.map((card) => card.dataset.customerId));
    assert.deepEqual(await order(), ["ana", "bruno", "camila", "diego", "helena"]);
    assert.equal(await page.locator("#other-priorities .priority-card").count(), 3);
    const open = async (id) => page.locator(`[data-customer-id="${id}"] button`).click();
    const close = async () => page.keyboard.press("Escape");
    let layouts = 0;
    for (const width of [320, 360, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        if ((await page.locator("html").getAttribute("data-theme")) !== theme)
          await page.locator("#theme").click();
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
          `${width}/${theme}: overflow`,
        );
        const measures = await page.locator(".priority-card").evaluateAll((cards) =>
          cards.map((card) => ({
            paragraphs: [...card.querySelectorAll("p")].map((p) => ({
              width: p.getBoundingClientRect().width,
              size: parseFloat(getComputedStyle(p).fontSize),
            })),
            nameHeight: card.querySelector("h4").getBoundingClientRect().height,
            buttonHeight: card.querySelector("button").getBoundingClientRect().height,
          })),
        );
        for (const card of measures) {
          assert(card.nameHeight < 55, "Nome não pode quebrar em colunas estreitas");
          assert(card.buttonHeight >= 44);
          for (const p of card.paragraphs) {
            assert(
              p.width >= (width <= 390 ? 200 : 100),
              `${width}/${theme}: parágrafo com ${p.width}px`,
            );
            assert(p.size >= 12);
          }
        }
        if ([390, 1440].includes(width)) {
          await page
            .locator("#customer-priorities")
            .screenshot({ path: path.join(output, `queue-${width}-${theme}.png`) });
          await page.evaluate(() => window.scrollTo(0, 0));
          await page.screenshot({ path: path.join(output, `overview-${width}-${theme}.png`) });
        }
        await open("ana");
        assert(await page.locator("#priority-detail").isVisible());
        assert(
          await page.locator("#priority-detail").evaluate((el) => el.scrollWidth <= el.clientWidth),
          `${width}/${theme}: detalhe transbordou: ${JSON.stringify(await page.locator("#priority-detail").evaluate((el) => [...el.querySelectorAll("*")].filter((child) => child.getBoundingClientRect().right > el.getBoundingClientRect().right).map((child) => ({ tag: child.tagName, id: child.id, width: child.getBoundingClientRect().width }))))}`,
        );
        assert(
          (await page.locator("#priority-detail-summary").textContent()).includes(
            "Acompanhar primeiro",
          ),
        );
        if ([390, 1440].includes(width))
          await page
            .locator("#priority-detail")
            .screenshot({ path: path.join(output, `detail-${width}-${theme}.png`) });
        await close();
        assert(
          await page
            .locator('[data-customer-id="ana"] button')
            .evaluate((el) => el === document.activeElement),
        );
        layouts++;
      }
    }
    // Every displayed excerpt must occur in that customer's own source message.
    await page.setViewportSize({ width: 1440, height: 1000 });
    for (const id of [
      "ana",
      "bruno",
      "camila",
      "diego",
      "helena",
      "gabriela",
      "eduardo",
      "fernanda",
    ]) {
      await open(id);
      const entries = await page.locator(".priority-message").evaluateAll((messages) =>
        messages.map((message) => ({
          source: message.querySelector(".priority-source").textContent,
          quotes: [...message.querySelectorAll(".priority-quotes blockquote")].map(
            (q) => q.textContent,
          ),
        })),
      );
      for (const entry of entries)
        for (const quote of entry.quotes)
          assert(entry.source.includes(quote), `${id}: evidência inventada ou de outro cliente`);
      await close();
    }
    await open("camila");
    await page.locator(".priority-editor > summary").click();
    await page.locator("#priority-message").fill("Quero comprar a camisa agora.");
    await page.locator("#priority-message-form button").click();
    assert.equal((await order())[0], "camila", "Texto novo deve mudar a recomendação e a ordem");
    assert(
      (await page.locator("#priority-detail-summary").textContent()).includes(
        "Acompanhar primeiro",
      ),
    );
    await page.locator("#priority-review-group").selectOption("support");
    await page
      .locator("#priority-review-reason")
      .fill("Prefiro esclarecer o pedido anterior antes de oferecer outra compra.");
    await page.locator('#priority-review-form [type="submit"]').click();
    assert.equal(await page.locator('#other-priorities [data-customer-id="camila"]').count(), 1);
    assert(
      (await page.locator("#priority-detail-summary").textContent()).includes(
        "Recomendação automática: Acompanhar primeiro",
      ),
    );
    assert(
      (await page.locator("#priority-detail-summary").textContent()).includes("Revisão humana"),
    );
    await page
      .locator("#priority-detail")
      .screenshot({ path: path.join(output, "review-1440-dark.png") });
    await page.locator("#priority-remove-review").click();
    assert.equal((await order())[0], "camila");
    await page
      .locator("#priority-review-reason")
      .fill("Quero conferir pessoalmente antes de continuar.");
    await page.locator("#priority-review-group").selectOption("clarify");
    await page.locator('#priority-review-form [type="submit"]').click();
    await page.locator("#priority-message").fill("Não quero comprar mais. Desisti.");
    await page.locator("#priority-message-form button").click();
    assert(
      (await page.locator("#priority-detail-summary").textContent()).includes(
        "Respeitar desistência",
      ),
    );
    assert(
      !(await page.locator("#priority-detail-summary").textContent()).includes(
        "Revisão humana nesta sessão:",
      ),
    );
    await close();
    await page.locator("#reanalyze-customers").click();
    assert.equal(await page.locator('#other-priorities [data-customer-id="camila"]').count(), 1);
    await page.locator("#reset-customers").click();
    assert.deepEqual(await order(), ["ana", "bruno", "camila", "diego", "helena"]);
    await page.setViewportSize({ width: 390, height: 1000 });
    await open("bruno");
    await page
      .locator("#priority-review-reason")
      .fill('<img src=x onerror="window.priorityInjection=true">');
    await page.locator('#priority-review-form [type="submit"]').click();
    assert.equal(await page.locator("#priority-detail-summary img").count(), 0);
    assert(!(await page.evaluate(() => window.priorityInjection)));
    await close();
    assert((await page.locator('[data-customer-id="bruno"]').textContent()).includes("<img"));
    await page.reload();
    assert.deepEqual(await order(), ["ana", "bruno", "camila", "diego", "helena"]);
    assert.equal(await page.locator(".review-badge").count(), 0);
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert(
      requests.every((request) => request.method === "GET" && new URL(request.url).search === ""),
      "Nenhum texto em rede",
    );
    return `Priorização: ${layouts} layouts, oito clientes, evidências por cliente, mensagem nova/negação, reordenação, revisão/restauração, foco, isolamento e reset passaram.`;
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
