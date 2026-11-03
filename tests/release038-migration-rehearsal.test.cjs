const assert = require("node:assert/strict"),
  { test } = require("node:test");
const future = import("../tools/release038-migration-rehearsal.mjs");
test("038 plan explicitly starts from reviewed035 and never authorizes deployment", async () => {
  const { rehearse, parseOptions } = await future;
  const plan = await rehearse(parseOptions([]));
  assert.equal(plan.mode, "plan");
  assert.equal(plan.profile, "038");
  assert.equal(plan.baseline, "035");
  assert.equal(Object.keys(plan.source_migrations).length, 38);
  assert.equal(Object.keys(plan.baseline_migrations).length, 35);
  assert.equal(plan.production_runtime_changed, false);
  const legacy = await import("../tools/release-migration-rehearsal.mjs");
  assert.throws(() => legacy.migrationManifest(), /migration_profile_not_035/);
});
test("038 real contract covers additive FK, duration, price/schema and customer unlink trigger", async () => {
  const { CONTRACT, parseOptions } = await future;
  for (const contract of [
    "duracao_minutos=0",
    "cliente_id=3002",
    "servico_id=4002",
    "resource_id=",
    "ends_at=ends_at+",
    "customer_unlink_revision_missing",
    "038_table_count_invalid",
    "ROLLBACK;",
  ])
    assert(CONTRACT.includes(contract), contract);
  for (const args of [
    ["--run"],
    ["--database-url", "postgresql://production"],
    ["--run", "--source-sha", "a".repeat(40), "--api-image", "latest"],
  ])
    assert.throws(() => parseOptions(args));
});
