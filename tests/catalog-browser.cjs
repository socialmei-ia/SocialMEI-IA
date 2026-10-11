const assert = require("node:assert/strict");
module.exports = async function catalogFlows(browser, origin, errors) {
  const rows = [],
    imports = new Map(),
    requests = [];
  let nextId = 200,
    offline = false;
  const seed = {
    schemaVersion: 1,
    clientes: [],
    produtos: [
      {
        id: 1,
        nome: "Local catálogo",
        tipo: "Produto",
        preco: 12,
        custo: 4,
        estoque: 3,
        minimo: 1,
        status: "Ativo",
      },
    ],
    vendas: [],
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
          body: `const SOCIALMEI_CONFIG=Object.freeze({n8nMessagesUrl:"${origin}/disabled-n8n",n8nAuthHeader:null,clientes:{mode:"local"},produtos:{mode:"remote",apiBaseUrl:"${origin}/api/v1",workspaceKey:"qa"}});`,
        });
      if (!url.pathname.startsWith("/api/v1/produtos")) return route.continue();
      if (offline) return route.fulfill({ status: 503, json: {} });
      const data = req.postDataJSON();
      requests.push({ path: url.pathname, method: req.method(), data });
      let result,
        status = 200;
      if (url.pathname.includes("/importacoes/")) {
        const items = data.itens.map((i) => {
          const prior = imports.get(data.origem + ":" + i.local_id);
          return {
            local_id: i.local_id,
            produto_id: prior?.id ?? null,
            acao: !prior
              ? "criar"
              : prior.fingerprint === JSON.stringify(i)
                ? "existente"
                : "conflito",
          };
        });
        if (url.pathname.endsWith("/preview"))
          result = { itens: items, pode_importar: items.every((r) => r.acao !== "conflito") };
        else if (items.some((r) => r.acao === "conflito")) {
          status = 409;
          result = {};
        } else {
          items.forEach((item, index) => {
            if (item.acao === "existente") return;
            const input = data.itens[index],
              row = { ...input.produto, id: ++nextId, versao: 1 };
            rows.push(row);
            item.produto_id = row.id;
            imports.set(data.origem + ":" + item.local_id, {
              id: row.id,
              fingerprint: JSON.stringify(input),
            });
          });
          result = { itens: items };
        }
      } else if (url.pathname === "/api/v1/produtos") result = rows;
      else {
        const stock = url.pathname.endsWith("/estoque"),
          id = Number(url.pathname.split("/").at(stock ? -2 : -1));
        const row = rows.find((r) => r.id === id);
        if (!row) {
          status = 404;
          result = {};
        } else if (req.method() === "PATCH" || stock) {
          if (data.expected_version !== row.versao) {
            status = 409;
            result = {};
          } else if (stock && (row.tipo !== "Produto" || row.estoque + data.delta < 0)) {
            status = 409;
            result = {};
          } else {
            const { expected_version, ...fields } = data;
            Object.assign(row, stock ? { estoque: row.estoque + data.delta } : fields, {
              versao: row.versao + 1,
            });
            result = row;
          }
        } else if (req.method() === "DELETE") {
          if (Number(url.searchParams.get("expected_version")) !== row.versao) {
            status = 409;
            result = {};
          } else {
            rows.splice(rows.indexOf(row), 1);
            status = 204;
          }
        } else result = row;
      }
      return status === 204
        ? route.fulfill({ status, body: "" })
        : route.fulfill({ status, json: result });
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Produtos e Serviços"));
    await page.waitForFunction(() =>
      document.getElementById("productsSourceStatus").textContent.includes("conectado"),
    );
  }
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  await setup(page, true);
  assert.equal(await page.evaluate(() => appData.produtos.length), 0);
  for (let repeat = 0; repeat < 2; repeat++) {
    await page.locator("[data-products-import]").click();
    await page.locator("#confirmProductImport").click();
    await page.waitForFunction(
      () => !document.getElementById("productImportModal").classList.contains("open"),
    );
  }
  assert.equal(rows.length, 1);
  await page.evaluate(() => openCreate("produto"));
  for (const [id, value] of Object.entries({
    f_nome: "Produto remoto",
    f_preco: "30",
    f_custo: "8",
    f_estoque: "5",
    f_minimo: "2",
  }))
    await page.locator("#" + id).fill(value);
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() => appData.produtos.length === 2);
  const pid = rows.find((r) => r.nome === "Produto remoto").id;
  await page.evaluate((id) => openRecord("products", id), pid);
  await page.locator(`[data-adjust-stock="${pid}"][data-delta="1"]`).click();
  await page.waitForFunction((id) => appData.produtos.find((p) => p.id === id).estoque === 6, pid);
  await page.evaluate((id) => openRecordEditor("products", id), pid);
  await page.locator("#f_nome").fill("Editado remoto");
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() => appData.produtos.some((p) => p.nome === "Editado remoto"));
  await page.evaluate((id) => openRecordEditor("products", id), pid);
  await page.locator("#f_nome").fill("Rascunho antigo");
  rows.find((r) => r.id === pid).versao++;
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() =>
    document.getElementById("productsSourceStatus").textContent.includes("indisponível"),
  );
  assert.equal(rows.find((r) => r.id === pid).nome, "Editado remoto");
  assert.equal(await page.locator("#f_nome").inputValue(), "Rascunho antigo");
  await page.evaluate(() => closeModal("createModal"));
  await page.evaluate(() => SocialMEIProducts.refresh());
  await page.evaluate(() => openCreate("produto"));
  await page.locator("#f_tipo").selectOption("Serviço");
  await page.locator("#f_nome").fill("Serviço remoto");
  await page.locator("#f_preco").fill("50");
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() => appData.produtos.some((p) => p.nome === "Serviço remoto"));
  assert.equal(rows.find((r) => r.nome === "Serviço remoto").estoque, null);
  const second = await browser.newPage();
  await setup(second, false);
  assert.equal(
    await second.evaluate(() => appData.produtos.find((p) => p.nome === "Editado remoto").estoque),
    6,
  );
  await page.evaluate(() => {
    appData.prefs.test = true;
    saveAppData();
  });
  assert.deepEqual(
    await page.evaluate(() => JSON.parse(localStorage.getItem("socialmei-app-data-v2")).produtos),
    seed.produtos,
  );
  assert.equal(await page.evaluate(() => SocialMEIProducts.backup().produtos.length), 3);
  offline = true;
  await page.evaluate(() => SocialMEIProducts.refresh());
  assert.equal(
    await page.evaluate(() => SocialMEIProducts.adjustStock(appData.produtos[0], 1)),
    null,
  );
  offline = false;
  await page.evaluate(() => SocialMEIProducts.refresh());
  await page.evaluate((id) => openRecordConfirmation("products", id), pid);
  await page.locator("#reviewConfirmAction").click();
  await page.waitForFunction(() => appData.produtos.length === 2);
  await second.evaluate(() => SocialMEIProducts.refresh());
  assert.equal(await second.evaluate(() => appData.produtos.length), 2);
  await page.reload();
  await page.waitForFunction(() => appData.produtos.length === 2);
  assert.deepEqual(
    await page.evaluate(() => JSON.parse(localStorage.getItem("socialmei-app-data-v2")).produtos),
    seed.produtos,
  );
  assert(
    requests.some(
      (r) => r.path.endsWith("/estoque") && r.data.delta === 1 && r.data.expected_version === 1,
    ),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => SocialMEIExperience.enterApp("Produtos e Serviços"));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.close();
  await second.close();
  return "Catálogo remoto: importação, produto/serviço, CRUD, estoque, conflito, falha e duas sessões";
};
