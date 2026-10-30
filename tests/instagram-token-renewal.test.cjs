const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const script = fs.readFileSync(
  path.join(__dirname, "../frontend/scripts/v22-instagram.js"),
  "utf8",
);
const start = script.indexOf("  async function renew() {");
const end = script.indexOf("  function details(errorCode) {", start);
assert(start > 0 && end > start);
const functionSource = script.slice(start, end);

function sandbox({ renewAvailable = true, connected = true, role = "owner", response } = {}) {
  const calls = [];
  const details = [];
  const notices = [];
  const state = { renewAvailable, connected, phase: "ready" };
  const host = {
    identity: { papel: role },
    async request(...args) {
      calls.push(args);
      if (response instanceof Error) throw response;
      return response || { status: "refreshed" };
    },
  };
  const ctx = {
    state, host, busy: false,
    paintAll() {},
    async refresh() {},
    details(code) { details.push(code); },
    toast(message) { notices.push(message); },
    Number, Error,
  };
  vm.createContext(ctx);
  vm.runInContext(functionSource, ctx);
  return { ctx, calls, details, notices };
}

test("owner renewal uses existing POST and never sends Direct or publications", async () => {
  const app = sandbox();
  await app.ctx.renew();
  assert.equal(app.calls.length, 1);
  assert.equal(app.calls[0][0], "/instagram/meta/connection/refresh-token");
  assert.equal(app.calls[0][1], "POST");
  assert.equal(JSON.stringify(app.calls[0][2]), "{}");
  assert.equal(app.details.length, 1);
  assert.equal(app.notices.length, 1);
  assert.equal(app.ctx.busy, false);
});

test("renewal does not execute without opt-in, connected account, or owner", async () => {
  for (const input of [
    { renewAvailable: false },
    { connected: false },
    { role: "report_viewer" },
  ]) {
    const app = sandbox(input);
    await app.ctx.renew();
    assert.equal(app.calls.length, 0);
    assert.equal(app.notices.length, 0);
  }
});

test("provider failure cannot be reported as a successful renewal", async () => {
  const failure = Object.assign(new Error("provider token must stay private"), { status: 409 });
  const app = sandbox({ response: failure });
  await app.ctx.renew();
  assert.equal(app.notices.length, 0);
  assert.equal(app.details[0], "HTTP 409");
});
