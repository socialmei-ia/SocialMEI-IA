const { test } = require("node:test");
const assert = require("node:assert/strict");
const { validPlan, createRepository, LIMIT } = require("../frontend/scripts/publication-planning.js");

const now = new Date("2026-10-21T12:00:00").getTime();
const fixture = () => ({
  format: "story",
  title: "    Promoção do mês  ",
  caption: "Confira as ofertas.",
  when: "2026-10-23T18:45",
  mediaName: "capa.png",
});
const fakeStorage = () => {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    values,
  };
};
test("local plan validates formats, required title and future time without transports", () => {
  assert.equal(validPlan(fixture(), now).title, "Promoção do mês");
  for (const format of ["feed", "story", "reel"])
    assert.equal(validPlan({ ...fixture(), format }, now).format, format);
  assert.throws(() => validPlan({ ...fixture(), format: "carousel" }, now), /Feed/);
  assert.throws(() => validPlan({ ...fixture(), title: "" }, now), /título/);
  assert.throws(() => validPlan({ ...fixture(), when: "2026-10-21T12:00" }, now), /futuro/);
  assert.throws(() => validPlan({ ...fixture(), when: "2027-12-01T12:00" }, now), /60 dias/);
  assert.throws(() => validPlan({ ...fixture(), when: "not-a-date" }, now), /data/);
  assert.throws(() => validPlan({ ...fixture(), caption: "x".repeat(2201) }, now), /legenda/);
});
test("plans stay isolated by verified browser scope and can be removed", () => {
  const storage = fakeStorage();
  let scope = "account:3:workspace:20";
  const repository = createRepository(storage, () => scope, () => now);
  const item = repository.add(fixture());
  assert.equal(repository.read().length, 1);
  assert.equal(repository.read()[0].id, item.id);
  scope = "account:3:workspace:21";
  assert.deepEqual(repository.read(), []);
  repository.add({ ...fixture(), title: "Loja B" });
  assert.equal(repository.read()[0].title, "Loja B");
  scope = "account:3:workspace:20";
  assert.equal(repository.read()[0].title, "Promoção do mês");
  repository.remove(item.id);
  assert.deepEqual(repository.read(), []);
  scope = null;
  assert.throws(() => repository.read(), /negócio/);
});
test("corrupted storage is rejected without overwriting original data", () => {
  const storage = fakeStorage();
  const repository = createRepository(storage, () => "test", () => now);
  storage.setItem("socialmei-publication-plans-v1:test", "{broken");
  assert.throws(() => repository.add(fixture()), /não foi possível ler/i);
  assert.equal(storage.getItem("socialmei-publication-plans-v1:test"), "{broken");
});
test("local planner enforces bounded rows, no external publishing path", () => {
  const storage = fakeStorage();
  const repository = createRepository(storage, () => "test", () => now);
  for (let i = 0; i < LIMIT; i++)
    repository.add({ ...fixture(), title: "Plano " + i });
  assert.equal(repository.read().length, LIMIT);
  assert.throws(() => repository.add(fixture()), /Limite/);
  assert.deepEqual(Object.keys(repository).sort(), ["add", "read", "remove"]);
});