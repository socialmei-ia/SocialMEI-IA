const { test } = require("node:test");
const assert = require("node:assert/strict");
const model = require("../frontend/scripts/business-profile.js");
const profile = (segment, offers = model.segments[segment].offers) =>
  model.normalize({
    segment,
    businessName: "MEI sintético",
    offers,
    completed: true,
    capabilities: { inventory: true, appointments: true },
    modules: Object.keys(model.modules),
  });
for (const segment of ["barber", "perfume", "tailoring", "commerce", "services", "other"]) {
  test(`configurable capabilities: ${segment}`, () => {
    const mixed = profile(segment, ["products", "services"]);
    assert.equal(mixed.capabilities.inventory, true);
    assert.equal(mixed.capabilities.appointments, true);
    assert(mixed.modules.includes("products"));
    assert(mixed.modules.includes("services"));
  });
}
test("offering filters prevent stale capability and module selections", () => {
  const services = profile("barber");
  assert.equal(services.capabilities.inventory, false);
  assert(!services.modules.includes("products"));
  assert(!services.modules.includes("inventory"));
  const products = profile("perfume");
  assert.equal(products.capabilities.appointments, false);
  assert(!products.modules.includes("appointments"));
  assert(!products.modules.includes("services"));
});
test("normalization allows optional answers, manual activity, deduplicates and limits data", () => {
  const result = model.normalize({
    segment: "not-in-catalog",
    offers: ["products", "unknown"],
    productCategories: [" Perfumes ", "Perfumes", {}, ""],
    services: ["hidden"],
    activity: "Atividade própria",
    modules: ["finance", "future"],
    capabilities: { inventory: "yes" },
  });
  assert.equal(result.segment, "other");
  assert.equal(result.activity, "Atividade própria");
  assert.deepEqual(result.productCategories, ["Perfumes"]);
  assert.deepEqual(result.services, []);
  assert.deepEqual(result.modules, ["finance"]);
  assert.equal(result.capabilities.inventory, false);
});
function setup() {
  const memory = new Map();
  let id = "account:1:workspace:1";
  const storage = {
    getItem: (key) => memory.get(key) || null,
    setItem: (key, value) => memory.set(key, value),
  };
  return {
    memory,
    storage,
    setScope: (next) => {
      id = next;
    },
    repo: model.repository(storage, () => id),
  };
}
test("final profile recovery, update, no cross-user or cross-workspace reads", () => {
  const { repo, setScope } = setup();
  assert.equal(repo.read().status, "empty");
  assert.equal(repo.save(profile("barber")), true);
  assert.equal(repo.read().profile.segment, "barber");
  setScope("account:2:workspace:1");
  assert.equal(repo.read().profile, null);
  repo.save(profile("perfume"));
  setScope("account:1:workspace:2");
  assert.equal(repo.read().profile, null);
  setScope("account:1:workspace:1");
  assert.equal(repo.read().profile.segment, "barber");
  repo.save(profile("tailoring"));
  assert.equal(repo.read().profile.segment, "tailoring");
  setScope(null);
  assert.equal(repo.read().status, "unavailable");
  assert.equal(repo.save(profile("barber")), false);
});
test("corrupt, foreign-scope or incompatible records are never recovered", () => {
  const { repo, memory } = setup();
  repo.save(profile("barber"));
  const key = [...memory.keys()][0];
  for (const value of [
    "{",
    JSON.stringify({ version: 2 }),
    JSON.stringify({ version: 1, scope: "account:2:workspace:1", profile: profile("perfume") }),
  ]) {
    memory.set(key, value);
    assert.equal(repo.read().profile, null);
  }
});
test("storage failures are explicit and never report success", () => {
  const repo = model.repository(
    {
      getItem() {
        throw Error("blocked");
      },
      setItem() {
        throw Error("quota");
      },
    },
    () => "demo:test",
  );
  assert.equal(repo.read().status, "unavailable");
  assert.equal(repo.save(profile("barber")), false);
});
test("only finalized profiles with offerings and business names can be saved", () => {
  const { repo } = setup();
  for (const incomplete of [
    { ...profile("barber"), completed: false },
    { ...profile("barber"), businessName: "" },
    { ...profile("barber"), offers: [] },
  ])
    assert.equal(repo.save(incomplete), false);
});
test("scope requires a verified session and a matching browser binding", () => {
  assert.equal(model.scope({ remote: true }), null);
  assert.equal(model.scope(null), null);
  const auth = { remote: true, current: { usuario: { id: 1 }, negocio: { id: 2 } } };
  assert.equal(model.scope(auth, "", "1:2"), "account:1:workspace:2");
  assert.equal(model.scope(auth, "", "2:2"), null);
  assert.equal(model.scope({ remote: false }, "A@example.com"), "demo:a@example.com");
  assert.notEqual(
    model.scope({ remote: false }, "A@example.com"),
    model.scope({ remote: false }, "B@example.com"),
  );
});

test("a stale draft cannot be written into a newly switched identity", () => {
  const { repo, setScope } = setup();
  const owner = repo.scope();
  setScope("account:2:workspace:1");
  assert.equal(repo.save(profile("barber"), owner), false);
  assert.equal(repo.read().profile, null);
});
