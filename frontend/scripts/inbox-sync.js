/* INBOX SYNC */
function syncElapsed() {
  if (!lastSyncAt) {
    return "";
  }
  const secs = Math.max(0, Math.floor((Date.now() - lastSyncAt) / 1000));
  return secs < 10
    ? "Sincronizado agora"
    : secs < 60
      ? `Atualizado há ${plural(secs, "segundo")}`
      : `Atualizado há ${plural(Math.floor(secs / 60), "minuto")}`;
}
function updateSyncLabels() {
  const text = {
    idle: "Sincronização disponível",
    loading: "Sincronizando conversas…",
    success: syncElapsed(),
    empty: syncElapsed(),
    error: "Não foi possível sincronizar",
    offline: "Sem conexão",
  }[syncState];
  if ($("integrationStatus")) {
    $("integrationStatus").textContent = text;
  }
  if ($("channelConnectionText")) {
    $("channelConnectionText").textContent = text;
  }
  if ($("topSync")) {
    $("topSync").textContent = text;
    $("topSync").dataset.state = syncState;
  }
}
function normalizeRemoteText(value) {
  const original = String(value ?? "");
  if (!/[ÃÂ]/.test(original)) {
    return original;
  }
  try {
    return decodeURIComponent(escape(original));
  } catch (error) {
    return original;
  }
}
function safeRemoteHttpUrl(value) {
  if (typeof value !== "string" || !value.trim()) {
    return "";
  }
  try {
    const url = new URL(value, location.href);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
  } catch (_) {
    return "";
  }
}
function remoteSinceValue(item) {
  const value = item?.horario;
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString();
}
function remoteHour(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? nowTime()
    : d.toLocaleTimeString("pt-BR", {
        timeZone: APP_TIMEZONE,
        hour: "2-digit",
        minute: "2-digit",
      });
}
function remoteDate(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? todayISO()
    : d.toLocaleDateString("en-CA", {
        timeZone: APP_TIMEZONE,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
}
function setIntegrationStatus(text, state = "wait") {
  syncState =
    {
      ok: "success",
      wait: "loading",
      err: "error",
      offline: "offline",
      empty: "empty",
      idle: "idle",
    }[state] || state;
  const pill = $("integrationPill");
  if (pill) {
    pill.className = "integration-pill " + syncState;
    pill.title = text;
    pill.setAttribute("aria-busy", String(syncState === "loading"));
  }
  const alert = $("integrationAlert");
  if (alert) {
    alert.hidden = !["error", "offline"].includes(syncState);
    if ($("integrationAlertText")) {
      $("integrationAlertText").textContent =
        syncState === "offline"
          ? "Você está offline. Conversas locais preservadas."
          : "Sincronização indisponível. Conversas locais preservadas.";
    }
  }
  const channelDot = document.querySelector("#dashboardView .meta .dot");
  if (channelDot) {
    channelDot.style.background = ["success", "empty"].includes(syncState)
      ? "var(--success)"
      : syncState === "error"
        ? "var(--ng)"
        : syncState === "loading"
          ? "var(--amber)"
          : "var(--mt)";
  }
  updateSyncLabels();
  if (currentView === "Configurações" && selectedSettingsTab === "integracoes") {
    renderSettings();
  }
  queueInboxLayout();
}

// Dados do webhook são normalizados ao entrar e escapados com esc() em todo HTML renderizado.
// Fotos remotas só são aceitas quando usam http(s).
function mergeRemoteMessage(item) {
  if (!item || !item.id || REMOTE_MESSAGE_IDS.has(String(item.id))) {
    return null;
  }
  const nome = normalizeRemoteText(item.cliente || "Cliente").trim() || "Cliente";
  const canal = String(item.canal || "whatsapp")
    .toLowerCase()
    .includes("insta")
    ? "instagram"
    : "whatsapp";
  const texto = normalizeRemoteText(item.mensagem || "").trim();
  if (!texto) {
    return null;
  }
  REMOTE_MESSAGE_IDS.add(String(item.id));
  let c = sessionData.conversas.find(
    (conversation) =>
      conversation.nome.toLowerCase() === nome.toLowerCase() && conversation.canal === canal,
  );
  let created = false;
  if (!c) {
    const nextId =
      Math.max(0, ...sessionData.conversas.map((conversation) => Number(conversation.id) || 0)) + 1;
    const remotePhoto = safeRemoteHttpUrl(item.foto || item.avatarUrl || item.avatar || "");
    c = {
      id: nextId,
      nome,
      iniciais: initialsFromName(nome),
      canal,
      status: "aberto",
      telefone: "—",
      usuario: usernameFromName(nome),
      naoLidas: 0,
      atualizado: "agora",
      mensagens: [],
      ...(remotePhoto
        ? {
            avatarUrl: remotePhoto,
          }
        : {}),
    };
    sessionData.conversas.unshift(c);
    created = true;
    const storedState = inboxLocalState[`state:${conversationKey(c)}`];
    if (storedState?.clientId) {
      c.clientId = storedState.clientId;
    }
    if (
      !SocialMEIClients.remote &&
      !appData.clientes.some(
        (client) => client.id === c.clientId || client.nome.toLowerCase() === nome.toLowerCase(),
      )
    ) {
      const clientId = Math.max(0, ...appData.clientes.map((client) => client.id)) + 1;
      appData.clientes.unshift({
        id: clientId,
        nome,
        telefone: "—",
        instagram: canal === "instagram" ? usernameFromName(nome) : "—",
        status: "Novo",
        ultima: "Agora",
        total: 0,
        pendente: 0,
        observacao: `Contato recebido pelo ${channelLabel(canal)} via n8n.`,
        tags: ["Novo cliente"],
      });
      saveAppData();
    }
  }
  const msg = {
    de: "cliente",
    texto,
    hora: remoteHour(item.horario),
    data: remoteDate(item.horario),
    remoteId: String(item.id),
  };
  c.mensagens.push(msg);
  c.atualizado = "agora";
  touchConversationActivity(c);
  if (c.status === "concluido") {
    c.status = "aberto";
  }
  const isOpen = isConversationVisible(c) && isNearMessageBottom();
  if (!isOpen) {
    c.naoLidas += 1;
  }
  if (
    appData.prefs.notificacoes !== false &&
    appData.prefs.notifications?.message !== false &&
    !isQuietPeriodActive()
  ) {
    sessionData.notificacoes.unshift({
      t: "Nova mensagem recebida via n8n",
      s: `${nome} pelo ${channelLabel(canal)} · agora`,
    });
  }
  sessionData.atividade.unshift({
    t: "msg",
    a: "Mensagem recebida",
    b: `${nome} · “${texto}”`,
    w: "agora",
  });
  const remoteSince = remoteSinceValue(item);
  if (remoteSince && (!lastRemoteMessageAt || remoteSince > lastRemoteMessageAt)) {
    lastRemoteMessageAt = remoteSince;
  }
  return {
    conversation: c,
    message: msg,
    created,
    isOpen,
  };
}
/**
 * Consulta o endpoint configurado, normaliza dados remotos e preserva o trabalho local quando a rede falha. Não abre conversas automaticamente.
 */
async function syncN8nMessages(showFeedback = false) {
  if (isN8nSyncing || !document.body.classList.contains("experience-app")) {
    return {
      checked: false,
      added: 0,
    };
  }
  if (!navigator.onLine) {
    isN8nConnected = false;
    setIntegrationStatus("Sem conexão com a internet", "offline");
    if (showFeedback) {
      toast("Você está offline", "A sincronização será retomada quando a conexão voltar.");
    }
    return {
      checked: false,
      added: 0,
    };
  }
  isN8nSyncing = true;
  syncError = null;
  setIntegrationStatus("Sincronizando conversas…", "wait");
  if (!sessionData.conversas.length && $("conversationList")) {
    $("conversationList").innerHTML = loadingConversations();
  }
  if ($("simulateIncoming")) {
    $("simulateIncoming").disabled = true;
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    let requestUrl = N8N_MESSAGES_URL;
    if (N8N_USE_SINCE && lastRemoteMessageAt) {
      const url = new URL(N8N_MESSAGES_URL);
      url.searchParams.set("since", lastRemoteMessageAt);
      requestUrl = url.toString();
    }
    const headers = {
      Accept: "application/json",
    };
    if (SOCIALMEI_CONFIG.n8nAuthHeader) {
      headers.Authorization = SOCIALMEI_CONFIG.n8nAuthHeader;
    }
    const res = await fetch(requestUrl, {
      method: "GET",
      cache: "no-store",
      headers,
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error("HTTP " + res.status);
    }
    const data = await res.json();
    if (!data || !Array.isArray(data.mensagens)) {
      throw new Error("Resposta de mensagens inválida");
    }
    const list = data.mensagens;
    const added = [];
    for (const item of list) {
      const r = mergeRemoteMessage(item);
      if (r) {
        added.push(r);
      }
    }
    hydrateLocalNotes();
    isN8nConnected = true;
    lastSyncAt = new Date();
    setIntegrationStatus(
      list.length ? "Mensagens sincronizadas" : "Conectado · nenhuma mensagem remota",
      list.length ? "ok" : "empty",
    );
    if (added.length) {
      updateInboxNavBadge();
      renderNotifications();
      renderChannelSummary();
      renderActivityFeed();
      renderAttention();
      if (currentView === "Caixa Unificada") {
        renderConversationList();

        // Sincronização nunca abre uma conversa sozinha.
        // A entrada na thread é sempre consequência de um clique do usuário.
        if (!isInboxListMode && !getConversation()) {
          isInboxListMode = true;
          applyInboxDisplayMode({
            animate: false,
          });
        }
        if (!isInboxListMode) {
          for (const r of added) {
            if (
              r.conversation.id === activeConversationId &&
              isConversationVisible(r.conversation)
            ) {
              appendSingleMessage(r.conversation, r.message, true);
            }
          }
          if (getConversation()) {
            renderDetails(getConversation());
          }
        }
      }
      for (const r of added) {
        persistConversationState(r.conversation);
      }
    }
    if (
      added.length &&
      appData.prefs.notificacoes !== false &&
      appData.prefs.notifications?.message !== false &&
      !isQuietPeriodActive()
    ) {
      toast(
        plural(added.length, "nova mensagem", "novas mensagens"),
        "Conversas atualizadas pelo n8n.",
      );
    } else if (showFeedback) {
      toast(
        "Dados sincronizados",
        list.length ? "As conversas estão atualizadas." : "Nenhuma mensagem retornada pelo n8n.",
      );
    }
    return {
      checked: true,
      added: added.length,
    };
  } catch (err) {
    console.info("Sincronização indisponível; conversas locais preservadas.");
    isN8nConnected = false;
    syncError = err;
    setIntegrationStatus("Não foi possível sincronizar as conversas.", "err");
    if (showFeedback) {
      toast(
        "Não foi possível sincronizar",
        "Tente novamente. As conversas locais continuam disponíveis.",
      );
    }
    if (currentView === "Caixa Unificada") {
      // Erro remoto não destrói a experiência local.
      // Se não houver uma conversa válida escolhida, volta obrigatoriamente
      // para a lista centralizada.
      if (!getConversation()) {
        isInboxListMode = true;
      }
      renderConversationList();
      applyInboxDisplayMode({
        animate: false,
      });
      if (!isInboxListMode && getConversation()) {
        renderThread({
          preserveScroll: true,
        });
      }
    }
    return {
      checked: true,
      added: 0,
      error: true,
    };
  } finally {
    clearTimeout(timeout);
    isN8nSyncing = false;
    if ($("simulateIncoming")) {
      $("simulateIncoming").disabled = false;
    }
  }
}
function resetN8nBackoff() {
  n8nBackoffLevel = 0;
}
function scheduleN8nSync(result = null) {
  clearTimeout(n8nSyncTimer);
  n8nSyncTimer = null;
  if (document.hidden || !navigator.onLine || !document.body.classList.contains("experience-app")) {
    return;
  }
  if (result?.added > 0) {
    n8nBackoffLevel = 0;
  }
  const delay = N8N_POLL_DELAYS[n8nBackoffLevel];
  if (result?.checked && !result?.added) {
    n8nBackoffLevel = Math.min(n8nBackoffLevel + 1, N8N_POLL_DELAYS.length - 1);
  }
  n8nSyncTimer = setTimeout(async () => {
    n8nSyncTimer = null;
    const nextResult = await syncN8nMessages(false);
    scheduleN8nSync(nextResult);
  }, delay);
}
function wakeN8nSync() {
  resetN8nBackoff();
  if (document.hidden || !navigator.onLine || !document.body.classList.contains("experience-app")) {
    return;
  }
  clearTimeout(n8nSyncTimer);
  n8nSyncTimer = null;
  n8nSyncTimer = setTimeout(async () => {
    n8nSyncTimer = null;
    const result = await syncN8nMessages(false);
    scheduleN8nSync(result);
  }, N8N_POLL_DELAYS[0]);
}
["pointerdown", "keydown"].forEach((type) => {
  document.addEventListener(
    type,
    (event) => {
      if (
        n8nBackoffLevel > 0 &&
        currentView === "Caixa Unificada" &&
        event.target.closest?.("#inboxView")
      ) {
        wakeN8nSync();
      }
    },
    type === "pointerdown"
      ? {
          passive: true,
        }
      : false,
  );
});
function startN8nSync() {
  clearTimeout(n8nSyncTimer);
  n8nSyncTimer = null;
  resetN8nBackoff();
  if (document.hidden || !navigator.onLine || !document.body.classList.contains("experience-app")) {
    return;
  }
  if (!isN8nSyncing) {
    syncN8nMessages(false).then(scheduleN8nSync);
  } else {
    scheduleN8nSync();
  }
}
