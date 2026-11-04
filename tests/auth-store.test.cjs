const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(
  require("node:path").join(__dirname, "../frontend/scripts/auth-store.js"),
  "utf8",
);
function storage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    get length() {
      return data.size;
    },
    key: (i) => [...data.keys()][i],
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    data,
  };
}
const identity = (id) => ({
  usuario: { id, email: `${id}@example.com`, nome: "Person", administrador_plataforma: false },
  negocio: { id, slug: "mei-" + id, nome: "Business", configuracao: {} },
  csrf_token: "a".repeat(64),
});
const reply = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
function setup(
  fetch,
  config = { mode: "remote", apiBaseUrl: "/api/v1" },
  local = storage(),
  session = storage(),
  entry = {},
) {
  let reloads = 0;
  const requests = [];
  const events = {};
  const context = vm.createContext({
    SOCIALMEI_CONFIG: { auth: config },
    window: {
      addEventListener: (name, callback) => {
        events[name] = callback;
      },
    },
    localStorage: local,
    sessionStorage: session,
    location: {
      href: "https://app.example.com/frontend/socialmei-app.html",
      origin: "https://app.example.com",
      pathname: "/frontend/socialmei-app.html",
      hash: "",
      reload() {
        reloads++;
      },
      ...entry,
    },
    URL,
    AbortController,
    setTimeout,
    clearTimeout,
    fetch: async (url, options) => {
      requests.push({ url, options });
      return fetch(url, options);
    },
  });
  vm.runInContext(source + "\nthis.auth=SocialMEIAuth", context);
  return {
    auth: context.auth,
    requests,
    local,
    location: context.location,
    events,
    get reloads() {
      return reloads;
    },
  };
}
test("public demo never calls the account API", async () => {
  const local = setup(
    () => {
      throw Error("must not fetch");
    },
    { mode: "local" },
  );
  assert.equal(await local.auth.ready, null);
  assert.equal(local.auth.remote, false);
});
test("invalid cross-origin authentication fails closed without a fallback", async () => {
  const ctx = setup(
    () => {
      throw Error("must not fetch");
    },
    { mode: "remote", apiBaseUrl: "https://evil.example/api/v1" },
  );
  assert.equal(await ctx.auth.ready, null);
  assert.equal(ctx.auth.remote, true);
  assert(ctx.auth.problem);
  assert.equal(ctx.requests.length, 0);
});
test("remote bootstrap ignores the local demo session", async () => {
  const ctx = setup(() => reply(null));
  assert.equal(await ctx.auth.ready, null);
  assert.equal(ctx.auth.current, null);
  assert.equal(ctx.reloads, 0);
  assert.equal(ctx.requests[0].options.credentials, "same-origin");
  assert.equal(ctx.requests[0].options.cache, "no-store");
  assert(ctx.requests[0].url.endsWith("/auth/session"));
});
test("Basic refusal is not mistaken for an anonymous application session", async () => {
  const ctx = setup(() => reply(null, 401));
  assert.equal(await ctx.auth.ready, null);
  assert(ctx.auth.problem);
  assert.equal(ctx.reloads, 0);
});
test("switching accounts archives previous work and reloads before exposing data", async () => {
  const local = storage({
    "socialmei-auth-browser-scope": "1:1",
    "socialmei-app-data-v2": "previous-private-work",
    foreign: "keep",
    "socialmei-account-state-2:2": JSON.stringify({
      "socialmei-app-data-v2": "second-work",
      foreign: "ignored",
    }),
  });
  const ctx = setup(() => reply(identity(2)), { mode: "remote", apiBaseUrl: "/api/v1" }, local);
  assert.equal(await ctx.auth.ready, null);
  assert.equal(ctx.auth.current, null);
  assert.equal(ctx.reloads, 1);
  assert.equal(local.getItem("socialmei-app-data-v2"), "second-work");
  assert.equal(local.getItem("foreign"), "keep");
  assert.equal(
    JSON.parse(local.getItem("socialmei-account-state-1:1"))["socialmei-app-data-v2"],
    "previous-private-work",
  );
  assert.equal(local.getItem("socialmei-auth-browser-scope"), "2:2");
});
test("authenticated writes use CSRF and passwords never enter storage", async () => {
  const local = storage({ "socialmei-auth-browser-scope": "1:1" });
  const ctx = setup((url) => reply(identity(1)), { mode: "remote", apiBaseUrl: "/api/v1" }, local);
  assert.equal((await ctx.auth.ready).usuario.id, 1);
  await ctx.auth.request("/auth/password", "POST", { atual: "old-private", nova: "new-private" });
  const options = ctx.requests.at(-1).options;
  assert.equal(options.headers["X-SocialMEI-CSRF"], "a".repeat(64));
  assert.equal(options.headers["X-SocialMEI-Client"], "browser");
  assert(!JSON.stringify([...local.data]).includes("private"));
  assert(!JSON.stringify([...local.data]).includes("csrf_token"));
});

test("expired recovery link isolates old account state without reloading away its in-memory token", async () => {
  const local = storage({
    "socialmei-auth-browser-scope": "1:1",
    "socialmei-private-work": "preserve-old-account",
  });
  let complete;
  const ctx = setup(
    () => new Promise((resolve) => (complete = resolve)),
    { mode: "remote", apiBaseUrl: "/api/v1" },
    local,
    storage(),
    { pathname: "/frontend/entrada.html", hash: "#/recuperar/" + "T".repeat(43) },
  );
  // entrada.js erases the token fragment while the session request is pending.
  ctx.location.hash = "#/recuperar";
  complete(reply(null));
  assert.equal(await ctx.auth.ready, null);
  assert.equal(ctx.auth.current, null);
  assert.equal(ctx.reloads, 0);
  assert.equal(local.getItem("socialmei-auth-browser-scope"), "");
  assert.equal(local.getItem("socialmei-private-work"), null);
  assert.equal(
    JSON.parse(local.getItem("socialmei-account-state-1:1"))["socialmei-private-work"],
    "preserve-old-account",
  );
  assert(!JSON.stringify([...local.data]).includes("T".repeat(43)));
});

test("normal entry still reloads when the server identity changes", async () => {
  const local = storage({ "socialmei-auth-browser-scope": "1:1" });
  const ctx = setup(
    () => reply(null),
    { mode: "remote", apiBaseUrl: "/api/v1" },
    local,
    storage(),
    { pathname: "/frontend/entrada.html", hash: "#/entrar" },
  );
  await ctx.auth.ready;
  assert.equal(ctx.reloads, 1);
});
test("invalid password response does not change account state or reload", async () => {
  const ctx = setup((url) =>
    url.endsWith("/auth/session")
      ? reply(null)
      : reply({ detail: "E-mail ou senha inválidos." }, 400),
  );
  await ctx.auth.ready;
  await assert.rejects(
    ctx.auth.login({ email: "a@example.com", senha: "private-password" }),
    /E-mail ou senha/,
  );
  assert.equal(ctx.reloads, 0);
  assert.equal(ctx.local.getItem("socialmei-auth-browser-scope"), null);
});
test("logout clears presentation state and expired bootstrap cannot restore an app session", async () => {
  const local = storage({
    "socialmei-auth-browser-scope": "1:1",
    "socialmei-theme-v1": "private-theme",
  });
  const ctx = setup(
    (url) => (url.endsWith("/auth/session") ? reply(identity(1)) : reply(null, 204)),
    { mode: "remote", apiBaseUrl: "/api/v1" },
    local,
  );
  await ctx.auth.ready;
  await ctx.auth.logout();
  assert.equal(ctx.auth.current, null);
  assert.equal(local.getItem("socialmei-theme-v1"), null);
  assert.equal(ctx.reloads, 1);
  assert(ctx.auth.internalStorageKey("socialmei-account-state-1:1"));
  assert(ctx.auth.internalStorageKey("socialmei-auth-browser-scope"));
});
test("confirmed logout leaves the app even when browser storage cannot archive local work", async () => {
  const local = storage({
    "socialmei-auth-browser-scope": "1:1",
    "socialmei-private-work": "keep",
  });
  const ctx = setup(
    (url) => (url.endsWith("/auth/session") ? reply(identity(1)) : reply(null, 204)),
    { mode: "remote", apiBaseUrl: "/api/v1" },
    local,
  );
  await ctx.auth.ready;
  local.setItem = () => {
    throw new Error("Quota exceeded");
  };
  await ctx.auth.logout();
  assert.equal(ctx.auth.current, null);
  assert.equal(ctx.reloads, 1);
  assert.equal(local.getItem("socialmei-private-work"), "keep");
});

test("new password policy accepts eight characters without mandatory character classes", () => {
  const { auth } = setup(() => reply(null), { mode: "local" });
  for (const value of ["FlorSol!", "73925186", "luaverde"]) {
    assert.equal(auth.passwordPolicy(value).error, "");
    assert.match(auth.passwordPolicy(value).warning, /fraca/i);
  }
  for (const value of [
    "FlorSol",
    "7392518",
    "12345678",
    "PASSWORD",
    "senha123",
    "aaaaaaaa",
    "x".repeat(129),
  ])
    assert(auth.passwordPolicy(value).error);
  assert.equal(auth.passwordPolicy("Uma frase longa original").warning, "");
});

test("switching workspace archives drafts and rejects pending old-workspace responses", async () => {
  const local = storage({
    "socialmei-auth-browser-scope": "1:1",
    "socialmei-inbox-draft": "private previous draft",
  });
  let resolveOld;
  const other = identity(1);
  other.negocio = { ...other.negocio, id: 2, slug: "second" };
  const ctx = setup(
    (url) => {
      if (url.endsWith("/auth/session")) return reply(identity(1));
      if (url.endsWith("/auth/workspaces/switch")) return reply(other);
      return new Promise((resolve) => {
        resolveOld = resolve;
      });
    },
    undefined,
    local,
  );
  await ctx.auth.ready;
  const old = ctx.auth.request("/clientes");
  await ctx.auth.switchWorkspace(2);
  resolveOld(reply([{ nome: "Old customer" }]));
  await assert.rejects(old, /sessão mudou/);
  assert.equal(ctx.auth.current, null);
  assert.equal(local.getItem("socialmei-auth-browser-scope"), "1:2");
  await assert.rejects(
    ctx.auth.request("/clientes", "POST", { nome: "Stale after switch" }),
    /sessão mudou/,
  );
  assert.equal(local.getItem("socialmei-inbox-draft"), null);
  assert.equal(
    JSON.parse(local.getItem("socialmei-account-state-1:1"))["socialmei-inbox-draft"],
    "private previous draft",
  );
  assert.equal(ctx.reloads, 1);
});

test("another tab changing workspace invalidates identity and pending responses", async () => {
  const local = storage({ "socialmei-auth-browser-scope": "1:1" });
  let resolveOld;
  const ctx = setup(
    (url) =>
      url.endsWith("/auth/session")
        ? reply(identity(1))
        : new Promise((resolve) => {
            resolveOld = resolve;
          }),
    undefined,
    local,
  );
  await ctx.auth.ready;
  const old = ctx.auth.request("/clientes");
  local.setItem("socialmei-auth-browser-scope", "1:2");
  ctx.events.storage({ key: "socialmei-auth-browser-scope" });
  resolveOld(reply([{ nome: "Old customer" }]));
  await assert.rejects(old, /sessão mudou/);
  assert.equal(ctx.auth.current, null);
  assert.equal(ctx.reloads, 1);
});

test("stale tab cannot send a write before its storage event is delivered", async () => {
  const local = storage({ "socialmei-auth-browser-scope": "1:1" });
  const ctx = setup(() => reply(identity(1)), undefined, local);
  await ctx.auth.ready;
  local.setItem("socialmei-auth-browser-scope", "1:2");
  await assert.rejects(ctx.auth.request("/clientes", "POST", { nome: "Stale" }), /outra aba/);
  assert.equal(ctx.requests.length, 1);
  assert.equal(ctx.auth.current, null);
});

test("failed switch preserves the active workspace and its local drafts", async () => {
  const local = storage({ "socialmei-auth-browser-scope": "1:1", "socialmei-draft": "keep" });
  const ctx = setup(
    (url) =>
      url.endsWith("/auth/session")
        ? reply(identity(1))
        : reply({ detail: "Você não possui acesso a este negócio." }, 403),
    undefined,
    local,
  );
  await ctx.auth.ready;
  await assert.rejects(ctx.auth.switchWorkspace(99), /não possui acesso/);
  assert.equal(ctx.auth.current.negocio.id, 1);
  assert.equal(local.getItem("socialmei-draft"), "keep");
  assert.equal(ctx.reloads, 0);
});
