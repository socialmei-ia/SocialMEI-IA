"use strict";
const examples = [
  {
    id: "ana",
    name: "Ana Paula",
    initials: "AP",
    segment: "Vestuário",
    interest: "Duas peças em azul, tamanho M",
    signal: "Perguntou sobre disponibilidade",
    time: "Hoje, 10:42 · WhatsApp",
    stage: "Em conversa",
    reasons: ["Perguntou sobre preço e disponibilidade", "Informou tamanho e quantidade"],
    history: [
      "Pediu duas peças em azul",
      "Perguntou os tamanhos disponíveis",
      "Iniciou uma conversa",
    ],
    signalType: "explicit",
  },
  {
    id: "rafael",
    name: "Rafael Costa",
    initials: "RC",
    segment: "Manutenção",
    interest: "Orçamento de revisão da bicicleta",
    signal: "Pediu um orçamento",
    time: "Hoje, 09:18 · WhatsApp",
    stage: "Proposta enviada",
    reasons: ["Pediu um orçamento detalhado", "Informou quando pode levar a bicicleta"],
    history: [
      "Recebeu proposta ilustrativa",
      "Descreveu o reparo necessário",
      "Pediu informações sobre revisão",
    ],
    signalType: "explicit",
  },
  {
    id: "juliana",
    name: "Juliana Lima",
    initials: "JL",
    segment: "Beleza e cuidados",
    interest: "Horários para corte e hidratação",
    signal: "Consultou horários da semana",
    time: "Ontem, 16:20 · Instagram",
    stage: "Em conversa",
    reasons: ["Perguntou quais horários estão livres", "Demonstrou interesse em dois serviços"],
    history: [
      "Consultou horários disponíveis",
      "Perguntou sobre hidratação",
      "Conheceu o perfil do negócio",
    ],
    signalType: "exploring",
  },
  {
    id: "marcos",
    name: "Marcos Alves",
    initials: "MA",
    segment: "Serviços",
    interest: "Identidade visual para o negócio",
    signal: "Pediu exemplos de trabalhos",
    time: "Ontem, 14:06 · Instagram",
    stage: "Novo contato",
    reasons: ["Pediu referências de trabalhos anteriores", "Ainda está explorando possibilidades"],
    history: [
      "Recebeu portfólio ilustrativo",
      "Pediu exemplos de identidade visual",
      "Iniciou contato",
    ],
    signalType: "exploring",
  },
  {
    id: "beatriz",
    name: "Beatriz Souza",
    initials: "BS",
    segment: "Presentes",
    interest: "Caneca para presente",
    signal: "Primeiro contato, sem pedido",
    time: "Há 3 dias · WhatsApp",
    stage: "Novo contato",
    reasons: [
      "Perguntou quais tipos de presente existem",
      "Ainda não escolheu produto ou quantidade",
    ],
    history: ["Conheceu opções de presentes", "Iniciou uma conversa"],
    signalType: "initial",
  },
  {
    id: "lucas",
    name: "Lucas Mendes",
    initials: "LM",
    segment: "Barbearia",
    interest: "Informações sobre o atendimento",
    signal: "Enviou uma saudação",
    time: "Há 4 dias · Instagram",
    stage: "Novo contato",
    reasons: [
      "Iniciou uma conversa sem detalhar interesse",
      "Ainda não indicou serviço ou horário",
    ],
    history: ["Enviou uma saudação", "Conheceu o perfil do negócio"],
    signalType: "initial",
  },
];
const $ = (selector) => document.querySelector(selector);
const labels = {
  explicit: "Pedido explícito",
  exploring: "Interesse a esclarecer",
  initial: "Contato inicial",
};
const stages = ["Novo contato", "Em conversa", "Proposta enviada"];
let opportunities = structuredClone(examples),
  view = "list",
  selectedId = null,
  panel = "signals";
const drafts = new Map();
const escapeHTML = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );
const normalize = (value) =>
  value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
function render() {
  const query = normalize($("#search").value.trim());
  const visible = opportunities.filter(
    (item) =>
      ($("#signal").value === "all" || item.signalType === $("#signal").value) &&
      normalize(item.name + " " + item.interest + " " + item.signal).includes(query),
  );
  $("#total").textContent = opportunities.length;
  $("#explicit").textContent = opportunities.filter(
    (item) => item.signalType === "explicit",
  ).length;
  $("#exploring").textContent = opportunities.filter(
    (item) => item.signalType === "exploring",
  ).length;
  $("#results-status").textContent =
    `${visible.length} de ${opportunities.length} exemplos · sem ordenação por chance de compra`;
  const row = (item) =>
    `<article class="row"><div><strong>${escapeHTML(item.name)}</strong><p>${escapeHTML(item.segment)} · ${escapeHTML(item.stage)}</p></div><div><p>${escapeHTML(item.interest)}</p><span class="badge">${labels[item.signalType]}</span></div><p>${escapeHTML(item.signal)}</p><button data-open="${item.id}" aria-label="Ver detalhes de ${escapeHTML(item.name)}">Ver detalhes</button></article>`;
  $("#results").innerHTML = !visible.length
    ? '<div class="empty"><h2>Nenhum exemplo encontrado</h2><p>Tente outro interesse ou limpe os filtros.</p><button id="clear">Limpar filtros</button></div>'
    : view === "list"
      ? `<div class="collection">${visible.map(row).join("")}</div>`
      : `<div class="board">${stages
          .map(
            (stage) =>
              `<section><h2>${stage}</h2>${
                visible
                  .filter((item) => item.stage === stage)
                  .map(row)
                  .join("") || '<p class="muted">Nenhum exemplo nesta etapa.</p>'
              }</section>`,
          )
          .join("")}</div>`;
  document
    .querySelectorAll("[data-view]")
    .forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.view === view)));
}
function renderPanel() {
  const item = opportunities.find((item) => item.id === selectedId);
  $("#detail-title").textContent = item.name;
  $("#detail-interest").textContent = item.interest + " · exemplo fictício";
  $("#stage").value = item.stage;
  document
    .querySelectorAll("[data-panel]")
    .forEach((button) =>
      button.setAttribute("aria-pressed", String(button.dataset.panel === panel)),
    );
  $("#detail-content").innerHTML =
    panel === "signals"
      ? `<h3>Por que acompanhar</h3><p class="muted">Classificação manual: ${labels[item.signalType]}. Não é uma previsão de compra.</p><ul>${item.reasons.map((reason) => `<li>${escapeHTML(reason)}<br><small class="muted">Sinal sintético, sem peso calculado</small></li>`).join("")}</ul><button id="prepare" class="primary">Preparar próximo contato</button>`
      : panel === "conversation"
        ? `<h3>Contexto na Caixa Unificada</h3><p class="muted">Demonstração contextual; não é a Caixa real.</p><div class="timeline">${item.history.map((event) => `<p>${escapeHTML(event)}<br><small class="muted">Evento fictício</small></p>`).join("")}</div><label for="draft">Rascunho de retorno</label><textarea id="draft" placeholder="Escreva uma sugestão local">${escapeHTML(drafts.get(item.id) || "")}</textarea><button id="save-draft">Guardar na demonstração</button>`
        : `<h3>Cliente 360 · exemplo</h3><dl class="review-list"><dt>Pessoa</dt><dd>${escapeHTML(item.name)}</dd><dt>Interesse</dt><dd>${escapeHTML(item.interest)}</dd><dt>Etapa</dt><dd>${escapeHTML(item.stage)}</dd><dt>Origem</dt><dd>Exemplo sintético, sem vínculo com o CRM</dd></dl><h3>Histórico resumido</h3><ul>${item.history.map((event) => `<li>${escapeHTML(event)}</li>`).join("")}</ul>`;
}
$("#search").addEventListener("input", render);
$("#signal").addEventListener("change", render);
document.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.view) {
    view = button.dataset.view;
    render();
  }
  if (button.dataset.open) {
    selectedId = button.dataset.open;
    panel = "signals";
    $("#detail-status").textContent = "";
    renderPanel();
    $("#detail").showModal();
  }
  if (button.dataset.panel) {
    panel = button.dataset.panel;
    $("#detail-status").textContent = "";
    renderPanel();
  }
  if (button.id === "prepare") {
    const item = opportunities.find((item) => item.id === selectedId);
    if (!drafts.has(item.id))
      drafts.set(
        item.id,
        `Olá, ${item.name.split(" ")[0]}! Podemos conversar sobre ${item.interest.toLowerCase()}?`,
      );
    panel = "conversation";
    renderPanel();
    $("#detail-status").textContent = "Sugestão local preparada. Revise; nada foi enviado.";
    $("#draft").focus();
  }
  if (button.id === "save-draft") {
    $("#detail-status").textContent = "Rascunho guardado somente nesta prévia. Nada foi enviado.";
  }
  if (button.id === "clear") {
    $("#search").value = "";
    $("#signal").value = "all";
    render();
    $("#search").focus();
  }
});
$("#detail-content").addEventListener("input", (event) => {
  if (event.target.id === "draft") drafts.set(selectedId, event.target.value);
});
$("#stage").addEventListener("change", () => {
  opportunities.find((item) => item.id === selectedId).stage = $("#stage").value;
  render();
  $("#detail-status").textContent = "Etapa alterada só na demonstração.";
  if (panel === "client") renderPanel();
});
$("#detail").addEventListener("close", () =>
  document.querySelector(`[data-open="${selectedId}"]`)?.focus(),
);
$("#reset").addEventListener("click", () => {
  opportunities = structuredClone(examples);
  drafts.clear();
  $("#search").value = "";
  $("#signal").value = "all";
  view = "list";
  render();
  $("#results-status").textContent = "Demonstração reiniciada. Os seis exemplos foram restaurados.";
});
$("#theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("#theme").setAttribute("aria-pressed", String(dark));
  $("#theme").textContent = dark ? "Tema claro" : "Tema escuro";
});
render();
