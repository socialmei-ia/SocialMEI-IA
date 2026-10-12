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
) {
  let reloads = 0;
  const requests = [];
  const context = vm.createContext({
    SOCIALMEI_CONFIG: { auth: config },
    window: {},
    localStorage: local,
    sessionStorage: session,
    location: {
      href: "https://app.example.com/frontend/socialmei-app.html",
      origin: "https://app.example.com",
      reload() {
        reloads++;
      },
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
  const ctx = setup(() => reply({ detail: "Login required" }, 401));
  assert.equal(await ctx.auth.ready, null);
  assert.equal(ctx.auth.current, null);
  assert.equal(ctx.reloads, 0);
  assert.equal(ctx.requests[0].options.credentials, "same-origin");
  assert.equal(ctx.requests[0].options.cache, "no-store");
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
test("invalid password response does not change account state or reload", async () => {
  const ctx = setup((url) =>
    url.endsWith("/auth/me")
      ? reply({}, 401)
      : reply({ detail: "E-mail ou senha inválidos." }, 401),
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
    (url) => (url.endsWith("/auth/me") ? reply(identity(1)) : reply(null, 204)),
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
