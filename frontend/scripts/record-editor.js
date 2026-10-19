/* RECORD EDITOR */
/* Edição e confirmação de alterações preservam o esquema dos registros. */
let activeRecordEdit = null;
function validateRequiredFormText(form) {
  if (!form) {
    return false;
  }
  form.querySelectorAll("input[required],textarea[required]").forEach((input) => {
    if (["text", "search", "tel", "url", "textarea"].includes(input.type)) {
      input.setCustomValidity(input.value.trim() ? "" : "Preencha este campo com um texto.");
    }
  });
  updateCatalogMoneyValidity(form);
  return form.reportValidity();
}
document.addEventListener(
  "input",
  (event) => {
    const input = event.target;
    if (input.closest?.("#createForm") && ["preco", "custo"].includes(input.name))
      updateCatalogMoneyValidity(input.closest("form"));
    if (
      input.matches?.("input[required],textarea[required]") &&
      ["text", "search", "tel", "url", "textarea"].includes(input.type)
    ) {
      input.setCustomValidity(input.value.trim() ? "" : "Preencha este campo com um texto.");
    }
  },
  true,
);
document.addEventListener(
  "submit",
  (event) => {
    if (!validateRequiredFormText(event.target)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },
  true,
);
// Restaurar o tema automático ou personalizado do app não altera a preferência pública.
window.addEventListener("socialmei-theme-change", () => {
  if (!document.body.classList.contains("experience-public")) {
    return;
  }
  const theme = document.documentElement.dataset.publicTheme === "dark" ? "dark" : "light";
  SocialMEIThemes.applyTokens(document.documentElement, SocialMEIThemes.official[theme]);
  document.documentElement.dataset.theme = theme;
});
const baseUpdateSaleReview = updateSaleReview;
updateSaleReview = function () {
  baseUpdateSaleReview();
  if (!activeRecordEdit) {
    return;
  }
  $("createSubmit").textContent = "Salvar alterações";
  if (activeRecordEdit.type === "sales") {
    const sale = findBusinessRecord("sales", activeRecordEdit.id);
    const note = $("saleReview").querySelector(".table-help");
    if (sale && note) {
      note.textContent = `A venda continua ${sale.status.toLowerCase()}. O histórico financeiro não será alterado.`;
    }
  }
};
$("createForm").addEventListener("input", () => updateSaleReview());
$("createForm").addEventListener("change", () => updateSaleReview());
const BUSINESS_COLLECTION_KEYS = {
  sales: "vendas",
  clients: "clientes",
  products: "produtos",
  finance: "financeiro",
};
function findBusinessRecord(type, id) {
  return appData[BUSINESS_COLLECTION_KEYS[type]]?.find((x) => x.id === Number(id));
}
function renderRecordActions(type, id) {
  const record = findBusinessRecord(type, id);
  if (!record) {
    return "";
  }
  return /* HTML */ `<div class="management-review-actions">${type === "sales" && SocialMEISales.remote && record.status === "Rascunho" && !record.importada ? `<button class="management-button pr" type="button" data-sale-register="${id}">Registrar venda</button>` : ""}
          <button
            class="management-button"
            type="button"
            ${(type === "sales" && SocialMEISales.remote && (record.importada || !["Pendente", "Rascunho"].includes(record.status))) || (type === "finance" && SocialMEIFinance.remote && record.status === "pago") ? "disabled" : ""}
            data-review-edit="${type}"
            data-review-id="${id}"
          >
            Editar</button
          >${
            type === "sales" &&
            (["Pendente", "Rascunho"].includes(record.status) ||
              (SocialMEISales.remote && record.status === "Pago"))
              ? /* HTML */ `<button
                    class="management-button"
                    type="button"
                    data-review-cancel="${id}"
                  >
                    Cancelar venda
                  </button>`
              : ""
          }<button
            class="management-button management-danger"
            type="button"
            data-review-delete="${type}"
            data-review-id="${id}"
          >
            Excluir
            ${type === "clients" ? "perfil" : type === "sales" ? "venda" : type === "finance" ? "lançamento" : "item"}
          </button>
        </div>`;
}
const openRecordWithSaleDetails = openRecord;
openRecord = function (type, id) {
  openRecordWithSaleDetails(type, id);
  if (findBusinessRecord(type, id)) {
    $("recordBody").insertAdjacentHTML("beforeend", renderRecordActions(type, Number(id)));
  }
};
const baseRenderSaleDrawer = renderSaleDrawer;
renderSaleDrawer = function (id) {
  baseRenderSaleDrawer(id);
  if (findBusinessRecord("sales", id)) {
    $("recordBody").insertAdjacentHTML("beforeend", renderRecordActions("sales", Number(id)));
  }
};
// A abertura de registros já renderiza os detalhes da venda; mantém uma única lista de ações.
const openRecordWithActions = openRecord;
openRecord = function (type, id) {
  openRecordWithActions(type, id);
  const actions = $("recordBody").querySelectorAll(".management-review-actions");
  actions.forEach((a, i) => {
    if (i) {
      a.remove();
    }
  });
};
const baseRenderClientPanel = renderClientPanel;
renderClientPanel = function () {
  baseRenderClientPanel();
  if (findBusinessRecord("clients", drawerClientId)) {
    $("clientModalBody").insertAdjacentHTML(
      "beforeend",
      renderRecordActions("clients", drawerClientId),
    );
  }
};
const openCreateWithManagementStyle = openCreate;
openCreate = function (type = "venda", preset = {}) {
  if (SocialMEIDemoData.enabled()) return;
  activeRecordEdit = null;
  $("createType").disabled = false;
  $("createType").closest(".form-group").hidden = false;
  openCreateWithManagementStyle(type, preset);
};
async function openRecordEditor(type, id) {
  if (SocialMEIDemoData.enabled()) return;
  const record = findBusinessRecord(type, id);
  if (!record) return;
  if (
    type === "sales" &&
    SocialMEISales.remote &&
    (record.importada || !["Pendente", "Rascunho"].includes(record.status))
  ) {
    toast("Histórico preservado", "Duplique como rascunho para criar outra venda.");
    return;
  }
  if (type === "finance" && SocialMEIFinance.remote && record.status === "pago") {
    toast(
      "Histórico preservado",
      "Lançamento quitado não pode ser editado. Crie outro para corrigir.",
    );
    return;
  }
  const returnFocus = document.activeElement;
  await closeModal(type === "clients" ? "clientModal" : "recordModal");
  const createType =
    type === "sales"
      ? "venda"
      : type === "clients"
        ? "cliente"
        : type === "finance"
          ? record.tipo
          : "produto";
  openCreate(createType, {
    cliente: record.cliente || "",
  });
  activeRecordEdit = {
    type,
    id: Number(id),
    returnFocus,
    versao: record.versao,
  };
  $("createType").disabled = true;
  $("createType").closest(".form-group").hidden = true;
  $("createModalTitle").textContent =
    type === "sales"
      ? `Editar venda #${id}`
      : type === "clients"
        ? "Editar cliente"
        : type === "finance"
          ? "Editar lançamento"
          : "Editar produto ou serviço";
  const values = { ...record };
  if (type === "finance" && SocialMEIFinance.remote) {
    values.cliente_id = record.cliente_id ?? "";
    $("f_status").disabled = true;
  }
  if (type === "sales" && SocialMEISales.remote) {
    values.cliente = record.cliente_id;
    values.item = record.produto_id;
  }
  if (type === "sales") {
    values.quantidade = record.quantidade || 1;
    values.desconto = record.desconto || 0;
    values.preco = record.preco ?? (record.valor + values.desconto) / values.quantidade;
    if (!record.item) {
      $("f_item").required = false;
      $("f_item").placeholder = "Item não informado no registro";
    }
    $("createFields").insertAdjacentHTML(
      "beforeend",
      createField("Data da venda", "data", "date", {
        value: record.data,
        required: true,
        full: true,
      }) +
        '<p class="management-note full">O status e os lançamentos financeiros continuam separados. Editar a venda não confirma um recebimento.</p>',
    );
  }
  if (type === "clients") {
    $("createFields").insertAdjacentHTML(
      "beforeend",
      createField("Status", "status", "select", {
        value: record.status,
        options: ["Novo", "Ativo", "Inativo"],
      }) +
        createField("Etiquetas (separadas por vírgula)", "tags", "text", {
          value: (record.tags || []).join(", "),
          full: true,
        }),
    );
  }
  $("createFields")
    .querySelectorAll("[name]")
    .forEach((input) => {
      if (input.name === "tags") {
        return;
      }
      const value = values[input.name];
      if (value === undefined || value === null) {
        return;
      }
      if (
        input.tagName === "SELECT" &&
        ![...input.options].some((o) => o.value === String(value))
      ) {
        input.add(new Option(String(value), String(value)));
      }
      input.value = String(value);
    });
  toggleProductInventory();
  updateSaleReview();
  if (type === "sales") {
    $("saleReview").querySelector(".table-help").textContent =
      `A venda continua ${record.status.toLowerCase()}. O histórico financeiro não será alterado.`;
  }
  $("createSubmit").textContent = "Salvar alterações";
  requestAnimationFrame(() => $("createFields").querySelector("input,select,textarea")?.focus());
}
async function saveRecordEdit(form) {
  if (SocialMEIDemoData.enabled()) return;
  if (!validateRequiredFormText(form) || !activeRecordEdit) {
    return;
  }
  const context = activeRecordEdit;
  const record = findBusinessRecord(context.type, context.id);
  if (!record) {
    return;
  }
  const before = cloneData(appData);
  const d = Object.fromEntries(new FormData(form));
  if (context.type === "clients" && SocialMEIClients.remote) {
    const saved = await SocialMEIClients.update(
      { ...record, versao: context.versao },
      {
        nome: d.nome.trim(),
        telefone: d.telefone.trim() || "—",
        instagram: d.instagram.trim() || "—",
        observacao: d.observacao.trim(),
        status: d.status,
        tags: [
          ...new Set(
            d.tags
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean),
          ),
        ],
      },
    );
    if (saved) {
      if (activeRecordEdit === context) {
        activeRecordEdit = null;
        closeModal("createModal");
      }
      toast("Alterações salvas", "Cliente atualizado na API compartilhada.");
    }
    return;
  }
  if (context.type === "products" && SocialMEIProducts.remote) {
    const service = d.tipo === "Serviço";
    const saved = await SocialMEIProducts.update(
      { ...record, versao: context.versao },
      {
        nome: d.nome.trim(),
        tipo: d.tipo,
        preco: Number(d.preco),
        custo: Number(d.custo) || 0,
        estoque: service ? null : Number(d.estoque) || 0,
        minimo: service ? null : Number(d.minimo) || 0,
      },
    );
    if (saved) {
      if (activeRecordEdit === context) {
        activeRecordEdit = null;
        closeModal("createModal");
      }
      toast("Alterações salvas", "Catálogo atualizado na API compartilhada.");
    }
    return;
  }
  if (context.type === "sales" && SocialMEISales.remote) {
    const saved = await SocialMEISales.update(
      { ...record, versao: context.versao },
      {
        cliente_id: Number(d.cliente),
        produto_id: Number(d.item),
        data: d.data,
        quantidade: Number(d.quantidade),
        preco: Number(d.preco),
        desconto: Number(d.desconto) || 0,
        pagamento: d.pagamento,
        observacao: d.observacao || "",
      },
    );
    if (saved) {
      if (activeRecordEdit === context) {
        activeRecordEdit = null;
        closeModal("createModal");
      }
      toast("Venda atualizada", "Estoque ajustado junto com a venda.");
    }
    return;
  }
  if (context.type === "finance" && SocialMEIFinance.remote) {
    const saved = await SocialMEIFinance.update(
      { ...record, versao: context.versao },
      {
        descricao: d.descricao.trim(),
        pessoa: d.pessoa || "",
        tipo: record.tipo,
        valor: Number(d.valor),
        vencimento: d.vencimento,
        cliente_id: d.cliente_id ? Number(d.cliente_id) : null,
      },
    );
    if (saved) {
      if (activeRecordEdit === context) {
        activeRecordEdit = null;
        closeModal("createModal");
      }
      toast("Lançamento atualizado", "Salvo no Financeiro compartilhado.");
    }
    return;
  }
  const oldName = record.nome;
  if (context.type === "sales") {
    Object.assign(record, {
      cliente: d.cliente.trim(),
      item: d.item.trim(),
      quantidade: Number(d.quantidade),
      preco: Number(d.preco),
      desconto: Number(d.desconto) || 0,
      pagamento: d.pagamento,
      data: d.data,
      observacao: d.observacao.trim(),
    });
    record.valor = Math.max(
      0,
      Math.round((record.preco * record.quantidade - record.desconto) * 100) / 100,
    );
  } else if (context.type === "clients") {
    Object.assign(record, {
      nome: d.nome.trim(),
      telefone: d.telefone.trim() || "—",
      instagram: d.instagram.trim() || "—",
      observacao: d.observacao.trim(),
      status: d.status,
      tags: [
        ...new Set(
          d.tags
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
        ),
      ],
    });
    // Atualiza somente vínculos existentes e inequívocos com nome exato.
    if (
      appData.clientes.filter(
        (client) =>
          normalizedText(client.nome) === normalizedText(oldName) && client.id !== record.id,
      ).length === 0
    ) {
      appData.vendas
        .filter((sale) => normalizedText(sale.cliente) === normalizedText(oldName))
        .forEach((sale) => (sale.cliente = record.nome));
      (SocialMEIFinance.remote ? [] : appData.financeiro)
        .filter((entry) => normalizedText(entry.pessoa || "") === normalizedText(oldName))
        .forEach((entry) => (entry.pessoa = record.nome));
    }
  } else if (context.type === "finance") {
    Object.assign(record, {
      descricao: d.descricao.trim(),
      pessoa: d.pessoa.trim() || "—",
      valor: Number(d.valor),
      vencimento: d.vencimento,
      status: d.status,
    });
  } else {
    const service = d.tipo === "Serviço";
    Object.assign(record, {
      nome: d.nome.trim(),
      tipo: d.tipo,
      preco: Number(d.preco),
      custo: Number(d.custo) || 0,
      estoque: service ? null : Number(d.estoque) || 0,
      minimo: service ? null : Number(d.minimo) || 0,
    });
  }
  if (!saveAppData()) {
    appData = before;
    return;
  }
  if (context.type === "clients") {
    sessionData.conversas
      .filter(
        (conversation) =>
          conversation.clientId === record.id ||
          (normalizedText(conversation.nome) === normalizedText(oldName) &&
            before.clientes.filter(
              (client) => normalizedText(client.nome) === normalizedText(oldName),
            ).length === 1),
      )
      .forEach((conversation) => {
        conversation.clientId = record.id;
        persistConversationState(conversation);
      });
  }
  activeRecordEdit = null;
  renderCurrentView();
  const target =
    context.type === "clients"
      ? document.querySelector(`[data-open-client="${context.id}"]`)
      : document.querySelector(
          `[data-record-open="${context.type}"][data-record-id="${context.id}"]`,
        );
  if (target) {
    $("createModal")._returnFocus = target;
  }
  closeModal("createModal");
  toast("Alterações salvas", "Registro atualizado neste navegador.");
}
// Confirmação explícita, acessível por teclado, evita exclusão acidental.
document.body.insertAdjacentHTML(
  "beforeend",
  /* HTML */ `<div class="modal-backdrop" id="reviewConfirm" aria-hidden="true">
          <section
            class="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reviewConfirmTitle"
          >
            <div class="modal-head">
              <h3 id="reviewConfirmTitle"></h3>
              <button
                class="management-button"
                type="button"
                data-close-modal="reviewConfirm"
                aria-label="Fechar confirmação"
              >
                Fechar
              </button>
            </div>
            <div class="modal-body"><p id="reviewConfirmText"></p></div>
            <div class="modal-foot">
              <button class="management-button" type="button" data-close-modal="reviewConfirm">
                Voltar</button
              ><button
                class="management-button management-danger"
                type="button"
                id="reviewConfirmAction"
              >
                Confirmar
              </button>
            </div>
          </section>
        </div>`,
);
let reviewPending = null;
function openRecordConfirmation(type, id, cancel = false) {
  const record = findBusinessRecord(type, id);
  if (!record) {
    return;
  }
  reviewPending = {
    type,
    id: Number(id),
    cancel,
    versao: record.versao,
  };
  $("reviewConfirmTitle").textContent = cancel ? "Cancelar esta venda?" : "Excluir este registro?";
  const label = type === "sales" ? `Venda #${id}` : record.nome || record.descricao;
  $("reviewConfirmText").textContent = cancel
    ? `${label} ficará cancelada. Os lançamentos financeiros serão preservados e precisam ser conferidos separadamente.`
    : type === "clients"
      ? `O perfil de ${label} será excluído. As conversas, vendas e lançamentos permanecem no navegador.`
      : `${label} será excluído deste navegador. Os demais registros serão preservados. Esta exclusão não pode ser desfeita; mantenha um backup para recuperar o registro.`;
  if (type === "products" && SocialMEIProducts.remote)
    $("reviewConfirmText").textContent =
      `${label} será excluído do catálogo compartilhado. As vendas locais permanecem registradas.`;
  if (type === "sales" && SocialMEISales.remote)
    $("reviewConfirmText").textContent =
      `${label}: ${cancel ? "cancelar" : "excluir"} estorna apenas o estoque aplicado por esta venda. O financeiro permanece separado. Vendas importadas não estornam estoque.`;
  if (type === "finance" && SocialMEIFinance.remote)
    $("reviewConfirmText").textContent =
      `${label} será excluído do Financeiro compartilhado e deixará de entrar nos totais. O histórico é preservado no servidor. Vendas e estoque não serão alterados.`;
  $("reviewConfirmAction").textContent = cancel ? "Cancelar venda" : "Excluir registro";
  openModal("reviewConfirm");
}
async function confirmRecordChange() {
  if (SocialMEIDemoData.enabled()) return;
  const pending = reviewPending;
  if (!pending) {
    return;
  }
  const record = findBusinessRecord(pending.type, pending.id);
  if (!record) {
    return;
  }
  if (pending.type === "clients" && SocialMEIClients.remote) {
    if (await SocialMEIClients.remove({ ...record, versao: pending.versao })) {
      reviewPending = null;
      await closeModal("reviewConfirm");
      await closeModal("clientModal");
      toast("Cliente excluído", "Cadastro removido da API compartilhada.");
    }
    return;
  }
  if (pending.type === "products" && SocialMEIProducts.remote) {
    if (await SocialMEIProducts.remove({ ...record, versao: pending.versao })) {
      reviewPending = null;
      await closeModal("reviewConfirm");
      await closeModal("recordModal");
      toast("Item excluído", "Removido da API compartilhada.");
    }
    return;
  }
  if (pending.type === "sales" && SocialMEISales.remote) {
    const saved = await SocialMEISales.transition(
      { ...record, versao: pending.versao },
      pending.cancel ? "cancelar" : "excluir",
    );
    if (saved) {
      reviewPending = null;
      await closeModal("reviewConfirm");
      await closeModal("recordModal");
      renderCurrentView();
      toast(
        pending.cancel ? "Venda cancelada" : "Venda excluída",
        "Estoque tratado na mesma operação.",
      );
    }
    return;
  }
  if (pending.type === "finance" && SocialMEIFinance.remote) {
    if (await SocialMEIFinance.remove({ ...record, versao: pending.versao })) {
      reviewPending = null;
      await closeModal("reviewConfirm");
      await closeModal("recordModal");
      toast("Lançamento excluído", "Removido dos totais compartilhados.");
    }
    return;
  }
  const before = cloneData(appData);
  if (pending.cancel) {
    if (!["Pendente", "Rascunho"].includes(record.status)) {
      return;
    }
    record.status = "Cancelado";
  } else {
    appData[BUSINESS_COLLECTION_KEYS[pending.type]] = appData[
      BUSINESS_COLLECTION_KEYS[pending.type]
    ].filter((x) => x.id !== pending.id);
  }
  if (!saveAppData()) {
    appData = before;
    return;
  }
  if (!pending.cancel && pending.type === "clients") {
    sessionData.conversas
      .filter((conversation) => conversation.clientId === record.id)
      .forEach((conversation) => {
        conversation.nome = record.nome;
        delete conversation.clientId;
        persistConversationState(conversation);
      });
  }
  reviewPending = null;
  await closeModal("reviewConfirm");
  if (pending.cancel) {
    renderCurrentView();
    openRecord("sales", pending.id);
  } else {
    await closeModal(pending.type === "clients" ? "clientModal" : "recordModal");
    renderCurrentView();
  }
  toast(
    pending.cancel ? "Venda cancelada" : "Registro excluído",
    "Alteração salva neste navegador.",
  );
}
document.addEventListener("click", (event) => {
  const edit = event.target.closest("[data-review-edit]");
  if (edit) {
    openRecordEditor(edit.dataset.reviewEdit, edit.dataset.reviewId);
    return;
  }
  const remove = event.target.closest("[data-review-delete]");
  if (remove) {
    openRecordConfirmation(remove.dataset.reviewDelete, remove.dataset.reviewId);
    return;
  }
  const cancel = event.target.closest("[data-review-cancel]");
  if (cancel) {
    openRecordConfirmation("sales", cancel.dataset.reviewCancel, true);
    return;
  }
  if (event.target.closest("#reviewConfirmAction")) {
    confirmRecordChange();
  }
});
// Preserva textos inacabados após recarga; anexos permanecem objetos File da sessão.
const COMPOSER_DRAFT_STORAGE_KEY = "socialmei-inbox-drafts-v1";
try {
  const drafts = JSON.parse(localStorage.getItem(COMPOSER_DRAFT_STORAGE_KEY) || "{}");
  if (drafts && typeof drafts === "object" && !Array.isArray(drafts)) {
    Object.entries(drafts).forEach(([id, d]) => {
      if (
        Number.isSafeInteger(Number(id)) &&
        d &&
        typeof d.text === "string" &&
        typeof d.note === "boolean" &&
        sessionData.conversas.some((conversation) => conversation.id === Number(id))
      ) {
        conversationDrafts.set(Number(id), {
          text: d.text,
          note: d.note,
        });
      }
    });
  }
} catch (_) {}
let composerDraftSaveTimer = 0;
let isDraftPersistenceSuspended = false;
document.addEventListener("socialmei-storage-reset", () => {
  isDraftPersistenceSuspended = true;
  clearTimeout(composerDraftSaveTimer);
});
function persistComposerDrafts() {
  if (isDraftPersistenceSuspended) {
    return;
  }
  clearTimeout(composerDraftSaveTimer);
  const data = {};
  for (const [id, draft] of conversationDrafts) {
    if (draft.text?.trim()) {
      data[id] = {
        text: draft.text,
        note: !!draft.note,
      };
    }
  }
  socialmeiStorageSet(
    COMPOSER_DRAFT_STORAGE_KEY,
    JSON.stringify(data),
    "os rascunhos das conversas",
  );
}
const baseSaveCurrentDraft = saveCurrentDraft;
saveCurrentDraft = function () {
  baseSaveCurrentDraft();
  clearTimeout(composerDraftSaveTimer);
  composerDraftSaveTimer = setTimeout(persistComposerDrafts, 200);
};
$("messageInput").addEventListener("input", () => saveCurrentDraft());
window.addEventListener("pagehide", () => {
  baseSaveCurrentDraft();
  persistComposerDrafts();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    baseSaveCurrentDraft();
    persistComposerDrafts();
  }
});
const reviewOriginalBackup = exportSocialMEIBackup;
exportSocialMEIBackup = function () {
  baseSaveCurrentDraft();
  persistComposerDrafts();
  reviewOriginalBackup();
};
