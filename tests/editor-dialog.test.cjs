const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const scripts = path.join(__dirname, "../frontend/scripts");
const editor = fs.readFileSync(path.join(scripts, "record-editor.js"), "utf8");
const dialogs = fs.readFileSync(path.join(scripts, "dialogs.js"), "utf8");
const editSource = editor.slice(
  editor.indexOf("async function saveRecordEdit("),
  editor.indexOf("\n// Confirmação explícita"),
);
const createSource = dialogs.slice(
  dialogs.indexOf("async function handleCreate("),
  dialogs.indexOf("\nfunction globalSearchItems("),
);

function setup(type) {
  let resolveOperation;
  const pending = new Promise((resolve) => {
    resolveOperation = resolve;
  });
  const modal = { _closeEpoch: 1 };
  const fields = {
    nome: "Registro QA",
    telefone: "",
    instagram: "",
    observacao: "",
    status: "aberto",
    tags: "",
    tipo: "Produto",
    preco: "10",
    custo: "5",
    estoque: "10",
    minimo: "1",
    cliente: "1",
    item: "2",
    quantidade: "2",
    desconto: "0",
    pagamento: "Pix",
    data: "2026-10-13",
    descricao: "Registro QA",
    pessoa: "",
    valor: "10",
    vencimento: "2026-10-13",
  };
  const store = { remote: true, create: () => pending, update: () => pending };
  const closed = [];
  const notifications = [];
  const context = vm.createContext({
    activeRecordEdit: { type, id: 1, versao: 1 },
    appData: {},
    cloneData: structuredClone,
    validateRequiredFormText: () => true,
    findBusinessRecord: () => ({ id: 1, versao: 1, tipo: "receita" }),
    SocialMEIDemoData: { enabled: () => false },
    SocialMEIClients: store,
    SocialMEIProducts: store,
    SocialMEISales: store,
    SocialMEIFinance: store,
    todayISO: () => "2026-10-13",
    closeModal: (id) => closed.push(id),
    toast: (title) => notifications.push(title),
    $: (id) => (id === "createModal" ? modal : id === "createType" ? { value: type } : {}),
    FormData: class {
      *[Symbol.iterator]() {
        yield* Object.entries(fields);
      }
    },
  });
  vm.runInContext(editSource + "\n" + createSource, context);
  return { context, modal, closed, notifications, fields, resolveOperation };
}

test("late remote edits preserve a newer editor for the same record", async () => {
  for (const type of ["clients", "products", "sales", "finance"]) {
    const fixture = setup(type);
    const request = fixture.context.saveRecordEdit({});
    const newer = { type, id: 1, versao: 2 };
    fixture.context.activeRecordEdit = newer;
    fixture.resolveOperation({ id: 1 });
    await request;
    assert.equal(fixture.context.activeRecordEdit, newer, type);
    assert.deepEqual(fixture.closed, [], type);
    assert.equal(fixture.notifications.length, 1, type);
  }
});

test("completed remote edits close their own editor and retain feedback", async () => {
  for (const type of ["clients", "products", "sales", "finance"]) {
    const fixture = setup(type);
    const request = fixture.context.saveRecordEdit({});
    fixture.resolveOperation({ id: 1 });
    await request;
    assert.equal(fixture.context.activeRecordEdit, null, type);
    assert.deepEqual(fixture.closed, ["createModal"], type);
    assert.equal(fixture.notifications.length, 1, type);
  }
});

test("late remote creations preserve a reopened form", async () => {
  for (const type of ["cliente", "produto", "venda", "receita"]) {
    const fixture = setup(type);
    const request = fixture.context.handleCreate(fixture.fields);
    fixture.modal._closeEpoch++;
    fixture.resolveOperation({ id: 1 });
    await request;
    assert.deepEqual(fixture.closed, [], type);
    assert.equal(fixture.notifications.length, 1, type);
  }
});

test("completed remote creations close their own form and retain feedback", async () => {
  for (const type of ["cliente", "produto", "venda", "receita"]) {
    const fixture = setup(type);
    const request = fixture.context.handleCreate(fixture.fields);
    fixture.resolveOperation({ id: 1 });
    await request;
    assert.deepEqual(fixture.closed, ["createModal"], type);
    assert.equal(fixture.notifications.length, 1, type);
  }
});

test("demo presentation refuses pending editor saves before invoking remote stores", async () => {
  for (const type of ["clients", "products", "sales", "finance"]) {
    const fixture = setup(type);
    let writes = 0;
    fixture.context.SocialMEIDemoData.enabled = () => true;
    fixture.context.SocialMEIClients.update = () => {
      writes++;
      return Promise.resolve({ id: 1 });
    };
    await fixture.context.saveRecordEdit({});
    assert.equal(writes, 0);
    assert.equal(fixture.context.activeRecordEdit.type, type);
    assert.deepEqual(fixture.closed, []);
  }
});
