// Real authenticated V8 regression and golden-master comparison, only in the disposable preview.
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const { randomUUID } = require("node:crypto");
module.exports = async (context, origin, client, headers) => {
  assert.equal(origin, "https://127.0.0.1:8443");
  const output = path.resolve(__dirname, "../test-results/exact-v8-v4");
  fs.mkdirSync(output, { recursive: true });
  const page = await context.newPage(),
    errors = [],
    comparisons = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  const midday = new Date();
  midday.setHours(12, 0, 0, 0);
  await page.clock.setFixedTime(midday);
  await page.route("**/*", (route) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
  );
  const settled = async (p) => {
    await p.evaluate(async () => {
      await document.fonts.ready;
      await Promise.allSettled(
        document
          .getAnimations()
          .filter((a) => a.effect?.getTiming().iterations !== Infinity)
          .map((a) => a.finished),
      );
    });
  };
  const enter = async () => {
    await page.goto(origin + "/");
    await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
    await page.evaluate(async () => {
      await SocialMEIProfileSync.ready;
      SocialMEIExperience.enterApp("Oportunidades");
    });
    await page.waitForFunction(() => SocialMEIOpportunityV8Bridge.snapshot().ready);
  };
  const root = page.locator("#opportunityLifecycle");
  const measure = async (p, selector) =>
    p.locator(selector).evaluate((el) => {
      const root = getComputedStyle(el),
        style = (s) => getComputedStyle(el.querySelector(s));
      return {
        tokens: ["--bg", "--sf", "--sf2", "--bd", "--tx", "--mu", "--ac"].map((k) =>
          root.getPropertyValue(k).trim(),
        ),
        columnCount: style(".cf").gridTemplateColumns.split(" ").length,
        illustration: style(".ill2").display,
        title: ["fontSize", "fontWeight", "lineHeight", "letterSpacing"].map((k) => style("h1")[k]),
        form: ["padding", "borderRadius", "backgroundImage", "borderColor"].map(
          (k) => style(".panel.cr")[k],
        ),
        button: ["borderRadius", "backgroundImage", "color", "minHeight"].map(
          (k) => style(".btn.pri.big")[k],
        ),
        views: ["borderRadius", "gridTemplateColumns"].map((k) => style(".views")[k]),
      };
    });
  try {
    await enter();
    assert.equal(await page.locator(".op8-shell,.op8-entry").count(), 0);
    assert.equal(await root.locator(".hero2,.panel.cr,.trkh").count(), 3);
    for (const field of ["opportunityClient", "opportunityInterest", "opportunityTitle"])
      assert.equal(await page.locator('label[for="' + field + '"]').count(), 1);
    await root.locator('[data-commercial-filter="cold"]').click();
    assert(await root.locator(".empty").isVisible());
    assert(
      await root
        .locator('[data-commercial-filter="cold"]')
        .evaluate((el) => el === document.activeElement),
    );
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
    await root.locator("#v8-refresh").click();
    await page.waitForFunction(() => SocialMEIOpportunityV8Bridge.snapshot().totals.open === 3);
    await root.locator('[data-commercial-filter="open"]').click();
    assert.equal(await root.locator(".r").count(), 3);
    await root.locator('.views [data-v="board"]').click();
    assert.equal(await root.locator(".bz").count(), 4);
    assert.equal(await root.locator(".tk").count(), 3);
    const id = await root.locator('[data-zone="warm"] .tk').getAttribute("data-id");
    const token = root.locator('.tk[data-id="' + id + '"]');
    await token.focus();
    await page.keyboard.press("ArrowLeft");
    await page.waitForFunction(
      (id) =>
        SocialMEIOpportunityV8Bridge.snapshot().items.find((r) => r.id === id).interest_level ===
        "cold",
      id,
    );
    assert(
      await token.evaluate((el) => el === document.activeElement),
      "Keyboard focus follows the same persisted token",
    );
    assert.equal(await root.locator('[data-zone="cold"] .tk').count(), 1);
    assert.equal(await root.locator('[data-zone="warm"] .tk').count(), 0);
    await token.press("Enter");
    const card = root.locator('.r[data-id="' + id + '"]');
    assert.equal(await card.locator(".rh").getAttribute("aria-expanded"), "true");
    await card.locator(".vl").fill("350,50");
    await card.locator(".nt").fill("Anotação local fictícia");
    await card.locator('[data-act="note"]').click();
    await card.locator('[data-act="fu"][data-d="1"]').click();
    await root.locator('.views [data-v="week"]').click();
    assert.equal(await root.locator('[data-col="1"] .ch[data-id="' + id + '"]').count(), 1);
    await root.locator('.ch[data-id="' + id + '"]').click();
    await root.locator('.dh[data-col="0"]').click();
    assert.equal(await root.locator('[data-col="0"] .ch[data-id="' + id + '"]').count(), 1);
    await root.locator('.views [data-v="list"]').click();
    assert(await root.locator("#v8-today").isVisible());
    const returned = await context.request.get(origin + "/api/v1/opportunities");
    assert.equal(returned.status(), 200);
    const records = (await returned.json()).items;
    const saved = records.find((row) => row.id === id);
    assert.equal(saved.interest_level, "cold");
    for (const name of ["amount", "date", "note", "v", "f", "n"])
      assert(
        !Object.hasOwn(saved, name),
        "Local planning must not masquerade as API fields: " + name,
      );
    await page.reload();
    await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
    await page.evaluate(async () => {
      await SocialMEIProfileSync.ready;
      SocialMEIExperience.enterApp("Oportunidades");
    });
    await page.waitForFunction(() => SocialMEIOpportunityV8Bridge.snapshot().ready);
    const scope = await page.evaluate(() => SocialMEIOpportunityV8Bridge.snapshot().scope);
    const metadata = await page.evaluate(
      (scope) =>
        JSON.parse(localStorage.getItem("socialmei-op8-local-v1:" + encodeURIComponent(scope))),
      scope,
    );
    assert.equal(metadata.items[id].amount, 350.5);
    assert.equal(metadata.items[id].note, "Anotação local fictícia");
    const viewItems = await page.evaluate(() => {
      const scope = SocialMEIOpportunityV8Bridge.snapshot().scope;
      const metadata =
        JSON.parse(localStorage.getItem("socialmei-op8-local-v1:" + encodeURIComponent(scope)))
          ?.items || {};
      return SocialMEIOpportunityV8Bridge.snapshot().items.map((row) => {
        const local = metadata[row.id] || {};
        return {
          id: row.id,
          c: row.client_name,
          w: row.title,
          i: row.interest_level === "unknown" ? "analysis" : row.interest_level,
          r: row.outcome,
          n: local.note || "",
          v: local.amount || 0,
          f: local.date ? new Date(local.date + "T09:00:00").getTime() : null,
          u: Date.parse(row.updated_at),
          h: [],
        };
      });
    });
    const reference = await context.newPage();
    await reference.emulateMedia({ reducedMotion: "reduce" });
    await reference.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    await reference.addInitScript((items) => {
      localStorage.setItem("smei-opp-v6", JSON.stringify(items));
    }, viewItems);
    for (const width of [320, 390, 768, 1024, 1440]) {
      const height = width === 320 ? 700 : width === 390 ? 844 : 900;
      await page.setViewportSize({ width, height });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((t) => {
          SocialMEIThemes.select(t, { persist: false });
          document.querySelector("#v8-filters")?.scrollTo(0, 0);
          scrollTo(0, 0);
        }, theme);
        await settled(page);
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
          "page overflow " + width,
        );
        for (const control of await root.locator(".cf :is(input,select),.fl").all()) {
          await control.scrollIntoViewIfNeeded();
          const box = await control.boundingBox();
          assert(box.height >= 44, "touch target " + width);
          assert(box.x >= -1 && box.x + box.width <= width + 1, "control fully reachable " + width);
        }
        await page.evaluate(() => {
          document.activeElement?.blur();
          document.querySelector("#v8-filters")?.scrollTo(0, 0);
          scrollTo(0, 0);
        });
        const canvas = Math.round((await root.boundingBox()).width);
        await reference.setViewportSize({ width, height });
        await reference.goto(origin + "/frontend/reference/Oportunidades-V8-original.html");
        await reference.evaluate((t) => (document.documentElement.dataset.theme = t), theme);
        await settled(reference);
        await reference.screenshot({
          path: path.join(output, `oportunidades-original-${width}-${theme}.png`),
          fullPage: true,
        });
        await page.screenshot({
          path: path.join(output, `oportunidades-integrated-${width}-${theme}.png`),
          fullPage: true,
        });
        await reference.setViewportSize({ width: canvas, height });
        await settled(reference);
        const actual = await measure(page, "#opportunityLifecycle"),
          expected = await reference.locator("body").evaluate((el) => {
            const root = getComputedStyle(document.documentElement),
              style = (s) => getComputedStyle(el.querySelector(s));
            return {
              tokens: ["--bg", "--sf", "--sf2", "--bd", "--tx", "--mu", "--ac"].map((k) =>
                root.getPropertyValue(k).trim(),
              ),
              columnCount: style(".cf").gridTemplateColumns.split(" ").length,
              illustration: style(".ill2").display,
              title: ["fontSize", "fontWeight", "lineHeight", "letterSpacing"].map(
                (k) => style("h1")[k],
              ),
              form: ["padding", "borderRadius", "backgroundImage", "borderColor"].map(
                (k) => style(".panel.cr")[k],
              ),
              button: ["borderRadius", "backgroundImage", "color", "minHeight"].map(
                (k) => style(".btn.pri.big")[k],
              ),
              views: ["borderRadius", "gridTemplateColumns"].map((k) => style(".views")[k]),
            };
          });
        assert.deepEqual(
          actual,
          expected,
          "Golden V8 composition tokens/component styles " + width + " " + theme,
        );
        const goldenWrap = reference.locator(".wrap");
        await goldenWrap.screenshot({
          path: path.join(output, `oportunidades-original-canvas-${width}-${theme}.png`),
        });
        await root.screenshot({
          path: path.join(output, `oportunidades-integrated-canvas-${width}-${theme}.png`),
        });
        comparisons.push({ width, theme, canvas, stylesEqual: true });
      }
    }
    await reference.close();
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(output, "opportunities-comparison.json"),
      JSON.stringify(comparisons, null, 2),
    );
    return {
      originalComposition: true,
      authenticatedCRM: true,
      localPlanning: true,
      focus: true,
      goldenComparisons: comparisons.length,
      errors,
    };
  } finally {
    await page.close();
  }
};
