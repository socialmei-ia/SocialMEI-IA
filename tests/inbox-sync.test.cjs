const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

test("an unconfigured message integration makes no requests and schedules no polling", async () => {
  for (const endpoint of [null, undefined, "", "   "]) {
    const feedback = [];
    const labels = new Map(
      ["topSync", "integrationStatus", "channelConnectionText"].map((id) => [id, { dataset: {} }]),
    );
    const context = vm.createContext({
      N8N_MESSAGES_URL: endpoint,
      isN8nSyncing: false,
      isN8nConnected: null,
      syncState: "idle",
      lastSyncAt: null,
      currentView: "Início",
      n8nSyncTimer: 123,
      n8nBackoffLevel: 1,
      document: {
        hidden: false,
        body: { classList: { contains: () => true } },
        querySelector: () => null,
        addEventListener() {},
      },
      navigator: { onLine: true },
      $: (id) => labels.get(id),
      clearTimeout() {},
      setTimeout() {
        assert.fail("Disabled integration scheduled a timer");
      },
      fetch() {
        assert.fail("Disabled integration made a request");
      },
      toast: (...args) => feedback.push(args),
      queueInboxLayout() {},
    });
    vm.runInContext(
      fs.readFileSync(path.join(__dirname, "../frontend/scripts/inbox-sync.js"), "utf8"),
      context,
    );
    assert.equal((await context.syncN8nMessages(true)).checked, false);
    context.scheduleN8nSync({ checked: false, added: 0 });
    context.wakeN8nSync();
    context.startN8nSync();
    assert.equal(context.n8nSyncTimer, null);
    assert.equal(context.syncState, "disabled");
    assert.equal(context.isN8nConnected, false);
    assert.equal(labels.get("topSync").textContent, "Integração de mensagens não configurada");
    assert.equal(feedback.length, 1);
  }
});
