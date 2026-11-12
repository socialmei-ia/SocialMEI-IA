const assert = require("node:assert/strict"),
  { test, after } = require("node:test");
const {
  mkdtempSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
  rmSync,
} = require("node:fs");
const { tmpdir } = require("node:os");
const { join, resolve } = require("node:path");
const future = import("../tools/release038-migration-rehearsal.mjs");
const repository = resolve(__dirname, "..");
const reviewed038 = mkdtempSync(join(tmpdir(), "socialmei-reviewed038-"));
mkdirSync(join(reviewed038, "database/migrations"), { recursive: true });
mkdirSync(join(reviewed038, "tools"), { recursive: true });
writeFileSync(
  join(reviewed038, "tools/team-release-profile.py"),
  readFileSync(join(repository, "tools/team-release-profile.py")),
);
for (const name of readdirSync(join(repository, "database/migrations")).filter(
  (name) => /^\d{3}_.*\.sql$/.test(name) && Number(name.slice(0, 3)) <= 38,
))
  writeFileSync(
    join(reviewed038, "database/migrations", name),
    readFileSync(join(repository, "database/migrations", name)),
  );
after(() => rmSync(reviewed038, { recursive: true, force: true }));

test("038 plan explicitly starts from reviewed035 and never authorizes deployment", async () => {
  const { rehearse, parseOptions } = await future;
  const plan = await rehearse(parseOptions([]), reviewed038);
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
