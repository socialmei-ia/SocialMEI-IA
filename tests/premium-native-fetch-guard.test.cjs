const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const { installReadOnlyFetchGuard } = require("../tools/premium-smoke-diagnostics.cjs");

async function fixture() {
  const calls = [];
  const window = {
    fetch: function (...args) {
      calls.push(args);
      return Promise.resolve("native-result");
    },
  };
  const context = {
    route() {
      throw Error("HTTP interception must remain disabled");
    },
    async exposeBinding(name, fn) {
      window[name] = (record) => fn({}, record);
    },
    async addInitScript(fn, args) {
      vm.runInNewContext(`(${fn.toString()})(${JSON.stringify(args)})`, {
        window,
        Request,
        URL,
        location: { href: "https://app.example.test/frontend/socialmei-app.html" },
      });
    },
  };
  const guard = await installReadOnlyFetchGuard(context, "https://app.example.test");
  return { window, calls, guard };
}

test("reads preserve native fetch arguments, abort signal and result without routing", async () => {
  const { window, calls, guard } = await fixture();
  const options = { signal: new AbortController().signal, cache: "no-store" };
  assert.equal(await window.fetch("/api/v1/clientes", options), "native-result");
  assert.equal(calls[0][1], options);
  assert.equal(guard.blocked.length, 0);
});

test("business mutations and registration are blocked before native fetch", async () => {
  const { window, calls, guard } = await fixture();
  for (const [url, method] of [
    ["/api/v1/clientes?token=never-log", "POST"],
    ["/api/v1/produtos", "PATCH"],
    ["/api/v1/auth/register", "POST"],
    ["/api/v1/vendas/1", "DELETE"],
  ]) {
    await assert.rejects(
      window.fetch(url, { method, body: "password=never-log" }),
      /blocked fetch/,
    );
  }
  assert.equal(calls.length, 0);
  assert.equal(guard.blocked.length, 4);
  assert(!JSON.stringify(guard.blocked).includes("never-log"));
});

test("only the existing login, workspace switch and logout posts are allowed", async () => {
  const { window, calls } = await fixture();
  for (const path of ["login", "workspaces/switch", "logout"])
    await window.fetch("/api/v1/auth/" + path, { method: "POST" });
  assert.equal(calls.length, 3);
  await assert.rejects(
    window.fetch("https://outside.example.test/api/v1/auth/login", { method: "POST" }),
    /blocked/,
  );
  assert.equal(calls.length, 3);
});

test("Request objects and method overrides are checked without reading their bodies", async () => {
  const { window, calls } = await fixture();
  const request = new Request("https://app.example.test/api/v1/clientes", {
    method: "POST",
    body: "never-log",
  });
  await assert.rejects(window.fetch(request), /blocked/);
  await window.fetch(request, { method: "GET" });
  assert.equal(calls.length, 1);
});
