const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const context = vm.createContext({
  document: { addEventListener() {}, getElementById: () => null },
});
vm.runInContext(fs.readFileSync("frontend/scripts/data-and-backup.js", "utf8"), context);
test("avatar initials ignore annotations, punctuation and emoji while preserving Portuguese letters", () => {
  for (const [name, expected] of [
    ["Lia (exemplo)", "LI"],
    ["Bia (exemplo)", "BI"],
    ["João da Silva", "JS"],
    ["Érica de Sá", "ÉS"],
    ["Ana-Maria d’Ávila", "AD"],
    ["  Maria   Clara  ", "MC"],
    ["💈 José 👨🏽‍🔧 Luís", "JL"],
    ["A\u0301lvaro de Assunção", "ÁA"],
    ["(exemplo) Luís", "LU"],
    ["123 — 🎉", "CL"],
    ["", "CL"],
    [null, "CL"],
  ])
    assert.equal(context.initialsFromName(name), expected, String(name));
});
test("unread conversation and message counts remain distinct and ignore invalid metadata", () => {
  const result = context.conversationCounts([
    { naoLidas: 4, status: "aberto" },
    { naoLidas: 2, status: "andamento" },
    { naoLidas: 0, status: "resolvido" },
    { naoLidas: -3, status: "aberto" },
    { naoLidas: NaN, status: "resolvido" },
  ]);
  assert.equal(result.total, 5);
  assert.equal(result.unreadMessages, 6);
  assert.equal(result.unreadConversations, 2);
  assert.equal(result.pending, 2);
});
