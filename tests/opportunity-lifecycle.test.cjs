const test = require("node:test");
const assert = require("node:assert/strict");
const { createStore, counts } = require("../frontend/scripts/opportunity-lifecycle-store.js");
const identity = () => ({ usuario: { id: 1 }, negocio: { id: 7 }, papel: "owner" });
const row = {
  id: "00000000-0000-4000-8000-000000000001",
  client_id: 2,
  client_name: "Teste",
  title: "Compra",
  interest_level: "hot",
  outcome: "open",
  revision: 1,
};
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

test("lost responses reuse the same operation key and never write a local fallback", async () => {
  const writes = [];
  const store = createStore({
    identity,
    headers: () => ({}),
    origin: "https://preview.test",
    fetch: async (url, options) => {
      writes.push(JSON.parse(options.body));
      if (writes.length === 1) throw new Error("offline");
      return response({ workspace_id: 7, ...row });
    },
  });
  const payload = { client_id: 2, title: "Compra", interest_level: "hot" };
  await assert.rejects(store.create(payload), /offline/);
  assert.deepEqual(store.snapshot().items, []);
  await store.create(payload);
  assert.equal(writes[0].operation_id, writes[1].operation_id);
  assert.equal(store.snapshot().items.length, 1);
});

test("late reads after account switch cannot install rows in the new business", async () => {
  let person = identity(),
    finish;
  const store = createStore({
    identity: () => person,
    headers: () => ({}),
    origin: "https://preview.test",
    fetch: () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  });
  const pending = store.reload();
  person = { usuario: { id: 3 }, negocio: { id: 9 }, papel: "owner" };
  finish(response({ workspace_id: 7, items: [row] }));
  await assert.rejects(pending, /sessão mudou/);
  assert.deepEqual(store.snapshot().items, []);
  assert.equal(store.snapshot().ready, false);
});

test("foreign envelopes and viewer writes are refused before accepting data", async () => {
  let calls = 0;
  const store = createStore({
    identity,
    headers: () => ({}),
    origin: "https://preview.test",
    fetch: async () => {
      calls++;
      return response({ workspace_id: 9, items: [row] });
    },
  });
  await assert.rejects(store.reload(), /outro negócio/);
  assert.deepEqual(store.snapshot().items, []);
  const viewer = createStore({
    identity: () => ({ ...identity(), papel: "viewer" }),
    origin: "https://preview.test",
    fetch: async () => {
      calls++;
    },
  });
  await assert.rejects(viewer.create({}), /somente leitura/);
  assert.equal(calls, 1);
});

test("closed results leave active interest counters and reopening restores only that opportunity", () => {
  const rows = [
    row,
    { ...row, id: "won", outcome: "won" },
    { ...row, id: "lost", outcome: "lost" },
    { ...row, id: "analysis", interest_level: "unknown" },
  ];
  assert.deepEqual(counts(rows), {
    open: 2,
    unknown: 1,
    cold: 0,
    warm: 0,
    hot: 1,
    won: 1,
    lost: 1,
  });
  rows[2].outcome = "open";
  assert.equal(counts(rows).hot, 2);
  assert.equal(counts(rows).lost, 0);
});
