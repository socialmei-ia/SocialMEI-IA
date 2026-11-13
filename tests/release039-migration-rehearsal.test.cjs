const assert = require("node:assert/strict");
const { test, after } = require("node:test");
const { mkdtempSync, mkdirSync, readdirSync, copyFileSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join, resolve } = require("node:path");
const future = import("../tools/release039-migration-rehearsal.mjs");
const repository = resolve(__dirname, "..");
const reviewed039 = mkdtempSync(join(tmpdir(), "socialmei-reviewed039-"));
mkdirSync(join(reviewed039, "database/migrations"), { recursive: true });
mkdirSync(join(reviewed039, "tools"), { recursive: true });
copyFileSync(
  join(repository, "tools/team-release-profile.py"),
  join(reviewed039, "tools/team-release-profile.py"),
);
for (const name of readdirSync(join(repository, "database/migrations")).filter(
  (name) => /^\d{3}_.*\.sql$/.test(name) && Number(name.slice(0, 3)) <= 39,
))
  copyFileSync(
    join(repository, "database/migrations", name),
    join(reviewed039, "database/migrations", name),
  );
after(() => rmSync(reviewed039, { recursive: true, force: true }));

test("039 plan verifies all 39 migrations without using production", async () => {
  const { rehearse, parseOptions } = await future;
  const plan = await rehearse(parseOptions([]), reviewed039);
  assert.equal(plan.mode, "plan");
  assert.equal(plan.profile, "039");
  assert.equal(plan.baseline, "035");
  assert.equal(Object.keys(plan.source_migrations).length, 39);
  assert.equal(Object.keys(plan.baseline_migrations).length, 35);
  assert.equal(plan.production_runtime_changed, false);
  assert.equal(plan.provider_messages_sent, false);
});
test("039 legacy verifier still refuses a source containing unreviewed040", async () => {
  const { migrationManifest } = await future;
  assert.throws(() => migrationManifest(repository));
});
test("039 rehearsal enforces Instagram menu tenant boundary and exact image", async () => {
  const { CONTRACT, parseOptions } = await future;
  for (const text of [
    "039_tenant_fk_contract_invalid",
    "039_table_count_invalid",
    "039_receipt_indexes_missing",
    "ig_menu_conversations",
    "last_message_id=7002",
    "state='not_a_state'",
    "ROLLBACK;",
  ])
    assert(CONTRACT.includes(text), text);
  for (const args of [
    ["--run"],
    ["--database-url", "postgresql://production"],
    ["--run", "--source-sha", "a".repeat(40), "--api-image", "latest"],
  ])
    assert.throws(() => parseOptions(args));
});
