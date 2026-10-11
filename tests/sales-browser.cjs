const assert = require("node:assert/strict");
module.exports = async function salesFlows(browser, origin, errors) {
  const clients = [{ id: 11, versao: 1, nome: "Cliente remoto", tags: [], telefone: "—" }];
  const products = [
    {
      id: 21,
      versao: 1,
      nome: "Produto remoto",
      tipo: "Produto",
      preco: 30,
      custo: 10,
      estoque: 7,
      minimo: 2,
      status: "Ativo",
    },
    {
      id: 22,
      versao: 1,
      nome: "Serviço remoto",
      tipo: "Serviço",
      preco: 50,
      custo: 10,
      estoque: null,
      minimo: null,
      status: "Ativo",
    },
  ];
  const rows = [],
    operations = new Map(),
    imports = new Map();
  let nextId = 300,
    loseResponse = false;
  const seed = {
    schemaVersion: 1,
    clientes: [{ id: 1, nome: "Cliente local", tags: [] }],
    produtos: [
      { id: 1, nome: "Produto local", tipo: "Produto", preco: 20, custo: 5, estoque: 9, minimo: 1 },
    ],
    vendas: [
      {
        id: 1001,
        cliente: "Cliente local",
        item: "Produto local",
        data: "2026-10-10",
        valor: 40,
        quantidade: 2,
        preco: 20,
        status: "Pago",
      },
    ],
    financeiro: [],
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
          body: `const source={mode:"remote",apiBaseUrl:"${origin}/api/v1",workspaceKey:"qa"};const SOCIALMEI_CONFIG=Object.freeze({n8nMessagesUrl:"${origin}/disabled-n8n",n8nAuthHeader:null,clientes:source,produtos:source,vendas:source});`,
        });
      if (!url.pathname.startsWith("/api/v1/")) return route.continue();
      const data = req.postDataJSON();
      if (url.pathname === "/api/v1/clientes") return route.fulfill({ json: clients });
      if (url.pathname === "/api/v1/produtos") return route.fulfill({ json: products });
      if (url.pathname === "/api/v1/vendas" && req.method() === "GET")
        return route.fulfill({ json: rows.filter((v) => !v.excluida) });
      if (url.pathname.includes("/vendas/importacoes/")) {
        const items = data.itens.map((i) => {
          const prior = imports.get(data.origem + ":" + i.local_id);
          return {
            local_id: i.local_id,
            venda_id: prior?.id ?? null,
            acao: !prior
              ? "criar"
              : rows.find((v) => v.id === prior.id)?.excluida
                ? "excluido"
                : prior.fingerprint === JSON.stringify(i)
                  ? "existente"
                  : "conflito",
          };
        });
        const allowed = items.every((r) => ["criar", "existente"].includes(r.acao));
        if (url.pathname.endsWith("/preview"))
          return route.fulfill({
            json: { itens: items, pode_importar: allowed, estoque_movimentado: false },
          });
        if (!allowed) return route.fulfill({ status: 409, json: {} });
        items.forEach((item, index) => {
          if (item.acao === "existente") return;
          const input = data.itens[index];
          const row = {
            ...input.venda,
            id: ++nextId,
            versao: 1,
            importada: true,
            excluida: false,
            estoque_aplicado: false,
          };
          rows.push(row);
          item.venda_id = row.id;
          imports.set(data.origem + ":" + item.local_id, {
            id: row.id,
            fingerprint: JSON.stringify(input),
          });
        });
        return route.fulfill({ json: { itens: items, estoque_movimentado: false } });
      }
      const match = url.pathname.match(/^\/api\/v1\/vendas\/(\d+)(?:\/(\w+))?$/);
      if (req.method() === "GET" && match) {
        const row = rows.find((v) => v.id === Number(match[1]) && !v.excluida);
        return route.fulfill({ status: row ? 200 : 404, json: row || {} });
      }
      const signature = JSON.stringify({ path: url.pathname, method: req.method(), data });
      const previous = operations.get(data?.operation_id);
      if (previous)
        return route.fulfill({
          status: previous.signature === signature ? previous.status : 409,
          json: previous.signature === signature ? previous.result : {},
        });
      let row,
        status = 200;
      if (url.pathname === "/api/v1/vendas" && req.method() === "POST") {
        const product = products.find((p) => p.id === data.produto_id),
          client = clients.find((c) => c.id === data.cliente_id);
        if (!product || !client) return route.fulfill({ status: 422, json: {} });
        const applied = data.status !== "Rascunho" && product.tipo === "Produto";
        if (applied && product.estoque < data.quantidade)
          return route.fulfill({ status: 409, json: { detail: "Estoque insuficiente." } });
        const { operation_id, ...fields } = data;
        row = {
          ...fields,
          id: ++nextId,
          versao: 1,
          cliente: client.nome,
          item: product.nome,
          tipo_item: product.tipo,
          valor: data.preco * data.quantidade - (data.desconto || 0),
          importada: false,
          excluida: false,
          estoque_aplicado: applied,
        };
        if (applied) {
          product.estoque -= data.quantidade;
          product.versao++;
        }
        rows.push(row);
        status = 201;
      } else if (match) {
        row = rows.find((v) => v.id === Number(match[1]) && !v.excluida);
        if (!row) return route.fulfill({ status: 404, json: {} });
        if (row.versao !== data.expected_version) return route.fulfill({ status: 409, json: {} });
        if (req.method() === "PATCH") {
          if (row.importada || !["Pendente", "Rascunho"].includes(row.status))
            return route.fulfill({ status: 409, json: {} });
          const product = products.find((p) => p.id === data.produto_id),
            old = products.find((p) => p.id === row.produto_id);
          const applied = row.status === "Pendente" && product.tipo === "Produto";
          const available =
            product.estoque + (row.estoque_aplicado && old.id === product.id ? row.quantidade : 0);
          if (applied && available < data.quantidade)
            return route.fulfill({ status: 409, json: {} });
          if (row.estoque_aplicado) {
            old.estoque += row.quantidade;
            old.versao++;
          }
          if (applied) {
            product.estoque -= data.quantidade;
            product.versao++;
          }
          const { operation_id, expected_version, ...fields } = data;
          Object.assign(row, fields, {
            item: product.nome,
            cliente: clients.find((c) => c.id === data.cliente_id).nome,
            tipo_item: product.tipo,
            estoque_aplicado: applied,
            valor: data.preco * data.quantidade - data.desconto,
            versao: row.versao + 1,
          });
        } else {
          const action = match[2];
          const target = {
            registrar: "Pendente",
            pagar: "Pago",
            cancelar: "Cancelado",
            excluir: "Cancelado",
          }[action];
          const product = products.find((p) => p.id === row.produto_id);
          if (["cancelar", "excluir"].includes(action)) {
            if (row.estoque_aplicado) {
              product.estoque += row.quantidade;
              product.versao++;
            }
            row.estoque_aplicado = false;
            row.excluida = action === "excluir";
          } else if (!row.importada && row.status === "Rascunho" && product.tipo === "Produto") {
            if (product.estoque < row.quantidade) return route.fulfill({ status: 409, json: {} });
            product.estoque -= row.quantidade;
            product.versao++;
            row.estoque_aplicado = true;
          }
          row.status = target;
          row.versao++;
        }
      } else return route.fulfill({ status: 404, json: {} });
      operations.set(data.operation_id, { signature, result: structuredClone(row), status });
      if (loseResponse) {
        loseResponse = false;
        return route.abort();
      }
      return route.fulfill({ status, json: row });
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Vendas"));
    await page.waitForFunction(() =>
      ["salesSourceStatus", "productsSourceStatus", "clientsSourceStatus"].every((id) =>
        document.getElementById(id).textContent.includes("conectado"),
      ),
    );
  }
  const page = await browser.newPage({
    viewport: { width: 1366, height: 900 },
    reducedMotion: "reduce",
  });
  await setup(page, true);
  assert.equal(await page.evaluate(() => appData.vendas.length), 0);
  await page.evaluate(() => openCreate("venda"));
  await page.locator("#f_cliente").selectOption("11");
  await page.locator("#f_item").selectOption("21");
  await page.locator("#f_quantidade").fill("2");
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() => appData.vendas.length === 1);
  assert.equal(products[0].estoque, 5);
  const saleId = rows[0].id;
  const second = await browser.newPage();
  await setup(second, false);
  assert.equal(await second.evaluate(() => appData.vendas[0].produto_id), 21);
  assert.equal(await second.evaluate(() => appData.produtos[0].estoque), 5);
  await page.evaluate((id) => openRecordEditor("sales", id), saleId);
  await page.locator("#f_quantidade").fill("3");
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() => appData.vendas[0].quantidade === 3);
  assert.equal(products[0].estoque, 4);
  await page.evaluate((id) => openRecordEditor("sales", id), saleId);
  await page.locator("#f_quantidade").fill("4");
  rows[0].versao++;
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() =>
    document.getElementById("salesSourceStatus").textContent.includes("indisponível"),
  );
  assert.equal(products[0].estoque, 4);
  await page.evaluate(() => closeModal("createModal"));
  await page.evaluate(() => SocialMEISales.refresh());
  await page.evaluate((id) => openRecordConfirmation("sales", id, true), saleId);
  await page.locator("#reviewConfirmAction").click();
  await page.waitForFunction(() => appData.vendas[0].status === "Cancelado");
  assert.equal(products[0].estoque, 7);
  await page.waitForFunction(
    () =>
      !document.getElementById("reviewConfirm").classList.contains("open") &&
      !document.getElementById("recordModal").classList.contains("open"),
  );
  await second.evaluate(() => SocialMEISales.refresh());
  assert.equal(await second.evaluate(() => appData.vendas[0].status), "Cancelado");
  await page.evaluate(() => SocialMEISales.duplicate(appData.vendas[0]));
  const draft = rows.find((v) => v.status === "Rascunho");
  assert(draft);
  assert.equal(products[0].estoque, 7);
  await page.evaluate((id) => openRecord("sales", id), draft.id);
  await page.locator(`[data-sale-register="${draft.id}"]`).click();
  await page.waitForFunction(
    (id) => appData.vendas.find((v) => v.id === id)?.status === "Pendente",
    draft.id,
  );
  assert.equal(products[0].estoque, 4);
  await page.locator(`[data-sale-paid="${draft.id}"]`).first().click();
  await page.waitForFunction(
    (id) => appData.vendas.find((v) => v.id === id)?.status === "Pago",
    draft.id,
  );
  assert.equal(products[0].estoque, 4);
  await page.waitForFunction(() =>
    document.getElementById("salesSourceStatus").textContent.includes("conectado"),
  );
  await page.evaluate(() => closeModal("recordModal"));
  await page.evaluate(() => openCreate("venda"));
  await page.locator("#f_cliente").selectOption("11");
  await page.locator("#f_item").selectOption("22");
  loseResponse = true;
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() =>
    document.getElementById("salesSourceStatus").textContent.includes("indisponível"),
  );
  const length = rows.length;
  assert.equal(products[0].estoque, 4);
  await page.evaluate(() => closeModal("createModal"));
  await page.locator("[data-sales-recover]").click();
  await page.waitForFunction((n) => appData.vendas.length === n, length);
  assert.equal(rows.length, length);
  assert.equal(products[0].estoque, 4);
  for (let i = 0; i < 2; i++) {
    await page.locator("[data-sales-import]").click();
    await page.locator("#confirmSaleImport").click();
    await page.waitForFunction(
      () => !document.getElementById("saleImportModal").classList.contains("open"),
    );
  }
  assert.equal(rows.filter((v) => v.importada).length, 1);
  assert.equal(products[0].estoque, 4);
  await page.evaluate(() => {
    appData.prefs.test = true;
    saveAppData();
  });
  assert.deepEqual(
    await page.evaluate(() => JSON.parse(localStorage.getItem("socialmei-app-data-v2")).vendas),
    seed.vendas,
  );
  assert.equal(await page.evaluate(() => appData.financeiro.length), 0);
  await page.evaluate((id) => openRecordConfirmation("sales", id), draft.id);
  await page.locator("#reviewConfirmAction").click();
  await page.waitForFunction((id) => !appData.vendas.some((v) => v.id === id), draft.id);
  assert.equal(products[0].estoque, 7);
  await page.reload();
  await page.waitForFunction(() => appData.vendas.length === 3);
  assert.deepEqual(
    await page.evaluate(() => JSON.parse(localStorage.getItem("socialmei-app-data-v2")).vendas),
    seed.vendas,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => SocialMEIExperience.enterApp("Vendas"));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.close();
  await second.close();
  return "Vendas remotas: vínculos, estoque, edição, cancelamento, rascunho, pagamento, recuperação e histórico";
};
