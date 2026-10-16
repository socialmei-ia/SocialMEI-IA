const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const { customers } = require("../prototypes/opportunities/priority-scenario.js");
const fixture = customers.filter((customer) => ["ana", "diego", "gabriela"].includes(customer.id));
const root = path.resolve(__dirname, "..");
module.exports = async function tourBrowser(browser, origin) {
  const output = path.join(root, "test-results/tapioca-valley");
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
    let journeys = 0;
    for (const width of [320, 390, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        const check = async () => {
          await page.locator(".tour-banner").waitFor({ state: "visible" });
          assert.equal(await page.locator("html").getAttribute("data-theme"), theme);
          assert((await page.locator(".tour-banner").textContent()).includes("Perfumaria Aurora"));
          assert(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
            `${width}/${theme}: overflow`,
          );
          assert.equal(await page.locator(".tour-steps a").count(), 4);
        };
        const capture = async (name) => {
          if (width !== 320) {
            await page.evaluate(() => document.fonts.ready);
            await page
              .locator("main")
              .screenshot({ path: path.join(output, `${name}-${width}-${theme}.png`) });
          }
        };
        await page.goto(origin + `/prototypes/index.html?theme=${theme}`);
        await page.locator(".tour-feature [data-tour-link]").click();
        await check();
        assert(await page.locator("#perfume").isChecked());
        assert.equal(await page.locator('[name="segment"]:visible').count(), 1);
        await page.locator("#next").click();
        assert(await page.locator("#products").isChecked());
        assert(!(await page.locator("#services").isChecked()));
        assert((await page.locator("#area").inputValue()).includes("Fortaleza"));
        await page.locator("#next").click();
        const config = JSON.parse(await page.locator("#config-preview").textContent());
        assert.equal(config.businessProfile, "perfume");
        assert.equal(config.integrationsEnabled, false);
        assert.equal(config.demo, true);
        await capture("onboarding");
        await page.locator("#tour-next").click();
        await check();
        assert.equal(await page.locator(".tour-conversation").count(), 3);
        for (const customer of fixture) {
          const details = page.locator(`.tour-conversation[data-customer-id="${customer.id}"]`);
          if (!(await details.evaluate((el) => el.open))) await details.locator("summary").click();
          assert((await details.locator("summary").textContent()).includes(customer.name));
          assert.deepEqual(
            await details.locator("blockquote").allTextContents(),
            customer.messages.map((message) => message.text),
          );
        }
        await capture("inbox");
        for (const customer of fixture) {
          const details = page.locator(`.tour-conversation[data-customer-id="${customer.id}"]`);
          if (!(await details.evaluate((el) => el.open))) await details.locator("summary").click();
          await details.locator("a").click();
          await check();
          assert.equal(await page.locator("#intent-example option").count(), 4);
          assert.equal(
            await page.locator("#intent-message").inputValue(),
            customer.messages.at(-1).text,
          );
          await page.locator("#analyze-intent").click();
          const expected = {
            ana: "Intenção elevada",
            diego: "Sinais conflitantes",
            gabriela: "Informações insuficientes",
          };
          assert.equal(
            await page.locator("#intent-result-title").textContent(),
            expected[customer.id],
          );
          for (const excerpt of await page.locator("#intent-signals blockquote").allTextContents())
            assert(customer.messages.at(-1).text.includes(excerpt));
          if (customer.id === "ana") {
            for (const [value, label] of [
              ["1", "Sinais conflitantes"],
              ["2", "Informações insuficientes"],
              ["0", "Intenção elevada"],
            ]) {
              await page.locator("#intent-example").selectOption(value);
              await page.locator("#analyze-intent").click();
              assert.equal(await page.locator("#intent-result-title").textContent(), label);
            }
          }
          if (customer.id === "ana" && width !== 320)
            await page
              .locator(".intent-workspace")
              .screenshot({ path: path.join(output, `intent-${width}-${theme}.png`) });
          if (customer.id !== "gabriela") {
            await page.locator(".tour-steps a").nth(1).click();
            await check();
          }
        }
        await page.locator("a.tour-next").click();
        await check();
        const order = () =>
          page
            .locator("#commercial-priorities .priority-card")
            .evaluateAll((cards) => cards.map((card) => card.dataset.customerId));
        assert.deepEqual(await order(), ["ana", "diego"]);
        assert.equal(
          await page.locator('#other-priorities [data-customer-id="gabriela"]').count(),
          1,
        );
        assert(await page.locator("#manual-library").isHidden());
        if (width !== 320)
          await page
            .locator("#customer-priorities")
            .screenshot({ path: path.join(output, `queue-${width}-${theme}.png`) });
        await page.locator('[data-customer-id="gabriela"] button').click();
        assert(
          (await page.locator("#priority-detail-summary").textContent()).includes(
            "Encaminhar ao suporte",
          ),
        );
        assert(
          (await page.locator("#priority-conversation").textContent()).includes(
            fixture[2].messages.at(-1).text,
          ),
        );
        await page.keyboard.press("Escape");
        await page.locator('[data-customer-id="ana"] button').click();
        await page.locator("#priority-review-group").selectOption("clarify");
        await page
          .locator("#priority-review-reason")
          .fill("Prefiro confirmar o prazo com Ana antes de avançar.");
        await page.locator('#priority-review-form [type="submit"]').click();
        assert(
          (await page.locator("#priority-detail-summary").textContent()).includes(
            "Recomendação automática: Acompanhar primeiro",
          ),
        );
        assert(
          (await page.locator("#priority-detail-summary").textContent()).includes("Revisão humana"),
        );
        if (width !== 320)
          await page
            .locator("#priority-detail")
            .screenshot({ path: path.join(output, `review-${width}-${theme}.png`) });
        await page.keyboard.press("Escape");
        assert.deepEqual(await order(), ["diego", "ana"]);
        await page.locator("#reset-customers").click();
        assert.deepEqual(await order(), ["ana", "diego"]);
        assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
        journeys++;
      }
    // Original previews keep their original datasets and profile choices outside the tour.
    await page.goto(origin + "/prototypes/opportunities/index.html");
    assert.equal(await page.locator(".priority-card").count(), 8);
    assert.equal(await page.locator("#intent-example option").count(), 13);
    assert.equal(await page.locator(".tour-banner").count(), 0);
    assert(!(await page.locator("#manual-library").evaluate((el) => el.hidden)));
    await page.goto(origin + "/prototypes/onboarding/index.html");
    assert.equal(await page.locator('[name="segment"]:visible').count(), 6);
    await page.locator("#barber").check();
    await page.locator("#next").click();
    assert(await page.locator("#services").isChecked());
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert(
      requests.every(
        (request) =>
          request.method === "GET" &&
          [...new URL(request.url).searchParams.keys()].every((key) =>
            ["tour", "theme", "client"].includes(key),
          ),
      ),
    );
    return `Tapioca Valley: ${journeys} percursos completos (320/390/1440, claro/escuro), onboarding, três conversas, análise, fila, revisão, coerência e isolamento passaram; prévias originais preservadas.`;
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
