const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const path = require("node:path");
module.exports = async (browser, origin) => {
  execFileSync(process.execPath, [path.resolve(__dirname, "../tools/package-public-demo.mjs")]);
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage(),
    errors = [],
    external = [],
    writes = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (req) => {
    if (new URL(req.url()).origin !== origin && !req.url().startsWith("data:"))
      external.push(req.url().split("?")[0]);
    if (req.method() !== "GET") writes.push(req.method());
  });
  const base = origin + "/test-results/public-demo/";
  const settle = async () =>
    page.waitForFunction(
      () =>
        document
          .getAnimations()
          .every(
            (a) =>
              a.effect?.getTiming().iterations === Infinity ||
              ["finished", "idle"].includes(a.playState),
          ),
      null,
      { timeout: 10000 },
    );
  try {
    await page.goto(base + "index.html");
    await page.getByRole("link", { name: "Abrir Oportunidades" }).click();
    await page.locator("#client option").nth(1).waitFor({ state: "attached" });
    await page.locator("#client").selectOption({ index: 1 });
    await page.locator("#what").fill("Interesse inteiramente fictício para teste");
    await page.locator("#interest").selectOption("hot");
    await page.locator("#form [type=submit]").click();
    await page.locator("#q").fill("Interesse inteiramente fictício");
    assert.equal(await page.locator("#list .r").count(), 1);
    await page.reload();
    await page.locator("#q").fill("Interesse inteiramente fictício");
    assert.equal(await page.locator("#list .r").count(), 1);
    await page.locator('.views [data-v="board"]').click();
    assert.equal(await page.locator(".bz").count(), 4);
    await page.locator('.views [data-v="week"]').click();
    assert(await page.locator("#vw").isVisible());
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((t) => (document.documentElement.dataset.theme = t), theme);
        await settle();
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
          "V8 public overflow " +
            width +
            " " +
            (await page.evaluate(() =>
              [...document.querySelectorAll("body *")]
                .filter((el) => {
                  const r = el.getBoundingClientRect();
                  return r.width && r.right > innerWidth + 1;
                })
                .slice(0, 12)
                .map((el) => [el.tagName, el.className, el.id, el.getBoundingClientRect().width]),
            )),
        );
      }
    }
    await page.getByRole("link", { name: "Voltar ao laboratório" }).click();
    await page.getByRole("link", { name: "Abrir Divulgação" }).click();
    assert.equal(
      await page.evaluate(() => {
        const injected = document.createElement("script");
        injected.textContent = "window.unapprovedDemoScript = true";
        document.body.append(injected);
        return window.unapprovedDemoScript === true;
      }),
      false,
      "Only the original hashed scripts may execute in the distributed demo",
    );
    await page.locator("#d2 > summary").click();
    await page.locator("#tema").fill("Bastidores fictícios");
    await page.locator("#prod").fill("Serviço demonstrativo");
    await page.locator("#sug").click();
    await page.waitForFunction(() => document.querySelectorAll("#sugs button").length === 3);
    await page.locator("#sugs button").first().click();
    await page.locator("#titulo").fill("Rascunho fictício público");
    await page.locator("#leg").fill("Somente teste, sem divulgação real.");
    const png = await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = 100;
      canvas.height = 200;
      canvas.getContext("2d").fillRect(0, 0, 100, 200);
      return canvas.toDataURL("image/png").split(",")[1];
    });
    await page.locator("#file").setInputFiles({
      name: "ficticio.png",
      mimeType: "image/png",
      buffer: Buffer.from(png, "base64"),
    });
    await page.locator("#media canvas,#media img").waitFor();
    await page.locator("#zoom").fill("1.5");
    await page.locator("#d4 > summary").click();
    await page.locator("#save").click();
    await page.waitForFunction(() =>
      JSON.parse(localStorage.getItem("smei4_d") || "[]").some(
        (d) => d.titulo === "Rascunho fictício público",
      ),
    );
    await page.locator("#week").click();
    await page.waitForFunction(
      () => JSON.parse(localStorage.getItem("smei4_s") || "[]").length === 3,
    );
    assert.equal(await page.locator("#strip .dy").count(), 14);
    await page.locator('#al [data-a="c"]').first().click();
    assert(
      await page.evaluate(() =>
        JSON.parse(localStorage.getItem("smei4_s")).some((job) => job.st === "Cancelado"),
      ),
    );
    await page.locator("#k3").click();
    await page.locator('#cg [data-k="ig"]').click();
    assert(await page.evaluate(() => JSON.parse(localStorage.getItem("smei4_c")).ig));
    await page.reload();
    await page.keyboard.press("2");
    await page.locator("#q").fill("Rascunho fictício público");
    assert.equal(await page.locator("#dg .dc").count(), 1);
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((t) => (document.documentElement.dataset.t = t), theme);
        await settle();
        assert(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
          "V4 public overflow " + width,
        );
      }
    }
    const other = await browser.newContext();
    const clean = await other.newPage();
    await clean.goto(base + "reference/Divulgacao-V4-original.html");
    assert.equal(
      await clean.evaluate(() => localStorage.getItem("smei4_d")),
      null,
      "Another browser context has no previous drafts",
    );
    await other.close();
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert.deepEqual(writes, []);
    return "Public static candidate: links, local CRUD/reload, four widths/themes, isolated browser storage, zero external requests or writes";
  } finally {
    await context.close();
  }
};
