const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function exactV4(browser, origin) {
  const context = await browser.newContext({
    reducedMotion: "reduce",
    acceptDownloads: true,
    viewport: { width: 1440, height: 900 },
    timezoneId: "America/Fortaleza",
    hasTouch: true,
  });
  const page = await context.newPage(),
    errors = [],
    external = [];
  const output = path.resolve(__dirname, "../test-results/exact-v8-v4");
  fs.mkdirSync(output, { recursive: true });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) =>
    new URL(route.request().url()).origin === origin
      ? route.continue()
      : (external.push(route.request().url()), route.abort()),
  );
  const step = async (number) => {
    const details = page.locator("#exactV4-d" + number);
    if (!(await details.evaluate((el) => el.open)))
      await details.locator(":scope > summary").click();
  };
  const dock = async (name) => {
    await page.evaluate(() => document.activeElement?.blur());
    await page.locator("#contentWorkspace-" + name).click();
  };
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    await page.locator("#contentStudioOpen").click();
    assert.equal(await page.evaluate(() => currentView), "Divulgação");
    await page.evaluate(() => {
      SocialMEIBusinessProfile.browserRepository().save({
        completed: true,
        businessName: "Negócio de Maiccon",
        segment: "barber",
        offers: ["services"],
        modules: ["clients"],
      });
      SocialMEIContentStudio.render();
    });
    assert.equal(await page.locator(".exact-v4-root").count(), 1);
    const geometry = await page.locator("#contentCreatePanel").evaluate((el) => ({
      left: el.querySelector(".stage").getBoundingClientRect().left,
      right: el.querySelector("#contentDraftForm").getBoundingClientRect().left,
    }));
    assert(geometry.left < geometry.right, "Original phone must be left of the guided form");
    assert.equal(
      await page.locator('[data-content-format="story"]').getAttribute("aria-checked"),
      "true",
    );
    await step(2);
    await page.locator("#dv4Topic").fill("Bastidores");
    await page.locator("#dv4Offering").fill("Corte de cabelo");
    await page.locator("#exactV4-sug").click();
    assert.equal(await page.locator("#exactV4-sugs button").count(), 3);
    await page.locator("#exactV4-sugs button").first().click();
    await page.locator("#contentTitle").fill("Novidade fictícia");
    await page.locator("#contentPreviewCaption").fill("Texto escrito diretamente na prévia.");
    assert.equal(
      await page.locator("#contentCaption").inputValue(),
      "Texto escrito diretamente na prévia.",
    );
    await page.locator("#contentCta").fill("Converse com a gente");
    await page.locator("#contentHashtags").fill("#mei");
    const png = await page.evaluate(() => {
      const c = document.createElement("canvas");
      c.width = 640;
      c.height = 800;
      c.getContext("2d").fillRect(0, 0, 640, 800);
      return c.toDataURL("image/png").split(",")[1];
    });
    await page.locator("#contentMedia").setInputFiles({
      name: "ficticio.png",
      mimeType: "image/png",
      buffer: Buffer.from(png, "base64"),
    });
    await page.locator("#contentPreviewStage img").waitFor();
    await page.locator("#dv4Zoom").fill("1.5");
    await page.locator("#contentPreviewStage").focus();
    await page.keyboard.press("ArrowLeft");
    assert.equal(await page.locator("#contentPreviewStage").getAttribute("data-dv4-x"), "55");
    await page.locator("#dv4SafeArea").check();
    assert.match(await page.locator("#contentPreviewDevice").getAttribute("class"), /sf/);
    await page.keyboard.press("Control+s");
    assert.match(await page.locator("#contentActionStatus").textContent(), /Rascunho salvo/);
    await dock("drafts");
    assert.equal(await page.locator("[data-content-draft]").count(), 1);
    assert.equal(
      await page.locator("[data-content-draft] .th img").count(),
      1,
      "Bounded local thumbnail should appear in the original draft card",
    );
    await page.locator("[data-content-action=duplicate]").click();
    assert.equal(await page.locator("#contentTitle").inputValue(), "Novidade fictícia · cópia");
    await dock("drafts");
    await page.locator("#dv4DraftQuery").fill("inexistente");
    assert.equal(await page.locator("[data-content-draft]:visible").count(), 0);
    await page.locator("#dv4DraftQuery").fill("");
    await page.locator("#dv4DraftFormat").selectOption("story");
    assert.equal(await page.locator("[data-content-draft]:visible").count(), 2);
    const downloading = page.waitForEvent("download");
    await page.locator("#dv4Export").click();
    const download = await downloading;
    const payload = JSON.parse(fs.readFileSync(await download.path(), "utf8"));
    assert.equal(payload.drafts.length, 2);
    assert(payload.drafts.every((item) => !item.presentation?.thumbnail));
    page.once("dialog", (dialog) => dialog.accept());
    await page.locator("#dv4ImportFile").setInputFiles({
      name: "original-v4.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          app: "socialmei-divulgacao",
          v: 4,
          drafts: [
            {
              id: "foreign-id",
              f: "feed",
              titulo: "Importado V4",
              leg: "Somente teste",
              tema: "Tema",
              prod: "Serviço",
            },
          ],
        }),
      ),
    });
    // File parsing opens confirmation asynchronously; confirm through the native dialog event.
    await page.waitForFunction(
      () => document.querySelectorAll("[data-content-draft]").length === 3,
    );
    await dock("agenda");
    assert.equal(await page.locator("#exactV4-strip .dy").count(), 14);
    await page.locator("#exactV4-strip .dy").nth(2).click();
    assert.equal(
      await page.locator("#exactV4-strip .dy").nth(2).getAttribute("aria-pressed"),
      "true",
    );
    assert(
      await page.locator("#exactV4-sch").isDisabled(),
      "Unavailable backend cannot fake a local server schedule",
    );
    await dock("connections");
    assert.equal(await page.locator("#exactV4-cg .cn").count(), 3);
    assert.match(await page.locator("#exactV4-cg").textContent(), /Não conectado/);
    await dock("create");
    await step(3);
    await page.locator("#contentCaption").fill("Rascunho humano preservado ao atualizar");
    await page.reload();
    await page.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
    await step(3);
    assert.equal(
      await page.locator("#contentCaption").inputValue(),
      "Rascunho humano preservado ao atualizar",
    );
    assert.equal(
      await page.locator("#contentPreviewStage img").count(),
      0,
      "Original media must not be stored",
    );
    await page.evaluate(() => {
      sessionStorage.setItem("socialmei-business-demo-identity", "v4-other-business");
      setView("Início");
      setView("Divulgação");
    });
    assert.equal(await page.locator("#contentTitle").inputValue(), "");
    assert.equal(await page.locator("[data-content-draft]").count(), 0);
    await page.evaluate(() => {
      sessionStorage.removeItem("socialmei-business-demo-identity");
      setView("Início");
      setView("Divulgação");
    });
    assert.equal(await page.locator("[data-content-draft]").count(), 3);
    await dock("create");
    await step(4);
    await page.locator("#contentNew").click();
    if (await page.locator("#contentConfirmModal").isVisible())
      await page.locator("#contentConfirmAction").click();
    await step(1);
    await page.waitForFunction(
      () => !document.getElementById("exactV4-toast").classList.contains("on"),
    );
    for (const width of [1440, 1024, 768, 390, 320])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({
          width,
          height: width === 320 ? 700 : width === 390 ? 844 : 900,
        });
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        await page.evaluate(() => {
          document.activeElement?.blur();
          scrollTo(0, 0);
        });
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
          "No horizontal overflow",
        );
        assert.equal(await page.locator(".exact-v4-root").getAttribute("data-t"), theme);
        await page.waitForFunction(() => {
          const selected = document.querySelector("#contentStudioView .dock [aria-selected=true]");
          const indicator = document.getElementById("exactV4-ind");
          return (
            Math.abs(
              indicator.getBoundingClientRect().width - selected.getBoundingClientRect().width,
            ) <= 1
          );
        });
        await page.screenshot({
          path: path.join(output, `divulgacao-integrated-${width}-${theme}.png`),
          fullPage: true,
        });
        const reference = await context.newPage();
        await reference.route("**/*", (r) =>
          new URL(r.request().url()).origin === origin ? r.continue() : r.abort(),
        );
        await reference.setViewportSize({
          width,
          height: width === 320 ? 700 : width === 390 ? 844 : 900,
        });
        await reference.goto(origin + "/frontend/reference/Divulgacao-V4-original.html");
        await reference.evaluate((theme) => (document.documentElement.dataset.t = theme), theme);
        await reference.screenshot({
          path: path.join(output, `divulgacao-original-${width}-${theme}.png`),
          fullPage: true,
        });
        const canvasWidth = await page
          .locator(".exact-v4-root")
          .evaluate((el) => Math.round(el.getBoundingClientRect().width));
        await reference.setViewportSize({ width: canvasWidth, height: 900 });
        // ResizeObserver delivery and media-query layout happen on rendering frames.
        // Opening the reference tab can background the native page before that delivery.
        // Compare settled layouts; keep the exact original/native geometry assertion below.
        await page.bringToFront();
        await page.waitForFunction(() => {
          const el = document.querySelector(".exact-v4-root");
          const width = el.getBoundingClientRect().width;
          return (
            width > 0 &&
            [
              ["compact", 900],
              ["mobile", 560],
              ["tiny", 340],
            ].every(([name, max]) => el.hasAttribute("data-v4-" + name) === width <= max) &&
            Math.abs(parseFloat(el.style.getPropertyValue("--v4-vw")) * 100 - width) < 0.2
          );
        });
        await reference.bringToFront();
        await reference.evaluate(
          () =>
            new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        const nativeStyle = await page.locator(".exact-v4-root").evaluate((el) => {
          const root = getComputedStyle(el),
            phone = getComputedStyle(el.querySelector(".phone")),
            button = getComputedStyle(el.querySelector(".fmt"));
          return {
            tokens: ["--bg", "--s1", "--s2", "--ln", "--tx", "--mu", "--ac"].map((key) =>
              root.getPropertyValue(key).trim(),
            ),
            phoneWidth: phone.width,
            phoneRadius: phone.borderRadius,
            formatRadius: button.borderRadius,
          };
        });
        const originalStyle = await reference.locator("body").evaluate((el) => {
          const root = getComputedStyle(document.documentElement),
            phone = getComputedStyle(el.querySelector(".phone")),
            button = getComputedStyle(el.querySelector(".fmt"));
          return {
            tokens: ["--bg", "--s1", "--s2", "--ln", "--tx", "--mu", "--ac"].map((key) =>
              root.getPropertyValue(key).trim(),
            ),
            phoneWidth: phone.width,
            phoneRadius: phone.borderRadius,
            formatRadius: button.borderRadius,
          };
        });
        assert.deepEqual(
          nativeStyle,
          originalStyle,
          "Original tokens and component geometry must match at the same content width: " +
            JSON.stringify({ viewport: width, theme, canvasWidth }),
        );
        await reference.screenshot({
          path: path.join(output, `divulgacao-original-canvas-${width}-${theme}.png`),
          fullPage: true,
        });
        await page.locator(".exact-v4-root").screenshot({
          path: path.join(output, `divulgacao-integrated-canvas-${width}-${theme}.png`),
        });
        await reference.close();
      }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    return "Divulgação V4 original: dock/etapas, edição na prévia, regras locais, mídia/zoom/setas/safe, CRUD/miniatura, backup V4/nativo,14dias, sessão/refresh, cinco larguras/dois temas; nenhum transporte";
  } finally {
    await context.close();
  }
};
