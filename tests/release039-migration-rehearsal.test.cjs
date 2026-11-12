const assert = require("node:assert/strict");
const { test } = require("node:test");
const future = import("../tools/release039-migration-rehearsal.mjs");

test("039 plan verifies all 39 migrations without using production", async () => {
  const { rehearse, parseOptions } = await future;
  const plan = await rehearse(parseOptions([]));
  assert.equal(plan.mode, "plan");
  assert.equal(plan.profile, "039");
  assert.equal(plan.baseline, "035");
  assert.equal(Object.keys(plan.source_migrations).length, 39);
  assert.equal(Object.keys(plan.baseline_migrations).length, 35);
  assert.equal(plan.production_runtime_changed, false);
  assert.equal(plan.provider_messages_sent, false);
});
test(
  "039 rehearsal enforces Instagram menu tenant boundary and exact image",
  async () => {
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
  },
);
