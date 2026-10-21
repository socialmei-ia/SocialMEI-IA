const assert = require("node:assert/strict");
const test = require("node:test");
const { navigateInitialPage } = require("./team-navigation.cjs");

const url = "https://localhost:32768/";
const changed = () => new Error("page.goto: net::ERR_NETWORK_CHANGED at " + url);

function pageWith(results) {
  const calls = [];
  return {
    calls,
    async goto(target) {
      calls.push(target);
      const result = results.shift();
      if (result instanceof Error) throw result;
      return result;
    },
  };
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
