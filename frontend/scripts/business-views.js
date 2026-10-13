/* BUSINESS VIEWS */

const MANAGEMENT_TABS = [
  ["Visão Geral", "Resumo", "resumo"],
  ["Vendas", "Vendas", "vendas"],
  ["Clientes", "Clientes", "clientes"],
  ["Produtos e Serviços", "Produtos", "produtos"],
  ["Financeiro", "Financeiro", "financeiro"],
];
const MANAGEMENT_VIEWS = MANAGEMENT_TABS.map((t) => t[0]);
const MANAGEMENT_VIEW_CONFIG = {
  "Visão Geral": ["Resumo", "Como o negócio está neste período.", [["venda", "+ Nova venda", 1]]],
  Vendas: [
    "Vendas",
    "Pedidos, pagamentos e situação de cada venda.",
    [["venda", "+ Nova venda", 1]],
  ],
  Clientes: [
    "Clientes",
    "Quem compra, quando falou e quanto comprou.",
    [["cliente", "+ Novo cliente", 1]],
  ],
  "Produtos e Serviços": [
    "Produtos",
    "O que você oferece e o que mais sai.",
    [["produto", "+ Produto ou serviço", 1]],
  ],
  Financeiro: [
    "Financeiro",
    "Entradas, saídas e vencimentos.",
    [
      ["despesa", "− Saída", 0],
      ["receita", "+ Entrada", 1],
    ],
  ],
};
let productDisplayMode = "grid";
const isManagementViewActive = () => document.body.classList.contains("management-active");
const getContactInitials = (n) =>
  String(n || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((x) => x[0].toUpperCase())
    .join("");
function renderManagementSelect(id, options, val, prefix = "") {
  const cur = options.find((o) => String(o[0]) === String(val)) || options[0] || ["", ""];
  return /* HTML */ `<div class="management-select" data-id="${id}">
          <button
            type="button"
            role="combobox"
            aria-haspopup="listbox"
            aria-expanded="false"
            aria-controls="${id}L"
            aria-label="${escapeHtml(prefix)}: ${escapeHtml(cur[1])}"
          >
            <span
              >${prefix ? /* HTML */ `<small>${escapeHtml(prefix)}</small> ` : ""}${escapeHtml(cur[1])}</span
            ><i aria-hidden="true"></i>
          </button>
          <ul role="listbox" id="${id}L" aria-label="${escapeHtml(prefix)}" hidden>
            ${options
              .map(
                (o) => /* HTML */ `<li
                      role="option"
                      tabindex="-1"
                      data-v="${escapeHtml(o[0])}"
                      aria-selected="${String(o[0]) === String(cur[0])}"
                    >
                      ${escapeHtml(o[1])}
                    </li>`,
              )
              .join("")}
          </ul>
        </div>`;
}
function syncManagementSelect(id) {
  const h = document.querySelector(`[data-nv-host="${id}"]`);
  const s = document.getElementById(id);
  if (!h || !s || h.querySelector("[aria-expanded=true]")) {
    return;
  }
  h.innerHTML = renderManagementSelect(
    id,
    [...s.options].map((o) => [o.value, o.text]),
    s.value,
    h.dataset.pre || "",
  );
}
function openManagementSelect(b) {
  const l = b.nextElementSibling;
  l.hidden = false;
  b.setAttribute("aria-expanded", "true");
  (l.querySelector("[aria-selected=true]") || l.firstElementChild)?.focus();
}
function closeManagementSelect(b, f) {
  b.nextElementSibling.hidden = true;
  b.setAttribute("aria-expanded", "false");
  if (f) {
    b.focus();
  }
}
function playPeriodReveal() {
  [$("kp"), $("financeSummary"), $("financeMiniChart")].forEach((target) => {
    if (!target) {
      return;
    }
    target.classList.remove("is-period-reveal");
    void target.offsetWidth;
    target.classList.add("is-period-reveal");
    setTimeout(() => target.classList.remove("is-period-reveal"), 420);
  });
}
function selectManagementOption(sel, v) {
  const id = sel.dataset.id;
  closeManagementSelect(sel.querySelector("button"));
  if (id === "nvPeriod") {
    if (v === "Personalizado") {
      const dateRange = periodRange();
      $("mobileDateFrom").value = dateRange.from;
      $("mobileDateTo").value = dateRange.to;
      openModal("periodModal");
      return;
    }
    selectedPeriod = v;
    customRange = null;
    updatePeriodLabel();
    renderCurrentView();
    playPeriodReveal();
    document.querySelector("#nvPer button")?.focus();
    return;
  }
  if (id === "nvTrack") {
    focusedSaleId = Number(v);
    renderBusinessHub();
    document.querySelector("[data-id=nvTrack] button")?.focus();
    return;
  }
  const n = document.getElementById(id);
  n.value = v;
  n.dispatchEvent(
    new Event("change", {
      bubbles: true,
    }),
  );
  syncManagementSelect(id);
  document.querySelector(`[data-nv-host="${id}"] button`)?.focus();
}
function syncManagementHeader() {
  const p = $("nvPer");
  if (!p.querySelector("[aria-expanded=true]")) {
    p.innerHTML = renderManagementSelect(
      "nvPeriod",
      [
        "Hoje",
        "7 dias",
        "30 dias",
        "Este mês",
        "3 meses",
        "6 meses",
        "12 meses",
        "Personalizado",
      ].map((x) => [x, x]),
      selectedPeriod,
      "Período",
    );
  }
  updatePrivacyButton();
}
function positionManagementTabIndicator() {
  const t = $("nvTabs");
  const b = t.querySelector("[aria-selected=true]");
  const i = t.querySelector(".management-tab-indicator");
  if (b && i) {
    i.style.transform = `translateX(${b.offsetLeft}px) scaleX(${b.offsetWidth})`;
  }
}
function showManagementView(name) {
  const h = MANAGEMENT_VIEW_CONFIG[name];
  const t = $("nvTabs");
  $("nvShell").hidden = false;
  $("nvTitle").textContent = h[0];
  $("nvSub").textContent = h[1];
  $("nvActs").innerHTML = h[2]
    .map(
      (a) => /* HTML */ `<button
                class="management-button${a[2] ? " pr" : ""}"
                type="button"
                data-create="${a[0]}"
              >
                ${a[1]}
              </button>`,
    )
    .join("");
  if (!t.children.length) {
    t.innerHTML =
      '<i class="management-tab-indicator" aria-hidden="true"></i>' +
      MANAGEMENT_TABS.map(
        ([v, l, s]) => /* HTML */ `<button
                  role="tab"
                  id="nvt-${s}"
                  data-nv-tab="${v}"
                  aria-controls="${
                    $("dashboardView").id &&
                    {
                      "Visão Geral": "dashboardView",
                      Vendas: "salesView",
                      Clientes: "clientsView",
                      "Produtos e Serviços": "productsView",
                      Financeiro: "financeView",
                    }[v]
                  }"
                >
                  ${l}
                </button>`,
      ).join("");
  }
  t.querySelectorAll("[role=tab]").forEach((b) => {
    const on = b.dataset.nvTab === name;
    b.setAttribute("aria-selected", on);
    b.tabIndex = on ? 0 : -1;
  });
  requestAnimationFrame(() => {
    positionManagementTabIndicator();
    t.querySelector("[aria-selected=true]")?.scrollIntoView({
      inline: "nearest",
      block: "nearest",
    });
  });
  try {
    history.replaceState(null, "", "#negocio/" + MANAGEMENT_TABS.find((x) => x[0] === name)[2]);
  } catch (_) {}
  syncManagementHeader();
}
const baseSetView = setView;
setView = function (name, o = {}) {
  let track = false;
  if (name === "Meu negócio") {
    name = "Visão Geral";
    track = true;
  }
  const on = MANAGEMENT_VIEWS.includes(name);
  document.body.classList.toggle("management-active", on);
  $("nvShell").hidden = !on;
  if (!on && location.hash.startsWith("#negocio")) {
    try {
      history.replaceState(null, "", location.pathname + location.search);
    } catch (_) {}
  }
  baseSetView(name, o);
  if (on) {
    showManagementView(name);
  }
  if (track) {
    setTimeout(
      () =>
        $("nvTrackCard")?.scrollIntoView({
          block: "start",
        }),
      60,
    );
  }
};
const baseRenderCurrentView = renderCurrentView;
renderCurrentView = function () {
  baseRenderCurrentView();
  if (isManagementViewActive()) {
    syncManagementHeader();
  }
};
const baseOpenRecord = openRecord;
openRecord = function (t, i) {
  baseOpenRecord(t, i);
  if (t === "sales") {
    renderSaleDrawer(Number(i));
  }
};
const baseOpenCreate = openCreate;
openCreate = function (t, p) {
  $("createModal").classList.toggle("management-drawer", isManagementViewActive());
  baseOpenCreate(t, p);
};
function updateHeaderContext() {
  const nv = MANAGEMENT_VIEWS.includes(currentView);
  $("businessTabs").hidden = true;
  document.querySelectorAll("[data-nav]").forEach((a) => {
    const on = a.dataset.navGroup ? nv : a.dataset.nav === currentView;
    if (on) {
      a.setAttribute("aria-current", "page");
    } else {
      a.removeAttribute("aria-current");
    }
  });
  const T = {
    Início: "Seu espaço",
    "Caixa Unificada": "SocialMEI.IA",
    Automações: "Automações",
    Assistente: "Assistente",
    Relatórios: "Relatórios",
    Configurações: "Configurações",
  };
  document.querySelector(".hd-title h1").textContent = nv
    ? "Negócio"
    : T[currentView] || currentView;
  $("gr").textContent = "Seu espaço";
  $("globalCreateBtn").style.display = "none";
  $("utilityTools").open = false;
  updatePeriodCaptions();
  positionSidebarIndicator();
  closeRowMenu();
  syncShellInert();
}
/**
 * Renderiza os destinos da sidebar. Os nomes de rota permanecem compatíveis com as preferências salvas.
 */
function renderNavigation() {
  const L = (n, l, i, x = "") => /* HTML */ `<a
            class="nav-chapter"
            href="#${normalizedText(n).replaceAll(" ", "-")}"
            data-nav="${n}"
            ${n === "Visão Geral" ? 'data-nav-group="negocio"' : ""}
            aria-label="${x || l}"
            title="${x || l}"
            ><span class="nav-index">${renderIcon(i)}</span><span><b>${l}</b></span></a
          >`;
  $("nav").innerHTML = /* HTML */ `<span class="nav-indicator" aria-hidden="true"></span
          ><span class="nav-group-label">Dia a dia</span
          >${L("Início", "Início", "user")}${L("Caixa Unificada", "Caixa Unificada", "inbox")}<span
            class="nav-group-label"
            >Negócio</span
          >${L("Visão Geral", "Negócio", "bag", "Negócio")}<span class="nav-group-label"
            >Assistência</span
          >${L("Automações", "Automações", "bolt")}${L("Assistente", "Assistente", "detail")}<span
            class="nav-group-label"
            >Gestão</span
          >${L("Relatórios", "Relatórios", "note")}${L("Configurações", "Configurações", "cfg")}`;
  $("businessTabs").innerHTML = "";
  updateInboxNavBadge();
}
function renderManagementSparkline(a, c) {
  if (areMoneyValuesHidden || a.length < 2 || !a.some((x) => x)) {
    return '<svg class="management-sparkline" viewBox="0 0 100 28" aria-hidden="true"><path class="flat" d="M0 24H100"/></svg>';
  }
  const mn = Math.min(...a, 0);
  const mx = Math.max(...a, 0);
  const g = mx - mn || 1;
  return /* HTML */ `<svg
          class="management-sparkline ${c || ""}"
          viewBox="0 0 100 28"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <polyline
            points="${a.map((x, i) => `${(i / (a.length - 1)) * 100},${26 - ((x - mn) / g) * 24}`).join(" ")}"
          />
        </svg>`;
}
function renderManagementChart(series) {
  const sales = series.source === "sales";
  const mx = Math.max(...series.r, ...series.d);
  const st = Math.pow(10, Math.floor(Math.log10(mx)));
  const top = (Math.ceil((mx / st) * 2) / 2) * st || st;
  const f = (v) =>
    new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: "BRL",
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(v);
  return /* HTML */ `<div class="management-chart">
          <div class="management-axis" aria-hidden="true">
            ${[1, 0.5, 0].map((t) => /* HTML */ `<span style="--y:${100 - t * 100}%">${f(top * t)}</span>`).join("")}
          </div>
          <div class="management-plot" style="--chart-column-count:${Math.max(1, series.labels.length)}">
            ${series.labels
              .map(
                (l, i) => /* HTML */ `<button
                    class="management-chart-column"
                    style="--chart-column-index:${i}"
                    type="button"
                    aria-label="${escapeHtml(l)}: ${sales ? "faturamento" : "entrou"} ${money(series.r[i])}${sales ? "" : `, saiu ${money(series.d[i])}`}"
                  >
                    <span class="management-bars"
                      ><i
                        style="height:${series.r[i] ? Math.max((series.r[i] / top) * 100, 2) : 0}%"
                      ></i
                      >${
                        sales
                          ? ""
                          : /* HTML */ `<i
                        class="out"
                        style="height:${series.d[i] ? Math.max((series.d[i] / top) * 100, 2) : 0}%"
                      ></i>`
                      }</span
                    ><span class="management-chart-tooltip" aria-hidden="true"
                      >${escapeHtml(l)}<br />${sales ? "Faturamento" : "Entrou"} ${money(series.r[i])}${sales ? "" : `<br />Saiu ${money(series.d[i])}`}</span
                    ><em>${escapeHtml(l)}</em>
                  </button>`,
              )
              .join("")}
          </div>
        </div>`;
}
function renderManagementChartMarkup() {
  const dateRange = periodRange();
  const series = chartSeries(dateRange);
  if (areMoneyValuesHidden) {
    return emptyMarkup("Valores ocultos", "Use “Exibir valores” para ver o gráfico.");
  }
  if (!Math.max(...series.r, ...series.d)) {
    return emptyMarkup(
      "Sem movimentação paga neste período",
      "Registre uma entrada ou saída para ver o gráfico.",
      '<button class="management-button" data-create="receita">+ Entrada</button>',
    );
  }
  return renderManagementChart(series);
}
function renderDashboardMetrics() {
  const metrics = operationalMetrics();
  const dateRange = periodRange();
  const d =
    Math.round(
      (new Date(dateRange.to + "T12:00:00Z") - new Date(dateRange.from + "T12:00:00Z")) / 864e5,
    ) + 1;
  const p = operationalMetrics({
    from: dateShift(dateRange.from, -d),
    to: dateShift(dateRange.from, -1),
  });
  const series = chartSeries(dateRange);
  const dl = (a, b, inv) => {
    if (areMoneyValuesHidden) {
      return "";
    }
    if (!b) {
      return '<small class="management-metric-change">sem comparação ainda</small>';
    }
    const x = ((a - b) / Math.abs(b)) * 100;
    const g = inv ? x <= 0 : x >= 0;
    return /* HTML */ `<small class="management-metric-change ${g ? "up" : "dn"}"
            >${x >= 0 ? "▲" : "▼"}
            ${Math.abs(x).toLocaleString("pt-BR", {
              maximumFractionDigits: 0,
            })}%
            vs. período anterior</small
          >`;
  };
  const C = (l, v, sub, sp, c = "") => /* HTML */ `<article class="management-kpi">
            <span>${l}</span><b class="${c}">${money(v)}</b>${sub}${sp}
          </article>`;
  $("kp").innerHTML =
    C(
      "Entrou",
      metrics.received,
      dl(metrics.received, p.received),
      renderManagementSparkline(series.r),
    ) +
    C(
      "Saiu",
      metrics.spent,
      dl(metrics.spent, p.spent, 1),
      renderManagementSparkline(series.d, "out"),
    ) +
    C(
      "Ficou no período",
      metrics.balance,
      dl(metrics.balance, p.balance),
      renderManagementSparkline(series.r.map((x, i) => x - series.d[i])),
      metrics.balance < 0 ? "neg" : "",
    ) +
    C(
      "A receber",
      metrics.receivable,
      /* HTML */ `<small class="management-metric-change"
              >${plural(metrics.receivables.length, "lançamento em aberto", "lançamentos em aberto")}</small
            >`,
      "",
    );
  renderAttention();
  renderSalesOverviewCard();
  renderBusinessHub();
  updatePrivacyButton();
  updatePeriodCaptions();
}
function renderDashboardChart() {
  const dateRange = periodRange();
  $("cs").textContent = `${rangeCaption(dateRange)} · pelo vencimento dos lançamentos pagos`;
  $("cw").innerHTML = renderManagementChartMarkup();
}
function renderActivityFeed() {}
function renderChannelSummary() {}
function renderUpcomingPayments() {}
function renderAttention() {
  const today = todayISO();
  const L = [];
  const tg = (c, x) => /* HTML */ `<span class="pill ${c}">${x}</span>`;
  const od = appData.financeiro
    .filter((entry) => ledgerStatus(entry) === "atrasado")
    .sort((entry, otherEntry) => entry.vencimento.localeCompare(otherEntry.vencimento));
  od.slice(0, 3).forEach((x) =>
    L.push([
      tg("red", "Atrasado"),
      x.descricao,
      `${x.tipo === "receita" ? "A receber" : "A pagar"} · venceu ${formatDate(x.vencimento)} · ${money(x.valor)}`,
      /* HTML */ `<button class="management-button sm" data-finance-paid="${x.id}">
              ${x.tipo === "receita" ? "Marcar recebido" : "Marcar pago"}
            </button>`,
    ]),
  );
  if (od.length > 3) {
    L.push([
      tg("red", "Atrasado"),
      `Mais ${od.length - 3} em atraso`,
      "Veja todos no Financeiro",
      '<button class="management-button sm" data-go="Financeiro">Abrir</button>',
    ]);
  }
  appData.financeiro
    .filter((entry) => entry.status !== "pago" && entry.vencimento === today)
    .forEach((entry) =>
      L.push([
        tg("amber", "Vence hoje"),
        entry.descricao,
        `${entry.tipo === "receita" ? "A receber" : "A pagar"} · ${money(entry.valor)}`,
        /* HTML */ `<button
                class="management-button sm"
                data-record-open="finance"
                data-record-id="${entry.id}"
              >
                Conferir
              </button>`,
      ]),
    );
  appData.vendas
    .filter((sale) => sale.status === "Pendente")
    .slice(0, 3)
    .forEach((sale) =>
      L.push([
        tg("amber", "Aguardando pagamento"),
        `Venda #${sale.id} · ${sale.cliente}`,
        `${formatDate(sale.data)} · ${sale.pagamento} · ${money(sale.valor)}`,
        /* HTML */ `<button
                class="management-button sm"
                data-record-open="sales"
                data-record-id="${sale.id}"
              >
                Conferir
              </button>`,
      ]),
    );
  sessionData.conversas
    .filter(
      (conversation) =>
        ["aberto", "andamento"].includes(conversation.status) &&
        [...conversation.mensagens].reverse().find((m) => m.de !== "nota")?.de === "cliente",
    )
    .slice(0, 3)
    .forEach((conversation) =>
      L.push([
        tg("info", "Espera resposta"),
        displayName(conversation),
        lastMessage(conversation).slice(0, 70),
        /* HTML */ `<button
                class="management-button sm"
                data-client-conversation="${conversation.id}"
              >
                Responder
              </button>`,
      ]),
    );
  const low = priorityItems().find((x) => x.kind === "stock");
  if (low) {
    L.push([
      tg("amber", "Estoque"),
      low.title,
      low.desc,
      '<button class="management-button sm" data-resolve-priority="stock">Ver estoque</button>',
    ]);
  }
  $("attentionList").innerHTML = L.length
    ? L.slice(0, 8)
        .map(
          (x) => /* HTML */ `<li>
                    ${x[0]}
                    <div><b>${escapeHtml(x[1])}</b><small>${escapeHtml(x[2])}</small></div>
                    ${x[3]}
                  </li>`,
        )
        .join("")
    : /* HTML */ `<li style="display:block">
              ${emptyMarkup("Tudo em dia", "Nada pedindo sua atenção agora.")}
            </li>`;
}
function renderSalesOverviewCard() {
  const metrics = operationalMetrics();
  const it = {};
  metrics.valid.forEach((v) => {
    if (v.item) {
      it[v.item] = (it[v.item] || 0) + (Number(v.quantidade) || 1);
    }
  });
  const top = Object.entries(it)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  $("nvSales").innerHTML = /* HTML */ `<div class="management-stats">
            <div><small>Pagos</small><b>${metrics.paidSales.length}</b></div>
            <div><small>Pendentes</small><b>${metrics.pendingSales.length}</b></div>
            <div><small>Ticket médio</small><b>${money(metrics.ticket)}</b></div>
          </div>
          <h4 style="font-size:14px;margin:12px 0 8px">Mais vendidos</h4>
          ${
            top.length
              ? /* HTML */ `<ul class="management-top">
                  ${top.map(([n, q]) => /* HTML */ `<li><span>${escapeHtml(n)}</span><b class="management-numeric-value">${q} un.</b></li>`).join("")}
                </ul>`
              : '<p class="management-note">Nenhuma venda do período tem item registrado.</p>'
          }<button class="management-button sm" style="margin-top:12px" data-go="Vendas">
            Ver vendas
          </button>`;
}
function renderBusinessHub() {
  const host = $("businessHubBody");
  if (!host) {
    return;
  }
  const sales = [...appData.vendas].sort((a, b) => b.data.localeCompare(a.data));
  const c =
    sales.find((sale) => sale.id === focusedSaleId) ||
    sales.find((sale) => sale.status === "Pendente") ||
    sales[0];
  if (!c) {
    host.innerHTML = emptyMarkup(
      "Nenhuma venda para acompanhar",
      "Registre um pedido para ver o caminho dele.",
      '<button class="management-button pr" data-create="venda">+ Nova venda</button>',
    );
    return;
  }
  const cl = appData.clientes.find((client) => SocialMEISales.matchesClient(c, client));
  const cv = sessionData.conversas.find(
    (conversation) =>
      conversation.clientId === cl?.id ||
      normalizedText(displayName(conversation)) === normalizedText(c.cliente),
  );
  const led =
    SocialMEISales.remote || SocialMEIFinance.remote
      ? []
      : appData.financeiro.filter((entry) => entry.descricao === `Venda #${c.id}`);
  const pr = appData.produtos.find((product) => SocialMEISales.matchesProduct(c, product));
  const S = (n, k, t, a) => /* HTML */ `<li>
            <i>${n}</i>
            <div><small>${k}</small><b>${t}</b></div>
            ${a || ""}
          </li>`;
  host.innerHTML = /* HTML */ `<div class="management-tracking">
            ${renderManagementSelect(
              "nvTrack",
              sales.map((sale) => [sale.id, `#${sale.id} · ${sale.cliente}`]),
              c.id,
              "Pedido",
            )}<span
              ><b class="management-numeric-value">${money(c.valor)}</b>
              <span class="pill ${saleStatusClass(c.status)}">${escapeHtml(c.status)}</span></span
            >
          </div>
          <ol class="management-flow">
            ${S(
              1,
              "Pessoa",
              cl
                ? `${escapeHtml(cl.nome)} · ${escapeHtml(cl.status)}`
                : "Sem perfil de cliente com este nome",
              cl
                ? /* HTML */ `<button class="management-button sm" data-open-client="${cl.id}">
                      Abrir
                    </button>`
                : '<button class="management-button sm" data-create="cliente">Cadastrar</button>',
            )}${S(
              2,
              "Dinheiro",
              led.length
                ? `${money(led.reduce((s, x) => s + x.valor, 0))} · ${led.map((x) => financeStatusLabel(ledgerStatus(x), x.tipo)).join(", ")}`
                : "Nenhum lançamento vinculado",
              led[0]
                ? /* HTML */ `<button
                      class="management-button sm"
                      data-record-open="finance"
                      data-record-id="${led[0].id}"
                    >
                      Abrir
                    </button>`
                : "",
            )}${S(
              3,
              "Item",
              c.item
                ? `${escapeHtml(c.item)}${c.quantidade ? ` × ${c.quantidade}` : ""}${pr ? "" : " (fora do catálogo)"}`
                : "Item não informado no pedido",
              pr
                ? /* HTML */ `<button
                      class="management-button sm"
                      data-record-open="products"
                      data-record-id="${pr.id}"
                    >
                      Abrir
                    </button>`
                : "",
            )}${S(
              4,
              "Conversa",
              cv
                ? `${channelLabel(cv.canal)} · ${statusLabel(cv.status)}`
                : "Nenhuma conversa vinculada",
              cv
                ? /* HTML */ `<button
                      class="management-button sm"
                      data-client-conversation="${cv.id}"
                    >
                      Abrir
                    </button>`
                : "",
            )}
          </ol>
          <button class="management-button" data-record-open="sales" data-record-id="${c.id}">
            ${c.status === "Pendente" ? "Conferir recebimento" : "Abrir pedido"}
          </button>`;
}
function renderSales() {
  const metrics = operationalMetrics();
  // Apresentação derivada dos mesmos dados e período; os filtros operacionais permanecem.
  $("salesPremiumSummary").innerHTML = `<div class="internal-metric internal-metric--primary">
          <span>Vendas pagas</span><b>${money(metrics.revenue)}</b><small>${plural(metrics.paidSales.length, "venda", "vendas")} · ${rangeCaption(periodRange())}</small>
        </div><div class="internal-metric"><span>Pedidos</span><b>${metrics.sales.length}</b><small>${plural(metrics.paidSales.length, "pago", "pagos")}</small></div>
        <div class="internal-metric"><span>Ticket médio</span><b>${money(metrics.ticket)}</b><small>vendas pagas</small></div>
        <div class="internal-metric"><span>Pendentes</span><b>${metrics.pendingSales.length}</b><small>${money(metrics.pendingSales.reduce((total, sale) => total + (Number(sale.valor) || 0), 0))} a conferir</small></div>`;
  const searchQuery = normalizedText($("salesSearch").value.trim());
  const st = $("salesStatusFilter").value;
  const ps = $("salesPaymentFilter");
  const pays = [...new Set(appData.vendas.map((sale) => sale.pagamento).filter(Boolean))];
  const keep = ps.value;
  if (JSON.stringify([...ps.options].slice(1).map((o) => o.value)) !== JSON.stringify(pays)) {
    ps.innerHTML =
      '<option value="all">Todas</option>' +
      pays.map((p) => /* HTML */ `<option>${escapeHtml(p)}</option>`).join("");
    ps.value = pays.includes(keep) ? keep : "all";
  }
  const pay = ps.value || "all";
  $("salesSummary").innerHTML = [
    ["all", "Todos", metrics.sales.length],
    ...["Rascunho", "Pendente", "Pago", "Cancelado"].map((s) => [
      s,
      s,
      metrics.sales.filter((sale) => sale.status === s).length,
    ]),
  ]
    .map(
      ([k, l, n]) => /* HTML */ `<button
                type="button"
                class="management-chip"
                data-trade-phase="${k}"
                aria-pressed="${st === k}"
              >
                ${l}<b>${n}</b>
              </button>`,
    )
    .join("");
  const rows = metrics.sales
    .filter(
      (sale) =>
        (!searchQuery ||
          normalizedText(`#${sale.id} ${sale.cliente} ${sale.item || ""}`).includes(searchQuery)) &&
        (st === "all" || sale.status === st) &&
        (pay === "all" || sale.pagamento === pay),
    )
    .sort((sale, otherSale) => otherSale.data.localeCompare(sale.data));
  $("salesTable").innerHTML = rows.length
    ? /* HTML */ `<div class="management-table-wrapper">
              <table class="management-table">
                <caption class="sr-only"> Vendas do período </caption>
                <thead>
                  <tr>
                    <th scope="col">Cliente</th>
                    <th scope="col">Data</th>
                    <th scope="col">Pagamento</th>
                    <th scope="col" class="r">Valor</th>
                    <th scope="col">Situação</th>
                    <th scope="col"><span class="sr-only">Ações</span></th>
                  </tr>
                </thead>
                <tbody>
                  ${rows
                    .map(
                      (v) => /* HTML */ `<tr>
                          <td data-l="Cliente">
                            <div class="management-contact">
                              <span class="av">${escapeHtml(getContactInitials(v.cliente))}</span>
                              <div>
                                <button
                                  class="row-action"
                                  type="button"
                                  data-record-open="sales"
                                  data-record-id="${v.id}"
                                >
                                  ${escapeHtml(v.cliente)}</button
                                ><small>#${v.id}${v.item ? " · " + escapeHtml(v.item) : ""}</small>
                              </div>
                            </div>
                          </td>
                          <td data-l="Data">${formatDate(v.data)}</td>
                          <td data-l="Pagamento">${escapeHtml(v.pagamento)}</td>
                          <td data-l="Valor" class="r management-numeric-value"
                            >${money(v.valor)}</td
                          >
                          <td data-l="Situação">
                            <span class="pill ${saleStatusClass(v.status)}"
                              >${escapeHtml(v.status)}</span
                            >
                          </td>
                          <td class="act">
                            <button
                              class="management-button sm"
                              type="button"
                              data-record-open="sales"
                              data-record-id="${v.id}"
                            >
                              ${v.status === "Pendente" ? "Conferir" : "Abrir"}</button
                            >${rowMenuButton("sales", v.id, "venda #" + v.id)}
                          </td>
                        </tr>`,
                    )
                    .join("")}
                </tbody>
              </table>
            </div>`
    : emptyMarkup(
        "Nenhuma venda encontrada",
        "Tente outra busca, situação ou período.",
        clearFilterAction("sales") +
          '<button class="management-button pr" data-create="venda">+ Nova venda</button>',
      );
  tableMeta("sales", rows.length);
  updatePeriodCaptions();
  updateFilterIndicators("sales");
  syncManagementSelect("salesPaymentFilter");
}
function renderSaleDrawer(id) {
  const v = appData.vendas.find((sale) => sale.id === id);
  if (!v) {
    return;
  }
  const cl = appData.clientes.find((client) => SocialMEISales.matchesClient(v, client));
  const led =
    SocialMEISales.remote || SocialMEIFinance.remote
      ? []
      : appData.financeiro.filter((entry) => entry.descricao === `Venda #${v.id}`);
  const pay =
    v.status === "Pendente" || v.status === "Rascunho"
      ? /* HTML */ `<p class="management-note" style="font-size:14px">
                  Recebeu ${money(v.valor)} por ${escapeHtml(v.pagamento)}? Confirme para marcar a
                  venda como paga.
                </p>
                <button
                  class="management-button pr"
                  style="margin-top:8px"
                  data-sale-paid="${v.id}"
                >
                  Conferir recebimento
                </button>`
      : /* HTML */ `<p style="font-size:14px">
                ${v.status === "Pago" ? "Recebimento confirmado." : "Pedido cancelado."}
              </p>`;
  $("recordTitle").textContent = `Venda #${v.id}`;
  $("recordBody").innerHTML = /* HTML */ `<div class="management-detail-summary">
            <div>
              <small>Valor</small
              ><b class="management-metric-value management-numeric-value">${money(v.valor)}</b>
            </div>
            <span class="pill ${saleStatusClass(v.status)}">${escapeHtml(v.status)}</span>
          </div>
          <dl class="management-detail-list">
            <div>
              <dt>Cliente</dt>
              <dd>
                ${cl ? /* HTML */ `<button class="lk" data-open-client="${cl.id}">${escapeHtml(v.cliente)}</button>` : escapeHtml(v.cliente)}
              </dd>
            </div>
            <div>
              <dt>Data</dt>
              <dd>${formatDate(v.data)}</dd>
            </div>
            <div>
              <dt>Pagamento</dt>
              <dd>${escapeHtml(v.pagamento)}</dd>
            </div>
          </dl>
          <h4>Itens</h4>
          <div class="management-item">
            ${v.item ? /* HTML */ `<span>${escapeHtml(v.item)}</span><b>× ${v.quantidade || 1}</b>` : "<span>Item não informado no registro</span>"}
          </div>
          <h4>Pagamento</h4>
          ${pay}
          <h4>Histórico</h4>
          <ol class="management-history">
            <li><span>Pedido registrado</span><span>${formatDate(v.data)}</span></li>
            ${led.map((x) => /* HTML */ `<li><span>Lançamento: ${financeStatusLabel(ledgerStatus(x), x.tipo)}</span><span>${formatDate(x.vencimento)}</span></li>`).join("")}${v.status === "Cancelado" ? "<li><span>Pedido cancelado</span><span></span></li>" : ""}
          </ol>
          <div class="management-drawer-footer">
            <button class="management-button" data-sale-duplicate="${v.id}">
              Duplicar como rascunho
            </button>
          </div>`;
}
function renderManagementChannel(c, cv) {
  return cv
    ? channelLabel(cv.canal)
    : /@/.test(c.instagram || "")
      ? "Instagram"
      : /\d/.test(c.telefone || "")
        ? "WhatsApp"
        : "—";
}
function renderClients() {
  const searchQuery = normalizedText($("clientsSearch").value.trim());
  const st = $("clientsStatusFilter").value;
  const cs = $("clientsTypeFilter");
  const ts = $("clientsTagFilter");
  const all = appData.clientes;
  const rel = (c) => appData.vendas.filter((sale) => SocialMEISales.matchesClient(sale, c));
  const cvs = (c) =>
    sessionData.conversas.filter(
      (conversation) =>
        conversation.clientId === c.id ||
        normalizedText(displayName(conversation)) === normalizedText(c.nome),
    );
  const wait = (c) => cvs(c).some((v) => v.naoLidas || v.status === "aberto");
  const ret = (c) => rel(c).filter((v) => v.status === "Pago").length > 1;
  // Contagens da base atual; nenhuma estimativa ou cadastro fictício.
  $("clientsPremiumSummary").innerHTML =
    `<div class="internal-metric internal-metric--primary"><span>Clientes ativos</span><b>${all.filter((client) => client.status === "Ativo").length}</b><small>${plural(all.length, "cliente", "clientes")} na base · ${plural(all.filter((client) => client.status === "Novo").length, "novo", "novos")}</small></div>
          <div class="internal-metric"><span>Aguardando</span><b>${all.filter(wait).length}</b><small>conversa aberta ou não lida</small></div>
          <div class="internal-metric"><span>Recorrentes</span><b>${all.filter(ret).length}</b><small>mais de uma compra paga</small></div>`;
  const chans = [
    ...new Set(all.map((c) => renderManagementChannel(c, cvs(c)[0])).filter((x) => x !== "—")),
  ];
  const tags = [...new Set(all.flatMap((c) => c.tags || []))];
  const k1 = cs.value;
  const k2 = ts.value;
  cs.innerHTML =
    '<option value="all">Todos</option>' +
    chans.map((x) => /* HTML */ `<option>${escapeHtml(x)}</option>`).join("");
  cs.value = chans.includes(k1) ? k1 : "all";
  ts.innerHTML =
    '<option value="all">Todas</option>' +
    tags.map((x) => /* HTML */ `<option>${escapeHtml(x)}</option>`).join("");
  ts.value = tags.includes(k2) ? k2 : "all";
  $("clientsIntro").innerHTML = [
    ["all", "Todos", all.length],
    ["waiting", "Aguardando", all.filter(wait).length],
    ["returning", "Recorrentes", all.filter(ret).length],
  ]
    .map(
      ([k, l, n]) => /* HTML */ `<button
                type="button"
                class="management-chip"
                data-client-segment="${k}"
                aria-pressed="${selectedClientSegment === k}"
              >
                ${l}<b>${n}</b>
              </button>`,
    )
    .join("");
  const rows = all
    .filter(
      (c) =>
        (!searchQuery ||
          normalizedText(c.nome + " " + c.telefone + " " + c.instagram).includes(searchQuery)) &&
        (st === "all" || c.status === st) &&
        (cs.value === "all" || renderManagementChannel(c, cvs(c)[0]) === cs.value) &&
        (ts.value === "all" || (c.tags || []).includes(ts.value)) &&
        (selectedClientSegment === "all" ||
          (selectedClientSegment === "waiting" && wait(c)) ||
          (selectedClientSegment === "returning" && ret(c))),
    )
    .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  $("clientsTable").innerHTML = rows.length
    ? /* HTML */ `<div class="management-table-wrapper">
              <table class="management-table">
                <caption class="sr-only"> Clientes </caption>
                <thead>
                  <tr>
                    <th scope="col">Cliente</th>
                    <th scope="col">Canal</th>
                    <th scope="col">Última interação</th>
                    <th scope="col" class="r">Total comprado</th>
                    <th scope="col">Etiquetas</th>
                    <th scope="col">Status</th>
                    <th scope="col"><span class="sr-only">Ações</span></th>
                  </tr>
                </thead>
                <tbody>
                  ${rows
                    .map(
                      (c) => /* HTML */ `<tr>
                          <td data-l="Cliente">
                            <div class="management-contact">
                              <span class="av">${escapeHtml(getContactInitials(c.nome))}</span>
                              <div>
                                <button class="row-action" type="button" data-open-client="${c.id}">
                                  ${escapeHtml(c.nome)}</button
                                ><small
                                  >${escapeHtml(c.telefone && c.telefone !== "—" ? c.telefone : c.instagram || "Contato não informado")}${ret(c) ? ' · <span class="management-recurring">Recorrente</span>' : ""}</small
                                >
                              </div>
                            </div>
                          </td>
                          <td data-l="Canal"
                            ><span class="management-channel">${escapeHtml(renderManagementChannel(c, cvs(c)[0]))}</span></td
                          >
                          <td data-l="Última">${escapeHtml(c.ultima || "—")}</td>
                          <td data-l="Valor" class="r management-numeric-value">
                            ${money(c.total || 0)}
                          </td>
                          <td data-l="Etiquetas">
                            <span class="management-tags"
                              >${
                                (c.tags || [])
                                  .slice(0, 2)
                                  .map(
                                    (t) =>
                                      /* HTML */ `<span class="pill draft">${escapeHtml(t)}</span>`,
                                  )
                                  .join("") || "—"
                              }</span
                            >
                          </td>
                          <td data-l="Status">
                            <span
                              class="pill ${c.status === "Novo" ? "amber" : c.status === "Inativo" ? "draft" : "green"}"
                              >${escapeHtml(c.status)}</span
                            >
                          </td>
                          <td class="act">
                            <button
                              class="management-button sm"
                              type="button"
                              data-open-client="${c.id}"
                            >
                              Abrir</button
                            >${rowMenuButton("clients", c.id, c.nome)}
                          </td>
                        </tr>`,
                    )
                    .join("")}
                </tbody>
              </table>
            </div>`
    : emptyMarkup(
        all.length ? "Nenhum cliente nesta seleção" : "Nenhum cliente ainda",
        all.length ? "Tente outro nome ou limpe os filtros." : "Cadastre seu primeiro cliente.",
        all.length
          ? clearFilterAction("clients")
          : '<button class="management-button pr" data-create="cliente">+ Novo cliente</button>',
      );
  tableMeta("clients", rows.length);
  updateFilterIndicators("clients");
  ["clientsTypeFilter", "clientsTagFilter", "clientsStatusFilter"].forEach(syncManagementSelect);
}
function renderClientPanel() {
  const c = appData.clientes.find((client) => client.id === drawerClientId);
  if (!c) {
    return;
  }
  const rel = appData.vendas.filter((sale) => SocialMEISales.matchesClient(sale, c));
  const fin = appData.financeiro.filter(
    (entry) =>
      SocialMEIFinance.matchesClient(entry, c) ||
      (!SocialMEIFinance.remote &&
        !SocialMEISales.remote &&
        rel.some((v) => entry.descricao === `Venda #${v.id}`)),
  );
  const cv = sessionData.conversas.filter((conversation) =>
    SocialMEIClients.remote
      ? SocialMEIClients.conversationClient(conversation)?.id === c.id
      : conversation.clientId === c.id ||
        normalizedText(displayName(conversation)) === normalizedText(c.nome),
  );
  const li = (a, b, r) => /* HTML */ `<li
            style="display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);font-size:14px"
          >
            <div>${a}<small class="management-note" style="display:block">${b}</small></div>
            ${r || ""}
          </li>`;
  let h = "";
  if (selectedClientTab === "resumo") {
    const last = [...rel].sort((a, b) => b.data.localeCompare(a.data))[0];
    h = /* HTML */ `<div class="management-stats">
              <div><small>Total comprado</small><b>${money(c.total || 0)}</b></div>
              <div><small>Pendente</small><b>${money(c.pendente || 0)}</b></div>
              <div><small>Última interação</small><b>${escapeHtml(c.ultima || "—")}</b></div>
            </div>
            <dl class="management-detail-list">
              <div>
                <dt>Telefone</dt>
                <dd>${escapeHtml(c.telefone || "—")}</dd>
              </div>
              <div>
                <dt>Instagram</dt>
                <dd>${escapeHtml(c.instagram || "—")}</dd>
              </div>
              <div>
                <dt>Última venda</dt>
                <dd>${last ? `#${last.id} · ${formatDate(last.data)}` : "Nenhuma"}</dd>
              </div>
            </dl>
            <p class="management-note"
              >Totais do perfil; não recalculados a partir dos pedidos.</p
            >`;
  }
  if (selectedClientTab === "conversas") {
    h = cv.length
      ? /* HTML */ `<ul class="management-list">
                ${cv
                  .map((x) =>
                    li(
                      /* HTML */ `<b>${channelLabel(x.canal)}</b> · ${statusLabel(x.status)}`,
                      escapeHtml(lastMessage(x).slice(0, 80)),
                      /* HTML */ `<button
                          class="management-button sm"
                          data-client-conversation="${x.id}"
                        >
                          Abrir
                        </button>`,
                    ),
                  )
                  .join("")}
              </ul>`
      : emptyMarkup("Sem conversa vinculada", "As conversas do cliente aparecem aqui.");
  }
  if (selectedClientTab === "compras") {
    h = rel.length
      ? /* HTML */ `<ul class="management-list">
                ${rel
                  .map((v) =>
                    li(
                      /* HTML */ `<button class="lk" data-record-open="sales" data-record-id="${v.id}">
                          Venda #${v.id}
                        </button>`,
                      `${formatDate(v.data)} · ${escapeHtml(v.status)}${v.item ? " · " + escapeHtml(v.item) : ""}`,
                      /* HTML */ `<b class="management-numeric-value">${money(v.valor)}</b>`,
                    ),
                  )
                  .join("")}
              </ul>`
      : emptyMarkup("Sem compras vinculadas", "Registre uma venda para este cliente.");
  }
  if (selectedClientTab === "financeiro") {
    h = fin.length
      ? /* HTML */ `<ul class="management-list">
                ${fin
                  .map((x) =>
                    li(
                      /* HTML */ `<button
                          class="lk"
                          data-record-open="finance"
                          data-record-id="${x.id}"
                        >
                          ${escapeHtml(x.descricao)}
                        </button>`,
                      `${formatDate(x.vencimento)} · ${financeStatusLabel(ledgerStatus(x), x.tipo)}`,
                      /* HTML */ `<b class="management-numeric-value">${money(x.valor)}</b>`,
                    ),
                  )
                  .join("")}
              </ul>`
      : emptyMarkup(
          "Sem lançamentos vinculados",
          "As movimentações com este cliente aparecem aqui.",
        );
  }
  if (selectedClientTab === "notas") {
    h = /* HTML */ `<label class="filter-label" for="clientObservation"
              >Observações<textarea
                class="details-note"
                id="clientObservation"
                data-client-note="${c.id}"
              >
${escapeHtml(c.observacao || "")}</textarea>
            </label>
            <p class="management-note">Salvo neste navegador ao sair do campo.</p>`;
  }
  $("clientModalBody").innerHTML = /* HTML */ `<div class="management-detail-heading">
            <span class="av">${escapeHtml(getContactInitials(c.nome))}</span>
            <div>
              <h3>${escapeHtml(c.nome)}</h3>
              <span class="management-tags"
                ><span
                  class="pill ${c.status === "Ativo" ? "green" : c.status === "Novo" ? "amber" : "draft"}"
                  >${escapeHtml(c.status || "Novo")}</span
                >${(c.tags || []).map((t) => /* HTML */ `<span class="pill draft">${escapeHtml(t)}</span>`).join("")}</span
              >
            </div>
          </div>
          <div class="management-drawer-footer">
            ${
              cv[0]
                ? /* HTML */ `<button
                    class="management-button pr"
                    data-client-conversation="${cv[0].id}"
                  >
                    Abrir conversa
                  </button>`
                : '<button class="management-button" disabled>Sem conversa vinculada</button>'
            }<button
              class="management-button"
              data-create-sale-client="${c.id}"
            >
              Nova venda
            </button>
          </div>
          <div class="management-tabs sm" role="tablist" aria-label="Informações do cliente">
            ${[
              ["resumo", "Resumo"],
              ["conversas", "Conversas"],
              ["compras", "Compras"],
              ["financeiro", "Financeiro"],
              ["notas", "Notas"],
            ]
              .map(
                ([i, l]) => /* HTML */ `<button
                    role="tab"
                    id="clientTab-${i}"
                    data-client-tab="${i}"
                    aria-selected="${selectedClientTab === i}"
                    aria-controls="clientPanel"
                    tabindex="${selectedClientTab === i ? 0 : -1}"
                    ${selectedClientTab === i ? 'style="box-shadow:inset 0 -2px var(--brand-primary)"' : ""}
                  >
                    ${l}
                  </button>`,
              )
              .join("")}
          </div>
          <section
            id="clientPanel"
            role="tabpanel"
            aria-labelledby="clientTab-${selectedClientTab}"
          >
            ${h}
          </section>`;
}
function getProductUnitsSold(product) {
  return appData.vendas.filter(
    (sale) =>
      !["Cancelado", "Rascunho"].includes(sale.status) &&
      sale.item &&
      SocialMEISales.matchesProduct(sale, product),
  ).length;
}
function renderProducts() {
  const searchQuery = normalizedText($("productsSearch").value.trim());
  const type = $("productsTypeFilter").value;
  const all = appData.produtos;
  const isLow = (p) => p.tipo === "Produto" && p.estoque <= p.minimo;
  const low = all.filter(isLow);
  const best = Math.max(0, ...all.map(getProductUnitsSold));
  const rows = all.filter(
    (p) =>
      (!searchQuery || normalizedText(p.nome).includes(searchQuery)) &&
      (type === "all" || p.tipo === type) &&
      (!isCatalogLowStockOnly || isLow(p)),
  );
  $("catalogIntro").innerHTML = /* HTML */ `<span class="catalog-lead"
            ><b>${all.length}</b> ${all.length === 1 ? "item" : "itens"} no catálogo</span
          ><span class="management-note catalog-split"
            >${plural(all.filter((p) => p.tipo === "Produto").length, "produto", "produtos")} ·
            ${plural(all.filter((p) => p.tipo === "Serviço").length, "serviço", "serviços")}</span
          ><button
            type="button"
            class="management-chip"
            data-catalog-low
            aria-pressed="${isCatalogLowStockOnly}"
          >
            Estoque baixo<b>${low.length}</b></button
          >`;
  $("nvPv").textContent = productDisplayMode === "grid" ? "Ver em tabela" : "Ver em cards";
  $("nvPv").dataset.nvPv = productDisplayMode === "grid" ? "table" : "grid";
  const tag = (p) => {
    const n = getProductUnitsSold(p);
    return n && n === best ? '<span class="pill green">Mais vendido</span>' : "";
  };
  const stock = (p) =>
    p.tipo === "Produto"
      ? isLow(p)
        ? /* HTML */ `<span class="pill red">Estoque baixo · ${p.estoque}</span>`
        : /* HTML */ `<span class="management-note">Estoque ${p.estoque}</span>`
      : '<span class="management-note">Sem estoque</span>';
  $("productsGrid").innerHTML = !all.length
    ? emptyMarkup(
        "Nenhum produto ou serviço ainda",
        "Cadastre o que você vende para registrar vendas mais rápido.",
        '<button class="management-button pr" data-create="produto">Cadastrar primeiro produto</button>',
      )
    : !rows.length
      ? emptyMarkup(
          "Nenhum item nesta seleção",
          "Ajuste a busca ou a categoria.",
          clearFilterAction("products"),
        )
      : productDisplayMode === "grid"
        ? /* HTML */ `<div class="management-pagination">
                  ${rows
                    .map(
                      (
                        p,
                      ) => /* HTML */ `<article class="management-product-card" data-product-kind="${escapeHtml(p.tipo)}">
                          <div class="catalog-card-top">
                            <span class="catalog-product-icon" aria-hidden="true">${renderIcon(p.tipo === "Serviço" ? "note" : "box")}</span>
                            <span class="catalog-kind">${escapeHtml(p.tipo)}</span>${tag(p)}
                          </div>
                          <button
                            class="row-action"
                            type="button"
                            data-record-open="products"
                            data-record-id="${p.id}"
                          >
                            ${escapeHtml(p.nome)}</button
                          ><b class="management-metric-value management-numeric-value catalog-price"
                            >${money(p.preco)}</b
                          ><div class="catalog-card-foot"
                            ><span class="management-note"
                              >${plural(getProductUnitsSold(p), "venda", "vendas")}</span
                            >${stock(p)}</div
                          >
                        </article>`,
                    )
                    .join("")}
                </div>`
        : /* HTML */ `<div class="management-table-wrapper">
                  <table class="management-table">
                    <caption class="sr-only"> Produtos e serviços </caption>
                    <thead>
                      <tr>
                        <th scope="col">Nome</th>
                        <th scope="col">Categoria</th>
                        <th scope="col" class="r">Preço</th>
                        <th scope="col">Vendas</th>
                        <th scope="col">Estoque</th>
                        <th scope="col"><span class="sr-only">Ações</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      ${rows
                        .map(
                          (p) => /* HTML */ `<tr>
                              <td data-l="Cliente">
                                <div class="management-contact" data-product-kind="${escapeHtml(p.tipo)}">
                                  <span class="catalog-product-icon" aria-hidden="true">${renderIcon(p.tipo === "Serviço" ? "note" : "box")}</span>
                                  <div>
                                    <button
                                      class="row-action"
                                      type="button"
                                      data-record-open="products"
                                      data-record-id="${p.id}"
                                    >
                                      ${escapeHtml(p.nome)}
                                    </button>
                                    ${tag(p)}
                                  </div>
                                </div>
                              </td>
                              <td data-l="Categoria">${escapeHtml(p.tipo)}</td>
                              <td data-l="Valor" class="r management-numeric-value"
                                >${money(p.preco)}</td
                              >
                              <td data-l="Vendas">${getProductUnitsSold(p)}</td>
                              <td data-l="Estoque">${stock(p)}</td>
                              <td class="act">
                                <button
                                  class="management-button sm"
                                  data-record-open="products"
                                  data-record-id="${p.id}"
                                >
                                  Abrir
                                </button>
                              </td>
                            </tr>`,
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`;
  tableMeta("products", rows.length);
  updateFilterIndicators("products");
  syncManagementSelect("productsTypeFilter");
}
function renderFinance() {
  const metrics = operationalMetrics();
  const all = operationalMetrics({
    from: "0000-01-01",
    to: "9999-12-31",
  });
  const bal = operationalMetrics({
    from: "0000-01-01",
    to: todayISO(),
  }).balance;
  const today = todayISO();
  const wk = dateShift(today, 6);
  const late = all.receivables.concat(all.payables).filter((x) => ledgerStatus(x) === "atrasado");
  $("financeSummary").innerHTML = /* HTML */ `<article class="management-kpi">
            <span>Saldo dos lançamentos pagos</span
            ><b class="${bal < 0 ? "neg" : ""}">${money(bal)}</b
            ><small class="management-note">Não representa o saldo bancário.</small>
          </article>
          <article class="management-kpi">
            <span>Entrou</span><b>${money(metrics.received)}</b
            ><small class="management-metric-change">${rangeCaption(periodRange())}</small>
          </article>
          <article class="management-kpi">
            <span>Saiu</span><b>${money(metrics.spent)}</b
            ><small class="management-metric-change">${rangeCaption(periodRange())}</small>
          </article>
          <article class="management-kpi">
            <span>A receber</span><b>${money(all.receivable)}</b
            ><small class="management-metric-change"
              >${plural(all.receivables.length, "lançamento", "lançamentos")} em aberto</small
            >
          </article>
          <article class="management-kpi">
            <span>A pagar</span><b>${money(all.payable)}</b
            ><small
              class="management-metric-change ${late.some((x) => x.tipo === "despesa") ? "dn" : ""}"
              >${plural(all.payables.length, "lançamento", "lançamentos")} em aberto</small
            >
          </article>`;
  $("financeMiniChart").innerHTML = renderManagementChartMarkup();
  const searchQuery = normalizedText($("financeSearch").value.trim());
  const ty = $("financeTypeFilter").value;
  const st = $("financeStatusFilter").value;
  const rows = appData.financeiro.filter(
    (entry) =>
      (entry.status !== "pago" || inRange(entry.vencimento)) &&
      (!searchQuery ||
        normalizedText(entry.descricao + " " + entry.pessoa).includes(searchQuery)) &&
      (ty === "all" || entry.tipo === ty) &&
      (st === "all" || ledgerStatus(entry) === st),
  );
  const G = [
    ["Atrasados", rows.filter((x) => ledgerStatus(x) === "atrasado"), 1],
    ["Esta semana", rows.filter((x) => ledgerStatus(x) === "aberto" && x.vencimento <= wk)],
    ["Próximos", rows.filter((x) => ledgerStatus(x) === "aberto" && x.vencimento > wk)],
    ["Pagos no período", rows.filter((x) => x.status === "pago")],
  ];
  const row = (x) => {
    const s = ledgerStatus(x);
    const d = Math.round((new Date(today) - new Date(x.vencimento)) / 864e5);
    return /* HTML */ `<li class="management-ledger-row" data-due="${s}">
            <span
              class="management-directory ${x.tipo === "despesa" ? "out" : ""}"
              aria-hidden="true"
              >${x.tipo === "receita" ? "+" : "−"}</span
            >
            <div>
              <button
                class="row-action"
                type="button"
                data-record-open="finance"
                data-record-id="${x.id}"
              >
                ${escapeHtml(x.descricao)}</button
              ><small
                >${escapeHtml(x.pessoa || "Sem pessoa vinculada")} ·
                ${s === "atrasado" ? `venceu ${formatDate(x.vencimento)} (há ${d} ${d === 1 ? "dia" : "dias"})` : formatDate(x.vencimento)}</small
              >
            </div>
            <span class="pill ${financeStatusClass(s)}">${financeStatusLabel(s, x.tipo)}</span
            ><b class="management-numeric-value ${x.tipo === "receita" ? "in" : "out"}"
              >${x.tipo === "receita" ? "+" : "−"} ${money(x.valor)}</b
            >${
              x.status !== "pago"
                ? /* HTML */ `<button
                      class="management-button sm"
                      type="button"
                      data-finance-paid="${x.id}"
                    >
                      ${x.tipo === "receita" ? "Marcar recebido" : "Marcar pago"}
                    </button>`
                : "<span></span>"
            }
          </li>`;
  };
  $("financeTable").innerHTML = rows.length
    ? G.filter((g) => g[1].length)
        .map(
          ([n, l, lt]) => /* HTML */ `<div class="management-group-label ${lt ? "late" : ""}">
                      ${n}<span class="management-note">${l.length}</span>
                    </div>
                    <ul class="management-list">
                      ${l
                        .sort((a, b) =>
                          n === "Pagos no período"
                            ? b.vencimento.localeCompare(a.vencimento)
                            : a.vencimento.localeCompare(b.vencimento),
                        )
                        .map(row)
                        .join("")}
                    </ul>`,
        )
        .join("")
    : emptyMarkup(
        "Nenhuma movimentação encontrada",
        "Ajuste os filtros ou o período.",
        clearFilterAction("finance") +
          '<button class="management-button pr" data-create="receita">+ Entrada</button>',
      );
  tableMeta("finance", rows.length);
  updatePeriodCaptions();
  updateFilterIndicators("finance");
  ["financeTypeFilter", "financeStatusFilter"].forEach(syncManagementSelect);
}
document.addEventListener("click", (event) => {
  const t = event.target;
  const tab = t.closest("[data-nv-tab]");
  if (tab) {
    setView(tab.dataset.nvTab);
    return;
  }
  const o = t.closest(".management-select li");
  if (o) {
    selectManagementOption(o.closest(".management-select"), o.dataset.v);
    return;
  }
  const b = t.closest(".management-select>button");
  document.querySelectorAll(".management-select>button[aria-expanded=true]").forEach((x) => {
    if (x !== b) {
      closeManagementSelect(x);
    }
  });
  if (b) {
    b.getAttribute("aria-expanded") === "true" ? closeManagementSelect(b) : openManagementSelect(b);
    return;
  }
  const pv = t.closest("[data-nv-pv]");
  if (pv) {
    productDisplayMode = pv.dataset.nvPv;
    renderProducts();
  }
});
document.addEventListener(
  "keydown",
  (event) => {
    const tab = event.target.closest?.("[data-nv-tab]");
    if (tab && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const i = MANAGEMENT_VIEWS.indexOf(tab.dataset.nvTab);
      const n =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? 4
            : (i + (event.key === "ArrowRight" ? 1 : 4)) % 5;
      setView(MANAGEMENT_VIEWS[n]);
      $("nvTabs").children[n + 1].focus();
      return;
    }
    const sel = event.target.closest?.(".management-select");
    if (!sel) {
      return;
    }
    const button = sel.querySelector("button");
    const options = [...sel.querySelectorAll("li")];
    if (event.target === button && ["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      openManagementSelect(button);
      return;
    }
    if (event.target.matches("li")) {
      const i = options.indexOf(event.target);
      if (event.key === "ArrowDown") {
        event.preventDefault();
        options[Math.min(i + 1, options.length - 1)].focus();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        options[Math.max(i - 1, 0)].focus();
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectManagementOption(sel, event.target.dataset.v);
      } else if (event.key === "Escape" || event.key === "Tab") {
        if (event.key === "Escape") {
          event.stopPropagation();
        }
        closeManagementSelect(button, event.key === "Escape");
      }
    }
  },
  true,
);
window.addEventListener("hashchange", () => {
  const m = location.hash.match(/^#negocio\/(\w+)/);
  if (!m || !document.body.classList.contains("experience-app")) {
    return;
  }
  const t = MANAGEMENT_TABS.find((x) => x[2] === m[1]);
  if (t && t[0] !== currentView) {
    setView(t[0]);
  }
});
window.addEventListener("resize", () => {
  if (isManagementViewActive()) {
    positionManagementTabIndicator();
  }
});
["salesPaymentFilter", "clientsTypeFilter", "clientsTagFilter"].forEach((id) =>
  document.getElementById(id).addEventListener("change", () =>
    ({
      salesPaymentFilter: renderSales,
      clientsTypeFilter: renderClients,
      clientsTagFilter: renderClients,
    })[id](),
  ),
);
