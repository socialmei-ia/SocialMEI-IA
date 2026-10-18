/* DIALOGS */
function closeRowMenu(returnFocus = false) {
  $("rowMenu").hidden = true;
  if (rowMenuAnchor) {
    rowMenuAnchor.setAttribute("aria-expanded", "false");
    if (returnFocus && rowMenuAnchor.isConnected) {
      rowMenuAnchor.focus();
    }
  }
  rowMenuAnchor = null;
}
function openRowMenu(button) {
  if (rowMenuAnchor === button) {
    closeRowMenu(true);
    return;
  }
  closeRowMenu();
  rowMenuAnchor = button;
  let content = "";
  const id = Number(button.dataset.rowId);
  if (button.dataset.rowMenu === "finance") {
    const x = appData.financeiro.find((entry) => entry.id === id);
    if (x) {
      content =
        x.status === "pago"
          ? '<button role="menuitem" type="button" disabled>Movimentação regularizada</button>'
          : /* HTML */ `<button role="menuitem" type="button" data-finance-paid="${id}">
                    ${x.tipo === "receita" ? "Marcar como recebido" : "Marcar como pago"}
                  </button>`;
    }
  }
  if (button.dataset.rowMenu === "sales") {
    const v = appData.vendas.find((sale) => sale.id === id);
    if (v) {
      content = /* HTML */ `${!["Pago", "Cancelado"].includes(v.status) ? /* HTML */ `<button role="menuitem" type="button" data-sale-paid="${id}">Marcar como paga</button>` : ""}<button
                role="menuitem"
                type="button"
                data-sale-duplicate="${id}"
              >
                Duplicar como rascunho</button
              ><button
                role="menuitem"
                type="button"
                data-open-client-name="${escapeHtml(v.cliente)}"
              >
                Ver cliente
              </button>`;
    }
  }
  if (button.dataset.rowMenu === "clients") {
    content = /* HTML */ `<button role="menuitem" type="button" data-open-client="${id}">
              Ver perfil do cliente</button
            ><button role="menuitem" type="button" data-create-sale-client="${id}"
              >Criar venda</button
            >`;
  }
  const menu = $("rowMenu");
  menu.innerHTML = content;
  menu.hidden = false;
  button.setAttribute("aria-expanded", "true");
  const r = button.getBoundingClientRect();
  menu.style.left =
    Math.max(8, Math.min(innerWidth - menu.offsetWidth - 8, r.right - menu.offsetWidth)) + "px";
  menu.style.top = Math.max(8, Math.min(innerHeight - menu.offsetHeight - 8, r.bottom + 5)) + "px";
  menu.querySelector("button:not(:disabled)")?.focus();
}
const NATIVE_INERT = "inert" in HTMLElement.prototype;
const INERT_FOCUSABLE = 'a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])';
function setAccessibleInert(element, inert) {
  if (!element) {
    return;
  }
  if (NATIVE_INERT) {
    element.inert = !!inert;
    return;
  }
  if (inert) {
    if (!element.hasAttribute("data-inert-aria-hidden")) {
      element.setAttribute("data-inert-aria-hidden", element.getAttribute("aria-hidden") ?? "");
    }
    element.setAttribute("aria-hidden", "true");
  } else if (element.hasAttribute("data-inert-aria-hidden")) {
    const previous = element.getAttribute("data-inert-aria-hidden");
    element.removeAttribute("data-inert-aria-hidden");
    if (previous === "") {
      element.removeAttribute("aria-hidden");
    } else {
      element.setAttribute("aria-hidden", previous);
    }
  }
  element.querySelectorAll(INERT_FOCUSABLE).forEach((node) => {
    if (inert) {
      if (!node.hasAttribute("data-inert-tabindex")) {
        node.setAttribute("data-inert-tabindex", node.getAttribute("tabindex") ?? "");
        node.setAttribute("tabindex", "-1");
      }
    } else if (node.hasAttribute("data-inert-tabindex")) {
      const previous = node.getAttribute("data-inert-tabindex");
      node.removeAttribute("data-inert-tabindex");
      if (previous === "") {
        node.removeAttribute("tabindex");
      } else {
        node.setAttribute("tabindex", previous);
      }
    }
  });
}
function dialogFocusables(dialog) {
  return [...dialog.querySelectorAll(INERT_FOCUSABLE)].filter(
    (element) => !element.disabled && !element.hidden && element.getClientRects().length,
  );
}
function activeModalDialog() {
  const backdrop = [...document.querySelectorAll(".modal-backdrop.open")].at(-1);
  return (
    backdrop?.querySelector('[role="dialog"]') ||
    document.querySelector('#detailsPane.mobile-open[role="dialog"]')
  );
}
function syncShellInert() {
  const modal = [...document.querySelectorAll(".modal-backdrop.open")].at(-1);
  const mobileMenu = innerWidth <= 900 && $("sb").classList.contains("open");
  const context = !!$("detailsPane")?.classList.contains("mobile-open");
  setAccessibleInert($("app"), !!modal);
  document
    .querySelectorAll(".modal-backdrop")
    .forEach((m) => setAccessibleInert(m, !!modal && m !== modal));
  setAccessibleInert($("sb"), context || (innerWidth <= 900 && !mobileMenu));
  setAccessibleInert(document.querySelector(".mn"), mobileMenu && !modal);
  setAccessibleInert(document.querySelector(".hd"), context);
  setAccessibleInert($("businessTabs"), context);
  setAccessibleInert(document.querySelector(".data-origin"), context);
  setAccessibleInert(document.querySelector("#inboxView .list-heading"), context);
  syncMobileInert();
  document.body.classList.toggle("dialog-open", !!modal || mobileMenu || context);
}
document.addEventListener(
  "keydown",
  (event) => {
    if (event.key !== "Tab") {
      return;
    }
    const dialog = activeModalDialog();
    if (!dialog) {
      return;
    }
    const items = dialogFocusables(dialog);
    if (!items.length) {
      event.preventDefault();
      dialog.tabIndex = -1;
      dialog.focus();
      return;
    }
    const first = items[0];
    const last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  },
  true,
);
function openModal(id) {
  const m = $(id);
  if (!m) {
    return;
  }
  m._closeEpoch = (m._closeEpoch || 0) + 1;
  m._closing = false;
  if (!m.classList.contains("open")) {
    m._returnFocus = document.activeElement;
  }
  m.classList.add("open");
  m.setAttribute("aria-hidden", "false");
  syncShellInert();
  requestAnimationFrame(() => {
    const dialog = m.querySelector('[role="dialog"]');
    (dialogFocusables(dialog || m)[0] || dialog)?.focus();
  });
}
/**
 * Fecha o diálogo com proteção contra reabertura e fechamento concorrente. Reutiliza a promessa em andamento.
 * @param {string} id ID do backdrop.
 * @returns {Promise<void>}
 */
function closeModal(id) {
  const m = $(id);
  if (!m || !m.classList.contains("open")) {
    return Promise.resolve();
  }
  if (m._closing) {
    return m._closePromise || Promise.resolve();
  }
  if (id === "reportGenerateModal" && typeof SocialMEIReportUI !== "undefined")
    SocialMEIReportUI.cancelGeneration();
  m._closing = true;
  const epoch = m._closeEpoch;
  const motion = window.SocialMEIMotion;
  const pending = Promise.all([
    motion.animate(
      m,
      [
        {
          opacity: 1,
        },
        {
          opacity: 0,
        },
      ],
      "motion-fast",
      "ease-exit",
    ),
    motion.animate(
      m.querySelector(".modal"),
      [
        {
          transform: "none",
        },
        {
          transform: m.matches(".client-drawer,.record-drawer")
            ? "translateX(24px)"
            : "translateY(8px) scale(.985)",
        },
      ],
      "motion-fast",
      "ease-exit",
    ),
  ])
    .then(() => {
      if (epoch !== m._closeEpoch) {
        return;
      }
      m.classList.remove("open");
      m.setAttribute("aria-hidden", "true");
      syncShellInert();
      if (
        m._returnFocus?.isConnected &&
        !m._returnFocus.closest("[inert]") &&
        m._returnFocus.getClientRects().length
      ) {
        m._returnFocus.focus();
      }
    })
    .finally(() => {
      if (epoch === m._closeEpoch) {
        m._closing = false;
        m._closePromise = null;
      }
    });
  m._closePromise = pending;
  return pending;
}
function createField(label, name, type = "text", options = {}) {
  if (type === "select") {
    return /* HTML */ `<div class="form-group ${options.full ? "full" : ""}">
            <label for="f_${name}">${label}</label
            ><select class="form-control" id="f_${name}" name="${name}">
              ${(options.options || [])
                .map(
                  (o) => /* HTML */ `<option
                        value="${escapeHtml(o)}"
                        ${String(options.value ?? "") === String(o) ? "selected" : ""}
                      >
                        ${escapeHtml(o)}
                      </option>`,
                )
                .join("")}
            </select>
          </div>`;
  }
  if (type === "textarea") {
    return /* HTML */ `<div class="form-group full">
            <label for="f_${name}">${label}</label
            ><textarea
              class="form-control"
              id="f_${name}"
              name="${name}"
              placeholder="${escapeHtml(options.placeholder || "")}"
            >
${escapeHtml(options.value || "")}</textarea>
          </div>`;
  }
  return /* HTML */ `<div class="form-group ${options.full ? "full" : ""}">
          <label for="f_${name}">${label}</label
          ><input
            class="form-control"
            id="f_${name}"
            name="${name}"
            type="${type}"
            ${options.step ? `step="${options.step}"` : ""}
            ${options.min != null ? `min="${options.min}"` : ""}
            ${options.max != null ? `max="${options.max}"` : ""}
            value="${escapeHtml(options.value ?? "")}"
            placeholder="${escapeHtml(options.placeholder || "")}"
            ${options.required ? "required" : ""}
          />
        </div>`;
}
function remoteSaleSelect(label, name, rows, selected) {
  const match = Number.isSafeInteger(selected)
    ? rows.filter((r) => r.id === selected)
    : rows.filter((r) => r.nome === selected);
  const id = match.length === 1 ? match[0].id : "";
  return `<div class="form-group full"><label for="f_${name}">${escapeHtml(label)}</label><select class="form-control" id="f_${name}" name="${name}" required><option value="">Selecione um cadastro compartilhado</option>${rows.map((r) => `<option value="${r.id}" ${r.id === id ? "selected" : ""}>${escapeHtml(r.nome)} · #${r.id}</option>`).join("")}</select></div>`;
}
function renderCreateFields(type, preset = {}) {
  const h = $("createFields");
  if (!h) {
    return;
  }
  if (type === "venda") {
    h.innerHTML = /* HTML */ `<h4 class="sale-form-heading">1. Para quem você vendeu?</h4>
            ${createField("Cliente", "cliente", "text", {
              value: preset.cliente || "",
              required: true,
              full: true,
            })}
            <h4 class="sale-form-heading">2. O que foi vendido?</h4>
            ${createField("Produto ou serviço", "item", "text", {
              placeholder: "Nome do item vendido",
              required: true,
              full: true,
            })}${createField("Quantidade", "quantidade", "number", {
              value: 1,
              min: 1,
              required: true,
            })}${createField("Preço por unidade (R$)", "preco", "number", {
              step: "0.01",
              min: 0,
              required: true,
            })}
            <h4 class="sale-form-heading">3. Como será o pagamento?</h4>
            ${createField("Forma de pagamento", "pagamento", "select", {
              options: ["Pix", "Cartão", "Boleto", "Dinheiro"],
            })}${createField("Desconto, se houver (R$)", "desconto", "number", {
              step: "0.01",
              min: 0,
              value: 0,
            })}
            <details class="detail-disclosure full form-group">
              <summary>Adicionar uma observação</summary>
              ${createField("Observação", "observacao", "textarea", {
                placeholder: "Opcional",
              })}
            </details>`;
    if (SocialMEISales.remote) {
      $("f_cliente").closest(".form-group").outerHTML = remoteSaleSelect(
        "Cliente",
        "cliente",
        appData.clientes,
        preset.cliente,
      );
      $("f_item").closest(".form-group").outerHTML = remoteSaleSelect(
        "Produto ou serviço",
        "item",
        appData.produtos,
        preset.item,
      );
      $("f_item").addEventListener("change", () => {
        const product = appData.produtos.find((p) => p.id === Number($("f_item").value));
        if (product) {
          $("f_preco").value = product.preco;
          updateSaleReview();
        }
      });
      $("f_quantidade").step = "1";
    }
  } else if (type === "cliente") {
    h.innerHTML = [
      createField("Nome", "nome", "text", {
        required: true,
        full: true,
      }),
      createField("Telefone", "telefone", "tel", {
        placeholder: "DDD e número",
      }),
      createField("Instagram", "instagram", "text", {
        placeholder: "@usuario",
      }),
      createField("Observação", "observacao", "textarea", {
        placeholder: "Configurações ou contexto importante",
      }),
    ].join("");
  } else if (type === "receita" || type === "despesa") {
    h.innerHTML = [
      createField("Descrição", "descricao", "text", {
        required: true,
        full: true,
      }),
      createField("Cliente ou fornecedor", "pessoa", "text", {
        full: true,
      }),
      createField("Valor (R$)", "valor", "number", {
        step: "0.01",
        min: 0,
        required: true,
      }),
      createField("Vencimento", "vencimento", "date", {
        value: todayISO(),
        required: true,
      }),
      createField("Situação", "status", "select", {
        options: ["aberto", "pago"],
      }),
    ].join("");
    if (SocialMEIFinance.remote) {
      h.insertAdjacentHTML(
        "beforeend",
        `<div class="form-group full"><label for="f_cliente_id">Vincular a um cliente (opcional)</label><select id="f_cliente_id" name="cliente_id"><option value="">Sem vínculo — usar pessoa informada</option>${appData.clientes.map((c) => `<option value="${c.id}">${escapeHtml(c.nome)} · #${c.id}</option>`).join("")}</select></div><p class="management-note full">Selecionar um cliente usa o nome desse cadastro. Pagamentos de vendas são registrados separadamente.</p>`,
      );
    }
  } else {
    h.innerHTML = [
      createField("Nome", "nome", "text", {
        value: preset.nome || "",
        required: true,
        full: true,
      }),
      createField("Tipo", "tipo", "select", {
        options: ["Produto", "Serviço"],
      }),
      createField("Preço de venda (R$)", "preco", "number", {
        step: "any",
        min: 0,
        max: 9999999999999.99,
        required: true,
      }),
      createField("Custo informado (R$)", "custo", "number", {
        step: "any",
        min: 0,
        max: 9999999999999.99,
        value: 0,
      }),
      createField("Estoque atual", "estoque", "number", {
        min: 0,
        value: 0,
      }),
      createField("Estoque mínimo", "minimo", "number", {
        min: 0,
        value: 0,
      }),
    ].join("");
  }
  if (type === "receita" || type === "despesa") {
    $("f_status").innerHTML = /* HTML */ `<option value="aberto">Em aberto</option>
            <option value="pago">${type === "receita" ? "Recebido" : "Pago"}</option>`;
  }
  updateSaleReview();
}
function openCreate(type = "venda", preset = {}) {
  $("createType").value = type;
  $("createModalTitle").textContent =
    {
      venda: "Nova venda",
      cliente: "Novo cliente",
      receita: "Registrar receita",
      despesa: "Registrar despesa",
      produto: "Novo produto ou serviço",
    }[type] || "Criar";
  renderCreateFields(type, preset);
  if (type === "produto" && ["Produto", "Serviço"].includes(preset.tipo))
    $("f_tipo").value = preset.tipo;
  toggleProductInventory();
  openModal("createModal");
}
async function handleCreate(data) {
  if (!validateRequiredFormText($("createForm"))) {
    return;
  }
  const modalEpoch = $("createModal")._closeEpoch;
  if ($("createType").value === "cliente" && SocialMEIClients.remote) {
    const saved = await SocialMEIClients.create({
      nome: data.nome.trim(),
      telefone: data.telefone || "—",
      instagram: data.instagram || "—",
      status: "Novo",
      ultima: "Agora",
      total: 0,
      pendente: 0,
      observacao: data.observacao || "",
      tags: ["Novo cliente"],
    });
    if (saved) {
      if ($("createModal")._closeEpoch === modalEpoch) {
        closeModal("createModal");
      }
      toast("Cliente criado", "Salvo na API compartilhada.");
    }
    return;
  }
  if ($("createType").value === "produto" && SocialMEIProducts.remote) {
    const service = data.tipo === "Serviço";
    const saved = await SocialMEIProducts.create({
      nome: data.nome.trim(),
      tipo: data.tipo || "Produto",
      preco: Number(data.preco),
      custo: Number(data.custo) || 0,
      estoque: service ? null : Number(data.estoque) || 0,
      minimo: service ? null : Number(data.minimo) || 0,
      status: "Ativo",
    });
    if (saved) {
      if ($("createModal")._closeEpoch === modalEpoch) {
        closeModal("createModal");
      }
      toast("Item criado", "Salvo na API compartilhada.");
    }
    return;
  }
  if ($("createType").value === "venda" && SocialMEISales.remote) {
    const saved = await SocialMEISales.create({
      cliente_id: Number(data.cliente),
      produto_id: Number(data.item),
      data: todayISO(),
      quantidade: Number(data.quantidade),
      preco: Number(data.preco),
      desconto: Number(data.desconto) || 0,
      pagamento: data.pagamento || "Pix",
      observacao: data.observacao || "",
      status: "Pendente",
    });
    if (saved) {
      if ($("createModal")._closeEpoch === modalEpoch) {
        closeModal("createModal");
      }
      toast("Venda registrada", "Venda e estoque salvos na API.");
    }
    return;
  }
  if (["receita", "despesa"].includes($("createType").value) && SocialMEIFinance.remote) {
    const saved = await SocialMEIFinance.create({
      descricao: data.descricao.trim(),
      pessoa: data.pessoa || "",
      tipo: $("createType").value,
      valor: Number(data.valor),
      vencimento: data.vencimento,
      status: data.status === "pago" ? "pago" : "aberto",
      cliente_id: data.cliente_id ? Number(data.cliente_id) : null,
    });
    if (saved) {
      if ($("createModal")._closeEpoch === modalEpoch) {
        closeModal("createModal");
      }
      toast("Lançamento registrado", "Salvo no Financeiro compartilhado.");
    }
    return;
  }
  const previous = cloneData(appData);
  const activity = cloneData(sessionData.atividade);
  const type = $("createType").value;
  if (type === "venda") {
    const next = Math.max(1000, ...appData.vendas.map((sale) => sale.id)) + 1;
    const total = Math.max(
      0,
      (Number(data.preco) || 0) * (Number(data.quantidade) || 1) - (Number(data.desconto) || 0),
    );
    appData.vendas.unshift({
      id: next,
      cliente: data.cliente.trim(),
      data: todayISO(),
      valor: total,
      pagamento: data.pagamento || "Pix",
      status: "Pendente",
      item: data.item,
      quantidade: Number(data.quantidade) || 1,
      preco: Number(data.preco) || 0,
      desconto: Number(data.desconto) || 0,
      observacao: data.observacao || "",
    });
    sessionData.atividade.unshift({
      t: "sale",
      a: `Venda #${next}`,
      b: `${data.cliente} · ${data.pagamento || "Pix"}`,
      v: total,
      w: "agora",
    });
  } else if (type === "cliente") {
    const next = Math.max(0, ...appData.clientes.map((client) => client.id)) + 1;
    appData.clientes.unshift({
      id: next,
      nome: data.nome.trim(),
      criadoEm: new Date().toISOString(),
      telefone: data.telefone || "—",
      instagram: data.instagram || "—",
      status: "Novo",
      ultima: "Agora",
      total: 0,
      pendente: 0,
      observacao: data.observacao || "",
      tags: ["Novo cliente"],
    });
    sessionData.atividade.unshift({
      t: "client",
      a: "Novo cliente",
      b: data.nome.trim(),
      w: "agora",
    });
  } else if (type === "receita" || type === "despesa") {
    const next = Math.max(0, ...appData.financeiro.map((entry) => entry.id)) + 1;
    const status = data.status === "pago" ? "pago" : "aberto";
    appData.financeiro.unshift({
      id: next,
      descricao: data.descricao.trim(),
      pessoa: data.pessoa || "—",
      tipo: type,
      valor: Number(data.valor) || 0,
      vencimento: data.vencimento || todayISO(),
      status,
    });
  } else {
    const next = Math.max(0, ...appData.produtos.map((product) => product.id)) + 1;
    const isService = data.tipo === "Serviço";
    appData.produtos.unshift({
      id: next,
      nome: data.nome.trim(),
      tipo: data.tipo || "Produto",
      preco: Number(data.preco) || 0,
      custo: Number(data.custo) || 0,
      estoque: isService ? null : Number(data.estoque) || 0,
      minimo: isService ? null : Number(data.minimo) || 0,
      status: "Ativo",
    });
  }
  if (!saveAppData()) {
    appData = previous;
    sessionData.atividade = activity;
    return;
  }
  toast(
    type === "venda"
      ? "Venda criada"
      : type === "cliente"
        ? "Cliente criado"
        : type === "produto"
          ? "Item criado"
          : type === "receita"
            ? "Receita registrada"
            : "Despesa registrada",
    "Salvo neste navegador.",
  );
  renderCurrentView();
  closeModal("createModal");
  const kind =
    type === "venda"
      ? "sales"
      : type === "cliente"
        ? "clients"
        : type === "receita" || type === "despesa"
          ? "finance"
          : "products";
  const list =
    kind === "sales"
      ? appData.vendas
      : kind === "clients"
        ? appData.clientes
        : kind === "finance"
          ? appData.financeiro
          : appData.produtos;
  const fresh = document
    .querySelector(`.page-view.active [data-row-menu="${kind}"][data-row-id="${list[0]?.id}"]`)
    ?.closest("article");
  window.SocialMEIMotion.highlight(fresh);
}
function globalSearchItems() {
  return [
    ...appData.clientes.map((client) => ({
      kind: "Cliente",
      label: client.nome,
      sub: client.telefone,
      view: "Clientes",
      id: client.id,
    })),
    ...appData.vendas.map((sale) => ({
      kind: "Venda",
      label: `#${sale.id} · ${sale.cliente}`,
      sub: money(sale.valor),
      view: "Vendas",
      id: sale.id,
    })),
    ...appData.produtos.map((product) => ({
      kind: product.tipo,
      label: product.nome,
      sub: money(product.preco),
      view: "Produtos e Serviços",
      id: product.id,
    })),
    ...sessionData.conversas.map((conversation) => ({
      kind: "Conversa",
      label: conversation.nome,
      sub: `${channelLabel(conversation.canal)} · ${lastMessage(conversation)}`,
      view: "Caixa Unificada",
      id: conversation.id,
    })),
  ];
}
function renderGlobalSearch(q = "") {
  const term = q.trim().toLowerCase();
  const list = globalSearchItems()
    .filter((x) => !term || (x.kind + " " + x.label + " " + x.sub).toLowerCase().includes(term))
    .slice(0, 12);
  $("globalSearchResults").innerHTML = list.length
    ? list
        .map(
          (x) => /* HTML */ `<button
                    class="command-item"
                    type="button"
                    data-search-view="${x.view}"
                    ${x.id ? `data-search-id="${x.id}"` : ""}
                  >
                    <span class="fi"
                      >${renderIcon(x.kind === "Cliente" ? "users" : x.kind === "Venda" ? "bag" : x.kind === "Conversa" ? "inbox" : "box")}</span
                    >
                    <span
                      ><b>${escapeHtml(x.label)}</b
                      ><small>${escapeHtml(x.kind)} · ${escapeHtml(x.sub)}</small></span
                    ><span class="command-kbd">↵</span>
                  </button>`,
        )
        .join("")
    : /* HTML */ `<div class="empty"
              ><b>Nada encontrado</b><span>Tente outro termo.</span></div
            >`;
}
function openGlobalSearch() {
  renderGlobalSearch("");
  openModal("searchModal");
  setTimeout(() => {
    $("globalSearchInput").value = "";
    $("globalSearchInput").focus();
  }, 0);
}
function closeDropdowns(except = null) {
  document.querySelectorAll(".dd.open").forEach((dd) => {
    if (dd !== except) {
      dd.classList.remove("open");
      dd.querySelector(":scope > button")?.setAttribute("aria-expanded", "false");
    }
  });
}
function toggleDropdown(dd) {
  const willOpen = !dd.classList.contains("open");
  closeDropdowns(dd);
  dd.classList.toggle("open", willOpen);
  dd.querySelector(":scope > button")?.setAttribute("aria-expanded", String(willOpen));
}
function toast(title, desc = "") {
  const node = document.createElement("div");
  node.className = "toast";
  node.setAttribute("role", "status");
  node.innerHTML = /* HTML */ `${renderIcon("success")}
          <div>
            <b>${escapeHtml(title)}</b>${desc ? /* HTML */ `<span>${escapeHtml(desc)}</span>` : ""}
          </div>`;
  $("toastZone").appendChild(node);
  let timer = 0;
  let started = 0;
  let remaining = window.SocialMEIMotion.ms("motion-feedback");
  const clear = () => {
    clearTimeout(timer);
    TOAST_TIMERS.delete(timer);
  };
  const remove = () => {
    clear();
    node.remove();
  };
  function start() {
    started = performance.now();
    timer = setTimeout(() => {
      clear();
      node.style.opacity = "0";
      node.style.transform = "translateY(5px) scale(.98)";
      timer = setTimeout(
        remove,
        window.SocialMEIMotion.reduced ? 0 : window.SocialMEIMotion.ms("motion-fast"),
      );
      TOAST_TIMERS.add(timer);
    }, remaining);
    TOAST_TIMERS.add(timer);
  }
  node.addEventListener("pointerenter", () => {
    clear();
    remaining = Math.max(0, remaining - (performance.now() - started));
  });
  node.addEventListener("pointerleave", start);
  start();
}
function openRecord(type, id) {
  const item = (
    type === "finance" ? appData.financeiro : type === "sales" ? appData.vendas : appData.produtos
  ).find((x) => x.id === Number(id));
  if (!item) {
    return;
  }
  recordContext = {
    type,
    id: Number(id),
  };
  $("recordTitle").textContent =
    type === "sales" ? `Venda #${item.id}` : item.descricao || item.nome;
  const fields =
    type === "finance"
      ? [
          ["Descrição", item.descricao],
          ["Cliente / fornecedor", item.pessoa],
          ["Tipo", item.tipo === "receita" ? "Entrada" : "Saída"],
          ["Vencimento", formatDate(item.vencimento)],
          ["Situação", financeStatusLabel(ledgerStatus(item), item.tipo)],
          ["Valor", money(item.valor)],
        ]
      : type === "sales"
        ? [
            ["Cliente", item.cliente],
            ["Data", formatDate(item.data)],
            ["Pagamento", item.pagamento],
            ["Situação", item.status],
            ["Valor", money(item.valor)],
            ["Item", item.item || "Não informado no registro"],
            ["Quantidade", item.quantidade || "Não informada"],
          ]
        : [
            ["Tipo", item.tipo],
            ["Preço", money(item.preco)],
            ["Custo informado", money(item.custo)],
            [
              "Margem simples",
              item.preco
                ? (((item.preco - item.custo) / item.preco) * 100).toLocaleString("pt-BR", {
                    maximumFractionDigits: 1,
                  }) + "%"
                : "—",
            ],
            ["Situação", item.status],
            ...(item.tipo === "Produto"
              ? [
                  ["Estoque", plural(item.estoque, "unidade")],
                  ["Mínimo", plural(item.minimo, "unidade")],
                ]
              : []),
          ];
  let actions = "";
  if (type === "finance" && item.status !== "pago") {
    actions = /* HTML */ `<button class="btn pr" data-finance-paid="${item.id}">
            ${item.tipo === "receita" ? "Marcar como recebido" : "Marcar como pago"}
          </button>`;
  }
  if (type === "sales") {
    actions = /* HTML */ `${!["Pago", "Cancelado"].includes(item.status) ? /* HTML */ `<button class="btn pr" data-sale-paid="${item.id}">Marcar como paga</button>` : ""}<button
              class="btn"
              data-sale-duplicate="${item.id}"
            >
              Duplicar como rascunho
            </button>`;
  }
  if (type === "products" && item.tipo === "Produto") {
    actions = /* HTML */ `<div class="drawer-section">
            <h4>Ajustar estoque</h4>
            <p class="section-sub">Registre a entrada ou saída de uma unidade.</p>
            <div class="page-actions" style="margin-top:16px">
              <button
                class="btn"
                data-adjust-stock="${item.id}"
                data-delta="-1"
                ${item.estoque === 0 ? "disabled" : ""}
              >
                − Registrar saída</button
              ><button class="btn pr" data-adjust-stock="${item.id}" data-delta="1">
                + Registrar entrada
              </button>
            </div>
          </div>`;
  }
  $("recordBody").innerHTML = /* HTML */ `<p class="section-sub">
            Registro local · consulte os dados antes de alterar.
          </p>
          <dl class="detail-fields">
            ${fields
              .map(
                ([label, value]) => /* HTML */ `<div>
                    <dt>${label}</dt>
                    <dd>${escapeHtml(value)}</dd>
                  </div>`,
              )
              .join("")}
          </dl>
          ${type === "products" ? '<p class="table-help">Margem simples: (preço − custo) ÷ preço. Não inclui impostos nem despesas adicionais.</p>' : ""}${
            item.observacao
              ? /* HTML */ `<div class="drawer-section">
                  <h4>Observação</h4>
                  <p>${escapeHtml(item.observacao)}</p>
                </div>`
              : ""
          }
          <div class="page-actions">${actions}</div>`;
  openModal("recordModal");
}
