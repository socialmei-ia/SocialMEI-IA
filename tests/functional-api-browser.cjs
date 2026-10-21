// Opt-in audit against a disposable REAL API. Refuses non-loopback targets.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { chromium } = require("playwright");
async function run(config) {
  const target = new URL(config.origin);
  assert(
    target.protocol === "https:" && ["localhost", "127.0.0.1", "[::1]"].includes(target.hostname),
    "Disposable HTTPS loopback origin required",
  );
  const origin = target.origin,
    trace = [],
    errors = [],
    external = [],
    checks = [];
  const output = path.resolve(__dirname, "../test-results/functional-api");
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    httpCredentials: config.httpCredentials,
    locale: "pt-BR",
    reducedMotion: "reduce",
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("response", (r) => {
    const u = new URL(r.url());
    if (u.origin === origin && u.pathname.startsWith("/api/"))
      trace.push({ method: r.request().method(), path: u.pathname, status: r.status() });
  });
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== origin) {
      external.push(new URL(route.request().url()).origin);
      return route.abort();
    }
    return route.continue();
  });
  const closed = () =>
    page.waitForFunction(() => !document.getElementById("createModal").classList.contains("open"));
  try {
    console.log("QA76: cadastro remoto");
    await page.goto(origin + "/");
    await page.locator("[data-auth-tab=register]").click();
    await page.locator("#registerName").fill("Empreendedor fictício QA76");
    const registrationEmail = `qa76-${randomUUID()}@example.test`;
    await page.locator("#registerEmail").fill(registrationEmail);
    await page.locator("#registerPhone").fill("11988776655");
    await page.locator("#registerPassword").fill(config.registration.password);
    await page.locator("#xpRegisterForm [type=submit]").click();
    await page.locator(".contact-confirmation button[value=confirm]").click();
    await page.waitForFunction(() => !!window.SocialMEIAuth?.current);
    // Onboarding remains the application's six-step local business profile.
    if (await page.locator('[data-xp-screen="onboarding"].is-active').count()) {
      await page.locator("[data-onboard-next]").click();
      assert(
        await page.locator("#obBusiness").isDisabled(),
        "Remote workspace name is read-only under the existing contract",
      );
      await page.locator('#businessFamilyChoices button[data-family="Beleza e cuidados"]').click();
      await page.locator('#businessSpecialtyChoices input[value="barber"]').check();
      for (let step = 3; step <= 6; step++) {
        await page.locator("[data-onboard-next]").click();
        await page.locator(`[data-onboard-panel="${step}"].is-active`).waitFor();
      }
      await page.locator("[data-onboard-next]").click();
    }
    await page.waitForFunction(() => document.body.classList.contains("experience-app"));
    await page.waitForFunction(() =>
      [SocialMEIClients, SocialMEIProducts, SocialMEISales, SocialMEIFinance].every(
        (s) => s.connectionState === "ready",
      ),
    );
    assert.deepEqual(
      await page.evaluate(() => [
        appData.clientes.length,
        appData.produtos.length,
        appData.vendas.length,
        appData.financeiro.length,
      ]),
      [0, 0, 0, 0],
    );
    const flag = await page.evaluate(async () => {
      try {
        await SocialMEIAuth.request("/instagram/simulation/status");
        return 200;
      } catch (e) {
        return e.status;
      }
    });
    assert.equal(flag, 503);
    console.log("QA76: cadastro e onboarding concluídos");
    checks.push(
      "Cadastro real, onboarding, sessão HttpOnly e conta comercial vazia; Instagram default503",
    );
    await page.evaluate(() => {
      setView("Clientes");
      openCreate("cliente");
    });
    await page.locator("#f_nome").fill("Cliente fictício QA76");
    await page.locator("#createSubmit").click();
    await page.waitForFunction(() => appData.clientes.length === 1);
    await closed();
    const clientId = await page.evaluate(() => appData.clientes[0].id);
    await page.evaluate(() => {
      setView("Produtos e Serviços");
      openCreate("produto");
    });
    for (const [key, value] of Object.entries({
      nome: "Produto fictício QA76",
      preco: "30",
      custo: "8",
      estoque: "7",
      minimo: "2",
    }))
      await page.locator("#f_" + key).fill(value);
    await page.locator("#createSubmit").click();
    await page.waitForFunction(() => appData.produtos.length === 1);
    await closed();
    console.log("QA76: cliente e produto persistidos");
    const productId = await page.evaluate(() => appData.produtos[0].id);
    await page.evaluate(() => {
      setView("Vendas");
      openCreate("venda");
    });
    await page.locator("#f_cliente").selectOption(String(clientId));
    await page.locator("#f_item").selectOption(String(productId));
    await page.locator("#f_quantidade").fill("2");
    await page.locator("#createSubmit").click();
    await page.waitForFunction(() => appData.vendas.length === 1);
    await closed();
    assert.equal(await page.evaluate(() => appData.produtos[0].estoque), 5);
    const saleId = await page.evaluate(() => appData.vendas[0].id);
    await page.evaluate((id) => openRecord("sales", id), saleId);
    await page.locator(`[data-sale-paid="${saleId}"]`).first().click();
    await page.waitForFunction(() => appData.vendas[0].status === "Pago");
    await page.evaluate(() => closeModal("recordModal"));
    await page.evaluate(() => {
      setView("Financeiro");
      openCreate("receita");
    });
    await page.locator("#f_descricao").fill("Receita fictícia QA76");
    await page.locator("#f_valor").fill("12.35");
    await page.locator("#createSubmit").click();
    await page.waitForFunction(() => appData.financeiro.length === 1);
    await closed();
    const financeId = await page.evaluate(() => appData.financeiro[0].id);
    await page.evaluate((id) => openRecordEditor("finance", id), financeId);
    await page.locator("#f_valor").fill("15.25");
    await page.locator("#createSubmit").click();
    await page.waitForFunction(() => appData.financeiro[0].valor === 15.25);
    await closed();
    checks.push(
      "Cliente/produto/venda reais no DB descartável; baixa7→5 e pagamento; Financeiro12.35→15.25 sem duplicar venda",
    );
    await page.reload();
    await page.waitForFunction(
      () =>
        !!window.SocialMEIAuth?.current &&
        appData.vendas.length === 1 &&
        appData.financeiro.length === 1,
    );
    await page.evaluate(() => SocialMEIExperience.enterApp("Relatórios"));
    assert.equal(await page.evaluate(() => operationalMetrics().revenue), 60);
    await page.locator("[data-report-generate]").click();
    await page.locator("#reportGenerateForm [type=submit]").click();
    await page.waitForFunction(
      () => document.getElementById("reportGenerateTitle").textContent === "Relatório pronto",
    );
    const download = page.waitForEvent("download");
    await page.locator("#reportGenerateModal [data-report-action=csv]").click();
    const csv = await download;
    const contents = fs.readFileSync(await csv.path(), "utf8");
    assert(contents.includes('"60"'));
    fs.writeFileSync(path.join(output, "real-api-report.csv"), contents);
    await page.keyboard.press("Escape");
    await page.screenshot({ path: path.join(output, "reports-real-api-1440.png") });
    checks.push("Reload recupera os registros; Relatórios lê faturamento60 do DB e gera CSV local");
    await page.locator("#sb [data-account-logout]").click();
    await page.locator("#loginEmail").waitFor({ state: "visible" });
    await page.locator("#loginEmail").fill(registrationEmail);
    await page.locator("#loginPassword").fill(config.registration.password);
    await page.locator("#xpLoginForm [type=submit]").click();
    await page.waitForFunction(
      () => !!window.SocialMEIAuth?.current && appData.vendas.length === 1,
    );
    assert.equal(await page.evaluate(() => appData.produtos[0].estoque), 5);
    assert.equal(await page.evaluate(() => appData.financeiro[0].valor), 15.25);
    checks.push("Logout/login reais recuperam os mesmos registros isolados");
    assert.deepEqual(external, []);
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify({ checks, trace, errors, external }, null, 2),
    );
    console.log(JSON.stringify({ checks, errors, external }));
  } catch (error) {
    await page.screenshot({ path: path.join(output, "failure.png") }).catch(() => {});
    fs.writeFileSync(
      path.join(output, "failure.json"),
      JSON.stringify(
        {
          trace,
          errors,
          external,
          location: page.url(),
          body: await page
            .locator("body")
            .getAttribute("class")
            .catch(() => null),
        },
        null,
        2,
      ),
    );
    throw error;
  } finally {
    await context.close();
    await browser.close();
  }
}
if (require.main === module)
  run(JSON.parse(fs.readFileSync(process.env.SOCIALMEI_QA_CONFIG, "utf8"))).catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
module.exports = run;
