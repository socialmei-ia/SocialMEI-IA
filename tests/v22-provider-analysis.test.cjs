const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = (path) => fs.readFileSync("frontend/scripts/" + path, "utf8");
const analysis = (extra = {}) => ({
  source: "automation",
  sentiment: "positive",
  confidence: "low",
  explanation: "Classificação de teste",
  ...extra,
});

function bridge() {
  let result = [];
  const context = {
    console,
    Date,
    location: { origin: "https://example.test" },
    SocialMEIAuth: {
      remote: true,
      ready: Promise.resolve(),
      current: {
        usuario: { id: 1, nome: "Teste" },
        negocio: { id: 17, nome: "Teste" },
        papel: "owner",
      },
      async request(path) {
        if (path.endsWith("/capabilities")) return { mode: "disabled", waha_inbox: true };
        if (path.endsWith("/conversations"))
          return { workspace_id: 17, items: structuredClone(result) };
        if (path === "/workspace-profile") return { profile: {} };
        if (path === "/auth/preferences") return { preferences: {} };
        return [];
      },
    },
    document: {
      hidden: false,
      getElementById: (id) => (id === "app" ? {} : null),
      querySelector: () => null,
      querySelectorAll: () => [],
    },
    S: { user: {}, biz: {} },
    A: {},
    SEL: {},
    C: [],
    CL: [],
    PR: [],
    V: [],
    F: [],
    T1: [],
    T2: [],
    PER: [],
    H: "/caixa",
    ini: (text) => text.slice(0, 1),
    esc: (text) => text,
    render() {},
    setInterval(callback) {
      context.poll = callback;
    },
  };
  context.window = context;
  vm.runInNewContext(source("v22-backend.js"), context);
  return {
    context,
    set(value) {
      result = value;
    },
    async poll() {
      context.poll();
      await new Promise(setImmediate);
    },
  };
}
const row = (provider_analysis) => ({
  id: 3,
  revision: 1,
  origin: "waha",
  channel: "whatsapp",
  contact_name: "Teste",
  account_ref: "waha:account",
  contact_ref: "waha:contact",
  messages: [{ id: 11, text: "Recebida", occurred_at: "2026-10-30T10:00:00Z", provider_analysis }],
});

test("CRM discards an in-flight refresh after workspace changes", async () => {
  const app = bridge();
  await app.context.SocialMEIV22.ready;
  let release;
  const pending = new Promise((resolve) => {
    release = resolve;
  });
  app.context.SocialMEIAuth.request = () => pending;
  const reading = app.context.SocialMEIV22.refresh();
  app.context.SocialMEIAuth.current.negocio.id = 18;
  release([{ id: 99, nome: "Previous workspace record" }]);
  await assert.rejects(reading, /sessão/i);
  assert.equal(app.context.CL.length, 0);
  assert.equal(app.context.SocialMEIV22.clients.length, 0);
});

test("CRM hides previously loaded clients after logout or workspace switch", async () => {
  const app = bridge();
  await app.context.SocialMEIV22.ready;
  app.context.SocialMEIAuth.request = async (path) =>
    path === "/clientes" ? [{ id: 99, nome: "Scoped client" }] : [];
  await app.context.SocialMEIV22.refresh();
  assert.equal(app.context.SocialMEIV22.clients.length, 1);
  app.context.SocialMEIAuth.current.negocio.id = 18;
  assert.equal(app.context.SocialMEIV22.clients.length, 0);
  app.context.SocialMEIAuth.current = null;
  assert.equal(app.context.SocialMEIV22.clients.length, 0);
});

test("CRM ignores a write completion after changing workspace or logging out", async () => {
  for (const logout of [false, true]) {
    const app = bridge();
    await app.context.SocialMEIV22.ready;
    let release;
    app.context.SocialMEIAuth.request = () =>
      new Promise((resolve) => {
        release = resolve;
      });
    const saving = app.context.SocialMEIV22.write("/clientes", "POST", { nome: "Original scope" });
    if (logout) app.context.SocialMEIAuth.current = null;
    else app.context.SocialMEIAuth.current.negocio.id = 18;
    release({ id: 99 });
    await assert.rejects(saving, /sessão/i);
  }
});

test("CRM refuses stale-form writes before contacting the new workspace", async () => {
  const app = bridge();
  await app.context.SocialMEIV22.ready;
  let writes = 0;
  app.context.SocialMEIAuth.request = async () => {
    writes++;
    return {};
  };
  app.context.SocialMEIAuth.current.negocio.id = 18;
  await assert.rejects(
    app.context.SocialMEIV22.write("/clientes", "POST", { nome: "Old form" }),
    /sessão/i,
  );
  assert.equal(writes, 0);
  app.context.SocialMEIAuth.current = null;
  await assert.rejects(
    app.context.SocialMEIV22.write("/produtos", "POST", { nome: "Old product" }),
    /sessão/i,
  );
  assert.equal(writes, 0);
});

test("CRM preserves the original pending receipt when a write finishes after a scope change", async () => {
  const app = bridge();
  await app.context.SocialMEIV22.ready;
  const storage = new Map();
  app.context.localStorage = {
    getItem: (key) => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  app.context.crypto = { randomUUID: () => "11111111-1111-4111-8111-111111111111" };
  let release;
  app.context.SocialMEIAuth.request = () =>
    new Promise((resolve) => {
      release = resolve;
    });
  const saving = app.context.SocialMEIV22.write("/vendas", "POST", { valor: 10 }, true);
  const key = "socialmei-v22-operation:1:17";
  const before = storage.get(key);
  assert.ok(before);
  app.context.SocialMEIAuth.current.negocio.id = 18;
  release({ id: 99 });
  await assert.rejects(saving, /sessão/i);
  assert.equal(storage.get(key), before);
  assert.equal(storage.has("socialmei-v22-operation:1:18"), false);
});

test("late, changed and removed analysis refreshes V22 without a new message", async () => {
  const app = bridge();
  app.set([row(null)]);
  await app.context.SocialMEIV22.ready;
  app.set([row(analysis())]);
  await app.poll();
  assert.equal(
    app.context.SocialMEIV22.conversation("me-3").messages[0].provider_analysis?.sentiment,
    "positive",
  );
  app.set([row(analysis({ sentiment: "negative", explanation: "Revisada" }))]);
  await app.poll();
  assert.equal(
    app.context.SocialMEIV22.conversation("me-3").messages[0].provider_analysis?.explanation,
    "Revisada",
  );
  app.set([row(null)]);
  await app.poll();
  assert.equal(app.context.SocialMEIV22.conversation("me-3").messages[0].provider_analysis, null);
});
test("conversation and thread exports hide previously read data after an identity switch", async () => {
  const app = bridge();
  app.set([row(analysis())]);
  await app.context.SocialMEIV22.ready;
  app.context.SocialMEIAuth.current = { ...app.context.SocialMEIAuth.current, usuario: { id: 2 } };
  assert.equal(app.context.SocialMEIV22.conversation("me-3"), null);
  assert.equal(app.context.SocialMEIV22.thread("me-3").length, 0);
});

function panelFixture(conversation) {
  const all = [];
  class Element {
    constructor(tag) {
      this.tagName = tag;
      this.children = [];
      this.dataset = {};
      this.style = {};
      all.push(this);
    }
    append(...nodes) {
      for (const node of nodes) {
        node.parent = this;
        this.children.push(node);
      }
    }
    setAttribute(name, value) {
      this[name] = value;
    }
    remove() {
      if (this.parent) this.parent.children = this.parent.children.filter((x) => x !== this);
      this.parent = null;
    }
    set innerHTML(_) {
      throw Error("Unsafe HTML sink");
    }
  }
  const thread = new Element("section"),
    head = new Element("head"),
    tasks = [];
  const host = {
    remote: true,
    identity: { usuario: { id: 1 }, negocio: { id: 17 } },
    conversation: () => conversation,
  };
  const window = { SocialMEIV22: host, render() {}, addEventListener() {} };
  const document = { head, createElement: (tag) => new Element(tag), querySelector: () => thread };
  const context = {
    window,
    document,
    Date,
    location: { hash: "#/caixa/me-3" },
    queueMicrotask: (fn) => tasks.push(fn),
  };
  const path = "frontend/scripts/v22-provider-analysis.js";
  vm.runInNewContext(fs.existsSync(path) ? fs.readFileSync(path, "utf8") : "", context);
  const flush = () => {
    while (tasks.length) tasks.shift()();
  };
  flush();
  return {
    host,
    all,
    thread,
    window,
    flush,
    text: () =>
      all
        .filter((n) => n.parent)
        .map((n) => n.textContent || "")
        .join(" "),
  };
}
test("analysis associates an exact incoming message and treats malicious strings as text", () => {
  const incoming = row(analysis({ explanation: "<img src=x onerror=alert(1)>" }));
  incoming.messages.push({
    ...incoming.messages[0],
    id: "direct-receipt",
    direction: "outgoing",
    text: "Resposta",
    provider_analysis: analysis(),
  });
  const app = panelFixture(incoming);
  assert.match(app.text(), /automação/);
  assert.match(app.text(), /<img src=x onerror=alert\(1\)>/);
  assert.equal(app.all.filter((n) => n.dataset.messageId).length, 1);
  assert.equal(app.all.find((n) => n.dataset.messageId).dataset.messageId, "11");
  assert.doesNotMatch(app.text(), /Resposta/);
});
test("invalid or non-provider analysis is hidden and absent metadata removes old panel", () => {
  for (const patch of [
    { source: "fixture" },
    { sentiment: "invented" },
    { confidence: "certain" },
    { explanation: "" },
    { explanation: 1 },
  ]) {
    const app = panelFixture(row(analysis(patch)));
    assert.equal(app.thread.children.length, 0);
  }
  for (const origin of ["synthetic", "unknown"]) {
    const app = panelFixture({ ...row(analysis()), origin });
    assert.equal(app.thread.children.length, 0);
  }
  const conversation = row(analysis());
  const app = panelFixture(conversation);
  assert.equal(app.thread.children.length, 1);
  conversation.messages[0].provider_analysis = null;
  app.window.render();
  app.flush();
  assert.equal(app.thread.children.length, 0);
});

test("Inbox backs off failed polling but permits an immediate refresh after workspace change", async () => {
  const app = bridge();
  await app.context.SocialMEIV22.ready;
  let reads = 0;
  app.context.SocialMEIAuth.request = async () => {
    reads++;
    throw Object.assign(new Error("Unavailable"), { status: 503 });
  };
  await app.poll();
  assert.equal(reads, 1);
  await app.poll();
  assert.equal(reads, 1);
  app.context.SocialMEIAuth.current.negocio.id = 18;
  await app.poll();
  assert.equal(reads, 2);
});

test("Inbox retry delay grows on failures, resets on success and pauses while hidden", async () => {
  const app = bridge();
  await app.context.SocialMEIV22.ready;
  let now = 100000;
  app.context.Date = class extends Date {
    static now() {
      return now;
    }
  };
  let reads = 0;
  let failing = true;
  app.context.SocialMEIAuth.request = async (path) => {
    reads++;
    if (failing) throw Object.assign(new Error("Unavailable"), { status: 503 });
    return path.endsWith("/capabilities")
      ? { mode: "disabled", waha_inbox: true }
      : { workspace_id: 17, items: [] };
  };
  await app.poll();
  now += 12000;
  await app.poll();
  assert.equal(reads, 2);
  now += 12000;
  await app.poll();
  assert.equal(reads, 2);
  now += 12000;
  failing = false;
  await app.poll();
  assert.equal(reads, 4);
  now += 6000;
  await app.poll();
  assert.equal(reads, 6);
  app.context.document.hidden = true;
  await app.poll();
  assert.equal(reads, 6);
});
