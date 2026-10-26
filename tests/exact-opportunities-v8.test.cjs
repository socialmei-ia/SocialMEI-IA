const assert = require("node:assert/strict");
const test = require("node:test");
const { createRepository, parseMoney } = require("../frontend/scripts/opportunities-v8-parity.js");
function fixture() {
  let scope = "11|201|",
    writable = true,
    failure = false;
  const data = new Map();
  const repo = createRepository({
    scope: () => scope,
    writable: () => writable,
    exists: (id) => id === "opportunity-1",
    storage: {
      getItem: (k) => data.get(k) || null,
      setItem(k, v) {
        if (failure) throw Error("quota");
        data.set(k, v);
      },
    },
  });
  return {
    repo,
    data,
    setScope: (v) => (scope = v),
    setWritable: (v) => (writable = v),
    setFailure: (v) => (failure = v),
  };
}
test("V8 keeps existing scoped planning metadata and does not mix users or workspaces", () => {
  const f = fixture();
  f.data.set(
    "socialmei-op8-local-v1:" + encodeURIComponent("11|201|"),
    JSON.stringify({
      v: 1,
      scope: "11|201|",
      items: {
        "opportunity-1": { amount: 350, date: "2026-11-02", note: "legado", contacted: true },
      },
    }),
  );
  assert.equal(f.repo.get("opportunity-1").note, "legado");
  f.repo.save("opportunity-1", { note: "revisado" });
  f.setScope("12|201|");
  assert.equal(f.repo.get("opportunity-1").note, "");
  f.setScope("11|202|");
  assert.equal(f.repo.get("opportunity-1").amount, 0);
  f.setScope("11|201|");
  assert.equal(f.repo.get("opportunity-1").note, "revisado");
});
test("V8 local planning requires a writable loaded record; quota failure is atomic", () => {
  const f = fixture();
  f.setWritable(false);
  assert.throws(() => f.repo.save("opportunity-1", { amount: 1 }), /leitura|acesso/i);
  f.setWritable(true);
  assert.throws(() => f.repo.save("another-record", { amount: 1 }), /oportunidade/i);
  assert.equal(f.data.size, 0);
  f.repo.save("opportunity-1", { amount: 10 });
  f.setFailure(true);
  assert.throws(() => f.repo.save("opportunity-1", { amount: 99 }), /navegador/i);
  assert.equal(f.repo.get("opportunity-1").amount, 10);
});
test("V8 undo is local, checks the same identity and refuses a newer edit", () => {
  const f = fixture();
  const receipt = f.repo.save("opportunity-1", { amount: 100 });
  assert.equal(f.repo.undo(receipt), true);
  assert.equal(f.repo.get("opportunity-1").amount, 0);
  const stale = f.repo.save("opportunity-1", { amount: 100 });
  f.repo.save("opportunity-1", { note: "nova edição" });
  assert.throws(() => f.repo.undo(stale), /mudou|edição/i);
  f.setScope("11|202|");
  assert.throws(() => f.repo.undo(stale), /sessão|negócio/i);
  assert.equal(f.repo.get("opportunity-1").amount, 0);
});
test("V8 validates money, real calendar dates, IDs and bounded notes before writing", () => {
  assert.equal(parseMoney("1.200,50"), 1200.5);
  assert.equal(parseMoney(""), 0);
  for (const value of ["-1", "abc", "12 reais", "Infinity", "1.2.3", "1,2,3"])
    assert(Number.isNaN(parseMoney(value)), value);
  const f = fixture();
  assert.throws(() => f.repo.save("opportunity-1", { date: "2026-02-30" }), /data/i);
  assert.throws(() => f.repo.save("opportunity-1", { amount: -2 }), /valor/i);
  assert.throws(() => f.repo.save("opportunity-1", { note: "x".repeat(141) }), /anotação/i);
  assert.equal(f.data.size, 0);
});
