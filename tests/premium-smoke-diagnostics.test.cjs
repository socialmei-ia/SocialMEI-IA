const { test } = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const {
  attachRequestDiagnostics,
  readWorkspaceApi,
} = require("../tools/premium-smoke-diagnostics.cjs");

test("diagnostics track concurrent requests for the same path and redact query secrets", () => {
  const page = new EventEmitter();
  const diagnostic = attachRequestDiagnostics(page, "https://app.example.test");
  const request = () => ({
    url: () => "https://app.example.test/api/v1/auth/session?secret=never-log",
    method: () => "GET",
  });
  const first = request();
  const second = request();
  page.emit("request", first);
  page.emit("request", second);
  page.emit("requestfailed", first);
  assert.equal(diagnostic.pending().length, 1);
  page.emit("requestfinished", second);
  assert.equal(diagnostic.pending().length, 0);
  assert.deepEqual(
    diagnostic.events.map((e) => e.failed),
    [true, false],
  );
  assert(!JSON.stringify(diagnostic.events).includes("never-log"));
});

test("failed reads name the endpoint, redact exception bodies and are never retried", async () => {
  const records = [];
  let attempts = 0;
  const page = {
    evaluate: async () => {
      attempts++;
      throw Error("cookie=never-log");
    },
  };
  await assert.rejects(
    readWorkspaceApi(page, "/clientes?limit=20", records),
    /failed: \/clientes \(request_failed\)/,
  );
  assert.equal(attempts, 1);
  assert.equal(records[0].ok, false);
  assert(!JSON.stringify(records).includes("never-log"));
});

test("unsafe paths never reach the browser", async () => {
  const page = {
    evaluate: () => {
      throw Error("Unexpected browser call");
    },
  };
  await assert.rejects(readWorkspaceApi(page, "https://outside.example.test", []), /Invalid/);
});

test("a real request timeout remains a failure without retries or timeout changes", async () => {
  const records = [];
  let attempts = 0;
  const page = {
    evaluate: async () => {
      attempts++;
      return { ok: false, code: "request_timeout" };
    },
  };
  await assert.rejects(readWorkspaceApi(page, "/auth/session", records), /request_timeout/);
  assert.equal(records[0].code, "request_timeout");
  assert.equal(attempts, 1);
});

test("successful reads return the API value without recording its contents", async () => {
  const records = [];
  const value = { privateField: "never-log" };
  const page = { evaluate: async () => ({ ok: true, value }) };
  assert.deepEqual(await readWorkspaceApi(page, "/clientes", records), value);
  assert.equal(records[0].ok, true);
  assert(!JSON.stringify(records).includes("never-log"));
});
