const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const resultDirectory = path.join(root, "test-results/visual-redesign");
const contentTypes = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".png": "image/png",
  ".woff2": "font/woff2",
};
const server = http.createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const file = path.resolve(root, "." + pathname);
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
  fs.mkdirSync(resultDirectory, { recursive: true });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const errors = [];
  const missingResources = [];
  let browser;
  let geometryStates = 0;
  let financeStates = 0;
  try {
    browser = await chromium.launch(
      process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
    );
    const page = await browser.newPage({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "reduce",
    });
    page.on("pageerror", (error) => errors.push(error.name));
    page.on("response", (response) => {
      if (new URL(response.url()).origin === origin && response.status() >= 400) {
        missingResources.push({
          path: new URL(response.url()).pathname,
          status: response.status(),
        });
      }
    });
    await page.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => SocialMEIExperience.enterApp("Início"));

    for (const width of [1920, 1600, 1440, 1366, 1280, 1024, 900, 768, 430, 390, 360]) {
      await page.setViewportSize({ width, height: 900 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => {
          setTheme(theme);
          setView("Início");
        }, theme);
        await page.evaluate(
          () =>
            new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        const bounds = await page.evaluate(() => {
          const main = document.querySelector("#mainContent").getBoundingClientRect();
          const sidebar = document.querySelector("#sb").getBoundingClientRect();
          const title = document.querySelector("#clientHomeTitle").getBoundingClientRect();
          const header = document.querySelector(".hd").getBoundingClientRect();
          const input = document.querySelector("#clientCommandInput");
          return {
            mainLeft: main.left,
            sidebarRight: sidebar.right,
            headerTop: header.top,
            titleTop: title.top,
            documentWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
            inputBorder: getComputedStyle(input).borderStyle,
          };
        });
        assert(
          bounds.documentWidth <= bounds.viewportWidth + 1,
          `Home overflow at ${width}/${theme}`,
        );
        if (width > 900)
          assert(
            bounds.mainLeft >= bounds.sidebarRight - 1,
            "Desktop shell stopped placing navigation beside content",
          );
        assert(bounds.headerTop < 100, "Header was displaced beneath the sidebar");
        assert(bounds.titleTop < 300, "Home opening fell below the initial viewport");
        assert.equal(
          await page.evaluate(() => document.getAnimations().length),
          0,
          "Reduced motion retained animations",
        );
        geometryStates++;
        await page.evaluate(() => setView("Financeiro"));
        const amounts = await page
          .locator("#financeSummary .management-kpi > b")
          .evaluateAll((elements) =>
            elements.map((element) => ({
              text: element.textContent,
              height: element.getBoundingClientRect().height,
              lineHeight: parseFloat(getComputedStyle(element).lineHeight),
            })),
          );
        assert.equal(amounts.length, 5);
        for (const amount of amounts) {
          assert(
            amount.height <= amount.lineHeight + 1,
            `Finance amount split across lines at ${width}/${theme}: ${amount.text}`,
          );
        }
        financeStates++;
      }
    }

    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.evaluate(() => {
      setTheme("light");
      setView("Início");
    });
    await page.locator(".home-sale-row").first().click();
    assert.equal(await page.locator(".page-view.active").getAttribute("data-view"), "Vendas");
    assert.equal(
      await page.locator("#createModal").evaluate((element) => element.classList.contains("open")),
      false,
    );
    await page.evaluate(() => setView("Início"));
    await page.locator('[data-home-create="venda"]').click();
    assert(
      await page.locator("#createModal").evaluate((element) => element.classList.contains("open")),
    );
    await page.keyboard.press("Escape");
    assert.equal(
      await page.locator("#createModal").evaluate((element) => element.classList.contains("open")),
      false,
    );
    await page.evaluate(() => {
      setView("Início");
      toggleMoney();
    });
    assert.equal((await page.locator("#homeRecentSales").innerText()).includes("R$"), false);
    await page.evaluate(() => toggleMoney());

    await page.evaluate(() => SocialMEIExperience.showScreen("auth"));
    await page.locator('[data-auth-tab="register"]').click();
    await page.locator("#registerPassword").fill("Password123456!");
    assert.equal(
      await page.locator('#registerPasswordStrength [role="meter"]').getAttribute("aria-valuenow"),
      "1",
    );
    assert(await page.locator("#registerPassword").evaluate((input) => input.validity.valid));
    await page.locator("#registerPasswordStrength summary").press("Enter");
    assert(
      await page.locator("#registerPasswordStrength details").evaluate((element) => element.open),
    );
    await page.locator("#registerPassword").fill("Private-Synthetic-9!");
    assert.equal(
      await page.locator('#registerPasswordStrength [role="meter"]').getAttribute("aria-valuenow"),
      "4",
    );
    assert(
      await page.evaluate(() =>
        [...Object.values(localStorage)].every((value) => !value.includes("Private-Synthetic-9!")),
      ),
    );
    await page.waitForFunction(() =>
      document
        .querySelector('#registerPasswordStrength [aria-live="polite"]')
        .textContent.includes("forte"),
    );
    await page.screenshot({
      path: path.join(resultDirectory, "password-strength.png"),
      fullPage: true,
    });

    await page.evaluate(() => SocialMEIExperience.showScreen("landing"));
    assert.equal(await page.locator("[data-spotlight]").count(), 3);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    const surface = page.locator(".landing-ai[data-spotlight]");
    await surface.scrollIntoViewIfNeeded();
    const box = await surface.boundingBox();
    await page.mouse.move(box.x + box.width * 0.4, box.y + box.height * 0.5);
    await page.waitForFunction(
      () => !!document.querySelector(".landing-ai[data-spotlight-active]"),
    );
    assert.equal(await page.locator("[data-spotlight-active]").count(), 1);
    assert.equal(
      await surface
        .locator(".spotlight-layer")
        .evaluate((element) => getComputedStyle(element).pointerEvents),
      "none",
    );
    await surface.screenshot({ path: path.join(resultDirectory, "spotlight-desktop.png") });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.waitForFunction(() => !document.querySelector("[data-spotlight-active]"));
    assert.equal(
      await surface
        .locator(".spotlight-layer")
        .evaluate((element) => getComputedStyle(element).display),
      "none",
    );

    const touch = await browser.newPage({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
      isMobile: true,
      reducedMotion: "no-preference",
    });
    await touch.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    await touch.goto(origin + "/frontend/socialmei-app.html");
    const touchSurface = touch.locator(".landing-ai[data-spotlight]");
    await touchSurface.scrollIntoViewIfNeeded();
    assert.equal(
      await touchSurface
        .locator(".spotlight-layer")
        .evaluate((element) => getComputedStyle(element).display),
      "none",
    );
    assert.notEqual(
      await touchSurface.evaluate((element) => getComputedStyle(element).touchAction),
      "none",
    );
    const beforeScroll = await touch.evaluate(() => scrollY);
    await touch.evaluate(() => window.scrollBy(0, 150));
    assert((await touch.evaluate(() => scrollY)) > beforeScroll);
    await touch.close();

    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.evaluate(() => {
      SocialMEIExperience.enterApp("Início");
      sessionData.conversas = [];
      for (const module of ["clientes", "produtos", "vendas", "financeiro"]) appData[module] = [];
      renderClientHome();
    });
    assert((await page.locator("#homePulseFinance").innerText()).includes("Ainda sem lançamentos"));
    assert(
      (await page.locator("#homePulseConversations").innerText()).includes("Nenhum atendimento"),
    );
    assert.equal(await page.locator("#homeRecentSales .home-sale-row").count(), 0);
    await page.screenshot({ path: path.join(resultDirectory, "home-empty.png"), fullPage: true });
    assert.deepEqual(errors, []);
    assert.deepEqual(missingResources, []);
    console.log(
      `${geometryStates} Home and ${financeStates} Finance geometry/theme states; navigation, privacy, password advisory, keyboard, spotlight, touch, empty state and reduced motion PASS.`,
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
