const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const script = fs.readFileSync(
  path.join(__dirname, "../frontend/scripts/v22-instagram.js"),
  "utf8",
);
const start = script.indexOf("  async function connect(confirmedScope) {");
const end = script.indexOf("  async function renew() {", start);
assert(start > 0 && end > start);

function sandbox() {
  let owner = "91:17",
    resolve,
    started;
  const response = new Promise((r) => {
    resolve = r;
  });
  const requested = new Promise((r) => {
    started = r;
  });
  const navigations = [],
    dialogs = [],
    calls = [];
  const ctx = {
    busy: false,
    state: { oauth: true, phase: "ready" },
    host: {
      identity: { papel: "owner", negocio: { nome: "Negócio controlado" } },
      request(...args) {
        calls.push(args);
        started();
        return response;
      },
    },
    scope: () => owner,
    paintAll() {},
    async refresh() {},
    info(...args) {
      dialogs.push(args);
    },
    details(...args) {
      dialogs.push(args);
    },
    esc: (value) => value,
    authorization: (value) => value.authorization_url,
    location: {
      assign(url) {
        navigations.push(url);
      },
    },
    Number,
    Error,
  };
  vm.createContext(ctx);
  vm.runInContext(script.slice(start, end), ctx);
  return {
    ctx,
    requested,
    resolve,
    navigations,
    dialogs,
    calls,
    switchWorkspace() {
      owner = "91:18";
    },
  };
}

test("Instagram authorization cannot navigate after the business changes during POST", async () => {
  const flow = sandbox();
  const pending = flow.ctx.connect("91:17");
  await flow.requested;
  flow.switchWorkspace();
  flow.resolve({ authorization_url: "https://www.instagram.com/oauth/authorize?state=controlled" });
  await pending;
  assert.deepEqual(flow.navigations, []);
  assert.equal(flow.calls.length, 1);
  assert.equal(flow.ctx.busy, false);
});

test("Instagram authorization proceeds only after explicit confirmation in the same business", async () => {
  const initial = sandbox();
  await initial.ctx.connect();
  assert.equal(initial.calls.length, 0);
  assert.equal(initial.dialogs.length, 1);
  const confirmed = sandbox();
  const pending = confirmed.ctx.connect("91:17");
  await confirmed.requested;
  confirmed.resolve({
    authorization_url: "https://www.instagram.com/oauth/authorize?state=controlled",
  });
  await pending;
  assert.equal(confirmed.navigations.length, 1);
});
