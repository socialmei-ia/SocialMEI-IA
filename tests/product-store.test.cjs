const assert = require("node:assert/strict");
const { test } = require("node:test");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const source = fs.readFileSync(
  path.join(__dirname, "../frontend/scripts/product-store.js"),
  "utf8",
);
const product = {
  id: 101,
  versao: 1,
  nome: "Remoto",
  tipo: "Produto",
  preco: 10,
  custo: 3,
  estoque: 5,
  minimo: 2,
  status: "Ativo",
};
const reply = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
function setup(fetch) {
  const storage = new Map();
  const context = vm.createContext({
    SOCIALMEI_CONFIG: { produtos: { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "qa" } },
    SocialMEIClients: { newId: randomUUID },
    location: { href: "http://192.168.0.3/frontend/" },
    URL,
    document: {
      addEventListener() {},
      getElementById() {
        return null;
      },
      querySelectorAll() {
        return [];
      },
      dispatchEvent() {},
    },
    cloneData: structuredClone,
    escapeHtml: String,
    toast() {},
    renderCurrentView() {},
    CustomEvent: class {},
    AbortController,
    setTimeout,
    clearTimeout,
    localStorage: { getItem: (k) => storage.get(k) || null },
    socialmeiStorageSet(k, v) {
      storage.set(k, v);
      return true;
    },
    fetch,
    appData: {
      produtos: [{ ...product, id: 1, nome: "Local" }],
      clientes: [{ id: 1, nome: "Cliente" }],
    },
  });
  vm.runInContext(source + "\nthis.store = SocialMEIProducts", context);
  context.store.attach(context.appData);
  context.storage = storage;
  return context;
}
test("catalog remote list preserves local snapshot and blocks writes after outage", async () => {
  let offline = false;
  const ctx = setup(async () => (offline ? reply({}, 503) : reply([product])));
  assert.equal(ctx.appData.produtos.length, 0);
  await ctx.store.refresh();
  assert.equal(ctx.appData.produtos[0].id, 101);
  assert.equal(ctx.store.localData(ctx.appData).produtos[0].id, 1);
  assert.equal(ctx.store.localData(ctx.appData).clientes[0].nome, "Cliente");
  offline = true;
  assert.equal(await ctx.store.refresh(), null);
  assert.equal(await ctx.store.adjustStock(ctx.appData.produtos[0], 1), null);
  assert.equal(ctx.appData.produtos[0].estoque, 5);
});
test("stock conflict sends version and delta without mutating local or displayed stock", async () => {
  let sent;
  const ctx = setup(async (url, options) => {
    if (options.method === "GET") return reply([product]);
    sent = JSON.parse(options.body);
    return reply({}, 409);
  });
  await ctx.store.refresh();
  assert.equal(await ctx.store.adjustStock(ctx.appData.produtos[0], -1), null);
  assert.deepEqual(sent, { delta: -1, expected_version: 1 });
  assert.equal(ctx.appData.produtos[0].estoque, 5);
  assert.equal(ctx.store.localData(ctx.appData).produtos[0].estoque, 5);
});
test("catalog creation retries durable origin after a lost response", async () => {
  let lost = true;
  const origins = [];
  const ctx = setup(async (url, options) => {
    if (url.endsWith("/confirmar")) {
      const data = JSON.parse(options.body);
      origins.push(data.origem);
      assert.equal(data.itens[0].produto.nome, "Novo");
      if (lost) {
        lost = false;
        throw new Error("Resposta perdida");
      }
      return reply({ itens: [{ produto_id: 101 }] });
    }
    return reply(url.endsWith("/101") ? product : [product]);
  });
  const fields = { nome: "Novo", tipo: "Produto", preco: 10, custo: 3, estoque: 5, minimo: 2 };
  await ctx.store.refresh();
  assert.equal(await ctx.store.create(fields), null);
  await ctx.store.refresh();
  assert.equal((await ctx.store.create(fields)).id, 101);
  assert.equal(origins[0], origins[1]);
  assert.equal(ctx.appData.produtos.length, 1);
});
test("catalog rejects malformed inventory and accepts service without stock", async () => {
  const broken = setup(async () => reply([{ ...product, estoque: -1 }]));
  assert.equal(await broken.store.refresh(), null);
  assert.equal(broken.appData.produtos.length, 0);
  const service = setup(async () =>
    reply([{ ...product, tipo: "Serviço", estoque: null, minimo: null }]),
  );
  assert(await service.store.refresh());
  assert.equal(service.appData.produtos[0].estoque, null);
});
