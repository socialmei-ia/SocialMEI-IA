const { test } = require("node:test");
const assert = require("node:assert/strict");

test("demo operation identities are stable and isolated by business", async () => {
  const { operationId } = await import("../tools/prepare-valter-demo.mjs");
  assert.equal(operationId(1, "sale"), operationId(1, "sale"));
  assert.notEqual(operationId(1, "sale"), operationId(2, "sale"));
  assert.notEqual(operationId(1, "sale"), operationId(1, "message"));
  assert.match(
    operationId(1, "sale"),
    /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/,
  );
});

test("demo refuses production or real analysis transports", async () => {
  const { requirePreview, origin } = await import("../tools/prepare-valter-demo.mjs");
  assert.equal(origin, "https://127.0.0.1:8443");
  for (const marker of [
    {},
    { environment: "team", transport: "none" },
    { environment: "local-disposable-preview", transport: "waha" },
  ])
    assert.throws(() => requirePreview(marker, { mode: "stub", transport: "none" }));
  assert.throws(() =>
    requirePreview(
      { environment: "local-disposable-preview", transport: "none" },
      { mode: "provider", transport: "none" },
    ),
  );
});

test("demo refuses an unrelated account before writing any business record", async () => {
  const { prepareDemo } = await import("../tools/prepare-valter-demo.mjs");
  const calls = [];
  const api = async (route, method = "GET") => {
    calls.push(method);
    if (route === "/__preview")
      return { environment: "local-disposable-preview", transport: "none" };
    if (route.endsWith("capabilities")) return { mode: "stub", transport: "none" };
    return { usuario: { email: "other@example.test" }, negocio: { id: 1 } };
  };
  await assert.rejects(prepareDemo(api, { email: "demo@example.test" }), /conta fictícia/);
  assert(calls.every((method) => method === "GET"));
});
