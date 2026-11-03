const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../frontend/scripts/v22-whatsapp-readiness.js"),
  "utf8",
);

function browser(result) {
  const text = { nodeType: 3, textContent: "Não conectado" };
  const classes = new Set(["st2", "s-g"]);
  const badge = {
    childNodes: [text],
    classList: {
      add(...names) {
        names.forEach((name) => classes.add(name));
      },
      remove(...names) {
        names.forEach((name) => classes.delete(name));
      },
    },
    matches(selector) {
      return selector === ".st2";
    },
    ownerDocument: {
      createTextNode(value) {
        return { nodeType: 3, textContent: value };
      },
    },
  };
  const button = { disabled: true, textContent: "Conectar" };
  const row = {
    matches() {
      return false;
    },
    querySelector(selector) {
      if (selector === "b") return { textContent: "WhatsApp" };
      if (selector === ".st2, .chip") return badge;
      if (selector === "button") return button;
      return null;
    },
  };
  const calls = [];
  const events = {};
  const identity = { usuario: { id: 1 }, negocio: { id: 1 } };
  const host = {
    remote: true,
    identity,
    async request(route) {
      calls.push(route);
      if (result instanceof Error) throw result;
      return result;
    },
  };
  const window = {
    SocialMEIV22: host,
    addEventListener(event, callback) {
      events[event] = callback;
    },
  };
  const context = {
    window,
    document: {
      querySelectorAll() {
        return [row];
      },
    },
    location: { hash: "#/config/integracoes" },
    Node: { TEXT_NODE: 3 },
    render() {},
  };
  vm.runInNewContext(source, context);
  return { window, host, identity, calls, badge, button, text, classes, events, context };
}

(async () => {
  const allowed = browser({
    source: "server",
    whatsapp: { configured: true, receiving_configured: true, sending_available: false },
  });
  await allowed.window.SocialMEIWhatsAppReadiness.refresh();
  assert.equal(allowed.text.textContent, "Recebimento configurado");
  assert.equal(allowed.classes.has("s-ok"), true);
  assert.equal(allowed.button.disabled, true);
  assert.equal(allowed.button.textContent, "Gerenciado pela equipe");
  assert(allowed.badge.title.includes("não verificados"));
  assert(allowed.calls.every((route) => route === "/integrations/readiness"));

  const unconfigured = browser({
    source: "server",
    whatsapp: { configured: false, receiving_configured: false, sending_available: false },
  });
  await unconfigured.window.SocialMEIWhatsAppReadiness.refresh();
  assert.equal(unconfigured.text.textContent, "Não configurado");
  assert.equal(unconfigured.classes.has("s-ok"), false);

  for (const response of [
    {
      source: "server",
      whatsapp: { configured: true, receiving_configured: true, sending_available: true },
    },
    {
      source: "local",
      whatsapp: { configured: true, receiving_configured: true, sending_available: false },
    },
    new Error("provider-secret"),
  ]) {
    const failure = browser(response);
    await failure.window.SocialMEIWhatsAppReadiness.refresh();
    assert.equal(failure.text.textContent, "Estado não verificado");
    assert.equal(failure.classes.has("s-ok"), false);
    assert(!failure.badge.title.includes("provider-secret"));
  }
  const registeredOnly = browser({
    source: "server",
    whatsapp: { configured: false, receiving_configured: false, sending_available: false },
  });
  registeredOnly.text.textContent = "Canal cadastrado";
  await registeredOnly.window.SocialMEIWhatsAppReadiness.refresh();
  assert.equal(registeredOnly.text.textContent, "Canal cadastrado");
  assert.equal(registeredOnly.classes.has("s-ok"), false);
  assert(registeredOnly.badge.title.includes("não foi verificada"));

  const registeredButUnverified = browser({
    source: "local",
    instagram: { oauth_available: false },
  });
  registeredButUnverified.text.textContent = "Canal cadastrado";
  await registeredButUnverified.window.SocialMEIWhatsAppReadiness.refresh();
  assert.equal(registeredButUnverified.text.textContent, "Canal cadastrado");
  assert.equal(registeredButUnverified.classes.has("s-ok"), false);

  console.log("v22 WhatsApp readiness: synthetic UI checks passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
