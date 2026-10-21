const assert = require("node:assert/strict");
const test = require("node:test");
const { EventEmitter } = require("node:events");
const { navigateInitialPage } = require("./team-navigation.cjs");

const url = "https://localhost:32768/";
const changed = () => new Error("page.goto: net::ERR_NETWORK_CHANGED at " + url);

function pageWith(results) {
  const calls = [];
  return Object.assign(new EventEmitter(), {
    calls,
    async goto(target) {
      calls.push(target);
      const result = results.shift();
      if (result instanceof Error) throw result;
      if (typeof result === "function") return result(this);
      return result;
    },
  });
}

function assetFailure(error, pathname = "/scripts/app.js", resourceType = "script") {
  return {
    url: () => new URL(pathname, url).href,
    resourceType: () => resourceType,
    failure: () => ({ errorText: error }),
  };
}

test("HTML 200 with startup network-cancelled scripts recovers before app actions", async () => {
  const response = { status: () => 200 };
  const page = pageWith([
    (page) => {
      page.emit("requestfailed", assetFailure("net::ERR_NETWORK_CHANGED"));
      return response;
    },
    response,
  ]);
  const retries = [];
  assert.equal(
    await navigateInitialPage(page, url, { onStartupRetry: (r) => retries.push(r) }),
    response,
  );
  assert.equal(page.calls.length, 2);
  assert.equal(retries.length, 1);
  assert.equal(retries[0].failures[0].path, "/scripts/app.js");
  assert.equal(page.listenerCount("requestfailed"), 0);
  assert.equal(page.listenerCount("response"), 0);
});

test("persistent asset network cancellations still fail at the original three-attempt bound", async () => {
  const cancelled = (page) => {
    page.emit("requestfailed", assetFailure("net::ERR_NETWORK_CHANGED"));
    return { status: () => 200 };
  };
  const page = pageWith([cancelled, cancelled, cancelled]);
  await assert.rejects(navigateInitialPage(page, url), /net::ERR_NETWORK_CHANGED/);
  assert.equal(page.calls.length, 3);
  assert.equal(page.listenerCount("requestfailed"), 0);
});

for (const other of ["net::ERR_FAILED", "net::ERR_CERT_AUTHORITY_INVALID", "HTTP 404"]) {
  test(`mixed startup failure ${other} must not retry or hide a broken asset`, async () => {
    const response = { status: () => 200 };
    const page = pageWith([
      (page) => {
        page.emit("requestfailed", assetFailure("net::ERR_NETWORK_CHANGED"));
        if (other === "HTTP 404")
          page.emit("response", {
            ok: () => false,
            status: () => 404,
            url: () => new URL("/scripts/missing.js", url).href,
            request: () => assetFailure(null),
          });
        else page.emit("requestfailed", assetFailure(other));
        return response;
      },
    ]);
    assert.equal(await navigateInitialPage(page, url), response);
    assert.equal(page.calls.length, 1);
  });
}

test("initial navigation recovers from startup network changes", async () => {
  const response = { status: () => 200 };
  const page = pageWith([changed(), changed(), response]);
  assert.equal(await navigateInitialPage(page, url), response);
  assert.deepEqual(page.calls, [url, url, url]);
});

test("persistent network changes fail after three attempts with the original error", async () => {
  const error = changed();
  const page = pageWith([error, error, error]);
  await assert.rejects(navigateInitialPage(page, url), (actual) => actual === error);
  assert.equal(page.calls.length, 3);
});

for (const status of [200, 401, 403, 500]) {
  test(`HTTP ${status} returns immediately for the caller's existing status assertion`, async () => {
    const response = { status: () => status };
    const page = pageWith([response]);
    assert.equal(await navigateInitialPage(page, url), response);
    assert.equal(page.calls.length, 1);
  });
}

for (const message of [
  "page.goto: net::ERR_CERT_AUTHORITY_INVALID at " + url,
  "page.goto: net::ERR_CONNECTION_REFUSED at " + url,
  "page.goto: Timeout 30000ms exceeded.",
  "page.goto: net::ERR_NETWORK_CHANGED_OTHER at " + url,
  "page.goto: net::ERR_FAILED\nCall log: net::ERR_NETWORK_CHANGED",
]) {
  test(`does not retry ${message.split("\n")[0]}`, async () => {
    const error = new Error(message);
    const page = pageWith([error]);
    await assert.rejects(navigateInitialPage(page, url), (actual) => actual === error);
    assert.equal(page.calls.length, 1);
  });
}
