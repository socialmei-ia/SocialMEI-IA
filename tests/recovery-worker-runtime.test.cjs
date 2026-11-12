const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const base = readFileSync(path.join(root, "compose.team.yaml"), "utf8");
const override = readFileSync(path.join(root, "compose.team-recovery.yaml"), "utf8");

test("default stack leaves recovery delivery off and has no SMTP sender worker", () => {
  assert.ok(base.includes("SOCIALMEI_RECOVERY_MODE: ${SOCIALMEI_RECOVERY_MODE:-disabled}"));
  assert.ok(!base.includes("team-recovery-worker:"));
  assert.ok(!base.includes("recovery-egress"));
});

test("recovery override adds exactly an opt-in bounded worker with SMTP egress", () => {
  assert.ok(override.includes("team-recovery-worker:"));
  assert.ok(override.includes('"--run", "--watch", "--limit", "10", "--interval", "15"'));
  assert.ok(override.includes("networks: [database, recovery-egress]"));
  assert.ok(override.includes("recovery-egress:"));
  assert.ok(override.includes("SOCIALMEI_RECOVERY_MODE: ${SOCIALMEI_RECOVERY_MODE:-disabled}"));
  assert.ok(override.includes("SOCIALMEI_SMTP_PASSWORD: ${SOCIALMEI_SMTP_PASSWORD:-}"));
  for (const unsafe of ["ports:", "privileged:", "cap_add:", "network_mode: host"]) {
    assert.ok(!override.includes(unsafe), "Forbidden recovery override property: " + unsafe);
  }
});
