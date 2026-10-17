const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const output = path.join(root, "test-results/onboarding-v3");
const model = require("../frontend/scripts/business-profile.js");
const server = http.createServer((req, res) => {
  const file = path.resolve(root, "." + new URL(req.url, "http://localhost").pathname);
  const entry =
    fs.existsSync(file) && fs.statSync(file).isDirectory() ? path.join(file, "index.html") : file;
  if (!entry.startsWith(root + path.sep) || !fs.existsSync(entry)) return res.writeHead(404).end();
  res.setHeader(
    "Content-Type",
    {
      ".html": "text/html",
      ".js": "text/javascript",
      ".css": "text/css",
      ".png": "image/png",
      ".woff2": "font/woff2",
    }[path.extname(entry)] || "application/octet-stream",
  );
  fs.createReadStream(entry).pipe(res);
});
async function run() {
  fs.mkdirSync(output, { recursive: true });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
  });
  const errors = [],
    external = [],
    api = [],
    checks = [];
  let layouts = 0;
  const newPage = async () => {
    const context = await browser.newContext({
      reducedMotion: "reduce",
      viewport: { width: 1440, height: 900 },
    });
    await context.addInitScript(() => {
      Storage.prototype.setItem.call(localStorage, "official-profile-sentinel", "unchanged");
      window.previewWrites = [];
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        window.previewWrites.push(key);
        return original.call(this, key, value);
      };
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) {
        external.push(url.href);
        return route.abort();
      }
      if (/\/(api|auth)\//.test(url.pathname)) {
        api.push(url.pathname);
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(origin + "/experimental/onboarding-v3/");
    await page.evaluate(() => document.fonts.ready);
    return { context, page };
  };
  const snapshot = (page) => page.evaluate(() => SocialMEIOnboardingPreview.snapshot());
  const settled = (page, step) =>
    page.waitForFunction(
      (n) =>
        SocialMEIOnboardingPreview.snapshot().step === n &&
        !document.querySelector("#nextButton").disabled,
      step,
    );
  const next = async (page, step) => {
    await page.locator("#nextButton").click();
    await settled(page, step);
    assert.equal(
      await page.locator("#stageTitle").evaluate((el) => el === document.activeElement),
      true,
    );
  };
  const theme = async (page, value) => {
    if ((await page.locator("html").getAttribute("data-preview-theme")) !== value)
      await page.locator("#themeToggle").click();
  };
  const capture = async (page, label) => {
    for (const width of [320, 360, 390, 768, 1024, 1440])
      for (const color of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 900 });
        await theme(page, color);
        await page.evaluate(() => window.scrollTo(0, 0));
        const geometry = await page.evaluate(() => {
          const footer = document.querySelector(".ob3-footer").getBoundingClientRect();
          const next = document.querySelector("#nextButton").getBoundingClientRect();
          return {
            overflow: document.documentElement.scrollWidth > innerWidth,
            footerTop: footer.top,
            nextBottom: next.bottom,
            nextHeight: next.height,
            height: innerHeight,
          };
        });
        assert(!geometry.overflow, `${label} ${width} ${color}: overflow`);
        if (!(await snapshot(page)).done) {
          assert(geometry.nextBottom <= geometry.height + 1);
          assert(geometry.nextHeight >= 44);
        }
        if (label === "05-ferramentas" && width <= 390) {
          const first = await page.locator(".ob3-tools-options input").first().boundingBox();
          assert(
            first.y + first.height < geometry.footerTop,
            "mobile tool choices must appear before the preview and footer",
          );
        }
        const reachable = await page
          .locator("#stage input")
          .evaluateAll((inputs) =>
            inputs.filter((e) => e.getClientRects().length).map((e) => e.id || e.name),
          );
        if (reachable.length) {
          const last = page.locator("#stage input:visible").last();
          await last.evaluate((e) => e.scrollIntoView({ block: "center" }));
          const bounds = await last.boundingBox();
          const footerTop = await page
            .locator(".ob3-footer")
            .evaluate((e) => e.getBoundingClientRect().top);
          assert(
            bounds.y >= -1 && bounds.y + bounds.height <= footerTop + 1,
            `${label} ${width}: final control reachable above footer`,
          );
          await page.evaluate(() => window.scrollTo(0, 0));
        }
        layouts++;
        if ([390, 1440].includes(width))
          await page.screenshot({
            path: path.join(output, `${label}-${width}-${color}.png`),
            fullPage: false,
            animations: "disabled",
          });
      }
  };
  const useExample = async (page) => {
    await page.getByRole("button", { name: "Usar exemplo", exact: true }).click();
    await next(page, 2);
  };
  const choose = async (page, id, mixed = false) => {
    await page
      .locator("#businessName")
      .fill(id === "other" ? "Oficina de ideias · teste" : model.segments[id].label + " · teste");
    if (id === "other") await page.locator('[data-action="other"]').click();
    else {
      await page.locator("#activitySearch").fill(model.segments[id].label);
      await page.locator(`input[name="segment"][value="${id}"]`).check();
    }
    if (id === "other") {
      await page.locator("#activity").fill("Restauração de móveis");
      await page.locator('input[name="offers"][value="services"]').check();
    }
    if (mixed) await page.locator('input[name="offers"][value="products"]').check();
  };
  try {
    const { page, context } = await newPage();
    await page.locator("#nextButton").click();
    assert.equal(await page.locator("#personName").getAttribute("aria-invalid"), "true");
    await page.setViewportSize({ width: 390, height: 900 });
    await page.screenshot({ path: path.join(output, "estado-validacao-390-light.png") });
    assert.equal(
      await page.locator("#personName").evaluate((e) => e === document.activeElement),
      true,
    );
    await page.getByRole("button", { name: "Usar exemplo", exact: true }).click();
    await capture(page, "01-voce");
    await next(page, 2);
    await page.locator("#businessName").fill("Barbearia da Ana · teste");
    await page.locator("#activitySearch").fill("atividade inexistente xyz");
    await page.locator("#nextButton").click();
    assert.equal(
      await page.locator("#activitySearch").evaluate((e) => e === document.activeElement),
      true,
    );
    assert.match(await page.locator("#segmentFeedback").textContent(), /Escolha/);
    await page.setViewportSize({ width: 390, height: 900 });
    await theme(page, "dark");
    await page.screenshot({ path: path.join(output, "estado-busca-vazia-390-dark.png") });
    await page.locator("#activitySearch").fill("");
    assert.equal(await page.locator("[data-family]").count(), 6);
    await page.locator('[data-family="beauty"]').click();
    await page.locator('input[name="segment"][value="barber"]').focus();
    await page.keyboard.press("Space");
    await page.keyboard.press("ArrowDown");
    assert.equal((await snapshot(page)).profile.segment, "hairdresser");
    await page.keyboard.press("ArrowUp");
    assert.equal((await snapshot(page)).profile.segment, "barber");
    await page.locator('input[name="offers"][value="products"]').check();
    await page.locator(".ob3-optional summary").click();
    await page.locator("#instagram").fill("ana.demo");
    await page.locator("#instagram").blur();
    await page.locator(".ob3-optional summary").click();
    await capture(page, "02-negocio");
    await next(page, 3);
    const service = page.locator('input[name="services"][value="Barba"]');
    await service.focus();
    await page.keyboard.press("Space");
    assert(await service.isChecked());
    await page.locator('input[name="services"][value="Corte masculino"]').check();
    await page.locator('input[name="productCategories"][value="Cosméticos"]').check();
    await page.locator("#servicesCustom").fill("Corte infantil");
    await page.locator("#servicesCustom").press("Enter");
    assert((await snapshot(page)).profile.services.includes("Corte infantil"));
    await capture(page, "03-ofertas");
    await next(page, 4);
    assert.equal(await page.locator('input[name="capabilities"]').count(), 9);
    for (const id of ["appointments", "inventory", "orders", "deliveries", "team"])
      await page.locator(`input[name="capabilities"][value="${id}"]`).check();
    await capture(page, "04-rotina");
    await next(page, 5);
    assert((await snapshot(page)).profile.modules.length <= 5);
    assert(!(await snapshot(page)).profile.modules.some((id) => model.futureFeatures[id]));
    await page.locator(".ob3-future summary").click();
    await page.locator('input[name="modules"][value="appointments"]').check();
    assert(!(await page.locator("#spacePreview").textContent()).includes("Agenda"));
    await page.setViewportSize({ width: 390, height: 900 });
    await page.locator(".ob3-future").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, "estado-recursos-futuros-390-dark.png") });
    await page.locator(".ob3-future summary").click();
    await page.locator('input[name="channels"][value="WhatsApp"]').check();
    await capture(page, "05-ferramentas");
    await next(page, 6);
    assert.match(await page.locator("#stage").textContent(), /@ana.demo/);
    await capture(page, "06-revisao");
    await page.locator('[data-edit="3"]').click();
    await settled(page, 3);
    assert((await snapshot(page)).profile.services.includes("Barba"));
    assert.match(await page.locator("#nextButton").textContent(), /voltar à revisão/);
    await next(page, 6);
    // Required fields must stay protected across revisits and non-linear navigation.
    await page.locator('[data-edit="2"]').click();
    await settled(page, 2);
    await page.locator("#businessName").fill("");
    await page.locator('[data-step="1"]').click();
    await settled(page, 1);
    await page.locator('[data-step="6"]').click();
    await settled(page, 2);
    assert.equal(await page.locator("#businessName").getAttribute("aria-invalid"), "true");
    await page.locator("#businessName").fill("Barbearia da Ana · teste");
    await next(page, 6);
    await page.locator("#nextButton").click();
    assert.equal((await snapshot(page)).done, true);
    assert.equal((await snapshot(page)).profile.completed, true);
    assert.match(await page.locator("#stageTitle").textContent(), /demonstração está pronta/);
    await capture(page, "07-concluido");
    await page.locator('[data-step="2"]').click();
    await settled(page, 2);
    assert.equal((await snapshot(page)).done, false);
    assert(await page.locator("#businessName").isVisible());
    await page.locator('[data-step="6"]').click();
    await settled(page, 6);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.evaluate(() => {
      window.previewAnimations = [];
      const original = Element.prototype.animate;
      Element.prototype.animate = function (frames, options) {
        window.previewAnimations.push({ frames, duration: options.duration });
        return original.call(this, frames, options);
      };
    });
    await page.locator('[data-step="1"]').click();
    await settled(page, 1);
    const motion = await page.evaluate(() => previewAnimations);
    assert.deepEqual(
      motion.map((m) => m.duration),
      [160, 180],
    );
    assert(motion[0].frames[1].transform.includes("8px"));
    await page.evaluate(() => document.querySelector("#nextButton").click());
    assert(
      await page.locator("#resetPreview").isDisabled(),
      "reset cannot race pending navigation",
    );
    await settled(page, 2);
    await page.emulateMedia({ reducedMotion: "reduce" });
    const before = await page.evaluate(() => previewAnimations.length);
    await page.locator('[data-step="3"]').click();
    await settled(page, 3);
    assert.equal(await page.evaluate(() => previewAnimations.length), before);
    assert.equal(
      await page.locator("#progressFill").evaluate((e) => getComputedStyle(e).transitionDuration),
      "0s",
    );
    await page.locator("#resetPreview").click();
    assert(await page.locator("#resetDialog").evaluate((e) => e.contains(document.activeElement)));
    await page.setViewportSize({ width: 320, height: 480 });
    const dialogBounds = await page.locator("#resetDialog").boundingBox();
    assert(
      dialogBounds.x >= 0 && dialogBounds.y >= 0 && dialogBounds.y + dialogBounds.height <= 480,
    );
    await page.screenshot({ path: path.join(output, "estado-reiniciar-320-dark.png") });
    await page.keyboard.press("Escape");
    assert(!(await page.locator("#resetDialog").isVisible()));
    assert.equal(
      await page.locator("#resetPreview").evaluate((e) => e === document.activeElement),
      true,
    );
    await page.locator("#resetPreview").click();
    await page.locator("#confirmReset").click();
    assert.equal((await snapshot(page)).step, 1);
    assert.equal((await snapshot(page)).contact.name, "");
    assert.deepEqual(await page.evaluate(() => window.previewWrites), []);
    assert.equal(
      await page.evaluate(() => localStorage.getItem("official-profile-sentinel")),
      "unchanged",
    );
    checks.push(
      "Fluxo misto, erros, teclado, seis etapas, edição direta, guardas, conclusão, motion e reset",
    );
    await context.close();
    for (const id of ["barber", "perfume", "tailoring", "phoneRepair", "other"]) {
      const { page, context } = await newPage();
      await useExample(page);
      await choose(page, id);
      if (id === "other")
        await page.locator("#businessName").fill("Negócio demonstrativo ".repeat(6).slice(0, 120));
      await next(page, 3);
      if (id === "barber") {
        for (let n = 1; n <= 30; n++) {
          await page.locator("#servicesCustom").fill("Serviço demonstrativo " + n);
          await page.locator('[data-add="services"]').click();
        }
        await page.locator('input[name="services"][value="Barba"]').click();
        assert(!(await page.locator('input[name="services"][value="Barba"]').isChecked()));
        assert.equal((await snapshot(page)).profile.services.length, 30);
      }
      if (id === "other") {
        await page.locator("#servicesCustom").fill('<img src=x onerror="alert(1)">');
        await page.locator('[data-add="services"]').click();
        assert.equal(await page.locator("#stage img").count(), 0);
        assert.match(await page.locator("#servicesChoices").textContent(), /<img/);
        await page.locator("#servicesCustom").fill("Personalização".repeat(6).slice(0, 80));
        await page.locator('[data-add="services"]').click();
        await page.setViewportSize({ width: 320, height: 900 });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      }
      await next(page, 4);
      if (id === "perfume")
        assert.equal(await page.locator('input[value="appointments"]').count(), 0);
      if (["barber", "tailoring", "phoneRepair", "other"].includes(id))
        assert.equal(await page.locator('input[value="inventory"]').count(), 0);
      await page.locator('[data-action="skip"]').click();
      await settled(page, 5);
      await page.locator('[data-action="skip"]').click();
      await settled(page, 6);
      if (id === "other")
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.locator("#nextButton").click();
      assert((await snapshot(page)).done);
      assert.deepEqual(await page.evaluate(() => window.previewWrites), []);
      checks.push(id + ": capacidades condicionais, opcionais e conclusão sem persistir");
      await context.close();
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert.deepEqual(api, []);
    fs.writeFileSync(
      path.join(output, "summary.json"),
      JSON.stringify({ layouts, checks, errors, external, api }, null, 2),
    );
    console.log(
      `${layouts} estados visuais; ${checks.length} cenários passaram; zero erros JS, APIs, requisições externas ou gravações de perfil.`,
    );
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
