const test = require("node:test");
const assert = require("node:assert/strict");
const model = require("../frontend/scripts/integration-setup.js");
const identity = (user = 1, workspace = 2, role = "owner") => ({
  usuario: { id: user },
  negocio: { id: workspace },
  papel: role,
});
test("setup saves only public preparation with CAS and never grants connection", async () => {
  let current = identity(),
    calls = [];
  const store = model.repository({
    identity: () => current,
    request: async (path, method, body) => {
      calls.push({ path, method, body });
      return {
        workspace_id: 2,
        revision: method === "PUT" ? 2 : 1,
        instagram: { username: "loja" },
        connected: false,
        transport: "none",
      };
    },
  });
  await store.read();
  await store.save({
    username: "@loja",
    account_type: "business",
    meta_app_status: "exists",
    test_participants: ["teste"],
    reply_mode: "review",
  });
  assert.equal(calls[1].body.expected_revision, 1);
  assert.equal(calls[1].body.instagram.username, "loja");
  assert.equal(calls[1].path, "/integrations/setup");
  assert.equal(store.snapshot().connected, false);
  current = identity(1, 2, "viewer");
  await assert.rejects(store.save({ username: "loja" }), /permissão/);
  assert.equal(calls.length, 2);
});
test("late setup response cannot cross identity and wrong workspace cannot replace snapshot", async () => {
  let current = identity(),
    resolve;
  const store = model.repository({
    identity: () => current,
    request: () => new Promise((r) => (resolve = r)),
  });
  const pending = store.read();
  current = identity(3, 2);
  resolve({ workspace_id: 2, revision: 1 });
  await assert.rejects(pending, /sessão/);
  assert.equal(store.snapshot(), null);
  const next = store.read();
  resolve({ workspace_id: 99, revision: 1 });
  await assert.rejects(next, /negócio/);
  assert.equal(store.snapshot(), null);
});
test("setup rejects secrets and unsupported modes before sending a write", async () => {
  const store = model.repository({
    identity: () => identity(),
    request: async () => ({ workspace_id: 2, revision: 1 }),
  });
  await store.read();
  await assert.rejects(store.save({ username: "loja", password: "secret" }), /públicos/);
  await assert.rejects(store.save({ username: "loja", reply_mode: "automatic" }), /revisão/);
});
