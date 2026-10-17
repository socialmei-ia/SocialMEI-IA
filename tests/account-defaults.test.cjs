const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(
  require("node:path").join(__dirname, "../frontend/scripts/app.js"),
  "utf8",
);
const startup = source.slice(
  source.indexOf("const DEFAULT_APP_DATA ="),
  source.indexOf("SocialMEIClients.attach(appData)"),
);
function initialize(remote, saved = null) {
  const context = vm.createContext({
    SOCIALMEI_APP_SCHEMA_VERSION: 1,
    SocialMEIAuth: { remote },
    structuredClone,
    saved,
  });
  vm.runInContext(
    startup +
      "\nfunction loadAppData(){ return saved || structuredClone(DEFAULT_APP_DATA); }\nglobalThis.result = appData;",
    context,
  );
  return JSON.parse(JSON.stringify(context.result));
}
test("fresh authenticated accounts never inherit demo commercial records, including local modules", () => {
  const state = initialize(true);
  for (const key of ["clientes", "produtos", "vendas", "financeiro"])
    assert.deepEqual(state[key], [], key);
});
test("the explicit public demonstration preserves its existing examples", () => {
  const state = initialize(false);
  for (const key of ["clientes", "produtos", "vendas", "financeiro"])
    assert(state[key].length > 0, key);
});
test("authenticated startup preserves business records already saved in that account scope", () => {
  const saved = {
    clientes: [{ id: 90, nome: "Cliente cadastrado" }],
    produtos: [],
    vendas: [],
    financeiro: [],
    prefs: {},
  };
  assert.deepEqual(initialize(true, saved), saved);
});
