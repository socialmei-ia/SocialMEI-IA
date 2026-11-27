/* Human replies use a durable server operation; never retry provider dispatch. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIWhatsAppReplies) return;
  const states = new Map();
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const canWrite = () => ["owner", "admin", "member"].includes(host.identity?.papel);
  const labels = {
    draft: "Rascunho salvo",
    dispatching: "Envio iniciado · consulte antes de continuar",
    confirmed: "Aceita para envio · entrega não verificada",
    uncertain: "Resultado incerto · não repita o envio",
  };
  function selected() {
    const match = /^#\/caixa\/(me-\d+)$/.exec(location.hash);
    const row = match && host.conversation(match[1]);
    return row?.origin === "waha" ? row : null;
  }
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function stateFor(row) {
    const key = scope() + ":" + row.id;
    if (!states.has(key)) {
      const state = { scope: scope(), id: row.id, jobs: [], text: "", busy: false, loaded: false };
      state.key = "socialmei-whatsapp-reply-pending-v1:" + key;
      try {
        state.pending = JSON.parse(localStorage.getItem(state.key) || "null");
        if (
          state.pending &&
          (!/^[a-f0-9-]{36}$/.test(state.pending.operation_id) ||
            !Number.isSafeInteger(state.pending.source_message_id) ||
            typeof state.pending.text !== "string")
        )
          throw Error("invalid pending operation");
      } catch {
        state.storageError = true;
      }
      states.set(key, state);
    }
    return states.get(key);
  }
  const current = (state) => state.scope === scope() && selected()?.id === state.id;
  function valid(job, state) {
    return (
      job &&
      typeof job.id === "string" &&
      job.conversation_id === state.id &&
      typeof job.text === "string" &&
      Object.hasOwn(labels, job.status)
    );
  }
  function clearPending(state, job) {
    const pending = state.pending;
    if (
      !pending ||
      job.id !== pending.operation_id ||
      job.source_message_id !== pending.source_message_id ||
      job.text !== pending.text
    )
      return false;
    localStorage.removeItem(state.key);
    state.pending = null;
    return true;
  }
  async function refresh(state) {
    if (state.busy) return;
    state.busy = true;
    paint();
    try {
      const result = await host.request("/whatsapp/replies?conversation_id=" + state.id);
      if (!current(state)) return;
      if (
        !Array.isArray(result.items) ||
        !result.items.every((job) => valid(job, state)) ||
        typeof result.send_enabled !== "boolean"
      )
        throw Error("Estado das respostas não reconhecido.");
      state.jobs = result.items;
      state.enabled = result.send_enabled;
      state.loaded = true;
      const recovered =
        state.pending && state.jobs.find((job) => job.id === state.pending.operation_id);
      if (recovered) {
        if (!clearPending(state, recovered))
          throw Error("Registro divergente; não repita a resposta.");
        state.job = recovered;
        window.SocialMEIDrafts?.clear("me-" + state.id);
      } else if (state.job)
        state.job = state.jobs.find((job) => job.id === state.job.id) || state.job;
      state.message = state.pending
        ? "Registro não confirmado. Consulte ou repita somente o registro pendente."
        : "";
      window.render();
    } catch (error) {
      if (current(state)) {
        state.enabled = false;
        state.loaded = false;
        state.message = error.message || "Não foi possível consultar as respostas.";
      }
    } finally {
      state.busy = false;
      paint();
    }
  }
  async function prepare(state, row, input) {
    if (state.busy || !canWrite() || state.job || state.storageError || !state.loaded) return;
    state.busy = true;
    try {
      if (!state.pending) {
        const text = input.value,
          source = row.messages?.at(-1)?.id;
        if (
          !Number.isSafeInteger(source) ||
          !text.trim() ||
          new TextEncoder().encode(text).length > 4096
        )
          throw Error("Informe uma resposta de até 4096 bytes.");
        const pending = { operation_id: crypto.randomUUID(), source_message_id: source, text };
        localStorage.setItem(state.key, JSON.stringify(pending));
        state.pending = pending;
      }
      paint();
      const job = await host.request("/whatsapp/replies", "POST", state.pending);
      if (!current(state)) return;
      if (!valid(job, state) || !clearPending(state, job))
        throw Error("Registro divergente; consulte as respostas antes de continuar.");
      state.job = job;
      state.jobs = [job, ...state.jobs.filter((item) => item.id !== job.id)];
      state.message = "Rascunho salvo no servidor e bot pausado. Nenhuma mensagem foi enviada.";
      window.SocialMEIDrafts?.clear("me-" + state.id);
    } catch (error) {
      if (current(state))
        state.message =
          (error.message || "Registro não confirmado.") +
          (state.pending ? " A mesma operação será usada ao repetir o registro." : "");
    } finally {
      state.busy = false;
      paint();
    }
  }
  const ui = () => window.SocialMEIAtendimentoUI;
  const tones = { draft: "info", dispatching: "warn", confirmed: "ok", uncertain: "warn" };
  const when = (job) => (ui() ? ui().stamp(job.finished_at || job.created_at) : "");
  /* A janela de revisão é a confirmação: nada é enviado sem o clique em "Confirmar envio". */
  async function send(state) {
    if (state.busy || !current(state) || !canWrite() || state.job?.status !== "draft") return;
    const job = state.job,
      row = selected();
    const result = await ui().review({
      title: "Revisar antes de enviar",
      channelLabel: "WhatsApp",
      recipient: row?.contact_name,
      text: job.text,
      canConfirm: !!state.enabled,
      blockedReason: "O envio externo está desativado para este negócio. O rascunho continua salvo no servidor.",
      note: "Ao confirmar, esta mensagem será enviada de verdade ao contato.",
      confirmLabel: "Confirmar envio",
      sendingText: "Enviando. Não feche esta janela.",
      run: async () => {
        if (state.busy || !state.enabled || !current(state))
          return { tone: "warn", title: "Envio indisponível", text: "Nada foi enviado. Consulte as respostas e tente de novo." };
        state.busy = true;
        // A lost response must be reconciled by GET, never by repeating dispatch.
        state.enabled = false;
        paint();
        try {
          const result = await host.request("/whatsapp/replies/" + job.id + "/send", "POST", {});
          if (!current(state)) return { tone: "warn", title: "Conversa alterada", text: "Consulte as respostas desta conversa antes de continuar." };
          if (!valid(result, state) || result.id !== job.id) throw Error("Resultado não reconhecido.");
          state.job = result;
          state.jobs = state.jobs.map((item) => (item.id === result.id ? result : item));
          state.message = labels[result.status];
          window.render();
          if (result.status === "confirmed")
            return { tone: "ok", title: "Aceita para envio", text: "A entrega e a leitura não são verificadas por este painel." };
          if (result.status === "uncertain")
            return { tone: "warn", title: "Resultado incerto", text: "Não sabemos se a mensagem saiu. Confira no WhatsApp antes de escrever outra. Nada será reenviado automaticamente." };
          return { tone: "warn", title: "Envio em andamento", text: "Consulte as respostas para ver o resultado. Nada será reenviado automaticamente." };
        } catch (error) {
          if (current(state))
            state.message =
              (error.message || "Resultado não confirmado.") +
              " Consulte as respostas. O envio não será repetido automaticamente.";
          return { tone: "err", title: "Resultado não confirmado", text: (error.message || "Não foi possível confirmar.") + " Consulte as respostas antes de qualquer nova tentativa. Nada será repetido automaticamente." };
        } finally {
          state.busy = false;
          paint();
        }
      },
    });
    if (result && current(state)) refresh(state);
  }
  async function startNew(state) {
    if (state.busy || state.pending) return;
    if (
      state.job &&
      !(await ui().confirm({
        title: "Preparar outra resposta?",
        body: "Confira o histórico antes para não repetir uma mensagem que já foi preparada ou enviada.",
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
    if (state.busy || state.pending) return;
    ui().history({
      title: "Respostas do WhatsApp",
      items: state.jobs.map((job) => ({ id: job.id, tone: tones[job.status], label: labels[job.status], text: job.text, time: when(job) })),
      selectedId: state.job?.id,
      canNew: !!state.job && canWrite(),
      onNew: () => startNew(state),
      onPick: (id) => {
        state.job = state.jobs.find((job) => job.id === id) || null;
        state.text = state.job?.text || "";
        state.message = "";
        paint();
      },
    });
  }
  function stageOf(state) {
    if (!state.loaded && state.busy) return "loading";
    if (state.pending) return "pending";
    const status = state.job?.status;
    if (!status) return "compose";
    if (status === "draft") return state.busy ? "sending" : "review";
    if (status === "confirmed") return "accepted";
    if (status === "dispatching") return "sending";
    return "uncertain";
  }
  function paint() {
    const row = selected();
    if (!row || !ui()) return;
    const state = stateFor(row),
      composer = document.querySelector(".ct .cp"),
      input = document.getElementById("ta");
    if (!composer || !input) return;
    const stage = stageOf(state),
      bytes = new TextEncoder().encode(input.value).length;
    input.value = state.job?.text || state.pending?.text || state.text;
    input.disabled =
      !canWrite() || state.busy || !!state.job || !!state.pending || state.storageError;
    input.oninput = () => {
      state.text = input.value;
      paint();
    };
    const empty = !input.value.trim(),
      over = new TextEncoder().encode(input.value).length > 4096;
    const base = {
      compose: ["Escreva a resposta. Nada é enviado sem a sua confirmação.", "info"],
      loading: ["Carregando respostas desta conversa…", "busy"],
      pending: ["O registro ainda não foi confirmado. Recupere a mesma operação antes de escrever outra.", "warn"],
      review: [state.enabled ? "Rascunho salvo. Revise e confirme para enviar." : "Rascunho salvo no servidor. O envio está desativado.", "info"],
      sending: ["Envio iniciado. Consulte antes de continuar.", "busy"],
      accepted: ["Aceita para envio. A entrega e a leitura não são verificadas.", "ok"],
      uncertain: ["Resultado incerto. Confira no WhatsApp; não repita o envio.", "warn"],
    }[stage];
    if (state.busy && state.pending && !state.job) base.pending = ["Salvando o rascunho no servidor…", "busy"];
    let message = state.message || base[0],
      tone = state.message && stage === "compose" ? "warn" : base[1];
    if (!state.loaded && !state.busy && !state.message) {
      message = "Não foi possível consultar as respostas. Toque em Atualizar.";
      tone = "err";
    }
    if (!canWrite() && !state.message) {
      message = "Seu acesso permite consultar as respostas, mas não preparar ou enviar.";
      tone = "info";
    }
    if (state.storageError) {
      message = "Não foi possível recuperar a operação pendente deste navegador. Nenhum novo registro será criado.";
      tone = "err";
    }
    const primary = state.job
      ? state.job.status === "draft"
        ? { label: "Revisar e enviar", icon: "eye", disabled: state.busy || !canWrite(), onClick: () => send(state) }
        : { label: "Nova resposta", icon: "plus", disabled: state.busy || !canWrite(), onClick: () => startNew(state) }
      : {
          label: state.pending ? "Recuperar registro" : "Preparar resposta",
          icon: state.pending ? "refresh" : "save",
          disabled: state.busy || !canWrite() || !state.loaded || state.storageError || (!state.pending && (empty || over)),
          onClick: () => prepare(state, row, input),
        };
    const source = row.messages?.at(-1);
    ui().update(composer, {
      channel: "whatsapp",
      attr: "waReplies",
      stage,
      tone,
      message,
      busy: state.busy,
      quote: source?.direction !== "outgoing" ? String(source?.text || "").replace(/\s+/g, " ").slice(0, 120) : "",
      primary,
      history: { count: state.jobs.length, disabled: state.busy || !!state.pending || !state.jobs.length, onClick: () => openHistory(state) },
      refresh: { busy: state.busy && state.loaded, disabled: state.busy, onClick: () => refresh(state) },
      counter: state.job || state.pending ? null : { used: bytes, max: 4096 },
      banner: !state.loaded
        ? null
        : state.enabled
        ? { state: "on", title: "Envio com confirmação", detail: "toda resposta passa por revisão." }
        : { state: "off", title: "Envio desativado", detail: "os rascunhos ficam salvos no servidor." },
      footer: !state.loaded
        ? ""
        : state.enabled
        ? "Nada é enviado automaticamente. Cada resposta exige a sua confirmação."
        : "Envio externo desativado. Rascunhos ficam salvos no servidor.",
    });
  }
  function mount() {
    const row = selected();
    if (!row) return;
    const state = stateFor(row);
    paint();
    if (!state.started) {
      state.started = true;
      refresh(state);
    }
  }
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      const result = render.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.SocialMEIWhatsAppReplies = {
    confirmed(id) {
      const row = host.conversation(id);
      if (row?.origin !== "waha") return [];
      return stateFor(row)
        .jobs.filter((job) => job.status === "confirmed" && job.provider_message_id)
        .map((job) => ({
          id: "wa-reply-" + job.id,
          text: job.text,
          direction: "outgoing",
          occurred_at: job.finished_at || job.created_at,
          provider: "waha",
        }));
    },
  };
  queueMicrotask(mount);
})();
