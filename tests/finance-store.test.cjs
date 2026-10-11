const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const { randomUUID } = require("node:crypto");
const source = fs.readFileSync(
  require("node:path").join(__dirname, "../frontend/scripts/finance-store.js"),
  "utf8",
);
const sale = {
  id: 101,
  versao: 1,
  cliente_id: 11,
  descricao: "Mensalidade",
  pessoa: "Maria",
  tipo: "receita",
  valor: 20,
  vencimento: "2026-10-11",
  status: "aberto",
  data_pagamento: null,
  importada: false,
  excluida: false,
};

const reply = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
function setup(fetch, configChanges = {}) {
  const storage = new Map();
  const config = { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "qa" };
  const context = vm.createContext({
    SOCIALMEI_CONFIG: { financeiro: config, clientes: config, produtos: config, ...configChanges },
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
      financeiro: [{ ...sale, id: 1, pessoa: "Local" }],
      clientes: [],
      produtos: [],
    },
  });
  vm.runInContext(source + "\nthis.store = SocialMEIFinance", context);
  context.store.attach(context.appData);
  context.storage = storage;
  return context;
}
test("remote finance preserve local snapshot and never write on outage", async () => {
  let offline = false;
  const ctx = setup(async () => (offline ? reply({}, 503) : reply([sale])));
  await ctx.store.refresh();
  assert.equal(ctx.appData.financeiro[0].id, 101);
  assert.equal(ctx.store.localData(ctx.appData).financeiro[0].id, 1);
  offline = true;
  assert.equal(await ctx.store.refresh(), null);
  assert.equal(await ctx.store.transition(sale, "pagar"), null);
  assert.equal(ctx.appData.financeiro[0].status, "aberto");
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
      descricao: "Mensalidade",
      pessoa: "Maria",
      tipo: "receita",
      valor: 20,
      vencimento: sale.vencimento,
    }),
    null,
  );
  assert(ctx.storage.get("socialmei-finance-operation-pending-v1"));
  assert.equal((await ctx.store.recover()).id, 101);
  assert.equal(ids[0], ids[1]);
  assert.equal(ctx.appData.financeiro.length, 1);
  assert.equal(ctx.storage.get("socialmei-finance-operation-pending-v1"), "null");
});
test("settlement conflicts retain state and clear rejected operation identity", async () => {
  let body;
  const ctx = setup(async (url, options) => {
    if (options.method === "GET") return reply([sale]);
    body = JSON.parse(options.body);
    return reply({ detail: "Lançamento alterado por outra sessão." }, 409);
  });
  await ctx.store.refresh();
  assert.equal(await ctx.store.transition(sale, "pagar"), null);
  assert.equal(body.expected_version, 1);
  assert.equal(ctx.appData.financeiro[0].status, "aberto");
  assert.equal(ctx.storage.get("socialmei-finance-operation-pending-v1"), "null");
});
test("finance requires clients at the same remote source", async () => {
  let calls = 0;
  const ctx = setup(
    async () => {
      calls++;
    },
    { clientes: { mode: "local" } },
  );
  assert.equal(await ctx.store.refresh(), null);
  assert.equal(calls, 0);
  assert.equal(ctx.appData.financeiro.length, 0);
});
test("remote finance link by IDs even when names collide", () => {
  const ctx = setup(async () => reply([]));
  assert.equal(ctx.store.matchesClient(sale, { id: 11, nome: "Nome diferente" }), true);
  assert.equal(ctx.store.matchesClient(sale, { id: 12, nome: "Maria" }), false);
});

test("accepted payment followed by read failure stays saved but blocks further writes", async () => {
  let committed = false;
  const ctx = setup(async (_url, options) => {
    if (options.method === "POST") {
      committed = true;
      return reply({ ...sale, status: "pago", versao: 2 });
    }
    return committed ? reply({}, 503) : reply([sale]);
  });
  await ctx.store.refresh();
  assert.equal((await ctx.store.transition(sale, "pagar")).status, "pago");
  assert.equal(ctx.appData.financeiro[0].status, "pago");
  assert.equal(await ctx.store.remove(ctx.appData.financeiro[0]), null);
  assert.equal(ctx.store.localData(ctx.appData).financeiro[0].status, "aberto");
});
test("unresolved finance identity survives reload and blocks a different operation", async () => {
  const ctx = setup(async (_url, options) =>
    options.method === "POST" ? Promise.reject(new Error("lost")) : reply([sale]),
  );
  await ctx.store.refresh();
  await ctx.store.transition(sale, "pagar");
  const saved = ctx.storage.get("socialmei-finance-operation-pending-v1");
  await ctx.store.refresh();
  assert.equal(await ctx.store.remove(sale), null);
  assert.equal(ctx.storage.get("socialmei-finance-operation-pending-v1"), saved);
});
