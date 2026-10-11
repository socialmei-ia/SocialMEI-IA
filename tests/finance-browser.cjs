const assert = require("node:assert/strict");
module.exports = async function financeFlows(browser, origin, errors) {
  const clients = [11, 12].map((id) => ({ id, versao: 1, nome: "Mesmo nome", tags: [] }));
  const rows = [],
    operations = new Map(),
    imports = new Map();
  let nextId = 500,
    offline = false,
    lost = false;
  const seed = {
    schemaVersion: 1,
    clientes: [{ id: 1, nome: "Cliente local", tags: [] }],
    produtos: [],
    vendas: [],
    financeiro: [
      {
        id: 1,
        descricao: "Histórico",
        pessoa: "Fornecedor",
        tipo: "despesa",
        valor: 10.25,
        vencimento: "2026-10-10",
        status: "pago",
      },
    ],
    prefs: {},
  };
  async function setup(page, local) {
    page.on("pageerror", (error) => errors.push(error.message));
    if (local)
      await page.addInitScript((data) => {
        if (!localStorage.getItem("socialmei-app-data-v2"))
          localStorage.setItem("socialmei-app-data-v2", JSON.stringify(data));
      }, seed);
    await page.route("**/*", async (route) => {
      const req = route.request(),
        url = new URL(req.url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname.endsWith("/config.js"))
        return route.fulfill({
          contentType: "application/javascript",
          body: `const source={mode:"remote",apiBaseUrl:"${origin}/api/v1",workspaceKey:"qa"};const SOCIALMEI_CONFIG=Object.freeze({n8nMessagesUrl:"${origin}/disabled",clientes:source,financeiro:source});`,
        });
      if (!url.pathname.startsWith("/api/v1/")) return route.continue();
      if (url.pathname === "/api/v1/clientes") return route.fulfill({ json: clients });
      if (offline) return route.fulfill({ status: 503, json: {} });
      const data = req.postDataJSON();
      if (req.method() === "GET" && url.pathname === "/api/v1/financeiro")
        return route.fulfill({ json: rows.filter((r) => !r.excluida) });
      if (url.pathname.includes("/financeiro/importacoes/")) {
        const items = data.itens.map((i) => {
          const key = data.origem + ":" + i.local_id,
            prior = imports.get(key);
          const action = !prior
            ? "criar"
            : rows.find((r) => r.id === prior.id).excluida
              ? "excluido"
              : prior.signature === JSON.stringify(i)
                ? "existente"
                : "conflito";
          if (url.pathname.endsWith("/confirmar") && action === "criar") {
            const entry = {
              ...i.lancamento,
              id: nextId++,
              versao: 1,
              importada: true,
              excluida: false,
            };
            rows.push(entry);
            imports.set(key, { id: entry.id, signature: JSON.stringify(i) });
          }
          return {
            local_id: i.local_id,
            lancamento_id: imports.get(key)?.id ?? null,
            acao: action,
          };
        });
        return route.fulfill({
          json: {
            itens: items,
            pode_importar: items.every((i) => ["criar", "existente"].includes(i.acao)),
          },
        });
      }
      const signature = req.method() + url.pathname + JSON.stringify(data),
        prior = operations.get(data.operation_id);
      if (prior)
        return route.fulfill(
          prior.signature === signature
            ? { status: prior.status, json: prior.result }
            : { status: 409, json: {} },
        );
      let row,
        status = 200;
      if (url.pathname === "/api/v1/financeiro" && req.method() === "POST") {
        row = {
          ...data,
          pessoa: data.cliente_id
            ? clients.find((c) => c.id === data.cliente_id).nome
            : data.pessoa,
          id: nextId++,
          versao: 1,
          data_pagamento: data.status === "pago" ? "2026-10-11" : null,
          importada: false,
          excluida: false,
        };
        delete row.operation_id;
        rows.push(row);
        status = 201;
      } else {
        const match = url.pathname.match(/^\/api\/v1\/financeiro\/(\d+)(?:\/(pagar|excluir))?$/);
        row = match && rows.find((r) => r.id === Number(match[1]) && !r.excluida);
        if (!row) return route.fulfill({ status: 404, json: {} });
        if (row.versao !== data.expected_version)
          return route.fulfill({
            status: 409,
            json: { detail: "Lançamento alterado por outra sessão." },
          });
        if (req.method() === "PATCH") {
          if (row.status === "pago") return route.fulfill({ status: 409, json: {} });
          const { operation_id, expected_version, ...fields } = data;
          Object.assign(row, fields, { versao: row.versao + 1 });
        } else if (match[2] === "pagar") {
          if (row.status !== "pago")
            Object.assign(row, {
              status: "pago",
              versao: row.versao + 1,
              data_pagamento: "2026-10-11",
            });
        } else Object.assign(row, { excluida: true, versao: row.versao + 1 });
      }
      operations.set(data.operation_id, { signature, result: structuredClone(row), status });
      if (lost) {
        lost = false;
        return route.abort();
      }
      return route.fulfill({ status, json: row });
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Financeiro"));
    await page.waitForFunction(() =>
      ["financeSourceStatus", "clientsSourceStatus"].every((id) =>
        document.getElementById(id).textContent.includes("conectado"),
      ),
    );
  }
  const page = await browser.newPage({
    viewport: { width: 1366, height: 900 },
    reducedMotion: "reduce",
  });
  await setup(page, true);
  assert.equal(await page.evaluate(() => appData.financeiro.length), 0);
  await page.evaluate(() => openCreate("receita"));
  await page.locator("#f_descricao").fill("Entrada compartilhada");
  await page.locator("#f_valor").fill("12.35");
  await page.locator("#f_cliente_id").selectOption("12");
  await page.locator("#createSubmit").click();
  await page.waitForFunction(
    () =>
      appData.financeiro.length === 1 &&
      !document.getElementById("createModal").classList.contains("open"),
  );
  const id = rows[0].id;
  assert.equal(rows[0].cliente_id, 12);
  assert.equal(rows[0].pessoa, "Mesmo nome");
  assert.equal(
    await page.evaluate(() =>
      SocialMEIFinance.matchesClient(appData.financeiro[0], appData.clientes[0]),
    ),
    false,
  );
  const second = await browser.newPage({ reducedMotion: "reduce" });
  await setup(second, false);
  assert.equal(await second.evaluate(() => appData.financeiro[0].valor), 12.35);
  await page.evaluate((id) => openRecordEditor("finance", id), id);
  await page.locator("#f_valor").fill("15.25");
  await page.locator("#createSubmit").click();
  await page.waitForFunction(
    () =>
      appData.financeiro[0].valor === 15.25 &&
      !document.getElementById("createModal").classList.contains("open"),
  );
  await second.evaluate((id) => openRecordEditor("finance", id), id);
  await second.locator("#f_valor").fill("99");
  await second.locator("#createSubmit").click();
  await second.waitForFunction(() =>
    document.getElementById("financeSourceStatus").textContent.includes("indisponível"),
  );
  assert.equal(rows[0].valor, 15.25);
  await second.evaluate(() => closeModal("createModal"));
  await second.evaluate(() => SocialMEIFinance.refresh());
  await page.evaluate((id) => openRecord("finance", id), id);
  await page.locator(`#recordModal [data-finance-paid="${id}"]`).click();
  await page.waitForFunction(
    () =>
      appData.financeiro[0].status === "pago" &&
      document.getElementById("financeSourceStatus").textContent.includes("conectado"),
  );
  await page.waitForFunction(
    () => document.querySelector('#recordModal [data-review-edit="finance"]')?.disabled,
  );
  await page.evaluate(() => closeModal("recordModal"));
  await second.evaluate(() => SocialMEIFinance.refresh());
  assert.equal(await second.evaluate(() => appData.financeiro[0].status), "pago");
  await page.evaluate(() => openCreate("despesa"));
  await page.locator("#f_descricao").fill("Saída recuperável");
  await page.locator("#f_pessoa").fill("Fornecedor");
  await page.locator("#f_valor").fill("5.5");
  lost = true;
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() =>
    document.getElementById("financeSourceStatus").textContent.includes("indisponível"),
  );
  await page.evaluate(() => closeModal("createModal"));
  const length = rows.length;
  await page.reload();
  await page.evaluate(() => SocialMEIExperience.enterApp("Financeiro"));
  await page.locator("[data-finance-recover]").click();
  await page.waitForFunction(
    () =>
      localStorage.getItem("socialmei-finance-operation-pending-v1") === "null" &&
      document.getElementById("financeSourceStatus").textContent.includes("conectado"),
  );
  assert.equal(rows.length, length);
  for (let i = 0; i < 2; i++) {
    await page.locator("[data-finance-import]").click();
    await page.locator("#confirmFinanceImport").click();
    await page.waitForFunction(
      () =>
        !document.getElementById("financeImportModal").classList.contains("open") &&
        document.getElementById("financeSourceStatus").textContent.includes("conectado"),
    );
  }
  assert.equal(rows.filter((r) => r.importada).length, 1);
  await page.evaluate(() => {
    appData.prefs.test = true;
    saveAppData();
  });
  assert.deepEqual(
    await page.evaluate(() => JSON.parse(localStorage.getItem("socialmei-app-data-v2")).financeiro),
    seed.financeiro,
  );
  await page.evaluate((id) => openRecordConfirmation("finance", id), id);
  await page.locator("#reviewConfirmAction").click();
  await page.waitForFunction(
    (id) =>
      !appData.financeiro.some((r) => r.id === id) &&
      !document.getElementById("reviewConfirm").classList.contains("open"),
    id,
  );
  offline = true;
  await page.evaluate(() => SocialMEIFinance.refresh());
  const before = rows.length;
  assert.equal(
    await page.evaluate(() =>
      SocialMEIFinance.create({
        descricao: "Não salvar",
        tipo: "receita",
        pessoa: "",
        valor: 1,
        vencimento: "2026-10-11",
      }),
    ),
    null,
  );
  assert.equal(rows.length, before);
  offline = false;
  await page.evaluate(() => SocialMEIFinance.refresh());
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.close();
  await second.close();
  return "Financeiro remoto: duas sessões, entrada/saída, vínculo por ID, conflito, quitação, recuperação após reload, importação repetida, snapshot, exclusão e indisponibilidade";
};
