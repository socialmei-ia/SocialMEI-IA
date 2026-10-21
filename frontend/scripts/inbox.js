/* INBOX */
function appendInitialLocalMessage(conversation, message) {
  const text = message.trim();
  if (!text) return;
  conversation.mensagens.push({
    de: "empresa",
    texto: text,
    hora: nowTime(),
    data: todayISO(),
    localOnly: true,
  });
}
function touchConversationActivity(conversation) {
  if (!conversation) {
    return;
  }
  conversation._activityOrder = ++conversationActivitySequence;
}
function loadInboxLocal() {
  try {
    return JSON.parse(localStorage.getItem(INBOX_LOCAL_KEY) || "{}") || {};
  } catch (error) {
    return {};
  }
}
function saveInboxLocal() {
  return socialmeiStorageSet(
    INBOX_LOCAL_KEY,
    JSON.stringify(inboxLocalState),
    "os dados locais da Caixa Unificada",
  );
}
function conversationKey(conversation) {
  if (conversation._enrichmentSynthetic) return "enrichment:" + conversation._enrichmentKey;
  const key = `${conversation.canal}:${conversation.nome.toLowerCase()}`;
  return conversation._socialmeiDemoSample ? `demo:${key}` : key;
}
function isReducedMotion() {
  return window.SocialMEIMotion.reduced;
}
function lastMessage(conversation) {
  return (
    [...conversation.mensagens].reverse().find((m) => m.de !== "nota")?.texto || "Sem mensagens"
  );
}
function getConversation(id = activeConversationId) {
  return sessionData.conversas.find((conversation) => conversation.id === Number(id));
}
function inboxActiveTags(c) {
  if (c._socialmeiDemoSample) return ["Demonstração"];
  const client = c._socialmeiDemoSample ? null : SocialMEIClients.conversationClient(c);
  const tags = [...(client?.tags || [])];
  if (c.naoLidas >= 2 && !tags.includes("Urgente")) {
    tags.push("Urgente");
  }
  return tags;
}
function filteredConversations() {
  const searchQuery = foldText(($("conversationSearch")?.value || "").trim());
  const ch = $("channelFilter")?.value || "all";
  const st = $("statusFilter")?.value || "all";
  const tag = $("tagFilter")?.value || inboxSelectedTag || "all";
  const sort = $("sortFilter")?.value || inboxSortOrder || "priority";
  let list = businessViewConversations().filter((conversation) => {
    const searchable = foldText(
      [
        displayName(conversation),
        conversation.nome,
        conversation.usuario,
        conversation.canal,
        channelLabel(conversation.canal),
        conversation.telefone,
        clientContext(conversation).client?.telefone,
        ...inboxActiveTags(conversation),
        ...conversation.mensagens.map((message) => message.texto),
      ].join(" "),
    );
    const tags = inboxActiveTags(conversation);
    const base =
      (!searchQuery || searchable.includes(searchQuery)) &&
      (ch === "all" || conversation.canal === ch) &&
      (st === "all" || conversation.status === st) &&
      (tag === "all" || tags.includes(tag));
    if (!base) {
      return false;
    }
    if (
      isReplyPriorityOnly &&
      !(
        ["aberto", "andamento"].includes(conversation.status) &&
        [...conversation.mensagens].reverse().find((m) => m.de !== "nota")?.de === "cliente"
      )
    ) {
      return false;
    }
    if (inboxQuickFilter === "all") {
      return true;
    }
    if (inboxQuickFilter === "unread") {
      return conversation.naoLidas > 0;
    }
    return conversation.status === inboxQuickFilter;
  });
  if (sort === "favorite") {
    list.sort(
      (a, b) =>
        Number(isFavorite(b)) - Number(isFavorite(a)) ||
        (b._activityOrder || 0) - (a._activityOrder || 0),
    );
  } else if (sort === "name") {
    list.sort((a, b) => displayName(a).localeCompare(displayName(b), "pt-BR"));
  } else if (sort === "recent") {
    list.sort((a, b) => (b._activityOrder || 0) - (a._activityOrder || 0));
  } else {
    list.sort((a, b) => {
      const aDone = a.status === "concluido" ? 1 : 0;
      const bDone = b.status === "concluido" ? 1 : 0;
      return aDone - bDone || (b._activityOrder || 0) - (a._activityOrder || 0);
    });
  }
  return list;
}
function conversationTags(c) {
  const tags = inboxActiveTags(c).filter(
    (tag) => !c._socialmeiDemoSample || tag !== "Demonstração",
  );
  if (c.status === "aberto" && !tags.includes("Orçamento")) {
    tags.unshift("Pendente");
  }
  return tags.slice(0, 2);
}
function updateInboxCounts() {
  const records = businessViewConversations();
  const { unreadMessages: unread, unreadConversations, pending } = conversationCounts(records);
  if ($("totalSummary")) {
    $("totalSummary").textContent = records.length;
  }
  document
    .querySelectorAll('[data-filter-count="all"]')
    .forEach((x) => (x.textContent = records.length));
  document
    .querySelectorAll('[data-filter-count="andamento"]')
    .forEach(
      (x) =>
        (x.textContent = records.filter(
          (conversation) => conversation.status === "andamento",
        ).length),
    );
  if ($("pendingSummary")) {
    $("pendingSummary").textContent = pending;
  }
  if ($("unreadSummary")) {
    $("unreadSummary").textContent = unread;
  }
  if ($("pendingCount")) {
    $("pendingCount").textContent =
      `${unread} mensage${unread === 1 ? "m" : "ns"} não lida${unread === 1 ? "" : "s"}`;
  }
  document
    .querySelectorAll('[data-filter-count="unread"]')
    .forEach((x) => (x.textContent = unreadConversations));
  document.querySelectorAll('[data-quick-filter="unread"]').forEach((button) => {
    const label = `${unreadConversations} conversa${unreadConversations === 1 ? "" : "s"} com mensagens não lidas`;
    button.setAttribute("aria-label", label);
    button.title = label;
  });
  document
    .querySelectorAll('[data-filter-count="aberto"]')
    .forEach(
      (x) =>
        (x.textContent =
          records.filter((conversation) => conversation.status === "aberto").length || ""),
    );
}
function updateFilterBadge() {
  const count = [
    $("channelFilter")?.value !== "all",
    $("statusFilter")?.value !== "all",
    $("tagFilter")?.value !== "all",
    ($("sortFilter")?.value || "priority") !== "priority",
  ].filter(Boolean).length;
  if ($("activeFilterCount")) {
    $("activeFilterCount").textContent = count;
    $("activeFilterCount").hidden = !count;
  }
}
function renderConversationList() {
  const host = $("conversationList");
  const previousScroll = host?.scrollTop || 0;
  const focusedId = host?.contains(document.activeElement)
    ? document.activeElement.dataset.conversation
    : null;
  const list = filteredConversations();
  const totalUnread = conversationCounts().unreadMessages;
  updateInboxCounts();
  updateFilterBadge();
  if ($("conversationCount")) {
    $("conversationCount").textContent = `${list.length} conversa${list.length === 1 ? "" : "s"}`;
  }
  if ($("pendingCount")) {
    $("pendingCount").textContent =
      `${totalUnread} mensage${totalUnread === 1 ? "m" : "ns"} não lida${totalUnread === 1 ? "" : "s"}`;
  }
  document.querySelectorAll(".quick-filter").forEach((b) => {
    b.classList.toggle("active", b.dataset.quickFilter === inboxQuickFilter);
    b.setAttribute("aria-pressed", String(b.dataset.quickFilter === inboxQuickFilter));
  });
  if (isReplyPriorityOnly) {
    $("conversationCount").textContent = "Aguardando sua resposta";
  }
  if (!list.length) {
    if (syncState === "loading" && !sessionData.conversas.length) {
      $("conversationList").innerHTML = loadingConversations();
      return;
    }
    const hasQuery = Boolean(($("conversationSearch")?.value || "").trim());
    $("conversationList").innerHTML = /* HTML */ `<li>
            <div class="inbox-empty compact">
              <div class="empty-visual">${renderIcon("search")}</div>
              <b
                >${hasQuery ? "Nenhum resultado" : sessionData.conversas.length ? "Nenhuma conversa nesta visualização" : "Nenhuma conversa por aqui."}</b
              ><span
                >${hasQuery ? "Tente outro nome, mensagem ou limpe a busca." : "Ajuste os filtros ou aguarde uma nova mensagem."}</span
              >${
                hasQuery
                  ? '<button class="btn" type="button" id="clearConversationSearch">Limpar busca</button>'
                  : sessionData.conversas.length
                    ? '<button class="btn" type="button" data-clear-inbox-filters>Limpar filtros</button>'
                    : '<button class="btn" type="button" data-new-inbox-conversation>Nova conversa local</button>'
              }
            </div>
          </li>`;
    return;
  }
  $("conversationList").innerHTML = list
    .map((c) => {
      const statusClass =
        c.status === "andamento" ? "progress" : c.status === "aberto" ? "open" : "";
      return /* HTML */ `<li role="presentation">
              <button
                class="conv-item ${!isInboxListMode && c.id === activeConversationId ? "active" : ""} ${c.naoLidas ? "unread-item" : ""}"
                role="option"
                aria-selected="${!isInboxListMode && c.id === activeConversationId}"
                type="button"
                data-conversation="${c.id}"
              >
                <span class="conv-avatar"
                  >${avatarContents(c)}<span class="channel-mini" title="${channelLabel(c.canal)}"
                    >${channelIcon(c.canal)}</span
                  ></span
                >
                <span class="conv-main">
                  <span class="conv-line"
                    ><span class="conv-name-text" title="${escapeHtml(displayName(c))}"
                      >${escapeHtml(displayName(c))}</span
                    >${isFavorite(c) ? /* HTML */ `<span class="favorite-mini">${renderIcon("star")}</span>` : ""}<span
                      class="conv-time"
                      >${escapeHtml(c.atualizado)}</span
                    ></span
                  >
                  <span class="conv-preview" title="${escapeHtml(lastMessage(c))}"
                    ><span class="preview-channel" aria-label="${channelLabel(c.canal)}"
                      >${channelIcon(c.canal)}</span
                    ><span class="preview-text">${escapeHtml(lastMessage(c))}</span></span
                  >
                  <span class="conv-tags"
                    ><span class="status-mini ${statusClass}">${statusLabel(c.status)}</span
                    >${c._socialmeiDemoSample && sessionData.conversas.some((row) => !row._socialmeiDemoSample) ? '<span class="conv-tag">Exemplo</span>' : ""}${conversationTags(
                      c,
                    )
                      .map((t) => /* HTML */ `<span class="conv-tag">${escapeHtml(t)}</span>`)
                      .join("")}</span
                  >
                </span>
                ${c.naoLidas ? /* HTML */ `<span class="unread">${c.naoLidas}</span>` : ""}
              </button>
            </li>`;
    })
    .join("");
  if (host) {
    requestAnimationFrame(() => {
      if (focusedId) {
        host.querySelector(`[data-conversation="${focusedId}"]`)?.focus({
          preventScroll: true,
        });
      }
      host.scrollTop = Math.min(previousScroll, Math.max(0, host.scrollHeight - host.clientHeight));
    });
  }
}
function messageDateKey(m) {
  return m.data || todayISO();
}
function messageDateLabel(key) {
  const today = todayISO();
  const d = new Date(key + "T12:00:00");
  const y = new Date();
  y.setDate(y.getDate() - 1);
  const yd = y.toISOString().slice(0, 10);
  if (key === today) {
    return "Hoje";
  }
  if (key === yd) {
    return "Ontem";
  }
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "long",
  }).format(d);
}
function messageHTML(m, prev = null, animate = false) {
  const cls = m.de === "empresa" ? "out" : m.de === "nota" ? "note" : "in";
  const grouped =
    prev && prev.de === m.de && messageDateKey(prev) === messageDateKey(m) ? " grouped" : "";
  const suffix = m.localOnly ? " · local" : m.de === "nota" ? " · nota interna" : "";
  return /* HTML */ `<div
          class="msg ${cls}${grouped}${animate ? " new-message" : ""}"
          data-message-text="${escapeHtml(m.texto).toLowerCase()}"
        >
          <span class="message-copy">${escapeHtml(m.texto)}</span
          ><small>${escapeHtml(m.hora)}${suffix}</small>
        </div>`;
}
function renderMessages(c, { preserveScroll = false } = {}) {
  const host = $("messages");
  if (!host) {
    return;
  }
  const oldTop = host.scrollTop;
  const oldBottom = host.scrollHeight - host.scrollTop - host.clientHeight;
  let html = "";
  let lastDate = null;
  let prev = null;
  c.mensagens.forEach((message) => {
    const dk = messageDateKey(message);
    if (dk !== lastDate) {
      html += /* HTML */ `<div class="day-sep" data-date="${dk}"
              >${messageDateLabel(dk)}</div
            >`;
      lastDate = dk;
      prev = null;
    }
    html += messageHTML(message, prev, false);
    prev = message;
  });
  const linkedSale = clientContext(c).lastSale;
  if (linkedSale) {
    html += /* HTML */ `<div class="thread-sale-context conversation-order">
            <span class="editorial-label">Pedido nesta história</span
            ><button class="lk" data-open-inbox-sale="${linkedSale.id}">
              Venda #${linkedSale.id} · ${money(linkedSale.valor)} →</button
            ><span class="pill ${saleStatusClass(linkedSale.status)}"
              >${escapeHtml(linkedSale.status)}</span
            >
          </div>`;
  }
  if (!c.mensagens.length) {
    html = /* HTML */ `<div class="inbox-empty">
            <div>
              <span class="empty-visual">${renderIcon("inbox")}</span><b>Sem mensagens ainda</b
              ><span>Quando uma mensagem chegar via n8n, ela aparecerá aqui.</span>
            </div>
          </div>`;
  }
  host.innerHTML = html;
  requestAnimationFrame(() => {
    if (activeConversationId !== c.id) {
      return;
    }
    if (preserveScroll && oldBottom > 80) {
      host.scrollTop = oldTop;
    } else {
      const lastMessageNode = [...host.querySelectorAll(".msg")].at(-1);
      if (linkedSale && lastMessageNode) {
        host.scrollTop = Math.max(
          0,
          lastMessageNode.offsetTop + lastMessageNode.offsetHeight - host.clientHeight + 26,
        );
      } else {
        host.scrollTop = host.scrollHeight;
      }
    }
  });
}
function clientContext(conversation) {
  const client = conversation._socialmeiDemoSample
    ? null
    : SocialMEIClients.conversationClient(conversation);
  const purchases = client
    ? appData.vendas.filter((sale) => SocialMEISales.matchesClient(sale, client))
    : [];
  const lastSale = [...purchases].sort((a, b) => b.data.localeCompare(a.data))[0];
  return {
    client,
    purchases,
    lastSale,
  };
}
function renderDetails(c) {
  const host = $("detailsPane");
  if (!host || !c) {
    return;
  }
  if (c._enrichmentSynthetic) {
    host.innerHTML =
      '<div class="context-body"><h3>Contato fictício</h3><p>Conversa isolada deste negócio. Não há cadastro de cliente vinculado por nome, canal conectado ou envio externo.</p></div>';
    return;
  }
  const missingFieldsExpanded = !!host.querySelector(".context-missing-fields[open]");
  const restoreFieldsFocus =
    host.querySelector(".context-missing-fields summary") === document.activeElement;
  const scroll = host.querySelector(".context-body")?.scrollTop || 0;
  const { client, purchases } = clientContext(c);
  const key = conversationKey(c);
  const since = client?.desde || client?.clienteDesde;
  const category =
    client?.categoria || (client?.status === "Novo" ? "Lead" : client ? "Cliente" : "Prospect");
  const profileFields = [
    ["Nome", displayName(c)],
    ["Telefone", client?.telefone || c.telefone],
    ["E-mail", client?.email],
    ["Cidade", client?.cidade],
    ["Cliente desde", since ? messageDateLabel(since) : null],
    ["Canal principal", channelLabel(c.canal)],
  ];
  const renderProfileField = ([label, value]) =>
    `<div><dt>${label}</dt><dd>${escapeHtml(value || "Não informado")}</dd></div>`;
  const missingFields = profileFields.filter(([, value]) => !value || value === "—");
  const tab = selectedContextTab;
  host.innerHTML = /* HTML */ `<div class="details-top">
            <div class="details-top-head">
              <b>Cliente 360</b
              ><button
                class="context-close"
                id="closeMobileDetails"
                type="button"
                aria-label="Fechar detalhes"
              >
                ${renderIcon("close")}
              </button>
            </div>
            <div class="details-profile">
              <span class="conv-avatar">${avatarContents(c)}</span>
              <div class="details-profile-copy">
                <b>${escapeHtml(displayName(c))}</b
                ><small>${channelLabel(c.canal)} · ${escapeHtml(c.usuario || "")}</small
                ><span class="pill ${category === "Lead" ? "amber" : "green"} profile-kind"
                  >${escapeHtml(category)}</span
                >
              </div>
            </div>
            <div class="context-relationship-story">
              <p>
                ${plural(purchases.length, "pedido vinculado", "pedidos vinculados")} neste
                histórico.
              </p>
              <p>
                Total do perfil
                <b>${money(client?.total || 0)}</b
                >${client?.pendente ? /* HTML */ ` · pendente <b>${money(client.pendente)}</b>` : ""}.
              </p>
            </div>
          </div>
          <div
            class="context-tabs"
            role="tablist"
            aria-label="Contexto do cliente"
            style="--tab-index:${["perfil", "historico", "vendas"].indexOf(tab)}"
          >
            ${[
              ["perfil", "Perfil"],
              ["historico", "Histórico"],
              ["vendas", "Vendas"],
            ]
              .map(
                ([id, label]) => /* HTML */ `<button
                    role="tab"
                    id="contextTab-${id}"
                    type="button"
                    data-context-tab="${id}"
                    aria-selected="${tab === id}"
                    tabindex="${tab === id ? "0" : "-1"}"
                    aria-controls="contextPanel"
                  >
                    ${label}
                  </button>`,
              )
              .join("")}
          </div>
          <div
            class="context-body"
            role="tabpanel"
            id="contextPanel"
            aria-labelledby="contextTab-${tab}"
          >
            ${
              tab === "perfil"
                ? /* HTML */ `
                    <section class="context-card context-next">
                      <span class="editorial-label">Próximo passo</span>
                      <h4>
                        ${purchases.some((sale) => sale.status === "Pendente") ? "Confirmar pagamento" : c.status === "concluido" ? "Preparar próximo contato" : "Continuar atendimento"}
                      </h4>
                      <p>
                        ${purchases.some((sale) => sale.status === "Pendente") ? "Revise a venda pendente no histórico." : "O histórico está aqui para preparar o retorno."}
                      </p>
                      <button class="lk" data-focus-note>Registrar uma nota →</button>
                    </section>
                    <section class="context-card">
                      <div class="context-card-head">
                        <h4>Informações do cliente</h4>
                        <button
                          type="button"
                          data-edit-profile
                          aria-label="Editar perfil"
                          title="Editar perfil"
                        >
                          ${renderIcon("edit")}
                        </button>
                      </div>
                      <dl class="profile-fields">${profileFields
                        .filter(([, value]) => value && value !== "—")
                        .map(renderProfileField)
                        .join("")}</dl>
                      ${missingFields.length ? `<details class="context-missing-fields" ${missingFieldsExpanded ? "open" : ""}><summary>${missingFields.length} informações não preenchidas</summary><dl class="profile-fields">${missingFields.map(renderProfileField).join("")}</dl></details>` : ""}
                    </section>
                    <section class="context-card">
                      <div class="context-card-head">
                        <h4>Tags</h4>
                        <button type="button" data-add-tag aria-label="Adicionar etiqueta">
                          ${renderIcon("plus")}
                        </button>
                      </div>
                      <div class="details-tags">
                        ${
                          (client?.tags || [])
                            .map(
                              (t) => /* HTML */ `<span class="details-tag"
                                    >${escapeHtml(t)}<button
                                      type="button"
                                      data-remove-tag="${escapeHtml(t)}"
                                      aria-label="Remover etiqueta ${escapeHtml(t)}"
                                    >
                                      ${renderIcon("close")}
                                    </button></span
                                  >`,
                            )
                            .join("") ||
                          '<span class="section-sub">Sem etiquetas. Adicione o contexto útil.</span>'
                        }
                      </div>
                    </section>
                    <section class="context-card client-note-card">
                      <div class="context-card-head">
                        <h4>Notas</h4>
                        <button type="button" data-edit-observation aria-label="Editar observação">
                          ${renderIcon("edit")}
                        </button>
                      </div>
                      <p>${escapeHtml(client?.observacao || "Nenhuma observação adicionada.")}</p>
                      ${
                        client?.observacao
                          ? /* HTML */ `<small
                              >${client.observacaoAtualizada ? "Editado por você · " + escapeHtml(localDateTime(client.observacaoAtualizada)) : "Observação cadastrada · data não informada"}</small
                            >`
                          : ""
                      }
                    </section>
                    <section class="context-card">
                      <div class="context-card-head"><h4>Atendimento</h4></div>
                      <div class="detail-row"
                        ><span>Status</span><b>${statusLabel(c.status)}</b></div
                      >
                      <div class="details-actions">
                        <button type="button" data-thread-action="status">Alterar status</button
                        ><button type="button" data-focus-note>Nota interna</button>
                      </div>
                    </section>
                  `
                : tab === "historico"
                  ? renderContextHistory(c, purchases)
                  : /* HTML */ `
                      ${
                        purchases.length
                          ? purchases
                              .map(
                                (sale) => /* HTML */ `<article class="context-sale">
                                    <div class="context-sale-head">
                                      <b>#${sale.id}</b
                                      ><span class="pill ${saleStatusClass(sale.status)}"
                                        >${escapeHtml(sale.status)}</span
                                      >
                                    </div>
                                    <p>${formatDate(sale.data)} · ${escapeHtml(sale.pagamento)}</p>
                                    <div class="context-sale-head" style="margin-bottom:10px">
                                      <b>${money(sale.valor)}</b>
                                    </div>
                                    <button
                                      class="btn"
                                      type="button"
                                      data-open-inbox-sale="${sale.id}"
                                    >
                                      Abrir venda ${renderIcon("chevron")}
                                    </button>
                                  </article>`,
                              )
                              .join("")
                          : /* HTML */ `<div class="context-empty">
                              ${renderIcon("bag")}<b>Nenhuma venda vinculada</b>As vendas
                              cadastradas para este cliente aparecerão aqui.
                            </div>`
                      }
                      <div class="context-sale-footer">
                        <button
                          class="btn pr"
                          type="button"
                          data-create-sale-name="${escapeHtml(displayName(c))}"
                        >
                          ${renderIcon("plus")} Nova venda
                        </button>
                      </div>
                    `
            }
          </div>`;
  host.querySelector(".context-body").scrollTop = scroll;
  if (restoreFieldsFocus)
    host.querySelector(".context-missing-fields summary")?.focus({ preventScroll: true });
}
function renderThread({ animate = false, preserveScroll = false, refreshList = true } = {}) {
  const conversation = getConversation();
  if (!conversation) {
    $("threadPane").classList.add("no-selection");
    $("messages").innerHTML =
      '<div class="inbox-empty"><div><span class="empty-visual">' +
      renderIcon("inbox") +
      "</span><b>Nenhum atendimento selecionado</b><span>Escolha uma conversa à esquerda para começar.</span></div></div>";
    $("detailsPane").innerHTML = "";
    return;
  }
  const deleteButton = document.querySelector('[data-thread-action="delete"]');
  if (deleteButton)
    deleteButton.hidden = conversation.mensagens.some((message) => message.remoteId);
  $("threadPane").classList.remove("no-selection");
  if (isConversationVisible(conversation) && isNearMessageBottom()) {
    conversation.naoLidas = 0;
    persistConversationState(conversation);
  }
  $("threadAvatar").innerHTML = avatarContents(conversation);
  $("threadName").textContent = displayName(conversation);
  const threadSource = conversation._enrichmentSynthetic
    ? "Mensagem fictícia · laboratório isolado"
    : conversation.mensagens.some((message) => message.remoteId)
      ? "Recebido via n8n"
      : conversation.localConversation
        ? "Conversa local"
        : "Demonstração";
  $("threadMeta").innerHTML = /* HTML */ `<span class="pill info" title="${threadSource}"
            >${channelIcon(conversation.canal)} ${channelLabel(conversation.canal)}${conversation._enrichmentSynthetic ? " · Fictício" : ""}</span
          ><span class="thread-recency" title="${threadSource}"
            >${escapeHtml(conversation.atualizado)}</span
          >`;
  $("threadStatus").value = conversation.status;
  updateFavoriteButton(conversation);
  renderMessages(conversation, {
    preserveScroll,
  });
  renderDetails(conversation);
  $("inboxShell")?.setAttribute("data-active-channel", conversation.canal || "whatsapp");
  if (refreshList) {
    renderConversationList();
  }
  updateInboxNavBadge();
  $("composerZone").hidden = !!conversation._enrichmentSynthetic;
  for (const id of ["threadStatus", "favoriteBtn", "threadMoreBtn"])
    if ($(id)) $(id).disabled = !!conversation._enrichmentSynthetic;
  window.SocialMEIMessageEnrichment?.render(conversation);
}
function hydrateLocalNotes() {
  for (const c of sessionData.conversas) {
    const replies = inboxLocalState[`replies:${conversationKey(c)}`] || [];
    for (const reply of replies) {
      if (
        reply.localMessageId &&
        !c.mensagens.some((message) => message.localMessageId === reply.localMessageId)
      ) {
        c.mensagens.push(reply);
      }
    }
    const saved = inboxLocalState[`notes:${conversationKey(c)}`];
    if (Array.isArray(saved)) {
      for (const n of saved) {
        if (!c.mensagens.some((message) => message.localNoteId === n.localNoteId)) {
          c.mensagens.push(n);
        }
      }
    }
  }
}
function applyInboxDisplayMode({ animate = false, focusList = false } = {}) {
  const view = $("inboxView");
  const shell = $("inboxShell");
  if (!view || !shell) {
    return;
  }

  // Invariante da Caixa:
  // sem uma conversa válida selecionada, o modo chat nunca pode existir.
  if (!isInboxListMode && !getConversation()) {
    isInboxListMode = true;
  }
  view.classList.toggle("inbox-list-mode", isInboxListMode);
  view.classList.toggle("inbox-conversation-mode", !isInboxListMode);
  shell.classList.toggle("list-mode", isInboxListMode);
  shell.classList.toggle("conversation-mode", !isInboxListMode);
  const listHeading = $("inboxListHeading");
  const listIntro = $("inboxListIntro");
  if (listHeading) {
    listHeading.textContent = isInboxListMode ? "Caixa Unificada" : "Conversas";
  }
  if (listIntro) {
    listIntro.textContent = isInboxListMode ? "Escolha uma pessoa para abrir o atendimento." : "";
  }
  if (isInboxListMode) {
    activeConversationId = null;
    view.classList.remove("chat-open");
    closeInboxPopovers();
    closeMobileDetails();
    document.querySelectorAll("#conversationList [data-conversation]").forEach((element) => {
      element.classList.remove("active");
      element.setAttribute("aria-selected", "false");
    });
  }
  syncMobileInert();
  queueInboxLayout();
  if (focusList) {
    requestAnimationFrame(() => {
      const target =
        $("conversationSearch") || document.querySelector("#conversationList [data-conversation]");
      target?.focus();
    });
  }
}
function enterInboxListMode({ animate = true, focusList = false } = {}) {
  if (currentView !== "Caixa Unificada") {
    return;
  }
  saveCurrentDraft();
  cancelConversationTransition();
  isInboxListMode = true;
  activeConversationId = null;
  hasPendingNewMessages = false;
  if ($("newMessagesBtn")) {
    $("newMessagesBtn").hidden = true;
  }
  toggleThreadSearch(false);
  toggleQuickReplies(false);
  if ($("threadMoreMenu")) {
    $("threadMoreMenu").hidden = true;
  }
  renderConversationList();
  applyInboxDisplayMode({
    animate,
    focusList,
  });
}
function renderInbox() {
  if (SocialMEIDemoData.enabled() && !sessionData.conversas.some((c) => c._socialmeiDemoSample))
    syncLegacySessionExamples();
  hydrateLocalNotes();
  refreshTagOptions();
  if ($("searchIcon")) {
    $("searchIcon").innerHTML = renderIcon("search");
  }
  if ($("filterIcon")) {
    $("filterIcon").innerHTML = renderIcon("filter");
  }
  if ($("simulateIncoming")) {
    $("simulateIncoming").innerHTML = renderIcon("refresh");
  }
  if ($("mobileBack")) {
    $("mobileBack").innerHTML = renderIcon("arrowLeft") + "Voltar";
  }
  if ($("mobileDetails")) {
    $("mobileDetails").innerHTML = renderIcon("detail");
  }
  if ($("threadSearchBtn")) {
    $("threadSearchBtn").innerHTML =
      renderIcon("search") + '<span class="thread-action-label">Buscar</span>';
  }
  if ($("threadMoreBtn")) {
    $("threadMoreBtn").innerHTML = renderIcon("more");
  }
  if ($("toggleDetailsBtn")) {
    $("toggleDetailsBtn").innerHTML =
      renderIcon(areInboxDetailsCollapsed ? "panelOpen" : "panel") + "<span>Cliente</span>";
  }
  if ($("threadSearchIcon")) {
    $("threadSearchIcon").innerHTML = renderIcon("search");
  }
  if ($("newMessagesIcon")) {
    $("newMessagesIcon").innerHTML = renderIcon("arrowDown");
  }
  if ($("quickReplyIcon")) {
    $("quickReplyIcon").innerHTML = renderIcon("bolt");
  }
  if ($("noteIcon")) {
    $("noteIcon").innerHTML = renderIcon("note");
  }
  if ($("sendMessage")) {
    $("sendMessage").innerHTML = "Salvar";
  }
  if ($("quickReplies")) {
    $("quickRepliesBtn").setAttribute("aria-expanded", String(!$("quickReplies").hidden));
  }
  if ($("quickReplies")) {
    $("quickReplies").innerHTML = [
      "Formas de pagamento",
      "Prazo de entrega",
      "Horários",
      "Agradecimento",
    ]
      .map(
        (t) => /* HTML */ `<button class="quick-reply" type="button" data-quick-reply="${t}">
                  ${t}
                </button>`,
      )
      .join("");
  }
  if ($("listSort")) {
    $("listSort").value = inboxSortOrder;
  }
  if ($("sortFilter")) {
    $("sortFilter").value = inboxSortOrder;
  }
  if ($("tagFilter")) {
    $("tagFilter").value = inboxSelectedTag;
  }
  $("inboxShell")?.classList.toggle("details-collapsed", areInboxDetailsCollapsed);
  renderConversationList();

  // A Caixa sempre entra pela lista. Thread/contexto só são materializados
  // visualmente depois de uma escolha explícita do usuário.
  if (!isInboxListMode && getConversation()) {
    renderThread();
  }
  applyInboxDisplayMode({
    animate: false,
  });
  updateComposerState();
}
function updateConversationSelectionDOM(previousId, nextId) {
  document.querySelectorAll("#conversationList [data-conversation]").forEach((element) => {
    const selected = Number(element.dataset.conversation) === nextId;
    element.classList.toggle("active", selected);
    element.setAttribute("aria-selected", String(selected));
    if (selected) {
      element.classList.remove("unread-item");
      element.querySelector(".unread")?.remove();
    }
  });
  updateInboxCounts();
  updateInboxNavBadge();
}
function cancelConversationTransition() {
  conversationTransitionEpoch++;
  [$("threadPane"), $("detailsPane")].forEach((element) =>
    element?.getAnimations().forEach((a) => a.cancel()),
  );
  isConversationSwitching = false;
  $("threadPane")?.removeAttribute("aria-busy");
}
/**
 * Seleciona uma conversa da Caixa e cancela transições anteriores para evitar que uma resposta atrasada troque o contexto.
 * @param {number|string} id Identificador existente da conversa.
 * @returns {Promise<void>}
 */
async function selectConversation(id) {
  const next = Number(id);
  if (currentView !== "Caixa Unificada" || !getConversation(next)) {
    return;
  }
  saveCurrentDraft();
  cancelConversationTransition();
  const epoch = conversationTransitionEpoch;
  const opening = isInboxListMode;
  const previous = activeConversationId;
  const thread = $("threadPane");
  const details = $("detailsPane");
  const motion = window.SocialMEIMotion;
  closeInboxPopovers();
  toggleThreadSearch(false);
  closeMobileDetails();
  isConversationSwitching = true;
  thread.inert = true;
  thread.setAttribute("aria-busy", "true");
  if (!opening && previous !== next && !motion.reduced) {
    await Promise.all(
      [thread, details].map((element) =>
        motion.animate(
          element,
          [
            {
              opacity: 1,
              transform: "translate3d(0,0,0)",
            },
            {
              opacity: 0,
              transform: "translate3d(0,-5px,0)",
            },
          ],
          110,
          "ease-exit",
        ),
      ),
    );
  }
  if (epoch !== conversationTransitionEpoch || currentView !== "Caixa Unificada") {
    return;
  }
  const conversation = getConversation(next);
  if (!conversation) {
    enterInboxListMode();
    return;
  }
  isInboxListMode = false;
  activeConversationId = next;
  selectedContextTab = "perfil";
  hasPendingNewMessages = false;
  $("newMessagesBtn").hidden = true;
  conversation.naoLidas = 0;
  persistConversationState(conversation);
  loadCurrentDraft();
  updateConversationSelectionDOM(previous, next);
  applyInboxDisplayMode();
  renderThread({
    refreshList: false,
  });
  details.querySelector(".context-body")?.scrollTo({
    top: 0,
  });
  isConversationSwitching = false;
  thread.removeAttribute("aria-busy");
  syncMobileInert();
  if (opening && innerWidth <= 720) {
    $("mobileBack").focus({
      preventScroll: true,
    });
  }
  if (!motion.reduced) {
    await Promise.all([
      motion.animate(
        thread,
        [
          {
            opacity: 0,
            transform: opening ? "translate3d(14px,0,0)" : "translate3d(0,7px,0)",
          },
          {
            opacity: 1,
            transform: "translate3d(0,0,0)",
          },
        ],
        opening ? 260 : 220,
        "ease-enter",
      ),
      innerWidth > 1370 && !areInboxDetailsCollapsed
        ? motion.animate(
            details,
            [
              {
                opacity: 0,
                transform: "translate3d(10px,0,0)",
              },
              {
                opacity: 1,
                transform: "translate3d(0,0,0)",
              },
            ],
            opening ? 250 : 210,
            "ease-enter",
            opening ? 55 : 20,
          )
        : Promise.resolve(),
    ]);
  }
  queueInboxLayout();
}
function nowTime() {
  return new Date().toLocaleTimeString("pt-BR", {
    timeZone: APP_TIMEZONE,
    hour: "2-digit",
    minute: "2-digit",
  });
}
function persistLocalNote(c, note) {
  const key = `notes:${conversationKey(c)}`;
  const arr = inboxLocalState[key] || [];
  arr.push(note);
  inboxLocalState[key] = arr.slice(-50);
  saveInboxLocal();
}
function sendCurrentMessage(text) {
  const conversation = getConversation();
  if (conversation?._enrichmentSynthetic) {
    toast("Sem envio externo", "Revise o rascunho no laboratório. Nenhuma resposta é enviada.");
    return;
  }
  if (isInboxListMode || isConversationSwitching || !conversation || !text.trim()) {
    return;
  }
  if (isComposerNoteMode) {
    const note = {
      de: "nota",
      texto: text.trim(),
      hora: nowTime(),
      data: todayISO(),
      localNoteId: `note-${Date.now()}`,
    };
    conversation.mensagens.push(note);
    persistLocalNote(conversation, note);
    isComposerNoteMode = false;
    updateComposerState();
    appendSingleMessage(conversation, note, true);
    recordEvent(conversation, "Nota interna adicionada");
    renderDetails(conversation);
    toast("Nota interna adicionada", "Ela não foi enviada ao cliente.");
    return;
  }
  const msg = {
    de: "empresa",
    texto: text.trim(),
    hora: nowTime(),
    data: todayISO(),
    localOnly: true,
    localMessageId: SocialMEIClients.newId(),
  };
  conversation.mensagens.push(msg);
  const localKey = `replies:${conversationKey(conversation)}`;
  inboxLocalState[localKey] = conversation.mensagens.filter((message) => message.localOnly);
  saveInboxLocal();
  conversation.atualizado = "agora";
  touchConversationActivity(conversation);
  if (conversation.status === "aberto") {
    setConversationStatus(conversation, "andamento");
  }
  persistConversationState(conversation);
  appendSingleMessage(conversation, msg, true);
  renderDetails(conversation);
  renderConversationList();
  toast("Resposta adicionada localmente", "Nenhuma mensagem foi enviada ao WhatsApp ou Instagram.");
}
function isNearMessageBottom() {
  const h = $("messages");
  return h ? h.scrollHeight - h.scrollTop - h.clientHeight < 90 : true;
}
function appendSingleMessage(c, msg, animate = true) {
  if (activeConversationId !== c.id || currentView !== "Caixa Unificada") {
    return;
  }
  const host = $("messages");
  if (!host) {
    return;
  }
  const near = isNearMessageBottom();
  const empty = host.querySelector(".inbox-empty");
  if (empty) {
    empty.remove();
  }
  const index = c.mensagens.indexOf(msg);
  const prev = c.mensagens[index - 1] || null;
  const lastSep = [...host.querySelectorAll(".day-sep")].at(-1);
  const dk = messageDateKey(msg);
  if (!lastSep || lastSep.dataset.date !== dk) {
    const sep = document.createElement("div");
    sep.className = "day-sep";
    sep.dataset.date = dk;
    sep.textContent = messageDateLabel(dk);
    host.appendChild(sep);
  }
  const wrap = document.createElement("div");
  wrap.innerHTML = messageHTML(msg, prev, animate);
  host.appendChild(wrap.firstElementChild);
  if (near) {
    requestAnimationFrame(() =>
      host.scrollTo({
        top: host.scrollHeight,
        behavior: isReducedMotion() ? "auto" : "smooth",
      }),
    );
    hasPendingNewMessages = false;
    if ($("newMessagesBtn")) {
      $("newMessagesBtn").hidden = true;
    }
  } else {
    hasPendingNewMessages = true;
    if ($("newMessagesBtn")) {
      $("newMessagesBtn").hidden = false;
    }
  }
}
function autoResizeComposer() {
  const element = $("messageInput");
  if (!element) {
    return;
  }
  element.style.height = "auto";
  element.style.height = Math.min(element.scrollHeight, 126) + "px";
}
function updateComposerState() {
  const input = $("messageInput");
  const send = $("sendMessage");
  if (!input || !send) {
    return;
  }
  send.disabled =
    isInboxListMode ||
    isConversationSwitching ||
    !getConversation() ||
    !!getConversation()?._enrichmentSynthetic ||
    !input.value.trim();
  autoResizeComposer();
  $("noteModeBtn")?.classList.toggle("active", isComposerNoteMode);
  if ($("noteModeLabel")) {
    $("noteModeLabel").textContent = isComposerNoteMode ? "Nota ativa" : "Nota interna";
  }
  $("composerZone")?.classList.toggle("note-mode", isComposerNoteMode);
  if ($("noteModeHint")) {
    $("noteModeHint").hidden = !isComposerNoteMode;
  }
  positionNewMessagesButton();
  send.textContent = isComposerNoteMode ? "Salvar nota" : "Salvar";
  send.setAttribute(
    "aria-label",
    isComposerNoteMode ? "Salvar nota interna" : "Salvar resposta local",
  );
  input.placeholder = isComposerNoteMode ? "Escreva uma nota interna..." : "Digite uma mensagem...";
  if ($("composerDemoLabel")) {
    $("composerDemoLabel").textContent = isComposerNoteMode
      ? "Nota local — não enviada"
      : "Rascunho e resposta locais";
  }
}
function openMobileDetails() {
  openContextDrawer();
}
function closeMobileDetails() {
  closeContextDrawer();
}
function toggleDetailsPanel() {
  toggleContextPanel();
}
function toggleFilterPopover(force) {
  isInboxFilterPopoverOpen = typeof force === "boolean" ? force : !isInboxFilterPopoverOpen;
  if ($("filterPopover")) {
    $("filterPopover").hidden = !isInboxFilterPopoverOpen;
  }
  if ($("filterBtn")) {
    $("filterBtn").setAttribute("aria-expanded", String(isInboxFilterPopoverOpen));
  }
}
function toggleQuickReplies(force) {
  const element = $("quickReplies");
  if (!element) {
    return;
  }
  element.hidden = typeof force === "boolean" ? !force : !element.hidden;
  $("quickRepliesBtn")?.setAttribute("aria-expanded", String(!element.hidden));
}
function toggleThreadSearch(force) {
  isThreadSearchOpen = typeof force === "boolean" ? force : !isThreadSearchOpen;
  if ($("threadSearchBar")) {
    $("threadSearchBar").hidden = !isThreadSearchOpen;
  }
  if (isThreadSearchOpen) {
    setTimeout(() => $("threadSearchInput")?.focus(), 0);
  } else {
    if ($("threadSearchInput")) {
      $("threadSearchInput").value = "";
    }
    clearThreadSearch();
  }
}
function clearThreadSearch() {
  document
    .querySelectorAll("#messages .msg.search-hit")
    .forEach((x) => x.classList.remove("search-hit"));
  if ($("threadSearchResult")) {
    $("threadSearchResult").textContent = "";
  }
}
function searchInThread() {
  clearThreadSearch();
  const searchQuery = ($("threadSearchInput")?.value || "").trim().toLowerCase();
  if (!searchQuery) {
    return;
  }
  const hits = [...document.querySelectorAll("#messages .msg")].filter((x) =>
    (x.dataset.messageText || "").includes(searchQuery),
  );
  hits.forEach((x) => x.classList.add("search-hit"));
  if ($("threadSearchResult")) {
    $("threadSearchResult").textContent = hits.length
      ? `${hits.length} encontrada${hits.length === 1 ? "" : "s"}`
      : "Nenhuma";
  }
  hits[0]?.scrollIntoView({
    block: "center",
    behavior: isReducedMotion() ? "auto" : "smooth",
  });
}
function applyInboxPreferences() {
  try {
    socialmeiStorageSet("socialmei-inbox-quick-v3", inboxQuickFilter, "o filtro da Caixa");
    socialmeiStorageSet("socialmei-inbox-sort-v3", inboxSortOrder, "a ordenação da Caixa");
    socialmeiStorageSet("socialmei-inbox-tag-v3", inboxSelectedTag, "o filtro de etiquetas");
  } catch (error) {}
}
async function addClientTag(c, label) {
  const client = SocialMEIClients.conversationClient(c);
  if (!client) {
    return false;
  }
  if (SocialMEIClients.remote) {
    return !!(await SocialMEIClients.update(client, {
      tags: [...new Set([...(client.tags || []), label])],
    }));
  }
  client.tags = client.tags || [];
  if (!client.tags.includes(label)) {
    client.tags.push(label);
  }
  saveAppData();
  return true;
}
async function removeClientTag(c, label) {
  const client = SocialMEIClients.conversationClient(c);
  if (!client) {
    return;
  }
  if (SocialMEIClients.remote) {
    const saved = await SocialMEIClients.update(client, {
      tags: (client.tags || []).filter((x) => x !== label),
    });
    if (saved) {
      renderDetails(c);
      renderConversationList();
    }
    return;
  }
  client.tags = (client.tags || []).filter((x) => x !== label);
  saveAppData();
}
function usernameFromName(name) {
  return (
    "@" +
    String(name || "cliente")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ".")
      .replace(/^\.+|\.+$/g, "")
  );
}
function displayName(conversation) {
  return clientContext(conversation).client?.nome || conversation.nome;
}
function isFavorite(c) {
  return !!inboxLocalState[`favorite:${conversationKey(c)}`];
}
function avatarContents(conversation) {
  const client = clientContext(conversation).client;
  const photo = client?.avatarUrl || client?.foto || conversation.avatarUrl || conversation.foto;
  const valid = typeof photo === "string" && /^https?:\/\//i.test(photo);
  return /* HTML */ `<span class="avatar-initials"
            >${escapeHtml(initialsFromName(displayName(conversation)))}</span
          >${valid ? /* HTML */ `<img class="avatar-photo" src="${escapeHtml(photo)}" alt="" loading="lazy" referrerpolicy="no-referrer" />` : ""}`;
}
function updateFavoriteButton(c) {
  const b = $("favoriteBtn");
  if (!b) {
    return;
  }
  b.innerHTML = renderIcon("star");
  b.setAttribute("aria-pressed", String(isFavorite(c)));
  b.setAttribute("aria-label", isFavorite(c) ? "Remover dos favoritos" : "Favoritar atendimento");
  b.title = isFavorite(c) ? "Remover dos favoritos" : "Favoritar atendimento";
}
function persistConversationState(c) {
  if (!c || c._enrichmentSynthetic) {
    return;
  }
  inboxLocalState[`state:${conversationKey(c)}`] = {
    status: c.status,
    naoLidas: c.naoLidas,
    clientId: c.clientId,
    remoteClients: c.remoteClients,
  };
  saveInboxLocal();
}
function recordEvent(c, label) {
  if (c._enrichmentSynthetic) return;
  const key = `events:${conversationKey(c)}`;
  const events = inboxLocalState[key] || [];
  events.push({
    label,
    at: new Date().toISOString(),
  });
  inboxLocalState[key] = events.slice(-100);
  saveInboxLocal();
}
function setConversationStatus(c, status) {
  if (!["aberto", "andamento", "aguardando", "concluido"].includes(status) || c.status === status) {
    return;
  }
  c.status = status;
  recordEvent(c, "Status alterado para " + statusLabel(status));
  persistConversationState(c);
}
async function ensureContextClient(c, changes = {}) {
  if (c?._socialmeiDemoSample || SocialMEIDemoData.enabled()) {
    toast(
      "Demonstração somente para leitura",
      "Desative os dados de teste para editar o cadastro comercial.",
      "info",
    );
    return null;
  }
  let client = clientContext(c).client;
  if (SocialMEIClients.remote) {
    const saved = client
      ? Object.keys(changes).length
        ? await SocialMEIClients.update(client, changes)
        : client
      : await SocialMEIClients.create({
          nome: c.nome,
          telefone: c.telefone || "—",
          instagram: c.usuario || "—",
          status: "Novo",
          tags: [],
          ...changes,
        });
    if (saved) SocialMEIClients.link(c, saved);
    return saved;
  }
  if (!client) {
    client = {
      id: Math.max(0, ...appData.clientes.map((x) => x.id)) + 1,
      nome: c.nome,
      criadoEm: new Date().toISOString(),
      telefone: c.telefone || "—",
      instagram: c.usuario || "—",
      status: "Novo",
      ultima: "Agora",
      total: 0,
      pendente: 0,
      tags: [],
      observacao: "",
    };
    appData.clientes.push(client);
  }
  c.clientId = client.id;
  saveAppData();
  persistConversationState(c);
  return client;
}
function renderContextHistory(c, purchases) {
  const events = [...(inboxLocalState[`events:${conversationKey(c)}`] || [])];
  const notes = c.mensagens.filter((message) => message.de === "nota");
  notes.forEach((m) => {
    if (
      !events.some((e) => e.label === "Nota interna adicionada" && e.at.slice(0, 10) === m.data)
    ) {
      events.push({
        label: "Nota interna registrada",
        at: null,
        detail: m.hora || "",
        date: m.data,
      });
    }
  });
  const dated = c.mensagens
    .filter((message) => message.remoteId && message.data)
    .sort((message, otherMessage) => message.data.localeCompare(otherMessage.data));
  if (dated.length) {
    events.push({
      label: "Primeira mensagem recebida registrada",
      date: dated[0].data,
      detail: dated[0].hora,
    });
  }
  purchases.forEach((sale) =>
    events.push({
      label: `Venda #${sale.id} · ${money(sale.valor)}`,
      date: sale.data,
      detail: `Status atual: ${sale.status}`,
    }),
  );
  if (!events.length) {
    return /* HTML */ `<div class="context-empty">
            ${renderIcon("note")}<b>Sem eventos registrados</b>Mudanças de status, notas e vendas
            aparecerão aqui. Datas ausentes não são estimadas.
          </div>`;
  }
  events.sort((a, b) => (b.at || b.date || "").localeCompare(a.at || a.date || ""));
  return /* HTML */ `<ol class="timeline">
          ${events
            .map(
              (event) => /* HTML */ `<li>
                    <b>${escapeHtml(event.label)}</b
                    ><small
                      >${event.at ? escapeHtml(localDateTime(event.at)) : event.date ? formatDate(event.date) : "Data não informada"}${event.detail ? " · " + escapeHtml(event.detail) : ""}</small
                    >
                  </li>`,
            )
            .join("")}
        </ol>`;
}
function refreshTagOptions() {
  const tags = [
    ...new Set([
      "Novo cliente",
      "Orçamento",
      "Pagamento",
      "Pós-venda",
      "Urgente",
      ...businessViewData().clientes.flatMap((client) => client.tags || []),
    ]),
  ].sort((a, b) => a.localeCompare(b, "pt-BR"));
  $("tagFilter").innerHTML =
    '<option value="all">Todas</option>' +
    tags
      .map((t) => /* HTML */ `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`)
      .join("");
  $("tagFilter").value = tags.includes(inboxSelectedTag) ? inboxSelectedTag : "all";
}
async function openTagPicker(anchor) {
  const conversation = getConversation();
  if (!conversation) {
    return;
  }
  if (!(await ensureContextClient(conversation))) return;
  const pop = $("tagPicker");
  const assigned = clientContext(conversation).client.tags || [];
  const tags = [
    ...new Set([
      "Cliente",
      "Orçamento",
      "Pagamento",
      "Pós-venda",
      "Interesse: Produto",
      ...appData.clientes.flatMap((client) => client.tags || []),
    ]),
  ];
  pop.innerHTML = /* HTML */ `<div class="tag-picker-head">
            <b>Adicionar etiqueta</b
            ><button type="button" data-close-tag-picker aria-label="Fechar etiquetas">
              ${renderIcon("close")}
            </button>
          </div>
          <div class="tag-options">
            ${tags
              .map(
                (t) => /* HTML */ `<button
                      type="button"
                      data-pick-tag="${escapeHtml(t)}"
                      ${assigned.includes(t) ? "disabled" : ""}
                    >
                      ${escapeHtml(t)}
                    </button>`,
              )
              .join("")}
          </div>
          <form class="tag-create" id="tagCreateForm">
            <input
              class="field"
              name="tag"
              placeholder="Criar nova etiqueta"
              aria-label="Nova etiqueta"
              maxlength="60"
              required
            /><button class="btn pr" type="submit" aria-label="Criar etiqueta">
              ${renderIcon("plus")}
            </button>
          </form>`;
  pop.hidden = false;
  pop._anchor = anchor;
  positionTagPicker();
  pop.querySelector("input").focus();
}
function positionTagPicker() {
  const pop = $("tagPicker");
  if (!pop || pop.hidden) {
    return;
  }
  const r = pop._anchor?.getBoundingClientRect();
  if (!r) {
    return;
  }
  pop.style.left = Math.max(12, Math.min(r.left, innerWidth - pop.offsetWidth - 12)) + "px";
  pop.style.top = Math.max(12, Math.min(r.bottom + 8, innerHeight - pop.offsetHeight - 12)) + "px";
}
async function finishTag(label) {
  label = label.trim().slice(0, 60);
  const conversation = getConversation();
  if (!label || !conversation) {
    return;
  }
  if (!(await ensureContextClient(conversation))) return;
  if (await addClientTag(conversation, label)) {
    recordEvent(conversation, "Etiqueta adicionada: " + label);
    refreshTagOptions();
    renderDetails(conversation);
    renderConversationList();
    $("tagPicker").hidden = true;
    updateInboxNavBadge();
    toast("Etiqueta adicionada", label);
  }
}
function closeInboxPopovers() {
  if ($("composerMoreMenu")) {
    $("composerMoreMenu").hidden = true;
  }
  toggleQuickReplies(false);
  toggleFilterPopover(false);
  if ($("tagPicker")) {
    $("tagPicker").hidden = true;
  }
  if ($("threadMoreMenu")) {
    $("threadMoreMenu").hidden = true;
  }
}
function saveCurrentDraft() {
  const conversation = getConversation();
  if (conversation?._enrichmentSynthetic) return;
  if (conversation) {
    conversationDrafts.set(conversation.id, {
      text: $("messageInput").value,
      note: isComposerNoteMode,
    });
  }
}
function loadCurrentDraft() {
  const conversation = getConversation();
  const draft = conversationDrafts.get(conversation?.id);
  $("messageInput").value = draft?.text || "";
  isComposerNoteMode = !!draft?.note;
  renderAttachmentPreview();
  updateComposerState();
}
function renderAttachmentPreview() {
  const item = attachmentDrafts.get(activeConversationId);
  const host = $("attachmentPreview");
  host.hidden = !item;
  host.innerHTML = item
    ? /* HTML */ `${item.url ? /* HTML */ `<img src="${escapeHtml(item.url)}" alt="Prévia do anexo local" />` : renderIcon("attach")}
              <div class="attachment-copy">
                <b>${escapeHtml(item.file.name)}</b
                ><small
                  >${(item.file.size / 1024).toFixed(1)} KB · Anexo local — integração de envio
                  necessária.</small
                >
              </div>
              <button type="button" id="removeAttachment" aria-label="Remover anexo local">
                ${renderIcon("close")}
              </button>`
    : "";
  positionNewMessagesButton();
}
function removeAttachment() {
  const item = attachmentDrafts.get(activeConversationId);
  if (item?.url) {
    URL.revokeObjectURL(item.url);
  }
  attachmentDrafts.delete(activeConversationId);
  $("attachmentInput").value = "";
  renderAttachmentPreview();
}
function positionNewMessagesButton() {
  const zone = $("composerZone");
  if (zone && $("newMessagesBtn")) {
    $("newMessagesBtn").style.bottom = zone.offsetHeight + 12 + "px";
  }
}
function isConversationVisible(c) {
  return (
    !!c &&
    !isInboxListMode &&
    activeConversationId === c.id &&
    currentView === "Caixa Unificada" &&
    document.visibilityState !== "hidden" &&
    (innerWidth > 720 || $("inboxView").classList.contains("chat-open"))
  );
}
function syncMobileInert() {
  const mobile = innerWidth <= 720;
  $("inboxView").classList.toggle("chat-open", mobile && !isInboxListMode);
  const chat = $("inboxView").classList.contains("chat-open");
  const context = $("detailsPane").classList.contains("mobile-open");
  const listMode = isInboxListMode;
  setAccessibleInert(document.querySelector("#inboxView .conv-pane"), context || (mobile && chat));
  setAccessibleInert(
    $("threadPane"),
    isConversationSwitching || listMode || context || (mobile && !chat),
  );
  if ($("detailsPane")) {
    setAccessibleInert(
      $("detailsPane"),
      listMode || (!context && (innerWidth <= 1370 || areInboxDetailsCollapsed)),
    );
  }
}
let inboxLayoutFrame = 0;
function queueInboxLayout() {
  if (inboxLayoutFrame) {
    return;
  }
  inboxLayoutFrame = requestAnimationFrame(() => {
    inboxLayoutFrame = 0;
    sizeInbox();
  });
}
function sizeInbox() {
  if (currentView !== "Caixa Unificada") {
    return;
  }
  const shell = $("inboxShell");
  const viewport = window.visualViewport;
  const bottom = viewport ? viewport.height + viewport.offsetTop : innerHeight;
  const top = shell.getBoundingClientRect().top;
  const padding = innerWidth <= 720 ? 0 : innerWidth <= 900 ? 8 : 12;
  shell.style.setProperty("--inbox-height", Math.max(0, bottom - top - padding) + "px");
  positionNewMessagesButton();
  positionTagPicker();
  syncMobileInert();
  const toggle = $("toggleDetailsBtn");
  if (toggle) {
    const narrow = innerWidth <= 1370;
    const open = narrow
      ? $("detailsPane").classList.contains("mobile-open")
      : !areInboxDetailsCollapsed;
    toggle.innerHTML = renderIcon(open ? "panel" : "panelOpen") + "<span>Cliente</span>";
    toggle.setAttribute("aria-label", open ? "Ocultar cliente" : "Mostrar cliente");
    toggle.title = open ? "Ocultar cliente" : "Mostrar cliente";
    toggle.setAttribute("aria-expanded", String(open));
  }
}
function openContextDrawer() {
  const pane = $("detailsPane");
  if (!getConversation()) {
    return;
  }
  contextReturnFocusElement = document.activeElement;
  pane.classList.add("mobile-open");
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-modal", "true");
  $("detailsBackdrop").hidden = false;
  $("detailsBackdrop").classList.add("mobile-open");
  syncShellInert();
  pane.querySelector(".context-close")?.focus();
  sizeInbox();
}
function closeContextDrawer() {
  const pane = $("detailsPane");
  const was = pane.classList.contains("mobile-open");
  pane.classList.remove("mobile-open");
  pane.removeAttribute("role");
  pane.removeAttribute("aria-modal");
  $("detailsBackdrop").classList.remove("mobile-open");
  $("detailsBackdrop").hidden = true;
  syncShellInert();
  if (was && contextReturnFocusElement?.isConnected) {
    contextReturnFocusElement.focus();
  }
  sizeInbox();
}
function toggleContextPanel() {
  if (innerWidth <= 1370) {
    if ($("detailsPane").classList.contains("mobile-open")) {
      closeContextDrawer();
    } else {
      openContextDrawer();
    }
    return;
  }
  areInboxDetailsCollapsed = !areInboxDetailsCollapsed;
  try {
    socialmeiStorageSet(
      "socialmei-inbox-details-v3",
      areInboxDetailsCollapsed ? "collapsed" : "open",
      "a preferência do painel de cliente",
    );
  } catch (error) {}
  $("inboxShell").classList.toggle("details-collapsed", areInboxDetailsCollapsed);
  sizeInbox();
}
function openInboxModal(title, content, submitLabel = "Salvar", mode = "profile") {
  const conversation = getConversation();
  modalConversationId = conversation?.id;
  const modal = $("inboxModal");
  modal.dataset.mode = mode;
  modal._clientVersion = clientContext(getConversation() || { nome: "" }).client?.versao;
  $("inboxModalTitle").textContent = title;
  $("inboxModalContent").innerHTML = content.replace(/\b(id|for)="f_/g, '$1="inbox_f_');
  $("inboxModalSubmit").textContent = submitLabel;
  openModal("inboxModal");
}
function openProfileEditor() {
  const conversation = getConversation();
  if (!conversation) {
    return;
  }
  const client = clientContext(conversation).client;
  openInboxModal(
    "Editar perfil do cliente",
    /* HTML */ `<div class="form-grid">
              ${createField("Nome", "nome", "text", {
                value: displayName(conversation),
                required: true,
                full: true,
              })}
              ${createField("Telefone", "telefone", "tel", {
                value: client?.telefone || conversation.telefone || "",
              })}
              ${createField("Instagram / @usuário", "instagram", "text", {
                value: client?.instagram || conversation.usuario || "",
              })}
              ${createField("E-mail", "email", "email", {
                value: client?.email || "",
              })}
              ${createField("Cidade", "cidade", "text", {
                value: client?.cidade || "",
              })}
              ${createField("Cliente desde (se conhecido)", "desde", "date", {
                value: client?.desde || "",
              })}
              ${createField("Relacionamento", "categoria", "select", {
                value: client?.categoria || (client?.status === "Novo" ? "Lead" : "Cliente"),
                options: ["Cliente", "Lead", "Prospect"],
              })}
            </div>
            <p class="section-sub" style="margin-top:12px"
              >Alterações salvas apenas neste navegador.</p
            >`,
  );
}
function openObservationEditor() {
  const conversation = getConversation();
  if (!conversation) {
    return;
  }
  openInboxModal(
    "Editar nota do cliente",
    createField("Observação interna", "observacao", "textarea", {
      value: clientContext(conversation).client?.observacao || "",
    }) + '<p class="section-sub" style="margin-top:10px">Não será enviada ao cliente.</p>',
    "Salvar nota",
    "observation",
  );
}
function openStatusModal(c) {
  openInboxModal(
    "Status do atendimento",
    /* HTML */ `<label class="form-group"
            ><span class="section-sub">Escolha o estado do atendimento</span
            ><select class="form-control" name="status">
              ${["aberto", "andamento", "aguardando", "concluido"]
                .map(
                  (st) => /* HTML */ `<option value="${st}" ${st === c.status ? "selected" : ""}>
                        ${statusLabel(st)}
                      </option>`,
                )
                .join("")}
            </select></label
          >`,
    "Salvar status",
    "status",
  );
}
function openNewConversation() {
  openInboxModal(
    "Nova conversa local",
    /* HTML */ `<div class="local-feature-note">
              Protótipo local. Iniciar uma conversa no WhatsApp ou Instagram depende da integração
              de saída. Nenhuma mensagem será enviada ao contato.
            </div>
            <div class="form-grid">
              ${createField("Canal", "canal", "select", {
                options: ["WhatsApp", "Instagram"],
              })}
              ${createField("Cliente", "nome", "text", {
                required: true,
              })}
              <div class="form-group full contact-input-group">
                <label for="inbox_f_contato" id="inboxContactLabel">Telefone · Brasil (+55)</label>
                <input class="form-control" id="inbox_f_contato" name="contato" type="tel" inputmode="tel" autocomplete="tel" maxlength="32" required data-contact-type="phone" data-contact-status="inboxContactError" aria-describedby="inboxContactHint inboxContactError" placeholder="(81) 99999-0000">
                <small id="inboxContactHint">DDD + número. Outro país? Use +código do país.</small>
                <small id="inboxContactError" class="contact-input-error" aria-live="polite"></small>
              </div>
              ${createField("Mensagem inicial (opcional, somente local)", "mensagem", "textarea")}
            </div>`,
    "Criar conversa local",
    "conversation",
  );
  const channel = $("inboxModalForm").elements.canal;
  const values = { WhatsApp: "", Instagram: "" };
  let previousChannel = channel.value;
  channel.addEventListener("change", () => {
    const input = $("inbox_f_contato");
    values[previousChannel] = input.value;
    previousChannel = channel.value;
    const instagram = channel.value === "Instagram";
    input.value = values[channel.value];
    input.type = instagram ? "text" : "tel";
    input.inputMode = instagram ? "text" : "tel";
    input.autocomplete = instagram ? "off" : "tel";
    input.maxLength = instagram ? 31 : 32;
    input.dataset.contactType = instagram ? "instagram" : "phone";
    input.placeholder = instagram ? "@seu.usuario" : "(81) 99999-0000";
    input.setCustomValidity("");
    input.removeAttribute("aria-invalid");
    $("inboxContactError").textContent = "";
    $("inboxContactLabel").textContent = instagram
      ? "Usuário do Instagram"
      : "Telefone · Brasil (+55)";
    $("inboxContactHint").textContent = instagram
      ? "Use o @usuário, não o telefone ou o link do perfil."
      : "DDD + número. Outro país? Use +código do país.";
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      input.closest(".contact-input-group").animate(
        [
          { opacity: 0.5, transform: "translateY(4px)" },
          { opacity: 1, transform: "none" },
        ],
        { duration: window.SocialMEIMotion.ms("motion-base"), easing: "ease-out" },
      );
    }
  });
}

function openDeleteConversation(conversation) {
  if (conversation.mensagens.some((message) => message.remoteId)) {
    toast(
      "Conversa integrada",
      "A exclusão no canal ainda não está disponível. Você pode concluir o atendimento.",
    );
    return;
  }
  openInboxModal(
    "Excluir esta conversa?",
    `<p>O histórico local de <strong>${escapeHtml(displayName(conversation))}</strong> será removido deste navegador.</p><p>O cadastro do cliente, as vendas e os lançamentos financeiros serão preservados. Nada será apagado no WhatsApp ou Instagram.</p>`,
    "Excluir conversa local",
    "delete-conversation",
  );
}

function removeLocalConversation(conversation) {
  if (!conversation || conversation.mensagens.some((message) => message.remoteId)) return false;
  const previousState = structuredClone(inboxLocalState);
  const key = conversationKey(conversation);
  inboxLocalState.localConversations = (inboxLocalState.localConversations || []).filter(
    (item) => conversationKey(item) !== key,
  );
  for (const prefix of ["state:", "events:", "favorite:"]) delete inboxLocalState[prefix + key];
  if (!conversation.localConversation) {
    inboxLocalState.removedDemoConversations = [
      ...new Set([...(inboxLocalState.removedDemoConversations || []), key]),
    ];
  }
  if (!saveInboxLocal()) {
    inboxLocalState = previousState;
    return false;
  }
  sessionData.conversas = sessionData.conversas.filter((item) => item.id !== conversation.id);
  conversationDrafts.delete(conversation.id);
  attachmentDrafts.delete(conversation.id);
  return true;
}

async function copyContact(c) {
  const client = clientContext(c).client;
  const contact =
    c.canal === "instagram" ? client?.instagram || c.usuario : client?.telefone || c.telefone;
  if (!contact || contact === "—") {
    toast("Contato não informado", "Adicione o contato no perfil.");
    return;
  }
  try {
    await navigator.clipboard.writeText(contact);
    toast("Contato copiado");
  } catch (error) {
    openInboxModal(
      "Copiar contato",
      /* HTML */ `<label class="form-group"
              ><span>Selecione e copie o contato</span
              ><input class="form-control" readonly value="${escapeHtml(contact)}"
            /></label>`,
      "Fechar",
      "copy",
    );
  }
}
function renderInboxIcons() {
  $("composerMoreBtn").innerHTML = renderIcon("more");
  $("threadTagBtn").innerHTML =
    renderIcon("tag") + '<span class="thread-action-label">Etiquetas</span>';
  $("favoriteBtn").innerHTML = renderIcon("star");
  $("mentionClientBtn").innerHTML =
    renderIcon("mention") + '<span class="action-label">Citar cliente</span>';
  $("mentionClientBtn").setAttribute("aria-label", "Citar cliente");
  $("attachBtn").innerHTML = renderIcon("attach") + '<span class="action-label">Anexar</span>';
  $("attachBtn").setAttribute("aria-label", "Anexar arquivo local");
  $("toggleDetailsBtn").setAttribute("aria-controls", "detailsPane");
  $("quickRepliesBtn").setAttribute("aria-controls", "quickReplies");
}
function themeMini(theme) {
  const t = THEMES.build(theme);
  const vars = [...Object.entries(t), ...Object.entries(THEMES.aliases).map(([k, v]) => [k, t[v]])]
    .map(([k, v]) => `--${k}:${v}`)
    .join(";");
  return /* HTML */ `<div class="theme-mini" style="${vars}" aria-hidden="true">
          <div class="theme-mini-side"><i></i><i></i><i></i><i></i></div>
          <div class="theme-mini-main">
            <i></i>
            <div class="theme-mini-cards"><span></span><span></span><span></span></div>
            <em></em>
          </div>
        </div>`;
}
function colorControl(key, label, value, advanced = false) {
  const prefix = advanced ? "adv-" : "basic-";
  const id = "theme-" + prefix + key;
  return /* HTML */ `<div class="theme-control">
          <label for="${id}-hex">${label}</label>
          <div class="theme-color-pair">
            <input
              type="color"
              id="${id}-picker"
              aria-label="Escolher ${label.toLowerCase()}"
              value="${value}"
              data-theme-color="${key}"
              data-theme-advanced="${advanced}"
            /><input
              class="form-control"
              type="text"
              id="${id}-hex"
              aria-label="${label} em HEX"
              value="${value}"
              maxlength="7"
              spellcheck="false"
              pattern="#[0-9a-fA-F]{6}"
              data-theme-color="${key}"
              data-theme-advanced="${advanced}"
            />
          </div>
        </div>`;
}
