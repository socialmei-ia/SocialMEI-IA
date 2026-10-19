const { test } = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs"),
  vm = require("node:vm"),
  path = require("node:path");
test("demo conversations cannot inherit drafts, notes or state of a real contact with the same name", () => {
  const source = fs.readFileSync(path.join(__dirname, "../frontend/scripts/inbox.js"), "utf8");
  const context = vm.createContext({});
  vm.runInContext(
    source.slice(
      source.indexOf("function conversationKey("),
      source.indexOf("function isReducedMotion("),
    ),
    context,
  );
  const real = { canal: "whatsapp", nome: "Pessoa QA" },
    sample = { ...real, _socialmeiDemoSample: true };
  assert.equal(context.conversationKey(real), "whatsapp:pessoa qa");
  assert.equal(context.conversationKey(sample), "demo:whatsapp:pessoa qa");
  assert.notEqual(context.conversationKey(real), context.conversationKey(sample));
});
test("feedback uses status for real success/info and alert for failures, escaping dynamic text", () => {
  const source = fs.readFileSync(path.join(__dirname, "../frontend/scripts/dialogs.js"), "utf8"),
    nodes = [];
  const context = vm.createContext({
    document: {
      createElement() {
        return {
          dataset: {},
          style: {},
          attrs: {},
          setAttribute(k, v) {
            this.attrs[k] = v;
          },
          addEventListener() {},
          remove() {},
        };
      },
    },
    $: () => ({
      appendChild(n) {
        nodes.push(n);
      },
    }),
    renderIcon: (type) => '<svg data-icon="' + type + '"></svg>',
    escapeHtml: (t) => String(t).replace(/</g, "&lt;"),
    window: { SocialMEIMotion: { ms: () => 100, reduced: false } },
    performance: { now: () => 0 },
    TOAST_TIMERS: new Set(),
    setTimeout: () => 1,
    clearTimeout() {},
  });
  vm.runInContext(
    source.slice(
      source.indexOf("function toast("),
      source.indexOf("function openRecord(", source.indexOf("function toast(")),
    ),
    context,
  );
  context.toast("Dados de teste ativados", "", "info");
  assert.equal(nodes[0].attrs.role, "status");
  assert.equal(nodes[0].dataset.tone, "info");
  context.toast("Não foi possível salvar", "<script>");
  assert.equal(nodes[1].attrs.role, "alert");
  assert.equal(nodes[1].dataset.tone, "error");
  assert(nodes[1].innerHTML.includes("&lt;script>"));
  context.toast("Registro salvo");
  assert.equal(nodes[2].dataset.tone, "success");
});
