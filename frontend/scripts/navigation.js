/* NAVIGATION */
let isSidebarCompact = false;
let sidebarFrame = 0;
try {
  isSidebarCompact = localStorage.getItem("socialmei-sidebar-compact-v2") === "1";
} catch (error) {}
function positionSidebarIndicator() {
  cancelAnimationFrame(sidebarFrame);
  sidebarFrame = requestAnimationFrame(() => {
    sidebarFrame = 0;
    const nav = $("nav");
    const indicator = nav?.querySelector(".nav-indicator");
    let active = nav?.querySelector("[aria-current=page]");
    if (active?.closest(".business-nav-items.collapsed")) {
      active = $("businessNavToggle");
    }
    if (!indicator) {
      return;
    }
    indicator.style.opacity = active ? "1" : "0";
    if (active) {
      const box = active.getBoundingClientRect();
      const origin = nav.getBoundingClientRect();
      indicator.style.height = box.height + "px";
      indicator.style.transform = `translateY(${box.top - origin.top + nav.scrollTop}px)`;
    }
  });
}
function applySidebarState() {
  const desktop = innerWidth > 900;
  $("app").classList.toggle("sb-mini", desktop && isSidebarCompact);
  hideSidebarTooltip();
  const label = desktop
    ? isSidebarCompact
      ? "Expandir menu"
      : "Recolher menu"
    : "Fechar navegação";
  $("sbCollapse").setAttribute("aria-label", label);
  $("sbCollapse").title = label;
  $("sbCollapse").setAttribute(
    "aria-expanded",
    String(desktop ? !isSidebarCompact : $("sb").classList.contains("open")),
  );
  $("sbCollapse").innerHTML = renderIcon(isSidebarCompact ? "panelOpen" : "panel");
  positionSidebarIndicator();
}
function closeMobileMenu() {
  const wasOpen = $("sb").classList.contains("open");
  $("sb").classList.remove("open");
  $("mb").setAttribute("aria-expanded", "false");
  syncShellInert();
  if (wasOpen) {
    $("mb").focus();
  }
}
function renderPeriodMenu() {
  const options = [
    "Hoje",
    "7 dias",
    "30 dias",
    "Este mês",
    "3 meses",
    "6 meses",
    "12 meses",
    "Personalizado",
  ];
  $("pm").innerHTML =
    options
      .map(
        (p) => /* HTML */ `<button
                  class="period-option"
                  role="menuitemradio"
                  aria-checked="${p === selectedPeriod}"
                  data-period="${p}"
                >
                  <span>${p}</span><span class="check">${renderIcon("check")}</span>
                </button>`,
      )
      .join("") +
    /* HTML */ `<div class="custom-box" id="customBox">
            <div class="custom-grid">
              <div><label for="dateFrom">De</label><input id="dateFrom" type="date" /></div>
              <div><label for="dateTo">Até</label><input id="dateTo" type="date" /></div>
            </div>
            <div class="custom-actions">
              <button class="btn" id="cancelCustom" type="button">Cancelar</button>
              <button class="btn pr" id="applyCustom" type="button">Aplicar</button>
            </div>
          </div>`;
  updatePeriodLabel();
}
function updatePeriodLabel() {
  $("pl").textContent =
    selectedPeriod === "Personalizado" && customRange ? customRange.label : selectedPeriod;
  $("pm")
    .querySelectorAll("[data-period]")
    .forEach((b) => b.setAttribute("aria-checked", String(b.dataset.period === selectedPeriod)));
  updatePeriodCaptions();
}
function renderHeader() {
  const h = Number(
    new Intl.DateTimeFormat("en-US", {
      timeZone: APP_TIMEZONE,
      hour: "numeric",
      hourCycle: "h23",
    }).format(new Date()),
  );
  $("gr").textContent =
    `${h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite"}, ${sessionData.usuario.primeiro}. ${capitalizeText(
      new Date().toLocaleDateString("pt-BR", {
        timeZone: APP_TIMEZONE,
        weekday: "long",
        day: "numeric",
        month: "long",
      }),
    )}`;
  $("av").textContent = sessionData.usuario.iniciais;
  $("un").textContent = sessionData.usuario.nome;
  $("mb").innerHTML = renderIcon("menu");
  $("refresh").innerHTML = renderIcon("refresh");
  if ($("globalSearchBtn")) {
    $("globalSearchBtn").innerHTML = renderIcon("search");
  }
  $("bell").innerHTML = renderIcon("bell") + '<span class="notify-dot" id="notifyDot"></span>';
  $("periodChevron").innerHTML = renderIcon("down");
  $("profileChevron").innerHTML = renderIcon("down");
  $("profileDd").querySelector('[data-profile-action="perfil"]').innerHTML =
    renderIcon("user") + "Meu perfil";
  $("profileDd").querySelector('[data-profile-action="config"]').innerHTML =
    renderIcon("cfg") + "Configurações";
  $("profileDd").querySelector('[data-profile-action="sair"]').innerHTML =
    renderIcon("logout") + '<span class="account-exit-label">Sair da conta</span>';
  const accountIdentity = SocialMEIAuth.current;
  $("profileMenuEmail").textContent = accountIdentity?.usuario.email || "Perfil deste navegador";
  $("profileMenuRole").textContent = accountIdentity
    ? accountIdentity.usuario.administrador_plataforma
      ? "Administrador do projeto"
      : "Conta do seu negócio"
    : "Demonstração local";
  $("profileAdminLink").hidden = !accountIdentity?.usuario.administrador_plataforma;
  $("profileAdminLink").href = "/frontend/admin.html";
  renderPeriodMenu();
  renderNotifications();
}
function notificationMeta(n) {
  const text = (n.t + " " + n.s).toLowerCase();
  if (text.includes("mensagem") || text.includes("whatsapp") || text.includes("instagram")) {
    return {
      label: "Atendimento",
      go: "Caixa Unificada",
    };
  }
  if (text.includes("estoque") || text.includes("produto")) {
    return {
      label: "Estoque",
      go: "Produtos e Serviços",
    };
  }
  if (text.includes("venda")) {
    return {
      label: "Vendas",
      go: "Vendas",
    };
  }
  return {
    label: "Financeiro",
    go: "Financeiro",
  };
}
function renderNotifications() {
  const list = sessionData.notificacoes;
  if (!list.length) {
    $("notList").innerHTML =
      '<li style="display:block"><div class="empty" style="padding:14px"><b>Sem notificações</b><span>Você está em dia.</span></div></li>';
    $("notifyDot").style.display = "none";
    return;
  }
  $("notifyDot").style.display = "";
  $("notList").innerHTML = list
    .map((n) => {
      const m = notificationMeta(n);
      return /* HTML */ `<li style="grid-template-columns:8px 1fr auto">
              <span class="ndot"></span>
              <div>
                <span class="pill" style="margin-bottom:4px">${m.label}</span
                ><b>${escapeHtml(n.t)}</b><span>${escapeHtml(n.s)}</span>
              </div>
              <button class="lk" data-go="${m.go}">Ver</button>
            </li>`;
    })
    .join("");
}
function setView(name, options = {}) {
  const changed = currentView !== name;
  const openInboxAsList = name === "Caixa Unificada" && options.preserveConversation !== true;
  if (changed || openInboxAsList) {
    saveCurrentDraft();
    cancelConversationTransition();
    closeMobileDetails();
  }
  if (openInboxAsList) {
    isInboxListMode = true;
    activeConversationId = null;
  }
  currentView = name;
  document.body.classList.toggle("inbox-active", name === "Caixa Unificada");
  closeInboxPopovers();
  queueInboxLayout();
  document
    .querySelectorAll(".page-view")
    .forEach((v) => v.classList.toggle("active", v.dataset.view === name));
  const titles = {
    Início: "Início",
    "Meu negócio": "Meu negócio",
    "Visão Geral": "Visão do negócio",
    Financeiro: "Financeiro",
    Vendas: "Vendas",
    Clientes: "Clientes",
    "Produtos e Serviços": "Produtos e serviços",
    "Caixa Unificada": "Caixa Unificada",
    Automações: "Automações",
    Assistente: "Assistente",
    Relatórios: "Relatórios",
    Configurações: "Configurações",
  };
  document.querySelector(".hd-title h1").textContent = titles[name] || name;
  const periodViews = ["Visão Geral", "Meu negócio", "Financeiro", "Vendas", "Relatórios"];
  $("per").style.display = periodViews.includes(name) ? "" : "none";
  $("refresh").style.display = name === "Visão Geral" ? "" : "none";
  document
    .querySelectorAll("#nav a")
    .forEach((a) => a.toggleAttribute("aria-current", a.dataset.nav === name));
  renderCurrentView();
  window.SocialMEIExperience?.refreshTools?.();
  window.SocialMEIMotion.enterView(document.querySelector(".page-view.active"));
  updateHeaderContext();
  const activeNav = $("nav").querySelector("[aria-current=page]");
  if (activeNav && !activeNav.closest(".collapsed")) {
    const rect = activeNav.getBoundingClientRect();
    const bounds = $("nav").getBoundingClientRect();
    if (rect.top < bounds.top) {
      $("nav").scrollTop += rect.top - bounds.top - 4;
    } else if (rect.bottom > bounds.bottom) {
      $("nav").scrollTop += rect.bottom - bounds.bottom + 4;
    }
  }
  positionSidebarIndicator();
  if (changed) {
    window.scrollTo({
      top: 0,
      behavior: "instant",
    });
  }
  if (name === "Caixa Unificada") {
    if (options.channel && $("channelFilter")) {
      $("channelFilter").value = options.channel;
      renderConversationList();
    }
    applyInboxDisplayMode({
      animate: !changed || openInboxAsList,
      focusList: false,
    });
  }
  if (innerWidth <= 900) {
    closeMobileMenu();
  }
  try {
    if (document.body.classList.contains("experience-app")) {
      sessionStorage.setItem("socialmei-current-view", name);
    }
  } catch (_) {}
  document.dispatchEvent(new CustomEvent("socialmei-view-change"));
}
function updateInboxNavBadge() {
  document.dispatchEvent(new CustomEvent("socialmei-data-change"));
  const totalUnread = sessionData.conversas.reduce(
    (conversation, c) => conversation + c.naoLidas,
    0,
  );
  const nav = document.querySelector('#nav [data-nav="Caixa Unificada"]');
  if (!nav) {
    return;
  }
  let badge = nav.querySelector("em");
  if (!badge) {
    badge = document.createElement("em");
    nav.appendChild(badge);
  }
  badge.textContent = String(totalUnread);
  badge.style.display = totalUnread ? "" : "none";
  updateInboxCounts();
}
function businessLinks() {
  return [
    ["Financeiro", "wallet"],
    ["Vendas", "bag"],
    ["Clientes", "users"],
    ["Produtos e Serviços", "box"],
  ]
    .map(
      ([name, icon]) => /* HTML */ `<a
                class="nav-chapter"
                href="#${normalizedText(name).replaceAll(" ", "-")}"
                data-nav="${name}"
                aria-label="${name}"
                ><span class="nav-index">${renderIcon(icon)}</span
                ><span
                  ><b>${name === "Produtos e Serviços" ? "Produtos e serviços" : name}</b></span
                ></a
              >`,
    )
    .join("");
}
