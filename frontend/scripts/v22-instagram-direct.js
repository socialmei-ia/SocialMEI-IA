/* Human-reviewed Direct outbox in the native inbox. Never auto-approves or auto-sends. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInstagramDirect) return;
  const states = new Map();
  let readiness = null,
    loading = null,
    dialog = null;
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const canWrite = () => ["owner", "admin", "member"].includes(host.identity?.papel);
  const canSend = () =>
    ["owner", "admin"].includes(host.identity?.papel) &&
    readiness?.send_enabled === true &&
    readiness?.incoming_available === true &&
    readiness?.account_connected === true;
  const labels = {
    draft: "Rascunho no servidor",
    approved: "Aprovada; não enviada",
    dispatching: "Envio iniciado",
    confirmed: "Confirmada pela Meta",
    retry_ready: "Aguardando intervalo",
    failed: "Recusada pela Meta",
    uncertain: "Resultado incerto; não repetir",
    cancelled: "Cancelada",
  };
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
    if (!states.has(key))
      states.set(key, {
        scope: scope(),
        conversation: row.id,
        text: "",
        job: null,
        jobs: [],
        busy: false,
        pending: null,
        lastRead: 0,
      });
    return states.get(key);
  }
  function message(state, text) {
    state.message = text;
    const n = document.querySelector("[data-ig-reply-status]");
    if (n && selected()?.id === state.conversation) n.textContent = text;
  }
  async function configuration() {
    if (readiness) return readiness;
    if (!loading)
      loading = host
        .request("/integrations/readiness")
        .then(async (r) => {
          const result = r.instagram || {};
          const connection = await host.request("/instagram/meta/status");
          return (readiness = {
            ...result,
            account_connected:
              connection.status === "connected" && connection.credential_available === true,
          });
        })
        .catch(() => (readiness = {}))
        .finally(() => (loading = null));
    return loading;
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
      if (changed && selected()?.id === state.conversation) window.render();
    } catch (error) {
      message(state, error.message || "Não foi possível consultar as respostas.");
    } finally {
      state.reading = false;
    }
  }
  function review(state) {
    const job = state.job;
    if (!job || state.busy) return;
    dialog?.close();
    const box = element("dialog");
    dialog = box;
    box.className = "ig-human-review";
    box.setAttribute("aria-label", "Revisar Direct do Instagram");
    const row = selected(),
      identity = scope();
    box.append(
      element("h2", "Revisar resposta ao Instagram"),
      element("p", "Destinatário da conversa: " + row.contact_name),
    );
    const text = element("p", job.text);
    text.style.whiteSpace = "pre-wrap";
    box.append(text);
    const feedback = element(
      "p",
      canSend()
        ? "Ao confirmar, esta resposta será enviada de verdade."
        : "Envio desativado. O responsável precisa validar a Meta e a convivência com o n8n antes de habilitar o dashboard.",
    );
    feedback.setAttribute("role", "status");
    box.append(feedback);
    const close = element("button", "Fechar");
    close.type = "button";
    close.onclick = () => {
      if (!state.busy) box.close();
    };
    const send = element("button", "Confirmar envio ao Instagram");
    send.type = "button";
    send.disabled = !canSend() || !["draft", "approved", "retry_ready"].includes(job.status);
    send.onclick = async () => {
      if (state.busy || !canSend() || identity !== scope()) return;
      state.busy = true;
      send.disabled = true;
      close.disabled = true;
      feedback.textContent = "Registrando a tentativa. Não feche esta janela.";
      try {
        let current = state.job;
        if (current.status === "draft")
          current = await host.request(
            "/instagram/direct/jobs/" + current.id + "/approve",
            "POST",
            { operation_id: crypto.randomUUID(), expected_revision: current.revision },
          );
        if (identity !== scope()) return;
        current = await host.request("/instagram/direct/jobs/" + current.id + "/run", "POST", {});
        if (identity !== scope()) return;
        state.job = current;
        feedback.textContent = labels[current.status] || "Consulte o estado da resposta.";
        message(state, feedback.textContent);
        await refresh(state, true);
      } catch (error) {
        feedback.textContent =
          (error.message || "Não foi possível confirmar o envio.") +
          " Consulte as respostas antes de qualquer nova tentativa. Nada será repetido automaticamente.";
        message(state, feedback.textContent);
        await refresh(state, true);
      } finally {
        state.busy = false;
        close.disabled = false;
        paint();
      }
    };
    box.addEventListener("cancel", (event) => {
      if (state.busy) event.preventDefault();
    });
    box.addEventListener("close", () => {
      box.remove();
      if (dialog === box) dialog = null;
    });
    box.append(close, send);
    document.body.append(box);
    box.showModal();
    close.focus();
  }
  function paint() {
    const row = selected();
    if (!row || !readiness?.reply_preparation_available) return;
    const state = stateFor(row),
      composer = document.querySelector(".ct .cp"),
      input = document.getElementById("ta");
    if (!composer || !input) return;
    let section = composer.querySelector("[data-ig-reply]");
    if (!section) {
      section = element("section");
      section.dataset.igReply = "true";
      section.className = "ig-human";
      const title = element("strong", "Resposta humana · Instagram");
      const feedback = element("p");
      feedback.dataset.igReplyStatus = "true";
      feedback.setAttribute("role", "status");
      feedback.setAttribute("aria-live", "polite");
      const select = element("select");
      select.setAttribute("aria-label", "Respostas registradas desta conversa");
      select.onchange = () => {
        if (state.busy) return;
        if (
          !select.value &&
          state.jobs.some((j) => ["uncertain", "dispatching", "confirmed"].includes(j.status)) &&
          !confirm(
            "Já existe uma tentativa iniciada ou confirmada. Confira o histórico para evitar repetir a resposta. Preparar outra?",
          )
        ) {
          select.value = state.job?.id || "";
          return;
        }
        state.job = state.jobs.find((j) => j.id === select.value) || null;
        state.pending = null;
        state.text = state.job?.text || "";
        paint();
      };
      const reviewButton = element("button", "Revisar resposta");
      reviewButton.type = "button";
      reviewButton.dataset.igReview = "true";
      reviewButton.onclick = () => review(state);
      const reload = element("button", "Consultar respostas");
      reload.type = "button";
      reload.onclick = () => refresh(state, true);
      section.append(title, feedback, select, reviewButton, reload);
      composer.append(section);
      const label = composer.querySelector(".row > b");
      if (label) label.textContent = "Resposta humana";
      composer.querySelectorAll(".k10-ax").forEach((el) => {
        el.hidden = true;
        el.style.display = "none";
      });
    }
    input.value = state.job?.text || state.text;
    section.setAttribute("aria-busy", String(state.busy));
    input.disabled = !canWrite() || state.busy || !!state.job || !!state.pending;
    input.oninput = () => {
      state.text = input.value;
      paintButtons();
    };
    let button =
      composer.querySelector("[data-ig-prepare]") || composer.querySelector('[data-a^="salvar:"]');
    if (button) {
      button.removeAttribute("data-a");
      button.dataset.igPrepare = "true";
      button.textContent = "Preparar resposta no servidor";
      button.onclick = async (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        if (state.busy || state.job || state.pending || !canWrite()) return;
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
        state.busy = true;
        state.pending = crypto.randomUUID();
        paint();
        try {
          const job = await host.request("/instagram/direct/jobs", "POST", {
            operation_id: state.pending,
            source_message_id: source,
            text,
          });
          if (state.scope !== scope()) return;
          state.job = job;
          state.pending = null;
          state.text = text;
          message(state, "Rascunho salvo no servidor. Nenhuma mensagem foi enviada.");
          await refresh(state, true);
        } catch (error) {
          if (Number.isInteger(error.status) && error.status < 500) state.pending = null;
          message(
            state,
            (error.message || "Resultado da preparação não confirmado.") +
              " Consulte a lista de respostas antes de continuar.",
          );
        } finally {
          state.busy = false;
          paint();
        }
      };
    }
    const select = section.querySelector("select");
    select.replaceChildren(element("option", "Nova resposta"));
    select.firstChild.value = "";
    for (const job of state.jobs) {
      const option = element(
        "option",
        (labels[job.status] || job.status) + " · " + job.text.slice(0, 45),
      );
      option.value = job.id;
      select.append(option);
    }
    select.value = state.job?.id || "";
    select.disabled = state.busy;
    section.querySelector("[data-ig-reply-status]").textContent =
      state.message || "Rascunhos e aprovação ficam no servidor. Nada é enviado automaticamente.";
    section.querySelector("[data-ig-review]").disabled = state.busy || !state.job;
    const warning = document.querySelector(".ct .hd .wn");
    if (warning)
      warning.textContent = canSend()
        ? "Resposta humana habilitada; exige revisão e confirmação."
        : "Envio desativado; é possível preparar e revisar rascunhos.";
    const note = document.querySelector(".ct > p.m.sm");
    if (note)
      note.textContent = canSend()
        ? "Toda resposta exige revisão e confirmação. Nada é enviado automaticamente."
        : "Preparação salva no servidor. Envio externo desativado.";
    const assistant = document.querySelector('.ct .hd [data-a="ai"]');
    if (assistant) {
      assistant.disabled = true;
      assistant.title = "Geração automática por IA ainda não conectada.";
    }
    function paintButtons() {
      if (button)
        button.disabled =
          state.busy || !!state.job || !!state.pending || !canWrite() || !input.value.trim();
    }
    paintButtons();
  }
  async function mount() {
    const row = selected();
    if (!row) return;
    const identity = scope();
    await configuration();
    if (identity !== scope() || !readiness.reply_preparation_available) return;
    paint();
    await refresh(stateFor(row));
  }
  const style = element("style");
  style.textContent =
    ".ig-human{margin-top:12px;display:flex;gap:10px;flex-wrap:wrap}.ig-human strong,.ig-human p{width:100%;font-size:14px}.ig-human select,.ig-human button,.ig-human-review button{min-height:44px;border:1px solid var(--b);border-radius:9px;padding:9px 12px;font:inherit;color:var(--t);background:var(--w);max-width:100%}.ig-human select{min-width:0;flex:1 1 100%}.ig-human-review{margin:auto;max-width:calc(100vw - 32px);width:520px;max-height:calc(100dvh - 32px);overflow:auto;background:var(--w);color:var(--t);border:1px solid var(--b);border-radius:16px;padding:22px}.ig-human-review::backdrop{background:#0008}.ig-human-review p{margin:14px 0;overflow-wrap:anywhere}.ig-human-review button{margin-right:10px}";
  document.head.append(style);
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      const result = render.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => {
    if (!dialog?.open) return;
    dialog.close();
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
