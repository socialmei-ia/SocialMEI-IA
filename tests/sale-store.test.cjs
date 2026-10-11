const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const { randomUUID } = require("node:crypto");
const source = fs.readFileSync(
  require("node:path").join(__dirname, "../frontend/scripts/sale-store.js"),
  "utf8",
);
const sale = {
  id: 101,
  versao: 1,
  cliente_id: 11,
  produto_id: 21,
  cliente: "Maria",
  item: "Produto",
  data: "2026-10-11",
  quantidade: 2,
  preco: 10,
  desconto: 0,
  valor: 20,
  pagamento: "Pix",
  observacao: "",
  status: "Pendente",
  importada: false,
  excluida: false,
  estoque_aplicado: true,
};
const reply = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
function setup(fetch, configChanges = {}) {
  const storage = new Map();
  const config = { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "qa" };
  const context = vm.createContext({
    SOCIALMEI_CONFIG: { vendas: config, clientes: config, produtos: config, ...configChanges },
    SocialMEIClients: { newId: randomUUID, localData: (d) => d },
    SocialMEIProducts: { refresh: async () => true, localData: (d) => d },
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
    normalizedText: (s) => String(s || "").toLowerCase(),
    todayISO: () => "2026-10-11",
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
      vendas: [{ ...sale, id: 1, cliente: "Local" }],
      clientes: [],
      produtos: [],
      financeiro: [],
    },
  });
  vm.runInContext(source + "\nthis.store = SocialMEISales", context);
  context.store.attach(context.appData);
  context.storage = storage;
  return context;
}
test("remote sales preserve local snapshot and never write on outage", async () => {
  let offline = false;
  const ctx = setup(async () => (offline ? reply({}, 503) : reply([sale])));
  await ctx.store.refresh();
  assert.equal(ctx.appData.vendas[0].id, 101);
  assert.equal(ctx.store.localData(ctx.appData).vendas[0].id, 1);
  offline = true;
  assert.equal(await ctx.store.refresh(), null);
  assert.equal(await ctx.store.transition(sale, "cancelar"), null);
  assert.equal(ctx.appData.vendas[0].status, "Pendente");
});
test("lost create response can recover without a second operation identity", async () => {
  let lost = true,
    accepted = false;
  const ids = [];
  const ctx = setup(async (url, options) => {
    if (options.method === "POST") {
      ids.push(JSON.parse(options.body).operation_id);
      accepted = true;
      if (lost) {
        lost = false;
        throw new Error("Resposta perdida após commit");
      }
      return reply(sale, 201);
    }
    return reply(accepted ? [sale] : []);
  });
  await ctx.store.refresh();
  assert.equal(
    await ctx.store.create({
      cliente_id: 11,
      produto_id: 21,
      data: sale.data,
      quantidade: 2,
      preco: 10,
    }),
    null,
  );
  assert(ctx.storage.get("socialmei-sale-operation-pending-v1"));
  assert.equal((await ctx.store.recover()).id, 101);
  assert.equal(ids[0], ids[1]);
  assert.equal(ctx.appData.vendas.length, 1);
  assert.equal(ctx.storage.get("socialmei-sale-operation-pending-v1"), "null");
});
test("sale cancellation conflicts retain state and clear rejected operation identity", async () => {
  let body;
  const ctx = setup(async (url, options) => {
    if (options.method === "GET") return reply([sale]);
    body = JSON.parse(options.body);
    return reply({ detail: "Venda alterada por outra sessão." }, 409);
  });
  await ctx.store.refresh();
  assert.equal(await ctx.store.transition(sale, "cancelar"), null);
  assert.equal(body.expected_version, 1);
  assert.equal(ctx.appData.vendas[0].status, "Pendente");
  assert.equal(ctx.storage.get("socialmei-sale-operation-pending-v1"), "null");
});
test("sales require the same remote source for client and catalog", async () => {
  let calls = 0;
  const ctx = setup(
    async () => {
      calls++;
    },
    { produtos: { mode: "local" } },
  );
  assert.equal(await ctx.store.refresh(), null);
  assert.equal(calls, 0);
  assert.equal(ctx.appData.vendas.length, 0);
});
test("remote sales link by IDs even when names collide", () => {
  const ctx = setup(async () => reply([]));
  assert.equal(ctx.store.matchesClient(sale, { id: 11, nome: "Nome diferente" }), true);
  assert.equal(ctx.store.matchesClient(sale, { id: 12, nome: "Maria" }), false);
  assert.equal(ctx.store.matchesProduct(sale, { id: 22, nome: "Produto" }), false);
});
