const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function onboarding(browser, origin) {
  const output = path.join(root, "test-results/adaptive-onboarding");
  fs.mkdirSync(output, { recursive: true });
  const errors = [],
    external = [];
  let layouts = 0;
  const next = async (page, step) => {
    await page.locator("[data-onboard-next]").click();
    await page.locator(`[data-onboard-panel="${step}"].is-active`).waitFor();
    assert(
      await page.evaluate(() =>
        document.activeElement?.matches(
          ".onboarding-panel.is-active h1,.onboarding-panel.is-active h2",
        ),
      ),
      "step heading receives keyboard focus",
    );
  };
  const back = async (page, step) => {
    await page.locator("[data-onboard-back]").click();
    await page.locator(`[data-onboard-panel="${step}"].is-active`).waitFor();
  };
  const navigateProfile = async (page) => {
    if (await page.evaluate(() => innerWidth <= 900)) await page.locator("#mb").click();
    await page.locator('#nav [data-nav="Configurações"]').click();
    await page.locator('[data-settings-tab="perfil"]').click();
  };
  const capture = async (page, name) => {
    for (const width of [320, 360, 390, 768, 1024, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        if (await page.locator(".onboarding-screen.is-active").count()) {
          if ((await page.locator("html").getAttribute("data-public-theme")) !== theme)
            await page.locator(".onboarding-screen [data-public-theme-toggle]").click();
          assert.equal(await page.locator("html").getAttribute("data-theme"), theme);
          assert.equal(
            await page
              .locator(".onboarding-screen [data-public-theme-toggle]")
              .getAttribute("aria-label"),
            theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro",
          );
        } else await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
          `${name} ${width} overflow`,
        );
        layouts++;
        if (await page.locator(".onboarding-screen.is-active").count()) {
          const button = await page.locator("[data-onboard-next]").boundingBox();
          assert(
            button && button.y >= 0 && button.y + button.height <= 1001 && button.height >= 44,
            `${name} ${width}: primary action visible`,
          );
          const last = page.locator(".onboarding-panel.is-active input:visible").last();
          if (await last.count()) {
            await last.evaluate((e) => e.scrollIntoView({ block: "center" }));
            const box = await last.boundingBox();
            const footer = await page.locator(".onboarding-footer").boundingBox();
            assert(
              box.y >= 0 && box.y + box.height <= footer.y + 1,
              `${name} ${width}: final field reachable`,
            );
          }
          await page.evaluate(() => scrollTo(0, 0));
        }
        const labels = await page
          .locator(".onboarding-panel.is-active .business-profile-options label")
          .evaluateAll((items) =>
            items.map((item) => ({
              width: item.getBoundingClientRect().width,
              height: item.getBoundingClientRect().height,
            })),
          );
        assert(
          labels.every((item) => item.width >= 80 && item.height >= 44),
          `${name} unreadable choices`,
        );
        if ([390, 1440].includes(width))
          await page.screenshot({
            path: path.join(output, `${name}-${width}-${theme}.png`),
            fullPage: false,
          });
      }
  };
  for (const [segment, label, service, category, mixed] of [
    ["barber", "Barbearia de teste", "Corte masculino", null, false],
    ["hairdresser", "Salão de teste", "Escova", null, false],
    ["phoneRepair", "Assistência de teste", "Troca de tela", null, false],
    ["perfume", "Perfumaria de teste", null, "Perfumes", false],
    ["tailoring", "Ateliê de teste", "Ajustes", null, false],
    ["barber", "Negócio misto de teste", "Barba", "Cosméticos", true],
  ]) {
    const context = await browser.newContext({
      reducedMotion: "reduce",
      viewport: { width: 390, height: 1000 },
    });
    try {
      const page = await context.newPage();
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/*", (route) => {
        if (new URL(route.request().url()).origin !== origin) {
          external.push(route.request().url());
          return route.abort();
        }
        return route.continue();
      });
      await page.goto(origin + "/frontend/socialmei-app.html");
      await page.locator("[data-start-signup]").first().click();
      await page.locator("#registerName").fill("Pessoa sintética");
      await page.locator("#registerEmail").fill(`${segment}${mixed ? "mixed" : ""}@example.com`);
      await page.locator("#registerPhone").fill("11999998888");
      await page.locator("#registerPassword").fill("TesteLocal123!");
      await page.locator("#xpRegisterForm [type=submit]").click();
      const phoneDialog = page.locator(".contact-confirmation");
      await phoneDialog.waitFor({ state: "visible" });
      for (const [width, height] of [
        [390, 560],
        [320, 480],
      ]) {
        await page.setViewportSize({ width, height });
        const bounds = await phoneDialog.boundingBox();
        assert(bounds, "phone confirmation dialog must be visible");
        assert(
          Math.abs(bounds.x + bounds.width / 2 - width / 2) <= 3,
          `phone dialog ${width}x${height} centered horizontally: ${JSON.stringify(bounds)}`,
        );
        assert(
          bounds.y >= 0 && bounds.y + bounds.height <= height + 1,
          `phone dialog ${width}x${height} fits short mobile viewport: ${JSON.stringify(bounds)}`,
        );
        if (segment === "barber" && !mixed)
          await page.screenshot({
            path: path.join(output, `phone-dialog-${width}x${height}.png`),
          });
      }
      await page.setViewportSize({ width: 390, height: 1000 });
      assert.match(await phoneDialog.textContent(), /não envia SMS/i);
      assert(
        await phoneDialog.evaluate((element) => element.contains(document.activeElement)),
        "phone confirmation retains keyboard focus",
      );
      if (segment === "barber" && !mixed) {
        await page.keyboard.press("Escape");
        await phoneDialog.waitFor({ state: "detached" });
        await page.locator("#xpRegisterForm [type=submit]").click();
        await phoneDialog.waitFor({ state: "visible" });
      }
      await page.locator(".contact-confirmation button[value=confirm]").click();
      await page.locator('[data-onboard-panel="1"].is-active').waitFor();
      assert.match(
        await page.locator("#xpOnboardingStepStatus").textContent(),
        /Etapa 1 de 6.*Você.*Negócio/,
      );
      assert.equal(await page.locator("#obName").inputValue(), "Pessoa sintética");
      if (segment === "barber" && !mixed) {
        await page.locator("#obName").fill("");
        await page.locator("[data-onboard-next]").click();
        assert.equal(await page.locator("#obName").getAttribute("aria-invalid"), "true");
        await page.locator("#obName").fill("Pessoa sintética");
        await page.locator("#obName").focus();
        await page.keyboard.press("Tab");
        assert(await page.locator("#obEmail").evaluate((e) => e === document.activeElement));
        await page.keyboard.press("Shift+Tab");
        assert(await page.locator("#obName").evaluate((e) => e === document.activeElement));
        await capture(page, "you");
        await page.setViewportSize({ width: 320, height: 780 });
        await page.evaluate(() => {
          window.onboardTextStyles = [
            ...document.querySelectorAll(
              ".onboarding-screen h1,.onboarding-screen label,.onboarding-screen p,.onboarding-screen button,.onboarding-screen input,.onboarding-screen small",
            ),
          ].map((e) => [e, e.getAttribute("style")]);
          const sizes = onboardTextStyles.map(([e]) => parseFloat(getComputedStyle(e).fontSize));
          onboardTextStyles.forEach(([e], i) => (e.style.fontSize = `${sizes[i] * 2}px`));
        });
        await page.evaluate(
          () =>
            new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
          "200% text stress at 320px must reflow",
        );
        await page.locator("#obPhone").evaluate((e) => e.scrollIntoView({ block: "center" }));
        const zoomPhone = await page.locator("#obPhone").boundingBox();
        const zoomFooter = await page.locator(".onboarding-footer").boundingBox();
        assert(
          zoomPhone.y + zoomPhone.height <= zoomFooter.y + 1,
          "200% text keeps final input reachable",
        );
        await page.screenshot({ path: path.join(output, "text-200-320-dark.png") });
        await page.evaluate(() =>
          onboardTextStyles.forEach(([e, old]) =>
            old === null ? e.removeAttribute("style") : e.setAttribute("style", old),
          ),
        );
        await page.emulateMedia({ reducedMotion: "no-preference" });
        await page.evaluate(() => {
          window.onboardingMotionFrames = [];
          const animate = Element.prototype.animate;
          Element.prototype.animate = function (frames, options) {
            if (this.matches(".onboarding-panel"))
              onboardingMotionFrames.push({ frames, duration: options.duration });
            return animate.call(this, frames, options);
          };
        });
        const started = Date.now();
        await page.evaluate(() => {
          const button = document.querySelector("[data-onboard-next]");
          for (let i = 0; i < 8; i++) button.click();
        });
        assert(await page.locator("[data-onboard-next]").isDisabled());
        await page.setViewportSize({ width: 360, height: 780 });
        await page.waitForFunction(
          () =>
            document.querySelector('[data-onboard-panel="2"]').classList.contains("is-active") &&
            !document.querySelector("[data-onboard-next]").disabled,
        );
        assert.equal(
          await page.locator(".onboarding-panel.is-active").getAttribute("data-onboard-panel"),
          "2",
        );
        const frames = await page.evaluate(() => onboardingMotionFrames);
        assert.deepEqual(
          frames.map((e) => e.duration),
          [160, 180],
        );
        assert(frames[0].frames[1].transform.includes("-8px"));
        fs.writeFileSync(
          path.join(output, "transition-sample.json"),
          JSON.stringify(
            {
              elapsedMs: Date.now() - started,
              durations: frames.map((e) => e.duration),
              note: "One local Chromium sample including viewport resize; not a device performance guarantee.",
            },
            null,
            2,
          ),
        );
        await back(page, 1);
        await page.waitForFunction(() => !document.querySelector("[data-onboard-next]").disabled);
        assert(
          (await page.evaluate(() => onboardingMotionFrames))[2].frames[1].transform.includes(
            "8px",
          ),
        );
        await page.emulateMedia({ reducedMotion: "reduce" });
        await page.setViewportSize({ width: 390, height: 1000 });
      }
      assert.match(
        await page.locator("#businessProfileStorageNotice").textContent(),
        /Nenhuma conta/,
      );
      await next(page, 2);
      assert.match(
        await page.locator("#xpOnboardingStepStatus").textContent(),
        /Etapa 2 de 6.*Negócio.*Ofertas/,
      );
      if (segment === "barber" && !mixed) {
        assert.equal(
          await page.locator('[data-onboard-step="5"]').isDisabled(),
          true,
          "steps not reached must not be clickable",
        );
        assert.equal(
          await page.locator('[data-onboard-step="1"]').isEnabled(),
          true,
          "completed step must be revisitable",
        );
        await page.locator('[data-onboard-step="1"]').focus();
        await page.keyboard.press("Enter");
        await page.locator('[data-onboard-panel="1"].is-active').waitFor();
        await next(page, 2);
        assert.equal(
          await page.locator("#xpOnboardingProgress").getAttribute("aria-valuenow"),
          "2",
        );
        assert.equal(
          await page.locator('[data-onboard-step="2"]').getAttribute("aria-current"),
          "step",
        );
      }
      assert.equal(
        await page
          .locator('#obSegment optgroup[label="Beleza e cuidados"] option[value="hairdresser"]')
          .count(),
        1,
      );
      assert.equal(
        await page
          .locator('#obSegment optgroup[label="Tecnologia e reparos"] option[value="phoneRepair"]')
          .count(),
        1,
      );
      if (segment === "barber" && !mixed) {
        assert.equal(
          await page.locator("#businessFamilyChoices button").count(),
          6,
          "only six business areas should be shown initially",
        );
        assert(!(await page.locator("#businessSpecialtySection").isVisible()));
        await page.locator("#businessSegmentSearch").fill("atividade inexistente xyz");
        await page.locator("[data-onboard-next]").click();
        assert(
          await page
            .locator("#businessSegmentSearch")
            .evaluate((e) => e === document.activeElement),
        );
        await page.locator("#businessSegmentSearch").fill("");
        await page
          .locator('#businessFamilyChoices button[data-family="Beleza e cuidados"]')
          .click();
        assert(await page.locator('#businessSpecialtyChoices input[value="barber"]').isVisible());
        assert(
          await page.locator('#businessSpecialtyChoices input[value="hairdresser"]').isVisible(),
        );
        assert.equal(
          await page.locator('#businessSpecialtyChoices input[value="phoneRepair"]').count(),
          0,
        );
        await page.locator('#businessSpecialtyChoices input[value="hairdresser"]').check();
        assert.equal(await page.locator("#obSegment").inputValue(), "hairdresser");
        await page.locator("#businessSegmentSearch").fill("celular");
        assert(
          await page.locator('#businessSpecialtyChoices input[value="phoneRepair"]').isVisible(),
        );
        assert.equal(
          await page.locator('#businessSpecialtyChoices input[value="barber"]').count(),
          0,
        );
        await page.locator('#businessSpecialtyChoices input[value="phoneRepair"]').check();
        assert.equal(await page.locator("#obSegment").inputValue(), "phoneRepair");
        await page.locator("#businessSegmentSearch").fill("atividade inexistente xyz");
        assert.match(
          await page.locator("#businessSpecialtyEmpty").textContent(),
          /não encontramos/i,
        );
        await page.locator("#businessSegmentSearch").fill("");
        assert.equal(
          await page.locator('#businessFamilyChoices button[aria-pressed="true"]').count(),
          1,
        );
      }
      await page.locator("#obBusiness").fill(label);
      await page.locator("#businessSegmentAlternative").evaluate((el) => (el.open = true));
      await page.locator("#obSegment").selectOption(segment);
      if (segment === "barber" && !mixed) {
        await page.locator(".onboarding-optional").evaluate((e) => (e.open = true));
        await page.locator("#obCnpj").fill("11111111111111");
        await page.locator(".onboarding-optional").evaluate((e) => (e.open = false));
        await page.locator("[data-onboard-next]").click();
        assert(await page.locator(".onboarding-optional").evaluate((e) => e.open));
        assert(await page.locator("#obCnpj").evaluate((e) => e === document.activeElement));
        await page.locator("#obCnpj").fill("");
        await page.locator(".onboarding-optional").evaluate((e) => (e.open = false));
      }
      assert(
        (await page.locator("#businessSegmentHint").textContent()).trim().length >= 20,
        "a segment-specific explanation must be visible",
      );
      if (mixed) await page.locator('input[name="businessOffer"][value="products"]').check();
      const before = await page.evaluate(() =>
        JSON.stringify({
          products: appData.produtos,
          clients: appData.clientes,
          sales: appData.vendas,
        }),
      );
      if (segment === "barber" && !mixed) await capture(page, "business");
      await next(page, 3);
      if (service) await page.getByLabel(service, { exact: true }).check();
      if (category) await page.getByLabel(category, { exact: true }).check();
      assert.equal(
        await page.locator("#businessCustom-productCategories").count(),
        category || segment === "perfume" ? 1 : 0,
      );
      if (segment === "barber" && !mixed) {
        const keyboardChoice = page.getByLabel("Barba", { exact: true });
        await keyboardChoice.focus();
        await page.keyboard.press("Space");
        assert(await keyboardChoice.isChecked());
        await page.keyboard.press("Space");
        assert(!(await keyboardChoice.isChecked()));
        await page.locator("#businessCustom-services").fill("Atendimento em domicílio");
        await capture(page, "offers");
        await page.locator('[data-business-add="services"]').click();
        for (let n = 1; n <= 28; n++) {
          await page.locator("#businessCustom-services").fill(`Extra ${n}`);
          await page.locator('[data-business-add="services"]').click();
        }
        await page.locator("#businessCustom-services").fill("Não descartar silenciosamente");
        await page.locator("[data-onboard-next]").click();
        assert(
          await page.locator('[data-onboard-panel="3"].is-active').count(),
          "pending custom text beyond limit must block navigation",
        );
        assert.equal(
          await page.locator("#businessCustom-services").inputValue(),
          "Não descartar silenciosamente",
        );
        assert.match(await page.locator("#obValidation").textContent(), /30/);
        await page.locator("#businessCustom-services").fill("");
        for (let n = 1; n <= 28; n++)
          await page.locator(`input[name="business-services"][value="Extra ${n}"]`).uncheck();
      }
      if (mixed) {
        for (let n = 1; n <= 29; n++) {
          await page.locator("#businessCustom-productCategories").fill(`Categoria extra ${n}`);
          await page.locator('[data-business-add="productCategories"]').click();
        }
        await page.locator("#businessCustom-productCategories").fill("Categoria pendente 31");
        await page.locator("#businessCustom-services").fill("Serviço pendente");
        await page.locator('[data-business-add="services"]').click();
        assert.equal(
          await page.locator("#businessCustom-productCategories").inputValue(),
          "Categoria pendente 31",
        );
        assert.equal(
          await page.locator("#businessCustom-services").inputValue(),
          "Serviço pendente",
        );
        assert.match(await page.locator("#obValidation").textContent(), /30/);
        await page.locator("#businessCustom-productCategories").fill("");
        await page.locator("#businessCustom-services").fill("");
        for (let n = 1; n <= 29; n++)
          await page
            .locator(`input[name="business-productCategories"][value="Categoria extra ${n}"]`)
            .uncheck();
      }
      await next(page, 4);
      assert.equal(
        await page.locator('input[value="appointments"][name="businessCapability"]').count(),
        segment === "perfume" ? 0 : 1,
      );
      assert.equal(
        await page.locator('input[value="inventory"][name="businessCapability"]').count(),
        category || segment === "perfume" ? 1 : 0,
      );
      if (service)
        await page.locator('input[name="businessCapability"][value="appointments"]').check();
      if (category)
        await page.locator('input[name="businessCapability"][value="inventory"]').check();
      if (segment === "tailoring")
        await page.locator('input[name="businessCapability"][value="orders"]').check();
      if (segment === "barber" && !mixed) await capture(page, "routine");
      await next(page, 5);
      if (service) {
        await page.locator(".business-future summary").click();
        assert(
          !(await page.locator('input[name="businessModule"][value="appointments"]').isChecked()),
          "future tools require explicit interest, not automatic activation",
        );
        await page.locator('input[name="businessModule"][value="appointments"]').check();
      }
      if (category) await page.locator('input[name="businessModule"][value="inventory"]').check();
      if (segment === "barber" && !mixed) {
        await page.locator('input[name="businessModule"][value="reports"]').check();
        await capture(page, "tools");
        await back(page, 4);
        await next(page, 5);
        assert(await page.locator('input[name="businessModule"][value="reports"]').isChecked());
      }
      await next(page, 6);
      assert.match(await page.locator("#xpReadyTitle").textContent(), /quase pronto/i);
      if (segment === "barber" && !mixed)
        assert.match(
          await page.locator("#businessProfileReview").textContent(),
          /Agenda \(em desenvolvimento\)/,
        );
      assert(
        (await page.locator("#xpReadySegment").textContent()).includes(
          await page.locator("#obSegment option:checked").textContent(),
        ),
        "the review must identify the precise selected specialty",
      );
      assert.equal(
        await page.locator(".experience-review-identity #xpReadyBusiness").textContent(),
        label,
      );
      assert.match(
        await page.locator("#xpOnboardingStepStatus").textContent(),
        /Etapa 6 de 6.*Revisão/,
      );
      assert.match(
        await page.locator("#businessProfileReview").textContent(),
        new RegExp(service || category),
      );
      assert.equal(
        await page.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
        null,
        "not saved before confirmation",
      );
      if (segment === "barber" && !mixed) {
        await capture(page, "review");
        await page.locator('[data-review-edit-step="2"]').click();
        await page.locator('[data-onboard-panel="2"].is-active').waitFor();
        await page.locator("#obBusiness").fill("Nome revisado de teste");
        await next(page, 6);
        assert.equal(
          await page.locator("#xpReadyBusiness").textContent(),
          "Nome revisado de teste",
          "direct review return updates business heading",
        );
        await page.locator('[data-review-edit-step="2"]').click();
        await page.locator('[data-onboard-panel="2"].is-active').waitFor();
        await page.locator("#obBusiness").fill(label);
        await next(page, 6);
        await page.locator('[data-review-edit-step="1"]').click();
        await page.locator('[data-onboard-panel="1"].is-active').waitFor();
        await page.locator("#obName").fill("Ana sintética");
        await next(page, 6);
        assert.match(
          await page.locator("#xpReadyTitle").textContent(),
          /Ana/,
          "direct review return updates person greeting",
        );
        await page.locator('[data-review-edit-step="3"]').click();
        await page.locator('[data-onboard-panel="3"].is-active').waitFor();
        assert(await page.getByLabel("Corte masculino", { exact: true }).isChecked());
        await next(page, 6);
        assert.match(await page.locator("#businessProfileReview").textContent(), /Corte masculino/);
        await page.evaluate(() => {
          window.originalProfileSet = Storage.prototype.setItem;
          Storage.prototype.setItem = function (key, value) {
            if (key.startsWith("socialmei-business-profile-v1:")) throw Error("quota");
            return originalProfileSet.call(this, key, value);
          };
        });
        await page.locator("[data-onboard-next]").click();
        assert(await page.locator('[data-onboard-panel="6"]').isVisible());
        assert.match(await page.locator("#obValidation").textContent(), /Não foi possível salvar/);
        await page.evaluate(() => {
          Storage.prototype.setItem = originalProfileSet;
        });
      }
      await page.locator("[data-onboard-next]").click();
      await page.waitForFunction(() => document.body.classList.contains("experience-app"));
      const saved = await page.evaluate(
        () => SocialMEIBusinessProfile.browserRepository().read().profile,
      );
      assert.equal(saved.segment, segment);
      assert.equal(saved.businessName, label);
      if (segment === "barber" && !mixed) await capture(page, "home-after-signup");
      assert.match(await page.locator("#homeProfileContext").textContent(), /serviços|produtos/);
      const tool = service ? "services" : "products";
      await page.locator(`[data-profile-route="${tool}"]`).click();
      assert.match(
        await page.locator("#catalogProfileSuggestions").textContent(),
        new RegExp(service || category),
      );
      await page.evaluate(() => setView("Início"));
      if (service) assert(saved.services.includes(service));
      if (category) assert(saved.productCategories.includes(category));
      assert.equal(
        await page.evaluate(() =>
          JSON.stringify({
            products: appData.produtos,
            clients: appData.clientes,
            sales: appData.vendas,
          }),
        ),
        before,
        "preferences never create business records",
      );
      await navigateProfile(page);
      if (segment === "barber" && !mixed) await capture(page, "settings");
      assert.match(
        await page.locator("#settingsPanel").textContent(),
        /Não criam registros nem ocultam abas/,
      );
      await page.reload();
      await page.waitForFunction(() => document.body.classList.contains("experience-app"));
      assert.deepEqual(
        await page.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
        saved,
      );
      await page.locator('[data-settings-tab="perfil"]').click();
      await page.locator("[data-business-profile-edit]").click();
      await page.locator('[data-onboard-panel="2"].is-active').waitFor();
      await page.locator("#businessSegmentAlternative").evaluate((el) => (el.open = true));
      await page.locator("#obSegment").selectOption("other");
      await page.locator("#obActivity").fill("Atividade manual de teste");
      await page.locator('input[name="businessOffer"][value="services"]').check();
      await page.locator("[data-business-cancel]").click();
      assert.deepEqual(
        await page.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
        saved,
        "cancel does not commit draft",
      );
      await page.locator("[data-business-profile-edit]").click();
      await page.locator("#businessSegmentAlternative").evaluate((el) => (el.open = true));
      await page.locator("#obSegment").selectOption("other");
      await page.locator("#obActivity").fill("Atividade manual de teste");
      await page.locator('input[name="businessOffer"][value="services"]').check();
      await next(page, 3);
      const skippedChoices = await page.evaluate(() => ({
        modules: [...document.querySelectorAll('input[name="businessModule"]:checked')].map(
          (e) => e.value,
        ),
        services: [...document.querySelectorAll('input[name="business-services"]:checked')].map(
          (e) => e.value,
        ),
      }));
      for (const step of [4, 5, 6]) {
        await page.locator("[data-business-skip]").click();
        await page.locator(`[data-onboard-panel="${step}"].is-active`).waitFor();
      }
      await page.locator("[data-onboard-next]").click();
      await page.waitForFunction(() => document.body.classList.contains("experience-app"));
      const edited = await page.evaluate(
        () => SocialMEIBusinessProfile.browserRepository().read().profile,
      );
      assert.equal(edited.activity, "Atividade manual de teste");
      assert.deepEqual(edited.modules, skippedChoices.modules);
      assert.deepEqual(edited.services, skippedChoices.services);
      // Local identities are explicit demo selectors, not authenticated accounts.
      await page.evaluate(() =>
        sessionStorage.setItem("socialmei-business-demo-identity", "another@example.com"),
      );
      assert.equal(
        await page.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
        null,
      );
    } finally {
      await context.close();
    }
  }
  // Authenticated browser preferences follow verified identities and workspace switches.
  const accountContext = await browser.newContext({ reducedMotion: "reduce" });
  try {
    let session = { user: 1, workspace: 10 },
      sessionFailure = false;
    const writes = [];
    const page = await accountContext.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      const request = route.request(),
        url = new URL(request.url());
      if (url.origin !== origin) {
        external.push(url.href);
        return route.abort();
      }
      if (url.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG = {n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"},clientes:{mode:"local"}};',
        });
      if (url.pathname === "/api/v1/auth/session")
        return route.fulfill({
          status: sessionFailure ? 503 : 200,
          json: sessionFailure
            ? { detail: "Sessão indisponível" }
            : session
              ? {
                  usuario: {
                    id: session.user,
                    nome: "Pessoa sintética",
                    email: `user${session.user}@example.com`,
                    telefone: "11999998888",
                  },
                  negocio: {
                    id: session.workspace,
                    slug: `mei-${session.workspace}`,
                    nome: "Negócio sintético",
                    configuracao: {},
                  },
                  papel: "owner",
                  csrf_token: "a".repeat(64),
                }
              : null,
        });
      if (url.pathname === "/api/v1/auth/registration")
        return route.fulfill({ json: { mode: "open" } });
      if (url.pathname.startsWith("/api/")) {
        writes.push(request.method() + " " + url.pathname);
        return route.fulfill({
          status: 501,
          json: { detail: "Nenhuma integração de perfil nesta etapa" },
        });
      }
      return route.continue();
    });
    const waitSession = async () =>
      page.waitForFunction(
        ({ user, workspace }) =>
          window.SocialMEIAuth?.current?.usuario.id === user &&
          SocialMEIAuth.current.negocio.id === workspace &&
          document.body.classList.contains("experience-app"),
        session,
      );
    await page.goto(origin + "/frontend/socialmei-app.html");
    await waitSession();
    assert.equal(
      await page.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
      null,
    );
    await navigateProfile(page);
    await page.locator("[data-business-profile-edit]").click();
    assert(
      await page.locator("#obBusiness").isDisabled(),
      "onboarding does not pretend to rename the server workspace",
    );
    assert.match(
      await page.locator("#businessProfileStorageNotice").textContent(),
      /apenas neste navegador/,
    );
    await page.locator("#businessSegmentAlternative").evaluate((el) => (el.open = true));
    await page.locator("#obSegment").selectOption("barber");
    await next(page, 3);
    await page.getByLabel("Corte masculino", { exact: true }).check();
    await capture(page, "account-offers");
    await next(page, 4);
    await next(page, 5);
    await next(page, 6);
    await page.locator("[data-onboard-next]").click();
    await page.waitForFunction(() => document.body.classList.contains("experience-app"));
    const ownerProfile = await page.evaluate(
      () => SocialMEIBusinessProfile.browserRepository().read().profile,
    );
    assert.equal(ownerProfile.segment, "barber");
    await page.reload();
    await waitSession();
    assert.deepEqual(
      await page.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
      ownerProfile,
    );
    for (const other of [
      { user: 2, workspace: 10 },
      { user: 1, workspace: 11 },
    ]) {
      session = other;
      await page.reload();
      await waitSession();
      assert.equal(
        await page.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
        null,
      );
      assert(
        !(await page
          .locator("body")
          .innerText()
          .then((text) => text.includes("Corte masculino"))),
      );
    }
    session = { user: 1, workspace: 10 };
    await page.reload();
    await waitSession();
    assert.deepEqual(
      await page.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
      ownerProfile,
    );
    for (const failed of [false, true]) {
      session = null;
      sessionFailure = failed;
      await page.reload();
      await page.locator('[data-xp-screen="auth"].is-active').waitFor();
      assert.equal(
        await page.evaluate(() => SocialMEIBusinessProfile.browserRepository().read().profile),
        null,
      );
      assert.equal(
        await page.evaluate(() =>
          SocialMEIBusinessProfile.browserRepository().save({
            completed: true,
            businessName: "No session",
            offers: ["services"],
          }),
        ),
        false,
      );
    }
    assert.deepEqual(writes, [], "preferences must not write backend data");
  } finally {
    await accountContext.close();
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  return `Onboarding adaptativo: 6 cadastros, edição/cancelamento, opcionais, recuperação/isolamento local e autenticado por workspace, sessões ausente/indisponível, falha de armazenamento; ${layouts} estados de layout em 6 larguras claro/escuro`;
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
        ".js": "text/javascript",
        ".css": "text/css",
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
