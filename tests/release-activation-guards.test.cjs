/* Non-destructive release gates: guard default-off channel activation on code changes.
 * These checks inspect repository text only. They do not connect to AWS, providers or a database.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

function optIn(text, key, fallback) {
  assert.ok(
    text.includes(key + ": ${" + key + ":-" + fallback + "}"),
    key + " must remain explicitly opt-in; release review required to change its default",
  );
}

test("production-facing channels and public booking default to OFF", () => {
  const compose = read("compose.team.yaml");
  for (const [key, fallback] of [
    ["SOCIALMEI_PUBLIC_BOOKING_ENABLED", "false"],
    ["SOCIALMEI_WHATSAPP_BOT_ENABLED", "false"],
    ["SOCIALMEI_WAHA_INGRESS_MODE", "disabled"],
    ["SOCIALMEI_WA_CATALOG_ENABLED", "false"],
    ["SOCIALMEI_INSTAGRAM_RUNTIME_MODE", "disabled"],
    ["SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED", "false"],
    ["SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED", "false"],
    ["SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED", "false"],
    ["SOCIALMEI_RECOVERY_MODE", "disabled"],
    ["SOCIALMEI_QUEUE_WAKEUP_MODE", "poll"],
    ["SOCIALMEI_IDENTITY_MODE", "disabled"],
    ["SOCIALMEI_WAHA_MANAGEMENT_ENABLED", "false"],
    ["SOCIALMEI_WAHA_MANAGEMENT_PROBE_ENABLED", "false"],
  ])
    optIn(compose, key, fallback);
});

test("optional Instagram workers require explicit profiles and send activation", () => {
  const config = read("compose.team-instagram-auto.yaml");
  for (const profile of ["instagram-menu-primary", "instagram-menu-secondary"]) {
    assert.ok(config.includes("profiles: [" + profile + "]"), "Missing opt-in worker " + profile);
  }
  optIn(config, "SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED", "false");
  optIn(config, "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED", "false");
});

test("recovery mail worker remains optional and shipping stays off", () => {
  const config = read("compose.team-recovery.yaml");
  assert.ok(config.includes("profiles: [recovery-mail]"));
  optIn(config, "SOCIALMEI_RECOVERY_MODE", "disabled");
});

test("API and optional workers use one opt-in application database override", () => {
  const token = "DATABASE_URL: ${TEAM_APPLICATION_DATABASE_URL:-}";
  for (const file of [
    "compose.team.yaml",
    "compose.team-recovery.yaml",
    "compose.team-instagram-auto.yaml",
    "compose.team-identity.yaml",
  ]) {
    assert.ok(read(file).includes(token), file + " lacks shared application DSN");
  }
  const base = read("compose.team.yaml");
  const apiPosition = base.indexOf("\n  team-api:");
  assert.ok(apiPosition > 0, "API section not found");
  assert.ok(!base.slice(0, apiPosition).includes("TEAM_APPLICATION_DATABASE_URL"));
});

test("identity delivery requires its explicit profile and enforcement mode", () => {
  const config = read("compose.team-identity.yaml");
  assert(config.includes("profiles: [identity-mail]"));
  optIn(config, "SOCIALMEI_IDENTITY_MODE", "disabled");
  optIn(config, "SOCIALMEI_QUEUE_WAKEUP_MODE", "poll");
});

test("public visitor route strips account credentials before proxying", () => {
  const proxy = read("deploy/team/Caddyfile");
  const start = proxy.indexOf("handle /api/v1/public/booking/* {");
  const end = proxy.indexOf("handle /api/v1/* {", start);
  assert.ok(start >= 0 && end > start, "Dedicated visitor route missing");
  const section = proxy.slice(start, end);
  for (const required of [
    "header_up -Authorization",
    "header_up -Cookie",
    "max_size 16384",
    "no-referrer",
  ]) {
    assert.ok(section.includes(required), "Missing visitor privacy gate: " + required);
  }
});
