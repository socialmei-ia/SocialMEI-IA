const assert = require("node:assert/strict");

module.exports = async function remoteFlows(browser, origin, errors) {
  const rows = [],
    imports = new Map(),
    requests = [];
  let nextId = 100,
    unavailable = false;
  const seed = {
    schemaVersion: 1,
    clientes: [
      {
        id: 1,
        nome: "Local Importado",
        tags: ["MEI"],
        observacao: "Original",
        telefone: "11999990000",
        status: "Ativo",
      },
    ],
    vendas: [],
    financeiro: [],
    produtos: [],
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
      const request = route.request(),
        url = new URL(request.url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname.endsWith("/config.js"))
        return route.fulfill({
          contentType: "application/javascript",
          body: `const SOCIALMEI_CONFIG = Object.freeze({n8nMessagesUrl:"${origin}/disabled-n8n",n8nAuthHeader:null,clientes:{mode:"remote",apiBaseUrl:"${origin}/api/v1",workspaceKey:"qa"}});`,
        });
      if (!url.pathname.startsWith("/api/v1/")) return route.continue();
      let result,
        status = 200;
      const data = request.postDataJSON();
      requests.push({ path: url.pathname, method: request.method(), data, query: url.search });
      if (unavailable) return route.fulfill({ status: 503, json: { detail: "Offline" } });
      if (url.pathname.includes("/importacoes/")) {
        const items = data.itens.map((item) => {
          const key = data.origem + ":" + item.local_id,
            mapped = imports.get(key);
          const fingerprint = JSON.stringify(item);
          return {
            local_id: item.local_id,
            cliente_id: mapped?.id ?? null,
            acao: !mapped ? "criar" : mapped.fingerprint === fingerprint ? "existente" : "conflito",
          };
        });
        if (url.pathname.endsWith("/preview"))
          result = {
            origem: data.origem,
            itens: items,
            pode_importar: items.every((r) => r.acao !== "conflito"),
          };
        else if (items.some((r) => r.acao === "conflito")) {
          status = 409;
          result = {};
        } else {
          items.forEach((item, index) => {
            if (item.acao === "existente") return;
            const input = data.itens[index],
              row = { ...input.cliente, id: ++nextId, versao: 1, tags: input.cliente.tags || [] };
            rows.push(row);
            item.cliente_id = row.id;
            imports.set(data.origem + ":" + item.local_id, {
              id: row.id,
              fingerprint: JSON.stringify(input),
            });
          });
          result = { origem: data.origem, itens: items };
        }
      } else if (url.pathname === "/api/v1/clientes") result = rows;
      else {
        const id = Number(url.pathname.split("/").pop()),
          row = rows.find((r) => r.id === id);
        if (!row) {
          status = 404;
          result = {};
        } else if (request.method() === "PATCH") {
          if (data.expected_version !== row.versao) {
            status = 409;
            result = {};
          } else {
            const { expected_version, ...fields } = data;
            Object.assign(row, fields, { versao: row.versao + 1 });
            result = row;
          }
        } else if (request.method() === "DELETE") {
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
    await page.evaluate(() => SocialMEIExperience.enterApp("Clientes"));
    await page.waitForFunction(() =>
      document.getElementById("clientsSourceStatus").textContent.includes("conectado"),
    );
  }
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  await setup(page, true);
  assert.equal(await page.evaluate(() => appData.clientes.length), 0);
  await page.locator("[data-clients-import]").click();
  await page.locator("#confirmClientImport").click();
  await page.waitForFunction(() => appData.clientes.length === 1);
  await page.locator("[data-clients-import]").click();
  await page.locator("#confirmClientImport").click();
  await page.waitForFunction(
    () => !document.getElementById("clientImportModal").classList.contains("open"),
  );
  assert.equal(rows.length, 1);
  const originalStorage = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("socialmei-app-data-v2")),
  );
  assert.deepEqual(originalStorage.clientes, seed.clientes);

  await page.evaluate(() => openCreate("cliente"));
  await page.locator("#f_nome").fill("Criado na API");
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() => appData.clientes.length === 2);
  const createdId = rows.find((r) => r.nome === "Criado na API").id;
  await page.evaluate((id) => openRecordEditor("clients", id), createdId);
  await page.locator("#f_nome").fill("Tentativa desatualizada");
  rows.find((r) => r.id === createdId).versao++;
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() =>
    document.getElementById("clientsSourceStatus").textContent.includes("indisponível"),
  );
  assert.equal(rows.find((r) => r.id === createdId).nome, "Criado na API");
  assert.equal(await page.locator("#f_nome").inputValue(), "Tentativa desatualizada");
  await page.evaluate(() => closeModal("createModal"));
  await page.evaluate(() => SocialMEIClients.refresh());
  await page.evaluate((id) => openRecordEditor("clients", id), createdId);
  await page.locator("#f_nome").fill("Editado na API");
  await page.locator("#createSubmit").click();
  await page.waitForFunction(() => appData.clientes.some((c) => c.nome === "Editado na API"));
  assert(requests.some((r) => r.method === "PATCH" && r.data.expected_version === 2));

  await page.evaluate(() => {
    setView("Caixa Unificada");
    const c = sessionData.conversas[0];
    c.nome = "Local Importado";
    c.clientId = 1;
    selectConversation(c.id);
  });
  assert.equal(await page.evaluate(() => clientContext(getConversation()).client?.id), 101);
  await page.evaluate(() => finishTag("Remota"));
  assert(rows.find((r) => r.id === 101).tags.includes("Remota"));
  await page.evaluate(() => removeClientTag(getConversation(), "Remota"));
  assert(!rows.find((r) => r.id === 101).tags.includes("Remota"));
  await page.evaluate(() =>
    openInboxModal(
      "Perfil",
      createField("Nome", "nome", "text", { value: "Local Importado", required: true }),
      "Salvar",
      "profile",
    ),
  );
  await page.locator("#inbox_f_nome").fill("Perfil da Caixa remoto");
  await page.locator("#inboxModalSubmit").click();
  await page.waitForFunction(() =>
    appData.clientes.some((c) => c.nome === "Perfil da Caixa remoto"),
  );
  await page.evaluate(() =>
    openInboxModal(
      "Observação",
      createField("Observação", "observacao", "textarea", { value: "" }),
      "Salvar",
      "observation",
    ),
  );
  await page.locator("#inbox_f_observacao").fill("Observação compartilhada");
  await page.locator("#inboxModalSubmit").click();
  await page.waitForFunction(() =>
    appData.clientes.some((c) => c.observacao === "Observação compartilhada"),
  );
  assert.equal(rows.find((r) => r.id === 101).observacao, "Observação compartilhada");
  await page.evaluate(() => {
    appData.prefs.test = true;
    saveAppData();
  });
  assert.deepEqual(
    await page.evaluate(() => JSON.parse(localStorage.getItem("socialmei-app-data-v2")).clientes),
    seed.clientes,
  );
  assert.equal(await page.evaluate(() => SocialMEIClients.backup().clientes.length), 2);
  const second = await browser.newPage();
  await setup(second, false);
  assert.equal(
    await second.evaluate(() => appData.clientes.find((c) => c.id === 101).observacao),
    "Observação compartilhada",
  );
  unavailable = true;
  await page.evaluate(() => SocialMEIClients.refresh());
  assert.equal(
    await page.evaluate(() => appData.clientes.find((c) => c.id === 101).nome),
    "Perfil da Caixa remoto",
  );
  assert.equal(
    await page.evaluate(() => SocialMEIClients.update(appData.clientes[0], { nome: "Não salvar" })),
    null,
  );
  unavailable = false;
  await page.evaluate(() => SocialMEIClients.refresh());
  await page.evaluate((id) => openRecordConfirmation("clients", id), createdId);
  await page.locator("#reviewConfirmAction").click();
  await page.waitForFunction(() => appData.clientes.length === 1);
  await second.evaluate(() => SocialMEIClients.refresh());
  assert.equal(await second.evaluate(() => appData.clientes.length), 1);
  await page.reload();
  await page.waitForFunction(() => appData.clientes.length === 1);
  assert.deepEqual(
    await page.evaluate(() => JSON.parse(localStorage.getItem("socialmei-app-data-v2")).clientes),
    seed.clientes,
  );
  await page.close();
  await second.close();
  return "Modo remoto: importação idempotente, CRUD, Caixa, conflito, indisponibilidade e duas sessões";
};
