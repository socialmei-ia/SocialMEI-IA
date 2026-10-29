// Current owner-approved V22 UI. Legacy browser scripts remain as historical controller fixtures.
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path"),
  http = require("node:http");
const { chromium } = require("playwright");
const { waitForViewportFit } = require("./v22-layout-ready.cjs");
const root = path.resolve(__dirname, ".."),
  out = path.join(root, "test-results/v22");
const server = http.createServer((req, res) => {
  let file;
  try {
    file = path.resolve(root, "." + new URL(req.url, "http://localhost").pathname);
  } catch {
    return res.writeHead(400).end();
  }
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
    return res.writeHead(404).end();
  res.setHeader(
    "Content-Type",
    {
      ".js": "text/javascript",
      ".html": "text/html",
      ".css": "text/css",
      ".png": "image/png",
      ".woff2": "font/woff2",
    }[path.extname(file)] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(res);
});
async function run() {
  fs.mkdirSync(out, { recursive: true });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  const errors = [],
    external = [];
  let states = 0;
  try {
    await require("./v22-layout-browser.cjs")(browser, origin);
    const entry = await require("./v22-entry-browser.cjs")(browser, origin);
    await require("./v25-entry-browser.cjs")(browser, origin);
    const contracts = await require("./v22-contract-browser.cjs")(browser, origin);
    await require("./v22-instagram-browser.cjs")(browser, origin);
    await require("./v22-inbox-polling-browser.cjs")(browser, origin);
    await require("./v22-instagram-direct-browser.cjs")(browser, origin);
    await require("./v22-instagram-publisher-browser.cjs")(browser, origin);
    await require("./v22-knowledge-reporting-browser.cjs")(browser, origin);
    await require("./v22-report-viewer-browser.cjs")(browser, origin);
    await require("./v22-whatsapp-catalog-browser.cjs")(browser, origin);
    const page = await browser.newPage({ reducedMotion: "reduce" });
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (r) => {
      if (new URL(r.request().url()).origin !== origin) {
        external.push(r.request().url());
        return r.abort();
      }
      return r.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(() => !!window.SocialMEIV22);
    await page.evaluate(() => document.fonts.ready);
    const routes = [
      "inicio",
      "caixa",
      "negocio/clientes",
      "negocio/produtos",
      "negocio/vendas",
      "negocio/financeiro",
      "oport",
      "divul",
      "relatorios",
      "config/conta",
      "config/seguranca",
      "config/integracoes",
      "agenda",
    ];
    for (const width of [320, 360, 390, 560, 640, 768, 900, 1024, 1180, 1440, 1600]) {
      await page.setViewportSize({ width, height: 1000 });
      await waitForViewportFit(page);
      for (const theme of ["claro", "escuro"]) {
        await page.evaluate((t) => {
          S.theme = t;
          applyTheme();
        }, theme);
        for (const route of routes) {
          await page.evaluate((r) => go("/" + r), route);
          await page.evaluate(
            () =>
              new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          const frame = page.frames().find((f) => f.url().includes("/telas/"));
          if (["oport", "divul"].includes(route)) {
            await page.locator("#v iframe").waitFor();
            await page.frameLocator("#v iframe").locator("body").waitFor();
          }
          assert.equal(
            await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
            false,
            `${width}/${theme}/${route} body overflow`,
          );
          assert(await page.locator("#v").isVisible());
          if (route === "negocio/financeiro") {
            const amounts = await page.locator(".kp b").evaluateAll((elements) =>
              elements.map((el) => {
                const range = document.createRange();
                range.selectNodeContents(el);
                const bounds = range.getBoundingClientRect(),
                  box = el.getBoundingClientRect();
                return {
                  text: el.textContent,
                  visible: bounds.width > 0 && bounds.height > 0,
                  fits: bounds.width <= box.width + 1,
                };
              }),
            );
            assert.equal(amounts.length, 3);
            assert(
              amounts.every((value) => value.visible && value.fits),
              JSON.stringify({ width, theme, amounts }),
            );
          }
          if (
            [390, 768, 1440].includes(width) &&
            ["inicio", "oport", "divul", "relatorios"].includes(route)
          )
            await page.screenshot({
              path: path.join(out, `${route}-${width}-${theme}.png`),
              fullPage: true,
              animations: "disabled",
            });
          states++;
        }
      }
    }
    await page.setViewportSize({ width: 1280, height: 1000 });
    await page.reload();
    await page.waitForFunction(() => !!window.SocialMEIV22);
    await page.evaluate(() => go("/oport"));
    const op = page.frameLocator("#v iframe");
    await op.locator("#client").selectOption({ index: 1 });
    await op.locator("#what").fill("Interesse demonstrativo de teste");
    await op.locator("#form button[type=submit]").click();
    await op.getByText("Interesse demonstrativo de teste", { exact: false }).first().waitFor();
    await page.evaluate(() => go("/divul"));
    const content = page.frameLocator("#v iframe");
    await content.locator("#d3 summary").click();
    await content.locator("#titulo").fill("Rascunho local V22");
    await content.locator("#d4 summary").click();
    await content.locator("#save").click();
    await content.getByText("Rascunho salvo neste navegador.", { exact: true }).waitFor();
    await page.evaluate(() => go("/negocio/clientes"));
    await page.getByRole("button", { name: "Novo cliente", exact: true }).click();
    assert(await page.locator("dialog[open]").isVisible());
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("dialog[open]").count(), 0);
    await page.evaluate(() => {
      S.calm = true;
      applyTheme();
    });
    assert(await page.locator("html").evaluate((e) => e.classList.contains("calm")));
    const touchContext = await browser.newContext({
      viewport: { width: 390, height: 1000 },
      isMobile: true,
      hasTouch: true,
      reducedMotion: "reduce",
    });
    try {
      const touch = await touchContext.newPage();
      touch.on("pageerror", (e) => errors.push(e.message));
      await touch.route("**/*", (r) =>
        new URL(r.request().url()).origin === origin ? r.continue() : r.abort(),
      );
      await touch.goto(origin + "/frontend/socialmei-app.html");
      await touch.waitForFunction(() => !!window.SocialMEIV22);
      await touch.evaluate(() => document.fonts.ready);
      await touch.evaluate(() => go("/oport"));
      const mobile = touch.frameLocator("#v iframe");
      await mobile.locator("#client").selectOption({ index: 1 });
      await mobile.locator("#what").tap();
      await mobile.locator("#what").fill("Interesse por toque no celular");
      await mobile.locator("#form button[type=submit]").tap();
      await mobile.getByText("Interesse por toque no celular", { exact: false }).first().waitFor();
    } finally {
      await touchContext.close();
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    fs.writeFileSync(
      path.join(out, "summary.json"),
      JSON.stringify({ states, entry, errors, external }, null, 2),
    );
    console.log(
      `V22: ${states} layout states, 5 entry flows, opportunity/draft/dialog/keyboard/reduced-motion checks passed.`,
    );
  } finally {
    await browser.close();
    await new Promise((r) => server.close(r));
  }
}
run().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
