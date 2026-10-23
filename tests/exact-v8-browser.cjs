const assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path");
module.exports = async function exactV8(browser, origin) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
    hasTouch: true,
  });
  const fixture = require("./opportunities-v8-fixture.cjs")();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await fixture.install(page, origin);
  await fixture.seedPlanning(page);
  const enter = async () => {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
    await page.evaluate(async () => {
      await SocialMEIProfileSync.ready;
      SocialMEIExperience.enterApp("Oportunidades");
    });
    await page.waitForFunction(
      () =>
        !!document.getElementById("opportunityClient")?.options.length &&
        !document.getElementById("opportunityTitle").disabled,
    );
  };
  const root = page.locator("#opportunityLifecycle");
  try {
    await enter();
    assert.equal(await root.locator(".hero2").count(), 1);
    assert.equal(await page.locator(".op8-shell").count(), 0);
    assert.equal(await root.locator(".r").count(), 4);
    await root.locator('[data-commercial-filter="cold"]').click();
    assert.equal(await root.locator(".r").count(), 1);
    await root.locator('[data-commercial-filter="open"]').click();
    await root.locator("#v8-q").fill("Troca de tela");
    assert.equal(await root.locator(".r").count(), 1);
    await root.locator("#v8-q").fill("");
    await root.locator('.views [data-v="board"]').click();
    assert.equal(await root.locator(".bz").count(), 4);
    assert.equal(await root.locator(".tk").count(), 4);
    const cold = fixture.rows.find((r) => r.interest_level === "cold"),
      token = root.locator('.tk[data-id="' + cold.id + '"]');
    await token.focus();
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction(
      (id) =>
        SocialMEIOpportunityV8Bridge.snapshot().items.find((r) => r.id === id).interest_level ===
        "warm",
      cold.id,
    );
    assert.equal(fixture.rows.find((r) => r.id === cold.id).interest_level, "warm");
    assert(
      await token.evaluate((el) => el === document.activeElement),
      "Arrow movement must keep focus on the same circular token",
    );
    await root.locator('.views [data-v="week"]').click();
    const chip = root.locator('.ch[data-id="' + cold.id + '"]');
    await chip.tap();
    await root.locator('.dh[data-col="1"]').tap();
    assert.equal(await root.locator('[data-col="1"] .ch[data-id="' + cold.id + '"]').count(), 1);
    await root.locator('.views [data-v="list"]').click();
    const row = root.locator('.r[data-id="' + cold.id + '"]');
    await row.locator(".rh").click();
    await row.locator(".nt").fill("Texto humano preservado");
    await row.locator(".vl").fill("990,50");
    await row.locator('[data-act="note"]').click();
    assert.equal(await row.locator(".nt").inputValue(), "Texto humano preservado");
    const writesBefore = fixture.writes.length;
    fixture.setConflict(true);
    await row.locator('[data-act="int"][data-v="hot"]').click();
    await page.waitForFunction(() =>
      document.getElementById("v8-status").textContent.includes("Conflito sintético"),
    );
    assert.equal(fixture.writes.length, writesBefore + 1);
    assert.equal(await row.locator(".nt").inputValue(), "Texto humano preservado");
    assert.equal(fixture.rows.find((r) => r.id === cold.id).interest_level, "warm");
    await row.locator('[data-act="closef"]').click();
    await row.locator('[data-act="close"]').click();
    await page.waitForFunction(
      (id) =>
        SocialMEIOpportunityV8Bridge.snapshot().items.find((r) => r.id === id).outcome === "won",
      cold.id,
    );
    await root.locator('[data-commercial-filter="won"]').click();
    const won = root.locator('.r[data-id="' + cold.id + '"]');
    if ((await won.locator(".rh").getAttribute("aria-expanded")) === "false")
      await won.locator(".rh").click();
    await won.locator('[data-act="reopenf"]').click();
    await won.locator('[data-act="reopen"]').click();
    assert.match(await root.locator("#v8-status").textContent(), /justificativa/);
    await won.locator('[data-box="rf"] input').fill("Cliente voltou a conversar");
    await won.locator('[data-act="reopen"]').click();
    await page.waitForFunction(
      (id) =>
        SocialMEIOpportunityV8Bridge.snapshot().items.find((r) => r.id === id).outcome === "open",
      cold.id,
    );
    await root.locator('[data-commercial-filter="open"]').click();
    await page.keyboard.press("Control+k");
    await root.locator("#v8-ci").fill("Cliente: Ana");
    assert.equal(await root.locator('#v8-cl [role="option"]').count(), 1);
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#opportunityClient").inputValue(), "1");
    await page.locator("#opportunityTitle").fill("Novo interesse confirmado");
    await root.locator(".mo summary").click();
    await root.locator("#v8-val").fill("350,50");
    await root.locator("#v8-fup").selectOption("3");
    await root.locator('button[type="submit"]').click();
    await page.waitForFunction(() =>
      [...document.querySelectorAll("#commercialOpportunityList .who small")].some(
        (e) => e.textContent === "Novo interesse confirmado",
      ),
    );
    assert.equal(fixture.rows.filter((r) => r.title === "Novo interesse confirmado").length, 1);
    assert(
      fixture.writes.every(
        (w) =>
          (!("amount" in w.body) && !("date" in w.body) && !("note" in w.body)) ||
          w.path.endsWith("/close"),
      ),
    );
    const output = path.resolve(__dirname, "../test-results/exact-v8-v4");
    fs.mkdirSync(output, { recursive: true });
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((t) => SocialMEIThemes.select(t, { persist: false }), theme);
        await page.evaluate(() => scrollTo(0, 0));
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
          "overflow " + width,
        );
        await page.screenshot({
          path: path.join(output, `v8-integrated-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    }
    fixture.identity.papel = "viewer";
    await page.reload();
    await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
    await page.evaluate(() => SocialMEIExperience.enterApp("Oportunidades"));
    await page.waitForFunction(() => SocialMEIOpportunityV8Bridge.snapshot().ready);
    assert(await page.locator("#opportunityTitle").isDisabled());
    fixture.identity.negocio = { id: 202, slug: "outro", nome: "Outro negócio", configuracao: {} };
    fixture.identity.papel = "owner";
    await page.reload();
    await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
    await page.evaluate(() => SocialMEIExperience.enterApp("Oportunidades"));
    await page.waitForFunction(() => SocialMEIOpportunityV8Bridge.snapshot().ready);
    assert.equal(await root.locator(".r").count(), 0);
    assert(!(await root.textContent().then((t) => t.includes("Texto humano preservado"))));
    assert.deepEqual(errors, []);
    return "V8 exata: filtros, lista, fichas/setas, semana/toque, planejamento, conflito, fechar/reabrir, comandos, criação, viewer e isolamento; 320/390/768/1440 claro/escuro";
  } finally {
    await page.close();
  }
};
