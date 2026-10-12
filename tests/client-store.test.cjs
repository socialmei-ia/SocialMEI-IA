const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const crypto = require("node:crypto");
const source = fs.readFileSync(
  require("node:path").join(__dirname, "../frontend/scripts/client-store.js"),
  "utf8",
);
function setup(fetch, config = { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "qa" }) {
  const storage = new Map();
  const appData = {
    clientes: [{ id: 1, nome: "Local", tags: [] }],
    vendas: [],
    financeiro: [],
    prefs: {},
  };
  const context = vm.createContext({
    SOCIALMEI_CONFIG: { clientes: config },
    location: { href: "http://localhost/frontend/" },
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
    crypto,
    AbortController,
    setTimeout,
    clearTimeout,
    localStorage: { getItem: (k) => storage.get(k) || null },
    socialmeiStorageSet(k, v) {
      storage.set(k, v);
      return true;
    },
    appData,
    inboxLocalState: {},
    conversationKey: (c) => c.canal + ":" + c.nome.toLowerCase(),
    persistConversationState() {},
    fetch,
    saveAppData() {
      return true;
    },
  });
  vm.runInContext(source + "\nthis.store = SocialMEIClients", context);
  context.store.attach(appData);
  context.storage = storage;
  return context;
}
const client = { id: 101, versao: 2, nome: "Remoto", tags: [], telefone: null };
const reply = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
test("remote reads preserve local snapshot and never fall back on API failure", async () => {
  let fail = false;
  const ctx = setup(async () => (fail ? reply({}, 503) : reply([client])));
  assert.equal(ctx.appData.clientes.length, 0);
  assert(await ctx.store.refresh());
  assert.equal(ctx.appData.clientes[0].id, 101);
  assert.equal(ctx.store.localData(ctx.appData).clientes[0].id, 1);
  fail = true;
  assert.equal(await ctx.store.refresh(), null);
  assert.equal(ctx.appData.clientes[0].id, 101);
  assert.equal(await ctx.store.update(ctx.appData.clientes[0], { nome: "Mudança" }), null);
  assert.equal(ctx.store.localData(ctx.appData).clientes[0].nome, "Local");
});
test("stale remote edit sends expected version and preserves state on conflict", async () => {
  const requests = [];
  const ctx = setup(async (url, options) => {
    requests.push({ url, ...options });
    return options.method === "GET" ? reply([client]) : reply({}, 409);
  });
  await ctx.store.refresh();
  assert.equal(
    await ctx.store.update(ctx.appData.clientes[0], { nome: "Tentativa", campo: "omitido" }),
    null,
  );
  assert.deepEqual(JSON.parse(requests[1].body), { nome: "Tentativa", expected_version: 2 });
  assert.equal(ctx.appData.clientes[0].nome, "Remoto");
});
test("uncertain creation reuses its durable identity after refreshing", async () => {
  const origins = [];
  const payloads = [];
  let lost = true;
  const ctx = setup(async (url, options) => {
    if (url.endsWith("/confirmar")) {
      origins.push(JSON.parse(options.body).origem);
      payloads.push(JSON.parse(options.body));
      if (lost) {
        lost = false;
        throw new Error("Resposta perdida após commit");
      }
      return reply({ itens: [{ cliente_id: 101 }] });
    }
    return reply(url.endsWith("/101") ? client : [client]);
  });
  await ctx.store.refresh();
  assert.equal(await ctx.store.create({ nome: "Novo", tags: [] }), null);
  assert(ctx.storage.get("socialmei-client-create-pending-v1"));
  await ctx.store.refresh();
  assert.equal((await ctx.store.create({ nome: "Novo", tags: [] })).id, 101);
  assert.equal(origins[0], origins[1]);
  assert.equal(Number.isNaN(Date.parse(payloads[0].itens[0].cliente.criadoEm)), false);
  assert.deepEqual(payloads[0], payloads[1]);
  assert.equal(ctx.appData.clientes.length, 1);
  assert.equal(ctx.storage.get("socialmei-client-create-pending-v1"), "null");
});
test("remote conversation links do not interpret local IDs as remote IDs", async () => {
  const ctx = setup(async () => reply([{ ...client, id: 1 }]));
  await ctx.store.refresh();
  const conversation = { clientId: 1, nome: "Local", canal: "whatsapp" };
  assert.equal(ctx.store.conversationClient(conversation), undefined);
  ctx.store.link(conversation, ctx.appData.clientes[0]);
  assert.equal(ctx.store.conversationClient(conversation).nome, "Remoto");
  assert.equal(conversation.clientId, 1);
});
test("invalid remote config and invalid list never show local clients", async () => {
  let calls = 0;
  const bad = setup(
    async () => {
      calls++;
    },
    { mode: "remote", apiBaseUrl: "", workspaceKey: "qa" },
  );
  assert.equal(await bad.store.refresh(), null);
  assert.equal(calls, 0);
  assert.equal(bad.appData.clientes.length, 0);
  const broken = setup(async () => reply([{ nome: "Sem ID" }]));
  assert.equal(await broken.store.refresh(), null);
  assert.equal(broken.appData.clientes.length, 0);
});

test("LAN HTTP creation uses cryptographic UUID even without randomUUID", async () => {
  let origem;
  const ctx = setup(async (url, options) => {
    if (url.endsWith("/confirmar")) {
      origem = JSON.parse(options.body).origem;
      return reply({ itens: [{ cliente_id: 101 }] });
    }
    return reply(url.endsWith("/101") ? client : [client]);
  });
  ctx.crypto = { getRandomValues: (bytes) => crypto.webcrypto.getRandomValues(bytes) };
  await ctx.store.refresh();
  assert.equal((await ctx.store.create({ nome: "Celular", tags: [] })).id, 101);
  assert.match(origem, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});
