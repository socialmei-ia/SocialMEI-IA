const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../frontend/scripts/v22-backend.js"), "utf8");
const start = source.indexOf("  function productForm(edit = false) {");
const end = source.indexOf("  // Incoming Meta webhooks", start);
assert(start > 0 && end > start);

function open(product) {
  let save;
  let fields;
  const calls = [];
  const inputs = {
    "#f_t": {
      value: product?.tipo || "Produto",
      addEventListener(event, callback) {
        this.change = callback;
      },
    },
    "#f_e": { disabled: false },
    "#f_m": { disabled: false },
  };
  const context = {
    S: { prod: 0 },
    data: { products: product ? [product] : [] },
    field: (id, label, value, extra) => ({ id, label, value, ...extra }),
    form(title, definitions, submit) {
      fields = definitions;
      save = submit;
    },
    dlg: () => ({ querySelector: (key) => inputs[key] }),
    money: (value) => Number(value.replace(",", ".")),
    write(...args) {
      calls.push(args);
    },
  };
  vm.createContext(context);
  vm.runInContext(source.slice(start, end), context);
  context.productForm(!!product);
  return { save: (data) => save(data), inputs, calls, fields };
}

const values = { n: "Atendimento", t: "Serviço", p: "35,00", k: "0", a: true, e: "8", m: "2" };

test("changing a stocked product into a service explicitly clears inventory", () => {
  const page = open({ id: 7, tipo: "Produto", estoque: 8, minimo: 2, versao: 3 });
  page.save(values);
  const [path, method, data] = page.calls[0];
  assert.equal(path, "/produtos/7");
  assert.equal(method, "PATCH");
  assert.equal(data.tipo, "Serviço");
  assert.equal(data.estoque, null);
  assert.equal(data.minimo, null);
  assert.equal(data.expected_version, 3);
});

test("service inventory inputs remain disabled and are restored when choosing product", () => {
  const page = open({ id: 7, tipo: "Serviço", estoque: null, minimo: null, versao: 3 });
  assert.equal(page.inputs["#f_e"].disabled, true);
  assert.equal(page.inputs["#f_m"].disabled, true);
  page.inputs["#f_t"].value = "Produto";
  page.inputs["#f_t"].change();
  assert.equal(page.inputs["#f_e"].disabled, false);
  assert.equal(page.inputs["#f_m"].disabled, false);
});

test("product inventory keeps integers and refuses fractional amounts before requesting API", () => {
  const page = open();
  assert.throws(() => page.save({ ...values, t: "Produto", e: "1.5" }), /inteiras/);
  assert.equal(page.calls.length, 0);
  page.save({ ...values, t: "Produto" });
  assert.equal(page.calls[0][2].estoque, 8);
  assert.equal(page.calls[0][2].minimo, 2);
});

test("catalog details are editable and sent with optimistic version and active state", () => {
  const page = open({
    id: 7,
    tipo: "Produto",
    categoria: "Roupas",
    descricao: "Tecido",
    versao: 3,
  });
  assert.equal(page.fields.find((f) => f.id === "c").value, "Roupas");
  assert.equal(page.fields.find((f) => f.id === "c").disabled, undefined);
  assert.equal(page.fields.find((f) => f.id === "d").value, "Tecido");
  assert.equal(page.fields.find((f) => f.id === "d").disabled, undefined);
  page.save({ ...values, t: "Produto", c: "Moda", d: "", a: false });
  assert.equal(page.calls[0][2].categoria, "Moda");
  assert.equal(page.calls[0][2].descricao, "");
  assert.equal(page.calls[0][2].status, "Inativo");
  assert.equal(page.calls[0][2].expected_version, 3);
});
