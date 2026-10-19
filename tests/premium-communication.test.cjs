const { test } = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs"),
  vm = require("node:vm"),
  path = require("node:path");
test("demo conversations cannot inherit drafts, notes or state of a real contact with the same name", () => {
  const source = fs.readFileSync(path.join(__dirname, "../frontend/scripts/inbox.js"), "utf8");
  const context = vm.createContext({});
  vm.runInContext(
    source.slice(
      source.indexOf("function conversationKey("),
      source.indexOf("function isReducedMotion("),
    ),
    context,
  );
  const real = { canal: "whatsapp", nome: "Pessoa QA" },
    sample = { ...real, _socialmeiDemoSample: true };
  assert.equal(context.conversationKey(real), "whatsapp:pessoa qa");
  assert.equal(context.conversationKey(sample), "demo:whatsapp:pessoa qa");
  assert.notEqual(context.conversationKey(real), context.conversationKey(sample));
  let reads = 0;
  context.SocialMEIClients = {
    conversationClient() {
      reads++;
      return { id: 701, nome: "Pessoa QA" };
    },
  };
  context.SocialMEISales = { matchesClient: (sale, client) => sale.cliente_id === client.id };
  context.appData = { vendas: [{ cliente_id: 701, data: "2026-10-19", valor: 100 }] };
  vm.runInContext(
    source.slice(
      source.indexOf("function clientContext("),
      source.indexOf("function renderDetails("),
    ),
    context,
  );
  assert.equal(context.clientContext(real).client.id, 701);
  assert.equal(context.clientContext(real).purchases.length, 1);
  const priorReads = reads;
  assert.equal(context.clientContext(sample).client, null);
  assert.equal(context.clientContext(sample).purchases.length, 0);
  assert.equal(reads, priorReads, "A sample must not even query the real CRM by name");
});
test("feedback uses status for real success/info and alert for failures, escaping dynamic text", () => {
  const source = fs.readFileSync(path.join(__dirname, "../frontend/scripts/dialogs.js"), "utf8"),
    nodes = [];
  const context = vm.createContext({
    document: {
      createElement() {
        return {
          dataset: {},
          style: {},
          attrs: {},
          setAttribute(k, v) {
            this.attrs[k] = v;
          },
          addEventListener() {},
          remove() {},
        };
      },
    },
    $: () => ({
      appendChild(n) {
        nodes.push(n);
      },
    }),
    renderIcon: (type) => '<svg data-icon="' + type + '"></svg>',
    escapeHtml: (t) => String(t).replace(/</g, "&lt;"),
    window: { SocialMEIMotion: { ms: () => 100, reduced: false } },
    performance: { now: () => 0 },
    TOAST_TIMERS: new Set(),
    setTimeout: () => 1,
    clearTimeout() {},
  });
  vm.runInContext(
    source.slice(
      source.indexOf("function toast("),
      source.indexOf("function openRecord(", source.indexOf("function toast(")),
    ),
    context,
  );
  context.toast("Dados de teste ativados", "", "info");
  assert.equal(nodes[0].attrs.role, "status");
  assert.equal(nodes[0].dataset.tone, "info");
  context.toast("Não foi possível salvar", "<script>");
  assert.equal(nodes[1].attrs.role, "alert");
  assert.equal(nodes[1].dataset.tone, "error");
  assert(nodes[1].innerHTML.includes("&lt;script>"));
  context.toast("Registro salvo");
  assert.equal(nodes[2].dataset.tone, "success");
  context.toast("Backup inválido");
  assert.equal(nodes[3].attrs.role, "alert");
  context.toast("Item de ferro salvo");
  assert.equal(nodes[4].dataset.tone, "success");
});

test("sample refresh honors new and legacy removals without importing real contact state", () => {
  const inbox = fs.readFileSync(path.join(__dirname, "../frontend/scripts/inbox.js"), "utf8"),
    app = fs.readFileSync(path.join(__dirname, "../frontend/scripts/app.js"), "utf8");
  const context = vm.createContext({
    structuredClone,
    SocialMEIAuth: { remote: false },
    SocialMEIDemoData: { enabled: () => true },
    sessionData: {
      conversas: [{ id: 7, nome: "Pessoa QA", canal: "whatsapp" }],
      atividade: [],
      notificacoes: [],
    },
    legacySessionExamples: {
      conversas: [{ id: 7, nome: "Pessoa QA", canal: "whatsapp", status: "aberto" }],
      atividade: [],
      notificacoes: [],
    },
    inboxLocalState: { "state:whatsapp:pessoa qa": { status: "concluido" } },
    activeConversationId: null,
    conversationActivitySequence: 0,
  });
  context.businessViewData = () => ({
    conversations: context.legacySessionExamples.conversas,
    atividade: context.legacySessionExamples.atividade,
    notificacoes: context.legacySessionExamples.notificacoes,
  });
  context.initialsFromName = () => "PQ";
  context.getConversation = () => null;
  vm.runInContext(
    inbox.slice(
      inbox.indexOf("function conversationKey("),
      inbox.indexOf("function isReducedMotion("),
    ),
    context,
  );
  vm.runInContext(
    app.slice(
      app.indexOf("function syncLegacySessionExamples("),
      app.indexOf("syncLegacySessionExamples();"),
    ),
    context,
  );
  context.syncLegacySessionExamples();
  assert.equal(context.sessionData.conversas.length, 2);
  assert.equal(context.sessionData.conversas[1].status, "aberto");
  assert.notEqual(context.sessionData.conversas[0].id, context.sessionData.conversas[1].id);
  for (const key of ["demo:whatsapp:pessoa qa", "whatsapp:pessoa qa"]) {
    context.sessionData.conversas = context.sessionData.conversas.filter(
      (row) => !row._socialmeiDemoSample,
    );
    context.inboxLocalState.removedDemoConversations = [key];
    context.syncLegacySessionExamples();
    assert.equal(context.sessionData.conversas.length, 1);
    assert.equal(context.sessionData.conversas[0]._socialmeiDemoSample, undefined);
  }
});

test("sample or active demo cannot create or update a CRM client, even through direct calls", async () => {
  const source = fs.readFileSync(path.join(__dirname, "../frontend/scripts/inbox.js"), "utf8");
  let active = false,
    writes = 0;
  const context = vm.createContext({
    SocialMEIDemoData: { enabled: () => active },
    toast() {},
    SocialMEIClients: {
      remote: true,
      async create() {
        writes++;
      },
      async update() {
        writes++;
      },
    },
    clientContext() {
      throw Error("A demo must stop before reading the real CRM");
    },
  });
  vm.runInContext(
    source.slice(
      source.indexOf("async function ensureContextClient("),
      source.indexOf("function renderContextHistory("),
    ),
    context,
  );
  assert.equal(await context.ensureContextClient({ _socialmeiDemoSample: true }), null);
  active = true;
  assert.equal(
    await context.ensureContextClient({ nome: "Contato real" }, { nome: "Alteração indevida" }),
    null,
  );
  assert.equal(writes, 0);
});
