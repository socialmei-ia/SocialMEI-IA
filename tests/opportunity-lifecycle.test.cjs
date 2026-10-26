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

test("planning import is explicit CAS and preserves raw browser copies on lost response", async () => {
  const payloads = [];
  const legacy = {
    amount: 1.23,
    date: "2026-11-02",
    note: "😀".repeat(70),
    contacted: false,
    updatedAt: 1,
    events: [],
  };
  const original = JSON.stringify(legacy);
  const store = createStore({
    identity,
    origin: "https://preview.test",
    headers: () => ({}),
    fetch: async (url, options) => {
      payloads.push(JSON.parse(options.body));
      if (payloads.length === 1) throw Error("offline");
      return response({ workspace_id: 7, ...row, planning_initialized: true, revision: 2 });
    },
  });
  await assert.rejects(store.importLegacyPlanning(row, legacy), /offline/);
  await store.importLegacyPlanning(row, legacy);
  assert.equal(payloads[0].expected_revision, 1);
  assert.equal(payloads[0].operation_id, payloads[1].operation_id);
  assert.equal(JSON.stringify(legacy), original);
  await assert.rejects(
    store.importLegacyPlanning({ ...row, planning_initialized: true }, legacy),
    /inicializado/,
  );
});

test("legacy candidates expose exact raw copies without normalization or writes", async () => {
  const { createRepository } = require("../frontend/scripts/opportunities-v8-parity.js");
  const scope = "1|7|",
    key = "socialmei-op8-local-v1:" + encodeURIComponent(scope);
  const raw = JSON.stringify({
    v: 1,
    scope,
    items: {
      [row.id]: {
        amount: 1.234,
        date: "",
        note: "x".repeat(141),
        contacted: false,
        updatedAt: 1,
        events: [],
      },
    },
  });
  let writes = 0;
  const repo = createRepository({
    scope: () => scope,
    writable: () => true,
    exists: (id) => id === row.id,
    storage: {
      getItem: (k) => (k === key ? raw : null),
      setItem() {
        writes++;
      },
    },
  });
  const store = createStore({
    identity,
    origin: "https://preview.test",
    headers: () => ({}),
    fetch: async () =>
      response({ workspace_id: 7, items: [{ ...row, planning_initialized: false }] }),
  });
  await store.reload();
  const candidates = store.listLegacyCandidates(repo);
  assert.equal(candidates[0].legacy.amount, 1.234);
  assert.equal(candidates[0].legacy.note.length, 141);
  await assert.rejects(store.importLegacyPlanning(row, candidates[0].legacy), /inválido/);
  assert.equal(writes, 0);
});

test("legacy validation rejects fractional cents, invalid calendar and broken Unicode without truncation", () => {
  const { validateLegacyPlanning } = require("../frontend/scripts/opportunity-lifecycle-store.js");
  const good = {
    amount: 1.23,
    date: "2028-02-29",
    note: "😀".repeat(70),
    contacted: false,
    updatedAt: 0,
    events: [],
  };
  assert.deepEqual(validateLegacyPlanning(good), good);
  for (const patch of [
    { amount: 1.234 },
    { amount: 1e9 + 0.01 },
    { note: "😀".repeat(71) },
    { note: "bad\ud800" },
    { date: "2026-02-30" },
    { date: "0000-01-01" },
    { contacted: 1 },
  ])
    assert.throws(() => validateLegacyPlanning({ ...good, ...patch }), /inválido/);
});

test("planning import cannot install a response after account switch and performs no local fallback", async () => {
  let person = identity(),
    finish;
  const legacy = { amount: 0, date: "", note: "", contacted: false, updatedAt: 0, events: [] };
  const store = createStore({
    identity: () => person,
    origin: "https://preview.test",
    headers: () => ({}),
    fetch: () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  });
  const request = store.importLegacyPlanning(row, legacy);
  person = { usuario: { id: 3 }, negocio: { id: 9 }, papel: "owner" };
  finish(response({ workspace_id: 7, ...row, revision: 2, planning_initialized: true }));
  await assert.rejects(request, /sessão mudou/);
  assert.deepEqual(store.snapshot().items, []);
  assert.deepEqual(legacy, {
    amount: 0,
    date: "",
    note: "",
    contacted: false,
    updatedAt: 0,
    events: [],
  });
});

test("incomplete legacy objects cannot fabricate initialized zeros or trigger HTTP", async () => {
  let calls = 0;
  const store = createStore({
    identity,
    origin: "https://preview.test",
    headers: () => ({}),
    fetch: async () => {
      calls++;
      return response({ ...row, workspace_id: 7 });
    },
  });
  for (const legacy of [
    {},
    { amount: 0 },
    { amount: 0, date: "", note: "", contacted: false, updatedAt: 0 },
  ])
    await assert.rejects(store.importLegacyPlanning(row, legacy), /inválido/);
  assert.equal(calls, 0);
});

test("shared planning undo refuses a switched scope or newer revision before HTTP", async () => {
  let person = identity(),
    writes = 0;
  const store = createStore({
    identity: () => person,
    origin: "https://preview.test",
    headers: () => ({}),
    fetch: async (url, options) => {
      if (options.method !== "GET") {
        writes++;
        return response({ workspace_id: 7, ...row, revision: 3 });
      }
      return response({ workspace_id: 7, items: [{ ...row, revision: 2 }] });
    },
  });
  await store.reload();
  const scope = store.snapshot().scope;
  await assert.rejects(store.undoPlanning(row, { estimated_amount: 0 }, scope), /mais recente/);
  person = { usuario: { id: 3 }, negocio: { id: 9 }, papel: "owner" };
  await assert.rejects(
    store.undoPlanning({ ...row, revision: 2 }, { estimated_amount: 0 }, scope),
    /sessão|negócio/,
  );
  assert.equal(writes, 0);
});
