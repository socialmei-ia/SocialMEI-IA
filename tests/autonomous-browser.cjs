const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const server = http.createServer((request, response) => {
  const file = path.resolve(root, "." + new URL(request.url, "http://local").pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404).end();
    return;
  }
  response.setHeader(
    "Content-Type",
    { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2" }[
      path.extname(file)
    ] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(response);
});
async function run() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  const errors = [],
    external = [];
  try {
    let page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: "reduce",
    });
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) {
        external.push(url.origin);
        return route.abort();
      }
      if (url.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "text/javascript",
          body: "const SOCIALMEI_CONFIG={n8nMessagesUrl:null};",
        });
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Caixa Unificada"));
    const first = page.locator("#conversationList [data-conversation]").first();
    const id = await first.getAttribute("data-conversation");
    await first.click();
    await page.locator("#messageInput").fill("Rascunho de revisão, sem envio");
    assert(
      (await page.locator(`[data-conversation="${id}"] .preview-text`).textContent()).startsWith(
        "Rascunho:",
      ),
    );
    await page.locator("#conversationList [data-conversation]").nth(1).click();
    await page.locator(`#conversationList [data-conversation="${id}"]`).click();
    assert.equal(
      await page.locator("#messageInput").inputValue(),
      "Rascunho de revisão, sem envio",
    );
    await page.locator("#sendMessage").click();
    assert((await page.locator(".msg.out").last().textContent()).includes("não enviada"));
    assert(
      !(await page.locator(`[data-conversation="${id}"] .preview-text`).textContent()).startsWith(
        "Rascunho:",
      ),
    );
    await page.evaluate(() => setView("Assistente"));
    await page.locator("[data-ai-conversation]").first().click();
    await page.locator("[data-ai-intent=reply]").click();
    await page.locator("[data-ai-prepare]").first().click();
    await page.locator(".assistant-edit summary").click();
    await page
      .locator("#assistantDraftEditor")
      .fill("Texto revisado pelo empreendedor, sem envio.");
    assert.equal(
      await page.locator(".assistant-draft-text").textContent(),
      "Texto revisado pelo empreendedor, sem envio.",
    );
    const beforeInsert = await page.evaluate(() =>
      sessionData.conversas.reduce((n, c) => n + c.mensagens.length, 0),
    );
    await page.locator("[data-ai-insert]").click();
    assert(
      (await page.locator("#messageInput").inputValue()).includes(
        "Texto revisado pelo empreendedor, sem envio.",
      ),
    );
    assert.equal(
      await page.evaluate(() => sessionData.conversas.reduce((n, c) => n + c.mensagens.length, 0)),
      beforeInsert,
    );
    await page.evaluate(() => setView("Automações"));
    assert(
      (await page.locator(".automation-integration-state").textContent()).includes("Não conectada"),
    );
    await page.locator("#automationFeature [data-rule-test]").click();
    assert.match(await page.locator("#nvManagementDrawerTitle").innerText(), /simulado/);
    await page.keyboard.press("Escape");
    const output = path.join(root, "test-results/autonomous");
    fs.mkdirSync(output, { recursive: true });
    console.log(await require("./mobile-refinement-browser.cjs")(browser, origin));
    let appLayouts = 0;
    for (const width of [320, 360, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => setTheme(theme), theme);
        for (const view of ["Relatórios", "Caixa Unificada", "Assistente", "Automações"]) {
          await page.evaluate((view) => setView(view), view);
          if (view === "Caixa Unificada")
            await page.locator("#conversationList [data-conversation]").first().click();
          await page.evaluate(
            () =>
              new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          assert.equal(await page.locator(".page-view.active").getAttribute("data-view"), view);
          assert(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
            `${view}/${width}/${theme}: overflow`,
          );
          if ([390, 1440].includes(width)) {
            await page.evaluate(() =>
              document.querySelectorAll(".toast").forEach((toast) => toast.remove()),
            );
            await page.screenshot({
              path: path.join(
                output,
                `app-${["Relatórios", "Caixa Unificada", "Assistente", "Automações"].indexOf(view)}-${width}-${theme}.png`,
              ),
              fullPage: true,
            });
          }
          appLayouts++;
        }
      }
    }
    console.log(`${appLayouts} layouts das quatro experiências alteradas passaram.`);
    await page.close();
    const demoContext = await browser.newContext({ reducedMotion: "reduce" });
    page = await demoContext.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      if (new URL(route.request().url()).origin === origin) return route.continue();
      external.push(route.request().url());
      return route.abort();
    });
    console.log(await require("./intent-browser.cjs")(browser, origin));
    let demoLayouts = 0;
    for (const demo of ["opportunities", "onboarding"]) {
      await page.goto(origin + `/prototypes/${demo}/index.html`);
      for (const width of [320, 360, 390, 768, 1024, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        for (const theme of ["light", "dark"]) {
          if ((await page.locator("html").getAttribute("data-theme")) !== theme)
            await page.locator("#theme").click();
          assert(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
            `${demo}/${width}/${theme}: overflow`,
          );
          if ([390, 1440].includes(width))
            await page.screenshot({
              path: path.join(output, `${demo}-${width}-${theme}.png`),
              fullPage: true,
            });
          demoLayouts++;
        }
      }
      await page.setViewportSize({ width: 390, height: 900 });
      if (demo === "opportunities") {
        await page.locator("#manual-library > summary").click();
        assert.equal(await page.locator("[data-open]").count(), 6);
        assert(
          !(await page
            .locator("main")
            .textContent()
            .then((text) => /\d+%/.test(text))),
        );
        await page.locator("#search").fill("hidratacao");
        assert.equal(await page.locator("[data-open]").count(), 1);
        await page.locator("#search").fill("sem-resultado");
        await page.locator("#clear").click();
        await page.locator("#signal").selectOption("explicit");
        assert.equal(await page.locator("[data-open]").count(), 2);
        await page.locator("[data-view=board]").click();
        await page.locator("[data-open=ana]").click();
        await page.locator("#stage").selectOption("Proposta enviada");
        await page.locator("#prepare").click();
        await page.locator("#draft").fill("Retorno sintético <img src=x>, não enviado");
        await page.locator("#save-draft").click();
        assert((await page.locator("#detail-status").textContent()).includes("Nada foi enviado"));
        await page.locator("[data-panel=client]").click();
        assert((await page.locator("#detail-content").textContent()).includes("Proposta enviada"));
        await page.locator("[data-panel=conversation]").click();
        assert.equal(
          await page.locator("#draft").inputValue(),
          "Retorno sintético <img src=x>, não enviado",
        );
        assert.equal(await page.locator("#detail-content img").count(), 0);
        await page.screenshot({
          path: path.join(output, "opportunities-context-390-dark.png"),
          fullPage: true,
        });
        await page.keyboard.press("Escape");
        assert(
          await page.locator("[data-open=ana]").evaluate((el) => el === document.activeElement),
        );
        await page.locator("#reset").click();
        assert.equal(await page.locator("[data-open]").count(), 6);
      } else {
        await page.locator("#next").click();
        assert((await page.locator("#validation").textContent()).includes("Escolha"));
        for (const profile of ["perfume", "grocery", "barber", "tailor", "repair", "other"]) {
          await page.locator("#" + profile).check();
          await page.locator("#next").click();
          assert(await page.locator(profile === "barber" ? "#services" : "#products").isChecked());
          await page.locator("#area").fill("Bairro demonstrativo <sem HTML>");
          await page.locator("#next").click();
          const config = JSON.parse(await page.locator("#config-preview").textContent());
          assert.equal(config.demo, true);
          assert.equal(config.businessProfile, profile);
          assert.equal(config.integrationsEnabled, false);
          assert.deepEqual(config.core, ["Clientes", "Vendas", "Financeiro", "Relatórios"]);
          assert(config.defaults.serviceArea.includes("<sem HTML>"));
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          if (profile === "barber") {
            const downloadPromise = page.waitForEvent("download");
            await page.locator("#download").click();
            const file = await downloadPromise;
            assert.equal(
              JSON.parse(fs.readFileSync(await file.path(), "utf8")).businessProfile,
              "barber",
            );
            await page.screenshot({
              path: path.join(output, "onboarding-review-390-dark.png"),
              fullPage: true,
            });
            await page.locator("#back").click();
            await page.locator("#products").check();
            await page.locator("#stock").check();
            await page.locator("#next").click();
            const adjusted = JSON.parse(await page.locator("#config-preview").textContent());
            assert(
              adjusted.capabilities.products &&
                adjusted.capabilities.services &&
                adjusted.capabilities.inventory,
            );
          }
          await page.locator("#restart").click();
        }
      }
      assert.equal(
        await page.evaluate(() => localStorage.length),
        0,
        "Demonstrações não persistem estado do app",
      );
    }
    console.log(
      `${demoLayouts} layouts dos protótipos passaram; busca, filtros, etapas, diálogo, rascunhos, seis perfis, ajustes e JSON passaram.`,
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "Atendimento, edição do Assistente e simulação de Automações passaram, sem envio externo.",
    );
  } finally {
    await browser.close();
    server.close();
  }
}
run().catch((error) => {
  console.error(error);
  server.close();
  process.exitCode = 1;
});
