const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const output = path.join(root, "test-results/business-layout");
const server = http.createServer((req, res) => {
  let file = path.resolve(root, "." + new URL(req.url, "http://localhost").pathname);
  if (!file.startsWith(root + path.sep)) return res.writeHead(403).end();
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
  if (!fs.existsSync(file)) return res.writeHead(404).end();
  res.setHeader(
    "Content-Type",
    {
      ".html": "text/html",
      ".js": "text/javascript",
      ".css": "text/css",
      ".png": "image/png",
      ".woff2": "font/woff2",
    }[path.extname(file)] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(res);
});
async function run() {
  fs.mkdirSync(output, { recursive: true });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
  });
  const errors = [],
    requests = [],
    metrics = [];
  const context = await browser.newContext({
    reducedMotion: "reduce",
    viewport: { width: 1440, height: 1000 },
  });
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin || /\/api\//.test(url.pathname)) {
      requests.push(url.href);
      return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  const capture = async (name) => {
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({
      path: path.join(output, `${name}.png`),
      fullPage: true,
      animations: "disabled",
    });
  };
  try {
    if (process.env.CAPTURE_NATIVE === "1") {
      await page.goto(origin + "/frontend/socialmei-app.html");
      await page.locator("[data-start-signup]").first().click();
      await page.locator("#registerName").fill("Ana de teste");
      await page.locator("#registerEmail").fill("ana@example.com");
      await page.locator("#registerPhone").fill("11999998888");
      await page.locator("#registerPassword").fill("TesteLocal123!");
      await page.locator("#xpRegisterForm [type=submit]").click();
      await page.locator('.contact-confirmation button[value="confirm"]').click();
      await page.locator('[data-onboard-panel="1"].is-active').waitFor();
      await page.locator("[data-onboard-next]").click();
      await page.locator('[data-onboard-panel="2"].is-active').waitFor();
      await page.locator("#obBusiness").fill("Studio da Ana");
      await page.locator('#businessFamilyChoices [data-family="Beleza e cuidados"]').click();
      await page.locator('#businessSpecialtyChoices input[value="barber"]').check();
      for (const width of [1440, 768, 390])
        for (const theme of ["light", "dark"]) {
          await page.setViewportSize({ width, height: 1000 });
          if ((await page.locator("html").getAttribute("data-public-theme")) !== theme)
            await page.locator(".onboarding-screen [data-public-theme-toggle]").click();
          await capture(`before-${width}-${theme}`);
          metrics.push(
            await page.evaluate(
              ({ width, theme }) => {
                const family = document
                  .querySelector("#businessFamilyChoices")
                  .getBoundingClientRect();
                const choices = document
                  .querySelector("#businessSpecialtyChoices")
                  .getBoundingClientRect();
                return {
                  version: "official-before",
                  width,
                  theme,
                  familyHeight: family.height,
                  specialtiesHeight: choices.height,
                  independentColumnGap:
                    choices.left > family.right ? Math.max(0, choices.bottom - family.bottom) : 0,
                };
              },
              { width, theme },
            ),
          );
        }
      fs.writeFileSync(path.join(output, "before-metrics.json"), JSON.stringify(metrics, null, 2));
      console.log("Native baseline: 6 screenshots captured.");
      return;
    }
    await context.addInitScript(() => {
      localStorage.setItem("official-profile-sentinel", "unchanged");
      window.storageWrites = [];
      Storage.prototype.setItem = function (key) {
        window.storageWrites.push(key);
      };
    });
    await page.goto(origin + "/experimental/onboarding-v3/");
    await page.getByRole("button", { name: "Usar exemplo", exact: true }).click();
    await page.locator("#nextButton").click();
    await page.locator("#businessName").waitFor();
    await page.locator("#businessName").fill("Studio da Ana");
    const snapshot = () => page.evaluate(() => SocialMEIOnboardingPreview.snapshot());
    const themeTo = async (theme) => {
      if ((await page.locator("html").getAttribute("data-preview-theme")) !== theme)
        await page.locator("#themeToggle").click();
    };
    for (const width of [1440, 768, 390])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await themeTo(theme);
        for (const [family, count] of [
          ["beauty", 6],
          ["fashion", 2],
          ["food", 3],
        ]) {
          await page.locator(`[data-family="${family}"]`).click();
          assert.equal(await page.locator('[name="segment"]').count(), count);
          const geometry = await page.evaluate(() => {
            const grid = document.querySelector("#familyGrid"),
              picker = document.querySelector(".ob3-picker");
            const family = grid.getBoundingClientRect(),
              choices = picker.getBoundingClientRect();
            const labels = [...document.querySelectorAll(".ob3-specialties label")];
            return {
              overflow: document.documentElement.scrollWidth > innerWidth,
              familyColumns: getComputedStyle(grid).gridTemplateColumns.split(" ").length,
              familyWidth: family.width,
              specialtyWidth: choices.width,
              specialtiesBelow: choices.top >= family.bottom,
              labelsReadable: labels.every(
                (e) =>
                  e.offsetWidth >= 200 &&
                  e.offsetHeight >= 44 &&
                  e.scrollWidth <= e.clientWidth &&
                  e.querySelector("small").textContent.trim(),
              ),
            };
          });
          assert(
            geometry.specialtiesBelow,
            "Specialties must be below all six areas, not an independent column",
          );
          assert.equal(geometry.familyColumns, width === 1440 ? 3 : width === 768 ? 2 : 1);
          assert(Math.abs(geometry.familyWidth - geometry.specialtyWidth) < 2);
          assert(
            !geometry.overflow && geometry.labelsReadable,
            "Readable, full-width choices without clipping",
          );
          await page.locator('[name="segment"]').first().check();
          await capture(`after-${family}-${width}-${theme}`);
          metrics.push({ width, theme, family, count, ...geometry });
        }
      }
    const allIds = new Set();
    for (const family of ["beauty", "fashion", "food", "commerce", "technology", "services"]) {
      await page.locator(`[data-family="${family}"]`).click();
      for (const id of await page
        .locator('[name="segment"]')
        .evaluateAll((inputs) => inputs.map((input) => input.value)))
        allIds.add(id);
    }
    assert.equal(allIds.size, 23, "All original specialties are accessible from six areas");
    // Browse/search without changing the draft or moving focus unexpectedly.
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('[data-family="beauty"]').click();
    await page.locator('[name="segment"][value="barber"]').check();
    await page.locator('[name="offers"][value="products"]').check();
    const selected = (await snapshot()).profile;
    await page.evaluate(() => scrollTo(0, 0));
    await page.locator('[data-family="fashion"]').evaluate((e) => e.focus({ preventScroll: true }));
    const scroll = await page.evaluate(() => scrollY);
    await page.keyboard.press("Enter");
    assert.equal(await page.evaluate(() => document.activeElement.dataset.family), "fashion");
    assert.equal(await page.evaluate(() => scrollY), scroll);
    assert.deepEqual((await snapshot()).profile, selected);
    await page.locator("#activitySearch").fill("barbeiro");
    assert.equal(await page.locator('[name="segment"][value="barber"]').count(), 1);
    assert(await page.locator("#activitySearch").evaluate((e) => e === document.activeElement));
    await themeTo("light");
    await capture("search-1440-light");
    await page.locator("#activitySearch").fill("zzzinexistente");
    assert.equal(await page.locator('[name="segment"]').count(), 0);
    assert.deepEqual((await snapshot()).profile, selected);
    await page.setViewportSize({ width: 390, height: 1000 });
    await themeTo("dark");
    await capture("empty-390-dark");
    await page.getByText("Prefiro ver a lista completa", { exact: true }).click();
    assert.equal(await page.locator("#allActivities option:not([disabled])").count(), 23);
    await page.locator("#allActivities").selectOption("barber");
    assert.deepEqual(
      (await snapshot()).profile,
      selected,
      "Re-selecting the same specialty must retain mixed offers",
    );
    await page.locator("#activitySearch").fill("");
    await page.locator('[data-family="beauty"]').click();
    await page.locator('[name="segment"][value="barber"]').focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(await page.locator('[name="segment"]:checked').inputValue(), "hairdresser");
    assert(
      await page.locator('[name="segment"]:checked').evaluate((e) => e === document.activeElement),
    );
    assert.deepEqual(
      (await snapshot()).profile.offers,
      selected.offers,
      "Explicit mixed offers remain when changing specialty",
    );
    await page.locator("#businessName").fill("");
    await page.locator("#nextButton").click();
    assert.equal(await page.locator("#businessName").getAttribute("aria-invalid"), "true");
    assert(await page.locator("#businessName").evaluate((e) => e === document.activeElement));
    await capture("error-390-dark");
    await page.locator("#businessName").fill("Studio da Ana");
    await page.locator("#nextButton").click();
    await page.locator("#servicesChoices").waitFor();
    await page.locator("#backButton").click();
    await page.locator("#businessName").waitFor();
    assert.equal(await page.locator("#businessName").inputValue(), "Studio da Ana");
    assert.equal(await page.locator('[name="segment"]:checked').inputValue(), "hairdresser");
    await page.locator("#businessName").focus();
    await page.keyboard.press("Tab");
    assert(await page.locator("#activitySearch").evaluate((e) => e === document.activeElement));
    await page.keyboard.press("Shift+Tab");
    assert(await page.locator("#businessName").evaluate((e) => e === document.activeElement));
    // Review editing must keep previously entered services and products.
    await page.locator("#nextButton").click();
    await page.locator("#servicesChoices").waitFor();
    await page.locator("#servicesChoices input").first().check();
    const offersBefore = (await snapshot()).profile;
    await page.locator("#backButton").click();
    await page.locator("#businessName").waitFor();
    await page.locator('[data-family="beauty"]').click();
    await page.locator('[name="segment"][value="perfume"]').check();
    assert.deepEqual((await snapshot()).profile.services, offersBefore.services);
    assert.deepEqual((await snapshot()).profile.offers, offersBefore.offers);
    // Text enlargement is a stress check, not a screen-reader certification.
    await page.setViewportSize({ width: 320, height: 800 });
    await page.evaluate(() => {
      window.textStyles = [
        ...document.querySelectorAll(
          "#stage b,#stage small,#stage h1,#stage h2,#stage p,#stage label > span",
        ),
      ].map((e) => [e, e.style.fontSize, getComputedStyle(e).fontSize]);
      textStyles.forEach(([e, , size]) => (e.style.fontSize = `${parseFloat(size) * 2}px`));
    });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator("#nextButton").scrollIntoViewIfNeeded();
    const button = await page.locator("#nextButton").boundingBox();
    assert(button.y >= 0 && button.y + button.height <= 800);
    await capture("text-200-320-dark");
    await page.evaluate(() => textStyles.forEach(([e, size]) => (e.style.fontSize = size)));
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.locator('[data-family="fashion"]').click();
    assert(await page.locator("#specialties").evaluate((e) => e.getAnimations().length > 0));
    await page.locator('[data-family="food"]').click();
    await page.locator('[data-family="beauty"]').click();
    assert.equal(await page.locator('[name="segment"]').count(), 6);
    await page.waitForTimeout(250);
    assert.equal(await page.locator("#specialties").evaluate((e) => e.getAnimations().length), 0);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.locator('[data-family="fashion"]').click();
    assert.equal(await page.locator("#specialties").evaluate((e) => e.getAnimations().length), 0);
    assert.deepEqual(await page.evaluate(() => window.storageWrites), []);
    assert.equal(
      await page.evaluate(() => localStorage.getItem("official-profile-sentinel")),
      "unchanged",
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(requests, []);
    fs.writeFileSync(
      path.join(output, "summary.json"),
      JSON.stringify({ layouts: metrics.length, errors, requests, metrics }, null, 2),
    );
    console.log(
      `PASS: ${metrics.length} layouts, search/full list, keyboard/focus, validation, data retention, motion/reduced, no storage/API writes.`,
    );
  } finally {
    await browser.close();
    server.close();
  }
}
run().catch((e) => {
  console.error(e);
  process.exitCode = 1;
  server.close();
});
