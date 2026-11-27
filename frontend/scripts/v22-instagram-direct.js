/* Human-reviewed Direct outbox in the native inbox. Never auto-approves or auto-sends. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInstagramDirect) return;
  const states = new Map();
  let readiness = null,
    readinessScope = null,
    loading = null;
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const canWrite = () => ["owner", "admin", "member"].includes(host.identity?.papel);
  const canSend = () =>
    ["owner", "admin"].includes(host.identity?.papel) &&
    readiness?.send_enabled === true &&
    readiness?.incoming_available === true &&
    readiness?.account_connected === true;
  const labels = {
    draft: "Rascunho salvo",
    approved: "Aprovada · ainda não enviada",
    dispatching: "Envio iniciado · consulte antes de continuar",
    confirmed: "Aceita pela Meta · entrega não verificada",
    retry_ready: "Aguardando intervalo para nova tentativa",
    failed: "Recusada pela Meta",
    uncertain: "Resultado incerto · não repita o envio",
    cancelled: "Cancelada",
  };
  const tones = {
    draft: "info",
    approved: "info",
    dispatching: "warn",
    confirmed: "ok",
    retry_ready: "warn",
    failed: "err",
    uncertain: "warn",
    cancelled: "info",
  };
  const ui = () => window.SocialMEIAtendimentoUI;
  const when = (job) => (ui() ? ui().stamp(job.updated_at || job.created_at) : "");
  const element = (type, text) => {
    const n = document.createElement(type);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  function selected() {
    const match = /^#\/caixa\/(me-\d+)$/.exec(location.hash);
    const row = match && host.conversation(match[1]);
    return row?.origin === "instagram" ? row : null;
  }
  function stateFor(row) {
    const key = scope() + ":" + row.id;
    if (!states.has(key)) {
      const state = {
        scope: scope(),
        conversation: row.id,
        text: "",
        job: null,
        jobs: [],
        busy: false,
        pending: null,
        lastRead: 0,
        storageKey: "socialmei-instagram-direct-pending-v1:" + key,
      };
      try {
        const raw = sessionStorage.getItem(state.storageKey);
        if (raw) {
          const pending = JSON.parse(raw);
          if (
            !pending ||
            !/^[a-f0-9-]{36}$/i.test(pending.operation_id) ||
            !Number.isSafeInteger(pending.source_message_id) ||
            pending.source_message_id < 1 ||
            typeof pending.text !== "string" ||
            !pending.text.trim() ||
            new TextEncoder().encode(pending.text).length > 1000
          )
            throw Error("Registro pendente inválido.");
          state.pending = pending;
          state.text = pending.text;
        }
      } catch {
        state.storageError = true;
      }
      states.set(key, state);
    }
    return states.get(key);
  }
  function matchesReceipt(state, row) {
    return (
      row &&
      typeof row.id === "string" &&
      /^[a-f0-9-]{36}$/i.test(row.id) &&
      row.conversation_id === state.conversation &&
      row.source_message_id === state.pending?.source_message_id &&
      row.text === state.pending?.text &&
      Object.hasOwn(labels, row.status)
    );
  }
  function clearPending(state, row) {
    if (!matchesReceipt(state, row)) return false;
    try {
      if (sessionStorage.getItem(state.storageKey) !== JSON.stringify(state.pending))
        throw Error("Registro local mudou.");
      sessionStorage.removeItem(state.storageKey);
      state.pending = null;
      return true;
    } catch {
      state.storageError = true;
      return false;
    }
  }
  function message(state, text) {
    state.message = text;
    if (selected()?.id === state.conversation) paint();
  }
  async function configuration(force = false) {
    const identity = scope();
    if (force || readinessScope !== identity) readiness = null;
    if (readiness) return readiness;
    if (!loading || loading.scope !== identity) {
      const current = { scope: identity };
      current.promise = host
        .request("/integrations/readiness")
        .then(async (r) => {
          const result = r.instagram || {};
          const connection = await host.request("/instagram/meta/status");
          if (identity !== scope()) return null;
          readinessScope = identity;
          return (readiness = {
            ...result,
            account_connected:
              connection.status === "connected" && connection.credential_available === true,
          });
        })
        .catch(() => null)
        .finally(() => {
          if (loading === current) loading = null;
        });
      loading = current;
    }
    return loading.promise;
  }
  async function refresh(state, force = false) {
    if (state.reading || (!force && Date.now() - state.lastRead < 5000)) return;
    state.reading = true;
    state.lastRead = Date.now();
    try {
      const result = await host.request("/instagram/direct/jobs");
      if (state.scope !== scope()) return;
      const rows = result.items.filter((job) => job.conversation_id === state.conversation);
      const changed = JSON.stringify(state.jobs) !== JSON.stringify(rows);
      state.jobs = rows;
      if (state.job) state.job = rows.find((job) => job.id === state.job.id) || state.job;
      let recovered = false;
      if (state.pending && !state.storageError) {
        try {
          const receipt = await host.request(
            "/instagram/direct/operations/" + state.pending.operation_id,
          );
          if (state.scope !== scope()) return;
          if (!clearPending(state, receipt))
            throw Error("Registro do servidor difere do rascunho salvo. Não repita.");
          state.job = receipt;
          state.text = receipt.text;
          window.SocialMEIDrafts?.clear("me-" + state.conversation);
          recovered = true;
          state.message = "Rascunho recuperado do servidor. Nenhuma mensagem foi enviada.";
        } catch (error) {
          if (error.status !== 404) {
            state.message = error.message || "Não foi possível conferir a operação pendente.";
            if (state.storageError) state.message += " Não crie outra resposta.";
          } else {
            state.message = "Registro ainda não confirmado. Recupere usando o mesmo identificador.";
          }
        }
      }
      if ((changed || recovered) && selected()?.id === state.conversation) window.render();
    } catch (error) {
      message(state, error.message || "Não foi possível consultar as respostas.");
    } finally {
      state.reading = false;
      if (selected()?.id === state.conversation) paint();
    }
  }
  /* A janela de revisão reúne confirmação, tentativa e resultado. Aprovação e envio seguem a ordem original. */
  async function review(state) {
    if (!state.job || state.busy) return;
    const job = Object.freeze({ ...state.job }),
      row = selected(),
      identity = scope();
    const sendable = canSend() && ["draft", "approved", "retry_ready"].includes(job.status);
    const blocked = !["draft", "approved", "retry_ready"].includes(job.status)
      ? "Esta resposta já tem um resultado. Consulte o histórico antes de preparar outra."
      : [
          !["owner", "admin"].includes(host.identity?.papel) ? "Somente responsáveis pelo negócio podem enviar." : "",
          readiness?.send_enabled !== true ? "O envio de respostas ainda não foi habilitado para este negócio." : "",
          readiness?.account_connected !== true ? "A conta do Instagram não está conectada." : "",
        ].filter(Boolean)[0] || "Envio indisponível no momento. Seu rascunho continua salvo.";
    dialogOpen = true;
    await ui().review({
      title: "Revisar antes de enviar",
      channelLabel: "Instagram Direct",
      recipient: row?.contact_name,
      text: job.text,
      canConfirm: sendable,
      blockedReason: blocked,
      note: "Ao confirmar, esta mensagem será enviada de verdade ao contato.",
      confirmLabel: "Confirmar envio",
      sendingText: "Registrando a tentativa. Não feche esta janela.",
      run: async () => {
        if (state.busy || !canSend() || identity !== scope())
          return { tone: "warn", title: "Envio indisponível", text: "Nada foi enviado. Consulte as respostas e tente de novo." };
        state.busy = true;
        paint();
        try {
          let current = job;
          if (current.status === "draft")
            current = await host.request(
              "/instagram/direct/jobs/" + current.id + "/approve",
              "POST",
              { operation_id: crypto.randomUUID(), expected_revision: current.revision },
            );
          if (identity !== scope()) return { tone: "warn", title: "Negócio alterado", text: "Nada foi confirmado neste negócio." };
          current = await host.request("/instagram/direct/jobs/" + current.id + "/run", "POST", {
            expected_revision: job.revision,
          });
          if (identity !== scope()) return { tone: "warn", title: "Negócio alterado", text: "Nada foi confirmado neste negócio." };
          state.job = current;
          message(state, labels[current.status] || "Consulte o estado da resposta.");
          state.busy = false;
          await refresh(state, true);
          if (current.status === "confirmed")
            return { tone: "ok", title: "Aceita pela Meta", text: "A entrega e a leitura não são verificadas por este painel." };
          if (current.status === "failed")
            return { tone: "err", title: "Recusada pela Meta", text: "A mensagem não foi enviada. Revise o texto antes de preparar outra resposta." };
          if (current.status === "uncertain")
            return { tone: "warn", title: "Resultado incerto", text: "Não sabemos se a mensagem saiu. Confira no Instagram antes de escrever outra. Nada será reenviado automaticamente." };
          return { tone: "warn", title: labels[current.status] || "Consulte a situação", text: "Consulte as respostas para ver o resultado. Nada será reenviado automaticamente." };
        } catch (error) {
          const text =
            (error.message || "Não foi possível confirmar o envio.") +
            " Consulte as respostas antes de qualquer nova tentativa. Nada será repetido automaticamente.";
          message(state, text);
          state.busy = false;
          await refresh(state, true);
          return { tone: "err", title: "Resultado não confirmado", text };
        } finally {
          state.busy = false;
          paint();
        }
      },
    });
    dialogOpen = false;
  }
  let dialogOpen = false;
  async function startNew(state) {
    if (state.busy || state.pending || state.storageError) return;
    if (
      state.jobs.some((j) => ["uncertain", "dispatching", "confirmed"].includes(j.status)) &&
      !(await ui().confirm({
        title: "Preparar outra resposta?",
        body: "Já existe uma tentativa iniciada ou confirmada nesta conversa. Confira o histórico para não repetir a mesma resposta.",
        confirmLabel: "Preparar outra",
        cancelLabel: "Conferir histórico",
        tone: "warn",
        icon: "warn",
      }))
    ) {
      openHistory(state);
      return;
    }
    state.job = null;
    state.text = "";
    state.message = "";
    paint();
    document.getElementById("ta")?.focus();
  }
  function openHistory(state) {
    if (state.busy || state.pending || state.storageError) return;
    ui().history({
      title: "Respostas do Instagram",
      items: state.jobs.map((j) => ({ id: j.id, tone: tones[j.status], label: labels[j.status] || j.status, text: j.text, time: when(j) })),
      selectedId: state.job?.id,
      canNew: !!state.job && canWrite(),
      onNew: () => startNew(state),
      onPick: (id) => {
        state.job = state.jobs.find((j) => j.id === id) || null;
        state.text = state.job?.text || "";
        state.message = "";
        paint();
      },
    });
  }
  function stageOf(state) {
    if (state.pending) return "pending";
    const status = state.job?.status;
    if (!status) return "compose";
    if (["draft", "approved", "retry_ready"].includes(status)) return state.busy ? "sending" : "review";
    if (status === "confirmed") return "accepted";
    if (status === "dispatching") return "sending";
    if (status === "failed" || status === "cancelled") return "blocked";
    return "uncertain";
  }
  async function prepare(state, row, input) {
    if (state.busy || state.job || state.storageError || !canWrite()) return;
    if (!state.pending) {
      const source = row.messages?.at(-1)?.id,
        text = input.value;
      if (
        !Number.isSafeInteger(source) ||
        !text.trim() ||
        new TextEncoder().encode(text).length > 1000
      ) {
        message(state, "Informe uma resposta de até 1000 bytes.");
        return;
      }
      const pending = {
        operation_id: crypto.randomUUID(),
        source_message_id: source,
        text,
      };
      try {
        sessionStorage.setItem(state.storageKey, JSON.stringify(pending));
      } catch {
        state.storageError = true;
        message(state, "Não foi possível preservar a operação. Nenhum registro foi enviado.");
        paint();
        return;
      }
      state.pending = pending;
    }
    state.busy = true;
    paint();
    try {
      // A lost response must be recovered by GET or by replaying this exact UUID.
      const job = await host.request("/instagram/direct/jobs", "POST", state.pending);
      if (state.scope !== scope()) return;
      if (!clearPending(state, job)) throw Error("Registro divergente. Não prepare outra resposta.");
      state.job = job;
      state.text = job.text;
      window.SocialMEIDrafts?.clear("me-" + state.conversation);
      message(state, "Rascunho salvo no servidor. Nenhuma mensagem foi enviada.");
      await refresh(state, true);
    } catch (error) {
      if (state.scope === scope())
        message(
          state,
          (error.message || "Resultado da preparação não confirmado.") +
            " A mesma operação será usada para recuperar o registro.",
        );
    } finally {
      state.busy = false;
      paint();
    }
  }
  function paint() {
    const row = selected();
    if (!row || !readiness?.reply_preparation_available || !ui()) return;
    const state = stateFor(row),
      composer = document.querySelector(".ct .cp"),
      input = document.getElementById("ta");
    if (!composer || !input) return;
    composer.querySelector("[data-ig-reply-unavailable]")?.remove();
    const label = composer.querySelector(".row > b");
    if (label) label.textContent = "Resposta humana";
    input.value = state.job?.text || state.pending?.text || state.text;
    input.disabled =
      !canWrite() || state.busy || !!state.job || !!state.pending || state.storageError;
    input.oninput = () => {
      state.text = input.value;
      paint();
    };
    const stage = stageOf(state),
      bytes = new TextEncoder().encode(input.value).length,
      empty = !input.value.trim();
    const sendOn = canSend();
    const base = {
      compose: ["Escreva a resposta. Nada é enviado sem a sua confirmação.", "info"],
      pending: [
        state.busy
          ? "Salvando o rascunho no servidor…"
          : "O registro ainda não foi confirmado. Recupere a mesma operação antes de escrever outra.",
        state.busy ? "busy" : "warn",
      ],
      review: [
        state.job?.status === "approved"
          ? "Aprovada, mas ainda não enviada. Revise e confirme para enviar."
          : sendOn
            ? "Rascunho salvo. Revise e confirme para enviar."
            : "Rascunho salvo no servidor. O envio está desativado.",
        "info",
      ],
      sending: ["Envio iniciado. Consulte antes de continuar.", "busy"],
      accepted: ["Aceita pela Meta. A entrega e a leitura não são verificadas.", "ok"],
      uncertain: ["Resultado incerto. Confira no Instagram; não repita o envio.", "warn"],
      blocked: [labels[state.job?.status] + ". Nada foi enviado; você pode preparar outra resposta.", state.job?.status === "failed" ? "err" : "info"],
    }[stage];
    let msg = state.message || base[0],
      tone = state.message && stage === "compose" ? "warn" : base[1];
    if (!canWrite() && !state.message) {
      msg = "Seu acesso permite consultar as respostas, mas não preparar ou enviar.";
      tone = "info";
    }
    if (state.storageError) {
      msg = "Operação pendente não pode ser validada neste navegador. Nenhuma nova resposta será criada.";
      tone = "err";
    }
    const primary = state.job
      ? ["draft", "approved", "retry_ready"].includes(state.job.status)
        ? { label: "Revisar e enviar", icon: "eye", disabled: state.busy || state.storageError, onClick: () => review(state) }
        : { label: "Nova resposta", icon: "plus", disabled: state.busy || !canWrite(), onClick: () => startNew(state) }
      : {
          label: state.pending ? "Recuperar registro" : "Preparar resposta",
          icon: state.pending ? "refresh" : "save",
          disabled: state.busy || state.storageError || !canWrite() || (!state.pending && (empty || bytes > 1000)),
          onClick: () => prepare(state, row, input),
        };
    const source = row.messages?.at(-1);
    ui().update(composer, {
      channel: "instagram",
      attr: "igReply",
      stage,
      tone,
      message: msg,
      busy: state.busy || state.reading,
      quote: source?.direction !== "outgoing" ? String(source?.text || "").replace(/\s+/g, " ").slice(0, 120) : "",
      primary,
      history: { count: state.jobs.length, disabled: state.busy || !!state.pending || state.storageError || !state.jobs.length, onClick: () => openHistory(state) },
      refresh: {
        busy: !!state.reading,
        disabled: state.busy || !!state.reading,
        onClick: async () => {
          await configuration(true);
          paint();
          await refresh(state, true);
        },
      },
      counter: state.job || state.pending ? null : { used: bytes, max: 1000 },
      banner: sendOn
        ? { state: "on", title: "Envio com confirmação", detail: "toda resposta passa por revisão." }
        : { state: "off", title: "Envio desativado", detail: "é possível preparar e revisar rascunhos." },
      footer: sendOn
        ? "Nada é enviado automaticamente. Cada resposta exige a sua confirmação."
        : "Preparação salva no servidor. Envio externo desativado.",
    });
    const assistant = document.querySelector('.ct .hd [data-a="ai"]');
    if (assistant) {
      assistant.disabled = true;
      assistant.title = "Geração automática por IA ainda não conectada.";
    }
  }
  async function mount() {
    const row = selected();
    if (!row) return;
    const identity = scope();
    const config = await configuration();
    if (identity !== scope() || selected()?.id !== row.id) return;
    const composer = document.querySelector(".ct .cp");
    composer?.querySelector("[data-ig-reply-unavailable]")?.remove();
    if (!config) {
      if (composer) {
        const section = element("section");
        section.dataset.igReplyUnavailable = "true";
        section.className = "sm-conn-foot sm-conn-unavailable";
        const feedback = element("p", "Não foi possível consultar a conexão do Instagram.");
        feedback.setAttribute("role", "status");
        feedback.className = "sm-status";
        feedback.dataset.tone = "err";
        const retry = element("button", "Consultar conexão novamente");
        retry.className = "sm-tool";
        retry.type = "button";
        retry.onclick = async () => {
          retry.disabled = true;
          await mount();
        };
        section.append(feedback, retry);
        composer.append(section);
      }
      return;
    }
    if (!config.reply_preparation_available) return;
    paint();
    await refresh(stateFor(row));
  }
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      const result = render.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => {
    if (dialogOpen) ui()?.closeAll();
  });
  window.SocialMEIInstagramDirect = {
    confirmed(id) {
      const row = host.conversation(id);
      if (!row) return [];
      return stateFor(row)
        .jobs.filter((j) => j.status === "confirmed" && j.provider_message_id)
        .map((j) => ({
          id: "direct-" + j.id,
          text: j.text,
          direction: "outgoing",
          occurred_at: j.updated_at,
        }));
    },
  };
  queueMicrotask(mount);
})();
