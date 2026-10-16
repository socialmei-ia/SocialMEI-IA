const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const resultDirectory = path.join(root, "test-results");
const contentTypes = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".png": "image/png",
  ".woff2": "font/woff2",
};
const server = http.createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const file = path.resolve(root, "." + (pathname === "/" ? "/index.html" : pathname));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404).end();
    return;
  }
  response.setHeader(
    "Content-Type",
    contentTypes[path.extname(file)] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(response);
});

async function run() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  let browser;
  const checks = [];
  const errors = [];
  try {
    browser = await chromium.launch(
      process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
    );
    checks.push(await require("./account-browser.cjs")(browser, origin));
    checks.push(await require("./native-opportunities-browser.cjs")(browser, origin));
    checks.push(await require("./adaptive-onboarding-browser.cjs")(browser, origin));
    checks.push(await require("./personalization-browser.cjs")(browser, origin));
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: "reduce",
      acceptDownloads: true,
    });
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    await page.clock.setFixedTime(new Date("2026-10-10T12:00:00Z"));
    await page.goto(origin + "/");
    await page.waitForURL("**/frontend/socialmei-app.html");
    await page.evaluate(() => document.fonts.ready);

    await page.locator("[data-start-signup]").first().click();
    await page.locator("#registerName").fill("Pessoa de Teste");
    await page.locator("#registerEmail").fill("teste@example.com");
    await page.locator("#registerPhone").fill("11999998888");
    await page.locator("#registerPassword").fill("TesteLocal123!");
    await page.locator("#xpRegisterForm [type=submit]").click();
    await page.locator(".contact-confirmation button[value=confirm]").click();
    await page.locator("[data-onboard-next]").click();
    await page.locator("#obBusiness").fill("Negócio QA");
    await page.locator("#obSegment").selectOption("barber");
    for (let step = 3; step <= 6; step++) {
      await page.locator("[data-onboard-next]").click();
      await page.locator(`[data-onboard-panel="${step}"].is-active`).waitFor();
    }
    await page.locator("[data-onboard-next]").click();
    await page.waitForFunction(() => document.body.classList.contains("experience-app"));
    checks.push("Landing, cadastro local e onboarding");
    assert.deepEqual(
      await page.evaluate(() => ({
        remote: SocialMEIAuth.remote,
        conversations: sessionData.conversas.length,
        activity: sessionData.atividade.length,
        notifications: sessionData.notificacoes.length,
      })),
      { remote: false, conversations: 4, activity: 6, notifications: 3 },
    );

    const data = () => page.evaluate(() => JSON.parse(JSON.stringify(appData)));
    const initial = await data();
    await page.evaluate(() => openCreate("cliente"));
    await page.locator("#f_nome").fill("Cliente QA");
    await page.locator("#f_telefone").fill("11999990000");
    await page.locator("#createSubmit").click();
    assert.equal((await data()).clientes.length, initial.clientes.length + 1);
    await page.evaluate(() => openCreate("produto"));
    for (const [field, value] of Object.entries({
      f_nome: "Produto QA",
      f_preco: "50",
      f_custo: "10",
      f_estoque: "10",
      f_minimo: "2",
    }))
      await page.locator("#" + field).fill(value);
    const productsBeforeValidation = (await data()).produtos.length;
    for (const field of ["preco", "custo"]) {
      await page.locator("#f_" + field).fill("12.345");
      await page.locator("#createSubmit").click();
      assert.equal((await data()).produtos.length, productsBeforeValidation);
      assert.match(
        await page.locator("#f_" + field).evaluate((e) => e.validationMessage),
        /duas casas/,
      );
      await page.locator("#f_" + field).fill(field === "preco" ? "50.000" : "10.000");
    }
    await page.locator("#createSubmit").click();
    await page.evaluate(() => openCreate("venda"));
    for (const [field, value] of Object.entries({
      f_cliente: "Cliente QA",
      f_item: "Produto QA",
      f_preco: "50",
      f_quantidade: "2",
    }))
      await page.locator("#" + field).fill(value);
    await page.locator("#createSubmit").click();
    assert.equal((await data()).vendas[0].valor, 100);
    await page.evaluate(() => openCreate("receita"));
    await page.locator("#f_descricao").fill("Receita QA");
    await page.locator("#f_valor").fill("100");
    await page.locator("#createSubmit").click();
    await page.evaluate(() => openClient(appData.clientes[0]));
    await page.locator("#clientModalBody [data-review-edit=clients]").click();
    await page.locator("#f_nome").fill("Cliente QA atualizado");
    await page.locator("#createSubmit").click();
    assert.equal((await data()).clientes[0].nome, "Cliente QA atualizado");
    await page.evaluate(() => closeModal("clientModal"));
    await page.evaluate(() => setView("Clientes"));
    await page.locator("#clientsSearch").fill("nome-inexistente");
    await page.waitForTimeout(250);
    assert((await page.locator("#clientsView").innerText()).includes("Nenhum"));
    await page.locator("#clientsSearch").fill("");
    checks.push("CRUD, drawer e busca vazia");

    await page.evaluate(() => {
      setView("Caixa Unificada");
      selectConversation(1);
    });
    await page.locator("#messageInput").fill("Rascunho QA");
    await page.evaluate(async () => {
      saveCurrentDraft();
      await selectConversation(2);
      await selectConversation(1);
    });
    assert.equal(await page.locator("#messageInput").inputValue(), "Rascunho QA");
    const messageCount = await page.evaluate(() => sessionData.conversas[0].mensagens.length);
    await page.evaluate(() => setView("Assistente"));
    await page.locator('[data-ai-conversation="1"]').click();
    await page.locator("[data-ai-prepare]").click();
    await page.locator("[data-ai-insert]").first().click();
    assert((await page.locator("#messageInput").inputValue()).length > 30);
    assert.equal(
      await page.evaluate(() => sessionData.conversas[0].mensagens.length),
      messageCount,
    );
    checks.push("Inbox e Assistente inserem rascunhos sem envio externo");

    await page.evaluate(() => setView("Automações"));
    await page.locator("[data-rule-create]").first().click();
    await page.locator("#ruleName").fill("Rotina QA");
    await page.locator("#nvRuleAfter").fill("Revisar o exemplo");
    await page.locator("#automationDraftForm [type=submit]").click();
    assert((await page.locator("#automationList").innerText()).includes("Rotina QA"));
    await page.locator("[data-rule-test]").first().click();
    assert((await page.locator("#nvManagementDrawerTitle").innerText()).includes("simulado"));
    await page.evaluate(() => closeModal("nvManagementDrawer"));
    checks.push("Automações locais e teste simulado");

    await page.evaluate(() => setView("Relatórios"));
    const csvPromise = page.waitForEvent("download");
    await page.evaluate(() => exportReportCsv());
    assert((await csvPromise).suggestedFilename().endsWith(".csv"));
    const backupPromise = page.waitForEvent("download");
    await page.evaluate(() => exportSocialMEIBackup());
    const backup = JSON.parse(fs.readFileSync(await (await backupPromise).path(), "utf8"));
    assert.equal(backup.product, "SocialMEI.IA");
    await page.reload();
    await page.waitForFunction(() => !!window.SocialMEIExperience);
    await page.evaluate(() => SocialMEIExperience.enterApp("Clientes"));
    assert.equal((await data()).clientes[0].nome, "Cliente QA atualizado");
    await page.evaluate(() => openClient(appData.clientes[0]));
    await page.locator("#clientModalBody [data-review-delete=clients]").click();
    await page.locator("#reviewConfirmAction").click();
    await page.waitForTimeout(250);
    assert.equal((await data()).clientes.length, initial.clientes.length);
    await page.locator("#backupImportInput").setInputFiles({
      name: "backup.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(backup)),
    });
    const reloadPromise = page.waitForEvent("load");
    await page.locator("#confirmBackupImport").click();
    await reloadPromise;
    assert.equal((await data()).clientes[0].nome, "Cliente QA atualizado");
    checks.push("CSV, localStorage, exclusão confirmada e restauração JSON");

    await page.evaluate(() => SocialMEIExperience.showScreen("auth"));
    await page.locator("[data-auth-tab=login]").click();
    await page.locator("#loginEmail").fill("teste@example.com");
    await page.locator("#loginPassword").fill("TesteLocal123!");
    await page.locator("#xpLoginForm [type=submit]").click();
    await page.waitForFunction(() => document.body.classList.contains("experience-app"));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator("#mb").click();
    assert(await page.locator("#mainContent").evaluate((element) => element.inert));
    await page.locator('#nav [data-nav="Visão Geral"]').click();
    assert.equal(await page.locator("#mainContent").evaluate((element) => element.inert), false);
    checks.push("Login local, sidebar mobile e foco/inert");

    await page.evaluate(() => setTheme("auto"));
    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForTimeout(100);
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    await page.emulateMedia({ colorScheme: "light" });
    await page.waitForTimeout(100);
    assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
    const customId = await page.evaluate(() => {
      const theme = SocialMEIThemes.save({
        version: 1,
        name: "QA",
        base: "dark",
        primary: "#2255BB",
        accent: "#FFCC00",
        intensity: 35,
        overrides: {},
      });
      SocialMEIThemes.select(theme.id);
      return theme.id;
    });
    assert.equal(await page.locator("html").getAttribute("data-active-theme"), customId);
    checks.push("Temas automático e custom");

    fs.mkdirSync(resultDirectory, { recursive: true });
    let states = 0;
    const views = [
      "Início",
      "Visão Geral",
      "Clientes",
      "Vendas",
      "Financeiro",
      "Produtos e Serviços",
      "Caixa Unificada",
      "Automações",
      "Assistente",
      "Relatórios",
      "Configurações",
    ];
    for (const [width, height] of [
      [1440, 1000],
      [1366, 768],
      [768, 1024],
      [390, 844],
    ]) {
      await page.setViewportSize({ width, height });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => setTheme(theme), theme);
        for (const view of views) {
          await page.evaluate((view) => setView(view), view);
          await page.waitForTimeout(50);
          assert.equal(await page.locator(".page-view.active").getAttribute("data-view"), view);
          assert(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
            `${view} ${width} ${theme}`,
          );
          states++;
        }
        await page.screenshot({
          path: path.join(resultDirectory, `workspace-${theme}-${width}.png`),
        });
      }
    }
    await page.evaluate(() => toast("QA", "Teste"));
    assert((await page.locator("#toastZone").innerText()).includes("QA"));
    assert.equal(await page.evaluate(() => document.getAnimations().length), 0);
    checks.push(await require("./remote-browser.cjs")(browser, origin, errors));
    checks.push(await require("./catalog-browser.cjs")(browser, origin, errors));
    checks.push(await require("./sales-browser.cjs")(browser, origin, errors));
    checks.push(await require("./finance-browser.cjs")(browser, origin, errors));
    checks.push(await require("./transfer-browser.cjs")(browser, origin, errors));
    checks.push(await require("./reports-browser.cjs")(browser, origin, errors));
    checks.push(await require("./visual-refinement-browser.cjs")(browser, origin, errors));
    checks.push(await require("./data-origin-browser.cjs")(browser, origin, errors));
    checks.push(await require("./visual-layout-browser.cjs")(browser, origin, errors));
    checks.push(await require("./visual-motion-browser.cjs")(browser, origin, errors));
    checks.push(await require("./audit-ui-browser.cjs")(browser, origin));
    checks.push(await require("./contact-browser.cjs")(browser, origin, errors));
    assert.deepEqual(errors, []);
    checks.push("11 módulos, quatro larguras, claro/escuro, toasts e reduced motion");
    fs.writeFileSync(
      path.join(resultDirectory, "browser-summary.json"),
      JSON.stringify({ checks, states, errors }, null, 2),
    );
    console.log(`${states} estados e ${checks.length} fluxos passaram.`);
  } finally {
    await browser?.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
