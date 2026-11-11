// Explicit local demonstration smoke; never runs against team or real providers.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const localBrowsers = path.resolve(__dirname, "../.preview/browsers");
if (!process.env.PLAYWRIGHT_BROWSERS_PATH && fs.existsSync(localBrowsers))
  process.env.PLAYWRIGHT_BROWSERS_PATH = localBrowsers;
const { chromium } = require("playwright");

async function run() {
  const origin = "https://127.0.0.1:8443";
  const root = path.resolve(__dirname, ".."),
    out = path.join(root, "test-results/valter-demo");
  const account = JSON.parse(
    fs.readFileSync(path.join(root, ".preview/valter-demo-account.json"), "utf8"),
  );
  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage(),
    errors = [],
    external = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== origin) {
      external.push(route.request().url());
      return route.abort();
    }
    return route.continue();
  });
  try {
    assert.equal(
      (await (await context.request.get(origin + "/__preview")).json()).environment,
      "local-disposable-preview",
    );
    fs.mkdirSync(out, { recursive: true });
    await page.goto(origin + "/frontend/entrada.html#/entrar");
    await page.locator("#preview-note-fE").waitFor({ state: "visible" });
    await page.locator("#eMailL").fill(account.email);
    await page.locator("#ePassL").fill(account.senha);
    await page.locator("#fE button[type=submit]").click();
    await page.waitForURL("**/socialmei-app.html**");
    await page.waitForFunction(
      () => window.SocialMEIV22?.identity && !document.getElementById("app").hidden,
    );
    const get = async (route) => (await context.request.get(origin + "/api/v1" + route)).json();
    assert.equal((await get("/auth/session")).negocio.id, account.workspaceId);
    const products = await get("/produtos");
    assert.equal(products.find((row) => row.nome.startsWith("Kit de costura")).estoque, 10);
    assert.equal(products.find((row) => row.tipo === "Serviço").estoque, null);
    assert.equal((await get("/vendas")).length, 2);
    assert.equal((await get("/financeiro")).length, 3);
    assert.equal((await get("/message-enrichment/conversations")).items.length, 3);
    const onlineReport = await get("/reporting/overview?days=7");
    assert.equal(
      onlineReport.attendance.reduce((sum, row) => sum + row.messages, 0),
      3,
    );
    assert(onlineReport.attendance.every((row) => row.origin === "synthetic"));
    await page.evaluate(() => go("/config/negocio"));
    const hours = "Segunda a sexta, 09:00–18:00; sábado, 09:00–12:00 — DEMONSTRAÇÃO";
    await page.getByLabel("Horário de funcionamento", { exact: true }).fill(hours);
    await page.locator('[data-a="savebiz"]').click();
    await page
      .getByText("Dados e horário de funcionamento salvos no negócio.", { exact: true })
      .waitFor();
    await page.reload();
    await page.getByLabel("Horário de funcionamento", { exact: true }).waitFor();
    assert.equal(
      await page.getByLabel("Horário de funcionamento", { exact: true }).inputValue(),
      hours,
    );
    await page.evaluate(() => go("/agenda"));
    await page.locator("[data-agenda]").waitFor();
    await page.getByText("Confirmar orçamento — fictício", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Novo lembrete", exact: true }).click();
    const reminder = "Verificação temporária — " + randomUUID().slice(0, 8);
    await page.locator("#f_agenda_title").fill(reminder);
    await page.locator("#f_agenda_date").fill(account.day);
    await page.locator("#f_agenda_time").fill("16:00");
    await page.getByRole("button", { name: "Salvar lembrete", exact: true }).click();
    await page.getByText("Lembrete salvo no negócio.", { exact: true }).waitFor();
    await page.reload();
    const appointment = page
      .locator(".agi")
      .filter({ has: page.getByText(reminder, { exact: true }) });
    await appointment.getByRole("checkbox").click();
    await appointment.getByRole("checkbox", { checked: true }).waitFor();
    page.once("dialog", (dialog) => dialog.accept());
    await appointment.getByRole("button", { name: "Cancelar", exact: true }).click();
    await appointment.waitFor({ state: "hidden" });
    assert.equal((await get("/agenda")).items.length, 1);
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const route of [
        "/agenda",
        "/negocio/clientes",
        "/negocio/produtos",
        "/negocio/vendas",
        "/negocio/financeiro",
        "/caixa",
        "/relatorios",
      ]) {
        await page.evaluate((route) => go(route), route);
        await page.evaluate(() => new Promise(requestAnimationFrame));
        if (route === "/negocio/clientes") {
          await page.locator('tr[data-a^="cli:"]').first().click();
          const buttons = await page
            .locator('.pn .row:has(> [data-a="edit:cli"]) > .btn')
            .evaluateAll((nodes) =>
              nodes.map((node) => {
                const range = document.createRange();
                range.selectNodeContents(node);
                return {
                  content: range.getBoundingClientRect().width,
                  width: node.clientWidth,
                  height: node.getBoundingClientRect().height,
                };
              }),
            );
          assert(
            buttons.every((button) => button.content <= button.width && button.height >= 44),
            "Customer action labels must fit their buttons",
          );
          await page.screenshot({ path: path.join(out, `clientes-${width}.png`), fullPage: true });
        }
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
          `${width}:${route}`,
        );
        if (route === "/agenda")
          await page.screenshot({ path: path.join(out, `agenda-${width}.png`), fullPage: true });
      }
    }
    const panel = page.locator("[data-sm-reports]");
    await panel.getByText("3 clientes", { exact: true }).waitFor();
    await panel.getByLabel("Período do relatório online").selectOption("7");
    await panel.getByText("Consulta concluída para os últimos 7 dias.", { exact: true }).waitFor();
    const download = page.waitForEvent("download");
    await panel.getByRole("button", { name: "Exportar CSV", exact: true }).click();
    await (await download).saveAs(path.join(out, "relatorio.csv"));
    assert(fs.readFileSync(path.join(out, "relatorio.csv"), "utf8").includes("90.00"));
    assert(
      fs.readFileSync(path.join(out, "relatorio.csv"), "utf8").includes("Mensagens recebidas"),
    );
    await page.addInitScript(() => {
      window.print = () => {};
    });
    // Replace only print() in new same-origin frames; no system print dialog during tests.
    await page.evaluate(() => {
      const create = document.createElement.bind(document);
      document.createElement = function (tag, ...args) {
        const node = create(tag, ...args);
        if (tag.toLowerCase() === "iframe") {
          const append = document.body.append.bind(document.body);
          document.body.append = function (...nodes) {
            append(...nodes);
            if (nodes.includes(node)) node.contentWindow.print = () => {};
          };
        }
        return node;
      };
    });
    await panel.getByRole("button", { name: "Salvar PDF / imprimir", exact: true }).click();
    const printed = await page
      .locator("[data-sm-report-print]")
      .evaluate((frame) => frame.contentDocument.documentElement.outerHTML);
    assert(printed.includes("Ateliê Escola") && printed.includes("últimos 7 dias"));
    const printer = await context.newPage();
    await printer.setContent(printed);
    await printer.pdf({ path: path.join(out, "relatorio.pdf"), format: "A4" });
    assert.equal(
      fs.readFileSync(path.join(out, "relatorio.pdf")).subarray(0, 4).toString(),
      "%PDF",
    );
    await printer.close();
    await page.screenshot({ path: path.join(out, "relatorios.png"), fullPage: true });
    await page.reload();
    await page.waitForFunction(() => window.SocialMEIV22?.identity);
    assert.equal((await get("/clientes")).length, 3);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "Valter demo: real login, CRM/stock/inbox, persistent Agenda CRUD, two widths, period filter and CSV/PDF verified. Messages and analysis are simulated.",
    );
  } finally {
    await context.close();
    await browser.close();
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
