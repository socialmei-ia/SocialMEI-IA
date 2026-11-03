const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup({ role = "owner", origin = "waha", request } = {}) {
  class Element {
    constructor(tag) {
      this.tagName = tag;
      this.children = [];
      this.dataset = {};
    }
    append(...nodes) {
      for (const node of nodes) {
        node.parent = this;
        this.children.push(node);
      }
    }
    setAttribute(name, value) {
      this[name] = value;
    }
    remove() {
      if (this.parent) this.parent.children = this.parent.children.filter((x) => x !== this);
      this.parent = null;
    }
    get isConnected() {
      return this === thread || !!this.parent?.isConnected;
    }
  }
  const thread = new Element("section"),
    head = new Element("head");
  const document = {
    hidden: false,
    head,
    createElement: (tag) => new Element(tag),
    querySelector: () => thread,
  };
  const identity = { usuario: { id: 2 }, negocio: { id: 1 }, papel: role };
  const calls = [],
    pending = [],
    timers = [];
  const host = {
    remote: true,
    identity,
    conversation: () => ({ id: 31, origin }),
    async request(...args) {
      calls.push(args);
      return request
        ? request(...args)
        : { channel_id: 9, state: "menu", enabled: true, claimed_in_flight: 0 };
    },
  };
  const window = {
    SocialMEIV22: host,
    render() {},
    addEventListener() {},
    setInterval(fn) {
      timers.push(fn);
    },
  };
  const context = {
    window,
    document,
    location: { hash: "#/caixa/me-31" },
    queueMicrotask: (fn) => pending.push(fn),
    console,
  };
  const path = "frontend/scripts/v22-whatsapp-bot.js";
  vm.runInNewContext(fs.existsSync(path) ? fs.readFileSync(path, "utf8") : "", context);
  async function settle() {
    while (pending.length) {
      pending.shift()();
      await new Promise(setImmediate);
    }
  }
  const panel = () => thread.children.find((n) => n.dataset.waBot);
  const button = (text) =>
    panel()?.children.find((n) => n.tagName === "button" && n.textContent === text);
  return { host, calls, settle, panel, button, window, timers };
}

test("only an owner of a received WhatsApp conversation gets bot controls", async () => {
  for (const options of [{ role: "member" }, { origin: "instagram" }, { origin: "synthetic" }]) {
    const app = setup(options);
    await app.settle();
    assert.equal(app.panel(), undefined);
    assert.equal(app.calls.length, 0);
  }
  const app = setup();
  await app.settle();
  assert.ok(app.panel());
  assert.equal(app.calls[0][0], "/whatsapp/bot/conversations/31/status");
});

test("pause and resume await server state and use the verified channel", async () => {
  let state = "menu";
  const app = setup({
    request: async (path, method, payload) => {
      if (method === "POST") {
        assert.equal(payload.channel_id, 9);
        state = path.endsWith("/pause") ? "human" : "menu";
        return;
      }
      return { channel_id: 9, state, enabled: true, claimed_in_flight: 0 };
    },
  });
  await app.settle();
  await app.button("Assumir atendimento").onclick();
  assert.match(
    app
      .panel()
      .children.map((x) => x.textContent)
      .join(" "),
    /Atendimento humano/,
  );
  assert.equal(app.calls.filter((x) => x[1] === "POST").length, 1);
  await app.button("Retomar bot").onclick();
  assert.equal(
    app.calls.filter((x) => x[1] === "POST")[1][0],
    "/whatsapp/bot/conversations/31/resume",
  );
});

test("an uncertain write never displays a successful takeover or permits another write", async () => {
  const app = setup({
    request: async (_, method) => {
      if (method === "POST") throw Error("Conexão interrompida");
      return { channel_id: 9, state: "menu", enabled: true, claimed_in_flight: 0 };
    },
  });
  await app.settle();
  await app.button("Assumir atendimento").onclick();
  const text = app
    .panel()
    .children.map((x) => x.textContent)
    .join(" ");
  assert.match(text, /não confirmado/);
  assert.doesNotMatch(text, /Atendimento humano ativo/);
  assert.equal(app.button("Assumir atendimento").disabled, true);
});

test("late responses are ignored after changing workspace and in-flight claims are disclosed", async () => {
  let finish;
  const app = setup({
    request: () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  });
  await app.settle();
  app.host.identity.negocio.id = 4;
  finish({ channel_id: 9, state: "human", enabled: false, claimed_in_flight: 1 });
  await new Promise(setImmediate);
  assert.doesNotMatch(
    app
      .panel()
      ?.children.map((x) => x.textContent)
      .join(" ") || "",
    /Atendimento humano ativo/,
  );
  const current = setup({
    request: async () => ({ channel_id: 9, state: "human", enabled: false, claimed_in_flight: 1 }),
  });
  await current.settle();
  assert.match(
    current
      .panel()
      .children.map((x) => x.textContent)
      .join(" "),
    /já reservad/,
  );
});
