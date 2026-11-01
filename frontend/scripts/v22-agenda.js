/* Workspace reminders. Stored records always come from the authenticated API. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIAgenda) return;
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const canWrite = () => ["owner", "admin", "member"].includes(host.identity?.papel);
  const active = () => location.hash === "#/agenda";
  const localDate = (date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const shift = (days) => {
    const date = new Date();
    date.setDate(date.getDate() + days);
    return localDate(date);
  };
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const key = () => "socialmei-agenda-pending-v1:" + scope();
  let state;
  function current() {
    if (!state || state.scope !== scope())
      state = {
        scope: scope(),
        from: shift(-7),
        to: shift(90),
        items: [],
        phase: "initial",
        busy: false,
        ticket: 0,
      };
    return state;
  }
  const valid = (row) =>
    row &&
    typeof row.id === "string" &&
    /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(row.id) &&
    Number.isSafeInteger(row.revision) &&
    row.revision > 0 &&
    typeof row.title === "string" &&
    Number.isFinite(Date.parse(row.scheduled_for)) &&
    ["pending", "done", "cancelled"].includes(row.status);
  function pending() {
    try {
      const raw = localStorage.getItem(key());
      if (!raw) return null;
      const packet = JSON.parse(raw);
      if (
        !/^[a-f0-9-]{36}$/i.test(packet.operation_id) ||
        typeof packet.title !== "string" ||
        !Number.isFinite(Date.parse(packet.scheduled_for))
      )
        throw Error();
      return { packet, raw };
    } catch (_) {
      throw Error("Não foi possível ler o lembrete pendente. Preserve os dados e peça suporte.");
    }
  }
  async function load(s = current()) {
    if (s.scope !== scope()) return;
    const ticket = ++s.ticket;
    s.phase = "loading";
    s.error = "";
    paint();
    try {
      const result = await host.request(
        `/agenda?from_date=${encodeURIComponent(s.from)}&to_date=${encodeURIComponent(s.to)}`,
      );
      if (s.scope !== scope() || ticket !== s.ticket) return;
      if (!Array.isArray(result.items) || !result.items.every(valid))
        throw Error("Resposta da Agenda inválida.");
      s.items = result.items;
      s.truncated = result.truncated;
      s.phase = "ready";
    } catch (error) {
      if (s.scope !== scope() || ticket !== s.ticket) return;
      s.phase = "error";
      s.error = error.message || "Não foi possível consultar a Agenda.";
    }
    paint();
  }
  async function change(row, status) {
    const s = current();
    if (s.busy || s.phase !== "ready" || !canWrite()) return;
    if (status === "cancelled" && !confirm("Cancelar este lembrete? O histórico será preservado."))
      return;
    s.busy = true;
    paint();
    try {
      const saved = await host.request("/agenda/" + row.id, "PATCH", {
        expected_revision: row.revision,
        status,
      });
      if (s.scope !== scope()) return;
      if (
        !valid(saved) ||
        saved.id !== row.id ||
        saved.status !== status ||
        saved.revision !== row.revision + 1
      )
        throw Error("Não foi possível validar a alteração. Consulte a Agenda.");
      s.items = s.items.map((item) => (item.id === saved.id ? saved : item));
      s.message = "Alteração confirmada no negócio.";
      await load(s);
    } catch (error) {
      if (s.scope === scope()) {
        s.error = error.message || "Alteração sem confirmação. Consulte a Agenda antes de repetir.";
        s.phase = "error";
      }
    } finally {
      s.busy = false;
      if (s.scope === scope()) paint();
    }
  }
  async function create(resuming = false) {
    const s = current();
    if (s.busy || !canWrite()) return;
    let savedPending;
    try {
      savedPending = pending();
    } catch (error) {
      toast(error.message);
      return;
    }
    if (savedPending && !resuming) {
      toast("Use Retomar lembrete pendente antes de criar outro.");
      return;
    }
    if (resuming && !savedPending) return paint();
    s.busy = true;
    paint();
    let clients;
    try {
      clients = await host.request("/clientes");
      if (!Array.isArray(clients)) throw Error("Clientes indisponíveis.");
    } catch (error) {
      s.busy = false;
      s.error = error.message;
      paint();
      return;
    }
    if (s.scope !== scope()) return;
    s.busy = false;
    const old = savedPending?.packet;
    const date = old ? new Date(old.scheduled_for) : new Date();
    const time = old
      ? `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`
      : "09:00";
    openForm(
      resuming ? "Retomar lembrete pendente" : "Novo lembrete",
      "Data e hora do seu dispositivo: " +
        Intl.DateTimeFormat().resolvedOptions().timeZone +
        ". Nenhuma mensagem será enviada.",
      [
        { id: "agenda_title", label: "O que lembrar", value: old?.title || "", req: 1 },
        { id: "agenda_date", label: "Data", value: localDate(date), req: 1 },
        { id: "agenda_time", label: "Horário", value: time, req: 1 },
        { id: "agenda_client", label: "Cliente", type: "select", options: ["Sem cliente"] },
        { id: "agenda_notes", label: "Observações", type: "textarea", value: old?.notes || "" },
      ],
      () => "",
      resuming ? "Confirmar registro original" : "Salvar lembrete",
    );
    const box = dlg(),
      form = box.querySelector("form");
    const ownsForm = () => box.querySelector("form") === form;
    const field = (name) => form.querySelector("#f_agenda_" + name);
    field("title").maxLength = 160;
    field("notes").maxLength = 1000;
    field("date").type = "date";
    field("time").type = "time";
    const select = field("client");
    select.replaceChildren(element("option", "Sem cliente"));
    select.firstChild.value = "";
    for (const client of clients) {
      const option = element("option", client.nome + (client.email ? " · " + client.email : ""));
      option.value = String(client.id);
      select.append(option);
    }
    select.value = old?.cliente_id ? String(old.cliente_id) : "";
    if (resuming)
      form.querySelectorAll("input,select,textarea").forEach((node) => (node.disabled = true));
    const feedback = element("p");
    feedback.setAttribute("role", "status");
    form.append(feedback);
    let submitting = false;
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (submitting) return;
      if (s.scope !== scope() || !canWrite()) {
        if (ownsForm()) box.close();
        return;
      }
      let packet, stored;
      try {
        if (resuming) {
          if (localStorage.getItem(key()) !== savedPending.raw)
            throw Error("O lembrete pendente mudou. Feche esta janela e confira novamente.");
          packet = old;
        } else {
          if (!form.reportValidity() || !field("title").value.trim())
            throw Error("Confira título, data e horário.");
          const local = field("date").value + "T" + field("time").value;
          const start = new Date(local);
          if (
            !Number.isFinite(start.getTime()) ||
            localDate(start) !== field("date").value ||
            `${String(start.getHours()).padStart(2, "0")}:${String(start.getMinutes()).padStart(2, "0")}` !==
              field("time").value
          )
            throw Error("Data ou horário inválido no fuso do seu dispositivo.");
          packet = {
            operation_id: crypto.randomUUID(),
            title: field("title").value.trim(),
            scheduled_for: start.toISOString(),
            notes: field("notes").value.trim(),
            cliente_id: select.value ? Number(select.value) : null,
          };
          if (pending())
            throw Error("Existe um lembrete sem confirmação. Retome o pedido original.");
        }
        stored = resuming ? savedPending.raw : JSON.stringify(packet);
        if (!resuming) localStorage.setItem(key(), stored);
        submitting = true;
        s.busy = true;
        form.querySelectorAll("button").forEach((button) => (button.disabled = true));
        const saved = await host.request("/agenda", "POST", packet);
        if (s.scope !== scope()) return;
        if (!valid(saved) || saved.id !== packet.operation_id.toLowerCase())
          throw Error("Resposta inválida. Retome o pedido original para conferir.");
        if (localStorage.getItem(key()) === stored) localStorage.removeItem(key());
        if (ownsForm()) box.close();
        s.message =
          saved.status === "cancelled"
            ? "Pedido original confirmado; esse lembrete já foi cancelado."
            : "Lembrete salvo no negócio.";
        await load(s);
      } catch (error) {
        if (s.scope !== scope()) return;
        let retained;
        try {
          if (
            stored &&
            [400, 403, 404, 409, 422].includes(error.status) &&
            localStorage.getItem(key()) === stored
          )
            localStorage.removeItem(key());
          retained = stored && !!localStorage.getItem(key());
        } catch (_) {
          feedback.textContent =
            "O armazenamento ficou indisponível. Consulte a Agenda antes de repetir o pedido.";
          return;
        }
        feedback.textContent =
          (error.message || "Resultado sem confirmação.") +
          (retained
            ? " Feche esta janela e use Retomar lembrete pendente; os dados originais foram preservados."
            : "");
      } finally {
        submitting = false;
        s.busy = false;
        form.querySelectorAll("button").forEach((button) => (button.disabled = false));
        if (s.scope === scope()) paint();
      }
    };
    const onCancel = (event) => {
      if (submitting && ownsForm()) event.preventDefault();
    };
    box.addEventListener("cancel", onCancel);
    box.addEventListener("close", () => box.removeEventListener("cancel", onCancel), {
      once: true,
    });
    if (resuming) form.querySelector("button[type=button]")?.focus();
  }
  function paint() {
    if (!active()) return;
    const s = current(),
      view = document.getElementById("v");
    if (!view) return;
    let hasPending = false;
    try {
      hasPending = !!localStorage.getItem(key());
    } catch (_) {
      s.phase = "error";
      s.error =
        "O navegador não permite preservar operações. Confira as permissões de armazenamento antes de salvar.";
    }
    const section = element("section");
    section.className = "pg sm-agenda";
    section.dataset.agenda = "true";
    const top = element("div");
    top.className = "row sp wr";
    const add = element("button", "Novo lembrete");
    add.type = "button";
    add.className = "btn";
    add.disabled = s.busy || s.phase !== "ready" || !canWrite();
    add.onclick = () => create();
    top.append(element("h1", "Seus horários e lembretes"), add);
    section.append(
      top,
      element(
        "p",
        "Salvos no negócio da sua sessão. Nenhuma mensagem ou notificação externa é enviada.",
      ),
    );
    const filters = element("form");
    filters.className = "row wr";
    filters.setAttribute("aria-label", "Período da Agenda");
    for (const [name, label] of [
      ["from", "De"],
      ["to", "Até"],
    ]) {
      const wrapper = element("label", label),
        input = element("input");
      input.type = "date";
      input.className = "in";
      input.value = s[name];
      input.required = true;
      input.disabled = s.busy;
      input.onchange = () => (s[name] = input.value);
      wrapper.append(input);
      filters.append(wrapper);
    }
    const reload = element("button", "Consultar agenda");
    reload.className = "btn o";
    reload.type = "submit";
    reload.disabled = s.busy;
    filters.append(reload);
    filters.onsubmit = (event) => {
      event.preventDefault();
      if (filters.reportValidity()) load(s);
    };
    const feedback = element(
      "p",
      s.error || (s.phase === "loading" ? "Consultando a Agenda…" : s.message || ""),
    );
    feedback.setAttribute("role", "status");
    feedback.setAttribute("aria-live", "polite");
    section.append(filters, feedback);
    if (s.phase === "error" && s.items.length)
      section.append(
        element(
          "p",
          "A lista exibida pode estar desatualizada. Consulte novamente antes de alterar.",
        ),
      );
    if (hasPending) {
      const resume = element("button", "Retomar lembrete pendente");
      resume.className = "btn o";
      resume.disabled = s.busy || !canWrite();
      resume.onclick = () => create(true);
      section.append(resume);
    }
    if (s.truncated)
      section.append(
        element("p", "Exibindo até 500 lembretes. Reduza o período para consultar os demais."),
      );
    let previous;
    for (const item of s.items.filter((item) => item.status !== "cancelled")) {
      const date = new Date(item.scheduled_for),
        day = localDate(date);
      if (day !== previous) {
        section.append(
          element(
            "h2",
            date.toLocaleDateString("pt-BR", {
              weekday: "long",
              day: "2-digit",
              month: "long",
              year: "numeric",
            }),
          ),
        );
        previous = day;
      }
      const line = element("div");
      line.className = "agi" + (item.status === "done" ? " done" : "");
      const done = element("button", item.status === "done" ? "✓" : "");
      done.type = "button";
      done.className = "ckb";
      done.setAttribute("role", "checkbox");
      done.setAttribute("aria-checked", String(item.status === "done"));
      done.setAttribute("aria-label", "Marcar como feito: " + item.title);
      done.disabled = s.busy || s.phase !== "ready" || !canWrite();
      done.onclick = () => change(item, item.status === "done" ? "pending" : "done");
      const details = element("div");
      details.className = "cks";
      details.append(element("strong", item.title));
      if (item.client_name) details.append(element("p", "Cliente: " + item.client_name));
      if (item.notes) details.append(element("p", item.notes));
      const cancel = element("button", "Cancelar");
      cancel.className = "btn o";
      cancel.type = "button";
      cancel.disabled = done.disabled;
      cancel.onclick = () => change(item, "cancelled");
      line.append(
        done,
        element("time", date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })),
        details,
        cancel,
      );
      section.append(line);
    }
    if (s.phase === "ready" && !s.items.filter((item) => item.status !== "cancelled").length)
      section.append(element("p", "Nenhum lembrete neste período."));
    view.replaceChildren(section);
  }
  function mount() {
    if (!active()) return;
    const s = current();
    paint();
    if (s.phase === "initial") load(s);
  }
  const style = element("style");
  style.textContent =
    ".sm-agenda>p,.sm-agenda>form{margin:14px 0}.sm-agenda h1{font-size:30px}.sm-agenda h2{margin-top:22px}.sm-agenda .agi{gap:12px;flex-wrap:wrap}.sm-agenda .cks{min-width:0;overflow-wrap:anywhere}.sm-agenda button{min-height:44px}.sm-agenda label{min-width:140px}.sm-agenda input{font:inherit;max-width:100%}.sm-agenda .ckb{width:44px;height:44px;flex:none}" +
    "@media(max-width:640px){.sm-agenda .agi{display:grid;grid-template-columns:44px minmax(0,1fr)}.sm-agenda .agi>time,.sm-agenda .cks,.sm-agenda .agi>.btn{grid-column:2}.sm-agenda .agi>.btn{justify-self:start}}";
  document.head.append(style);
  const render = window.render;
  window.render = function (...args) {
    const result = render.apply(this, args);
    mount();
    return result;
  };
  A.agnew = () => {
    create();
    return false;
  };
  window.SocialMEIAgenda = { refresh: () => load(current()) };
  mount();
})();
