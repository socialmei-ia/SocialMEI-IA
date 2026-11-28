const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend/socialmei-app.html"), "utf8");

const native = fs.readFileSync(path.join(root, "frontend/scripts/v22-native.js"), "utf8");
const css = fs.readFileSync(path.join(root, "frontend/styles/app-base.css"), "utf8");

test("V22 workspace preserves native shell, tabs and identity-gated bootstrap", () => {
  assert.match(html, /<div id="app"><\/div>/);
  assert.doesNotMatch(html, /id="v22-native-source"/);
  assert.match(native, /function nhead\(tab\)/);
  assert.match(native, /Resumo','Vendas','Clientes','Produtos','Financeiro/);
  const scripts = [...html.matchAll(/<script[^>]*src="([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(scripts.slice(0, 2), ["config.js", "scripts/auth-store.js"]);
  assert(scripts.indexOf("scripts/v22-bootstrap.js") < scripts.indexOf("scripts/v797-evolucao.js"));
  const bootstrap = fs.readFileSync(path.join(root, "frontend/scripts/v22-bootstrap.js"), "utf8");
  assert.match(bootstrap, /await auth.ready/);
  assert.match(bootstrap, /scripts\/v22-backend\.js/);
});

test("V22 workspace keeps each operational view and searchable record actions", () => {
  for (const name of ["vendas", "clientes", "produtos", "financeiro"])
    assert.match(native, new RegExp("function " + name + "\\(\\)"));
  assert(native.includes('data-a="novo:${a[0]}"'));
  for (const kind of ["venda", "cliente", "produto", "lanc"])
    assert(native.includes("if(k==='" + kind + "')"), kind);
  for (const action of ["edit:cli", "edit:prod"])
    assert(native.includes('data-a="' + action + '"'), action);
  for (const placeholder of [
    "Buscar por nome ou e-mail",
    "Buscar por nome ou código",
    "Buscar lançamento",
  ])
    assert(native.includes(placeholder), placeholder);
  assert.match(native, /const search=\(q,ph\)=>/);
  assert.match(native, /data-q="\$\{q\}"/);
  assert.match(native, /function filt\(inp\)/);
});

test("V22 workspace retains keyboard, mobile and reduced-motion rules", () => {
  assert.match(css, /:focus-visible/);
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /prefers-reduced-motion:reduce/);
  assert.match(css, /\.tb/);
  assert.match(native, /data-a="edit:cli"/);
  assert.match(native, /data-a="edit:prod"/);
});

function inboxBridge(request) {
  const vm = require("node:vm");
  const app = { hidden: false };
  const context = {
    console,
    Date,
    location: { origin: "https://example.test" },
    SocialMEIAuth: {
      remote: true,
      ready: Promise.resolve(),
      current: {
        usuario: { id: 1, nome: "Teste", email: "test@example.test" },
        negocio: { id: 17, nome: "Negócio de teste" },
        papel: "owner",
      },
      request: (path) => {
        if (path.startsWith("/message-enrichment/")) return request(path, context);
        if (path === "/workspace-profile") return Promise.resolve({ profile: {} });
        if (path === "/auth/preferences") return Promise.resolve({ preferences: {} });
        return Promise.resolve([]);
      },
    },
    document: {
      hidden: false,
      getElementById: (id) => (id === "app" ? app : null),
      querySelector: () => null,
      querySelectorAll: () => [],
    },
    S: { user: {}, biz: {} },
    A: {},
    SEL: {},
    C: [["demo", "Contato fictício"]],
    CL: [],
    PR: [],
    V: [],
    F: [],
    T1: [],
    T2: [],
    PER: [],
    H: "/caixa",
    ini: (name) => name.slice(0, 1),
    esc: (value) => value,
    render: () => {},
    setInterval: (callback) => {
      context.poll = callback;
    },
  };
  context.window = context;
  vm.runInNewContext(
    fs.readFileSync(path.join(root, "frontend/scripts/v22-backend.js"), "utf8"),
    context,
  );
  context.tick = async () => {
    context.poll();
    await new Promise((resolve) => setImmediate(resolve));
  };
  return context;
}

const inboxRow = (text = "Mensagem do Direct") => ({
  id: 1,
  revision: 1,
  contact_name: "Contato Instagram",
  channel: "instagram",
  messages: [{ id: 2, text, occurred_at: "2026-10-26T10:00:00Z" }],
});

test("V22 remote inbox clears demonstration and disabled provider rows", async () => {
  let enabled = false;
  const ctx = inboxBridge(async (path) =>
    path.endsWith("capabilities")
      ? { mode: "disabled", instagram_inbox: enabled }
      : { workspace_id: 17, items: [inboxRow()] },
  );
  await ctx.SocialMEIV22.ready;
  assert.equal(ctx.C.length, 0, "Remote accounts never display demo conversations");
  let now = Date.now();
  ctx.Date = class extends Date {
    static now() {
      return now;
    }
  };
  now += 60000;
  enabled = true;
  await ctx.tick();
  assert.equal(ctx.C[0][5], "Mensagem do Direct");
  now += 60000;
  enabled = false;
  await ctx.tick();
  assert.equal(ctx.C.length, 0, "Revoked capability removes previously loaded conversations");
  assert.equal(ctx.SocialMEIV22.thread("me-1").length, 0);
});

test("V22 polling discards a response when the user changes within the workspace", async () => {
  let release;
  const ctx = inboxBridge(async (path) =>
    path.endsWith("capabilities")
      ? { mode: "disabled", instagram_inbox: true }
      : release
        ? new Promise((resolve) => {
            release.resolve = resolve;
          })
        : { workspace_id: 17, items: [] },
  );
  await ctx.SocialMEIV22.ready;
  release = {};
  ctx.poll();
  await new Promise((resolve) => setImmediate(resolve));
  ctx.SocialMEIAuth.current = {
    ...ctx.SocialMEIAuth.current,
    usuario: { ...ctx.SocialMEIAuth.current.usuario, id: 2 },
    papel: "viewer",
  };
  release.resolve({ workspace_id: 17, items: [inboxRow("Resposta da sessão anterior")] });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(ctx.C.length, 0);
  assert.equal(
    ctx.SocialMEIV22.identity.papel,
    "viewer",
    "Preserve the real session role contract",
  );
});

test("V22 polling observes visibility, prevents overlap and recovers after failure", async () => {
  let reads = 0,
    fail = false,
    release;
  const ctx = inboxBridge(async (path) => {
    if (path.endsWith("capabilities")) return { mode: "disabled", instagram_inbox: true };
    reads++;
    if (fail) throw Object.assign(Error("Unavailable"), { status: 503 });
    if (release)
      return new Promise((resolve) => {
        release.resolve = resolve;
      });
    return { workspace_id: 17, items: [inboxRow()] };
  });
  await ctx.SocialMEIV22.ready;
  assert.equal(reads, 1);
  ctx.document.hidden = true;
  await ctx.tick();
  assert.equal(reads, 1);
  ctx.document.hidden = false;
  release = {};
  await ctx.tick();
  await ctx.tick();
  assert.equal(reads, 2);
  release.resolve({ workspace_id: 17, items: [inboxRow()] });
  await new Promise((resolve) => setImmediate(resolve));
  release = null;
  let now = 100000;
  ctx.Date = class extends Date {
    static now() {
      return now;
    }
  };
  fail = true;
  await ctx.tick();
  fail = false;
  await ctx.tick();
  assert.equal(reads, 3, "Failure backoff prevents an immediate automatic retry");
  now += 12000;
  await ctx.tick();
  assert.equal(reads, 4);
  assert.equal(ctx.C[0][5], "Mensagem do Direct");
});
