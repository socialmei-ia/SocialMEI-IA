const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(
  path.join(__dirname, "../frontend/scripts/v22-bootstrap.js"),
  "utf8",
);

function browser(failBackend, nativeStatus = 200) {
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
        const source = script.src.split("?")[0];
        requests.push(source);
        if (source === "scripts/v22-backend.js")
          queueMicrotask(() => (failBackend ? script.onerror(Error("Offline")) : script.onload()));
        if (source === "scripts/v781-atendimento-ui.js")
          queueMicrotask(() => script.onload());
      },
    },
  };
  const context = vm.createContext({
    window,
    document,
    Storage: function Storage() {},
    XMLHttpRequest: class {
      open(method, url, async) {
        assert.equal(method, "GET");
        assert.equal(async, false);
        requests.push(url.split("?")[0]);
      }
      send() {
        this.status = nativeStatus;
        this.responseText = "void 0;";
      }
    },
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
  assert.deepEqual(page.requests, ["scripts/v22-native.js", "scripts/v22-backend.js"]);
  assert.deepEqual(page.redirects, []);
});

test("a failed external native script blocks the backend and exposes the startup error", async () => {
  const page = browser(false, 404);
  await page.ready;
  assert.equal(page.app.hidden, false);
  assert.equal(page.app.attributes.role, "alert");
  assert.deepEqual(page.requests, ["scripts/v22-native.js"]);
});

test("successful bootstrap keeps the backend-controlled app and loads existing integrations", async () => {
  const page = browser(false);
  await page.ready;
  assert.equal(page.app.textContent, "");
  assert.equal(page.app.attributes.role, undefined);
  assert(page.requests.includes("scripts/v22-whatsapp-bot.js"));
  assert(page.requests.includes("scripts/v22-instagram.js"));
  assert.deepEqual(page.styles, ["styles/v22-client-details.css", "styles/connections-hub.css"]);
  assert.deepEqual(page.redirects, []);
});
