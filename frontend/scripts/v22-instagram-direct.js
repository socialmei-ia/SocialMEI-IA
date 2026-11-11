/* Human-reviewed Direct outbox in the native inbox. Never auto-approves or auto-sends. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInstagramDirect) return;
  const states = new Map();
  let readiness = null,
    readinessScope = null,
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
    const n = document.querySelector("[data-ig-reply-status]");
    if (n && selected()?.id === state.conversation) n.textContent = text;
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
  async function menuStatus(state) {
    if (
      !readiness?.auto_menu_available ||
      state.menuReading ||
      Date.now() - (state.menuReadAt || 0) < 15000
    )
      return;
    state.menuReading = true;
    state.menuReadAt = Date.now();
    try {
      const data = await host.request(`/instagram/menu/conversations/${state.conversation}/status`);
      if (state.scope !== scope() || selected()?.id !== state.conversation) return;
      state.menuState = ["menu", "ask_product", "human"].includes(data.state) ? data.state : null;
      state.menuError = !state.menuState;
    } catch {
      state.menuState = null;
      state.menuError = true;
    } finally {
      state.menuReading = false;
      if (state.scope === scope() && selected()?.id === state.conversation) paint();
    }
  }
  function review(state) {
    if (!state.job || state.busy) return;
    const job = Object.freeze({ ...state.job });
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
        let current = job;
        if (current.status === "draft")
          current = await host.request(
            "/instagram/direct/jobs/" + current.id + "/approve",
            "POST",
            { operation_id: crypto.randomUUID(), expected_revision: current.revision },
          );
        if (identity !== scope()) return;
        current = await host.request("/instagram/direct/jobs/" + current.id + "/run", "POST", {
          expected_revision: job.revision,
        });
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
        if (state.busy || state.pending || state.storageError) return;
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
        state.text = state.job?.text || "";
        paint();
      };
      const reviewButton = element("button", "Revisar resposta");
      reviewButton.type = "button";
      reviewButton.dataset.igReview = "true";
      reviewButton.onclick = () => review(state);
      const reload = element("button", "Consultar respostas");
      reload.type = "button";
      reload.onclick = async () => {
        state.menuReadAt = 0;
        await configuration(true);
        paint();
        await refresh(state, true);
      };
      section.append(title, feedback, select, reviewButton, reload);
      composer.append(section);
      const label = composer.querySelector(".row > b");
      if (label) label.textContent = "Resposta humana";
      composer.querySelectorAll(".k10-ax").forEach((el) => {
        el.hidden = true;
        el.style.display = "none";
      });
    }
    if (readiness.auto_menu_available) {
      let controls = section.querySelector("[data-ig-menu]");
      if (!controls) {
        controls = element("div");
        controls.dataset.igMenu = "true";
        const status = element("p");
        status.setAttribute("role", "status");
        status.setAttribute("aria-live", "polite");
        controls.append(status);
        for (const [action, label] of [
          ["pause", "Assumir atendimento"],
          ["resume", "Retomar menu"],
        ]) {
          const control = element("button", label);
          control.type = "button";
          control.dataset.igMenuAction = action;
          control.onclick = async () => {
            if (state.busy || state.scope !== scope() || selected()?.id !== state.conversation)
              return;
            state.busy = true;
            paint();
            try {
              await host.request(
                `/instagram/menu/conversations/${state.conversation}/${action}`,
                "POST",
                {},
              );
            } catch (error) {
              message(state, error.message || "Não foi possível alterar o atendimento.");
            } finally {
              state.busy = false;
              state.menuReadAt = 0;
              await menuStatus(state);
            }
          };
          controls.append(control);
        }
        section.append(controls);
      }
      controls.querySelector("p").textContent =
        state.menuState === "human"
          ? "Atendimento humano ativo. O menu está pausado."
          : state.menuState
            ? "Menu automático ativo nesta conversa."
            : state.menuError
              ? "Não foi possível consultar o menu. Atualize as respostas para tentar novamente."
              : "Consultando o menu automático…";
      for (const control of controls.querySelectorAll("button")) {
        control.disabled =
          state.busy ||
          !canWrite() ||
          !state.menuState ||
          (control.dataset.igMenuAction === "pause"
            ? state.menuState === "human"
            : state.menuState !== "human");
      }
      menuStatus(state);
    }
    input.value = state.job?.text || state.pending?.text || state.text;
    section.setAttribute("aria-busy", String(state.busy));
    input.disabled =
      !canWrite() || state.busy || !!state.job || !!state.pending || state.storageError;
    input.oninput = () => {
      state.text = input.value;
      paintButtons();
    };
    let button =
      composer.querySelector("[data-ig-prepare]") || composer.querySelector('[data-a^="salvar:"]');
    if (button) {
      button.removeAttribute("data-a");
      button.dataset.igPrepare = "true";
      button.textContent = state.pending
        ? "Recuperar registro pendente"
        : "Preparar resposta no servidor";
      button.onclick = async (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        if (state.busy || state.job || state.storageError || !canWrite()) return;
        if (!state.pending) {
          const source = row.messages
              ?.filter(
                (message) => message.direction !== "outgoing" && Number.isSafeInteger(message.id),
              )
              .at(-1)?.id,
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
          if (!clearPending(state, job))
            throw Error("Registro divergente. Não prepare outra resposta.");
          state.job = job;
          state.text = job.text;
          state.menuReadAt = 0;
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
    select.disabled = state.busy || !!state.pending || state.storageError;
    section.querySelector("[data-ig-reply-status]").textContent = state.storageError
      ? "Operação pendente não pode ser validada neste navegador. Nenhuma nova resposta será criada."
      : state.message ||
        (state.pending
          ? "Registro sem confirmação. Recupere a mesma operação antes de outra resposta."
          : "Rascunhos e aprovação ficam no servidor. Nada é enviado automaticamente.");
    section.querySelector("[data-ig-review]").disabled =
      state.busy || !!state.pending || state.storageError || !state.job;
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
          state.busy ||
          !!state.job ||
          state.storageError ||
          !canWrite() ||
          (!state.pending && !input.value.trim());
    }
    paintButtons();
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
        section.className = "ig-human";
        const feedback = element("p", "Não foi possível consultar a conexão do Instagram.");
        feedback.setAttribute("role", "status");
        const retry = element("button", "Consultar conexão novamente");
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
  const style = element("style");
  style.textContent =
    ".ig-human{margin-top:12px;display:flex;gap:10px;flex-wrap:wrap}.ig-human strong,.ig-human p{width:100%;font-size:14px}.ig-human select,.ig-human button,.ig-human-review button{min-height:44px;border:1px solid var(--b);border-radius:9px;padding:9px 12px;font:inherit;color:var(--t);background:var(--w);max-width:100%}.ig-human select{min-width:0;flex:1 1 100%}.ig-human-review{margin:auto;max-width:calc(100vw - 32px);width:520px;max-height:calc(100dvh - 32px);overflow:auto;background:var(--w);color:var(--t);border:1px solid var(--b);border-radius:16px;padding:22px}.ig-human-review::backdrop{background:#0008}.ig-human-review p{margin:14px 0;overflow-wrap:anywhere}.ig-human-review button{margin-right:10px}";
  document.head.append(style);
  style.textContent += ".ig-human [data-ig-menu]{display:flex;flex-wrap:wrap;gap:8px;width:100%}";
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
