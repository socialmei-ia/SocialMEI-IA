const assert = require("node:assert/strict");
const test = require("node:test");
const { readFileSync } = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const base = readFileSync(path.join(root, "compose.team.yaml"), "utf8");
const optIn = readFileSync(path.join(root, "compose.team-instagram-auto.yaml"), "utf8");

test("default Team compose does not start an Instagram menu sender", () => {
  assert.ok(!base.includes("team-instagram-menu-primary:"));
  assert.ok(!base.includes("team-instagram-menu-secondary:"));
});

test("explicit Instagram menu profiles keep workspaces and state independent", () => {
  assert.ok(optIn.includes("team-instagram-menu-primary:"));
  assert.ok(optIn.includes("team-instagram-menu-secondary:"));
  assert.ok(optIn.includes("profiles: [instagram-menu-primary]"));
  assert.ok(optIn.includes("profiles: [instagram-menu-secondary]"));
  assert.ok(optIn.includes("instagram_menu_primary_state:"));
  assert.ok(optIn.includes("instagram_menu_secondary_state:"));
  assert.ok(optIn.includes("SOCIALMEI_INSTAGRAM_MENU_PRIMARY_WORKSPACE_ID:-"));
  assert.ok(optIn.includes("SOCIALMEI_INSTAGRAM_MENU_SECONDARY_WORKSPACE_ID:-"));
  assert.ok(optIn.includes("SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED:-false"));
  assert.ok(optIn.includes("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED:-false"));
  assert.ok(optIn.includes("SOCIALMEI_INSTAGRAM_DIRECT_OWNER:-unassigned"));
  assert.ok(optIn.includes("networks: [database, instagram-menu-egress]"));
  assert.ok(!/\bports:|\bprivileged:|\bnetwork_mode: host/.test(optIn));
});
