/* APP */

/* ==================================================
UTILITÁRIOS DO APP — JAVASCRIPT
================================================== */
const $ = (id) => document.getElementById(id);
const formatCurrency = (amount) =>
  new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(amount);
const capitalizeText = (text) => (text ? text[0].toUpperCase() + text.slice(1) : text);
const wait = (milliseconds) => new Promise((r) => setTimeout(r, milliseconds));
const formatDate = (dateValue) =>
  new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(dateValue + "T12:00:00"));
const todayISO = () =>
  new Date().toLocaleDateString("en-CA", {
    timeZone: "America/Fortaleza",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
/* ==================================================
DADOS SIMULADOS — JAVASCRIPT
Campos em português pertencem ao contrato persistido; não os renomeie sem migração.
================================================== */
const sessionData = {
  usuario: {
    nome: "",
    primeiro: "",
    iniciais: "SM",
  },
  atividade: [
    {
      t: "sale",
      a: "Venda #1042",
      b: "Maria Helena Costa · Pix",
      v: 380,
      w: "há 12 min",
    },
    {
      t: "pay",
      a: "Pagamento recebido",
      b: "Ótica Bom Olhar · boleto compensado",
      v: 1150,
      w: "há 1 h",
    },
    {
      t: "client",
      a: "Novo cliente",
      b: "Rafael Nogueira · veio pelo WhatsApp",
      w: "há 2 h",
    },
    {
      t: "msg",
      a: "Mensagem sem resposta",
      b: "Juliana Prado · “Consegue entregar até sexta?”",
      w: "há 3 h",
    },
    {
      t: "sale",
      a: "Venda #1041",
      b: "Padaria Pão de Mel · cartão",
      v: 640,
      w: "ontem, 16:40",
    },
    {
      t: "pay",
      a: "Pagamento recebido",
      b: "Carlos Eduardo Lins · Pix",
      v: 210,
      w: "ontem, 11:05",
    },
  ],
  notificacoes: [
    {
      t: "Pagamento recebido",
      s: "R$ 1.150,00 de Ótica Bom Olhar · há 1 h",
    },
    {
      t: "Mensagem aguardando resposta",
      s: "Juliana Prado pelo WhatsApp · há 3 h",
    },
    {
      t: "Cobrança vencida",
      s: "Studio Flor de Lis · R$ 420,00",
    },
  ],
  conversas: [
    {
      id: 1,
      nome: "Maria Silva",
      iniciais: "MS",
      canal: "whatsapp",
      status: "aberto",
      telefone: "(81) 99981-2040",
      usuario: "@maria.silva",
      naoLidas: 2,
      atualizado: "agora",
      mensagens: [
        {
          de: "cliente",
          texto: "Oi, boa tarde! Vi uma camisa no Instagram.",
          hora: "13:46",
        },
      ],
    },
    {
      id: 2,
      nome: "Juliana Prado",
      iniciais: "JP",
      canal: "whatsapp",
      status: "andamento",
      telefone: "(81) 98820-1137",
      usuario: "@julianaprado",
      naoLidas: 1,
      atualizado: "há 18 min",
      mensagens: [
        {
          de: "cliente",
          texto: "Consegue entregar até sexta?",
          hora: "13:18",
        },
        {
          de: "empresa",
          texto: "Consigo sim. Vou confirmar o endereço com você.",
          hora: "13:24",
        },
        {
          de: "cliente",
          texto: "Perfeito, obrigada!",
          hora: "13:31",
        },
      ],
    },
    {
      id: 3,
      nome: "Rafael Nogueira",
      iniciais: "RN",
      canal: "instagram",
      status: "aberto",
      telefone: "—",
      usuario: "@rafa.nogueira",
      naoLidas: 3,
      atualizado: "há 42 min",
      mensagens: [
        {
          de: "cliente",
          texto: "Olá! Qual o valor desse conjunto?",
          hora: "12:57",
        },
        {
          de: "cliente",
          texto: "Vocês enviam para Belo Jardim?",
          hora: "13:02",
        },
      ],
    },
    {
      id: 4,
      nome: "Carla Menezes",
      iniciais: "CM",
      canal: "instagram",
      status: "concluido",
      telefone: "—",
      usuario: "@carlamenezes",
      naoLidas: 0,
      atualizado: "ontem",
      mensagens: [
        {
          de: "cliente",
          texto: "Recebi meu pedido, adorei!",
          hora: "17:10",
        },
        {
          de: "empresa",
          texto: "Que bom, Carla! Obrigada pela confiança 💚",
          hora: "17:14",
        },
      ],
    },
  ],
};
// Contas reais não herdam exemplos, mesmo antes da confirmação da sessão.
if (SocialMEIAuth.remote) {
  sessionData.atividade = [];
  sessionData.notificacoes = [];
  sessionData.conversas = [];
}
const DEFAULT_APP_DATA = {
  schemaVersion: SOCIALMEI_APP_SCHEMA_VERSION,
  financeiro: [
    {
      id: 1,
      descricao: "Venda #1042",
      pessoa: "Maria Helena Costa",
      tipo: "receita",
      valor: 380,
      vencimento: "2026-10-06",
      status: "pago",
    },
    {
      id: 2,
      descricao: "Ótica Bom Olhar",
      pessoa: "Boleto",
      tipo: "receita",
      valor: 1150,
      vencimento: "2026-10-06",
      status: "pago",
    },
    {
      id: 3,
      descricao: "Studio Flor de Lis",
      pessoa: "Cobrança",
      tipo: "receita",
      valor: 420,
      vencimento: "2026-09-28",
      status: "atrasado",
    },
    {
      id: 4,
      descricao: "Tecidos Aurora",
      pessoa: "Fornecedor",
      tipo: "despesa",
      valor: 960,
      vencimento: "2026-10-08",
      status: "aberto",
    },
    {
      id: 5,
      descricao: "DAS-MEI",
      pessoa: "Imposto",
      tipo: "despesa",
      valor: 82.05,
      vencimento: "2026-10-20",
      status: "aberto",
    },
    {
      id: 6,
      descricao: "Internet comercial",
      pessoa: "Operadora",
      tipo: "despesa",
      valor: 129.9,
      vencimento: "2026-10-10",
      status: "aberto",
    },
  ],
  vendas: [
    {
      id: 1042,
      item: "Conjunto Essentials",
      quantidade: 2,
      cliente: "Maria Helena Costa",
      data: "2026-10-06",
      valor: 380,
      pagamento: "Pix",
      status: "Pago",
    },
    {
      id: 1041,
      item: "Camisa Tech SocialMEI",
      quantidade: 7,
      cliente: "Padaria Pão de Mel",
      data: "2026-10-05",
      valor: 640,
      pagamento: "Cartão",
      status: "Pago",
    },
    {
      id: 1040,
      item: "Ajuste personalizado",
      quantidade: 6,
      cliente: "Juliana Prado",
      data: "2026-10-04",
      valor: 220,
      pagamento: "Pix",
      status: "Pendente",
    },
    {
      id: 1039,
      item: "Boné SocialMEI",
      quantidade: 3,
      cliente: "Rafael Nogueira",
      data: "2026-10-03",
      valor: 189.9,
      pagamento: "Boleto",
      status: "Rascunho",
    },
  ],
  clientes: [
    {
      id: 1,
      nome: "Maria Silva",
      telefone: "(81) 99981-2040",
      instagram: "@maria.silva",
      status: "Ativo",
      ultima: "Hoje",
      total: 1840,
      pendente: 0,
      observacao: "Prefere atendimento pelo WhatsApp.",
      tags: ["Cliente recorrente"],
    },
    {
      id: 2,
      nome: "Juliana Prado",
      telefone: "(81) 98820-1137",
      instagram: "@julianaprado",
      status: "Ativo",
      ultima: "Hoje",
      total: 930,
      pendente: 220,
      observacao: "Entrega preferencial na sexta-feira.",
      tags: ["Orçamento"],
    },
    {
      id: 3,
      nome: "Rafael Nogueira",
      telefone: "—",
      instagram: "@rafa.nogueira",
      status: "Novo",
      ultima: "Hoje",
      total: 189.9,
      pendente: 189.9,
      observacao: "Chegou pelo Instagram.",
      tags: ["Novo cliente"],
    },
    {
      id: 4,
      nome: "Carla Menezes",
      telefone: "—",
      instagram: "@carlamenezes",
      status: "Ativo",
      ultima: "Ontem",
      total: 720,
      pendente: 0,
      observacao: "Última compra concluída sem pendências.",
      tags: ["Pós-venda"],
    },
    {
      id: 5,
      nome: "Carlos Eduardo Lins",
      telefone: "(81) 98771-2210",
      instagram: "—",
      status: "Ativo",
      ultima: "Ontem",
      total: 1210,
      pendente: 0,
      observacao: "",
      tags: [],
    },
  ],
  produtos: [
    {
      id: 1,
      nome: "Camisa Tech SocialMEI",
      tipo: "Produto",
      preco: 89.9,
      custo: 46,
      estoque: 3,
      minimo: 5,
      status: "Ativo",
    },
    {
      id: 2,
      nome: "Conjunto Essentials",
      tipo: "Produto",
      preco: 149.9,
      custo: 82,
      estoque: 12,
      minimo: 4,
      status: "Ativo",
    },
    {
      id: 3,
      nome: "Boné SocialMEI",
      tipo: "Produto",
      preco: 54.9,
      custo: 28,
      estoque: 2,
      minimo: 3,
      status: "Ativo",
    },
    {
      id: 4,
      nome: "Ajuste personalizado",
      tipo: "Serviço",
      preco: 35,
      custo: 8,
      estoque: null,
      minimo: null,
      status: "Ativo",
    },
    {
      id: 5,
      nome: "Entrega local",
      tipo: "Serviço",
      preco: 15,
      custo: 7,
      estoque: null,
      minimo: null,
      status: "Ativo",
    },
  ],
  prefs: {
    notificacoes: true,
  },
};
let appData = loadAppData();
SocialMEIClients.attach(appData);
SocialMEIProducts.attach(appData);
SocialMEISales.attach(appData);
SocialMEIFinance.attach(appData);
appData.prefs = appData.prefs || {
  notificacoes: true,
};
const ICON_PATHS = {
  dash: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  inbox: '<path d="M4 4h16v14H4z"/><path d="M4 13h4l2 3h4l2-3h4"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  arrowLeft: '<path d="m15 18-6-6 6-6"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  bolt: '<path d="m13 2-9 12h7l-1 8 9-12h-7z"/>',
  note: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>',
  detail: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M14 4v16M17 8h1M17 12h1"/>',
  arrowDown: '<path d="m6 9 6 6 6-6"/>',
  wallet:
    '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
  users:
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  bag: '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18M16 10a4 4 0 0 1-8 0"/>',
  box: '<path d="m7.5 4.27 9 5.15M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5M12 22V12"/>',
  wa: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
  ig: '<rect x="2" y="2" width="20" height="20" rx="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37zM17.5 6.5h.01"/>',
  chart: '<path d="M3 3v18h18M18 17V9M13 17V5M8 17v-3"/>',
  cfg: '<path d="M20 7h-9M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  plus: '<path d="M5 12h14M12 5v14"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  menu: '<path d="M4 12h16M4 6h16M4 18h16"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/>',
  moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79"/>',
  refresh:
    '<path d="M20 6v6h-6"/><path d="M4 18v-6h6"/><path d="M6.5 9a7 7 0 0 1 11.6-2.6L20 8M4 16l1.9 1.6A7 7 0 0 0 17.5 15"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  panel: '<path d="M3 4h18v16H3zM9 4v16"/><path d="m14 9-3 3 3 3"/>',
  panelOpen: '<path d="M3 4h18v16H3zM9 4v16"/><path d="m12 9 3 3-3 3"/>',
  user: '<path d="M20 21a8 8 0 0 0-16 0"/><circle cx="12" cy="7" r="4"/>',
  lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4"/>',
  logout: '<path d="M10 17l5-5-5-5M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/>',
  success: '<path d="m5 12 4 4L19 6"/>',
  empty: '<path d="M3 6h18M5 6l1 14h12l1-14M9 10v6M15 10v6M8 6l1-3h6l1 3"/>',
};
const renderIcon = (name) => /* HTML */ `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">
          ${ICON_PATHS[name] || ""}
        </svg>`;
let selectedPeriod = "Este mês";
let isAllActivityVisible = false;
let customRange = null;
let loading = false;
/* ==================================================
ESTADO DA NAVEGAÇÃO — JAVASCRIPT
================================================== */
let currentView = "Início";
/* ==================================================
ESTADO DA CAIXA UNIFICADA — JAVASCRIPT
================================================== */
let activeConversationId = null;
let conversationTransitionEpoch = 0;
let isConversationSwitching = false;
let isInboxListMode = true;
let inboxQuickFilter = "all";
let isComposerNoteMode = false;
let selectedSettingsTab = "negocio";
let areMoneyValuesHidden = false;
try {
  areMoneyValuesHidden = localStorage.getItem("socialmei-hide-money") === "1";
} catch (error) {}
const money = (v) => (areMoneyValuesHidden ? "••••" : formatCurrency(v));

const N8N_MESSAGES_URL = SOCIALMEI_CONFIG.n8nMessagesUrl;
const N8N_USE_SINCE = false; // Opcional: só ative depois que o workflow aceitar ?since=<ISO timestamp>.
const N8N_POLL_DELAYS = [4000, 8000, 15000, 30000];
const REMOTE_MESSAGE_IDS = new Set();
let isN8nSyncing = false;
let n8nSyncTimer = null;
let isN8nConnected = null;
let n8nBackoffLevel = 0;
let lastRemoteMessageAt = null;
let inboxSortOrder = "priority";
let inboxSelectedTag = "all";
let areInboxDetailsCollapsed = false;
let isThreadSearchOpen = false;
let lastSyncAt = null;
let hasPendingNewMessages = false;
let isInboxFilterPopoverOpen = false;
let conversationActivitySequence = 0;
for (const [index, c] of sessionData.conversas.entries()) {
  if (!Number.isFinite(c._activityOrder)) {
    c._activityOrder = sessionData.conversas.length - index;
  }
  conversationActivitySequence = Math.max(conversationActivitySequence, c._activityOrder);
}
try {
  inboxQuickFilter = localStorage.getItem("socialmei-inbox-quick-v3") || inboxQuickFilter;
  inboxSortOrder = localStorage.getItem("socialmei-inbox-sort-v3") || "priority";
  inboxSelectedTag = localStorage.getItem("socialmei-inbox-tag-v3") || "all";
  areInboxDetailsCollapsed = localStorage.getItem("socialmei-inbox-details-v3") === "collapsed";
} catch (error) {}
const INBOX_LOCAL_KEY = "socialmei-inbox-local-v3";
let inboxLocalState = loadInboxLocal();
const APP_TIMEZONE = "America/Fortaleza";
const plural = (n, singular, pluralForm = singular + "s") =>
  `${n} ${n === 1 ? singular : pluralForm}`;
const normalizedText = (v) =>
  String(v || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
let localUpdatedAt = new Date();
let syncState = isN8nSyncConfigured() ? "idle" : "disabled";
let syncError = null;
let rowMenuAnchor = null;
$("mb").addEventListener("click", () => {
  $("sb").classList.add("open");
  $("mb").setAttribute("aria-expanded", "true");
});
$("ov").addEventListener("click", closeMobileMenu);
const escapeHtml = (text) =>
  String(text ?? "").replace(
    /[&<>'"]/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
      })[c],
  );
const statusLabel = (s) =>
  ({
    aberto: "Aberto",
    andamento: "Em andamento",
    aguardando: "Aguardando cliente",
    concluido: "Concluído",
  })[s] || s;
const channelLabel = (c) => (c === "whatsapp" ? "WhatsApp" : "Instagram");
const channelIcon = (c) => renderIcon(c === "whatsapp" ? "wa" : "ig");
document.addEventListener("click", async (event) => {
  const topButton = event.target.closest(".dd > button");
  if (topButton) {
    toggleDropdown(topButton.closest(".dd"));
    return;
  }
  const closeBtn = event.target.closest("[data-close-modal]");
  if (closeBtn) {
    closeModal(closeBtn.dataset.closeModal);
    return;
  }
  const period = event.target.closest("[data-period]");
  if (period) {
    if (period.dataset.period === "Personalizado") {
      $("customBox").classList.add("open");
      selectedPeriod = "Personalizado";
      updatePeriodLabel();
    } else {
      selectedPeriod = period.dataset.period;
      customRange = null;
      updatePeriodLabel();
      $("customBox")?.classList.remove("open");
      closeDropdowns();
      if (currentView === "Visão Geral") {
        showLoading();
        await wait(window.SocialMEIMotion.reduced ? 0 : window.SocialMEIMotion.ms("motion-medium"));
        hideLoading();
      } else {
        renderCurrentView();
      }
    }
    return;
  }
  if (event.target.closest("#cancelCustom")) {
    $("customBox").classList.remove("open");
    selectedPeriod = "Este mês";
    customRange = null;
    updatePeriodLabel();
    return;
  }
  if (event.target.closest("#applyCustom")) {
    const a = $("dateFrom").value;
    const b = $("dateTo").value;
    if (!a || !b) {
      toast("Selecione as duas datas", "Informe a data inicial e a final.");
      return;
    }
    const from = new Date(a + "T12:00:00");
    const to = new Date(b + "T12:00:00");
    if (to < from) {
      toast("Período inválido", "A data final deve ser posterior à inicial.");
      return;
    }
    const days = Math.max(1, Math.round((to - from) / 86400000) + 1);
    customRange = {
      days,
      from: a,
      to: b,
      label: `${from.toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
      })} – ${to.toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
      })}`,
    };
    selectedPeriod = "Personalizado";
    updatePeriodLabel();
    closeDropdowns();
    renderCurrentView();
    return;
  }
  if (event.target.closest("#actToggle")) {
    isAllActivityVisible = !isAllActivityVisible;
    renderActivityFeed();
    return;
  }
  if (event.target.closest("#privacyBtn")) {
    toggleMoney();
    return;
  }
  if (event.target.closest("#globalCreateBtn")) {
    openCreate("venda");
    return;
  }
  if (event.target.closest("#globalSearchBtn")) {
    openGlobalSearch();
    return;
  }
  const nav = event.target.closest("[data-nav]");
  if (nav) {
    event.preventDefault();
    setView(nav.dataset.nav);
    return;
  }
  const go = event.target.closest("[data-go]");
  if (go) {
    setView(go.dataset.go);
    closeDropdowns();
    return;
  }
  const create = event.target.closest("[data-create]");
  if (create) {
    openCreate(create.dataset.create);
    return;
  }
  if (event.target.closest("[data-new-inbox-conversation]")) {
    openNewConversation();
    return;
  }
  const conv = event.target.closest("[data-conversation]");
  if (conv) {
    selectConversation(conv.dataset.conversation);
    return;
  }
  if (
    event.target.closest("#simulateIncoming") ||
    event.target.closest("#integrationRetry") ||
    event.target.closest("#integrationPill")
  ) {
    syncN8nMessages(true);
    return;
  }
  if (event.target.closest("#mobileBack")) {
    enterInboxListMode({
      animate: true,
      focusList: true,
    });
    return;
  }
  if (event.target.closest("#mobileDetails")) {
    openMobileDetails();
    return;
  }
  if (event.target.closest("#closeMobileDetails") || event.target.closest("#detailsBackdrop")) {
    closeMobileDetails();
    return;
  }
  if (event.target.closest("#toggleDetailsBtn")) {
    toggleDetailsPanel();
    return;
  }
  if (event.target.closest("#filterBtn")) {
    toggleFilterPopover();
    return;
  }
  if (event.target.closest("#clearInboxFilters,[data-clear-inbox-filters]")) {
    isReplyPriorityOnly = false;
    if ($("channelFilter")) {
      $("channelFilter").value = "all";
    }
    if ($("statusFilter")) {
      $("statusFilter").value = "all";
    }
    if ($("tagFilter")) {
      $("tagFilter").value = "all";
    }
    if ($("sortFilter")) {
      $("sortFilter").value = "priority";
    }
    inboxSortOrder = "priority";
    inboxSelectedTag = "all";
    inboxQuickFilter = "all";
    applyInboxPreferences();
    renderConversationList();
    toggleFilterPopover(false);
    return;
  }
  if (event.target.closest("#quickRepliesBtn")) {
    toggleQuickReplies();
    return;
  }
  if (event.target.closest("#threadSearchBtn")) {
    toggleThreadSearch();
    return;
  }
  if (event.target.closest("#closeThreadSearch")) {
    toggleThreadSearch(false);
    return;
  }
  if (event.target.closest("#threadMoreBtn")) {
    const m = $("threadMoreMenu");
    if (m) {
      m.hidden = !m.hidden;
    }
    return;
  }
  if (event.target.closest("#newMessagesBtn")) {
    const h = $("messages");
    if (h) {
      h.scrollTo({
        top: h.scrollHeight,
        behavior: isReducedMotion() ? "auto" : "smooth",
      });
    }
    event.target.closest("#newMessagesBtn").hidden = true;
    hasPendingNewMessages = false;
    return;
  }
  if (event.target.closest("#clearConversationSearch")) {
    if ($("conversationSearch")) {
      $("conversationSearch").value = "";
      $("conversationSearch").focus();
    }
    renderConversationList();
    return;
  }
  const acc = event.target.closest("[data-accordion]");
  if (acc) {
    const conversation = getConversation();
    const wrap = acc.closest("[data-accordion-wrap]");
    if (wrap && conversation) {
      wrap.classList.toggle("open");
      inboxLocalState[`acc:${conversationKey(conversation)}:${acc.dataset.accordion}`] =
        wrap.classList.contains("open");
      saveInboxLocal();
    }
    return;
  }
  const threadAction = event.target.closest("[data-thread-action]");
  if (threadAction) {
    const conversation = getConversation();
    if (conversation && threadAction.dataset.threadAction === "unread") {
      conversation.naoLidas = Math.max(1, conversation.naoLidas);
      renderConversationList();
      updateInboxNavBadge();
      toast("Marcada como não lida", conversation.nome);
    }
    if (conversation && threadAction.dataset.threadAction === "conclude") {
      setConversationStatus(conversation, "concluido");
      renderThread();
      toast("Atendimento concluído", displayName(conversation));
    }
    if (conversation && threadAction.dataset.threadAction === "status") {
      openStatusModal(conversation);
    }
    if (conversation && threadAction.dataset.threadAction === "copy") {
      copyContact(conversation);
    }
    if (conversation && threadAction.dataset.threadAction === "tags") {
      openTagPicker($("threadMoreBtn"));
    }
    if (conversation && threadAction.dataset.threadAction === "search") {
      toggleThreadSearch(true);
    }
    if (conversation) {
      persistConversationState(conversation);
    }
    if ($("threadMoreMenu")) {
      $("threadMoreMenu").hidden = true;
    }
    return;
  }
  const addTag = event.target.closest("[data-add-tag]");
  if (addTag) {
    const conversation = getConversation();
    if (!conversation) {
      return;
    }
    openTagPicker(event.target.closest("[data-add-tag]"));
    return;
  }
  const removeTag = event.target.closest("[data-remove-tag]");
  if (removeTag) {
    const conversation = getConversation();
    if (conversation) {
      removeClientTag(conversation, removeTag.dataset.removeTag);
      renderDetails(conversation);
      renderConversationList();
    }
    return;
  }
  const quick = event.target.closest("[data-quick-filter]");
  if (quick) {
    isReplyPriorityOnly = false;
    inboxQuickFilter = quick.dataset.quickFilter;
    applyInboxPreferences();
    renderConversationList();
    return;
  }
  const qr = event.target.closest("[data-quick-reply]");
  if (qr) {
    const replies = {
      "Formas de pagamento": "Aceitamos Pix, cartão e dinheiro. Qual forma fica melhor para você?",
      "Prazo de entrega":
        "Consigo confirmar o prazo de entrega para você. Qual é o seu CEP ou bairro?",
      Horários:
        "Nosso atendimento funciona em horário comercial. Posso continuar seu atendimento por aqui.",
      Agradecimento: "Obrigada pelo contato! Se precisar de mais alguma coisa, estou por aqui.",
    };
    $("messageInput").value = replies[qr.dataset.quickReply] || "";
    toggleQuickReplies(false);
    updateComposerState();
    $("messageInput").focus();
    return;
  }
  if (event.target.closest("#noteModeBtn")) {
    isComposerNoteMode = !isComposerNoteMode;
    updateComposerState();
    $("messageInput").focus();
    return;
  }
  const conclude = event.target.closest("[data-mark-concluded]");
  if (conclude) {
    const conversation = getConversation(conclude.dataset.markConcluded);
    if (conversation) {
      setConversationStatus(conversation, "concluido");
      renderThread();
      toast("Atendimento concluído", conversation.nome);
    }
    return;
  }
  if (event.target.closest("[data-focus-note]")) {
    isComposerNoteMode = true;
    updateComposerState();
    $("messageInput").focus();
    return;
  }
  const paid = event.target.closest("[data-finance-paid]");
  if (paid) {
    const x = appData.financeiro.find((entry) => entry.id === Number(paid.dataset.financePaid));
    if (x) {
      if (SocialMEIFinance.remote) {
        SocialMEIFinance.transition(x, "pagar").then((saved) => {
          if (saved) {
            toast(
              saved.tipo === "receita" ? "Recebimento registrado" : "Pagamento registrado",
              saved.descricao,
            );
            if (
              $("recordModal").classList.contains("open") &&
              recordContext?.type === "finance" &&
              recordContext.id === saved.id
            )
              openRecord("finance", saved.id);
          }
        });
        return;
      }
      const previous = x.status;
      x.status = "pago";
      if (!saveAppData()) {
        x.status = previous;
        return;
      }
      renderFinance();
      renderDashboardMetrics();
      toast(x.tipo === "receita" ? "Recebimento registrado" : "Pagamento registrado", x.descricao);
    }
    return;
  }
  const salePaid = event.target.closest("[data-sale-paid]");
  if (salePaid) {
    const v = appData.vendas.find((sale) => sale.id === Number(salePaid.dataset.salePaid));
    if (v && v.status !== "Cancelado") {
      if (SocialMEISales.remote) {
        SocialMEISales.transition(v, "pagar").then((saved) => {
          if (saved) {
            renderSales();
            openRecord("sales", saved.id);
            toast("Venda marcada como paga", "Salva na API. O financeiro permanece separado.");
          }
        });
        return;
      }
      const previous = v.status;
      v.status = "Pago";
      if (!saveAppData()) {
        v.status = previous;
        return;
      }
      renderSales();
      toast("Venda marcada como paga", `#${v.id}`);
    }
    return;
  }
  const dup = event.target.closest("[data-sale-duplicate]");
  if (dup) {
    const v = appData.vendas.find((sale) => sale.id === Number(dup.dataset.saleDuplicate));
    if (v) {
      if (SocialMEISales.remote) {
        SocialMEISales.duplicate(v).then((saved) => {
          if (saved) {
            renderSales();
            openRecord("sales", saved.id);
            toast("Rascunho criado", "Estoque preservado até registrar a venda.");
          }
        });
        return;
      }
      const next = Math.max(...appData.vendas.map((sale) => sale.id)) + 1;
      appData.vendas.unshift({
        ...v,
        id: next,
        data: todayISO(),
        status: "Rascunho",
      });
      if (!saveAppData()) {
        appData.vendas.shift();
        return;
      }
      renderSales();
      toast("Venda duplicada", `Novo rascunho #${next}`);
    }
    return;
  }
  const stock = event.target.closest("[data-stock]");
  if (stock) {
    const p = appData.produtos.find((product) => product.id === Number(stock.dataset.stock));
    if (p && p.tipo === "Produto") {
      if (SocialMEIProducts.remote) {
        SocialMEIProducts.adjustStock(p, Number(stock.dataset.delta)).then((saved) => {
          if (saved) {
            renderProducts();
            renderDashboardMetrics();
            toast("Estoque atualizado", `${saved.nome}: ${saved.estoque} un.`);
          }
        });
        return;
      }
      p.estoque = Math.max(0, p.estoque + Number(stock.dataset.delta));
      saveAppData();
      renderProducts();
      renderDashboardMetrics();
      toast("Estoque atualizado", `${p.nome}: ${p.estoque} un.`);
    }
    return;
  }
  const openClientBtn = event.target.closest("[data-open-client]");
  if (openClientBtn) {
    openClient(
      appData.clientes.find((client) => client.id === Number(openClientBtn.dataset.openClient)),
    );
    return;
  }
  const openClientName = event.target.closest("[data-open-client-name]");
  if (openClientName) {
    openClient(
      appData.clientes.find(
        (client) =>
          client.nome.toLowerCase() === openClientName.dataset.openClientName.toLowerCase(),
      ),
    );
    return;
  }
  const saleClient = event.target.closest("[data-create-sale-client]");
  if (saleClient) {
    const c = appData.clientes.find(
      (client) => client.id === Number(saleClient.dataset.createSaleClient),
    );
    if (c) {
      closeModal("clientModal").then(() =>
        openCreate("venda", {
          cliente: c.nome,
        }),
      );
    }
    return;
  }
  const saleName = event.target.closest("[data-create-sale-name]");
  if (saleName) {
    openCreate("venda", {
      cliente: saleName.dataset.createSaleName,
    });
    return;
  }
  const inboxClient = event.target.closest("[data-go-inbox-client]");
  if (inboxClient) {
    const c = appData.clientes.find(
      (client) => client.id === Number(inboxClient.dataset.goInboxClient),
    );
    closeModal("clientModal");
    const conv = sessionData.conversas.find(
      (conversation) => conversation.nome.toLowerCase() === c?.nome.toLowerCase(),
    );
    setView("Caixa Unificada");
    if (conv) {
      selectConversation(conv.id);
      renderThread({
        preserveScroll: true,
      });
    }
    return;
  }
  const settingsTab = event.target.closest("[data-settings-tab]");
  if (settingsTab) {
    selectedSettingsTab = settingsTab.dataset.settingsTab;
    renderSettings();
    return;
  }
  if (event.target.closest("#settingsThemeBtn")) {
    setTheme(effectiveTheme() === "dark" ? "light" : "dark");
    renderSettings();
    return;
  }
  if (event.target.closest("#settingsPrivacy")) {
    toggleMoney();
    renderSettings();
    return;
  }
  if (event.target.closest("#settingsNotifications")) {
    appData.prefs.notificacoes = !(appData.prefs.notificacoes !== false);
    saveAppData();
    renderSettings();
    toast("Preferência atualizada");
    return;
  }
  if (event.target.closest("#exportCsv")) {
    exportReportCsv();
    return;
  }
  if (event.target.closest("#printReport")) {
    window.print();
    return;
  }
  const searchResult = event.target.closest("[data-search-view]");
  if (searchResult) {
    closeModal("searchModal");
    const view = searchResult.dataset.searchView;
    setView(view);
    if (view === "Caixa Unificada" && searchResult.dataset.searchId) {
      selectConversation(searchResult.dataset.searchId);
    }
    if (["Vendas", "Produtos e Serviços"].includes(view) && searchResult.dataset.searchId) {
      openRecord(view === "Vendas" ? "sales" : "products", Number(searchResult.dataset.searchId));
    }
    if (view === "Clientes" && searchResult.dataset.searchId) {
      openClient(
        appData.clientes.find((client) => client.id === Number(searchResult.dataset.searchId)),
      );
    }
    return;
  }
  const profile = event.target.closest("[data-profile-action]");
  if (profile) {
    if (["config", "perfil"].includes(profile.dataset.profileAction)) {
      closeDropdowns();
      if (profile.dataset.profileAction === "perfil") selectedSettingsTab = "conta";
      setView("Configurações");
      return;
    }
    toast(
      profile.dataset.profileAction === "perfil" ? "Meu perfil" : "Sessão",
      "Ação demonstrativa neste protótipo.",
    );
    closeDropdowns();
    return;
  }
  if (event.target.classList.contains("modal-backdrop")) {
    closeModal(event.target.id);
  }
  if (!event.target.closest(".filter-tools,#filterPopover")) {
    toggleFilterPopover(false);
  }
  if (!event.target.closest(".composer-popover-wrap")) {
    toggleQuickReplies(false);
  }
  if (
    !event.target.closest(".thread-actions") &&
    !event.target.closest("#threadMoreMenu") &&
    $("threadMoreMenu")
  ) {
    $("threadMoreMenu").hidden = true;
  }
  if (!event.target.closest(".dd")) {
    closeDropdowns();
  }
});
$("conversationSearch").addEventListener("input", renderConversationList);
$("channelFilter").addEventListener("change", () => {
  inboxQuickFilter = "all";
  renderConversationList();
});
$("statusFilter").addEventListener("change", () => {
  inboxQuickFilter = "all";
  renderConversationList();
});
$("tagFilter").addEventListener("change", () => {
  inboxSelectedTag = $("tagFilter").value;
  applyInboxPreferences();
  renderConversationList();
});
$("sortFilter").addEventListener("change", () => {
  inboxSortOrder = $("sortFilter").value;
  applyInboxPreferences();
  renderConversationList();
});
$("threadStatus").addEventListener("change", () => {
  const conversation = getConversation();
  if (!conversation) {
    return;
  }
  setConversationStatus(conversation, $("threadStatus").value);
  renderDetails(conversation);
  renderConversationList();
  $("threadStatus").classList.remove("status-bump");
  void $("threadStatus").offsetWidth;
  $("threadStatus").classList.add("status-bump");
  toast("Status atualizado", statusLabel(conversation.status));
});
$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const v = $("messageInput").value;
  if (!v.trim()) {
    return;
  }
  sendCurrentMessage(v);
  $("messageInput").value = "";
  saveCurrentDraft();
  updateComposerState();
});
$("messageInput").addEventListener("input", updateComposerState);
$("messageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
});
$("threadSearchInput").addEventListener("input", searchInThread);
$("messages").addEventListener("scroll", () => {
  if (isNearMessageBottom() && $("newMessagesBtn")) {
    $("newMessagesBtn").hidden = true;
    hasPendingNewMessages = false;
    const conversation = getConversation();
    if (conversation && isConversationVisible(conversation) && conversation.naoLidas) {
      conversation.naoLidas = 0;
      persistConversationState(conversation);
      renderConversationList();
      updateInboxNavBadge();
    }
  }
});
const scheduleRenderOnFrame = (callback) => {
  let frame = 0;
  return (...args) => {
    if (frame) {
      cancelAnimationFrame(frame);
    }
    frame = requestAnimationFrame(() => {
      frame = 0;
      callback(...args);
    });
  };
};
/* ==================================================
EVENTOS DOS MÓDULOS — JAVASCRIPT
================================================== */
const renderFinanceFrame = scheduleRenderOnFrame(renderFinance);
const renderSalesFrame = scheduleRenderOnFrame(renderSales);
const renderClientsFrame = scheduleRenderOnFrame(renderClients);
const renderProductsFrame = scheduleRenderOnFrame(renderProducts);
$("financeSearch").addEventListener("input", renderFinanceFrame);
$("financeTypeFilter").addEventListener("change", renderFinance);
$("financeStatusFilter").addEventListener("change", renderFinance);
$("salesSearch").addEventListener("input", renderSalesFrame);
$("salesStatusFilter").addEventListener("change", renderSales);
$("clientsSearch").addEventListener("input", renderClientsFrame);
$("clientsStatusFilter").addEventListener("change", renderClients);
$("productsSearch").addEventListener("input", renderProductsFrame);
$("productsTypeFilter").addEventListener("change", renderProducts);
$("createType").addEventListener("change", () => {
  renderCreateFields($("createType").value);
  toggleProductInventory();
});
$("createForm").addEventListener("submit", (event) => {
  event.preventDefault();
  if (activeRecordEdit) {
    saveRecordEdit(event.currentTarget);
  } else {
    handleCreate(Object.fromEntries(new FormData(event.currentTarget).entries()));
  }
});
$("globalSearchInput").addEventListener("input", (event) => renderGlobalSearch(event.target.value));
document.addEventListener("change", async (event) => {
  const note = event.target.closest("[data-client-note]");
  if (note && note.dataset.clientNote) {
    const c = appData.clientes.find((client) => client.id === Number(note.dataset.clientNote));
    if (c) {
      if (SocialMEIClients.remote) {
        const saved = await SocialMEIClients.update(c, { observacao: note.value });
        if (saved) toast("Observação salva", saved.nome);
        return;
      }
      c.observacao = note.value;
      saveAppData();
      toast("Observação salva", c.nome);
    }
  }
});
$("markRead").addEventListener("click", () => {
  sessionData.notificacoes.length = 0;
  renderNotifications();
  closeDropdowns();
  toast("Notificações marcadas como lidas");
});
$("refresh").addEventListener("click", async () => {
  if (loading) {
    return;
  }
  showLoading();
  await wait(window.SocialMEIMotion.reduced ? 0 : window.SocialMEIMotion.ms("motion-base"));
  hideLoading();
  await syncN8nMessages(true);
});
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    if (document.body.classList.contains("experience-app")) {
      setView("Início");
      $("clientCommandInput").focus();
    }
    return;
  }
  if (event.key === "Escape") {
    const topModal = [...document.querySelectorAll(".modal-backdrop.open")].at(-1);
    if (topModal) {
      event.preventDefault();
      event.stopImmediatePropagation();
      closeModal(topModal.id);
      return;
    }
    const overlay =
      document.querySelector(".modal-backdrop.open") ||
      $("detailsPane").classList.contains("mobile-open") ||
      (innerWidth <= 900 && $("sb").classList.contains("open")) ||
      isInboxFilterPopoverOpen ||
      !$("quickReplies").hidden ||
      isThreadSearchOpen ||
      !$("threadMoreMenu").hidden;
    closeDropdowns();
    closeMobileMenu();
    document.querySelectorAll(".modal-backdrop.open").forEach((m) => closeModal(m.id));
    closeMobileDetails();
    toggleFilterPopover(false);
    toggleQuickReplies(false);
    toggleThreadSearch(false);
    if ($("threadMoreMenu")) {
      $("threadMoreMenu").hidden = true;
    }
    if (
      !overlay &&
      currentView === "Caixa Unificada" &&
      (!isInboxListMode || isConversationSwitching)
    ) {
      event.preventDefault();
      enterInboxListMode({
        animate: true,
        focusList: true,
      });
    }
  }
});
const TOAST_TIMERS = new Set();
let resizeTimer;
addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    applySidebarState();
    if (currentView === "Visão Geral") {
      renderDashboardChart();
    }
    updateHeaderContext();
    positionSidebarIndicator();
    closeMobileDetails();
    syncMobileInert();
    sizeInbox();
  }, 120);
});
window.addEventListener("online", () => {
  setIntegrationStatus("Reconectando", "wait");
  resetN8nBackoff();
  syncN8nMessages(true).then(scheduleN8nSync);
});
window.addEventListener("offline", () => {
  isN8nConnected = false;
  setIntegrationStatus("Sem conexão com a internet", "offline");
  clearTimeout(n8nSyncTimer);
  n8nSyncTimer = null;
});
ICON_PATHS.star =
  '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/>';
ICON_PATHS.tag =
  '<path d="M20 13 11 22 2 13V3h10l8 8a1.4 1.4 0 0 1 0 2Z"/><circle cx="7" cy="8" r="1"/>';
ICON_PATHS.clock = '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>';
ICON_PATHS.edit = '<path d="m16 3 5 5-12 12H4v-5Z"/><path d="m14 5 5 5"/>';
ICON_PATHS.close = '<path d="m6 6 12 12M18 6 6 18"/>';
ICON_PATHS.attach = '<path d="m21 11-8 8a6 6 0 0 1-8-8l9-9a4 4 0 0 1 6 6l-9 9a2 2 0 0 1-3-3l8-8"/>';
ICON_PATHS.mention =
  '<circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/>';
ICON_PATHS.wa =
  '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/><path d="M8 7c-2 4 3 9 7 8l1-2-3-1-1 1-2-2 1-1-1-3Z"/>';
let selectedContextTab = "perfil";
let attachmentDrafts = new Map();
let conversationDrafts = new Map();
let modalConversationId = null;
let contextReturnFocusElement = null;
const foldText = (value) =>
  String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
const localDateTime = (iso) =>
  new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
document.addEventListener(
  "error",
  (event) => {
    if (event.target.matches?.(".avatar-photo")) {
      event.target.remove();
    }
  },
  {
    capture: true,
  },
);

// Editor compartilhado de rotinas locais, usando os mesmos modais da aplicação.
document.body.insertAdjacentHTML(
  "beforeend",
  /* HTML */ `<div
            class="inbox-floating"
            id="tagPicker"
            hidden
            aria-label="Seletor de etiquetas"
          ></div>
          <div class="modal-backdrop" id="inboxModal" aria-hidden="true">
            <section
              class="modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="inboxModalTitle"
            >
              <div class="modal-head">
                <h3 id="inboxModalTitle"></h3>
                <button
                  class="btn ib"
                  type="button"
                  data-close-modal="inboxModal"
                  aria-label="Fechar"
                >
                  ${renderIcon("close")}
                </button>
              </div>
              <form id="inboxModalForm">
                <div class="modal-body" id="inboxModalContent"></div>
                <div class="modal-foot">
                  <button class="btn" type="button" data-close-modal="inboxModal">Cancelar</button
                  ><button class="btn pr" id="inboxModalSubmit" type="submit">Salvar</button>
                </div>
              </form>
            </section>
          </div>`,
);
$("inboxModalForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const d = Object.fromEntries(new FormData(form));
  const mode = $("inboxModal").dataset.mode;
  const conversation = getConversation(modalConversationId);
  if (SocialMEIClients.remote && ["conversation", "profile", "observation"].includes(mode)) {
    if (mode === "conversation") {
      if (!d.nome.trim()) return;
      const next = {
        id: Math.max(0, ...sessionData.conversas.map((x) => x.id)) + 1,
        nome: d.nome.trim(),
        iniciais: initialsFromName(d.nome),
        canal: d.canal === "Instagram" ? "instagram" : "whatsapp",
        telefone: d.canal === "Instagram" ? "—" : d.contato.trim(),
        usuario: d.canal === "Instagram" ? d.contato.trim() : usernameFromName(d.nome),
        status: "aberto",
        naoLidas: 0,
        atualizado: "agora",
        mensagens: [],
        localConversation: true,
      };
      const client = await ensureContextClient(next);
      if (!client) return;
      if (d.mensagem.trim())
        next.mensagens.push({
          de: "empresa",
          texto: d.mensagem.trim(),
          hora: nowTime(),
          data: todayISO(),
          localOnly: true,
        });
      sessionData.conversas.unshift(next);
      inboxLocalState.localConversations = sessionData.conversas.filter((x) => x.localConversation);
      saveInboxLocal();
      selectConversation(next.id);
      renderConversationList();
      toast(
        "Conversa criada localmente",
        "Cliente salvo na API. Nenhuma mensagem foi enviada ao canal.",
      );
    } else if (conversation) {
      const current = clientContext(conversation).client;
      const changes =
        mode === "profile"
          ? Object.fromEntries(
              ["nome", "telefone", "instagram", "email", "cidade", "desde", "categoria"].map(
                (k) => [k, d[k]?.trim() || ""],
              ),
            )
          : { observacao: d.observacao.trim() };
      if (mode === "profile" && !changes.nome) return;
      const client = current
        ? await SocialMEIClients.update(
            { ...current, versao: $("inboxModal")._clientVersion },
            changes,
          )
        : await ensureContextClient(conversation, changes);
      if (!client) return;
      SocialMEIClients.link(conversation, client);
      renderThread({ preserveScroll: true });
      toast(
        mode === "profile" ? "Perfil atualizado" : "Observação salva",
        "Salvo na API compartilhada.",
      );
    }
    closeModal("inboxModal");
    queueInboxLayout();
    return;
  }
  if (mode === "conversation") {
    const name = d.nome.trim();
    if (!name) {
      return;
    }
    saveCurrentDraft();
    const canal = d.canal === "Instagram" ? "instagram" : "whatsapp";
    const next = {
      id: Math.max(0, ...sessionData.conversas.map((x) => x.id)) + 1,
      nome: name,
      iniciais: initialsFromName(name),
      canal,
      status: "aberto",
      telefone: canal === "whatsapp" ? d.contato.trim() : "—",
      usuario: canal === "instagram" ? d.contato.trim() : usernameFromName(name),
      naoLidas: 0,
      atualizado: "agora",
      mensagens: [],
      localConversation: true,
    };
    if (d.mensagem.trim()) {
      next.mensagens.push({
        de: "empresa",
        texto: d.mensagem.trim(),
        hora: nowTime(),
        data: todayISO(),
        localOnly: true,
      });
    }
    sessionData.conversas.unshift(next);
    touchConversationActivity(next);
    const client = await ensureContextClient(next);
    if (canal === "instagram") {
      client.instagram = d.contato.trim();
    }
    saveAppData();
    inboxLocalState.localConversations = sessionData.conversas.filter((x) => x.localConversation);
    saveInboxLocal();
    recordEvent(next, "Conversa local criada");
    $("conversationSearch").value = "";
    $("channelFilter").value = "all";
    $("statusFilter").value = "all";
    inboxSelectedTag = "all";
    $("tagFilter").value = "all";
    inboxQuickFilter = "all";
    applyInboxPreferences();
    selectConversation(next.id);
    renderConversationList();
    toast("Conversa criada localmente", "Nenhuma mensagem foi enviada ao canal.");
  } else if (conversation && mode === "profile") {
    const client = await ensureContextClient(conversation);
    const old = client.nome;
    if (!d.nome.trim()) {
      return;
    }
    client.nome = d.nome.trim();
    ["telefone", "instagram", "email", "cidade", "desde", "categoria"].forEach(
      (k) => (client[k] = d[k]?.trim() || ""),
    );
    conversation.telefone = client.telefone || "—";
    conversation.usuario = client.instagram || usernameFromName(client.nome);
    appData.vendas
      .filter((sale) => sale.cliente.toLowerCase() === old.toLowerCase())
      .forEach((sale) => (sale.cliente = client.nome));
    (SocialMEIFinance.remote ? [] : appData.financeiro)
      .filter((entry) => normalizedText(entry.pessoa || "") === normalizedText(old))
      .forEach((entry) => (entry.pessoa = client.nome));
    sessionData.conversas
      .filter((x) => x.clientId === client.id || x.nome.toLowerCase() === old.toLowerCase())
      .forEach((x) => {
        x.clientId = client.id;
        persistConversationState(x);
      });
    saveAppData();
    recordEvent(conversation, "Perfil editado localmente");
    renderThread({
      preserveScroll: true,
    });
    toast("Perfil atualizado", "Salvo neste navegador.");
  } else if (conversation && mode === "observation") {
    const client = await ensureContextClient(conversation);
    client.observacao = d.observacao.trim();
    client.observacaoAtualizada = new Date().toISOString();
    saveAppData();
    recordEvent(conversation, "Observação do cliente editada");
    renderDetails(conversation);
    toast("Nota salva", "Não enviada ao cliente.");
  } else if (conversation && mode === "status") {
    setConversationStatus(conversation, d.status);
    renderThread({
      preserveScroll: true,
    });
    toast("Status atualizado", statusLabel(conversation.status));
  }
  closeModal("inboxModal");
  queueInboxLayout();
});
$("attachmentInput").addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  removeAttachment();
  attachmentDrafts.set(activeConversationId, {
    file,
    url: /^image\/(png|jpeg|gif|webp)$/.test(file.type) ? URL.createObjectURL(file) : null,
  });
  renderAttachmentPreview();
});
document.addEventListener(
  "click",
  (event) => {
    const action = event.target.closest(
      "[data-context-tab], [data-edit-profile], [data-edit-observation], [data-open-inbox-sale], [data-pick-tag], [data-close-tag-picker], #favoriteBtn, #threadTagBtn, #composerMoreBtn, [data-composer-action], #mentionClientBtn, #attachBtn, #removeAttachment, #newConversationBtn",
    );
    if (!action) {
      return;
    }
    event.stopImmediatePropagation();
    const conversation = getConversation();
    if (action.id === "composerMoreBtn") {
      const menu = $("composerMoreMenu");
      menu.hidden = !menu.hidden;
      action.setAttribute("aria-expanded", String(!menu.hidden));
      toggleQuickReplies(false);
    } else if (action.dataset.composerAction) {
      const cmd = action.dataset.composerAction;
      if (cmd === "clear") {
        $("messageInput").value = "";
        isComposerNoteMode = false;
        removeAttachment();
        saveCurrentDraft();
        updateComposerState();
      }
      if (cmd === "mention" && conversation) {
        const input = $("messageInput");
        input.setRangeText(
          "@" + displayName(conversation).split(" ")[0] + " ",
          input.selectionStart,
          input.selectionEnd,
          "end",
        );
        updateComposerState();
        saveCurrentDraft();
        input.focus();
      }
      if (cmd === "attach") {
        $("attachmentInput").click();
      }
      if (cmd === "search") {
        toggleThreadSearch(true);
      }
      if (cmd === "client") {
        if (innerWidth <= 1370) {
          openContextDrawer();
        } else if (areInboxDetailsCollapsed) {
          toggleContextPanel();
        }
      }
      $("composerMoreMenu").hidden = true;
      $("composerMoreBtn").setAttribute("aria-expanded", "false");
    } else if (action.dataset.contextTab) {
      selectedContextTab = action.dataset.contextTab;
      renderDetails(conversation);
      $("contextTab-" + selectedContextTab).focus();
    } else if (action.hasAttribute("data-edit-profile")) {
      openProfileEditor();
    } else if (action.hasAttribute("data-edit-observation")) {
      openObservationEditor();
    } else if (action.dataset.openInboxSale) {
      closeContextDrawer();
      setView("Vendas");
      $("salesSearch").value = "#" + action.dataset.openInboxSale;
      $("salesStatusFilter").value = "all";
      renderSales();
    } else if (action.dataset.pickTag) {
      finishTag(action.dataset.pickTag);
    } else if (action.hasAttribute("data-close-tag-picker")) {
      $("tagPicker").hidden = true;
    } else if (action.id === "favoriteBtn" && conversation) {
      inboxLocalState[`favorite:${conversationKey(conversation)}`] = !isFavorite(conversation);
      saveInboxLocal();
      updateFavoriteButton(conversation);
      renderConversationList();
    } else if (action.id === "threadTagBtn") {
      openTagPicker(action);
    } else if (action.id === "mentionClientBtn" && conversation) {
      const input = $("messageInput");
      input.setRangeText(
        "@" + displayName(conversation).split(" ")[0] + " ",
        input.selectionStart,
        input.selectionEnd,
        "end",
      );
      updateComposerState();
      saveCurrentDraft();
      input.focus();
    } else if (action.id === "attachBtn") {
      $("attachmentInput").click();
    } else if (action.id === "removeAttachment") {
      removeAttachment();
    } else if (action.id === "newConversationBtn") {
      openNewConversation();
    }
  },
  true,
);
document.addEventListener("submit", (event) => {
  if (event.target.id === "tagCreateForm") {
    event.preventDefault();
    finishTag(new FormData(event.target).get("tag") || "");
  }
});
$("conversationList").setAttribute("role", "listbox");
$("conversationList").addEventListener("keydown", (event) => {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
    return;
  }
  const items = [...event.currentTarget.querySelectorAll("[data-conversation]")];
  const i = items.indexOf(document.activeElement);
  if (!items.length) {
    return;
  }
  event.preventDefault();
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? items.length - 1
        : (i + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
  items[next].focus();
  items[next].scrollIntoView({
    block: "nearest",
  });
});
$("listSort").addEventListener("change", () => {
  inboxSortOrder = $("listSort").value;
  $("sortFilter").value = inboxSortOrder;
  applyInboxPreferences();
  renderConversationList();
});
$("sortFilter").addEventListener("change", () => {
  $("listSort").value = inboxSortOrder;
});
$("messageInput").addEventListener("input", saveCurrentDraft);
$("composer").addEventListener("submit", () => {
  saveCurrentDraft();
  renderDetails(getConversation());
  queueInboxLayout();
});
document.addEventListener(
  "click",
  (event) => {
    if (!event.target.closest("#composerMoreBtn,#composerMoreMenu")) {
      if ($("composerMoreMenu")) {
        $("composerMoreMenu").hidden = true;
      }
      $("composerMoreBtn")?.setAttribute("aria-expanded", "false");
    }
    if (!event.target.closest("#tagPicker,[data-add-tag],#threadTagBtn")) {
      $("tagPicker").hidden = true;
    }
    if (event.target.closest("#mobileBack")) {
      syncMobileInert();
      queueInboxLayout();
    }
    if (
      event.target.closest(
        "[data-nav],[data-go],[data-search-view],#clearInboxFilters,[data-clear-inbox-filters]",
      )
    ) {
      requestAnimationFrame(() => {
        document.body.classList.toggle("inbox-active", currentView === "Caixa Unificada");
        $("listSort").value = inboxSortOrder;
        sizeInbox();
      });
    }
  },
  true,
);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if ($("composerMoreMenu")) {
      $("composerMoreMenu").hidden = true;
    }
    $("tagPicker").hidden = true;
    closeContextDrawer();
  }
  const tab = event.target.closest("[data-context-tab]");
  if (tab && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const tabs = ["perfil", "historico", "vendas"];
    const index = tabs.indexOf(selectedContextTab);
    selectedContextTab =
      event.key === "Home"
        ? tabs[0]
        : event.key === "End"
          ? tabs[2]
          : tabs[(index + (event.key === "ArrowRight" ? 1 : 2)) % 3];
    renderDetails(getConversation());
    $("contextTab-" + selectedContextTab).focus();
  }
});
// Mede a posição real da Caixa, incluindo a altura variável dos avisos de erro.
const inboxResizeObserver = new ResizeObserver(() => queueInboxLayout());
observeInboxLayout();
function observeInboxLayout() {
  [
    document.querySelector(".hd"),
    document.querySelector("#inboxView .list-heading"),
    $("integrationAlert"),
    $("composerZone"),
  ]
    .filter((element) => element instanceof Element)
    .forEach((element) => inboxResizeObserver.observe(element));
}
window.visualViewport?.addEventListener("resize", queueInboxLayout);
window.visualViewport?.addEventListener("scroll", queueInboxLayout);
addEventListener("resize", queueInboxLayout);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    if (currentView === "Caixa Unificada" && !isInboxListMode && getConversation()) {
      const near = isNearMessageBottom();
      renderThread({
        preserveScroll: true,
      });
      if (!near && getConversation().naoLidas) {
        hasPendingNewMessages = true;
        $("newMessagesBtn").hidden = false;
      }
    }
    sizeInbox();
  }
});
// Restaura preferências usando as chaves existentes, sem apagar dados.
for (const c of inboxLocalState.localConversations || []) {
  if (
    !sessionData.conversas.some(
      (conversation) => conversationKey(conversation) === conversationKey(c),
    )
  ) {
    c.id = Math.max(0, ...sessionData.conversas.map((conversation) => conversation.id)) + 1;
    sessionData.conversas.push(c);
  }
}
for (const c of sessionData.conversas) {
  const saved = inboxLocalState[`state:${conversationKey(c)}`];
  if (saved) {
    if (saved.status) {
      c.status = saved.status;
    }
    if (Number.isFinite(saved.naoLidas)) {
      c.naoLidas = saved.naoLidas;
    }
    c.remoteClients = saved.remoteClients || c.remoteClients;
    if (saved.clientId) {
      c.clientId = saved.clientId;
    }
  }
  const client = clientContext(c).client;
  if (client && !SocialMEIClients.remote) {
    c.clientId = client.id;
  }
  if (c.atualizado === "ontem") {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    const date =
      d.getFullYear() +
      "-" +
      String(d.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(d.getDate()).padStart(2, "0");
    c.mensagens.forEach((message) => {
      if (!message.data) {
        message.data = date;
      }
    });
  }
}
const THEMES = window.SocialMEIThemes;
let themeDraft = null;
let selectedThemePreviewTab = "dashboard";
let themeHexErrors = new Set();
const THEME_PRESETS = [
  {
    name: "SocialMEI",
    primary: "#1E73D8",
    accent: "#F2B11B",
    tip: "Azuis costumam transmitir confiança e tecnologia.",
  },
  {
    name: "Oceano",
    primary: "#145B9E",
    accent: "#20BED1",
    tip: "Use a cor de destaque com menos frequência que a principal.",
  },
  {
    name: "Esmeralda",
    primary: "#13795B",
    accent: "#E7B449",
    tip: "Cores moderadas funcionam bem em sistemas usados por muitas horas.",
  },
  {
    name: "Violeta",
    primary: "#7C3AED",
    accent: "#F28A73",
    tip: "No modo escuro, uma cor principal mais luminosa pode melhorar os detalhes.",
  },
  {
    name: "Terracota",
    primary: "#AF513C",
    accent: "#E7B449",
    tip: "Evite texto branco sobre amarelo claro. O tema escolhe um texto adequado.",
  },
  {
    name: "Grafite",
    primary: "#40556E",
    accent: "#4B9AE8",
    tip: "Superfícies neutras ajudam a manter a leitura confortável.",
  },
];
const THEME_ADVANCED = [
  ["background", "Fundo"],
  ["surface", "Superfície"],
  ["surface-secondary", "Superfície secundária"],
  ["border", "Borda"],
  ["text-primary", "Texto principal"],
  ["text-secondary", "Texto secundário"],
  ["brand-primary", "Cor principal"],
  ["brand-accent", "Destaque"],
  ["hover", "Hover"],
  ["selected", "Seleção"],
];
const THEME_STATUS = [
  ["success", "Sucesso"],
  ["warning", "Aviso"],
  ["danger", "Erro"],
  ["info", "Informação"],
];

// Prepara controles auxiliares e preserva os manipuladores dos módulos.
document.body.insertAdjacentHTML(
  "beforeend",
  /* HTML */ `<input
            type="file"
            id="themeImportInput"
            class="theme-import-input"
            accept=".json,application/json"
          />
          <div class="modal-backdrop theme-studio-modal" id="themeStudio" aria-hidden="true">
            <section
              class="modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="themeStudioTitle"
            >
              <div class="modal-head">
                <div>
                  <h3 id="themeStudioTitle">Personalizar tema</h3>
                  <p class="section-sub">Escolha suas cores. Veja o resultado antes de aplicar.</p>
                </div>
                <button
                  class="btn ib"
                  type="button"
                  data-close-modal="themeStudio"
                  aria-label="Fechar editor de tema"
                >
                  ×
                </button>
              </div>
              <div class="modal-body theme-studio-layout">
                <div class="theme-controls" id="themeStudioControls"></div>
                <div class="theme-preview-column">
                  <div
                    id="themePreviewTabs"
                    class="theme-preview-tabs"
                    role="tablist"
                    aria-label="Contexto da prévia"
                  ></div>
                  <div class="theme-preview" id="themePreview" role="tabpanel"></div>
                  <p class="theme-help" style="margin-top:8px">
                    Prévia ao vivo · estas alterações ainda não foram salvas.
                  </p>
                  <div class="theme-quality" id="themeQuality" aria-live="polite"></div>
                  <p class="theme-studio-alert" id="themeStudioAlert" role="status" hidden></p>
                  <button
                    class="btn"
                    id="themeAutoFix"
                    type="button"
                    data-theme-fix
                    style="margin-top:10px"
                    hidden
                  >
                    Corrigir automaticamente
                  </button>
                </div>
              </div>
              <div class="modal-foot theme-studio-footer">
                <button class="btn" type="button" data-close-modal="themeStudio">Cancelar</button
                ><button class="btn" type="button" data-theme-reset>Restaurar sugestões</button
                ><span class="theme-footer-spacer"></span
                ><button class="btn" id="themeSave" type="button" data-theme-save
                  >Salvar tema</button
                ><button class="btn pr" id="themeSaveApply" type="button" data-theme-save-apply>
                  Salvar e aplicar
                </button>
              </div>
            </section>
          </div>
          <div class="modal-backdrop" id="themeDeleteModal" aria-hidden="true">
            <section
              class="modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="themeDeleteTitle"
            >
              <div class="modal-head">
                <h3 id="themeDeleteTitle">Excluir tema?</h3>
                <button
                  class="btn ib"
                  type="button"
                  data-close-modal="themeDeleteModal"
                  aria-label="Fechar"
                >
                  ×
                </button>
              </div>
              <div class="modal-body"><p id="themeDeleteDescription"></p></div>
              <div class="modal-foot">
                <button class="btn" type="button" data-close-modal="themeDeleteModal"
                  >Cancelar</button
                ><button class="btn theme-danger-btn" type="button" data-theme-confirm-delete>
                  Excluir tema
                </button>
              </div>
            </section>
          </div>`,
);
$("themeImportInput").addEventListener("change", (event) =>
  importThemeFile(event.target.files?.[0]),
);
document.addEventListener(
  "click",
  (event) => {
    if (event.target.closest("#themeBtn")) {
      renderThemeMenu();
      return;
    }
    const action = event.target.closest(
      "[data-theme-apply],[data-theme-base],[data-theme-create],[data-theme-config],[data-theme-edit],[data-theme-duplicate],[data-theme-export],[data-theme-delete],[data-theme-confirm-delete],[data-theme-import],[data-theme-preset],[data-theme-preview-tab],[data-theme-fix],[data-theme-reset],[data-theme-save],[data-theme-save-apply],[data-theme-demo-toggle]",
    );
    if (!action) {
      return;
    }
    event.stopImmediatePropagation();
    if (action.hasAttribute("data-theme-apply")) {
      applyAppTheme(action.dataset.themeApply);
      closeDropdowns();
    } else if (action.hasAttribute("data-theme-config")) {
      closeDropdowns();
      selectedSettingsTab = "aparencia";
      setView("Configurações");
    } else if (action.hasAttribute("data-theme-base")) {
      openThemeStudio(THEMES.official[action.dataset.themeBase], true);
    } else if (action.hasAttribute("data-theme-create")) {
      openThemeStudio();
    } else if (action.hasAttribute("data-theme-edit")) {
      const t = THEMES.themes.find((x) => x.id === action.dataset.themeEdit);
      if (t) {
        openThemeStudio(t);
      }
    } else if (action.hasAttribute("data-theme-duplicate")) {
      const t = THEMES.themes.find((x) => x.id === action.dataset.themeDuplicate);
      if (t) {
        try {
          const copy = THEMES.save({
            ...t,
            id: undefined,
            name: t.name.slice(0, 52) + " (cópia)",
          });
          renderAppearance();
          renderThemeMenu();
          toast("Tema duplicado", copy.name);
        } catch (err) {
          toast("Não foi possível duplicar", err.message);
        }
      }
    } else if (action.hasAttribute("data-theme-export")) {
      const t = THEMES.themes.find((x) => x.id === action.dataset.themeExport);
      if (t) {
        exportTheme(t);
      }
    } else if (action.hasAttribute("data-theme-delete")) {
      const t = THEMES.themes.find((x) => x.id === action.dataset.themeDelete);
      if (t) {
        $("themeDeleteModal").dataset.themeId = t.id;
        $("themeDeleteDescription").textContent = `Excluir “${t.name}”? ${
          THEMES.active === t.id
            ? "O tema oficial " + (t.base === "dark" ? "escuro" : "claro") + " será aplicado."
            : "Você pode manter uma cópia exportando o JSON antes."
        }`;
        openModal("themeDeleteModal");
      }
    } else if (action.hasAttribute("data-theme-confirm-delete")) {
      const saved = THEMES.remove($("themeDeleteModal").dataset.themeId);
      closeModal("themeDeleteModal");
      renderAppearance();
      renderThemeMenu();
      updateThemeButton();
      requestAnimationFrame(renderDashboardChart);
      toast(
        saved ? "Tema excluído" : "Tema removido nesta sessão",
        saved ? "" : "O navegador não permitiu salvar a alteração.",
      );
    } else if (action.hasAttribute("data-theme-import")) {
      $("themeImportInput").click();
    } else if (action.hasAttribute("data-theme-preset")) {
      const p = THEME_PRESETS[Number(action.dataset.themePreset)];
      if (p && themeDraft) {
        themeDraft.primary = p.primary;
        themeDraft.accent = p.accent;
        themeDraft.overrides = {};
        themeHexErrors.clear();
        renderThemeControls();
        $("themeTip").textContent = p.tip;
        refreshThemePreview();
      }
    } else if (action.hasAttribute("data-theme-preview-tab")) {
      selectedThemePreviewTab = action.dataset.themePreviewTab;
      renderThemePreview();
      $("theme-preview-tab-" + selectedThemePreviewTab).focus();
    } else if (action.hasAttribute("data-theme-fix")) {
      themeDraft = THEMES.fix(themeDraft);
      themeHexErrors.clear();
      syncThemeColorControls();
      refreshThemePreview();
      toast(
        "Contraste ajustado",
        "Textos e superfícies foram ajustados. Sua cor principal foi preservada.",
      );
    } else if (action.hasAttribute("data-theme-reset")) {
      themeDraft.overrides = {};
      themeDraft.intensity = 35;
      themeDraft.recommendedStatus = true;
      themeHexErrors.clear();
      renderThemeControls();
      refreshThemePreview();
    } else if (action.hasAttribute("data-theme-save-apply")) {
      saveThemeDraft(true);
    } else if (action.hasAttribute("data-theme-save")) {
      saveThemeDraft(false);
    } else if (action.hasAttribute("data-theme-demo-toggle")) {
      action.setAttribute("aria-pressed", String(action.getAttribute("aria-pressed") !== "true"));
    }
  },
  true,
);
document.addEventListener("input", (event) => {
  if (!themeDraft || !event.target.closest("#themeStudioControls")) {
    return;
  }
  const element = event.target;
  if (element.id === "themeName") {
    themeDraft.name = element.value;
  } else if (element.id === "themeIntensity") {
    themeDraft.intensity = Number(element.value);
    $("themeIntensityValue").textContent = element.value + "%";
  } else if (element.hasAttribute("data-theme-color")) {
    const key = element.dataset.themeColor;
    const errorKey = (element.dataset.themeAdvanced === "true" ? "adv-" : "basic-") + key;
    if (!THEMES.HEX.test(element.value)) {
      themeHexErrors.add(errorKey);
      element.setAttribute("aria-invalid", "true");
      refreshThemePreview();
      return;
    }
    themeHexErrors.delete(errorKey);
    element.removeAttribute("aria-invalid");
    const color = element.value.toUpperCase();
    if (key === "primary" || key === "brand-primary") {
      themeDraft.primary = color;
    } else if (key === "accent" || key === "brand-accent") {
      themeDraft.accent = color;
    } else {
      themeDraft.overrides[key] = color;
    }
    const tokens = THEMES.build(themeDraft);
    document.querySelectorAll("#themeStudio [data-theme-color]").forEach((other) => {
      if (other === element) {
        return;
      }
      const k = other.dataset.themeColor;
      const otherError = (other.dataset.themeAdvanced === "true" ? "adv-" : "basic-") + k;
      if (
        k === key ||
        (k === "primary" && key === "brand-primary") ||
        (k === "brand-primary" && key === "primary") ||
        (k === "accent" && key === "brand-accent") ||
        (k === "brand-accent" && key === "accent")
      ) {
        other.value = other.dataset.themeAdvanced === "true" ? tokens[k] : themeDraft[k];
        other.removeAttribute("aria-invalid");
        themeHexErrors.delete(otherError);
      } else if (
        other.dataset.themeAdvanced === "true" &&
        !themeDraft.overrides[k] &&
        !themeHexErrors.has(otherError)
      ) {
        other.value = tokens[k];
      }
    });
  }
  refreshThemePreview();
});
document.addEventListener("change", (event) => {
  if (!themeDraft) {
    return;
  }
  if (event.target.id === "themeBase") {
    themeDraft.base = event.target.value;
    themeDraft.overrides = {};
    themeHexErrors.clear();
    renderThemeControls();
    refreshThemePreview();
  }
  if (event.target.id === "themeRecommendedStatus") {
    themeDraft.recommendedStatus = event.target.checked;
    $("themeStatusFields").hidden = event.target.checked;
    refreshThemePreview();
  }
});
document.addEventListener("keydown", (event) => {
  const tab = event.target.closest("[data-theme-preview-tab]");
  if (tab && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const ids = ["dashboard", "inbox", "components"];
    const i = ids.indexOf(selectedThemePreviewTab);
    selectedThemePreviewTab =
      event.key === "Home"
        ? ids[0]
        : event.key === "End"
          ? ids[2]
          : ids[(i + (event.key === "ArrowRight" ? 1 : 2)) % 3];
    renderThemePreview();
    $("theme-preview-tab-" + selectedThemePreviewTab).focus();
  }
  if (
    event.target.closest("#themeDd") &&
    ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)
  ) {
    event.preventDefault();
    const dd = $("themeDd");
    if (!dd.classList.contains("open")) {
      toggleDropdown(dd);
    }
    const items = [...$("themeMenu").querySelectorAll("button:not(:disabled)")];
    const i = items.indexOf(document.activeElement);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? items.length - 1
          : event.key === "ArrowDown"
            ? (i + 1) % items.length
            : i < 0
              ? items.length - 1
              : (i - 1 + items.length) % items.length;
    items[next]?.focus();
  }
});
window.addEventListener("socialmei-theme-change", () => {
  updateThemeButton();
  renderThemeMenu();
  requestAnimationFrame(renderDashboardChart);
  if (currentView === "Configurações" && selectedSettingsTab === "aparencia") {
    renderAppearance();
  }
});
renderThemeMenu();
renderInboxIcons();
document.addEventListener(
  "click",
  (event) => {
    const row = event.target.closest("[data-row-menu]");
    if (row) {
      event.stopImmediatePropagation();
      openRowMenu(row);
      return;
    }
    if (!event.target.closest("#rowMenu")) {
      closeRowMenu();
    } else {
      requestAnimationFrame(() => closeRowMenu());
    }
    const clear = event.target.closest("[data-clear-filters]");
    if (clear) {
      event.stopImmediatePropagation();
      clearModuleFilters(clear.dataset.clearFilters);
      return;
    }
    const retry = event.target.closest("[data-sync-retry]");
    if (retry) {
      event.stopImmediatePropagation();
      syncN8nMessages(true);
      return;
    }
    const report = event.target.closest("[data-report-period]");
    if (report) {
      event.stopImmediatePropagation();
      selectedPeriod = report.dataset.reportPeriod;
      customRange = null;
      updatePeriodLabel();
      renderReports();
      return;
    }
    const nav = event.target.closest("[data-nav]");
    if (nav) {
      requestAnimationFrame(() => {
        const view = document.querySelector(".page-view.active");
        const title = document.body.classList.contains("management-active")
          ? $("nvTitle")
          : view?.querySelector("h2");
        if (title) {
          title.tabIndex = -1;
          title.focus({
            preventScroll: true,
          });
        }
      });
    }
    const settings = event.target.closest("[data-settings-tab]");
    if (settings) {
      requestAnimationFrame(() => settings.focus());
    }
  },
  true,
);
document.addEventListener("change", (event) => {
  if (event.target.classList.contains("mobile-period-select")) {
    if (event.target.value === "Personalizado") {
      const range = periodRange();
      $("mobileDateFrom").value = range.from;
      $("mobileDateTo").value = range.to;
      openModal("periodModal");
      event.target.value = selectedPeriod;
    } else {
      selectedPeriod = event.target.value;
      customRange = null;
      updatePeriodLabel();
      renderCurrentView();
    }
  }
  if (event.target.id === "f_tipo") {
    toggleProductInventory();
  }
});
$("mb").addEventListener("click", () => {
  syncShellInert();
  $("sb").querySelector("a")?.focus();
});
$("sbCollapse").addEventListener("click", () => {
  if (innerWidth <= 900) {
    closeMobileMenu();
    return;
  }
  isSidebarCompact = !isSidebarCompact;
  try {
    socialmeiStorageSet(
      "socialmei-sidebar-compact-v2",
      isSidebarCompact ? "1" : "0",
      "a preferência da barra lateral",
    );
  } catch (error) {}
  applySidebarState();
});
const sidebarTooltip = document.createElement("div");
sidebarTooltip.className = "nav-tooltip";
sidebarTooltip.hidden = true;
sidebarTooltip.setAttribute("role", "tooltip");
sidebarTooltip.id = "sidebarTooltip";
document.body.appendChild(sidebarTooltip);
function showSidebarTooltip(event) {
  const item = event.target.closest("#nav [data-nav],#businessNavToggle");
  if (!item || !isSidebarCompact || innerWidth <= 900) {
    return;
  }
  const rect = item.getBoundingClientRect();
  sidebarTooltip.textContent = item.getAttribute("aria-label");
  sidebarTooltip.style.left = rect.right + 12 + "px";
  sidebarTooltip.style.top = rect.top + 4 + "px";
  sidebarTooltip.hidden = false;
  item.setAttribute("aria-describedby", "sidebarTooltip");
}
function hideSidebarTooltip() {
  sidebarTooltip.hidden = true;
  document
    .querySelectorAll('[aria-describedby="sidebarTooltip"]')
    .forEach((element) => element.removeAttribute("aria-describedby"));
}
$("nav").addEventListener("pointerover", showSidebarTooltip);
$("nav").addEventListener("focusin", showSidebarTooltip);
$("nav").addEventListener("pointerout", hideSidebarTooltip);
$("nav").addEventListener("focusout", hideSidebarTooltip);
window.addEventListener("pagehide", () => cancelAnimationFrame(sidebarFrame));
document.addEventListener(
  "keydown",
  (event) => {
    if (event.key === "Escape" && !$("rowMenu").hidden) {
      event.preventDefault();
      event.stopImmediatePropagation();
      closeRowMenu(true);
      return;
    }
    if (
      (event.ctrlKey || event.metaKey) &&
      event.key.toLowerCase() === "k" &&
      document.querySelector(".modal-backdrop.open")
    ) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if (
      event.target.closest("#rowMenu") &&
      ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)
    ) {
      event.preventDefault();
      const buttons = [...$("rowMenu").querySelectorAll("button:not(:disabled)")];
      const i = buttons.indexOf(document.activeElement);
      const n =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? buttons.length - 1
            : i < 0
              ? event.key === "ArrowDown"
                ? 0
                : buttons.length - 1
              : (i + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
      buttons[n]?.focus();
    }
    if (event.key === "Tab") {
      const modal = [...document.querySelectorAll(".modal-backdrop.open")].at(-1);
      const container =
        modal ||
        ($("detailsPane").classList.contains("mobile-open") ? $("detailsPane") : null) ||
        (innerWidth <= 900 && $("sb").classList.contains("open") ? $("sb") : null);
      if (!container) {
        return;
      }
      const controls = [
        ...container.querySelectorAll(
          'button,a[href],input:not([type=hidden]),select,textarea,[tabindex="0"]',
        ),
      ].filter(
        (element) =>
          !element.disabled &&
          !element.closest("[hidden]") &&
          element.getClientRects().length &&
          !element.closest("[inert]"),
      );
      const first = controls[0];
      const last = controls.at(-1);
      if (!first) {
        event.preventDefault();
        return;
      }
      if (
        event.shiftKey &&
        (document.activeElement === first || !container.contains(document.activeElement))
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || !container.contains(document.activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    }
    if (
      event.target.closest(".management-settings-nav") &&
      ["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
    ) {
      event.preventDefault();
      const buttons = [...document.querySelectorAll("[data-settings-tab]")];
      const i = buttons.indexOf(document.activeElement);
      const n =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? buttons.length - 1
            : (i + (["ArrowDown", "ArrowRight"].includes(event.key) ? 1 : -1) + buttons.length) %
              buttons.length;
      buttons[n]?.click();
      buttons[n]?.focus();
    }
    if (
      event.target.closest(".dd.open") &&
      ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) &&
      !event.target.closest("#themeDd")
    ) {
      event.preventDefault();
      const dd = event.target.closest(".dd");
      const buttons = [...dd.querySelectorAll(".mnu button")].filter(
        (b) => !b.disabled && b.getClientRects().length,
      );
      const i = buttons.indexOf(document.activeElement);
      const n =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? buttons.length - 1
            : (i + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
      buttons[n]?.focus();
    }
  },
  true,
);
window.addEventListener("resize", () => {
  closeRowMenu();
  syncShellInert();
});
let rowMenuScrollFrame = 0;
window.addEventListener(
  "scroll",
  () => {
    if (rowMenuScrollFrame) {
      return;
    }
    rowMenuScrollFrame = requestAnimationFrame(() => {
      rowMenuScrollFrame = 0;
      closeRowMenu();
    });
  },
  {
    capture: true,
    passive: true,
  },
);
let syncLabelsTimer = null;
function syncAppTimers() {
  clearInterval(syncLabelsTimer);
  syncLabelsTimer = null;
  if (document.hidden || !document.body.classList.contains("experience-app")) {
    clearTimeout(n8nSyncTimer);
    n8nSyncTimer = null;
    return;
  }
  syncLabelsTimer = setInterval(updateSyncLabels, 15000);
}
document.addEventListener("visibilitychange", () => {
  syncAppTimers();
  if (!document.hidden) {
    startN8nSync();
  } else {
    clearTimeout(n8nSyncTimer);
    n8nSyncTimer = null;
  }
});
window.addEventListener("pagehide", () => {
  cancelAnimationFrame(inboxLayoutFrame);
  inboxLayoutFrame = 0;
  cancelAnimationFrame(rowMenuScrollFrame);
  rowMenuScrollFrame = 0;
  clearInterval(syncLabelsTimer);
  clearTimeout(n8nSyncTimer);
  TOAST_TIMERS.forEach(clearTimeout);
  clearTimeout(resizeTimer);
  inboxResizeObserver.disconnect();
  sidebarResizeObserver.disconnect();
});
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    syncAppTimers();
    startN8nSync();
    observeInboxLayout();
    [$("nav"), $("sb")].forEach((element) => sidebarResizeObserver.observe(element));
  }
});
$("mobilePeriodForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const from = $("mobileDateFrom").value;
  const to = $("mobileDateTo").value;
  if (!from || !to || to < from) {
    $("mobilePeriodError").hidden = false;
    $("mobileDateTo").setAttribute("aria-invalid", "true");
    return;
  }
  customRange = {
    from,
    to,
    days: Math.round((new Date(to + "T12:00:00Z") - new Date(from + "T12:00:00Z")) / 86400000) + 1,
    label: formatDate(from) + " — " + formatDate(to),
  };
  selectedPeriod = "Personalizado";
  $("mobilePeriodError").hidden = true;
  $("mobileDateTo").removeAttribute("aria-invalid");
  updatePeriodLabel();
  renderCurrentView();
  closeModal("periodModal");
});
let isBusinessNavigationExpanded = true;
let drawerClientId = null;
let selectedClientTab = "resumo";
let recordContext = null;
let isCatalogLowStockOnly = false;
let isReplyPriorityOnly = false;
$("createForm").addEventListener("input", updateSaleReview);
$("createType").addEventListener("change", () => {
  $("createModalTitle").textContent = {
    venda: "Nova venda",
    cliente: "Novo cliente",
    receita: "Registrar entrada",
    despesa: "Registrar saída",
    produto: "Novo produto ou serviço",
  }[$("createType").value];
  updateSaleReview();
});
document.addEventListener(
  "click",
  (event) => {
    const record = event.target.closest("[data-record-open]");
    if (record) {
      event.stopImmediatePropagation();
      closeModal("clientModal").then(() =>
        openRecord(record.dataset.recordOpen, record.dataset.recordId),
      );
      return;
    }
    const tab = event.target.closest("[data-client-tab]");
    if (tab) {
      event.stopImmediatePropagation();
      selectedClientTab = tab.dataset.clientTab;
      renderClientPanel();
      $("clientTab-" + selectedClientTab).focus();
      return;
    }
    const conv = event.target.closest("[data-client-conversation]");
    if (conv) {
      event.stopImmediatePropagation();
      Promise.all(["clientModal", "recordModal"].map((id) => closeModal(id))).then(() => {
        setView("Caixa Unificada");
        selectConversation(conv.dataset.clientConversation);
      });
      return;
    }
    const adjust = event.target.closest("[data-adjust-stock]");
    if (adjust) {
      event.stopImmediatePropagation();
      const p = appData.produtos.find(
        (product) => product.id === Number(adjust.dataset.adjustStock),
      );
      if (p && p.tipo === "Produto") {
        if (SocialMEIProducts.remote) {
          SocialMEIProducts.adjustStock(p, Number(adjust.dataset.delta)).then((saved) => {
            if (saved) {
              renderProducts();
              openRecord("products", saved.id);
              toast("Estoque atualizado", `${saved.estoque} un. · ${saved.nome}`);
            }
          });
          return;
        }
        const delta = Number(adjust.dataset.delta);
        const previous = p.estoque;
        p.estoque = Math.max(0, p.estoque + delta);
        if (!saveAppData()) {
          p.estoque = previous;
          return;
        }
        renderProducts();
        openRecord("products", p.id);
        const buttons = $("recordBody").querySelectorAll("[data-adjust-stock]");
        [...buttons].find((b) => Number(b.dataset.delta) === delta && !b.disabled)?.focus();
        toast("Estoque atualizado", plural(p.estoque, "unidade") + " · " + p.nome);
      }
      return;
    }
    const priority = event.target.closest("[data-resolve-priority]");
    if (priority) {
      event.stopImmediatePropagation();
      const kind = priority.dataset.resolvePriority;
      if (kind === "overdue" || kind === "today") {
        clearModuleFilters("finance");
        const list = appData.financeiro;
        const dates = list.map((x) => x.vencimento).sort();
        customRange = {
          from: kind === "today" ? todayISO() : dates[0] || todayISO(),
          to: kind === "today" ? todayISO() : dates.at(-1) || todayISO(),
          label: kind === "today" ? "Vence hoje" : "Todas as datas dos registros",
        };
        selectedPeriod = "Personalizado";
        $("financeStatusFilter").value = kind === "overdue" ? "atrasado" : "aberto";
        setView("Financeiro");
        updatePeriodLabel();
        renderFinance();
      }
      if (kind === "reply") {
        isReplyPriorityOnly = true;
        inboxQuickFilter = "all";
        $("conversationSearch").value = "";
        $("channelFilter").value = "all";
        $("statusFilter").value = "all";
        $("tagFilter").value = "all";
        inboxSelectedTag = "all";
        setView("Caixa Unificada");
        renderConversationList();
      }
      if (kind === "stock") {
        isCatalogLowStockOnly = true;
        $("productsSearch").value = "";
        $("productsTypeFilter").value = "Produto";
        setView("Produtos e Serviços");
      }
      (document.body.classList.contains("management-active")
        ? $("nvTitle")
        : document.querySelector(".page-view.active h2")
      )?.focus();
      return;
    }
    if (event.target.closest("[data-finance-paid],[data-sale-paid],[data-sale-duplicate]")) {
      requestAnimationFrame(() => {
        if ($("recordModal").classList.contains("open") && recordContext) {
          openRecord(recordContext.type, recordContext.id);
        }
      });
    }
    if (!event.target.closest("#utilityTools")) {
      $("utilityTools").open = false;
    }
  },
  true,
);
document.addEventListener(
  "keydown",
  (event) => {
    const tab = event.target.closest("[data-client-tab]");
    if (tab && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const ids = ["resumo", "conversas", "compras", "financeiro", "notas"];
      const i = ids.indexOf(selectedClientTab);
      selectedClientTab =
        event.key === "Home"
          ? ids[0]
          : event.key === "End"
            ? ids.at(-1)
            : ids[(i + (event.key === "ArrowRight" ? 1 : ids.length - 1)) % ids.length];
      renderClientPanel();
      $("clientTab-" + selectedClientTab).focus();
    }
    if (event.key === "Escape" && $("utilityTools").open) {
      $("utilityTools").open = false;
      $("utilityTools").querySelector("summary").focus();
    }
  },
  true,
);

/* Telas de gestão e preferências explicitamente locais. */
const MANAGEMENT_AUXILIARY_VIEWS = ["Automações", "Assistente", "Relatórios", "Configurações"];
const readStoredJson = (key, fallback) => {
  try {
    return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
  } catch (_) {
    return fallback;
  }
};
const renderLocalDemoNotice = () =>
  '<div class="management-demo"><span class="pill draft" title="Execução automática, serviço de IA, envio oficial aos canais e autenticação externa ainda não estão conectados.">Modo demonstração</span><span>Rascunhos e preferências locais.</span></div>';
const renderManagementMetric = (label, value, note) => /* HTML */ `<article class="management-kpi">
          <span>${escapeHtml(label)}</span><b>${value}</b><small>${escapeHtml(note)}</small>
        </article>`;
const renderManagementTable = (caption, headers, rows) =>
  rows.length
    ? /* HTML */ `<div class="management-table-wrapper">
              <table class="management-table">
                <caption class="sr-only"> ${escapeHtml(caption)} </caption>
                <thead>
                  <tr>
                    ${headers.map((h) => /* HTML */ `<th scope="col">${escapeHtml(h)}</th>`).join("")}
                  </tr>
                </thead>
                <tbody>
                  ${rows
                    .map(
                      (row) => /* HTML */ `<tr>
                          ${row.map((v, i) => /* HTML */ `<td data-l="${escapeHtml(headers[i])}" ${/^Aç/.test(headers[i]) ? ' class="act"' : ""}>${v}</td>`).join("")}
                        </tr>`,
                    )
                    .join("")}
                </tbody>
              </table>
            </div>`
    : emptyMarkup(
        "Sem registros nesta seleção",
        "Escolha outro período ou cadastre seus primeiros registros.",
      );
function openManagementDrawer(title, content) {
  $("nvManagementDrawerTitle").textContent = title;
  $("nvManagementDrawerBody").innerHTML = content;
  openModal("nvManagementDrawer");
}
function getConnectionStatusText() {
  return (
    {
      loading: "Verificando leitura…",
      success: "Leitura disponível. Confira uma mensagem recebida do canal.",
      empty: "Leitura disponível, sem mensagens. Canal ainda sem evidência.",
      error: "Não foi possível ler as mensagens. Tente novamente.",
      offline: "Sem conexão. Registros locais preservados.",
      idle: "Leitura ainda não verificada.",
      disabled: "O recebimento de mensagens ainda não foi conectado.",
    }[syncState] || "Não verificado"
  );
}
function updateConnectionStatus() {
  const element = $("nvConnectionStepStatus");
  if (element) {
    element.textContent = getConnectionStatusText();
  }
  syncBusinessIdentity();
}
const baseUpdateSyncLabels = setIntegrationStatus;
setIntegrationStatus = function (...args) {
  baseUpdateSyncLabels(...args);
  updateConnectionStatus();
};
async function copyTextToClipboard(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      toast("Copiado");
      return true;
    }
  } catch (_) {}
  openManagementDrawer(
    "Copiar texto",
    /* HTML */ `<p class="management-note">
              Selecione o texto e use o comando de copiar do navegador.
            </p>
            <textarea
              class="management-input"
              id="nvCopyFallback"
              rows="12"
              readonly
              aria-label="Texto para copiar"
            >
${escapeHtml(text)}</textarea>`,
  );
  requestAnimationFrame(() => $("nvCopyFallback")?.select());
  return false;
}
function getBusinessPreferences() {
  if (SocialMEIAuth.remote && SocialMEIAuth.current) {
    return {
      ...(appData.prefs.negocio || {}),
      ...SocialMEIAuth.current.negocio.configuracao,
      nome: SocialMEIAuth.current.negocio.nome,
    };
  }
  return appData.prefs.negocio || {};
}
function getAccountPreferences() {
  if (SocialMEIAuth.remote && SocialMEIAuth.current) {
    return {
      nome: SocialMEIAuth.current.usuario.nome,
      email: SocialMEIAuth.current.usuario.email,
      telefone: SocialMEIAuth.current.usuario.telefone || "",
    };
  }
  const p = readStoredJson("socialmei-experience-profile-v1", {});
  return {
    nome: p.name || sessionData.usuario.nome,
    email: p.email || "",
    telefone: p.phone || "",
    ...(appData.prefs.conta || {}),
  };
}
function getBusinessLabel() {
  return (
    getBusinessPreferences().nome ||
    readStoredJson("socialmei-experience-profile-v1", {}).business ||
    "Meu negócio"
  );
}
const getChannelName = (c) =>
  c === "wa" || c === "whatsapp"
    ? "WhatsApp"
    : c === "ig" || c === "instagram"
      ? "Instagram"
      : "Outro";
function isChannelVerified(channel) {
  const canonical = channel === "wa" ? "whatsapp" : channel === "ig" ? "instagram" : channel;
  return (
    ["success", "empty"].includes(syncState) &&
    sessionData.conversas.some(
      (conversation) =>
        conversation.canal === canonical &&
        conversation.mensagens.some((message) => message.remoteId),
    )
  );
}
function getBusinessSetupSteps() {
  const a = getAccountPreferences();
  const p = getBusinessPreferences();
  return [
    ["Perfil", "conta", !!(a.nome?.trim() && a.email?.trim())],
    ["Logo", "negocio", !!p.logo],
    ["Horário", "negocio", !!p.horario?.trim()],
    ["Chave Pix", "negocio", !!p.pix?.trim()],
    ["Canal conectado", "integracoes", isChannelVerified("wa") || isChannelVerified("ig")],
    ["Primeira venda", "Vendas", appData.vendas.length > 0],
  ];
}
function syncBusinessIdentity() {
  const name = getBusinessLabel();
  const steps = getBusinessSetupSteps();
  const done = steps.filter((s) => s[2]).length;
  const a = getAccountPreferences();
  if ($("nvBusinessName")) {
    $("nvBusinessName").textContent = name;
  }
  if ($("nvBusinessSteps")) {
    $("nvBusinessSteps").textContent = `${done} de 6 passos`;
  }
  if ($("nvBusinessBar")) {
    $("nvBusinessBar").value = done;
    $("nvBusinessBar").setAttribute("aria-label", `Configuração: ${done} de 6 passos`);
  }
  if (MANAGEMENT_AUXILIARY_VIEWS.includes(currentView)) {
    $("gr").textContent = name;
  }
  if (appData.prefs.conta?.nome) {
    sessionData.usuario.nome = a.nome;
    sessionData.usuario.primeiro = a.nome.trim().split(/\s+/)[0];
    sessionData.usuario.iniciais = getContactInitials(a.nome);
  }
}
const baseRenderHeader = updateHeaderContext;
updateHeaderContext = function () {
  baseRenderHeader();
  syncBusinessIdentity();
};
const setViewWithManagementTabs = setView;
setView = function (name, options = {}) {
  // Aceita nomes antigos de telas persistidas e converte para as rotas atuais.
  if (name === ["Ferramentas", "de", "IA"].join(" ")) {
    name = "Assistente";
  }
  if (name === ["Pre", "ferências"].join("")) {
    name = "Configurações";
  }
  const on = MANAGEMENT_AUXILIARY_VIEWS.includes(name);
  document.body.classList.toggle("management-view-active", on);
  setViewWithManagementTabs(name, options);
  syncBusinessIdentity();
};
let selectedReportTab = "Resumo";
let isReportComparisonEnabled = true;
const getPreviousReportRange = (r) => {
  const days =
    Math.round((new Date(r.to + "T12:00:00Z") - new Date(r.from + "T12:00:00Z")) / 864e5) + 1;
  return {
    from: dateShift(r.from, -days),
    to: dateShift(r.from, -1),
  };
};
const getCustomerRegistrationDate = (c) => {
  const v = c.criadoEm || c.createdAt || c.dataCadastro;
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}/.test(v)) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  const date = new Date(v);
  return Number.isNaN(date.getTime())
    ? null
    : date.toLocaleDateString("en-CA", {
        timeZone: APP_TIMEZONE,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
};
function renderReportVariation(a, b, available = true) {
  if (!isReportComparisonEnabled) {
    return "Comparação desativada";
  }
  if (!available) {
    return "Sem data de cadastro";
  }
  if (areMoneyValuesHidden) {
    return "Comparação oculta";
  }
  if (!b) {
    return "Sem comparação ainda";
  }
  const v = ((a - b) / Math.abs(b)) * 100;
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("pt-BR", {
    maximumFractionDigits: 1,
  })}% vs. período anterior`;
}
function renderReportChart(source) {
  const series = chartSeries(periodRange(), source);
  const sales = source === "sales";
  const table = renderManagementTable(
    "Valores do gráfico",
    sales ? ["Data", "Vendas pagas"] : ["Data", "Entrou", "Saiu"],
    series.labels.map((l, i) =>
      sales
        ? [escapeHtml(l), money(series.r[i])]
        : [escapeHtml(l), money(series.r[i]), money(series.d[i])],
    ),
  );
  if (areMoneyValuesHidden) {
    return emptyMarkup("Valores ocultos", "Exiba os valores para consultar o gráfico e a tabela.");
  }
  return (
    (Math.max(0, ...series.r, ...series.d) > 0
      ? renderManagementChart(series)
      : emptyMarkup("Sem movimento neste período", "Os registros pagos formarão este gráfico.")) +
    /* HTML */ `<div class="management-chart-legend">
              <span style="--c:var(--chart-1)">${sales ? "Vendas pagas" : "Entrou"}</span
              >${sales ? "" : '<span style="--c:var(--chart-5)">Saiu</span>'}
            </div>
            <details class="management-chart-alternative">
              <summary>Ver valores em tabela</summary>
              ${table}
            </details>`
  );
}
function getReportSummaryText() {
  const metrics = operationalMetrics();
  const source =
    SocialMEISales.remote && SocialMEIFinance.remote
      ? "Vendas e financeiro: dados compartilhados."
      : SocialMEISales.remote || SocialMEIFinance.remote
        ? "Vendas e financeiro: fontes locais e compartilhadas."
        : "Vendas e financeiro: registros deste navegador.";
  return `SocialMEI.IA · ${getBusinessLabel()}\nPeríodo: ${rangeCaption()}\nVendas pagas: ${metrics.paidSales.length}\nFaturamento: ${money(metrics.revenue)}\nTicket médio: ${money(metrics.ticket)}\nEntrou: ${money(metrics.received)}\nSaiu: ${money(metrics.spent)}\nSaldo dos lançamentos pagos: ${money(metrics.balance)}\nPedidos pendentes: ${metrics.pendingSales.length}\n${source}\nSaldo não representa saldo bancário.`;
}
/* ==================================================
RELATÓRIOS — JAVASCRIPT
================================================== */
function renderReports() {
  const dateRange = periodRange();
  const metrics = operationalMetrics(dateRange);
  const prevRange = getPreviousReportRange(dateRange);
  const prev = operationalMetrics(prevRange);
  const newKnown = appData.clientes.filter((client) => getCustomerRegistrationDate(client));
  const newCount = newKnown.filter((c) =>
    inRange(getCustomerRegistrationDate(c), dateRange),
  ).length;
  const newPrev = newKnown.filter((c) => inRange(getCustomerRegistrationDate(c), prevRange)).length;
  const datesComplete = newKnown.length === appData.clientes.length && appData.clientes.length > 0;
  $("reportsPeriodLabel").textContent = rangeCaption(dateRange);
  $("nvReportPeriods").innerHTML = [
    "Hoje",
    "7 dias",
    "30 dias",
    "Este mês",
    "3 meses",
    "6 meses",
    "12 meses",
    "Personalizado",
  ]
    .map(
      (p) => /* HTML */ `<button
                class="management-chip"
                data-nv-report-period="${p}"
                aria-pressed="${selectedPeriod === p}"
              >
                ${p}
              </button>`,
    )
    .join("");
  $("nvReportCompare").checked = isReportComparisonEnabled;
  document.querySelector("#reportsView [data-nv-hide]").textContent = areMoneyValuesHidden
    ? "Exibir valores"
    : "Ocultar valores";
  document
    .querySelector("#reportsView [data-nv-hide]")
    .setAttribute("aria-pressed", String(areMoneyValuesHidden));
  $("nvReportKpis").innerHTML =
    renderManagementMetric(
      "Faturamento",
      money(metrics.revenue),
      renderReportVariation(metrics.revenue, prev.revenue),
    ) +
    renderManagementMetric(
      "Ticket médio",
      money(metrics.ticket),
      renderReportVariation(metrics.ticket, prev.ticket),
    ) +
    renderManagementMetric(
      "Vendas pagas",
      String(metrics.paidSales.length),
      renderReportVariation(metrics.paidSales.length, prev.paidSales.length),
    ) +
    renderManagementMetric(
      "Clientes novos",
      datesComplete ? String(newCount) : newKnown.length ? `${newCount}*` : "—",
      datesComplete
        ? renderReportVariation(newCount, newPrev)
        : "Cadastro sem data em parte da base",
    ) +
    renderManagementMetric(
      "Saldo do período",
      money(metrics.balance),
      renderReportVariation(metrics.balance, prev.balance),
    );
  const tabs = ["Resumo", "Vendas", "Clientes", "Atendimento", "Financeiro"];
  $("nvReportTabs").innerHTML = tabs
    .map(
      (t) => /* HTML */ `<button
                class="management-chip"
                data-nv-report-tab="${t}"
                aria-pressed="${t === selectedReportTab}"
              >
                ${t}
              </button>`,
    )
    .join("");
  const grouped = (rows, label, key = label) => {
    const o = new Map();
    rows.forEach((x) => {
      const k = key(x) || "Não informado";
      o.set(k, {
        label: label(x) || "Não informado",
        count: (o.get(k)?.count || 0) + 1,
        value: (o.get(k)?.value || 0) + (Number(x.valor) || 0),
        quantity: (o.get(k)?.quantity || 0) + (Number(x.quantidade) || 1),
      });
    });
    return [...o.values()].sort((a, b) => b.value - a.value).map((item) => [item.label, item]);
  };
  const contributors = grouped(
    metrics.paidSales,
    (x) => x.cliente,
    (x) =>
      SocialMEISales.remote && x.cliente_id != null ? `id:${x.cliente_id}` : `nome:${x.cliente}`,
  );
  const payments = grouped(metrics.paidSales, (x) => x.pagamento);
  const salesByChannel = grouped(metrics.paidSales, (v) => {
    if (v.canal) {
      return getChannelName(v.canal);
    }
    const cs = sessionData.conversas.filter((conversation) =>
      reportSaleMatchesConversation(v, conversation),
    );
    const channels = [...new Set(cs.map((c) => c.canal))];
    return channels.length === 1 ? getChannelName(channels[0]) : "Não informado";
  });
  const topProducts = grouped(
    metrics.paidSales.filter((v) => v.item),
    (v) => v.item,
    (v) =>
      SocialMEISales.remote && v.produto_id != null ? `id:${v.produto_id}` : `nome:${v.item}`,
  ).map(([name, d]) => {
    return [escapeHtml(name), String(d.quantity), String(d.count), money(d.value)];
  });
  const views = {};
  const pending = metrics.pendingSales;
  const contributorsTable = renderManagementTable(
    "Clientes com vendas pagas",
    ["Cliente", "Pedidos", "Total"],
    contributors.map(([n, d]) => [escapeHtml(n), String(d.count), money(d.value)]),
  );
  const narrative = /* HTML */ `<div class="management-report-chapters">
          <section class="management-card" id="resultChapter">
            <h3>Resultado</h3>
            <p>
              ${plural(metrics.paidSales.length, "venda paga", "vendas pagas")} no período, com
              ticket médio de ${money(metrics.ticket)}.
            </p>
            <div>${renderReportChart("sales")}</div>
          </section>
          <section class="management-card" id="driversChapter">
            <h3>O que puxou · Clientes</h3>
            ${contributorsTable}<button class="management-button" data-go="Clientes">
              Abrir clientes
            </button>
          </section>
          <section class="management-card" id="flowChapter">
            <h3>Movimento financeiro</h3>
            <p>
              Entrou ${money(metrics.received)}, saiu ${money(metrics.spent)}. Ficou
              ${money(metrics.balance)}.
            </p>
            <p class="management-note">
              Lançamentos pagos pelo vencimento. Não representa o saldo bancário.
            </p>
            <div>${renderReportChart("finance")}</div>
          </section>
          <section class="management-card" id="careChapter">
            <h3>Próximo cuidado</h3>
            <p>
              ${
                pending.length
                  ? `${plural(pending.length, "pedido aguarda", "pedidos aguardam")} pagamento neste período.`
                  : "Não há pedido pendente neste período. Confira os relacionamentos antes do próximo contato."
              }
            </p>
            <button class="management-button" data-go="${pending.length ? "Vendas" : "Clientes"}">
              ${pending.length ? "Conferir pedidos" : "Abrir clientes"}
            </button>
          </section>
        </div>`;
  const channelPayment = /* HTML */ `<div class="management-report-split">
          <section class="management-card">
            <h3>Por canal do relacionamento</h3>
            <p class="management-note">
              Canal informado na venda ou único canal do cliente vinculado; não comprova a origem da
              compra.
            </p>
            ${renderManagementTable(
              "Vendas pagas por canal",
              ["Canal", "Pedidos", "Total"],
              salesByChannel.map(([n, d]) => [escapeHtml(n), String(d.count), money(d.value)]),
            )}
          </section>
          <section class="management-card">
            <h3>Por pagamento</h3>
            ${renderManagementTable(
              "Vendas pagas por forma de pagamento",
              ["Forma", "Pedidos", "Total"],
              payments.map(([n, d]) => [escapeHtml(n), String(d.count), money(d.value)]),
            )}
          </section>
        </div>`;
  const productTable = /* HTML */ `<section class="management-card">
          <h3>Produtos e serviços mais vendidos</h3>
          <p class="management-note">Itens registrados em vendas pagas neste período.</p>
          ${renderManagementTable("Itens vendidos", ["Item", "Quantidade", "Pedidos", "Total"], topProducts)}${metrics.paidSales.some((v) => !v.item) ? '<p class="management-note">Há pedidos sem item informado; não entram no ranking.</p>' : ""}
        </section>`;
  views.Resumo = narrative + channelPayment + productTable;
  views.Vendas =
    /* HTML */ `<section class="management-card"><h3>Vendas pagas no período</h3>${renderManagementTable(
      "Vendas pagas",
      ["Pedido", "Cliente", "Data", "Pagamento", "Valor", "Ação"],
      metrics.paidSales.map((v) => [
        `#${v.id}`,
        escapeHtml(v.cliente),
        formatDate(v.data),
        escapeHtml(v.pagamento),
        money(v.valor),
        /* HTML */ `<button
                class="management-button sm"
                data-record-open="sales"
                data-record-id="${v.id}"
              >
                Abrir
              </button>`,
      ]),
    )}</section>` +
    channelPayment +
    productTable;
  views.Clientes = /* HTML */ `<section class="management-card">
          <h3>Clientes no resultado</h3>
          ${contributorsTable}
          <p class="management-note">
            ${
              datesComplete
                ? `${newCount} novos cadastros no período.`
                : "Os registros atuais não têm data de cadastro suficiente para calcular todos os clientes novos por período."
            }
          </p>
        </section>`;
  const conversations = sessionData.conversas.filter((conversation) =>
    conversation.mensagens.some((msg) => inRange(msg.data, dateRange)),
  );
  const linked = conversations.filter((conversation) =>
    metrics.sales.some((sale) => reportSaleMatchesConversation(sale, conversation)),
  );
  const linkedSales = metrics.sales.filter((sale) =>
    conversations.some((conversation) => reportSaleMatchesConversation(sale, conversation)),
  );
  const linkedPaid = linkedSales.filter((v) => v.status === "Pago");
  views.Atendimento = /* HTML */ `<section class="management-card">
          <h3>Conversa, pedido e pagamento</h3>
          <div class="management-report-funnel">
            <div><b>${conversations.length}</b><span>Conversas com mensagem no período</span></div>
            <div><b>${linkedSales.length}</b><span>Pedidos com cliente correspondente</span></div>
            <div><b>${linkedPaid.length}</b><span>Desses pedidos, pagos</span></div>
          </div>
          <p class="management-note">
            ${linked.length ? (SocialMEISales.remote ? "Vínculo pelo ID do cliente associado à conversa." : "Vínculo pelo perfil ou nome exato do cliente.") : "Sem pedidos vinculados às conversas do período."}
            Não há evento de conversão rastreado: estes números não formam uma taxa de conversão.
            Conversas sem mensagem datada não entram.
          </p>
          ${renderManagementTable(
            "Atendimento por canal",
            ["Canal", "Conversas", "Aguardando resposta"],
            ["whatsapp", "instagram"].map((c) => {
              const rows = conversations.filter((conversation) => conversation.canal === c);
              return [
                getChannelName(c),
                String(rows.length),
                String(
                  rows.filter(
                    (x) =>
                      ["aberto", "andamento"].includes(x.status) &&
                      [...x.mensagens].reverse().find((msg) => msg.de !== "nota")?.de === "cliente",
                  ).length,
                ),
              ];
            }),
          )}
        </section>`;
  views.Financeiro = /* HTML */ `<section class="management-card">
            <h3>Entradas e saídas pagas</h3>
            <p class="management-note">Pelo vencimento · não representa o saldo bancário.</p>
            ${renderReportChart("finance")}
          </section>
          <section class="management-card">
            <h3>Lançamentos do período</h3>
            ${renderManagementTable(
              "Lançamentos do relatório",
              ["Descrição", "Vencimento", "Situação", "Valor", "Ação"],
              metrics.ledger.map((x) => [
                escapeHtml(x.descricao),
                formatDate(x.vencimento),
                /* HTML */ `<span
                  class="pill ${ledgerStatus(x) === "atrasado" ? "red" : x.status === "pago" ? "green" : "draft"}"
                  >${financeStatusLabel(ledgerStatus(x), x.tipo)}</span
                >`,
                money(x.valor),
                /* HTML */ `<button
                  class="management-button sm"
                  data-record-open="finance"
                  data-record-id="${x.id}"
                >
                  Abrir
                </button>`,
              ]),
            )}
          </section>`;
  const insights = [];
  const late = appData.vendas.filter(
    (sale) => sale.status === "Pendente" && sale.data < dateShift(todayISO(), -5),
  );
  if (late.length) {
    insights.push([
      "Pedidos aguardando",
      `${plural(late.length, "pedido está", "pedidos estão")} pendente há mais de 5 dias.`,
      "Vendas",
      "Conferir pedidos",
    ]);
  }
  const overdue = appData.financeiro.filter((entry) => ledgerStatus(entry) === "atrasado");
  if (overdue.length) {
    insights.push([
      "Vencimentos atrasados",
      `${plural(overdue.length, "lançamento precisa", "lançamentos precisam")} de conferência.`,
      "Financeiro",
      "Abrir financeiro",
    ]);
  }
  const stale = appData.clientes.filter((client) => {
    const paid = appData.vendas
      .filter((sale) => sale.status === "Pago" && SocialMEISales.matchesClient(sale, client))
      .sort((sale, otherSale) => otherSale.data.localeCompare(sale.data));
    return paid[0] && paid[0].data < dateShift(todayISO(), -30);
  });
  if (stale.length) {
    insights.push([
      "Retomar relacionamento",
      `${plural(stale.length, "cliente não compra", "clientes não compram")} há mais de 30 dias, segundo os pedidos registrados.`,
      "Clientes",
      "Abrir clientes",
    ]);
  }
  $("reportsGrid").innerHTML =
    views[selectedReportTab] +
    /* HTML */ `<section class="management-stack">
            <h3>Insights</h3>
            <div class="management-insights">
              ${
                insights
                  .slice(0, 3)
                  .map(
                    ([
                      t,
                      d,
                      v,
                      a,
                    ]) => /* HTML */ `<article class="management-card management-insight">
                        <h3>${t}</h3>
                        <p>${escapeHtml(d)}</p>
                        <button class="management-button" data-go="${v}">${a}</button>
                      </article>`,
                  )
                  .join("") ||
                emptyMarkup(
                  "Nenhum cuidado identificado",
                  "As regras locais não encontraram pendências nos registros atuais.",
                )
              }
            </div>
          </section>`;
  updatePeriodCaptions();
}
function renderSettingsField(label, name, value, type = "text", extra = "") {
  return /* HTML */ `<label class="management-field" for="nvPref-${name}"
          >${label}<input
            class="management-input"
            id="nvPref-${name}"
            name="${name}"
            type="${type}"
            value="${escapeHtml(value || "")}"
            ${extra}
        /></label>`;
}
function renderSettingsForm(tab, fields) {
  return /* HTML */ `<form id="nvSettingsForm" data-tab="${tab}">
          <div class="management-form-grid">${fields}</div>
          <p
            id="nvSettingsFeedback"
            class="management-settings-feedback"
            role="status"
            aria-live="polite"
          ></p>
          <button class="management-button" type="submit">Salvar alterações</button>
        </form>`;
}
/* ==================================================
CONFIGURAÇÕES — JAVASCRIPT
================================================== */
function renderSettings() {
  const p = getBusinessPreferences();
  const a = getAccountPreferences();
  const steps = getBusinessSetupSteps();
  const done = steps.filter((x) => x[2]).length;
  const host = $("settingsPanel");
  if (!host) {
    return;
  }
  document.querySelectorAll("[data-settings-tab]").forEach((b) => {
    const on = b.dataset.settingsTab === selectedSettingsTab;
    b.classList.toggle("active", on);
    b.setAttribute("aria-current", on ? "page" : "false");
  });
  $("settingsIdentity").innerHTML = /* HTML */ `${
    p.logo
      ? /* HTML */ `<img
                  class="management-logo-preview"
                  src="${escapeHtml(p.logo)}"
                  alt="Logo do negócio"
                />`
      : /* HTML */ `<span class="av">${escapeHtml(getContactInitials(a.nome))}</span>`
  }
            <div
              ><b>${escapeHtml(getBusinessLabel())}</b><small>${escapeHtml(a.nome)}</small></div
            >`;
  $("nvSetupChecklist").innerHTML = /* HTML */ `<div class="management-setup-heading">
            <div>
              <b>${done} de 6 passos</b>
              <p class="management-note">
                Seu espaço pronto para trabalhar · conexão exige leitura confirmada.
              </p>
            </div>
            <progress
              class="management-settings-progress"
              max="6"
              value="${done}"
              aria-label="${done} de 6 passos de configuração"
            ></progress>
          </div>
          <div class="management-setup-grid">
            ${steps
              .map(
                ([label, tab, yes]) => /* HTML */ `<button
                      class="management-setup-step ${yes ? "done" : ""}"
                      data-nv-setup="${tab}"
                      aria-label="${escapeHtml(label)}: ${yes ? "concluído" : "pendente"}"
                    >
                      ${renderIcon(yes ? "check" : "chevron")}<span>${label}</span>
                    </button>`,
              )
              .join("")}
          </div>`;
  const primary = $("nvSettingsPrimary");
  primary.textContent = ["conta", "negocio", "notificacoes"].includes(selectedSettingsTab)
    ? "Salvar alterações"
    : "Exportar meus dados";
  if (SocialMEIAuth.remote && SocialMEIAuth.current) {
    $("accountSettingsNotice").innerHTML =
      '<span class="account-badge account-badge-active">Conta conectada</span><span>Seu perfil está salvo no servidor. Canais e automações têm configuração própria.</span>';
  }
  if (selectedSettingsTab === "conta") {
    const remote = SocialMEIAuth.remote;
    const administrator = !!SocialMEIAuth.current?.usuario.administrador_plataforma;
    host.innerHTML = /* HTML */ `<div class="account-section-heading"><div><span class="account-eyebrow">SEU ACESSO</span><h3>Minha conta</h3><p class="management-note">${remote ? "Seu perfil e a segurança do seu acesso, em um só lugar." : "Seu perfil na demonstração local."}</p></div><button type="button" class="account-button account-button-quiet" data-account-logout>${renderIcon("logout")}<span class="account-exit-label">Sair da conta</span></button></div>
      <div class="account-overview"><span class="account-avatar">${escapeHtml(getContactInitials(a.nome))}</span><div class="account-overview-info"><b>${escapeHtml(a.nome)}</b><span>${escapeHtml(a.email || "Perfil deste navegador")}</span><small>${escapeHtml(getBusinessLabel())}</small></div><span class="account-badge">${remote ? (administrator ? "Administrador" : "Conta MEI") : "Demonstração"}</span></div>
      <section class="account-section"><div class="account-section-heading"><div><h4>Dados pessoais</h4><p class="management-note">${remote ? "O e-mail identifica sua conta. Nome e telefone podem ser atualizados." : "Esses dados ficam salvos neste navegador."}</p></div></div>
        ${renderSettingsForm(
          "conta",
          renderSettingsField(
            "Seu nome",
            "nome",
            a.nome,
            "text",
            'required maxlength="100" autocomplete="name"',
          ) +
            renderSettingsField(
              "E-mail de acesso",
              "email",
              a.email,
              "email",
              'required autocomplete="email"' + (remote ? " readonly" : ""),
            ) +
            renderSettingsField(
              "Telefone",
              "telefone",
              a.telefone,
              "tel",
              'autocomplete="tel" maxlength="40"',
            ),
        )}
      </section>
      ${
        remote
          ? `<div class="account-security-grid"><section class="account-section account-security-card"><div class="account-card-icon">${renderIcon("lock")}</div><h4>Senha e segurança</h4><p class="management-note">Ao atualizar sua senha, você precisará entrar novamente nos seus aparelhos.</p><details class="account-password-disclosure"><summary>Alterar minha senha</summary><form id="accountPasswordForm" class="account-form"><label class="management-field" for="accountCurrentPassword">Senha atual<input id="accountCurrentPassword" class="management-input" type="password" name="atual" autocomplete="current-password" maxlength="128" required></label><label class="management-field" for="accountNewPassword">Nova senha<input id="accountNewPassword" class="management-input" type="password" name="nova" autocomplete="new-password" minlength="12" maxlength="128" required aria-describedby="accountPasswordHint"></label><small id="accountPasswordHint" class="account-helper">Use de 12 a 128 caracteres.</small><label class="management-field" for="accountConfirmPassword">Repita a nova senha<input id="accountConfirmPassword" class="management-input" type="password" name="confirmacao" autocomplete="new-password" minlength="12" maxlength="128" required></label><p id="accountPasswordFeedback" class="account-feedback" role="status" aria-live="polite"></p><button class="account-button account-button-primary" type="submit">Atualizar senha</button></form></details></section>
      <section class="account-section account-security-card"><div class="account-card-icon">${renderIcon(administrator ? "users" : "user")}</div><h4>${administrator ? "Administração do projeto" : "Seu negócio, seu acesso"}</h4><p class="management-note">${administrator ? "Convide novos MEIs e gerencie os acessos em um painel exclusivo." : "Sua conta acessa apenas os dados do negócio ao qual está vinculada."}</p>${administrator ? '<a class="account-button account-button-primary" href="/frontend/admin.html">Abrir administração →</a>' : '<span class="account-badge">Negócio separado</span>'}</section></div>
      <div class="account-recovery-note"><b>Precisa recuperar seu acesso?</b><p>A recuperação por e-mail está em preparação. Por enquanto, solicite ajuda ao administrador do projeto.</p></div>`
          : ""
      }`;
  } else if (selectedSettingsTab === "negocio") {
    host.innerHTML = /* HTML */ `<h3>Negócio</h3>
            <p class="management-note">Identidade e informações que ajudam seu atendimento.</p>
            <div class="management-stack" style="margin-top:16px">
              ${renderSettingsForm(
                "negocio",
                renderSettingsField(
                  "Nome fantasia",
                  "nome",
                  p.nome || getBusinessLabel(),
                  "text",
                  'required maxlength="100"',
                ) +
                  renderSettingsField(
                    "CNPJ (opcional)",
                    "cnpj",
                    p.cnpj,
                    "text",
                    'inputmode="numeric" maxlength="18" placeholder="00.000.000/0000-00"',
                  ) +
                  /* HTML */ `<label class="management-field full" for="nvBusinessLogo"
                      >Logo (opcional · até 1 MB)<input
                        class="management-input"
                        id="nvBusinessLogo"
                        type="file"
                        accept="image/png,image/jpeg,image/webp" /><span class="management-note"
                        >Imagem local salva apenas quando você confirmar o formulário.</span
                      >${p.logo ? /* HTML */ `<img class="management-logo-preview" src="${escapeHtml(p.logo)}" alt="Logo atual do negócio" /><button class="management-button" type="button" id="nvRemoveLogo">Remover logo ao salvar</button>` : ""}<span
                        id="nvLogoStatus"
                        role="status"
                        class="management-note"
                      ></span
                    ></label>` +
                  renderSettingsField("Telefone / WhatsApp", "telefone", p.telefone, "tel") +
                  renderSettingsField(
                    "Horário de atendimento",
                    "horario",
                    p.horario,
                    "text",
                    'maxlength="150" placeholder="Ex.: segunda a sexta, 9h às 18h"',
                  ) +
                  renderSettingsField(
                    "Chave Pix (opcional)",
                    "pix",
                    p.pix,
                    "text",
                    'maxlength="150"',
                  ) +
                  /* HTML */ `<label class="management-field full" for="nvPref-ausencia"
                      >Mensagem de ausência (opcional)<textarea
                        class="management-input"
                        id="nvPref-ausencia"
                        name="ausencia"
                        maxlength="500"
                      >
                ${escapeHtml(p.ausencia || "")}</textarea
                      ><span class="management-note"
                        >Salva como referência; envio automático indisponível.</span
                      ></label
                    >`,
              )}
            </div>`;
  } else if (selectedSettingsTab === "aparencia") {
    renderAppearance();
    host.querySelectorAll(".btn").forEach((b) => b.classList.add("management-button"));
  } else if (selectedSettingsTab === "notificacoes") {
    const n = appData.prefs.notifications || {};
    host.innerHTML = /* HTML */ `<h3>Notificações</h3>
            <div class="management-settings-row">
              <div>
                <b>Avisos do sistema</b>
                <p>Interruptor mestre para os avisos locais de novas mensagens.</p>
              </div>
              <button
                class="management-switch"
                id="settingsNotifications"
                aria-label="Avisos do sistema"
                role="switch"
                aria-checked="${appData.prefs.notificacoes !== false}"
              ></button>
            </div>
            ${renderSettingsForm(
              "notificacoes",
              /* HTML */ `<div class="full">
                  ${[
                    ["message", "Nova mensagem"],
                    ["payment", "Pagamento confirmado"],
                    ["pending", "Pedido pendente"],
                    ["routine", "Rotina executada"],
                  ]
                    .map(
                      ([key, label]) => /* HTML */ `<div class="management-settings-row">
                          <div>
                            <b>${label}</b>
                            <p>
                              ${key === "message" ? "Usado nos avisos locais de mensagens recebidas." : "Preferência salva; disparo por evento ainda não conectado."}
                            </p>
                          </div>
                          <button
                            class="management-switch"
                            type="button"
                            data-nv-notification="${key}"
                            role="switch"
                            aria-checked="${n[key] !== false}"
                            aria-label="${label}"
                            ${appData.prefs.notificacoes === false ? "disabled" : ""}
                          ></button>
                        </div>`,
                    )
                    .join("")}
                </div>
                <label class="management-field" for="nvNotificationChannel"
                  >Canal<select class="management-input" id="nvNotificationChannel" name="channel">
                    <option value="app">No app</option>
                    <option value="email" disabled>E-mail · indisponível</option>
                  </select></label
                >${renderSettingsField("Horário silencioso · início", "quietFrom", n.quietFrom, "time")}${renderSettingsField("Horário silencioso · fim", "quietTo", n.quietTo, "time")}
                <p class="management-note full">
                  Horário silencioso aplicado aos avisos locais. E-mail e execução automática de
                  rotinas ainda não conectados.
                </p>`,
            )}`;
  } else if (selectedSettingsTab === "integracoes") {
    const state =
      {
        idle: "Não verificado",
        disabled: "Integração de mensagens não configurada",
        loading: "Verificando…",
        success: "Leitura disponível",
        empty: "Leitura disponível · sem mensagens",
        error: "Falha na leitura",
        offline: "Sem conexão",
      }[syncState] || "Não verificado";
    host.innerHTML = /* HTML */ `<h3>Integrações</h3>
            <p class="management-note">
              Confirme a leitura das mensagens. O envio oficial ainda não está disponível.
            </p>
            <div class="management-integration-grid">
              ${[
                ["wa", "WhatsApp"],
                ["ig", "Instagram"],
                ["wallet", "Pix"],
              ]
                .map(([c, label]) => {
                  const verified = c !== "wallet" && isChannelVerified(c);
                  return /* HTML */ `<article class="management-integration-card">
                    <h4>${renderIcon(c)} ${label}</h4>
                    <span class="pill ${verified ? "green" : "draft"}"
                      >${verified ? "Leitura confirmada" : c === "wallet" ? "Sem conciliação automática" : "Conexão a verificar"}</span
                    >
                    <p>
                      ${
                        c === "wallet"
                          ? "Uma chave salva é referência para cobranças. Nenhuma confirmação bancária automática."
                          : "Envio oficial indisponível. A leitura depende da conexão configurada."
                      }
                    </p>
                    <button class="management-button pr" data-nv-connect="${c}">
                      ${verified ? "Verificar conexão" : "Conectar"}
                    </button>
                  </article>`;
                })
                .join("")}
            </div>
            <details class="management-advanced">
              <summary>Avançado (para quem configurou a integração)</summary>
              <p>n8n · leitura de mensagens: ${escapeHtml(state)}. ${escapeHtml(syncElapsed())}</p>
              <p>Endpoint configurado: <code>${escapeHtml(N8N_MESSAGES_URL || "Não configurado")}</code></p>
              <p>
                WhatsApp e Instagram podem receber dados pelo webhook configurado. O PostgreSQL é
                acessado pela infraestrutura; sua saúde não é verificada diretamente pelo navegador.
              </p>
              <button
                class="management-button"
                data-sync-retry
                ${syncState === "loading" ? "disabled" : ""}
              >
                Verificar leitura configurada
              </button>
            </details>`;
  } else if (selectedSettingsTab === "equipe") {
    host.innerHTML = /* HTML */ `<h3>Equipe</h3>
            <p class="management-note">Somente o dono neste espaço local.</p>
            ${renderManagementTable(
              "Pessoas do espaço",
              ["Pessoa", "E-mail", "Papel"],
              [
                [
                  /* HTML */ `<div class="management-contact">
                      <span class="av">${escapeHtml(getContactInitials(a.nome))}</span
                      ><b>${escapeHtml(a.nome)}</b>
                    </div>`,
                  escapeHtml(a.email || "Não informado"),
                  "Dono",
                ],
              ],
            )}
            <div class="management-inline-actions">
              <button
                class="management-button"
                disabled
                title="Convites e contas compartilhadas ainda não conectados."
              >
                Convidar pessoa</button
              >${renderLocalDemoNotice()}
            </div>`;
  } else if (selectedSettingsTab === "plano") {
    host.innerHTML = /* HTML */ `<!-- TROCAR: plano atual, recursos, limites e condições comerciais aprovados; não há cobrança conectada. -->
            <h3>Plano e cobrança</h3>
            <div class="management-card" style="margin-top:16px">
              <span class="pill draft">Plano gratuito</span>
              <h4>Demonstração local</h4>
              <p>
                Conversas de exemplo, clientes, vendas, catálogo, financeiro e backup neste
                navegador.
              </p>
              <p class="management-note">
                Recursos e limites comerciais a confirmar. Nenhuma assinatura ou cobrança ativa.
              </p>
              <button class="management-button" data-nv-plans>Ver planos</button>
            </div>`;
  } else if (selectedSettingsTab === "seguranca") {
    host.innerHTML = /* HTML */ `<h3>Segurança e privacidade</h3>
            <div class="management-settings-row">
              <div>
                <b>Alterar senha</b>
                <p>Autenticação externa indisponível. Nenhuma senha é salva nesta demonstração.</p>
              </div>
              <button class="management-button" disabled>Alterar senha</button>
            </div>
            <div class="management-settings-row">
              <div>
                <b>Sessões e dispositivos</b>
                <p>Não há gestão de sessões externas conectada.</p>
              </div>
              <button class="management-button" disabled>Ver sessões</button>
            </div>
            ${renderLocalDemoNotice()}
            <div class="management-settings-row">
              <div>
                <b>Exportar meus dados</b>
                <p>Backup dos registros e preferências deste navegador.</p>
              </div>
              <button class="management-button" id="exportBackup">Exportar meus dados</button>
            </div>
            <div class="management-settings-row">
              <div>
                <b>Excluir minha conta e dados locais</b>
                <p>
                  A limpeza remove os dados SocialMEI deste navegador. Não apaga mensagens nos
                  canais, registros em serviços externos nem uma conta externa. A LGPD orienta o
                  tratamento de dados; solicitações externas exigem o canal do responsável.
                </p>
              </div>
              <button class="management-button management-danger" data-nv-delete-account>
                Excluir dados locais
              </button>
            </div>`;
  } else {
    host.innerHTML = /* HTML */ `<h3>Dados</h3>
            <p>${SocialMEIClients.remote ? "Clientes são compartilhados pela API. Confira a conexão de Catálogo e Vendas nas respectivas telas. Financeiro e preferências ficam neste navegador." : "Seus dados ficam salvos neste navegador."}</p>
            <p class="management-note">
              Faça um backup antes de trocar de dispositivo ou limpar o navegador. Importar
              substitui os registros locais somente após sua confirmação.
            </p>
            <div class="management-inline-actions" style="margin-top:16px">
              <button class="management-button" id="exportBackup">Exportar backup</button
              ><button class="management-button" id="importBackup">Importar backup</button
              ><button class="management-button" data-go="Relatórios">Abrir relatórios</button>
            </div>`;
  }
  pendingBusinessLogo = undefined;
  pendingNotificationPreferences = {
    ...(appData.prefs.notifications || {}),
  };
  syncBusinessIdentity();
}
let pendingBusinessLogo;
let isBusinessLogoLoading = false;
let pendingNotificationPreferences = {};
function isValidCnpj(value) {
  const digits = value.replace(/\D/g, "");
  if (!digits) {
    return true;
  }
  if (digits.length !== 14 || /^(\d)\1+$/.test(digits)) {
    return false;
  }
  const check = (n, weights) => {
    const sum = weights.reduce((t, w, i) => t + Number(n[i]) * w, 0);
    const rest = sum % 11;
    return rest < 2 ? 0 : 11 - rest;
  };
  return (
    check(digits, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) === Number(digits[12]) &&
    check(digits, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) === Number(digits[13])
  );
}
function formatCnpj(value) {
  return value
    .replace(/\D/g, "")
    .slice(0, 14)
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\/\d{4})(\d)/, "$1-$2");
}
function isQuietPeriodActive() {
  const p = appData.prefs.notifications || {};
  if (!p.quietFrom || !p.quietTo || p.quietFrom === p.quietTo) {
    return false;
  }
  const time = new Intl.DateTimeFormat("pt-BR", {
    timeZone: APP_TIMEZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date());
  return p.quietFrom < p.quietTo
    ? time >= p.quietFrom && time < p.quietTo
    : time >= p.quietFrom || time < p.quietTo;
}
document.addEventListener("submit", async (event) => {
  if (event.target.id === "accountPasswordForm") {
    event.preventDefault();
    const form = event.target;
    const button = form.querySelector("button");
    const feedback = $("accountPasswordFeedback");
    const values = Object.fromEntries(new FormData(form));
    if (values.nova !== values.confirmacao) {
      feedback.textContent = "As novas senhas precisam ser iguais.";
      $("accountConfirmPassword").focus();
      return;
    }
    button.disabled = true;
    feedback.textContent = "Atualizando sua senha…";
    let passwordChanged = false;
    try {
      await SocialMEIAuth.request("/auth/password", "POST", {
        atual: values.atual,
        nova: values.nova,
      });
      passwordChanged = true;
      form.reset();
      feedback.textContent = "Senha atualizada. Entre novamente para continuar.";
      await SocialMEIAuth.logout();
    } catch (error) {
      feedback.textContent = passwordChanged
        ? "Senha atualizada. Recarregue o site e entre com a nova senha para continuar."
        : error.message;
      toast(passwordChanged ? "Senha atualizada" : "Senha não alterada", feedback.textContent);
      button.disabled = passwordChanged;
    }
    return;
  }
  if (event.target.id !== "nvSettingsForm") {
    return;
  }
  event.preventDefault();
  const f = event.target;
  const tab = f.dataset.tab;
  const data = Object.fromEntries(new FormData(f));
  const feedback = $("nvSettingsFeedback");
  if (!f.reportValidity()) {
    return;
  }
  if (data.nome !== undefined) {
    data.nome = data.nome.trim();
    if (!data.nome) {
      feedback.textContent = "Informe um nome para salvar.";
      $("nvPref-nome").focus();
      return;
    }
  }
  if (tab === "negocio" && isBusinessLogoLoading) {
    feedback.textContent = "Aguarde a leitura da imagem antes de salvar.";
    return;
  }
  if (tab === "negocio" && !isValidCnpj(data.cnpj || "")) {
    $("nvPref-cnpj").setAttribute("aria-invalid", "true");
    feedback.textContent = "Confira o CNPJ: use 14 dígitos válidos ou deixe em branco.";
    $("nvPref-cnpj").focus();
    return;
  }
  if (tab === "notificacoes" && !!data.quietFrom !== !!data.quietTo) {
    feedback.textContent = "Informe início e fim do horário silencioso, ou deixe ambos vazios.";
    return;
  }
  const old = JSON.stringify(appData.prefs);
  let savedOnServer = false;
  if (SocialMEIAuth.remote && ["conta", "negocio"].includes(tab)) {
    const payload =
      tab === "conta"
        ? { nome: data.nome, telefone: data.telefone }
        : {
            nome_negocio: data.nome,
            configuracao_negocio: Object.fromEntries(
              Object.entries({
                ...data,
                ...(pendingBusinessLogo !== undefined ? { logo: pendingBusinessLogo } : {}),
              }).filter(([key]) => ["cnpj", "telefone", "horario", "pix", "logo"].includes(key)),
            ),
          };
    const button = f.querySelector('[type="submit"]');
    if (button) button.disabled = true;
    try {
      await SocialMEIAuth.saveProfile(payload);
      savedOnServer = true;
    } catch (error) {
      feedback.textContent = error.message;
      return;
    } finally {
      if (button) button.disabled = false;
    }
  }
  if (tab === "negocio") {
    appData.prefs.negocio = {
      ...getBusinessPreferences(),
      ...data,
      ...(pendingBusinessLogo !== undefined
        ? {
            logo: pendingBusinessLogo,
          }
        : {}),
    };
  } else if (tab === "conta") {
    appData.prefs.conta = {
      ...getAccountPreferences(),
      ...data,
    };
  } else {
    appData.prefs.notifications = {
      ...pendingNotificationPreferences,
      ...data,
    };
  }
  // Preserva chave e esquema; só confirma o salvamento após gravar as preferências.
  if (
    !socialmeiStorageSet(
      "socialmei-app-data-v2",
      JSON.stringify({
        ...SocialMEIFinance.localData(
          SocialMEISales.localData(
            SocialMEIProducts.localData(SocialMEIClients.localData(appData)),
          ),
        ),
        schemaVersion: SOCIALMEI_APP_SCHEMA_VERSION,
      }),
      "as configurações",
    )
  ) {
    appData.prefs = JSON.parse(old);
    feedback.textContent = savedOnServer
      ? "Salvo no servidor. O navegador não conseguiu guardar a cópia local; recarregue para conferir."
      : "Não foi possível salvar neste navegador. Exporte um backup e tente novamente.";
    return;
  }
  if (tab === "conta" || tab === "negocio") {
    const profile = readStoredJson("socialmei-experience-profile-v1", {});
    if (tab === "conta") {
      Object.assign(profile, {
        name: data.nome,
        email: data.email,
        phone: data.telefone,
      });
    } else {
      profile.business = data.nome;
    }
    socialmeiStorageSet(
      "socialmei-experience-profile-v1",
      JSON.stringify(profile),
      "o perfil local",
    );
  }
  syncBusinessIdentity();
  feedback.textContent = "Salvo";
  pendingBusinessLogo = undefined;
  document.dispatchEvent(
    new CustomEvent("socialmei-data-change", {
      detail: {
        settingsSaved: true,
      },
    }),
  );
  // Atualiza identidade e checklist sem substituir o formulário ou perder sua confirmação.
  const after = getBusinessSetupSteps();
  const count = after.filter((x) => x[2]).length;
  $("nvSetupChecklist").querySelector("b").textContent = `${count} de 6 passos`;
  $("nvSetupChecklist").querySelector("progress").value = count;
  after.forEach((s, i) => {
    const b = $("nvSetupChecklist").querySelectorAll("[data-nv-setup]")[i];
    b.classList.toggle("done", s[2]);
    b.setAttribute("aria-label", `${s[0]}: ${s[2] ? "concluído" : "pendente"}`);
    b.innerHTML = renderIcon(s[2] ? "check" : "chevron") + /* HTML */ `<span>${s[0]}</span>`;
  });
});
document.addEventListener("input", (event) => {
  if (event.target.id === "nvPref-cnpj") {
    event.target.value = formatCnpj(event.target.value);
    event.target.removeAttribute("aria-invalid");
  }
});
document.addEventListener("change", (event) => {
  if (event.target.id === "nvReportCompare") {
    isReportComparisonEnabled = event.target.checked;
    renderReports();
  }
  if (event.target.id === "nvBusinessLogo") {
    const file = event.target.files[0];
    if (!file) {
      return;
    }
    if (file.size > 1048576 || !["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      $("nvLogoStatus").textContent = "Use PNG, JPG ou WebP com até 1 MB.";
      event.target.value = "";
      return;
    }
    isBusinessLogoLoading = true;
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        isBusinessLogoLoading = false;
        pendingBusinessLogo = reader.result;
        $("nvLogoStatus").textContent = "Logo pronta para salvar.";
      };
      img.onerror = () => {
        isBusinessLogoLoading = false;
        $("nvLogoStatus").textContent = "Esta imagem não pôde ser lida.";
      };
      img.src = reader.result;
    };
    reader.onerror = () => {
      isBusinessLogoLoading = false;
      $("nvLogoStatus").textContent = "Não foi possível ler o arquivo.";
    };
    reader.readAsDataURL(file);
  }
});
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-nv-hide]")) {
    toggleMoney();
    return;
  }
  const period = event.target.closest("[data-nv-report-period]");
  if (period) {
    const name = period.dataset.nvReportPeriod;
    if (name === "Personalizado") {
      const dateRange = periodRange();
      $("mobileDateFrom").value = dateRange.from;
      $("mobileDateTo").value = dateRange.to;
      openModal("periodModal");
    } else {
      selectedPeriod = name;
      customRange = null;
      updatePeriodLabel();
      renderReports();
      document.querySelector(`[data-nv-report-period="${name}"]`)?.focus();
    }
    return;
  }
  const rt = event.target.closest("[data-nv-report-tab]");
  if (rt) {
    selectedReportTab = rt.dataset.nvReportTab;
    renderReports();
    document.querySelector(`[data-nv-report-tab="${selectedReportTab}"]`)?.focus();
    return;
  }
  if (event.target.closest("#nvCopyReport")) {
    copyTextToClipboard(getReportSummaryText());
    return;
  }
  const setup = event.target.closest("[data-nv-setup]");
  if (setup) {
    const tab = setup.dataset.nvSetup;
    if (tab === "Vendas") {
      setView("Vendas");
      if (!appData.vendas.length) {
        openCreate("venda");
      }
    } else {
      selectedSettingsTab = tab;
      renderSettings();
      document.querySelector(`[data-settings-tab="${tab}"]`)?.focus();
    }
    return;
  }
  if (event.target.closest("#nvSettingsPrimary")) {
    if ($("nvSettingsForm")) {
      $("nvSettingsForm").requestSubmit();
    } else {
      exportSocialMEIBackup();
    }
    return;
  }
  if (event.target.closest("#nvRemoveLogo")) {
    pendingBusinessLogo = "";
    $("nvLogoStatus").textContent = "Logo será removida ao salvar.";
    return;
  }
  const nt = event.target.closest("[data-nv-notification]");
  if (nt) {
    const key = nt.dataset.nvNotification;
    const enabled = nt.getAttribute("aria-checked") !== "true";
    pendingNotificationPreferences[key] = enabled;
    nt.setAttribute("aria-checked", enabled);
    return;
  }
  const connect = event.target.closest("[data-nv-connect]");
  if (connect) {
    const c = connect.dataset.nvConnect;
    openManagementDrawer(
      c === "wallet" ? "Usar uma chave Pix" : `Conectar ${getChannelName(c)}`,
      c === "wallet"
        ? '<ol class="management-drawer-note"><li>Cadastre sua chave em Configurações → Negócio.</li><li>Revise a cobrança com seu cliente.</li><li>Confira o recebimento no banco e marque a venda como paga.</li></ol><p class="management-note">Nenhuma consulta bancária ou conciliação automática está conectada.</p><button class="management-button" data-nv-open-business>Abrir dados do negócio</button>'
        : /* HTML */ `<ol class="management-drawer-note">
                    <li>Tenha acesso à conta do canal e ao provedor escolhido.</li>
                    <li>Peça a quem configurou a integração para ativar a leitura de mensagens.</li>
                    <li>Verifique a conexão e confirme uma mensagem recebida deste canal.</li>
                  </ol>
                  <p class="management-note">
                    A verificação consulta a leitura já configurada. Não autoriza uma conta nem
                    conecta o envio oficial.
                  </p>
                  <button class="management-button pr" data-sync-retry>Verificar conexão</button>
                  <p class="management-note" role="status" id="nvConnectionStepStatus">
                    ${escapeHtml(getConnectionStatusText())}
                  </p>`,
    );
    return;
  }
  if (event.target.closest("[data-nv-open-business]")) {
    closeModal("nvManagementDrawer");
    selectedSettingsTab = "negocio";
    setView("Configurações");
    return;
  }
  if (event.target.closest("[data-nv-plans]")) {
    openManagementDrawer(
      "Planos",
      /* HTML */ `<!-- TROCAR: catálogo de planos, recursos, limites e link oficial de contratação, quando publicados. -->
              <p>Plano gratuito · demonstração local.</p>
              <p class="management-note">
                Planos comerciais, preços e contratação ainda não foram publicados. Não há cobrança
                ativa.
              </p>
              ${renderLocalDemoNotice()}`,
    );
    return;
  }
  if (event.target.closest("[data-nv-delete-account]")) {
    openManagementDrawer(
      "Excluir dados locais · etapa 1 de 2",
      /* HTML */ `<p>
                Você vai remover os registros, rascunhos, perfil e preferências SocialMEI deste
                navegador. Faça um backup antes.
              </p>
              <p class="management-note">
                Mensagens em WhatsApp/Instagram e dados em serviços externos não serão apagados. A
                base de exemplos reaparece quando você abrir a demonstração novamente.
              </p>
              <button class="management-button" data-nv-delete-backup>Exportar backup</button
              ><button class="management-button management-danger" data-nv-delete-next>
                Continuar para confirmação
              </button>`,
    );
    return;
  }
  if (event.target.closest("[data-nv-delete-backup]")) {
    exportSocialMEIBackup();
    return;
  }
  if (event.target.closest("[data-nv-delete-next]")) {
    openManagementDrawer(
      "Excluir dados locais · etapa 2 de 2",
      /* HTML */ `<p>Esta limpeza remove os dados locais SocialMEI deste navegador.</p>
              <label class="management-field" for="nvDeleteConfirm"
                >Digite EXCLUIR para confirmar<input
                  class="management-input"
                  id="nvDeleteConfirm"
                  autocomplete="off" /></label
              ><button class="management-button management-danger" data-nv-delete-final>
                Excluir dados deste navegador
              </button>
              <p class="management-note" id="nvDeleteFeedback" role="status"></p>`,
    );
    return;
  }
  if (event.target.closest("[data-nv-delete-final]")) {
    if ($("nvDeleteConfirm").value !== "EXCLUIR") {
      $("nvDeleteFeedback").textContent = "Digite EXCLUIR para concluir a confirmação.";
      $("nvDeleteConfirm").focus();
      return;
    }
    document.dispatchEvent(new CustomEvent("socialmei-storage-reset"));
    clearTimeout(n8nSyncTimer);
    n8nSyncTimer = null;
    for (const storage of [localStorage, sessionStorage]) {
      const keys = [];
      for (let i = 0; i < storage.length; i++) {
        const key = storage.key(i);
        if (isSocialMEIStorageKey(key)) {
          keys.push(key);
        }
      }
      keys.forEach((key) => storage.removeItem(key));
    }
    location.reload();
    return;
  }
  if (event.target.closest("#nvOpenAssistant")) {
    window.SocialMEIExperience.openAssistant?.(activeConversationId);
    return;
  }
});
document.addEventListener("socialmei-data-change", updateConnectionStatus);
document.addEventListener("socialmei-view-change", syncBusinessIdentity);
renderNavigation();
const sidebarResizeObserver = new ResizeObserver(positionSidebarIndicator);
[$("nav"), $("sb")].forEach((element) => sidebarResizeObserver.observe(element));
$("nav").addEventListener("scroll", hideSidebarTooltip, {
  passive: true,
});
renderHeader();
renderInbox();
renderFinance();
renderSales();
renderClients();
renderProducts();
renderReports();
renderSettings();
setView("Início");
applySidebarState();
syncShellInert();
updateThemeButton();
showLoading();
setTimeout(() => {
  hideLoading();
}, 420);
