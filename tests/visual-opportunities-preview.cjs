// Visual checks use the authenticated disposable preview already verified by the caller.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { execFileSync } = require("node:child_process");
module.exports = async (context, origin, client, headers) => {
  assert.equal(origin, "https://127.0.0.1:8443");
  const output = path.resolve(__dirname, "../test-results/visual-opportunities");
  fs.mkdirSync(output, { recursive: true });
  const errors = [];
  const assertButtonContrast = async (selector) => {
    const ratio = await page.locator(selector).evaluate((button) => {
      const hex = (color) =>
        "#" +
        color
          .match(/[\d.]+/g)
          .slice(0, 3)
          .map((value) => Math.round(Number(value)).toString(16).padStart(2, "0"))
          .join("");
      const style = getComputedStyle(button);
      return SocialMEIThemes.contrast(hex(style.color), hex(style.backgroundColor));
    });
    assert(ratio >= 4.5, `primary action contrast ${selector}: ${ratio}`);
  };
  const page = await context.newPage();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/*", (route) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
  );
  page.on("pageerror", (error) => errors.push(error.message));
  const enter = async () => {
    await page.goto(origin + "/");
    await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
    // Startup restores the view after profile/preferences; navigate only after both have settled.
    await page.evaluate(async () => {
      await SocialMEIAuth.ready;
      await SocialMEIProfileSync.ready;
    });
    await page.evaluate(() => SocialMEIExperience.enterApp("Oportunidades"));
    await page.waitForFunction(() => !document.getElementById("opportunityTitle").disabled);
    await page.evaluate(() => setView("Oportunidades"));
    await page.locator("#opportunitiesView").waitFor({ state: "visible" });
  };
  try {
    if (process.env.SOCIALMEI_VISUAL_BASELINE === "true") {
      const beforeFiles = [
        "styles/visual-workspace-polish.css",
        "scripts/opportunity-lifecycle.js",
      ];
      for (const file of beforeFiles) {
        const body = execFileSync("git", ["show", "a95c0fc:frontend/" + file], {
          encoding: "utf8",
        });
        await page.route("**/" + file, (route) =>
          route.fulfill({
            body,
            contentType: file.endsWith("css") ? "text/css" : "application/javascript",
          }),
        );
      }
      await enter();
      // The old HTML has no illustration or subsection title. Exclude these new hooks from baseline.
      await page
        .locator(".opportunity-hero-art,.opportunity-analysis-intro")
        .evaluateAll((nodes) => nodes.forEach((n) => n.remove()));
      for (const width of [390, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        for (const theme of ["light", "dark"]) {
          await page.evaluate((value) => SocialMEIThemes.select(value, { persist: false }), theme);
          assert.equal(await page.evaluate(() => SocialMEIThemes.current().base), theme);
          await page.evaluate(
            () =>
              new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          await page.evaluate(() => window.scrollTo(0, 0));
          await page.screenshot({
            path: path.join(output, `before-${width}-${theme}.png`),
            fullPage: true,
          });
        }
      }
      for (const file of beforeFiles) await page.unroute("**/" + file);
    }
    await enter();
    const form = page.locator("#opportunityCreateForm");
    assert.deepEqual(
      await form
        .locator("label > :is(input,select)")
        .evaluateAll((nodes) => nodes.map((n) => n.id)),
      [
        "opportunityClient",
        "opportunityInterest",
        "opportunityTitle",
        "op8CreateValue",
        "op8CreateDate",
      ],
    );
    await page.locator('[data-commercial-filter="cold"]').click();
    assert(await page.locator(".commercial-opportunity-empty").isVisible());
    assert(
      await page
        .locator('[data-commercial-filter="cold"]')
        .evaluate((n) => n === document.activeElement),
    );
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((value) => SocialMEIThemes.select(value, { persist: false }), theme);
        assert.equal(await page.evaluate(() => SocialMEIThemes.current().base), theme);
        await page.evaluate(
          () =>
            new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
          `overflow ${width} ${theme}`,
        );
        await assertButtonContrast('#opportunityCreateForm button[type="submit"]');
        const filtersBox = await page
          .locator("#opportunityLifecycle > .opportunity-controls")
          .boundingBox();
        const headingBox = await page.locator("#opportunityLifecycle > h3").boundingBox();
        assert(
          filtersBox.y >= headingBox.y + headingBox.height,
          `filters must follow heading ${width}`,
        );
        for (const item of await page
          .locator(
            "#opportunityCreateForm input,#opportunityCreateForm select,#opportunityLifecycle .opportunity-controls button",
          )
          .all()) {
          const box = await item.boundingBox();
          assert(box.height >= 44, `touch target ${width}`);
          assert(box.x >= 0 && box.x + box.width <= width + 1, `visible control ${width}`);
        }
        if ([390, 768, 1440].includes(width)) await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({
          path: path.join(output, `empty-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('[data-commercial-filter="won"]').click();
    assert.equal(await page.locator("[data-commercial-opportunity]").count(), 1);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(output, "one-1440-dark.png"), fullPage: true });
    for (const interest of ["hot", "warm", "unknown"]) {
      const response = await context.request.post(origin + "/api/v1/opportunities", {
        headers,
        data: {
          operation_id: randomUUID(),
          client_id: client.id,
          title: "Acompanhamento fictício " + interest,
          interest_level: interest,
        },
      });
      assert.equal(response.status(), 201, await response.text());
    }
    await page.getByRole("button", { name: "Atualizar oportunidades", exact: true }).click();
    await page.locator('[data-commercial-filter="open"]').click();
    await page.waitForFunction(
      () => document.querySelectorAll("[data-commercial-opportunity]").length === 3,
    );
    // Native V8 visualizations read the authenticated commercial store; no mock ledger.
    assert.equal(await page.locator("#op8Open").textContent(), "3");
    await page.locator('[data-op8-view="board"]').click();
    assert(await page.locator("#op8Board").isVisible());
    assert.equal(await page.locator("#op8Board .op8-entry").count(), 3);
    await page.locator(".op8-column-warm .op8-entry select").selectOption("cold");
    await page.locator(".op8-column-warm .op8-entry .op8-save").click();
    await page.waitForFunction(
      () =>
        document.getElementById("op8Feedback")?.textContent === "Interesse atualizado para Frio.",
    );
    assert.equal(await page.locator(".op8-column-cold .op8-entry").count(), 1);
    assert.equal(await page.locator(".op8-column-warm .op8-entry").count(), 0);
    assert.equal(await page.locator("#op8Open").textContent(), "3");
    assert(
      await page
        .locator(".op8-column-cold .op8-entry select")
        .evaluate((field) => field === document.activeElement),
      "After changing interest, keyboard focus must follow the same opportunity",
    );
    // Prototype parity: value, follow-up and Semana use scoped browser-only metadata.
    const localCard = page.locator(".op8-column-cold .op8-entry");
    await localCard.locator(".op8-extra summary").click();
    await localCard.locator('input[aria-label^="Valor estimado"]').fill("350,50");
    const today = await page.evaluate(() => {
      const d = new Date();
      return [
        d.getFullYear(),
        String(d.getMonth() + 1).padStart(2, "0"),
        String(d.getDate()).padStart(2, "0"),
      ].join("-");
    });
    await localCard.locator('input[type="date"]').fill(today);
    await localCard.getByRole("button", { name: "Salvar planejamento" }).click();
    assert(await page.locator("#op8DueList").getByText("Acompanhamento fictício warm").isVisible());
    await page.locator('[data-op8-view="week"]').click();
    assert(await page.locator("#op8Week").isVisible());
    assert(
      (await page
        .locator("#op8Week .op8-week-card")
        .filter({ hasText: "Acompanhamento fictício warm" })
        .count()) === 1,
    );
    await page.locator('[data-op8-view="board"]').click();
    await page.locator("#op8Query").fill("Acompanhamento fictício hot");
    assert.equal(await page.locator("#op8Board .op8-entry:visible").count(), 1);
    await page.locator("#op8Query").fill("");
    await page.locator('[data-op8-view="timeline"]').click();
    assert(await page.locator("#op8Timeline").isVisible());
    assert.equal(await page.locator("#op8Timeline .op8-day-list li").count(), 4);
    await page.locator('[data-op8-view="list"]').click();
    assert(await page.locator("#commercialOpportunityList").isVisible());
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((value) => SocialMEIThemes.select(value, { persist: false }), theme);
        assert.equal(await page.evaluate(() => SocialMEIThemes.current().base), theme);
        await page.evaluate(
          () =>
            new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({
          path: path.join(output, `many-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    assert.equal(
      await page
        .locator('[data-commercial-filter="hot"]')
        .evaluate((n) => getComputedStyle(n).transitionDuration),
      "0s",
    );
    // Browser zoom at 200% halves the CSS viewport; CSS `zoom` would not update media queries.
    const zoom = await context.newCDPSession(page);
    await zoom.send("Emulation.setDeviceMetricsOverride", {
      width: 720,
      height: 500,
      deviceScaleFactor: 2,
      mobile: false,
      screenWidth: 1440,
      screenHeight: 1000,
    });
    assert(
      await page.evaluate(
        () => innerWidth === 720 && document.documentElement.scrollWidth <= innerWidth + 1,
      ),
      "200% equivalent viewport must reflow",
    );
    await zoom.send("Emulation.clearDeviceMetricsOverride");
    await zoom.detach();
    await page.evaluate(() => setView("Oportunidades"));
    await page.locator("#opportunityClient").selectOption(String(client.id));
    await page.locator("#opportunityTitle").fill("Novo orçamento de teste V8");
    await page.locator("#op8CreateValue").fill("590,50");
    await page.locator("#op8CreateDate").fill(today);
    await page.locator("#opportunityCreateForm button[type=submit]").click();
    try {
      await page.waitForFunction(() =>
        [...document.querySelectorAll(".op8-entry")].some(
          (card) =>
            card.textContent.includes("Novo orçamento de teste V8") &&
            card.textContent.includes("590,50") &&
            card.textContent.includes("Retomar:"),
        ),
      );
    } catch (error) {
      const diagnostic = await page.evaluate(() => ({
        cards: [...document.querySelectorAll(".op8-entry")].map((card) =>
          card.textContent.slice(0, 180),
        ),
        status: document.querySelector("#opportunityLifecycle [role=status]")?.textContent,
        feedback: document.querySelector("#op8Feedback")?.textContent,
        form: {
          title: document.querySelector("#opportunityTitle")?.value,
          amount: document.querySelector("#op8CreateValue")?.value,
          date: document.querySelector("#op8CreateDate")?.value,
        },
        scope: SocialMEIOpportunityLifecycle?.snapshot?.().scope,
        ids: SocialMEIOpportunityLifecycle?.snapshot?.().items?.map((row) => row.id),
      }));
      throw new Error("V8 create preview never reached persisted-and-local metadata: " +
        JSON.stringify(diagnostic), { cause: error });
    }
    await page.evaluate(() => setView("Divulgação"));
    await page.locator("#contentWorkspace-create").click();
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((value) => SocialMEIThemes.select(value, { persist: false }), theme);
        await page.evaluate(
          () =>
            new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        for (const selector of ["#contentNew", "#contentSave", "#preparationCaptions"])
          await assertButtonContrast(selector);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({
          path: path.join(output, `content-preview-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    }
    assert.deepEqual(errors, []);
    return {
      sizes: [320, 390, 768, 1024, 1440],
      themes: ["light", "dark"],
      states: ["empty", "one", "many"],
      keyboard: true,
      reducedMotion: true,
      zoom: "200% equivalent CSS viewport",
      errors,
    };
  } finally {
    await page.close();
  }
};
