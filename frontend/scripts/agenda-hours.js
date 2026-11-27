/* Agenda · Funcionamento e disponibilidade (v7.3: resumo, linha do tempo, presets, cópia entre dias, erros por dia,
   aviso de alterações não salvas e confirmação lida de volta do servidor). O formato salvo NÃO mudou.
   Persiste só pelo contrato existente: PATCH /auth/profile { nome_negocio, configuracao_negocio:{telefone,horario} }
   (o mesmo de Configurações → Dados do negócio). O texto de horário é o que clientes e o menu veem; a
   disponibilidade para agendar continua calculada pelo servidor (serviços, recursos, /agenda/availability).
   Turnos por profissional, fuso do negócio, bloqueios e canais de reserva não têm contrato conhecido:
   ficam "Preparados" e só habilitam com SocialMEIAgendaConfig.register(). */
(() => {
  const host = window.SocialMEIV22, auth = window.SocialMEIAuth;
  if (!host?.remote || window.SocialMEIAgendaConfig) return;
  const DAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
  const MAX = 160;
  const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
  const writer = () => ["owner", "admin"].includes(host.identity?.papel);

  /* ---------- texto <-> modelo (puro) ---------- */
  const empty = () => DAYS.map(() => []);               // por dia: lista de [abre, fecha]
  const key = (shifts) => shifts.map((s) => s.join("–")).join(" e ");
  function serialize(model) {
    const parts = []; let i = 0;
    while (i < 7) {
      if (!model[i].length) { i++; continue; }
      let j = i; while (j + 1 < 7 && key(model[j + 1]) === key(model[i]) && model[j + 1].length) j++;
      const days = i === j ? DAYS[i] : j === i + 1 ? DAYS[i] + " e " + DAYS[j] : DAYS[i] + " a " + DAYS[j];
      parts.push(days + " " + key(model[i])); i = j + 1;
    }
    return parts.join("; ");
  }
  function parse(text) {
    const model = empty(); const t = String(text || "").trim();
    if (!t) return model;
    for (const part of t.split("; ")) {
      const m = /^(Seg|Ter|Qua|Qui|Sex|Sáb|Dom)(?: (a|e) (Seg|Ter|Qua|Qui|Sex|Sáb|Dom))? (\d\d:\d\d–\d\d:\d\d(?: e \d\d:\d\d–\d\d:\d\d)*)$/.exec(part);
      if (!m) return null;
      const a = DAYS.indexOf(m[1]), b = m[3] ? DAYS.indexOf(m[3]) : a;
      if (m[2] === "a" ? b < a : false) return null;
      const shifts = m[4].split(" e ").map((x) => x.split("–"));
      if (!shifts.every((s) => TIME.test(s[0]) && TIME.test(s[1]) && s[0] < s[1])) return null;
      for (let d = 0; d < 7; d++) if (m[2] === "e" ? d === a || d === b : d >= a && d <= b) { if (model[d].length) return null; model[d] = shifts.map((s) => [...s]); }
    }
    return serialize(model) === t ? model : null;
  }
  const toMin = (t) => (TIME.test(t) ? +t.slice(0, 2) * 60 + +t.slice(3) : NaN);
  const toHM = (m) => String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
  /* Erro de um dia (sem o nome do dia), ou "". Turnos devem estar em ordem e sem sobreposição. */
  function dayError(shifts) {
    for (const [o, c] of shifts) {
      if (!TIME.test(o) || !TIME.test(c)) return "informe horários válidos.";
      if (o >= c) return "o fechamento deve ser depois da abertura.";
    }
    for (let i = 0; i + 1 < shifts.length; i++) if (shifts[i][1] > shifts[i + 1][0]) return "os turnos não podem se sobrepor.";
    return "";
  }
  function validate(model) {
    for (let d = 0; d < 7; d++) {
      const e = dayError(model[d]);
      if (e) return DAYS[d] + ": " + e;
    }
    const text = serialize(model);
    if (text.length > MAX) return "O texto ficou com " + text.length + " caracteres (máximo " + MAX + "). Use menos turnos diferentes.";
    return "";
  }
  /* Horas abertas por dia e na semana (minutos). Pausa = intervalo entre dois turnos. */
  function stats(model) {
    const per = model.map((sh) => sh.reduce((t, [o, c]) => t + Math.max(0, toMin(c) - toMin(o)), 0));
    const open = model.map((sh) => sh.length > 0);
    return { per, open, days: open.filter(Boolean).length, total: per.reduce((a, b) => a + b, 0) };
  }
  const fmtDur = (m) => (m % 60 ? Math.floor(m / 60) + " h " + (m % 60) + " min" : Math.floor(m / 60) + " h");
  /* ---------- adaptadores ---------- */
  const SLOTS = { resourceHours: "Turnos e horários por profissional/recurso", timezone: "Fuso horário do negócio", blocks: "Bloqueios de horários", specialDays: "Horários especiais e feriados", bookingChannels: "Reservas por WhatsApp e Instagram" };
  const adapters = {};
  function register(impl) {
    if (!impl || typeof impl !== "object") throw Error("Adaptador inválido.");
    for (const [n, fn] of Object.entries(impl)) { if (!SLOTS[n] || typeof fn !== "function") throw Error("Operação desconhecida: " + n); adapters[n] = fn; }
    paint();
  }

  /* ---------- DOM ---------- */
  const node = (t, c, x) => { const n = document.createElement(t); if (c) n.className = c; if (x !== undefined) n.textContent = x; return n; };
  const clone = (m) => m.map((sh) => sh.map((x) => [...x]));
  let model = empty(), raw = "", unparsed = false, dirty = false, busy = false, msg = { t: "", k: "" }, open = false, owner = "", savedAt = "";
  let openPanel = false;
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const announce = () => document.dispatchEvent(new Event("socialmei-hours-changed"));
  function loadFromProfile() {
    owner = scope();
    raw = String(auth.current?.negocio?.configuracao?.horario || "");
    const p = parse(raw); unparsed = p === null && raw.trim() !== ""; model = p || empty(); dirty = false;
    announce();
  }
  const touch = () => { dirty = true; savedAt = ""; msg = { t: "", k: "" }; };
  /* Situação de hoje a partir do horário SALVO (não do rascunho). É horário comercial, não disponibilidade. */
  function todayLine() {
    const saved = parse(raw);
    if (!saved || !raw.trim()) return "";
    const now = new Date(), d = (now.getDay() + 6) % 7, cur = now.getHours() * 60 + now.getMinutes(), sh = saved[d];
    if (!sh.length) return "Hoje: fechado (horário comercial).";
    const cell = sh.find(([o, c]) => cur >= toMin(o) && cur < toMin(c));
    if (cell) return "Agora: aberto até " + cell[1] + " (horário comercial).";
    const next = sh.find(([o]) => cur < toMin(o));
    return next ? "Hoje abre às " + next[0] + " (horário comercial)." : "Hoje: já encerrou (horário comercial).";
  }
  function timeInput(value, label, on, invalid) {
    const i = node("input"); i.type = "time"; i.value = value; i.setAttribute("aria-label", label); i.disabled = busy || !writer(); i.required = true;
    if (invalid) i.setAttribute("aria-invalid", "true");
    i.addEventListener("change", () => { on(i.value); touch(); refreshRows(); paintSummary(); });
    return i;
  }
  /* Linha do tempo do dia: turnos em azul, pausa como vão. Escala 06–22 h, ampliada se houver turnos fora dela. */
  function timeline(shifts) {
    const tl = node("div", "sm-ah-tl"); tl.setAttribute("aria-hidden", "true");
    const mins = shifts.flat().map(toMin).filter((x) => !Number.isNaN(x));
    const lo = Math.min(360, mins.length ? Math.floor(Math.min(...mins) / 60) * 60 : 360), hi = Math.max(1320, mins.length ? Math.ceil(Math.max(...mins) / 60) * 60 : 1320);
    shifts.forEach(([o, c]) => {
      const a = toMin(o), b = toMin(c); if (Number.isNaN(a) || Number.isNaN(b) || b <= a) return;
      const seg = node("i", "sm-ah-seg"); seg.style.left = ((a - lo) / (hi - lo)) * 100 + "%"; seg.style.width = ((b - a) / (hi - lo)) * 100 + "%"; tl.append(seg);
    });
    return tl;
  }
  function pauseText(shifts) {
    return shifts.length > 1 && !dayError(shifts) && shifts[0][1] < shifts[1][0] ? "Pausa " + shifts[0][1] + "–" + shifts[1][0] : "";
  }
  const rows = [];
  function refreshRow(d) {
    const r = rows[d]; if (!r) return;
    const shifts = model[d], err = dayError(shifts);
    r.tl.replaceWith((r.tl = timeline(shifts)));
    r.err.textContent = err ? DAYS[d] + ": " + err : ""; r.err.hidden = !err;
    r.pause.textContent = pauseText(shifts);
    r.row.classList.toggle("is-bad", !!err);
    r.row.querySelectorAll(".sm-ah-shift input").forEach((i) => (err ? i.setAttribute("aria-invalid", "true") : i.removeAttribute("aria-invalid")));
  }
  const refreshRows = () => { for (let d = 0; d < 7; d++) refreshRow(d); };
  const COPY = [["", "Copiar para…"], ["util", "Dias úteis (Seg–Sex)"], ["sab", "Seg–Sáb"], ["todos", "Todos os dias"], ["fim", "Fim de semana"], ["prox", "Dia seguinte"]];
  function copyTo(d, how) {
    const src = model[d]; if (!src.length || dayError(src)) return;
    const targets = { util: [0, 1, 2, 3, 4], sab: [0, 1, 2, 3, 4, 5], todos: [0, 1, 2, 3, 4, 5, 6], fim: [5, 6], prox: [(d + 1) % 7] }[how] || [];
    targets.forEach((t) => { if (t !== d) model[t] = clone([src])[0]; });
    touch(); msg = { t: "Horário de " + DAYS[d] + " copiado. Confira e salve.", k: "" }; paint();
  }
  function dayRow(d) {
    const dis = busy || !writer(), shifts = model[d], err = dayError(shifts);
    const row = node("div", "sm-ah-day" + (shifts.length ? "" : " is-off") + (err ? " is-bad" : "")); row.dataset.day = DAYS[d];
    const cb = node("input"); cb.type = "checkbox"; cb.checked = shifts.length > 0; cb.disabled = dis;
    cb.setAttribute("aria-label", "Abre na " + DAYS[d]);
    cb.addEventListener("change", () => { model[d] = cb.checked ? [["09:00", "18:00"]] : []; touch(); paint(); });
    const lab = node("label", "sm-ah-name"); lab.append(cb, node("span", "", DAYS[d]), node("small", "sm-ah-state", shifts.length ? "Aberto" : "Fechado"));
    row.append(lab);
    const box = node("div", "sm-ah-shifts");
    if (!shifts.length) box.append(node("span", "sm-ah-closed", "Fechado · marque o dia para definir horários"));
    shifts.forEach((s, n) => {
      const sh = node("span", "sm-ah-shift");
      sh.append(timeInput(s[0], DAYS[d] + " turno " + (n + 1) + " abre", (v) => (s[0] = v), !!err), node("span", "", "às"), timeInput(s[1], DAYS[d] + " turno " + (n + 1) + " fecha", (v) => (s[1] = v), !!err));
      box.append(sh);
    });
    if (shifts.length) {
      const b = node("button", "btn o sm-ah-mini", shifts.length === 1 ? "+ Pausa / 2º turno" : "Remover 2º turno"); b.type = "button";
      const last = shifts[shifts.length - 1], room = shifts.length === 1 && toMin(last[1]) >= 21 * 60;
      b.disabled = dis || (shifts.length === 1 && (room || !!err)); if (room) b.title = "Não há espaço depois do primeiro turno.";
      b.addEventListener("click", () => {
        if (shifts.length === 1) { const c = toMin(shifts[0][1]); shifts.push([toHM(Math.min(c + 60, 22 * 60)), toHM(Math.min(c + 300, 23 * 60 + 59))]); } else shifts.pop();
        touch(); paint();
      });
      box.append(b);
      const sel = node("select", "sm-ah-copy"); sel.setAttribute("aria-label", "Copiar o horário de " + DAYS[d] + " para outros dias"); sel.disabled = dis || !!err;
      COPY.forEach(([v, t]) => { const o = node("option", "", t); o.value = v; sel.append(o); });
      sel.addEventListener("change", () => copyTo(d, sel.value));
      box.append(sel);
    }
    row.append(box);
    const tl = timeline(shifts), pause = node("small", "sm-ah-pause", pauseText(shifts)), er = node("p", "sm-ah-err", err ? DAYS[d] + ": " + err : ""); er.setAttribute("role", "alert"); er.hidden = !err;
    const side = node("div", "sm-ah-vis"); side.append(tl, pause); row.append(side, er);
    rows[d] = { row, tl, err: er, pause };
    return row;
  }
  const PRESETS = [
    ["Seg–Sex 9h–18h", () => model.map((_, d) => (d < 5 ? [["09:00", "18:00"]] : []))],
    ["Seg–Sáb 9h–18h", () => model.map((_, d) => (d < 6 ? [["09:00", "18:00"]] : []))],
    ["Almoço 12h–14h", () => model.map((sh) => (sh.length === 1 && sh[0][0] < "12:00" && sh[0][1] > "14:00" ? [[sh[0][0], "12:00"], ["14:00", sh[0][1]]] : sh))],
    ["Fechar fim de semana", () => model.map((sh, d) => (d >= 5 ? [] : sh))],
    ["Limpar tudo", () => empty()],
  ];
  function paintSummary() {
    const err = validate(model), dis = busy || !writer();
    const el = document.querySelector("[data-ah-summary]");
    if (el) {
      const st = stats(model), closed = DAYS.filter((_, d) => !st.open[d]);
      el.replaceChildren();
      if (err) { el.dataset.kind = "err"; el.textContent = err; }
      else {
        el.dataset.kind = "";
        el.append(node("b", "", st.days ? "Abre " + st.days + (st.days === 1 ? " dia" : " dias") + " · " + fmtDur(st.total) + " por semana" : "Nenhum dia aberto"));
        if (closed.length && st.days) el.append(node("span", "", " · Fechado: " + closed.join(", ")));
        const txt = serialize(model);
        el.append(node("br"), node("span", "", "Será exibido como: " + (txt || "(sem horário definido)") + " · " + txt.length + "/" + MAX));
      }
    }
    const save = document.querySelector("[data-ah-save]"); if (save) save.disabled = dis || !dirty || !!err;
    const disc = document.querySelector("[data-ah-discard]"); if (disc) disc.disabled = busy || !dirty;
    const flag = document.querySelector("[data-ah-flag]"); if (flag) { flag.hidden = !dirty; }
    const head = document.querySelector("[data-ah-head]"); if (head) head.dataset.dirty = String(dirty);
    const st2 = document.querySelector("[data-ah-status]");
    if (st2) { st2.textContent = dirty && !msg.t ? "Alterações não salvas. Os clientes ainda veem o horário anterior." : msg.t; st2.dataset.kind = dirty && !msg.t ? "warn" : msg.k; }
  }
  async function save() {
    const err = validate(model); if (err || busy || !writer() || !dirty) return;
    if (unparsed && !confirm("O horário atual (\"" + raw + "\") foi escrito em outro formato e será substituído. Continuar?")) return;
    const who = scope(); busy = true; msg = { t: "Salvando…", k: "" }; paint();
    try {
      const text = serialize(model), cur = auth.current.negocio;
      await auth.saveProfile({ nome_negocio: cur.nome, configuracao_negocio: { ...(cur.configuracao || {}), horario: text } });
      if (who !== scope()) return;
      const back = String(auth.current?.negocio?.configuracao?.horario || "");
      if (back !== text) { loadFromProfile(); throw Error("O servidor respondeu, mas o horário guardado é diferente do enviado. Confira em Configurações → Dados do negócio"); }
      try { if (typeof S !== "undefined") S.biz.horario = text; } catch { /* tela de dados do negócio relê ao recarregar */ }
      loadFromProfile(); savedAt = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
      msg = { t: "Horário salvo e confirmado pelo servidor às " + savedAt + ".", k: "ok" };
    } catch (e) {
      if (who !== scope()) { /* outra empresa/usuário: nada a mostrar aqui */ }
      else if (e?.code === "operation_unconfirmed" || (!e?.status && !e?.code && /confirmar a opera/i.test(e?.message || ""))) {
        /* v7.8 · resultado incerto: o servidor pode ter gravado. Reconsulta o contrato existente (GET /auth/session) antes de afirmar qualquer coisa. */
        const text = serialize(model);
        msg = { t: "Conferindo no servidor se o horário foi salvo…", k: "" }; paint();
        let seen = null;
        try { const ses = await auth.request("/auth/session"); seen = String(ses?.negocio?.configuracao?.horario ?? ""); } catch { seen = null; }
        if (who !== scope()) { /* contexto mudou durante a conferência */ }
        else if (seen === text) {
          try { const c = auth.current?.negocio?.configuracao; if (c && !Object.isFrozen(c)) c.horario = text; } catch { /* leitura de perfil local é só cache */ }
          try { if (typeof S !== "undefined") S.biz.horario = text; } catch { /* idem */ }
          loadFromProfile(); savedAt = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
          msg = { t: "A resposta se perdeu, mas o servidor confirmou o horário salvo às " + savedAt + ".", k: "ok" };
        } else if (seen !== null) {
          msg = { t: "Conferi no servidor: o horário não foi alterado. Suas edições continuam aqui; tente salvar de novo.", k: "err" };
        } else {
          msg = { t: "Não consegui confirmar se o horário foi salvo (sem resposta do servidor). Confira em Configurações → Dados do negócio antes de repetir; suas edições continuam aqui.", k: "err" };
        }
      }
      else msg = { t: (e?.message || "Não foi possível salvar.") + (dirty ? (e?.status ? ". O servidor recusou a alteração; suas edições continuam aqui." : ". Suas edições continuam aqui.") : "."), k: "err" };
    }
    finally { busy = false; paint(); }
  }
  async function run(name) {
    const fn = adapters[name]; if (!fn || busy || !writer()) return;
    busy = true; msg = { t: SLOTS[name] + "…", k: "" }; paint();
    try { await fn({ workspaceId: host.identity.negocio.id }); msg = { t: "Concluído pelo servidor.", k: "ok" }; }
    catch (e) { msg = { t: (e?.message || "Não foi possível concluir.") + (e?.status ? " O servidor recusou; nada foi alterado." : " Confira o resultado antes de repetir."), k: "err" }; }
    finally { busy = false; paint(); }
  }
  function paint() {
    const root = document.querySelector("[data-agenda-hours]"); if (!root) return;
    const sm = root.querySelector("[data-ah-head]"); if (sm) { sm.querySelector("[data-ah-today]").textContent = todayLine() || (raw.trim() ? "Horário em texto livre." : "Horário ainda não definido."); }
    const body = root.querySelector("[data-ah-body]"); const keep = document.activeElement && body.contains(document.activeElement) ? document.activeElement.getAttribute("aria-label") : null;
    body.replaceChildren(); rows.length = 0;
    const note = node("p", "sm-ah-note"); note.append(node("b", "", "Horário comercial ≠ disponibilidade. "), document.createTextNode("Aqui você define o horário que clientes e o menu veem. Os horários realmente livres para agendar são calculados pelo servidor (serviços, profissionais e agendamentos já feitos)."));
    body.append(note);
    if (unparsed) body.append(node("p", "sm-hub-detail sm-ah-warn", "Horário atual em texto livre: “" + raw + "”. Ao salvar um novo horário aqui, ele será substituído."));
    if (writer()) {
      const pr = node("div", "sm-ah-presets"); pr.setAttribute("role", "group"); pr.setAttribute("aria-label", "Atalhos de horário");
      PRESETS.forEach(([t, fn]) => { const b = node("button", "ag-chip sm-ah-preset", t); b.type = "button"; b.disabled = busy; b.addEventListener("click", () => { model = fn(); touch(); msg = { t: "Atalho aplicado: " + t + ". Revise e salve.", k: "" }; paint(); }); pr.append(b); });
      body.append(pr);
    }
    const grid = node("div", "sm-ah-grid"); for (let d = 0; d < 7; d++) grid.append(dayRow(d)); body.append(grid);
    const sum = node("p", "sm-ah-summary"); sum.dataset.ahSummary = "true"; sum.setAttribute("aria-live", "polite"); body.append(sum);
    body.append(node("p", "sm-hub-detail", "Fuso do dispositivo: " + Intl.DateTimeFormat().resolvedOptions().timeZone + ". O fuso do negócio ainda não é configurável aqui."));
    const bar = node("div", "sm-ah-bar");
    const st = node("p", "sm-hub-status", ""); st.dataset.ahStatus = "true"; st.setAttribute("role", "status"); bar.append(st);
    const act = node("div", "sm-hub-actions"), s = node("button", "btn", busy ? "Salvando…" : "Salvar horário"); s.type = "button"; s.dataset.ahSave = "true"; s.addEventListener("click", save);
    const r = node("button", "btn o", "Descartar alterações"); r.type = "button"; r.dataset.ahDiscard = "true"; r.addEventListener("click", () => { loadFromProfile(); msg = { t: "Alterações descartadas.", k: "" }; paint(); });
    act.append(s, r); bar.append(act); body.append(bar);
    if (!writer()) body.append(node("p", "sm-hub-detail", "Somente responsáveis pelo negócio podem alterar o horário."));
    const prep = node("details", "sm-hub-prepared"); prep.open = open; prep.addEventListener("toggle", () => { open = prep.open; });
    prep.append(node("summary", "", "Operações preparadas (dependem da API)")); const ul = node("ul");
    for (const [n, label] of Object.entries(SLOTS)) {
      const li = node("li"), fn = adapters[n], b = node("button", "btn o", fn ? "Executar" : "Indisponível"); b.type = "button"; b.disabled = !fn || busy || !writer(); b.dataset.ahAction = n;
      b.title = fn ? "" : "Interface pronta; falta a API correspondente."; b.addEventListener("click", () => run(n));
      const badge = node("span", "sm-hub-badge sm-hub-" + (fn ? "ok" : "off"), fn ? "Disponível" : "Aguardando API");
      li.append(node("span", "", label), badge, b); ul.append(li);
    }
    prep.append(ul); body.append(prep);
    paintSummary();
    if (keep) { const f = [...body.querySelectorAll("[aria-label]")].find((n) => n.getAttribute("aria-label") === keep && !n.disabled); f?.focus(); }
  }
  function mount() {
    if (location.hash !== "#/agenda") return;
    const view = document.getElementById("v"); if (!view) return;
    if (owner !== scope()) loadFromProfile();
    if (view.querySelector("[data-agenda-hours]")) return;
    const root = node("details", "sm-ah"); root.dataset.agendaHours = "true"; root.open = openPanel;
    root.addEventListener("toggle", () => { openPanel = root.open; });
    const head = node("summary", "sm-ah-sum"); head.dataset.ahHead = "true"; head.dataset.dirty = String(dirty);
    const t = node("span", "sm-ah-sumt"); t.append(node("b", "", "Funcionamento e disponibilidade"), node("small", "", ""));
    t.lastChild.dataset.ahToday = "true";
    const flag = node("span", "sm-ah-flag", "Alterações não salvas"); flag.dataset.ahFlag = "true"; flag.hidden = !dirty;
    head.append(t, flag);
    const inner = node("div", "sm-ah-body"); inner.dataset.ahBody = "true";
    root.append(head, inner);
    const anchor = view.querySelector("[data-appointments]"); anchor ? anchor.before(root) : (view.querySelector(".sm-agenda") || view).append(root);
    paint();
  }
  /* Evita perder edições sem querer ao fechar ou recarregar a página. */
  window.addEventListener("beforeunload", (e) => { if (dirty && location.hash === "#/agenda") { e.preventDefault(); e.returnValue = ""; } });
  document.addEventListener("socialmei-agenda-painted", mount);
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  window.SocialMEIAgendaConfig = { register, serialize, parse, validate, dayError, stats, slots: Object.freeze(Object.keys(SLOTS)) };
  queueMicrotask(mount);
})();
