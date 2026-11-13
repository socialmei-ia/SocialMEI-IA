const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

test("optional application DSN is shared by API and mail/Instagram workers, outside migrator anchor", () => {
  const read = (file) => fs.readFileSync(path.join(__dirname, "..", file), "utf8");
  const setting = "DATABASE_URL: ${TEAM_APPLICATION_DATABASE_URL:-}";
  const base = read("compose.team.yaml");
  const api = base.indexOf("  team-api:");
  assert(api > 0);
  assert(!base.slice(0, api).includes("TEAM_APPLICATION_DATABASE_URL"));
  assert(base.slice(api).includes(setting));
  for (const file of ["compose.team-recovery.yaml", "compose.team-instagram-auto.yaml"])
    assert(read(file).includes(setting), file);
});

test("public booking defaults off, private key is server-only and proxy removes account authority", () => {
  const base = fs.readFileSync(path.join(__dirname, "../compose.team.yaml"), "utf8");
  assert(
    base.includes("SOCIALMEI_PUBLIC_BOOKING_ENABLED: ${SOCIALMEI_PUBLIC_BOOKING_ENABLED:-false}"),
  );
  const gateway = fs.readFileSync(path.join(__dirname, "../deploy/team/Caddyfile"), "utf8");
  const publicPath = gateway.slice(
    gateway.indexOf("handle /api/v1/public/booking/*"),
    gateway.indexOf("handle /api/v1/*"),
  );
  for (const text of [
    "max_size 16384",
    "header_up -Authorization",
    "header_up -Cookie",
    "no-referrer",
  ])
    assert(publicPath.includes(text), text);
  const browser = fs.readFileSync(
    path.join(__dirname, "../frontend/scripts/public-booking.js"),
    "utf8",
  );
  assert(!browser.includes("SOCIALMEI_PUBLIC_BOOKING_KEY"));
});
