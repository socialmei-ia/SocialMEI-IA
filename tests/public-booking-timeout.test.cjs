/* Public booking request lifecycle without real HTTP, SMTP, Prisma or a browser. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../frontend/scripts/public-booking.js"),
  "utf8",
);
const start = source.indexOf("  async function request(path, body) {");
const end = source.indexOf("  function summary() {", start);
assert.ok(start >= 0 && end > start, "Public booking request function must exist");
const requestSource = source.slice(start, end);

function harness(fetch) {
  let nextTimer = 0;
  const timers = new Map();
  const context = vm.createContext({
    AbortController,
    fetch,
    state: { base: "/api/v1/public/booking/example" },
    generation: 1,
    controller: null,
    setTimeout(callback, delay) {
      const id = ++nextTimer;
      timers.set(id, { callback, delay });
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
  });
  vm.runInContext(requestSource + "\nthis.callRequest = request;", context);
  return {
    context,
    timers,
    request: context.callRequest,
    expire() {
      assert.equal(timers.size, 1, "One active request timeout expected");
      const [timer] = timers.values();
      assert.ok(timer.delay >= 5000 && timer.delay <= 30000);
      timer.callback();
    },
  };
}

test("stalled response is aborted and reported as uncertain network outcome", async () => {
  const h = harness((_url, { signal }) =>
    new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(Error("aborted")), { once: true });
    }),
  );
  const pending = h.request("/confirm", { offer: "fake", proof: "fake", confirmed: true });
  h.expire();
  await assert.rejects(pending, (error) => error.status === 0);
  assert.equal(h.timers.size, 0, "Timer must be cleared after request failure");
  assert.equal(h.context.controller, null);
});

test("stalled JSON body is aborted within the same timeout", async () => {
  let enteredJson = false;
  const h = harness((_url, { signal }) =>
    Promise.resolve({
      ok: true,
      json: () => {
        enteredJson = true;
        return new Promise((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(Error("aborted")), { once: true });
        });
      },
    }),
  );
  const pending = h.request("/slots", { day: "2031-11-13" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(enteredJson, true);
  h.expire();
  await assert.rejects(pending, (error) => error.status === 0);
  assert.equal(h.timers.size, 0);
});

test("HTTP errors retain their status and clear the timeout", async () => {
  const h = harness(() => Promise.resolve({ ok: false, status: 409 }));
  await assert.rejects(h.request("/confirm", { confirmed: true }), (error) => error.status === 409);
  assert.equal(h.timers.size, 0);
});

test("late response from a previous business remains stale", async () => {
  const h = harness((_url, { signal }) =>
    new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(Error("aborted")), { once: true });
    }),
  );
  const pending = h.request("");
  h.context.generation = 2;
  h.context.controller.abort();
  await assert.rejects(pending, (error) => error.stale === true);
  assert.equal(h.timers.size, 0);
});

test("successful requests keep privacy transport flags and clear timeout", async () => {
  let config;
  const h = harness((_url, options) => {
    config = options;
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ valid: true }) });
  });
  const result = await h.request("/resources", { service: "opaque" });
  assert.equal(result.valid, true);
  assert.equal(config.credentials, "omit");
  assert.equal(config.cache, "no-store");
  assert.equal(config.method, "POST");
  assert.equal(h.timers.size, 0);
});
