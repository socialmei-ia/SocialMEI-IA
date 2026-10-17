const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"),
  vm = require("node:vm");
const reports = require("../frontend/scripts/report-data.js");
const range = { from: "2026-10-01", to: "2026-10-31" },
  previousRange = { from: "2026-08-31", to: "2026-09-30" };
const sales = [
  {
    id: 1,
    data: "2026-10-10",
    cliente: '=HYPERLINK("bad")',
    item: "Corte masculino",
    valor: 100,
    status: "Pago",
    quantidade: 2,
  },
  { id: 2, data: "2026-10-11", cliente: "Cliente", item: "Perfume", valor: 50, status: "Pendente" },
  { id: 3, data: "2026-10-12", valor: 80, status: "Cancelado" },
  { id: 4, data: "2026-10-13", valor: 90, status: "Rascunho" },
  { id: 5, data: "2026-10-14", valor: 900, status: "Pago", excluida: true },
  { id: 6, data: "2026-09-10", cliente: "Cliente", item: "Ajuste", valor: 50, status: "Pago" },
  { id: 7, data: "2026-08-01", valor: 30, status: "Pago" },
].map((row) => ({ cliente: "Cliente", item: "Item", ...row }));
const ledger = [
  {
    tipo: "receita",
    descricao: "Venda já contabilizada",
    vencimento: "2026-10-10",
    valor: 100,
    status: "pago",
  },
  {
    tipo: "despesa",
    descricao: ' \t=CMD("x")',
    vencimento: "2026-10-12",
    valor: 30,
    status: "pago",
  },
  {
    tipo: "receita",
    descricao: "Em aberto",
    vencimento: "2026-10-13",
    valor: 200,
    status: "aberto",
  },
  {
    tipo: "receita",
    descricao: "Excluída",
    vencimento: "2026-10-14",
    valor: 900,
    status: "pago",
    excluida: true,
  },
];
const source = fs.readFileSync(
  require("node:path").join(__dirname, "../frontend/scripts/data-and-backup.js"),
  "utf8",
);
function metrics(range) {
  const context = vm.createContext({
    appData: { vendas: sales, financeiro: ledger },
    inRange: (date, period) => date >= period.from && date <= period.to,
  });
  vm.runInContext(
    source.slice(
      source.indexOf("function operationalMetrics("),
      source.indexOf("function emptyMarkup("),
    ),
    context,
  );
  return context.operationalMetrics(range);
}
function snapshot(options = {}) {
  return reports.snapshot({
    type: "geral",
    range,
    previousRange,
    current: metrics(range),
    previous: metrics(previousRange),
    sales,
    ledger,
    ready: { sales: true, finance: true },
    business: "MEI sintético",
    source: "API simulada · dados fictícios",
    createdAt: "2026-10-17T12:00:00Z",
    ...options,
  });
}
test("native definitions exclude drafts, cancellations, unpaid ledger and deleted records without doubling sales and revenue", () => {
  const s = snapshot();
  assert.equal(s.current.revenue, 100);
  assert.equal(s.current.received, 100);
  assert.equal(s.current.spent, 30);
  assert.equal(s.current.balance, 70);
  assert.equal(s.current.count, 1);
  assert.equal(s.current.pending, 1);
  assert.equal(s.sales.length, 4);
  assert.equal(s.ledger.length, 3);
  assert.equal(s.previous.revenue, 50);
});
test("a frozen snapshot does not change with later live records", () => {
  const s = snapshot();
  const before = s.current.revenue;
  sales[0].valor = 110;
  assert.equal(s.current.revenue, before);
  sales[0].valor = 100;
});
test("insufficient dates never establish comparison coverage; dated prior records allow conservative coverage", () => {
  assert.equal(reports.hasHistory([{ data: "2026-09-10" }], "data", previousRange), false);
  assert.equal(reports.hasHistory(sales, "data", previousRange), true);
  assert.equal(snapshot().comparison.finance, false);
});
test("only required sources block each supported type; unsupported metrics are unavailable, not zero", () => {
  assert.throws(() => snapshot({ ready: { sales: false, finance: true } }), /indisponível/);
  const finance = snapshot({ type: "financeiro", ready: { sales: false, finance: true } });
  assert.equal(finance.current.revenue, null);
  assert.equal(finance.current.balance, 70);
  assert.deepEqual(finance.sales, []);
  const s = snapshot({ type: "vendas", ready: { sales: true, finance: false } });
  assert.equal(s.current.balance, null);
  assert.equal(s.current.revenue, 100);
});
test("CSV freezes the same values, escapes quotes and protects formula/control prefixes while preserving negative numeric balances", () => {
  const s = snapshot();
  s.current.balance = -30;
  const csv = reports.csv(s);
  assert(csv.startsWith("\ufeff"));
  assert(csv.includes('"Faturamento · vendas pagas";"100";"50"'));
  assert(csv.includes('"Saldo realizado";"-30"'));
  assert(csv.includes('"\'=HYPERLINK(""bad"")"'));
  assert(csv.includes('"\' \t=CMD(""x"")"'));
  assert(csv.includes("Histórico anterior insuficiente"));
});
test("invalid data, dates and unsupported report types do not generate files", () => {
  assert.throws(() => snapshot({ type: "entregas" }));
  assert.throws(() => snapshot({ range: { from: "2026-02-30", to: "2026-03-01" } }));
  const s = snapshot();
  s.current.revenue = Infinity;
  assert.equal(reports.validSnapshot(s), false);
  assert.throws(() => reports.csv(s));
});
function fixture() {
  const memory = new Map();
  let owner = "user:1:workspace:1";
  return {
    memory,
    setScope: (value) => {
      owner = value;
    },
    repo: reports.history(
      {
        getItem: (key) => memory.get(key) || null,
        setItem: (key, value) => memory.set(key, value),
      },
      () => owner,
    ),
    scope: () => owner,
  };
}
const record = (id = "report-1") => ({
  id,
  title: "Resumo real dos registros sintéticos",
  createdAt: "2026-10-17T12:00:00Z",
  status: "ready",
  snapshot: snapshot(),
});
test("history recovers only the same user/workspace/source; absent identity and stale drafts cannot persist", () => {
  const f = fixture(),
    owner = f.scope();
  assert.equal(f.repo.save(record(), owner), true);
  f.setScope("user:2:workspace:1");
  assert.equal(f.repo.read().records.length, 0);
  assert.equal(f.repo.save(record(), owner), false);
  f.setScope("user:1:workspace:2");
  assert.equal(f.repo.read().records.length, 0);
  f.setScope(owner);
  assert.equal(f.repo.read().records.length, 1);
  f.setScope(null);
  assert.equal(f.repo.read().status, "unavailable");
  assert.equal(f.repo.save(record(), null), false);
});
test("history rejects shared prototype keys, corrupt envelopes, duplicate IDs and foreign scopes", () => {
  const f = fixture();
  f.memory.set("socialmei-relatorios-prototipo-v1", JSON.stringify([record()]));
  assert.equal(f.repo.read().records.length, 0);
  f.repo.save(record(), f.scope());
  const key = [...f.memory.keys()].find((key) => key.startsWith("socialmei-report-history"));
  for (const raw of [
    "{",
    JSON.stringify({ version: 1, scope: "foreign", records: [record()] }),
    JSON.stringify({ version: 1, scope: f.scope(), records: [record(), record()] }),
  ]) {
    f.memory.set(key, raw);
    assert.equal(f.repo.read().records.length, 0);
  }
});
test("history stores at most 20 frozen reports and explicitly rejects unavailable storage", () => {
  const f = fixture();
  for (let i = 0; i < 23; i++) assert(f.repo.save(record("id-" + i), f.scope()));
  assert.equal(f.repo.read().records.length, 20);
  const repo = reports.history(
    {
      getItem() {
        throw Error("blocked");
      },
      setItem() {
        throw Error("quota");
      },
    },
    () => f.scope(),
  );
  assert.equal(repo.read().status, "unavailable");
  assert.equal(repo.save(record(), f.scope()), false);
});
test("generation failure is a scoped record without downloadable snapshot; processing is never persisted", () => {
  const f = fixture(),
    r = { ...record(), status: "error", snapshot: null, error: "Fonte indisponível" };
  assert.equal(f.repo.save(r, f.scope()), true);
  assert.equal(f.repo.read().records[0].snapshot, null);
  assert.equal(f.repo.save({ ...r, status: "processing" }, f.scope()), false);
});

test("comparison preference is frozen and exports do not silently re-enable previous values", () => {
  const s = snapshot({ comparisonEnabled: false });
  const csv = reports.csv(s);
  assert(
    csv.includes(
      '"Faturamento · vendas pagas";"100";"Comparação desativada";"Comparação desativada"',
    ),
  );
});
test("native chart series exclude the same removed records as the operational totals", () => {
  const context = vm.createContext({
    appData: { vendas: sales, financeiro: ledger },
    inRange: (day, period) => day >= period.from && day <= period.to,
    dateShift: (date, days) =>
      new Date(Date.parse(date + "T12:00:00Z") + days * 864e5).toISOString().slice(0, 10),
    formatDate: (date) => date,
  });
  vm.runInContext(
    source.slice(
      source.indexOf("function chartSeries("),
      source.indexOf("function updatePeriodCaptions("),
    ),
    context,
  );
  const sold = context.chartSeries(range, "sales"),
    finance = context.chartSeries(range, "finance");
  assert.equal(
    sold.r.reduce((a, b) => a + b, 0),
    100,
  );
  assert.equal(
    finance.r.reduce((a, b) => a + b, 0),
    100,
  );
  assert.equal(
    finance.d.reduce((a, b) => a + b, 0),
    30,
  );
});
