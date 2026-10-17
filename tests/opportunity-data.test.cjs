const test = require("node:test");
const assert = require("node:assert/strict");
const data = require("../frontend/scripts/opportunity-data.js");
const original = {
  id: 1,
  nome: "Pessoa fictícia",
  canal: "whatsapp",
  mensagens: [
    { de: "cliente", texto: "Quero comprar." },
    { de: "empresa", texto: "Pode comprar." },
    { de: "nota", texto: "Urgente" },
    { de: "cliente", texto: " " },
  ],
};
const setup = () => ({
  enabled: true,
  remote: false,
  snapshot: [original],
  conversations: [
    {
      ...original,
      mensagens: [...original.mensagens, { de: "empresa", texto: "Rascunho local não analisado" }],
    },
  ],
});
test("analysis is opt-in and remote identities never inherit demo conversations", () => {
  assert.deepEqual(data.read({ ...setup(), enabled: false }), []);
  assert.deepEqual(data.read({ ...setup(), remote: true }), []);
});
test("only original fictional customer messages enter the queue, without invented dates", () => {
  const before = JSON.stringify(original);
  const rows = data.read(setup());
  assert.equal(rows.length, 1);
  assert.equal(rows[0].messages.length, 1);
  assert.equal(rows[0].messages[0].text, "Quero comprar.");
  assert.equal(rows[0].messages[0].at, null);
  assert.equal(JSON.stringify(original), before);
});
test("deleted conversations or reused IDs from another person/channel are not analyzed", () => {
  for (const conversations of [
    [],
    [{ ...original, nome: "Outra pessoa" }],
    [{ ...original, canal: "instagram" }],
  ])
    assert.deepEqual(data.read({ ...setup(), conversations }), []);
});
test("client lookup needs an explicit compatible ID and never a name match or remote ID collision", () => {
  const clients = [
    { id: 2, nome: "Pessoa fictícia" },
    { id: 3, nome: "Outra pessoa" },
  ];
  assert.equal(data.linkedClient(original, clients, false), null);
  assert.equal(data.linkedClient({ ...original, clientId: 2 }, clients, true), null);
  assert.equal(data.linkedClient({ ...original, clientId: 99 }, clients, false), null);
  assert.equal(data.linkedClient({ ...original, clientId: 3 }, clients, false), clients[1]);
});

test("remote messages merged into a same-name demo conversation invalidate the example", () => {
  const value = setup();
  value.conversations[0].mensagens.push({
    de: "cliente",
    texto: "Texto remoto",
    remoteId: "external",
  });
  assert.deepEqual(data.read(value), []);
});
