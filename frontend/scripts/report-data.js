/* Frozen report snapshots use the application's operational metrics, never synthetic series. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIReportData = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  const types = { geral: "Visão geral", vendas: "Vendas", financeiro: "Financeiro" };
  const definitions = {
    revenue: ["Faturamento · vendas pagas", "money"],
    ticket: ["Ticket médio", "money"],
    count: ["Vendas pagas", "number"],
    received: ["Receitas recebidas", "money"],
    spent: ["Despesas pagas", "money"],
    balance: ["Saldo realizado", "money"],
    pending: ["Vendas pendentes", "number"],
  };
  const date = (value) =>
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(value + "T12:00:00Z")) &&
    new Date(value + "T12:00:00Z").toISOString().slice(0, 10) === value;
  const validRange = (range) => date(range?.from) && date(range?.to) && range.from <= range.to;
  const text = (value, limit = 400) => (typeof value === "string" ? value.slice(0, limit) : "");
  function hasHistory(rows, field, previousRange) {
    return rows.some(
      (row) => !row.excluida && date(row[field]) && row[field] <= previousRange.from,
    );
  }
  function snapshot({
    type = "geral",
    range,
    previousRange,
    current,
    previous,
    sales,
    ledger,
    ready,
    business,
    source,
    createdAt,
    comparisonEnabled = true,
  }) {
    if (!Object.hasOwn(types, type) || !validRange(range) || !validRange(previousRange))
      throw Error("Tipo ou período inválido.");
    if ((type !== "financeiro" && !ready.sales) || (type !== "vendas" && !ready.finance))
      throw Error(
        "Uma fonte necessária está indisponível. Recarregue o módulo antes de gerar ou exportar.",
      );
    const totals = (metrics) => ({
      revenue: type === "financeiro" ? null : metrics.revenue,
      ticket: type === "financeiro" ? null : metrics.ticket,
      count: type === "financeiro" ? null : metrics.paidSales.length,
      pending: type === "financeiro" ? null : metrics.pendingSales.length,
      received: type === "vendas" ? null : metrics.received,
      spent: type === "vendas" ? null : metrics.spent,
      balance: type === "vendas" ? null : metrics.balance,
    });
    const result = {
      version: 1,
      comparisonEnabled,
      type,
      range: { from: range.from, to: range.to },
      previousRange: { from: previousRange.from, to: previousRange.to },
      business: text(business, 160),
      source: text(source, 1400),
      createdAt,
      current: totals(current),
      previous: totals(previous),
      comparison: {
        sales: hasHistory(sales, "data", previousRange),
        finance: hasHistory(ledger, "vencimento", previousRange),
      },
      sales:
        type === "financeiro"
          ? []
          : current.sales
              .filter((row) => !row.excluida)
              .map((row) => ({
                id: row.id,
                data: row.data,
                cliente: text(row.cliente, 10000),
                item: text(row.item, 10000),
                valor: row.valor,
                status: text(row.status, 40),
                quantidade: row.quantidade ?? null,
              })),
      ledger:
        type === "vendas"
          ? []
          : current.ledger
              .filter((row) => !row.excluida)
              .map((row) => ({
                tipo: row.tipo,
                descricao: text(row.descricao, 10000),
                vencimento: row.vencimento,
                valor: row.valor,
                status: row.status,
              })),
      notes:
        "Faturamento considera somente vendas pagas. Receitas e despesas são lançamentos pagos pelo vencimento, separados das vendas, sem soma duplicada. Saldo não representa saldo bancário. Não há dados de entrega ou de atendimento concluído.",
    };
    if (!validSnapshot(result)) throw Error("Os dados não puderam ser validados para exportação.");
    return result;
  }
  function validSnapshot(s) {
    return (
      !!s &&
      s.version === 1 &&
      typeof s.comparisonEnabled === "boolean" &&
      Object.hasOwn(types, s.type) &&
      validRange(s.range) &&
      validRange(s.previousRange) &&
      typeof s.business === "string" &&
      typeof s.source === "string" &&
      typeof s.notes === "string" &&
      Number.isFinite(Date.parse(s.createdAt)) &&
      [s.current, s.previous].every(
        (totals) =>
          totals &&
          Object.keys(definitions).every(
            (key) =>
              totals[key] === null ||
              (typeof totals[key] === "number" && Number.isFinite(totals[key])),
          ),
      ) &&
      typeof s.comparison?.sales === "boolean" &&
      typeof s.comparison?.finance === "boolean" &&
      Array.isArray(s.sales) &&
      Array.isArray(s.ledger) &&
      s.sales.length <= 10000 &&
      s.ledger.length <= 10000 &&
      s.sales.every(
        (row) =>
          Number.isSafeInteger(row.id) &&
          date(row.data) &&
          ["cliente", "item", "status"].every((key) => typeof row[key] === "string") &&
          Number.isFinite(row.valor) &&
          row.valor >= 0 &&
          (row.quantidade === null || (Number.isFinite(row.quantidade) && row.quantidade >= 0)),
      ) &&
      s.ledger.every(
        (row) =>
          ["receita", "despesa"].includes(row.tipo) &&
          date(row.vencimento) &&
          typeof row.descricao === "string" &&
          ["pago", "aberto"].includes(row.status) &&
          Number.isFinite(row.valor) &&
          row.valor >= 0,
      )
    );
  }
  function csv(s) {
    if (!validSnapshot(s)) throw Error("Relatório inválido.");
    const rows = [
      ["SocialMEI.IA · Relatório", types[s.type]],
      ["Negócio", s.business],
      ["Fonte", s.source],
      ["Gerado em", s.createdAt],
      ["Período inicial", s.range.from],
      ["Período final", s.range.to],
      ["Anterior inicial", s.previousRange.from],
      ["Anterior final", s.previousRange.to],
      [],
      ["Indicador", "Atual", "Anterior", "Comparação disponível"],
    ];
    Object.entries(definitions).forEach(([key, [label, format]]) => {
      if (s.current[key] !== null)
        rows.push([
          label,
          format === "money" ? Number(s.current[key].toFixed(2)) : s.current[key],
          s.comparisonEnabled
            ? format === "money"
              ? Number(s.previous[key].toFixed(2))
              : s.previous[key]
            : "Comparação desativada",
          !s.comparisonEnabled
            ? "Comparação desativada"
            : s.comparison[["received", "spent", "balance"].includes(key) ? "finance" : "sales"]
              ? "Sim"
              : "Histórico anterior insuficiente",
        ]);
    });
    rows.push(
      [],
      ["VENDAS"],
      ["id", "data", "cliente", "item", "valor", "status", "quantidade"],
      ...s.sales.map((row) => [
        row.id,
        row.data,
        row.cliente,
        row.item,
        row.valor,
        row.status,
        row.quantidade ?? "Não informada",
      ]),
      [],
      ["FINANCEIRO"],
      ["tipo", "descricao", "vencimento", "valor", "status"],
      ...s.ledger.map((row) => [row.tipo, row.descricao, row.vencimento, row.valor, row.status]),
      [],
      ["Definições", s.notes],
    );
    const safe = (value) => {
      const valueText = String(value ?? "Indisponível");
      return typeof value !== "number" && /^[\s\u0000-\u001f]*[=+@\-]|^[\t\r\n]/.test(valueText)
        ? "'" + valueText
        : valueText;
    };
    return (
      "\ufeff" +
      rows
        .map((row) => row.map((value) => '"' + safe(value).replace(/"/g, '""') + '"').join(";"))
        .join("\r\n")
    );
  }
  function validRecord(record) {
    return (
      record &&
      typeof record.id === "string" &&
      record.id.length <= 100 &&
      typeof record.title === "string" &&
      record.title.length <= 240 &&
      Number.isFinite(Date.parse(record.createdAt)) &&
      (record.status === "ready"
        ? validSnapshot(record.snapshot)
        : record.status === "error" && record.snapshot === null && typeof record.error === "string")
    );
  }
  function history(storage, getScope) {
    const key = (scope) => "socialmei-report-history-v1:" + encodeURIComponent(scope);
    const read = () => {
      try {
        const scope = getScope();
        if (!scope) return { status: "unavailable", records: [] };
        const raw = storage.getItem(key(scope));
        if (!raw) return { status: "empty", records: [] };
        if (raw.length > 6000000) return { status: "invalid", records: [] };
        const value = JSON.parse(raw);
        if (
          value?.version !== 1 ||
          value.scope !== scope ||
          !Array.isArray(value.records) ||
          value.records.length > 20 ||
          !value.records.every(validRecord) ||
          new Set(value.records.map((record) => record.id)).size !== value.records.length
        )
          return { status: "invalid", records: [] };
        return { status: "saved", records: value.records };
      } catch (_) {
        return { status: "unavailable", records: [] };
      }
    };
    return {
      read,
      save(record, expectedScope) {
        try {
          const scope = getScope();
          if (!scope || scope !== expectedScope || !validRecord(record)) return false;
          const previous = read();
          if (["invalid", "unavailable"].includes(previous.status)) return false;
          const records = [
            record,
            ...previous.records.filter((item) => item.id !== record.id),
          ].slice(0, 20);
          const serialized = JSON.stringify({ version: 1, scope, records });
          if (serialized.length > 6000000) return false;
          storage.setItem(key(scope), serialized);
          return true;
        } catch (_) {
          return false;
        }
      },
    };
  }
  return { types, definitions, validRange, hasHistory, snapshot, validSnapshot, csv, history };
});
