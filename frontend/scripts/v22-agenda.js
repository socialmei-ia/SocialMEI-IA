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
  /* ---------- v7.3 · utilidades puras ---------- */
  const plain = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const pad = (n) => String(n).padStart(2, "0");
  const WEEKDAYS = { domingo: 0, segunda: 1, terca: 2, quarta: 3, quinta: 4, sexta: 5, sabado: 6 };
  /* "ligar para a Ana amanhã às 14h30" -> { title, date, time }. Só interpreta; quem salva é o formulário. */
  function parseQuick(text, base = new Date()) {
    const orig = String(text || "").normalize("NFC").trim();
    if (!orig) return null;
    const low = plain(orig);
    const cut = Array.from(orig);
    const mark = (m) => {
      for (let k = m.index; k < m.index + m[0].length; k++) cut[k] = " ";
    };
    const day0 = new Date(base.getFullYear(), base.getMonth(), base.getDate(), 12);
    const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const plus = (n) => {
      const d = new Date(day0);
      d.setDate(d.getDate() + n);
      return d;
    };
    let date = null, time = null, m;
    if ((m = /\bdepois de amanha\b/.exec(low))) { date = iso(plus(2)); mark(m); }
    else if ((m = /\bamanha\b/.exec(low))) { date = iso(plus(1)); mark(m); }
    else if ((m = /\bhoje\b/.exec(low))) { date = iso(plus(0)); mark(m); }
    else if ((m = /\b(domingo|segunda|terca|quarta|quinta|sexta|sabado)(?:-feira)?\b/.exec(low))) {
      const diff = ((WEEKDAYS[m[1]] - day0.getDay() + 6) % 7) + 1;
      date = iso(plus(diff));
      mark(m);
    } else if ((m = /\b(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?(?!\d)/.exec(low))) {
      let y = m[3] ? (m[3].length === 2 ? 2000 + +m[3] : +m[3]) : day0.getFullYear();
      let d = new Date(y, +m[2] - 1, +m[1], 12);
      if (!m[3] && d < day0) d = new Date(y + 1, +m[2] - 1, +m[1], 12);
      if (d.getDate() === +m[1] && d.getMonth() === +m[2] - 1) { date = iso(d); mark(m); }
    } else if ((m = /\bdia (\d{1,2})\b/.exec(low))) {
      let d = new Date(day0.getFullYear(), day0.getMonth(), +m[1], 12);
      if (d < day0) d = new Date(day0.getFullYear(), day0.getMonth() + 1, +m[1], 12);
      if (d.getDate() === +m[1]) { date = iso(d); mark(m); }
    }
    const hm = (h, mi, period) => {
      h = +h; mi = mi ? +mi : 0;
      if (period && /tarde|noite/.test(period) && h < 12) h += 12;
      return h > 23 || mi > 59 ? null : `${pad(h)}:${pad(mi)}`;
    };
    if ((m = /\b(\d{1,2})\s*(?:h|:)\s*(\d{2})?(?!\d)/.exec(low)) && (time = hm(m[1], m[2]))) mark(m);
    else if ((m = /\b(\d{1,2})\s+da\s+(manha|tarde|noite)\b/.exec(low)) && (time = hm(m[1], 0, m[2]))) mark(m);
    else if ((m = /\bas\s+(\d{1,2})(?:\s+horas?)?(?![\d/])/.exec(low)) && (time = hm(m[1], 0))) mark(m);
    let title = cut.join("").replace(/\s+/g, " ").trim();
    title = title.replace(/^(?:lembrete|lembrar)(?:\s+(?:de|do|da|para))?\s+/i, "").replace(/\s+(?:as|às|a|em|no|na|dia|de|para)$/i, "").replace(/^[\s,.;:-]+|[\s,.;:-]+$/g, "");
    if (!title) title = "";
    return { title: title.charAt(0).toUpperCase() + title.slice(1), date, time };
  }
  /* "em 12 min", "em 2 h 10 min", "amanhã", "em 3 dias" */
  function relIn(at, now = Date.now()) {
    const ms = at - now;
    if (ms <= 60000) return "agora";
    const min = Math.round(ms / 60000);
    if (min < 60) return "em " + min + " min";
    const a = new Date(at), b = new Date(now);
    const days = Math.round((new Date(a.getFullYear(), a.getMonth(), a.getDate()) - new Date(b.getFullYear(), b.getMonth(), b.getDate())) / 864e5);
    if (days === 0) return "em " + Math.floor(min / 60) + " h" + (min % 60 ? " " + (min % 60) + " min" : "");
    return days === 1 ? "amanhã" : "em " + days + " dias";
  }
  const hhmm = (d) => d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  /* Horário comercial (texto do negócio) por dia da semana, para o cabeçalho da semana. Não é disponibilidade. */
  function weekHoursText() {
    const C = window.SocialMEIAgendaConfig;
    const raw = String(window.SocialMEIAuth?.current?.negocio?.configuracao?.horario || "").trim();
    if (!C?.parse || !raw) return undefined;
    const model = C.parse(raw);
    return model ? model.map((sh) => sh.map((x) => x.join("–")).join(" e ")) : undefined;
  }
  /* Agendamentos de serviços já carregados pelo componente de agendamentos (cópia somente leitura). */
  function servicesSource() {
    const api = window.SocialMEIAppointments;
    if (!api?.snapshot)
      return { list: [], raw: [], state: { s: "unavailable", msg: "Agendamentos de serviços não estão disponíveis nesta sessão; aqui aparecem só lembretes." } };
    const snap = api.snapshot();
    if (snap.scope !== scope()) return { list: [], raw: [], state: { s: "loading" } };
    const list = snap.items.map((r) => {
      const a = new Date(r.scheduled_for), b = new Date(r.ends_at);
      return { key: r.id, iso: localDate(a), time: hhmm(a), end: hhmm(b), title: r.service_name || "Serviço", client: r.client_name || "", resource: r.resource_name || "", status: r.status, late: r.status === "pending" && b.getTime() < Date.now(), channel: r.channel };
    });
    const state =
      snap.phase === "error"
        ? { s: "error", msg: "Não foi possível consultar os agendamentos de serviços (" + (snap.error || "erro desconhecido") + "). Os lembretes continuam valendo." }
        : snap.phase === "ready" ? { s: "ok" } : { s: "loading" };
    return { list, raw: snap.items, state };
  }
  /* v7.0: visão semanal. A preferência (lista/semana) é só da interface e fica no navegador. */
  const VIEW_KEY = "smei-agenda-view";
  const viewPref = () => {
    try {
      return localStorage.getItem(VIEW_KEY) === "week" && window.SocialMEIAgendaWeek ? "week" : "list";
    } catch (_) {
      return "list";
    }
  };
  const weekRange = (start) => {
    const W = window.SocialMEIAgendaWeek;
    return W ? W.range(start || W.mondayOf(new Date())) : { from: shift(-7), to: shift(90) };
  };
  function setView(s, view) {
    if (s.busy || s.view === view) return;
    s.view = view;
    s.message = "";
    try {
      localStorage.setItem(VIEW_KEY, view);
    } catch (_) {}
    if (view === "week") {
      s.weekStart = window.SocialMEIAgendaWeek.mondayOf(new Date());
      const r = weekRange(s.weekStart);
      s.from = r.from;
      s.to = r.to;
    } else {
      s.from = shift(-7);
      s.to = shift(90);
    }
    load(s);
  }
  function moveWeek(s, delta) {
    const W = window.SocialMEIAgendaWeek;
    s.weekStart = delta === 0 ? W.mondayOf(new Date()) : W.addDays(s.weekStart, 7 * delta);
    s.selectedDay = null;
    s.message = "";
    const r = weekRange(s.weekStart);
    s.from = r.from;
    s.to = r.to;
    load(s);
  }
  function jumpTo(s, iso) {
    const W = window.SocialMEIAgendaWeek;
    s.weekStart = W.mondayOf(iso);
    s.selectedDay = iso;
    s.message = "";
    const r = weekRange(s.weekStart);
    s.from = r.from;
    s.to = r.to;
    load(s);
  }
  let state;
  function current() {
    if (!state || state.scope !== scope())
      state = {
        scope: scope(),
        from: viewPref() === "week" ? weekRange().from : shift(-7),
        to: viewPref() === "week" ? weekRange().to : shift(90),
        view: viewPref(),
        weekStart: weekRange().from,
        items: [],
        phase: "initial",
        busy: false,
        ticket: 0,
        filter: "all",
        selectedDay: null,
        quick: "",
        restore: null,
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
  async function change(row, status, confirmed) {
    const s = current();
    if (s.busy || s.phase !== "ready" || !canWrite()) return;
    if (status === "cancelled" && !confirmed && !confirm("Cancelar este lembrete? O histórico será preservado."))
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
  async function create(resuming = false, preset = null) {
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
    paint(); /* v7.3: sem isto os botões ficavam desabilitados atrás do formulário até outra ação */
    const old = savedPending?.packet;
    const date = old
      ? new Date(old.scheduled_for)
      : preset?.date && /^\d{4}-\d{2}-\d{2}$/.test(preset.date)
        ? new Date(preset.date + "T09:00")
        : new Date();
    const time = old
      ? `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`
      : /^([01]\d|2[0-3]):[0-5]\d$/.test(preset?.time || "")
        ? preset.time
        : "09:00";
    openForm(
      resuming ? "Retomar lembrete pendente" : "Novo lembrete",
      "Data e hora do seu dispositivo: " +
        Intl.DateTimeFormat().resolvedOptions().timeZone +
        ". Nenhuma mensagem será enviada.",
      [
        { id: "agenda_title", label: "O que lembrar", value: old?.title || preset?.title || "", req: 1 },
        { id: "agenda_date", label: "Data", value: localDate(date), req: 1 },
        { id: "agenda_time", label: "Horário", value: time, req: 1 },
        { id: "agenda_client", label: "Cliente", type: "select", options: ["Sem cliente"] },
        { id: "agenda_notes", label: "Observações", type: "textarea", value: old?.notes || preset?.notes || "" },
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
    select.value = old?.cliente_id
      ? String(old.cliente_id)
      : preset?.cliente_id && [...select.options].some((o) => o.value === String(preset.cliente_id))
        ? String(preset.cliente_id)
        : "";
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
  /* ---------- v7.3 · peças da tela ---------- */
  const FILTERS = [["all", "Todos"], ["pending", "Pendentes"], ["late", "Atrasados"], ["done", "Feitos"]];
  const isLate = (item, now) => item.status === "pending" && Date.parse(item.scheduled_for) < now;
  const icon = (d) => {
    const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg"), path = document.createElementNS(ns, "path");
    for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: "26", height: "26", fill: "none", stroke: "currentColor", "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round" })) svg.setAttribute(k, v);
    path.setAttribute("d", d);
    svg.append(path);
    return svg;
  };
  /* Próximo compromisso: lembrete pendente ou serviço em andamento/agendado, só com dados já carregados. */
  function nextNode(s) {
    if (s.phase !== "ready" && !s.items.length) return null;
    const now = Date.now(), src = servicesSource(), cand = [];
    for (const i of s.items)
      if (i.status === "pending" && Date.parse(i.scheduled_for) >= now)
        cand.push({ at: Date.parse(i.scheduled_for), end: Date.parse(i.scheduled_for), kind: "Lembrete", title: i.title, who: i.client_name || "" });
    for (const r of src.raw)
      if (r.status === "pending" && Date.parse(r.ends_at) >= now)
        cand.push({ at: Date.parse(r.scheduled_for), end: Date.parse(r.ends_at), kind: "Serviço", title: r.service_name || "Serviço", who: [r.client_name, r.resource_name].filter(Boolean).join(" · ") });
    cand.sort((a, b) => a.at - b.at);
    const late = s.items.filter((i) => isLate(i, now)).length, first = cand[0];
    if (!first && !late) return null;
    const box = element("section");
    box.className = "ag-next";
    box.dataset.agNext = "true";
    box.setAttribute("aria-label", "Próximo compromisso");
    if (first) {
      const inProgress = first.at <= now;
      const when = new Date(first.at);
      const sameDay = localDate(when) === localDate(new Date());
      const body = element("div");
      body.className = "ag-nx-b";
      const eb = element("span", inProgress ? "Em andamento" : "Próximo compromisso");
      eb.className = "ag-nx-e";
      const line = element("b", (sameDay ? "" : when.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" }).replace(".", "") + " · ") + hhmm(when) + " · " + first.title);
      line.className = "ag-nx-t";
      const meta = element("span", first.kind + (first.who ? " · " + first.who : "") + " · ");
      meta.className = "ag-nx-m";
      const inn = element("span", inProgress ? "agora" : relIn(first.at));
      inn.dataset.at = String(first.at);
      inn.className = "ag-nx-in";
      meta.append(inn);
      body.append(eb, line, meta);
      box.append(body);
    }
    if (late) {
      const b = element("button", late === 1 ? "1 lembrete atrasado" : late + " lembretes atrasados");
      b.type = "button";
      b.className = "btn o ag-nx-late";
      b.onclick = () => {
        s.filter = "late";
        if (s.view === "week") setView(s, "list");
        else paint();
      };
      box.append(b);
    }
    return box;
  }
  function quickNode(s) {
    const f = element("form");
    f.className = "ag-qa";
    f.setAttribute("aria-label", "Criação rápida de lembrete");
    const lab = element("label", "Criação rápida");
    lab.htmlFor = "ag-qa-i";
    const row = element("div");
    row.className = "ag-qa-r";
    const input = element("input");
    input.id = "ag-qa-i";
    input.type = "text";
    input.className = "in";
    input.maxLength = 160;
    input.autocomplete = "off";
    input.placeholder = "Ex.: ligar para a Ana amanhã 14h · cobrar João sexta 9h";
    input.value = s.quick || "";
    input.setAttribute("aria-describedby", "ag-qa-p");
    const go = element("button", "Revisar");
    go.type = "submit";
    go.className = "btn o";
    const prev = element("p");
    prev.id = "ag-qa-p";
    prev.className = "ag-qa-p";
    prev.setAttribute("aria-live", "polite");
    const off = s.busy || s.phase !== "ready";
    input.disabled = off;
    const sync = () => {
      s.quick = input.value;
      const q = parseQuick(input.value);
      go.disabled = off || !q?.title;
      if (!input.value.trim()) prev.textContent = "Escreva o que lembrar, com dia e hora se quiser. Você revisa antes de salvar.";
      else if (!q?.title) prev.textContent = "Falta dizer o que lembrar.";
      else {
        const d = q.date ? new Date(q.date + "T12:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" }).replace(".", "") : "hoje";
        prev.textContent = "Vai abrir o formulário com: “" + q.title + "” · " + d + " · " + (q.time || "09:00") + ". Nada é salvo até você confirmar.";
      }
    };
    input.oninput = sync;
    sync();
    f.onsubmit = (e) => {
      e.preventDefault();
      const q = parseQuick(input.value);
      if (off || !q?.title) return;
      s.quick = "";
      create(false, { title: q.title, date: q.date || localDate(new Date()), time: q.time });
    };
    row.append(input, go);
    f.append(lab, row, prev);
    return f;
  }
  function weekNode(s) {
    const W = window.SocialMEIAgendaWeek, now = Date.now(), src = servicesSource(), api = window.SocialMEIAppointments;
    const live = s.items.filter((item) => item.status !== "cancelled");
    if (s.rangeAsked !== s.weekStart && api?.ensureRange) {
      s.rangeAsked = s.weekStart;
      const r = weekRange(s.weekStart);
      api.ensureRange(r.from, r.to);
    }
    return W.build({
      weekStart: s.weekStart,
      today: localDate(new Date()),
      loading: s.phase === "loading" && !live.length,
      error: s.phase === "error" ? s.error : "",
      busy: s.busy || s.phase !== "ready",
      navBusy: s.busy || s.phase === "loading",
      canWrite: canWrite(),
      selected: s.selectedDay,
      hours: weekHoursText(),
      services: src.list,
      servicesState: src.state,
      items: live.map((item) => {
        const at = new Date(item.scheduled_for);
        return { key: item.id, raw: item, iso: localDate(at), time: hhmm(at), title: item.title, client: item.client_name || "", notes: item.notes || "", status: item.status, late: isLate(item, now) };
      }),
      onNav: (delta) => {
        s.restore = delta + 1;
        moveWeek(s, delta);
      },
      onJump: (iso) => jumpTo(s, iso),
      onSelect: (iso) => (s.selectedDay = iso),
      onToggle: (item) => change(item.raw, item.status === "done" ? "pending" : "done"),
      onNew: (iso) => create(false, { date: iso }),
      onOpenService: (id) => {
        if (!api?.focusCard?.(id)) toast("Agendamento não encontrado na lista abaixo. Atualize os agendamentos.");
      },
      onRetry: () => {
        load(s);
        if (api?.snapshot?.().phase === "error") api.refresh();
      },
    });
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
    const live = s.items
        .filter((item) => item.status !== "cancelled")
        .sort((a, b) => Date.parse(a.scheduled_for) - Date.parse(b.scheduled_for)),
      now = Date.now(),
      today = localDate(new Date()),
      kp = {
        today: live.filter((i) => i.status === "pending" && localDate(new Date(i.scheduled_for)) === today).length,
        late: live.filter((i) => isLate(i, now)).length,
        pend: live.filter((i) => i.status === "pending").length,
        done: live.filter((i) => i.status === "done").length,
      };
    /* cabeçalho */
    const head = element("header");
    head.className = "ag-head";
    const ttl = element("div");
    ttl.className = "ag-title";
    const eyebrow = element("span", "Agenda");
    eyebrow.className = "ag-eyebrow";
    const sub = element("p", "Salvos no negócio da sua sessão. Nenhuma mensagem ou notificação externa é enviada.");
    sub.className = "ag-sub";
    ttl.append(eyebrow, element("h1", "Seus horários e lembretes"), sub);
    const add = element("button", "Novo lembrete");
    add.type = "button";
    add.className = "btn ag-add";
    add.title = "Atalho: tecla N";
    add.disabled = s.busy || s.phase !== "ready" || !canWrite();
    add.onclick = () => create();
    head.append(ttl, add);
    section.append(head);
    if (!canWrite()) {
      const ro = element("p", "Seu acesso é só de leitura: você pode consultar a Agenda, mas não criar nem alterar lembretes.");
      ro.className = "ag-ro";
      section.append(ro);
    }
    /* indicadores: só contagens reais dos lembretes carregados */
    if (s.phase === "ready" || live.length) {
      const k = element("div");
      k.className = "ag-kpis";
      k.setAttribute("role", "list");
      k.setAttribute("aria-label", "Resumo dos lembretes do período");
      for (const [label, n, tone] of [
        ["Hoje", kp.today, kp.today ? "on" : ""],
        ["Atrasados", kp.late, kp.late ? "warn" : ""],
        ["Pendentes no período", kp.pend, ""],
        ["Feitos", kp.done, ""],
      ]) {
        const c = element("div");
        c.className = "ag-k";
        c.dataset.tone = tone;
        c.setAttribute("role", "listitem");
        c.append(element("span", label), element("b", n));
        k.append(c);
      }
      section.append(k);
    }
    const holder = element("div");
    holder.dataset.agNexth = "true";
    const nn = nextNode(s);
    if (nn) holder.append(nn);
    section.append(holder);
    if (canWrite()) section.append(quickNode(s));
    /* cartão: lembretes */
    const rem = element("section");
    rem.className = "ag-card ag-rem";
    rem.setAttribute("aria-labelledby", "ag-rem-h");
    const rh = element("div");
    rh.className = "ag-ch";
    const rt = element("h2", "Lembretes");
    rt.id = "ag-rem-h";
    rh.append(rt, element("span", live.length ? live.length + " no período" : ""));
    if (window.SocialMEIAgendaWeek) {
      const sw = element("div");
      sw.className = "wk-sw";
      sw.setAttribute("role", "group");
      sw.setAttribute("aria-label", "Forma de ver a agenda");
      for (const [v, t] of [["list", "Lista"], ["week", "Semana"]]) {
        const b = element("button", t);
        b.type = "button";
        b.setAttribute("aria-pressed", String(s.view === v));
        b.disabled = s.busy;
        b.onclick = () => setView(s, v);
        sw.append(b);
      }
      rh.append(sw);
    }
    rem.append(rh);
    const filters = element("form");
    filters.className = "ag-range";
    filters.setAttribute("aria-label", "Período da Agenda");
    const quick = element("div");
    quick.className = "ag-quick";
    quick.setAttribute("role", "group");
    quick.setAttribute("aria-label", "Períodos rápidos");
    for (const [label, a0, b0] of [["Hoje", 0, 0], ["7 dias", 0, 7], ["30 dias", 0, 30], ["90 dias", 0, 90]]) {
      const q = element("button", label);
      q.type = "button";
      q.className = "ag-chip";
      q.setAttribute("aria-pressed", String(s.from === shift(a0) && s.to === shift(b0)));
      q.disabled = s.busy;
      q.onclick = () => {
        s.from = shift(a0);
        s.to = shift(b0);
        load(s);
      };
      quick.append(q);
    }
    filters.append(quick);
    const dates = element("div");
    dates.className = "ag-dates";
    for (const [name, label] of [["from", "De"], ["to", "Até"]]) {
      const wrapper = element("label", label), input = element("input");
      input.type = "date";
      input.className = "in";
      input.value = s[name];
      input.required = true;
      input.disabled = s.busy;
      input.onchange = () => (s[name] = input.value);
      wrapper.append(input);
      dates.append(wrapper);
    }
    const reload = element("button", "Consultar agenda");
    reload.className = "btn o";
    reload.type = "submit";
    reload.disabled = s.busy;
    dates.append(reload);
    filters.append(dates);
    filters.onsubmit = (event) => {
      event.preventDefault();
      if (!filters.reportValidity()) return;
      if (s.from > s.to) {
        s.error = "A data inicial deve ser anterior ou igual à final.";
        s.phase = s.items.length ? "ready" : "error";
        paint();
        return;
      }
      load(s);
    };
    const feedback = element("p", s.error || (s.phase === "loading" ? "Consultando a Agenda…" : s.message || ""));
    feedback.className = "ag-fb";
    if (s.error) feedback.dataset.kind = "err";
    feedback.setAttribute("role", "status");
    feedback.setAttribute("aria-live", "polite");
    rem.append(filters, feedback);
    if (s.phase === "error" && s.view !== "week") {
      const retry = element("button", "Tentar de novo");
      retry.type = "button";
      retry.className = "btn o ag-retry";
      retry.onclick = () => load(s);
      rem.append(retry);
    }
    if (s.phase === "error" && s.items.length && s.view !== "week")
      rem.append(element("p", "A lista exibida pode estar desatualizada. Consulte novamente antes de alterar."));
    if (hasPending) {
      const resume = element("button", "Retomar lembrete pendente");
      resume.className = "btn o";
      resume.disabled = s.busy || !canWrite();
      resume.onclick = () => create(true);
      rem.append(resume);
    }
    if (s.truncated) rem.append(element("p", "Exibindo até 500 lembretes. Reduza o período para consultar os demais."));
    /* filtros de situação (só na lista) */
    const counts = { all: live.length, pending: kp.pend, late: kp.late, done: kp.done };
    const chips = element("div");
    chips.className = "ag-fl";
    chips.setAttribute("role", "group");
    chips.setAttribute("aria-label", "Filtrar lembretes por situação");
    for (const [v, t] of FILTERS) {
      const b = element("button", t + " · " + counts[v]);
      b.type = "button";
      b.className = "ag-fc";
      b.dataset.f = v;
      b.setAttribute("aria-pressed", String(s.filter === v));
      b.onclick = () => {
        s.filter = v;
        paint();
      };
      chips.append(b);
    }
    chips.hidden = s.view === "week" || !live.length;
    rem.append(chips);
    const shown = live.filter((i) => s.filter === "all" || (s.filter === "late" ? isLate(i, now) : i.status === s.filter));
    const list = element("div");
    list.className = "ag-list";
    if (s.phase === "loading" && !live.length) {
      list.setAttribute("aria-hidden", "true");
      for (let n = 0; n < 3; n++) {
        const sk = element("div");
        sk.className = "ag-sk";
        list.append(sk);
      }
    }
    let previous, group;
    const rel = { [shift(-1)]: "Ontem", [shift(0)]: "Hoje", [shift(1)]: "Amanhã" };
    for (const item of shown) {
      const date = new Date(item.scheduled_for), day = localDate(date);
      if (day !== previous) {
        group = element("div");
        group.className = "ag-day";
        const h = element("h3", date.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long", year: "numeric" }));
        if (rel[day]) {
          const tag = element("span", rel[day]);
          tag.className = "ag-rel";
          h.append(tag);
        }
        group.append(h);
        list.append(group);
        previous = day;
      }
      const line = element("div"), late = isLate(item, now);
      line.className = "agi" + (item.status === "done" ? " done" : "") + (late ? " late" : "");
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
      const st = element("strong", item.title);
      details.append(st);
      if (late) {
        const lt = element("span", "Atrasado");
        lt.className = "ag-late";
        details.append(lt);
      }
      if (item.client_name) {
        const cl = element("p", "Cliente: " + item.client_name);
        cl.className = "ag-meta";
        details.append(cl);
      }
      if (item.notes) {
        const nt = element("p", item.notes);
        nt.className = "ag-meta";
        details.append(nt);
      }
      const dup = element("button", "Duplicar");
      dup.className = "btn o";
      dup.type = "button";
      dup.title = "Cria um novo lembrete com os mesmos dados. A API não permite editar um lembrete já salvo.";
      dup.disabled = done.disabled;
      dup.onclick = () => create(false, { title: item.title, notes: item.notes || "", cliente_id: item.cliente_id, date: shift(1) });
      const cancel = element("button", "Cancelar");
      cancel.className = "btn o";
      cancel.type = "button";
      cancel.disabled = done.disabled;
      cancel.onclick = () => {
        if (cancel.dataset.armed) return change(item, "cancelled", true);
        cancel.dataset.armed = "1";
        cancel.textContent = "Confirmar cancelamento";
        cancel.classList.add("is-armed");
        setTimeout(() => {
          if (cancel.isConnected && cancel.dataset.armed) {
            delete cancel.dataset.armed;
            cancel.textContent = "Cancelar";
            cancel.classList.remove("is-armed");
          }
        }, 5000);
      };
      line.append(done, element("time", hhmm(date)), details, dup, cancel);
      group.append(line);
    }
    if (s.phase === "ready" && live.length && !shown.length) {
      const e = element("div");
      e.className = "ag-empty";
      e.append(element("p", "Nenhum lembrete nesta situação."));
      const all = element("button", "Ver todos");
      all.type = "button";
      all.className = "btn o";
      all.onclick = () => {
        s.filter = "all";
        paint();
      };
      e.append(all);
      list.append(e);
    }
    if (s.phase === "ready" && !live.length) {
      const empty = element("div");
      empty.className = "ag-empty";
      const ic = element("span");
      ic.className = "ag-ei";
      ic.setAttribute("aria-hidden", "true");
      ic.append(icon("M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"));
      const t = element("p", "Nenhum lembrete neste período.");
      t.className = "ag-et";
      const hint = element("p", "Crie um lembrete ou amplie o período acima.");
      hint.className = "ag-eh";
      empty.append(ic, t, hint);
      if (canWrite()) {
        const e2 = element("button", "Novo lembrete");
        e2.type = "button";
        e2.className = "btn o";
        e2.onclick = () => create();
        empty.append(e2);
      }
      list.append(empty);
    }
    if (s.view === "week" && window.SocialMEIAgendaWeek) {
      filters.hidden = true;
      feedback.hidden = !(s.message && !s.error && s.phase === "ready");
      list.hidden = true;
      rem.append(weekNode(s));
    }
    rem.append(list);
    section.append(rem);
    view.replaceChildren(section);
    if (s.restore != null) {
      const b = section.querySelectorAll(".wk-nav button")[s.restore];
      if (b && !b.disabled) {
        b.focus();
        s.restore = null;
      } else if (!b && s.phase !== "loading") s.restore = null;
    }
    document.dispatchEvent(new Event("socialmei-agenda-painted"));
  }
  /* Atualiza só o que depende dos agendamentos de serviços/horário, sem repintar a página inteira
     (evita perder foco e evita laço com o componente de agendamentos). */
  function refreshLive(force) {
    if (!active()) return;
    const root = document.querySelector(".sm-agenda[data-agenda]");
    if (!root) return;
    const s = current(), api = window.SocialMEIAppointments;
    const snap = api?.snapshot?.();
    const sig = snap ? snap.phase + "|" + snap.from + "|" + snap.to + "|" + snap.items.map((r) => r.id + ":" + r.revision + ":" + r.status).join(",") : "none";
    if (!force && sig === s.apSig) return;
    s.apSig = sig;
    const holder = root.querySelector("[data-ag-nexth]");
    if (holder) {
      const nn = nextNode(s);
      holder.replaceChildren(...(nn ? [nn] : []));
    }
    const old = root.querySelector(".wk");
    if (old && s.view === "week") old.replaceWith(weekNode(s));
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
  document.addEventListener("socialmei-appointments-changed", () => refreshLive(false));
  document.addEventListener("socialmei-hours-changed", () => refreshLive(true));
  /* atalhos: N = novo lembrete (fora de campos e diálogos) */
  document.addEventListener("keydown", (ev) => {
    if (!active() || ev.altKey || ev.ctrlKey || ev.metaKey || ev.key.toLowerCase() !== "n") return;
    const t = ev.target;
    if (t && (/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(t.tagName) && t.tagName !== "BUTTON" || t.isContentEditable)) return;
    if (document.querySelector("dialog[open]")) return;
    const s = current();
    if (s.busy || s.phase !== "ready" || !canWrite()) return;
    ev.preventDefault();
    create();
  });
  setInterval(() => {
    if (!active()) return;
    for (const n of document.querySelectorAll(".ag-nx-in[data-at]")) n.textContent = relIn(Number(n.dataset.at));
  }, 30000);
  window.SocialMEIAgenda = {
    parseQuick,
    relIn,
    refresh: () => load(current()),
    /* v7.0: usado por Caixa, Clientes e Oportunidades para abrir o mesmo formulário já preenchido. */
    create: (preset) => create(false, preset || null),
    /* leitura dos lembretes já carregados, sem nova chamada à API */
    snapshot: () => ({ scope: current().scope, phase: current().phase, from: current().from, to: current().to, items: current().items.slice() }),
  };
  mount();
})();
