const test = require("node:test");
const assert = require("node:assert/strict");
const simulation = require("../frontend/scripts/instagram-simulation.js");

test("simulation mode is explicit", () => {
  assert.equal(simulation.enabled(undefined), false);
  assert.equal(simulation.enabled({ mode: "disabled" }), false);
  assert.equal(simulation.enabled({ mode: "simulation" }), true);
});

test("front-end sends only metadata; no file binary, token or Meta identity", () => {
  const media = { name: "test.png", mime: "image/png", size: 1024 };
  const payload = simulation.payloadOf(
    { scope: "account:1:workspace:2", format: "feed", caption: "test", media },
    "test-account-id",
    "test-idempotency-key",
  );
  assert.deepEqual(payload, {
    account_id: "test-account-id",
    idempotency_key: "test-idempotency-key",
    format: "feed",
    caption: "test",
    media: [media],
    scheduled_for: null,
  });
  assert(!JSON.stringify(payload).includes("workspace:"));
  assert.throws(() => simulation.payloadOf({ format: "feed" }, "a", "b"), /mídia/);
});
