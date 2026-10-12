const assert = require("node:assert/strict");

module.exports = async function reportsFlows(browser, origin, errors) {
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const clients = [11, 12].map((id) => ({
    id,
    versao: 1,
    nome: "Mesmo nome",
    tags: [],
    criadoEm: "2026-10-10T12:00:00Z",
  }));
  const products = [21, 22].map((id) => ({
    id,
    versao: 1,
    nome: "Mesmo item",
    tipo: "Produto",
    preco: 30,
    custo: 10,
    estoque: 10,
    minimo: 1,
    status: "Ativo",
  }));
  const sales = [
    { id: 31, cliente_id: 11, produto_id: 21, quantidade: 2, valor: 60 },
    { id: 32, cliente_id: 12, produto_id: 22, quantidade: 3, valor: 90 },
    { id: 33, cliente_id: 11, produto_id: 21, quantidade: 1, valor: 30, status: "Pendente" },
    { id: 34, cliente_id: 11, produto_id: 21, quantidade: 1, valor: 30, data: "2026-09-10" },
  ].map((sale) => ({
    versao: 1,
    cliente: "Mesmo nome",
    item: "Mesmo item",
    status: "Pago",
    data: "2026-10-10",
    pagamento: "Pix",
    ...sale,
  }));
  const finance = [
    { id: 41, descricao: "Entrada", tipo: "receita", valor: 50, status: "pago" },
    { id: 42, descricao: "Saída", tipo: "despesa", valor: 20, status: "pago" },
    { id: 43, descricao: "Em aberto", tipo: "receita", valor: 100, status: "aberto" },
  ].map((entry) => ({ versao: 1, pessoa: "", vencimento: "2026-10-10", ...entry }));
  const unexpected = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.clock.setFixedTime(new Date("2026-10-10T12:00:00Z"));
  await page.route("**/*", async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (url.origin !== origin) {
      unexpected.push(url.href);
      return route.abort();
    }
    if (url.pathname.endsWith("/config.js"))
      return route.fulfill({
        contentType: "application/javascript",
        body: `const source={mode:"remote",apiBaseUrl:"${origin}/api/v1",workspaceKey:"qa"};const SOCIALMEI_CONFIG=Object.freeze({n8nMessagesUrl:null,clientes:source,produtos:source,vendas:source,financeiro:source});`,
      });
    if (url.pathname.startsWith("/api/v1/")) {
      const datasets = {
        clientes: clients,
        produtos: products,
        vendas: sales,
        financeiro: finance,
      };
      const data = datasets[url.pathname.slice("/api/v1/".length)];
      assert.equal(request.method(), "GET");
      assert(data, url.pathname);
      return route.fulfill({ json: data });
    }
    if (url.pathname.endsWith("/null") || url.pathname.endsWith("/undefined"))
      unexpected.push(url.pathname);
    return route.continue();
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () =>
        appData.clientes.length === 2 &&
        appData.produtos.length === 2 &&
        appData.vendas.length === 4 &&
        appData.financeiro.length === 3,
    );
    await page.evaluate(() => {
      SocialMEIExperience.enterApp("Relatórios");
      selectedPeriod = "Este mês";
      renderReports();
    });
    const summary = await page.evaluate(() => getReportSummaryText());
    assert(summary.includes("Vendas pagas: 2"));
    assert(summary.includes("dados compartilhados"));
    assert(!summary.includes("registros deste navegador"));
    assert.equal(await page.evaluate(() => operationalMetrics().revenue), 150);
    assert.equal(await page.evaluate(() => operationalMetrics().balance), 30);
    assert.equal(
      await page.evaluate(() => getCustomerRegistrationDate({ criadoEm: "2026-10-11T01:00:00Z" })),
      "2026-10-10",
    );
    assert.equal(
      await page.evaluate(() => getCustomerRegistrationDate({ criadoEm: "2026-10-10" })),
      "2026-10-10",
    );
    const chart = page.locator("#resultChapter .management-chart");
    assert(
      (await chart.locator(".management-chart-column").first().getAttribute("aria-label")).includes(
        "faturamento",
      ),
    );
    assert.equal(await chart.locator(".management-bars .out").count(), 0);
    assert(!(await chart.innerText()).includes("Saiu"));
    assert.equal(await page.locator("#driversChapter tbody tr").count(), 2);
    const productTable = page.getByRole("table", { name: "Itens vendidos", exact: true });
    assert.equal(await productTable.locator("tbody tr").count(), 2);
    assert.deepEqual(await productTable.locator("tbody tr td:nth-child(2)").allTextContents(), [
      "3",
      "2",
    ]);

    await page.evaluate(() => {
      sessionData.conversas = ["whatsapp", "instagram", "other"].map((canal, index) => ({
        id: 101 + index,
        nome: "Mesmo nome",
        canal,
        status: "aberto",
        naoLidas: 0,
        mensagens: [{ de: "cliente", texto: "Oi", data: "2026-10-10" }],
      }));
      SocialMEIClients.link(
        sessionData.conversas[0],
        appData.clientes.find((c) => c.id === 11),
      );
      SocialMEIClients.link(
        sessionData.conversas[1],
        appData.clientes.find((c) => c.id === 12),
      );
      appData.clientes.find((c) => c.id === 11).nome = "Nome atualizado";
      selectedReportTab = "Atendimento";
      renderReports();
    });
    assert.deepEqual(await page.locator(".management-report-funnel b").allTextContents(), [
      "3",
      "3",
      "2",
    ]);
    const channelRows = await page.evaluate(() => {
      selectedReportTab = "Resumo";
      renderReports();
      const table = [...document.querySelectorAll("table")].find(
        (table) => table.caption?.textContent.trim() === "Vendas pagas por canal",
      );
      return [...table.querySelectorAll("tbody tr")].map((tr) =>
        tr.textContent.replace(/\s+/g, " ").trim(),
      );
    });
    assert(channelRows.some((row) => row.startsWith("WhatsApp")));
    assert(channelRows.some((row) => row.startsWith("Instagram")));
    for (const [view, meta] of [
      ["Clientes", "clientsMeta"],
      ["Produtos e Serviços", "productsMeta"],
      ["Vendas", "salesMeta"],
      ["Financeiro", "financeMeta"],
    ]) {
      await page.evaluate((view) => setView(view), view);
      assert((await page.locator("#" + meta).innerText()).includes("dados compartilhados"));
    }
    await page.evaluate(() => {
      setView("Relatórios");
      areMoneyValuesHidden = true;
      renderReports();
    });
    assert.equal(await page.locator("#reportsGrid .management-chart").count(), 0);
    assert(!(await page.evaluate(() => getReportSummaryText())).includes("150,00"));
    await page.evaluate(() => {
      areMoneyValuesHidden = false;
      selectedPeriod = "Personalizado";
      customRange = { from: "2026-08-01", to: "2026-08-31" };
      renderReports();
    });
    assert.equal(await page.locator("#reportsGrid .management-chart").count(), 0);
    assert(
      (await page.locator("#reportsGrid").innerText()).includes("Sem movimento neste período"),
    );
    // The retained SVG helper must put bars in SVG, rather than the surrounding HTML.
    assert(
      await page.evaluate(() => {
        const host = document.createElement("div");
        host.innerHTML = reportTrend(
          { source: "sales", labels: ["10/10"], r: [150], d: [0] },
          "Faturamento",
        );
        return (
          host.querySelector("svg rect")?.namespaceURI === "http://www.w3.org/2000/svg" &&
          !host.querySelector(":scope > rect")
        );
      }),
    );
    await page.evaluate(async () => {
      await syncN8nMessages(false);
      startN8nSync();
      scheduleN8nSync();
    });
    assert.equal(await page.evaluate(() => n8nSyncTimer), null);
    assert.equal(await page.evaluate(() => syncState), "disabled");
    assert.deepEqual(unexpected, []);
  } finally {
    await page.close();
  }
  return "Relatórios: totais e períodos, IDs com nomes repetidos, canais, fonte compartilhada, privacidade, SVG e mensagens desativadas";
};
