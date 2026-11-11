/* Human replies use a durable server operation; never retry provider dispatch. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIWhatsAppReplies) return;
  const states = new Map();
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const canWrite = () => ["owner", "admin", "member"].includes(host.identity?.papel);
  const labels = {
    draft: "Rascunho no servidor",
    dispatching: "Tentativa iniciada; consulte antes de continuar",
    confirmed: "Aceita pelo WAHA; entrega e leitura não verificadas",
    uncertain: "Resultado incerto; não repita o envio",
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
  async function send(state) {
    if (
      state.busy ||
      !current(state) ||
      !canWrite() ||
      !state.enabled ||
      state.job?.status !== "draft"
    )
      return;
    const job = state.job;
    if (!confirm("Enviar de verdade para o contato desta conversa?\n\n" + job.text)) return;
    state.busy = true;
    // A lost response must be reconciled by GET, never by repeating dispatch.
    state.enabled = false;
    paint();
    try {
      const result = await host.request("/whatsapp/replies/" + job.id + "/send", "POST", {});
      if (!current(state)) return;
      if (!valid(result, state) || result.id !== job.id) throw Error("Resultado não reconhecido.");
      state.job = result;
      state.jobs = state.jobs.map((item) => (item.id === result.id ? result : item));
      state.message = labels[result.status];
      window.render();
    } catch (error) {
      if (current(state))
        state.message =
          (error.message || "Resultado não confirmado.") +
          " Consulte as respostas. O envio não será repetido automaticamente.";
    } finally {
      state.busy = false;
      paint();
    }
  }
  function paint() {
    const row = selected();
    if (!row) return;
    const state = stateFor(row),
      composer = document.querySelector(".ct .cp"),
      input = document.getElementById("ta");
    if (!composer || !input) return;
    let section = composer.querySelector("[data-wa-replies]");
    if (!section) {
      section = element("section");
      section.dataset.waReplies = "true";
      section.className = "wa-human";
      const status = element("p");
      status.dataset.waReplyStatus = "true";
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      const history = element("select");
      history.setAttribute("aria-label", "Respostas WhatsApp registradas");
      history.onchange = () => {
        if (state.busy || state.pending) return;
        if (
          !history.value &&
          state.job &&
          !confirm("Confira o histórico antes de preparar outra resposta. Continuar?")
        ) {
          history.value = state.job.id;
          return;
        }
        state.job = state.jobs.find((job) => job.id === history.value) || null;
        state.text = state.job?.text || "";
        state.message = "";
        paint();
      };
      const reload = element("button", "Consultar respostas");
      reload.type = "button";
      reload.onclick = () => refresh(state);
      const dispatch = element("button", "Revisar e confirmar envio");
      dispatch.type = "button";
      dispatch.dataset.waSend = "true";
      dispatch.onclick = () => send(state);
      section.append(
        element("strong", "Resposta humana · WhatsApp"),
        status,
        history,
        reload,
        dispatch,
      );
      composer.append(section);
      composer.querySelectorAll(".k10-ax").forEach((node) => {
        node.hidden = true;
        node.style.display = "none";
      });
    }
    section.setAttribute("aria-busy", String(state.busy));
    input.value = state.job?.text || state.pending?.text || state.text;
    input.disabled =
      !canWrite() || state.busy || !!state.job || !!state.pending || state.storageError;
    input.oninput = () => {
      state.text = input.value;
      paint();
    };
    const button =
      composer.querySelector("[data-wa-prepare]") || composer.querySelector('[data-a^="salvar:"]');
    if (button) {
      button.removeAttribute("data-a");
      button.dataset.waPrepare = "true";
      button.textContent = state.pending
        ? "Repetir registro pendente"
        : "Preparar resposta no servidor";
      button.disabled =
        state.busy ||
        !canWrite() ||
        !state.loaded ||
        !!state.job ||
        state.storageError ||
        (!state.pending && !input.value.trim());
      button.onclick = (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        prepare(state, row, input);
      };
    }
    const history = section.querySelector("select");
    history.replaceChildren(element("option", "Nova resposta"));
    history.firstChild.value = "";
    for (const job of state.jobs) {
      const option = element("option", labels[job.status] + " · " + job.text.slice(0, 40));
      option.value = job.id;
      history.append(option);
    }
    history.value = state.job?.id || "";
    history.disabled = state.busy || !!state.pending;
    section.querySelector("[data-wa-send]").disabled =
      state.busy || !canWrite() || !state.enabled || state.job?.status !== "draft";
    section.querySelector("button:not([data-wa-send])").disabled = state.busy;
    section.querySelector("[data-wa-reply-status]").textContent = state.storageError
      ? "Não foi possível recuperar a operação pendente deste navegador. Nenhum novo registro será criado."
      : state.message ||
        (state.job
          ? labels[state.job.status]
          : state.loaded
            ? "Prepare um rascunho para pausar o bot. Nada é enviado automaticamente."
            : "Consulte as respostas antes de preparar uma mensagem.");
    const warning = document.querySelector(".ct .hd .wn");
    if (warning)
      warning.textContent = state.enabled
        ? "Envio exige revisão e confirmação."
        : "Envio externo desativado. Rascunhos ficam no servidor.";
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
  const style = element("style");
  style.textContent =
    ".wa-human{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}.wa-human strong,.wa-human p{width:100%;overflow-wrap:anywhere}.wa-human select{flex:1 1 100%;min-width:0}.wa-human button,.wa-human select{min-height:44px;max-width:100%;padding:9px;color:var(--t);background:var(--w);border:1px solid var(--b);border-radius:9px;font:inherit}";
  document.head.append(style);
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
