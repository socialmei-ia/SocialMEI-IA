const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(
  path.join(__dirname, "../experimental/reports-v21/sandbox.js"),
  "utf8",
);
function sandbox() {
  const real = new Map([["account", "private-user-data"]]);
  const context = vm.createContext({ navigator: {}, XMLHttpRequest: class {}, window: null });
  context.window = context;
  Object.defineProperty(context, "localStorage", { configurable: true, get: () => real });
  vm.runInContext(source, context);
  return { context, real };
}
test("Reports V2.1 preview storage cannot read, write or clear account storage", () => {
  const { context, real } = sandbox();
  assert.equal(context.localStorage.getItem("account"), null);
  context.localStorage.setItem("account", "synthetic");
  context.localStorage.setItem("__proto__", "safe-key");
  assert.equal(context.localStorage.getItem("__proto__"), "safe-key");
  assert.equal(context.localStorage.length, 2);
  context.localStorage.clear();
  assert.equal(real.get("account"), "private-user-data");
  assert.equal(context.localStorage.length, 0);
});
test("Reports V2.1 reloads and contexts receive independent synthetic storage", () => {
  const one = sandbox().context,
    two = sandbox().context;
  one.localStorage.setItem("history", "example");
  one.sessionStorage.setItem("user", "one");
  assert.equal(two.localStorage.getItem("history"), null);
  assert.equal(two.sessionStorage.getItem("user"), null);
  assert.equal(
    two.sessionStorage.getItem("socialmei-business-demo-identity"),
    "reports-v21-preview",
  );
});
test("Reports V2.1 business network transports fail closed", async () => {
  const { context } = sandbox();
  await assert.rejects(context.fetch("https://example.invalid/api"), /bloqueadas/);
  assert.throws(() => new context.XMLHttpRequest().open("POST", "/api"), /bloqueadas/);
  assert.throws(() => new context.WebSocket("wss://example.invalid"), /bloqueadas/);
  assert.throws(() => new context.EventSource("/events"), /bloqueadas/);
  assert.equal(context.navigator.sendBeacon("/api", "data"), false);
});
