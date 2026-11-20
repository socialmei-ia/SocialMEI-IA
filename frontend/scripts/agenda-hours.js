/* Agenda · Funcionamento e disponibilidade.
   Persiste só pelo contrato existente: PATCH /auth/profile { nome_negocio, configuracao_negocio:{telefone,horario} }
   (o mesmo de Configurações → Dados do negócio). O texto de horário é o que clientes e o menu veem; a
   disponibilidade para agendar continua calculada pelo servidor (serviços, recursos, /agenda/availability).
   Turnos por profissional, fuso do negócio, bloqueios e canais de reserva não têm contrato conhecido:
   ficam "Preparados" e só habilitam com SocialMEIAgendaConfig.register(). */
(() => {
  const host = window.SocialMEIV22,
    auth = window.SocialMEIAuth;
  if (!host?.remote || window.SocialMEIAgendaConfig) return;
  const DAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
  const MAX = 160;
  const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
  const writer = () => ["owner", "admin"].includes(host.identity?.papel);

  /* ---------- texto <-> modelo (puro) ---------- */
  const empty = () => DAYS.map(() => []); // por dia: lista de [abre, fecha]
  const key = (shifts) => shifts.map((s) => s.join("–")).join(" e ");
  function serialize(model) {
    const parts = [];
    let i = 0;
    while (i < 7) {
      if (!model[i].length) {
        i++;
        continue;
      }
      let j = i;
      while (j + 1 < 7 && key(model[j + 1]) === key(model[i]) && model[j + 1].length) j++;
      const days =
        i === j ? DAYS[i] : j === i + 1 ? DAYS[i] + " e " + DAYS[j] : DAYS[i] + " a " + DAYS[j];
      parts.push(days + " " + key(model[i]));
      i = j + 1;
    }
    return parts.join("; ");
  }
  function parse(text) {
    const model = empty();
    const t = String(text || "").trim();
    if (!t) return model;
    for (const part of t.split("; ")) {
      const m =
        /^(Seg|Ter|Qua|Qui|Sex|Sáb|Dom)(?: (a|e) (Seg|Ter|Qua|Qui|Sex|Sáb|Dom))? (\d\d:\d\d–\d\d:\d\d(?: e \d\d:\d\d–\d\d:\d\d)*)$/.exec(
          part,
        );
      if (!m) return null;
      const a = DAYS.indexOf(m[1]),
        b = m[3] ? DAYS.indexOf(m[3]) : a;
      if (m[2] === "a" ? b < a : false) return null;
      const shifts = m[4].split(" e ").map((x) => x.split("–"));
      if (!shifts.every((s) => TIME.test(s[0]) && TIME.test(s[1]) && s[0] < s[1])) return null;
      for (let d = 0; d < 7; d++)
        if (m[2] === "e" ? d === a || d === b : d >= a && d <= b) {
          if (model[d].length) return null;
          model[d] = shifts.map((s) => [...s]);
        }
    }
    return serialize(model) === t ? model : null;
  }
  function validate(model) {
    for (let d = 0; d < 7; d++) {
      const s = model[d];
      for (const [o, c] of s) {
        if (!TIME.test(o) || !TIME.test(c)) return DAYS[d] + ": informe horários válidos.";
        if (o >= c) return DAYS[d] + ": o fechamento deve ser depois da abertura.";
      }
      if (s.length === 2 && s[0][1] > s[1][0])
        return DAYS[d] + ": os turnos não podem se sobrepor.";
    }
    const text = serialize(model);
    if (text.length > MAX)
      return (
        "O texto ficou com " +
        text.length +
        " caracteres (máximo " +
        MAX +
        "). Use menos turnos diferentes."
      );
    return "";
  }

  /* ---------- adaptadores ---------- */
  const SLOTS = {
    resourceHours: "Turnos e horários por profissional/recurso",
    timezone: "Fuso horário do negócio",
    blocks: "Bloqueios de horários",
    bookingChannels: "Reservas por WhatsApp e Instagram",
  };
  const adapters = {};
  function register(impl) {
    if (!impl || typeof impl !== "object") throw Error("Adaptador inválido.");
    for (const [n, fn] of Object.entries(impl)) {
      if (!SLOTS[n] || typeof fn !== "function") throw Error("Operação desconhecida: " + n);
      adapters[n] = fn;
    }
    paint();
  }

  /* ---------- DOM ---------- */
  const node = (t, c, x) => {
    const n = document.createElement(t);
    if (c) n.className = c;
    if (x !== undefined) n.textContent = x;
    return n;
  };
  let model = empty(),
    raw = "",
    unparsed = false,
    dirty = false,
    busy = false,
    msg = { t: "", k: "" },
    open = false,
    owner = "";
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  function loadFromProfile() {
    owner = scope();
    raw = String(auth.current?.negocio?.configuracao?.horario || "");
    const p = parse(raw);
    unparsed = p === null && raw.trim() !== "";
    model = p || empty();
    dirty = false;
  }
  function timeInput(value, label, on) {
    const i = node("input");
    i.type = "time";
    i.value = value;
    i.setAttribute("aria-label", label);
    i.disabled = busy || !writer();
    i.addEventListener("change", () => {
      on(i.value);
      dirty = true;
      msg = { t: "", k: "" };
      paintSummary();
    });
    return i;
  }
  function dayRow(d) {
    const row = node("div", "sm-ah-day"),
      shifts = model[d];
    const cb = node("input");
    cb.type = "checkbox";
    cb.checked = shifts.length > 0;
    cb.disabled = busy || !writer();
    cb.setAttribute("aria-label", "Abre na " + DAYS[d]);
    cb.addEventListener("change", () => {
      model[d] = cb.checked ? [["09:00", "18:00"]] : [];
      dirty = true;
      msg = { t: "", k: "" };
      paint();
    });
    const lab = node("label", "sm-ah-name");
    lab.append(cb, node("span", "", DAYS[d]));
    row.append(lab);
    const box = node("div", "sm-ah-shifts");
    if (!shifts.length) box.append(node("span", "sm-ah-closed", "Fechado"));
    shifts.forEach((s, n) => {
      const sh = node("span", "sm-ah-shift");
      sh.append(
        timeInput(s[0], DAYS[d] + " turno " + (n + 1) + " abre", (v) => (s[0] = v)),
        node("span", "", "às"),
        timeInput(s[1], DAYS[d] + " turno " + (n + 1) + " fecha", (v) => (s[1] = v)),
      );
      box.append(sh);
    });
    if (shifts.length) {
      const b = node("button", "btn o", shifts.length === 1 ? "+ Turno" : "Remover turno");
      b.type = "button";
      b.disabled = busy || !writer();
      b.addEventListener("click", () => {
        if (shifts.length === 1) shifts.push(["14:00", "18:00"]);
        else shifts.pop();
        dirty = true;
        paint();
      });
      box.append(b);
    }
    row.append(box);
    return row;
  }
  function paintSummary() {
    const el = document.querySelector("[data-ah-summary]");
    if (!el) return;
    const err = validate(model);
    el.textContent = err || "Será exibido como: " + (serialize(model) || "(sem horário definido)");
    el.dataset.kind = err ? "err" : "";
    const save = document.querySelector("[data-ah-save]");
    if (save) save.disabled = busy || !writer() || !dirty || !!err;
  }
  async function save() {
    const err = validate(model);
    if (err || busy || !writer()) return;
    if (
      unparsed &&
      !confirm(
        'O horário atual ("' +
          raw +
          '") foi escrito em outro formato e será substituído. Continuar?',
      )
    )
      return;
    const who = scope();
    busy = true;
    msg = { t: "Salvando…", k: "" };
    paint();
    try {
      const text = serialize(model),
        cur = auth.current.negocio;
      await auth.saveProfile({
        nome_negocio: cur.nome,
        configuracao_negocio: { ...(cur.configuracao || {}), horario: text },
      });
      if (who !== scope()) return;
      try {
        if (typeof S !== "undefined") S.biz.horario = text;
      } catch {
        /* tela de dados do negócio relê ao recarregar */
      }
      loadFromProfile();
      msg = { t: "Horário salvo no negócio.", k: "ok" };
    } catch (e) {
      msg = { t: (e?.message || "Não foi possível salvar.") + " Nada foi alterado.", k: "err" };
    } finally {
      busy = false;
      paint();
    }
  }
  async function run(name) {
    const fn = adapters[name];
    if (!fn || busy || !writer()) return;
    busy = true;
    msg = { t: SLOTS[name] + "…", k: "" };
    paint();
    try {
      await fn({ workspaceId: host.identity.negocio.id });
      msg = { t: "Concluído pelo servidor.", k: "ok" };
    } catch (e) {
      msg = { t: (e?.message || "Não foi possível concluir.") + " Nada foi alterado.", k: "err" };
    } finally {
      busy = false;
      paint();
    }
  }
  function paint() {
    const root = document.querySelector("[data-agenda-hours]");
    if (!root) return;
    const body = root.querySelector("[data-ah-body]");
    body.replaceChildren();
    if (unparsed)
      body.append(
        node(
          "p",
          "sm-hub-detail",
          "Horário atual em texto livre: “" +
            raw +
            "”. Ao salvar um novo horário aqui, ele será substituído.",
        ),
      );
    const grid = node("div", "sm-ah-grid");
    for (let d = 0; d < 7; d++) grid.append(dayRow(d));
    body.append(grid);
    body.append(
      node(
        "p",
        "sm-hub-detail",
        "Fuso do dispositivo: " +
          Intl.DateTimeFormat().resolvedOptions().timeZone +
          ". O fuso do negócio ainda não é configurável aqui.",
      ),
    );
    const sum = node("p", "sm-ah-summary");
    sum.dataset.ahSummary = "true";
    body.append(sum);
    const st = node("p", "sm-hub-status", msg.t);
    st.dataset.kind = msg.k;
    st.setAttribute("role", "status");
    body.append(st);
    const act = node("div", "sm-hub-actions"),
      s = node("button", "btn", "Salvar horário");
    s.type = "button";
    s.dataset.ahSave = "true";
    s.addEventListener("click", save);
    const r = node("button", "btn o", "Descartar alterações");
    r.type = "button";
    r.disabled = busy || !dirty;
    r.addEventListener("click", () => {
      loadFromProfile();
      msg = { t: "", k: "" };
      paint();
    });
    act.append(s, r);
    body.append(act);
    if (!writer())
      body.append(
        node("p", "sm-hub-detail", "Somente responsáveis pelo negócio podem alterar o horário."),
      );
    const prep = node("details", "sm-hub-prepared");
    prep.open = open;
    prep.addEventListener("toggle", () => {
      open = prep.open;
    });
    prep.append(node("summary", "", "Operações preparadas (dependem da API)"));
    const ul = node("ul");
    for (const [n, label] of Object.entries(SLOTS)) {
      const li = node("li"),
        fn = adapters[n],
        b = node("button", "btn o", fn ? "Executar" : "Indisponível");
      b.type = "button";
      b.disabled = !fn || busy || !writer();
      b.dataset.ahAction = n;
      b.title = fn ? "" : "Interface pronta; falta a API correspondente.";
      b.addEventListener("click", () => run(n));
      const badge = node(
        "span",
        "sm-hub-badge sm-hub-" + (fn ? "ok" : "off"),
        fn ? "Disponível" : "Aguardando API",
      );
      li.append(node("span", "", label), badge, b);
      ul.append(li);
    }
    prep.append(ul);
    body.append(prep);
    paintSummary();
  }
  function mount() {
    if (location.hash !== "#/agenda") return;
    const view = document.getElementById("v");
    if (!view) return;
    if (owner !== scope()) loadFromProfile();
    if (view.querySelector("[data-agenda-hours]")) return;
    const root = node("details", "sm-ah");
    root.dataset.agendaHours = "true";
    root.open = openPanel;
    root.addEventListener("toggle", () => {
      openPanel = root.open;
    });
    const inner = node("div", "sm-ah-body");
    inner.dataset.ahBody = "true";
    root.append(node("summary", "", "Funcionamento e disponibilidade"), inner);
    const anchor = view.querySelector("[data-appointments]");
    anchor ? anchor.before(root) : (view.querySelector(".sm-agenda") || view).append(root);
    paint();
  }
  let openPanel = false;
  document.addEventListener("socialmei-agenda-painted", mount);
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  window.SocialMEIAgendaConfig = {
    register,
    serialize,
    parse,
    validate,
    slots: Object.freeze(Object.keys(SLOTS)),
  };
  queueMicrotask(mount);
})();
