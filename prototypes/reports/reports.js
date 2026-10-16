"use strict";
const $ = (selector) => document.querySelector(selector);
const money = (value) => value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const fixtures = {
  month: {
    labels: ["1–4 out.", "5–8 out.", "9–12 out.", "13–16 out."],
    values: [1800, 2400, 2100, 3300],
    orders: 32,
    income: 8400,
    expenses: 3200,
  },
  week: {
    labels: ["10–11 out.", "12–13 out.", "14–15 out.", "16 out."],
    values: [900, 1200, 1400, 1000],
    orders: 15,
    income: 3600,
    expenses: 1400,
  },
};
let privateValues = false;
let selectedView = "summary";
function render() {
  const data = fixtures[$("#period").value];
  const state = $("#scenario").value;
  const ready = state === "ready";
  const total = data.values.reduce((sum, value) => sum + value, 0);
  const display = (value, count = false) =>
    privateValues
      ? "••••"
      : state === "empty"
        ? count
          ? "0"
          : money(0)
        : !ready
          ? "—"
          : count
            ? String(value)
            : money(value);
  const metrics = {
    sales: total,
    orders: data.orders,
    ticket: total / data.orders,
    balance: data.income - data.expenses,
  };
  for (const [key, value] of Object.entries(metrics))
    $(`[data-value="${key}"]`).textContent = display(value, key === "orders");
  $("#context").textContent = {
    ready: `Dados fictícios · ${$("#period").value === "month" ? "01–16" : "10–16"} de outubro de 2026.`,
    empty: "Nenhum registro neste período. Os indicadores refletem uma leitura concluída.",
    loading: "Carregando os registros do período…",
    error:
      "Não foi possível ler os registros. Os valores estão indisponíveis; isso não significa saldo zero.",
  }[state];
  $("#chart").hidden = !ready || privateValues;
  $("#chart-details").hidden = !ready || privateValues;
  $("#chart-message").hidden = ready && !privateValues;
  $("#chart-message").textContent = privateValues
    ? "Valores ocultos. Use “Mostrar valores” para visualizar o gráfico e a tabela."
    : {
        empty: "As vendas aparecerão aqui quando houver registros no período.",
        loading: "Aguardando a leitura dos registros.",
        error: "Gráfico indisponível enquanto a leitura não for concluída.",
      }[state];
  $("#chart").replaceChildren();
  $("#chart-table").replaceChildren();
  data.values.forEach((value, index) => {
    const group = document.createElement("div");
    group.className = "bar-group";
    group.setAttribute("aria-hidden", "true");
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.height = `${(value / Math.max(...data.values)) * 85}%`;
    const label = document.createElement("span");
    label.textContent = data.labels[index];
    group.append(bar, label);
    if (ready && !privateValues) $("#chart").append(group);
    if (ready && !privateValues) {
      const row = document.createElement("tr");
      for (const text of [data.labels[index], money(value)]) {
        const cell = document.createElement("td");
        cell.textContent = text;
        row.append(cell);
      }
      $("#chart-table").append(row);
    }
  });
  $("#care-title").textContent = ready
    ? "Confira o movimento financeiro"
    : state === "empty"
      ? "Comece pelos registros"
      : "Aguarde os dados para decidir";
  $("#care-copy").textContent = ready
    ? "Compare as entradas e saídas registradas para entender o saldo do período. Faturamento e movimento de caixa são informações diferentes."
    : state === "empty"
      ? "Registre vendas, entradas e saídas para acompanhar o resultado do seu negócio."
      : "Sem uma leitura concluída, não é possível indicar um próximo cuidado com base nos registros.";
  $("#care-detail").hidden = !ready;
  $(".breakdowns").hidden = !ready;
  $("#finance-detail").textContent =
    `Entradas: ${display(data.income)}. Saídas: ${display(data.expenses)}. Saldo: ${display(data.income - data.expenses)}.`;
  $("#print-period").textContent = "Período: " + periodText() + " · dados fictícios";
  renderDetails(data, state, display);
  if (!ready || privateValues)
    document.querySelectorAll("details").forEach((element) => {
      element.open = false;
    });
}
$("#period").addEventListener("change", render);
$("#scenario").addEventListener("change", render);
$("#privacy").addEventListener("click", () => {
  privateValues = !privateValues;
  $("#privacy").setAttribute("aria-pressed", String(privateValues));
  $("#privacy").textContent = privateValues ? "Mostrar valores" : "Ocultar valores";
  render();
});
$("#theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("#theme").setAttribute("aria-pressed", String(dark));
  $("#theme").textContent = dark ? "Tema claro" : "Tema escuro";
});
function createTable(headers, rows) {
  const table = document.createElement("table");
  const caption = table.createCaption();
  caption.textContent = "Exemplo fictício · " + periodText();
  const head = table.createTHead().insertRow();
  headers.forEach((text) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = text;
    head.append(cell);
  });
  const body = table.createTBody();
  rows.forEach((row) => {
    const tr = body.insertRow();
    row.forEach((text) => {
      tr.insertCell().textContent = text;
    });
  });
  return table;
}
function renderDetails(data, state, display) {
  const ready = state === "ready",
    summary = selectedView === "summary";
  $(".overview").hidden = !summary;
  $(".breakdowns").hidden = !summary || !ready || privateValues;
  $("#view-detail").hidden = summary;
  $("#view-table").replaceChildren();
  const total = data.values.reduce((sum, value) => sum + value, 0);
  const info = {
    sales: [
      "Vendas pagas por intervalo",
      "Faturamento reconhecido pelas vendas pagas. Não representa dinheiro disponível em conta.",
    ],
    clients: [
      "Participação dos clientes",
      "Distribuição fictícia do faturamento. Clientes identificados apenas para esta demonstração.",
    ],
    service: [
      "Atendimento demonstrativo",
      "O histórico demonstrativo é separado das vendas. Não há WhatsApp conectado nem envio de mensagens neste protótipo.",
    ],
    finance: [
      "Movimento financeiro",
      "Entradas e saídas registradas. O saldo do período não representa saldo bancário.",
    ],
  }[selectedView];
  if (info) {
    $("#view-title").textContent = info[0];
    $("#view-copy").textContent = info[1];
  }
  if (!summary && (!ready || privateValues)) {
    const note = document.createElement("p");
    note.textContent = privateValues
      ? "Valores ocultos."
      : state === "empty"
        ? "Nenhum registro no período."
        : "Aguardando uma leitura concluída.";
    $("#view-table").append(note);
  } else if (!summary) {
    const tables = {
      sales: [
        ["Intervalo", "Faturamento"],
        data.values.map((value, i) => [data.labels[i], money(value)]),
      ],
      clients: [
        ["Cliente fictício", "Total pago"],
        [0.4, 0.35, 0.25].map((share, i) => [
          `Cliente ${String.fromCharCode(65 + i)}`,
          money(total * share),
        ]),
      ],
      finance: [
        ["Movimento", "Valor"],
        [
          ["Entradas", money(data.income)],
          ["Saídas", money(data.expenses)],
          ["Saldo", money(data.income - data.expenses)],
        ],
      ],
      service: [
        ["Conversa fictícia", "Estado local"],
        [
          ["Cliente A", "Rascunho, sem envio"],
          ["Cliente B", "Exemplo de conversa"],
        ],
      ],
    };
    $("#view-table").append(createTable(...tables[selectedView]));
  }
  document
    .querySelectorAll(".report-tabs button")
    .forEach((button) =>
      button.setAttribute("aria-pressed", String(button.dataset.reportView === selectedView)),
    );
  document.querySelectorAll(".metrics article").forEach((article, i) => {
    article.querySelector(".variation")?.remove();
    if (!$("#compare").checked) return;
    const note = document.createElement("span");
    note.className = "variation";
    const previous = [
      total * 0.8,
      Math.round(data.orders * 0.8),
      (total * 0.8) / Math.round(data.orders * 0.8),
      (data.income - data.expenses) * 0.8,
    ];
    note.textContent = !ready
      ? "Comparação indisponível"
      : privateValues
        ? "Comparação oculta"
        : "Anterior fictício: " + (i === 1 ? String(Math.round(previous[i])) : money(previous[i]));
    article.append(note);
  });
  $("#export-report").disabled = !ready || privateValues;
  $("#copy-report").disabled = !ready || privateValues;
  $("#export-status").textContent = "";
}
$("#compare").addEventListener("change", render);
document.querySelectorAll(".report-tabs button").forEach((button) =>
  button.addEventListener("click", () => {
    selectedView = button.dataset.reportView;
    render();
  }),
);
function periodText() {
  return $("#period").value === "month"
    ? "01 a 16 de outubro de 2026"
    : "10 a 16 de outubro de 2026";
}
function summaryText() {
  return [
    "SocialMEI.IA · RELATÓRIO FICTÍCIO",
    periodText(),
    ...[...document.querySelectorAll(".metrics article")].map(
      (article) =>
        `${article.querySelector("h2").textContent}: ${article.querySelector("strong").textContent}`,
    ),
  ].join("\n");
}
$("#copy-report").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(summaryText());
    $("#export-status").textContent = "Resumo fictício copiado.";
  } catch {
    $("#export-status").textContent =
      "Não foi possível copiar. Use a impressão para salvar a demonstração.";
  }
});
$("#export-report").addEventListener("click", () => {
  const data = fixtures[$("#period").value];
  const csv = [
    "Origem;Dados fictícios",
    "Intervalo;Faturamento de vendas pagas",
    ...data.values.map((value, i) => `${data.labels[i]};${value.toFixed(2).replace(".", ",")}`),
  ].join("\r\n");
  const url = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "socialmei-relatorio-ficticio.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  $("#export-status").textContent =
    "CSV de vendas fictícias gerado. Nenhum dado real foi exportado.";
});
$("#print-report").addEventListener("click", () => window.print());
render();
