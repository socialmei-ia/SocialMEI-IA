// Real API + SQL in the disposable HTTPS preview; never accepts a remote target.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const { randomUUID } = require("node:crypto");
const { waitForViewportFit, layoutSnapshot } = require("./v22-layout-ready.cjs");
const fs = require("node:fs"),
  path = require("node:path");
const out = path.join(__dirname, "../test-results/v22-integrated");
async function run() {
  const origin = process.env.SOCIALMEI_TEST_PREVIEW_ORIGIN || "https://127.0.0.1:8443";
  assert.match(
    origin,
    /^https:\/\/127\.0\.0\.1:[1-9][0-9]{3,4}$/,
    "Only local disposable preview is accepted",
  );
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  const contexts = [];
  fs.mkdirSync(out, { recursive: true });
  try {
    for (let i = 0; i < 2; i++) {
      const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
      contexts.push(ctx);
      const marker = await ctx.request.get(origin + "/__preview");
      assert.equal((await marker.json()).environment, "local-disposable-preview");
      assert.equal((await ctx.request.get(origin + "/api/v1/clientes")).status(), 401);
      const visitor = await ctx.newPage();
      await visitor.goto(origin + "/");
      await visitor.waitForURL(origin + "/frontend/entrada.html");
      await visitor.close();
      const response = await ctx.request.post(origin + "/api/v1/auth/register", {
        headers: { Origin: origin, "X-SocialMEI-Client": "browser" },
        data: {
          nome: "V22 Test " + i,
          email: `v22-${randomUUID()}@example.test`,
          senha: "Private-V22-test-123!",
        },
      });
      assert.equal(response.status(), 201, await response.text());
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await page.goto(origin + "/?from=root#/oport");
      await page.waitForURL(origin + "/frontend/socialmei-app.html?from=root#/oport");
      await page.waitForFunction(
        () => window.SocialMEIV22?.identity && document.getElementById("app")?.hidden === false,
      );
      await page.evaluate(() => go("/negocio/clientes"));
      assert(!(await page.locator("body").innerText()).includes("Lia Martins"));
      if (i === 0) {
        await page.getByRole("button", { name: "Novo cliente", exact: true }).click();
        await page.locator("#f_n").fill("Cliente exclusivo V22");
        await page.locator("#f_e").fill("cliente-v22@example.test");
        await page.locator("dialog button[type=submit]").click();
        await page.locator("dialog").waitFor({ state: "hidden" });
        let data = await (await ctx.request.get(origin + "/api/v1/clientes")).json();
        assert(data.some((c) => c.nome === "Cliente exclusivo V22"));
        await page.evaluate(() => go("/negocio/produtos"));
        await page.getByRole("button", { name: /Novo produto/ }).click();
        await page.locator("#f_n").fill("Produto real V22");
        await page.locator("#f_p").fill("35,50");
        await page.locator("#f_e").fill("5");
        await page.locator("dialog button[type=submit]").click();
        await page.locator("dialog").waitFor({ state: "hidden" });
        data = await (await ctx.request.get(origin + "/api/v1/produtos")).json();
        assert.equal(data.find((p) => p.nome === "Produto real V22").preco, 35.5);
        await page.evaluate(() => go("/negocio/vendas"));
        await page.getByRole("button", { name: "Nova venda", exact: true }).click();
        await page.locator("dialog button[type=submit]").click();
        await page.locator("dialog").waitFor({ state: "hidden" });
        data = await (await ctx.request.get(origin + "/api/v1/vendas")).json();
        assert.equal(data.length, 1);
        assert.equal(data[0].valor, 35.5);
        await page.reload();
        await page.waitForFunction(
          () => window.SocialMEIV22?.identity && document.getElementById("app")?.hidden === false,
        );
        await page.evaluate(() => go("/negocio/clientes"));
        assert((await page.locator("body").innerText()).includes("Cliente exclusivo V22"));
        await page.evaluate(() => go("/oport"));
        const frame = page.frameLocator("iframe");
        await frame.locator("#client").selectOption({ label: "Cliente exclusivo V22" });
        await frame.locator("#what").fill("Produto real V22");
        await frame.locator("#form button[type=submit]").click();
        await page.waitForFunction(async () => {
          const r = await SocialMEIV22.request("/opportunities");
          return r.items.length === 1;
        });
      } else {
        const data = await (await ctx.request.get(origin + "/api/v1/clientes")).json();
        assert.equal(data.length, 0);
        assert(!(await page.locator("body").innerText()).includes("Cliente exclusivo V22"));
      }
      if (i === 0)
        for (const width of [1440, 768, 390])
          for (const theme of ["claro", "escuro"]) {
            await page.setViewportSize({ width, height: 1000 });
            await waitForViewportFit(page);
            await page.evaluate((t) => {
              S.theme = t;
              applyTheme();
            }, theme);
            for (const route of ["inicio", "negocio/clientes", "oport", "divul", "relatorios"]) {
              await page.evaluate((r) => go("/" + r), route);
              if (["oport", "divul"].includes(route))
                await page.frameLocator("#v iframe").locator("body").waitFor();
              const layout = await layoutSnapshot(page);
              assert.equal(layout.scrollWidth > layout.width + 1, false, JSON.stringify(layout));
              await page.screenshot({
                path: path.join(out, `${route.replace("/", "-")}-${width}-${theme}.png`),
                fullPage: true,
                animations: "disabled",
              });
            }
          }
      assert.deepEqual(errors, []);
    }
    console.log(
      "V22 preview: two real accounts isolated; customer, product, sale, opportunity and reload verified.",
    );
  } finally {
    for (const ctx of contexts) await ctx.close();
    await browser.close();
  }
}
run().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
