const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(
  path.join(__dirname, "../frontend/scripts/v22-bootstrap.js"),
  "utf8",
);

function browser(failBackend) {
  const app = {
    hidden: false,
    textContent: "",
    attributes: {},
    setAttribute(key, value) {
      this.attributes[key] = value;
    },
  };
  const requests = [];
  const styles = [];
  const redirects = [];
  const storage = { getItem() {}, setItem() {}, removeItem() {} };
  const window = {
    SocialMEIAuth: {
      remote: true,
      ready: Promise.resolve(),
      current: { usuario: { id: 1 }, negocio: { id: 2 }, papel: "owner" },
    },
    SocialMEIV22: { ready: Promise.resolve() },
  };
  const document = {
    head: {
      appendChild(link) {
        styles.push(link.href);
      },
    },
    getElementById(id) {
      return id === "app" ? app : { textContent: "" };
    },
    createElement() {
      return {};
    },
    body: {
      appendChild(script) {
        if (!script.src) return;
        requests.push(script.src);
        if (script.src === "scripts/v22-backend.js")
          queueMicrotask(() => (failBackend ? script.onerror(Error("Offline")) : script.onload()));
      },
    },
  };
  const context = vm.createContext({
    window,
    document,
    Storage: function Storage() {},
    localStorage: storage,
    location: {
      pathname: "/frontend/socialmei-app.html",
      search: "",
      hash: "",
      replace(value) {
        redirects.push(value);
      },
    },
  });
  context.Storage.prototype = storage;
  return { app, requests, styles, redirects, ready: vm.runInContext(source, context) };
}

test("backend script outage exposes a visible accessible error instead of a hidden app", async () => {
  const page = browser(true);
  await page.ready;
  assert.equal(page.app.hidden, false);
  assert.equal(page.app.attributes.role, "alert");
  assert.match(page.app.textContent, /Atualize a página/);
  assert.deepEqual(page.requests, ["scripts/v22-backend.js"]);
  assert.deepEqual(page.redirects, []);
});

test("successful bootstrap keeps the backend-controlled app and loads existing integrations", async () => {
  const page = browser(false);
  await page.ready;
  assert.equal(page.app.textContent, "");
  assert.equal(page.app.attributes.role, undefined);
  assert(page.requests.includes("scripts/v22-whatsapp-bot.js"));
  assert(page.requests.includes("scripts/v22-instagram.js"));
  assert.deepEqual(page.styles, ["styles/v22-client-details.css"]);
  assert.deepEqual(page.redirects, []);
});
