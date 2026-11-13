const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const output = path.join(root, "test-results/functional-polish");
fs.mkdirSync(output, { recursive: true });
const server = http.createServer((req, res) => {
  const file = path.resolve(root, "." + new URL(req.url, "http://local").pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
    return res.writeHead(404).end();
  res.setHeader(
    "Content-Type",
    { ".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".woff2": "font/woff2" }[
      path.extname(file)
    ] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(res);
});
async function run() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  const errors = [];
  try {
    const page = await browser.newPage({ reducedMotion: "reduce" });
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    for (const width of [390, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(origin + "/frontend/entrada.html");
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => (document.documentElement.dataset.theme = theme), theme);
        await page.locator('[data-f="dinheiro"]').click();
        assert.match(await page.locator("#stage").innerText(), /Saldo/);
        await page.locator('[data-f="clientes"]').click();
        assert.match(await page.locator("#stage").innerText(), /Lembrete/);
        const faq = page.locator(".faq").first();
        await faq.locator("summary").focus();
        await page.keyboard.press("Enter");
        assert.equal(await faq.evaluate((el) => el.open), true);
        await page.keyboard.press("Enter");
        assert.equal(await faq.evaluate((el) => el.open), false);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: path.join(output, `landing-${width}-${theme}.png`) });
      }
    }
    await page.goto(origin + "/frontend/entrada.html");
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.locator('[data-f="vendas"]').click();
    assert.match(await page.locator("#stage").innerText(), /Venda #1042/);
    await page.locator('.cmd a[href="#/cadastro"]').click();
    await page.locator("#v-auth").waitFor({ state: "visible" });
    assert.equal(await page.locator("#v-auth").isVisible(), true);
    assert.deepEqual(errors, []);
    await page.close();

    const app = await browser.newPage({ reducedMotion: "reduce" });
    app.on("pageerror", (error) => errors.push(error.message));
    await app.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    await app.route("**/scripts/v22-frame.js", (route) =>
      route.fulfill({
        contentType: "text/javascript",
        body: `window.testLoads=0; window.testWrites=0; window.testRelease=null; window.testFailure=false; window.testEmpty=false;
        window.V22Frame={remote:true,clients:[{nome:'Cliente teste'}],persist:async function(){testWrites++;throw Error('Unexpected write');},history:async function(){return [];},
        load:async function(){testLoads++;if(testLoads===1)await new Promise(r=>testRelease=r);
        if(testFailure)throw Error('Falha controlada');return testEmpty?[]:[{id:'test-1',c:'Cliente teste',w:'Serviço teste',i:'hot',r:'open',n:'',u:Date.now(),f:null,v:100,h:[]}];}};`,
      }),
    );
    await app.goto(origin + "/frontend/telas/oportunidades.html?embed=1");
    await app.waitForFunction(
      () => document.getElementById("list").getAttribute("aria-busy") === "true",
    );
    assert.match(await app.locator("#sum").innerText(), /Carregando/);
    assert.match(await app.locator("#list").innerText(), /Carregando oportunidades/);
    assert.equal(await app.locator("#client").isDisabled(), true);
    await app.evaluate(() => testRelease());
    await app.waitForFunction(
      () => document.getElementById("list").getAttribute("aria-busy") === "false",
    );
    assert.match(await app.locator("#list").innerText(), /Cliente teste/);
    for (const width of [390, 1024, 1440]) {
      await app.setViewportSize({ width, height: 900 });
      for (const theme of ["light", "dark"]) {
        await app.evaluate((theme) => (document.documentElement.dataset.theme = theme), theme);
        assert(await app.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await app.screenshot({ path: path.join(output, `opportunities-${width}-${theme}.png`) });
      }
    }
    await app.evaluate(() => (testFailure = true));
    await app.locator("#refresh").click();
    await app.waitForFunction(() =>
      document.getElementById("sum").textContent.includes("Consulta indisponível"),
    );
    assert.equal(await app.locator("#client").isDisabled(), true);
    assert.match(await app.locator("#list").innerText(), /Cliente teste/);
    await app.locator('#list [data-act="tog"]').click();
    await app.locator('#list [data-act="fu"]').first().click();
    assert.match(
      await app.locator("#toast").innerText(),
      /Atualize as oportunidades antes de alterar/,
    );
    assert.equal(await app.evaluate(() => testWrites), 0);
    await app.evaluate(() => (testFailure = false));
    await app.locator("#refresh").click();
    await app.waitForFunction(() => !document.getElementById("client").disabled);
    assert.equal(await app.evaluate(() => testLoads), 3);
    await app.evaluate(() => (testEmpty = true));
    await app.locator("#refresh").click();
    await app.waitForFunction(() => document.querySelector("#list .empty"));
    assert.match(await app.locator("#list").innerText(), /Nenhuma oportunidade em andamento/);
    await app.evaluate(() => (testFailure = true));
    await app.locator("#refresh").click();
    await app.waitForFunction(
      () => document.querySelector("#list h4").textContent === "Consulta indisponível",
    );
    assert.equal(await app.locator('#list [data-act="focus"]').count(), 0);
    assert.deepEqual(errors, []);
    console.log(
      "Landing: 3 widths × 2 themes, FAQ keyboard, filters, reduced motion, signup; Opportunities: loading, failure and recovery passed.",
    );
  } finally {
    await browser.close();
    server.close();
  }
}
module.exports = run;
if (require.main === module)
  run().catch((error) => {
    console.error(error);
    server.close();
    process.exitCode = 1;
  });
