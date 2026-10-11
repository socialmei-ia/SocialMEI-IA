/* DATA AND BACKUP */
/* Estado de apresentação; mantém os contratos de dados e operações persistentes. */
let focusedSaleId = null;
let focusedTradeId = null;
let selectedClientSegment = "all";
document.addEventListener("change", (event) => {
  if (event.target.id === "operationSaleSelect") {
    focusedSaleId = Number(event.target.value);
    renderBusinessHub();
    $("operationSaleSelect").focus();
    SocialMEIMotion.animate(
      $("businessHubBody"),
      [
        {
          opacity: 0.6,
        },
        {
          opacity: 1,
        },
      ],
      "motion-page",
    );
  }
});
document.addEventListener("click", (event) => {
  const phase = event.target.closest("[data-trade-phase]");
  if (phase) {
    $("salesStatusFilter").value = phase.dataset.tradePhase;
    renderSales();
    document.querySelector(`[data-trade-phase="${phase.dataset.tradePhase}"]`)?.focus();
    return;
  }
  const trade = event.target.closest("[data-trade-focus]");
  if (trade) {
    focusedTradeId = Number(trade.dataset.tradeFocus);
    renderSales();
    document.querySelector(`[data-trade-focus="${focusedTradeId}"]`)?.focus();
    SocialMEIMotion.animate(
      $("salesSummary"),
      [
        {
          opacity: 0.55,
        },
        {
          opacity: 1,
        },
      ],
      "motion-page",
    );
    return;
  }
  const segment = event.target.closest("[data-client-segment]");
  if (segment) {
    selectedClientSegment = segment.dataset.clientSegment;
    renderClients();
    document
      .querySelector(`#clientsIntro [data-client-segment="${selectedClientSegment}"]`)
      ?.focus();
    return;
  }
  if (event.target.closest("[data-catalog-low]")) {
    isCatalogLowStockOnly = !isCatalogLowStockOnly;
    renderProducts();
    document.querySelector("[data-catalog-low]")?.focus();
    return;
  }
});
function cloneData(v) {
  if (typeof structuredClone === "function") {
    return structuredClone(v);
  }
  try {
    return JSON.parse(JSON.stringify(v));
  } catch (error) {
    throw new Error("Não foi possível copiar os dados locais", {
      cause: error,
    });
  }
}
function validAppDataShape(value) {
  const object = (x) => !!x && typeof x === "object" && !Array.isArray(x);
  const text = (x) => typeof x === "string";
  const number = (x) => typeof x === "number" && Number.isFinite(x) && x >= 0;
  const date = (x) =>
    text(x) &&
    /^\d{4}-\d{2}-\d{2}$/.test(x) &&
    !Number.isNaN(Date.parse(x + "T12:00:00Z")) &&
    new Date(x + "T12:00:00Z").toISOString().slice(0, 10) === x;
  if (!object(value)) {
    return false;
  }
  const checks = {
    financeiro: (r) =>
      text(r.descricao) &&
      text(r.tipo) &&
      number(r.valor) &&
      date(r.vencimento) &&
      text(r.status) &&
      (r.pessoa === undefined || text(r.pessoa)),
    vendas: (r) =>
      text(r.cliente) &&
      date(r.data) &&
      number(r.valor) &&
      text(r.status) &&
      (r.pagamento === undefined || text(r.pagamento)) &&
      (r.item === undefined || text(r.item)),
    clientes: (r) =>
      text(r.nome) &&
      (r.tags === undefined || (Array.isArray(r.tags) && r.tags.every(text))) &&
      ["telefone", "instagram", "status", "ultima", "observacao"].every(
        (k) => r[k] === undefined || text(r[k]),
      ) &&
      ["total", "pendente"].every((k) => r[k] === undefined || number(r[k])),
    produtos: (r) =>
      text(r.nome) &&
      text(r.tipo) &&
      number(r.preco) &&
      number(r.custo) &&
      ["estoque", "minimo"].every((k) => r[k] == null || number(r[k])),
  };
  for (const [key, check] of Object.entries(checks)) {
    if (!Array.isArray(value[key])) {
      return false;
    }
    const ids = new Set();
    for (const r of value[key]) {
      if (!object(r) || !Number.isSafeInteger(r.id) || r.id < 0 || ids.has(r.id) || !check(r)) {
        return false;
      }
      ids.add(r.id);
    }
  }
  if (value.prefs !== undefined && !object(value.prefs)) {
    return false;
  }
  for (const key of ["conta", "negocio", "notifications"]) {
    const p = value.prefs?.[key];
    if (
      p !== undefined &&
      (!object(p) ||
        Object.entries(p).some(([k, v]) =>
          k === "logo" && v == null ? false : typeof v !== "string" && typeof v !== "boolean",
        ))
    ) {
      return false;
    }
  }
  return true;
}
function migrateAppData(saved) {
  if (!validAppDataShape(saved)) {
    return cloneData(DEFAULT_APP_DATA);
  }
  const next = cloneData(saved);
  const fromVersion = Number.isInteger(next.schemaVersion) ? next.schemaVersion : 0;
  if (fromVersion > SOCIALMEI_APP_SCHEMA_VERSION) {
    console.warn(
      "Dados locais criados por uma versão mais nova; campos conhecidos foram preservados.",
    );
  }
  // v0 -> v1: apenas adiciona metadado de versão; não remove nem renomeia campos.
  if (fromVersion < 1) {
    next.schemaVersion = 1;
  }
  next.schemaVersion = Math.max(Number(next.schemaVersion) || 1, 1);
  next.prefs =
    next.prefs && typeof next.prefs === "object"
      ? next.prefs
      : {
          notificacoes: true,
        };
  return next;
}
function loadAppData() {
  try {
    const raw = localStorage.getItem("socialmei-app-data-v2");
    const saved = raw ? JSON.parse(raw) : null;
    const migrated = migrateAppData(saved);
    if (
      validAppDataShape(saved) &&
      (!Number.isInteger(saved.schemaVersion) || saved.schemaVersion < SOCIALMEI_APP_SCHEMA_VERSION)
    ) {
      socialmeiStorageSet(
        "socialmei-app-data-v2",
        JSON.stringify(migrated),
        "a migração dos dados do negócio",
      );
    }
    return migrated;
  } catch (error) {
    console.warn("Dados locais inválidos; usando a base de demonstração.", error);
    return cloneData(DEFAULT_APP_DATA);
  }
}
/**
 * Persiste o negócio na chave legada e notifica os módulos somente após o salvamento.
 * @returns {boolean}
 */
function saveAppData() {
  appData.schemaVersion = SOCIALMEI_APP_SCHEMA_VERSION;
  if (
    !socialmeiStorageSet(
      "socialmei-app-data-v2",
      JSON.stringify(
        SocialMEISales.localData(SocialMEIProducts.localData(SocialMEIClients.localData(appData))),
      ),
      "os dados do negócio",
    )
  ) {
    return false;
  }
  localUpdatedAt = new Date();
  document.dispatchEvent(new CustomEvent("socialmei-data-change"));
  return true;
}
const SOCIALMEI_BACKUP_SCHEMA_VERSION = 1;
let pendingBackupImport = null;
const isSocialMEIStorageKey = (key) => /^socialmei[-_]/i.test(String(key || ""));
function collectSocialMEIStorage() {
  const storage = {};
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && isSocialMEIStorageKey(key)) {
      storage[key] = localStorage.getItem(key);
    }
  }
  // Garante que o dado principal exportado já carregue metadado de esquema.
  storage["socialmei-app-data-v2"] = JSON.stringify({
    ...SocialMEISales.localData(SocialMEIProducts.localData(SocialMEIClients.localData(appData))),
    schemaVersion: SOCIALMEI_APP_SCHEMA_VERSION,
  });
  return storage;
}
function exportSocialMEIBackup() {
  const payload = {
    product: "SocialMEI.IA",
    schemaVersion: SOCIALMEI_BACKUP_SCHEMA_VERSION,
    exportedAt: new Date().toISOString(),
    storage: collectSocialMEIStorage(),
    remoteClientsSnapshot: SocialMEIClients.backup(),
    remoteProductsSnapshot: SocialMEIProducts.backup(),
    remoteSalesSnapshot: SocialMEISales.backup(),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `socialmei-backup-${todayISO()}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("Backup exportado", "Guarde o arquivo em um local seguro.");
}
/**
 * Valida o backup antes de permitir qualquer substituição de dados. Mantém os nomes de chaves e o esquema já usado pela aplicação.
 * @param {string} raw Conteúdo JSON recebido do arquivo.
 * @returns {object} Backup validado e dados normalizados.
 * @throws {Error} Quando o conteúdo não é compatível.
 */
function parseBackupForImport(raw) {
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    throw new Error("O arquivo não contém JSON válido.");
  }
  if (
    !payload ||
    !payload.storage ||
    payload.product !== "SocialMEI.IA" ||
    typeof payload.storage !== "object" ||
    Array.isArray(payload.storage)
  ) {
    throw new Error("Este arquivo não é um backup válido do SocialMEI.");
  }
  if ((Number(payload.schemaVersion) || 0) > SOCIALMEI_BACKUP_SCHEMA_VERSION) {
    throw new Error("O backup foi criado por uma versão mais nova do SocialMEI.");
  }
  const entries = {};
  let totalBytes = 0;
  let count = 0;
  for (const [key, value] of Object.entries(payload.storage)) {
    if (!isSocialMEIStorageKey(key) || typeof value !== "string") {
      continue;
    }
    count++;
    totalBytes += key.length + value.length;
    if (count > 100 || totalBytes > 5_000_000) {
      throw new Error("O backup excede o limite de segurança desta versão.");
    }
    entries[key] = value;
  }
  if (!entries["socialmei-app-data-v2"]) {
    throw new Error("O backup não contém os dados principais do negócio.");
  }
  let importedApp;
  try {
    importedApp = JSON.parse(entries["socialmei-app-data-v2"]);
  } catch (_) {
    throw new Error("Os dados principais do backup estão corrompidos.");
  }
  if (!validAppDataShape(importedApp)) {
    throw new Error("O formato dos dados do negócio é inválido.");
  }
  if ((Number(importedApp.schemaVersion) || 0) > SOCIALMEI_APP_SCHEMA_VERSION) {
    throw new Error("Os dados do negócio foram criados por uma versão mais nova.");
  }
  const migrated = migrateAppData(importedApp);
  migrated.schemaVersion = SOCIALMEI_APP_SCHEMA_VERSION;
  entries["socialmei-app-data-v2"] = JSON.stringify(migrated);
  return {
    payload,
    entries,
    app: migrated,
  };
}
function backupSummaryHTML(candidate) {
  const app = candidate.app;
  let rules = 0;
  let themes = 0;
  try {
    const parsed = JSON.parse(candidate.entries["socialmei-automation-drafts-v1"] || "[]");
    rules = Array.isArray(parsed) ? parsed.length : 0;
  } catch (_) {}
  try {
    const parsed = JSON.parse(candidate.entries["socialmei-custom-themes"] || "[]");
    themes = Array.isArray(parsed) ? parsed.length : 0;
  } catch (_) {}
  const when = new Date(candidate.payload.exportedAt);
  const date = Number.isNaN(when.getTime()) ? "data não informada" : when.toLocaleString("pt-BR");
  return /* HTML */ `<dl class="detail-fields">
          <div>
            <dt>Backup</dt>
            <dd>${escapeHtml(date)}</dd>
          </div>
          <div>
            <dt>Versão do esquema</dt>
            <dd>${SOCIALMEI_APP_SCHEMA_VERSION}</dd>
          </div>
          <div>
            <dt>Clientes</dt>
            <dd>${app.clientes.length}</dd>
          </div>
          <div>
            <dt>Vendas</dt>
            <dd>${app.vendas.length}</dd>
          </div>
          <div>
            <dt>Lançamentos</dt>
            <dd>${app.financeiro.length}</dd>
          </div>
          <div>
            <dt>Catálogo</dt>
            <dd>${app.produtos.length}</dd>
          </div>
          <div>
            <dt>Rotinas locais</dt>
            <dd>${rules}</dd>
          </div>
          <div>
            <dt>Temas personalizados</dt>
            <dd>${themes}</dd>
          </div>
        </dl>`;
}
async function chooseBackupFile(file) {
  if (SocialMEIClients.remote || SocialMEIProducts.remote || SocialMEISales.remote) {
    toast(
      "Backup local",
      "Restaure com Clientes, Catálogo e Vendas em modo local. Depois confira a prévia de importação para a API.",
    );
    return;
  }
  if (!file) {
    return;
  }
  try {
    if (file.size > 5_000_000) {
      throw new Error("O backup deve ter no máximo 5 MB.");
    }
    const candidate = parseBackupForImport(await file.text());
    pendingBackupImport = candidate;
    $("backupImportSummary").innerHTML = backupSummaryHTML(candidate);
    openModal("backupImportModal");
  } catch (error) {
    pendingBackupImport = null;
    toast("Backup inválido", error.message || "Não foi possível ler o arquivo.");
  } finally {
    $("backupImportInput").value = "";
  }
}
function confirmBackupImport() {
  const candidate = pendingBackupImport;
  if (!candidate) {
    return;
  }
  const current = {};
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && isSocialMEIStorageKey(key)) {
      current[key] = localStorage.getItem(key);
    }
  }
  try {
    Object.keys(current).forEach((key) => localStorage.removeItem(key));
    Object.entries(candidate.entries).forEach(([key, value]) => localStorage.setItem(key, value));
  } catch (error) {
    try {
      [...Array(localStorage.length)]
        .map((_, i) => localStorage.key(i))
        .filter((key) => key && isSocialMEIStorageKey(key))
        .forEach((key) => localStorage.removeItem(key));
      Object.entries(current).forEach(([key, value]) => localStorage.setItem(key, value));
    } catch (_) {}
    socialmeiNotifyStorageError("o backup importado", error);
    return;
  }
  pendingBackupImport = null;
  document.dispatchEvent(new CustomEvent("socialmei-storage-reset"));
  closeModal("backupImportModal");
  toast("Backup importado", "Os dados foram validados. O SocialMEI será recarregado.");
  setTimeout(() => location.reload(), 650);
}
document.addEventListener("click", (event) => {
  if (event.target.closest("#exportBackup")) {
    exportSocialMEIBackup();
    return;
  }
  if (event.target.closest("#importBackup")) {
    $("backupImportInput").click();
    return;
  }
  if (event.target.closest("#confirmBackupImport")) {
    confirmBackupImport();
    return;
  }
});
document
  .getElementById("backupImportInput")
  ?.addEventListener("change", (event) => chooseBackupFile(event.target.files?.[0]));
function clearModuleFilters(module) {
  if (module === "products") {
    isCatalogLowStockOnly = false;
  }
  if (module === "clients") {
    selectedClientSegment = "all";
  }
  for (const suffix of ["Search", "TypeFilter", "StatusFilter", "TagFilter"]) {
    const element = $(module + suffix);
    if (element) {
      element.value = suffix === "Search" ? "" : "all";
    }
  }
  ({
    finance: renderFinance,
    sales: renderSales,
    clients: renderClients,
    products: renderProducts,
  })[module]?.();
}
function dateShift(iso, days) {
  const d = new Date(iso + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
function monthShift(iso, months) {
  const d = new Date(iso + "T12:00:00Z");
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + months);
  return d.toISOString().slice(0, 10);
}
function periodRange(period = selectedPeriod) {
  const today = todayISO();
  let from = today;
  if (period === "Personalizado" && customRange?.from && customRange?.to) {
    return {
      from: customRange.from,
      to: customRange.to,
      label: customRange.label,
    };
  }
  if (period === "7 dias") {
    from = dateShift(today, -6);
  } else if (period === "30 dias") {
    from = dateShift(today, -29);
  } else if (["3 meses", "6 meses", "12 meses"].includes(period)) {
    from = monthShift(today, -(Number(period.split(" ")[0]) - 1));
  } else if (period !== "Hoje") {
    from = today.slice(0, 7) + "-01";
  }
  return {
    from,
    to: today,
    label: period === "Personalizado" ? "Este mês" : period,
  };
}
function inRange(iso, range = periodRange()) {
  return typeof iso === "string" && iso >= range.from && iso <= range.to;
}
function rangeCaption(range = periodRange()) {
  return `${formatDate(range.from)} — ${formatDate(range.to)}`;
}
function operationalMetrics(range = periodRange()) {
  const sales = appData.vendas.filter((sale) => inRange(sale.data, range));
  const valid = sales.filter((sale) => !["Cancelado", "Rascunho"].includes(sale.status));
  const paidSales = sales.filter((sale) => sale.status === "Pago");
  const ledger = appData.financeiro.filter((entry) => inRange(entry.vencimento, range));
  const sum = (items, key) => items.reduce((s, x) => s + (Number(x[key]) || 0), 0);
  const received = sum(
    ledger.filter((x) => x.tipo === "receita" && x.status === "pago"),
    "valor",
  );
  const spent = sum(
    ledger.filter((x) => x.tipo === "despesa" && x.status === "pago"),
    "valor",
  );
  const revenue = sum(paidSales, "valor");
  const receivables = appData.financeiro.filter(
    (entry) => entry.tipo === "receita" && entry.status !== "pago",
  );
  const payables = appData.financeiro.filter(
    (entry) => entry.tipo === "despesa" && entry.status !== "pago",
  );
  return {
    sales,
    valid,
    paidSales,
    ledger,
    revenue,
    ticket: paidSales.length ? revenue / paidSales.length : 0,
    received,
    spent,
    balance: received - spent,
    receivables,
    payables,
    receivable: sum(receivables, "valor"),
    payable: sum(payables, "valor"),
    pendingSales: sales.filter((sale) => sale.status === "Pendente"),
  };
}
function emptyMarkup(title, desc, action = "") {
  return /* HTML */ `<div class="empty">
          <b>${escapeHtml(title)}</b><span>${escapeHtml(desc)}</span>${action}
        </div>`;
}
function clearFilterAction(module) {
  return /* HTML */ `<button class="btn" type="button" data-clear-filters="${module}">
          Limpar filtros
        </button>`;
}
function tableEmpty(colspan, title, desc, module, create) {
  const hasFilters = ["Search", "TypeFilter", "StatusFilter"].some((suffix) => {
    const element = $(module + suffix);
    return element && element.value && element.value !== "all";
  });
  return /* HTML */ `<tr>
          <td colspan="${colspan}">
            ${emptyMarkup(
              title,
              desc,
              hasFilters
                ? clearFilterAction(module)
                : /* HTML */ `<button class="btn" type="button" data-create="${create}">
                      Adicionar
                      ${create === "produto" ? "item" : create === "receita" ? "movimentação" : create}
                    </button>`,
            )}
          </td>
        </tr>`;
}
function rowMenuButton(type, id, label) {
  return /* HTML */ `<button
          class="row-menu-trigger"
          type="button"
          data-row-menu="${type}"
          data-row-id="${id}"
          aria-label="Ações de ${escapeHtml(label)}"
          title="Ações de ${escapeHtml(label)}"
          aria-haspopup="menu"
          aria-expanded="false"
        >
          ${renderIcon("more")}
        </button>`;
}
function tableMeta(module, count) {
  const table = $(module + "View")?.querySelector(".table-wrap");
  if (table) {
    table.tabIndex = 0;
    table.setAttribute("role", "region");
    table.setAttribute(
      "aria-label",
      "Tabela de " +
        {
          finance: "movimentações",
          sales: "vendas",
          clients: "clientes",
          products: "produtos e serviços",
        }[module] +
        ". Role horizontalmente para ver todas as colunas.",
    );
  }
  const host = $(module + "Meta");
  if (host) {
    host.innerHTML = /* HTML */ `<span
              >${plural(count, "registro")} · armazenamento local</span
            ><span
              >Atualizado
              ${localUpdatedAt.toLocaleTimeString("pt-BR", {
                timeZone: APP_TIMEZONE,
                hour: "2-digit",
                minute: "2-digit",
              })}</span
            >`;
  }
}
function chartSeries(range, source = "finance") {
  const days =
    Math.round(
      (new Date(range.to + "T12:00:00Z") - new Date(range.from + "T12:00:00Z")) / 86400000,
    ) + 1;
  const buckets = [];
  if (days > 62) {
    let first = range.from.slice(0, 7) + "-01";
    while (first <= range.to) {
      const next = monthShift(first, 1);
      buckets.push({
        from: first < range.from ? range.from : first,
        to: dateShift(next, -1) < range.to ? dateShift(next, -1) : range.to,
        label: new Date(first + "T12:00:00Z")
          .toLocaleDateString("pt-BR", {
            month: "short",
            timeZone: "UTC",
          })
          .replace(".", ""),
        r: 0,
        d: 0,
      });
      first = next;
    }
  } else {
    const width = Math.max(1, Math.ceil(days / 7));
    for (let i = 0; i < days; i += width) {
      const from = dateShift(range.from, i);
      const to = dateShift(range.from, Math.min(days - 1, i + width - 1));
      buckets.push({
        from,
        to,
        label: formatDate(from).slice(0, 5),
        r: 0,
        d: 0,
      });
    }
  }
  if (source === "sales") {
    for (const v of appData.vendas.filter((sale) => sale.status === "Pago")) {
      const b = buckets.find((b) => inRange(v.data, b));
      if (b) {
        b.r += Number(v.valor) || 0;
      }
    }
  } else {
    for (const x of appData.financeiro.filter((entry) => entry.status === "pago")) {
      const b = buckets.find((b) => inRange(x.vencimento, b));
      if (b) {
        b[x.tipo === "receita" ? "r" : "d"] += Number(x.valor) || 0;
      }
    }
  }
  return {
    source,
    labels: buckets.map((b) => b.label),
    r: buckets.map((b) => b.r),
    d: buckets.map((b) => b.d),
  };
}
function updatePeriodCaptions() {
  const caption = rangeCaption();
  document
    .querySelectorAll("[data-current-period]")
    .forEach((element) => (element.textContent = caption));
  document
    .querySelectorAll(".mobile-period-select")
    .forEach((element) => (element.value = selectedPeriod));
}
function loadingConversations() {
  return Array.from(
    {
      length: 4,
    },
    () => /* HTML */ `<li class="conv-skeleton" aria-hidden="true">
              <div class="sk"></div>
              <div class="conv-skeleton-copy">
                <div class="sk" style="height:10px;width:65%"></div>
                <div class="sk" style="height:9px;width:88%"></div>
              </div>
            </li>`,
  ).join("");
}
function emptyState(target, title, desc) {
  $(target).innerHTML = /* HTML */ `<div class="empty">
          <span class="fi">${renderIcon("empty")}</span><b>${title}</b><span>${desc}</span>
        </div>`;
}
function renderCurrentView() {
  if (currentView === "Início") {
    if (typeof renderClientHome === "function") {
      renderClientHome();
    }
  } else if (currentView === "Visão Geral") {
    renderDashboardMetrics();
    renderDashboardChart();
    renderActivityFeed();
    renderChannelSummary();
    renderUpcomingPayments();
  } else if (currentView === "Meu negócio") {
    renderBusinessHub();
  } else if (currentView === "Financeiro") {
    renderFinance();
  } else if (currentView === "Vendas") {
    renderSales();
  } else if (currentView === "Clientes") {
    renderClients();
  } else if (currentView === "Produtos e Serviços") {
    renderProducts();
  } else if (currentView === "Caixa Unificada") {
    renderInbox();
  } else if (currentView === "Relatórios") {
    renderReports();
  } else if (currentView === "Configurações") {
    renderSettings();
  }
}
function initialsFromName(name) {
  return (
    String(name || "Cliente")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((x) => x[0]?.toUpperCase() || "")
      .join("") || "CL"
  );
}
function renderAll() {
  updatePeriodLabel();
  renderCurrentView();
  updateInboxNavBadge();
}
function updateFilterIndicators(module) {
  const view = $(module + "View");
  const count =
    ["TypeFilter", "StatusFilter"].reduce(
      (n, suffix) => n + Number(!!$(module + suffix) && $(module + suffix).value !== "all"),
      0,
    ) + (module === "products" && isCatalogLowStockOnly ? 1 : 0);
  const host = view.querySelector(".applied-filter-count");
  if (host) {
    host.textContent = count ? `${count} ${count === 1 ? "ativo" : "ativos"}` : "";
  }
}
