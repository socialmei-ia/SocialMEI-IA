const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const resultDirectory = path.join(root, "test-results");
const contentTypes = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".png": "image/png",
  ".woff2": "font/woff2",
};
const server = http.createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const file = path.resolve(root, "." + (pathname === "/" ? "/index.html" : pathname));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404).end();
    return;
  }
  response.setHeader(
    "Content-Type",
    contentTypes[path.extname(file)] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(response);
});

async function run() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  let browser;
  const errors = [];
  const missingResources = [];
  const buttons = new Map();
  let states = 0;
  try {
    browser = await chromium.launch(
      process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
    );
    const page = await browser.newPage({ reducedMotion: "reduce" });
    page.on("pageerror", (error) => errors.push(error.name));
    page.on("response", (response) => {
      if (new URL(response.url()).origin === origin && response.status() >= 400)
        missingResources.push({
          path: new URL(response.url()).pathname,
          status: response.status(),
        });
    });
    await page.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => SocialMEIExperience.enterApp("Início"));
    const views = await page
      .locator(".page-view")
      .evaluateAll((elements) => elements.map((element) => element.dataset.view));
    const customId = await page.evaluate(
      () =>
        SocialMEIThemes.save({
          version: 1,
          name: "QA layout",
          base: "dark",
          primary: "#2255BB",
          accent: "#FFCC00",
          intensity: 35,
          overrides: {},
        }).id,
    );
    for (const [width, height] of [
      [1920, 1080],
      [1600, 900],
      [1440, 900],
      [1366, 768],
      [1280, 720],
      [1024, 768],
      [900, 900],
      [768, 1024],
      [430, 932],
      [390, 844],
      [360, 800],
    ]) {
      await page.setViewportSize({ width, height });
      for (const mode of ["light", "dark", "auto-light", "auto-dark", "custom"]) {
        const dark = mode === "dark" || mode === "auto-dark" || mode === "custom";
        await page.emulateMedia({ colorScheme: dark ? "dark" : "light" });
        await page.evaluate(
          ({ mode, customId }) =>
            mode === "custom"
              ? SocialMEIThemes.select(customId)
              : setTheme(mode.startsWith("auto") ? "auto" : mode),
          { mode, customId },
        );
        await page.evaluate(() => SocialMEIExperience.enterApp("Início"));
        for (const view of views) {
          await page.evaluate((view) => setView(view), view);
          await page.evaluate(
            () =>
              new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          assert.equal(
            await page.locator(".page-view.active").getAttribute("data-view"),
            view === "Meu negócio" ? "Visão Geral" : view,
          );
          assert(
            await page.evaluate(
              () =>
                document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
            ),
            `${view}: ${width}/${mode}`,
          );
          await page
            .locator("button")
            .evaluateAll((elements) =>
              elements
                .filter((element) => element.getClientRects().length && !element.closest("[inert]"))
                .map((element) => ({
                  id: element.id,
                  label:
                    element.getAttribute("aria-label") || element.innerText.trim() || element.title,
                  disabled: element.disabled,
                  actions: Object.keys(element.dataset),
                })),
            )
            .then((items) => {
              for (const item of items) {
                const key = JSON.stringify(item);
                buttons.set(key, item);
                assert(
                  item.label,
                  `Botão sem nome acessível: ${item.id || item.actions.join(",")}`,
                );
              }
            });
          states++;
        }
        for (const screen of ["landing", "auth", "onboarding"]) {
          await page.evaluate((screen) => SocialMEIExperience.showScreen(screen), screen);
          await page.evaluate(
            () =>
              new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          assert(
            await page.evaluate(
              () =>
                document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
            ),
            `${screen}: ${width}/${mode}`,
          );
          states++;
        }
      }
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(missingResources, []);
    fs.mkdirSync(resultDirectory, { recursive: true });
    fs.writeFileSync(
      path.join(resultDirectory, "stability-summary.json"),
      JSON.stringify(
        {
          states,
          viewCount: views.length,
          buttons: [...buttons.values()],
          errors,
          missingResources,
        },
        null,
        2,
      ),
    );
    console.log(
      `${states} estados de layout/tema; ${buttons.size} estados de botões; zero pageerror/404 local.`,
    );
  } finally {
    await browser?.close();
    await new Promise((resolve) => server.close(resolve));
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
