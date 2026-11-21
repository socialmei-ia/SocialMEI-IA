/* Caixa Unificada · sugestões de cliente do CRM e rascunhos de IA.
   PREPARADO: não há contrato de backend confirmado para nenhum dos dois. A interface fala com adaptadores do
   frontend, desligados por padrão; registre-os na homologação com SocialMEIInboxAssist.register().
   Todos recebem { workspaceId, conversationId } e nunca recebem nem guardam chaves de API (a IA roda no servidor).
     customerCapabilities() -> { enabled: boolean }
     listCustomerSuggestions() -> { conversation_id, workspace_id, items:[{suggestion_id, cliente_id, nome, reason?}] }
     confirmCustomerSuggestion({suggestionId, clienteId}) -> void     rejectCustomerSuggestion({suggestionId}) -> void
     draftCapabilities() -> { enabled: boolean, reason?: string }
     generateDraft({expectedRevision}) -> { draft_id, conversation_id, workspace_id, text, based_on_revision }
   Garantias aqui: nada é associado sem clique + confirmação; nada é enviado (este módulo não tem código de envio):
   "Aceitar" só copia o texto para o campo de resposta, e o envio segue o fluxo existente com confirmação humana. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInboxAssist) return;
  const SLOTS = [
    "customerCapabilities",
    "listCustomerSuggestions",
    "confirmCustomerSuggestion",
    "rejectCustomerSuggestion",
    "draftCapabilities",
    "generateDraft",
  ];
  const adapters = {};
  const MAXTEXT = 4096;
  const writer = () => ["owner", "admin", "member"].includes(host.identity?.papel);
  const wid = () => host.identity?.negocio.id;
  const selected = () => {
    const m = /^#\/caixa\/(me-\d+)$/.exec(location.hash);
    return m && host.conversation(m[1]);
  };
  const el = (t, c, x) => {
    const n = document.createElement(t);
    if (c) n.className = c;
    if (x !== undefined) n.textContent = x;
    return n;
  };
  const btn = (label, fn, { primary = false, disabled = false } = {}) => {
    const b = el("button", "btn" + (primary ? "" : " o"), label);
    b.type = "button";
    b.disabled = disabled;
    b.addEventListener("click", fn);
    return b;
  };
  const msgOf = (e, map) => map?.[e?.code] || e?.message || "Não foi possível concluir.";

  /* estado por conversa; descartado quando muda a identidade (usuário/negócio) */
  let identity = null;
  const convs = new Map();
  const S = (id) => {
    if (identity !== host.identity) {
      convs.clear();
      identity = host.identity;
    }
    if (!convs.has(id))
      convs.set(id, {
        id,
        cs: { phase: "idle", items: [], msg: "", kind: "", busy: false, enabled: null },
        dr: {
          phase: "idle",
          text: "",
          draftId: null,
          basedOn: null,
          msg: "",
          kind: "",
          reason: "",
        },
      });
    return convs.get(id);
  };
  const live = (s) => identity === host.identity && selected()?.id === s.id;
  function register(impl) {
    if (!impl || typeof impl !== "object") throw Error("Adaptador inválido.");
    for (const [n, fn] of Object.entries(impl)) {
      if (!SLOTS.includes(n) || typeof fn !== "function")
        throw Error("Operação desconhecida: " + n);
      adapters[n] = fn;
    }
    convs.clear();
    mount();
  }
  const ctx = (s) => ({ workspaceId: wid(), conversationId: s.id });

  /* ---------- sugestões de cliente ---------- */
  function validSuggestions(r, s) {
    if (!r || r.conversation_id !== s.id || r.workspace_id !== wid() || !Array.isArray(r.items))
      throw Error("Resposta de sugestões inválida ou de outro negócio. Nada foi exibido.");
    const seen = new Set(),
      out = [];
    for (const i of r.items) {
      if (
        !i ||
        typeof i.suggestion_id === "undefined" ||
        !Number.isSafeInteger(i.cliente_id) ||
        i.cliente_id <= 0 ||
        typeof i.nome !== "string" ||
        !i.nome.trim()
      )
        throw Error("Sugestão em formato inesperado. Nada foi exibido.");
      if (seen.has(i.cliente_id)) continue; /* duplicidade: um cartão por cliente */
      seen.add(i.cliente_id);
      out.push({
        suggestion_id: i.suggestion_id,
        cliente_id: i.cliente_id,
        nome: i.nome.trim().slice(0, 120),
        reason: typeof i.reason === "string" ? i.reason.slice(0, 200) : "",
      });
    }
    return out;
  }
  async function loadSuggestions(s) {
    if (!adapters.listCustomerSuggestions || s.cs.busy) return;
    s.cs.busy = true;
    s.cs.phase = "loading";
    s.cs.msg = "";
    paintAll();
    try {
      if (adapters.customerCapabilities) {
        const c = await adapters.customerCapabilities(ctx(s));
        s.cs.enabled = c?.enabled === true;
        if (!s.cs.enabled) {
          s.cs.phase = "disabled";
          return;
        }
      }
      const r = await adapters.listCustomerSuggestions(ctx(s));
      if (!live(s)) return;
      s.cs.items = validSuggestions(r, s);
      s.cs.phase = "ready";
    } catch (e) {
      if (live(s)) {
        s.cs.phase = "error";
        s.cs.msg = msgOf(e);
        s.cs.kind = "err";
        s.cs.items = [];
      }
    } finally {
      s.cs.busy = false;
      paintAll();
    }
  }
  async function decide(s, item, confirmIt) {
    if (s.cs.busy || !writer()) return;
    if (
      confirmIt &&
      !confirm(
        "Associar esta conversa ao cliente “" +
          item.nome +
          "”?\n\nConfira se é a pessoa certa. Isso altera o vínculo no CRM.",
      )
    )
      return;
    s.cs.busy = true;
    s.cs.msg = "Processando…";
    s.cs.kind = "";
    paintAll();
    try {
      if (confirmIt)
        await adapters.confirmCustomerSuggestion({
          ...ctx(s),
          suggestionId: item.suggestion_id,
          clienteId: item.cliente_id,
        });
      else await adapters.rejectCustomerSuggestion({ ...ctx(s), suggestionId: item.suggestion_id });
      if (!live(s)) return;
      s.cs.items = confirmIt
        ? []
        : s.cs.items.filter((x) => x.suggestion_id !== item.suggestion_id);
      s.cs.msg = confirmIt ? "Cliente associado." : "Sugestão rejeitada.";
      s.cs.kind = "ok";
      if (confirmIt) window.SocialMEIInboxCustomer?.refresh();
    } catch (e) {
      if (live(s)) {
        s.cs.msg =
          msgOf(e, { conflict: "O vínculo mudou. Atualize antes de decidir." }) +
          " Nada foi alterado.";
        s.cs.kind = "err";
      }
    } finally {
      s.cs.busy = false;
      paintAll();
    }
  }
  function suggestionsNode(s) {
    const box = el("section", "sm-assist");
    box.dataset.assistSuggestions = "true";
    box.setAttribute("aria-label", "Sugestões de cliente do CRM");
    const head = el("div", "sm-assist-head");
    head.append(el("strong", "", "Sugestões de cliente"));
    const c = s.cs,
      on = !!adapters.listCustomerSuggestions;
    head.append(
      el(
        "span",
        "sm-hub-badge sm-hub-" + (on ? "ok" : "off"),
        on ? (c.enabled === false ? "Desativado" : "Ativo") : "Preparado",
      ),
    );
    box.append(head);
    const p = el("p", "sm-hub-detail");
    p.setAttribute("role", "status");
    if (!on) {
      p.textContent =
        "Aguardando API de sugestões do CRM. Você ainda pode associar o cliente manualmente.";
      box.append(p);
      return box;
    }
    if (c.phase === "disabled")
      p.textContent = "As sugestões de cliente estão desativadas para este negócio.";
    else if (c.phase === "loading") p.textContent = "Buscando possíveis clientes…";
    else if (c.phase === "error") {
      p.textContent = c.msg;
      p.dataset.kind = "err";
    } else if (c.phase === "ready" && !c.items.length)
      p.textContent = c.msg || "Nenhuma sugestão para esta conversa.";
    else if (c.phase === "ready")
      p.textContent =
        (c.items.length > 1
          ? "Mais de uma possível correspondência: confira antes de confirmar. "
          : "") + (c.msg || "Nada é associado sem a sua confirmação.");
    else p.textContent = "Nada é associado sem a sua confirmação.";
    box.append(p);
    for (const i of c.items) {
      const row = el("div", "sm-assist-row");
      row.dataset.suggestion = String(i.suggestion_id);
      const t = el("div");
      t.append(el("b", "", i.nome));
      if (i.reason) t.append(el("span", "sm-hub-detail", " · " + i.reason));
      row.append(
        t,
        btn("Confirmar", () => decide(s, i, true), {
          primary: true,
          disabled: c.busy || !writer(),
        }),
        btn("Rejeitar", () => decide(s, i, false), { disabled: c.busy || !writer() }),
      );
      box.append(row);
    }
    const act = el("div", "sm-hub-actions");
    act.append(
      btn(
        c.phase === "idle" ? "Buscar sugestões" : "Atualizar sugestões",
        () => loadSuggestions(s),
        { disabled: c.busy },
      ),
    );
    box.append(act);
    return box;
  }

  /* ---------- rascunhos de IA ---------- */
  async function generate(s) {
    const d = s.dr,
      row = selected();
    if (!row || !adapters.generateDraft || d.phase === "generating" || !writer()) return;
    d.phase = "generating";
    d.msg = "";
    d.kind = "";
    paintAll();
    const rev = row.revision;
    try {
      if (adapters.draftCapabilities) {
        const c = await adapters.draftCapabilities(ctx(s));
        if (c?.enabled !== true) {
          d.phase = "disabled";
          d.reason = typeof c?.reason === "string" ? c.reason.slice(0, 200) : "";
          return;
        }
      }
      const r = await adapters.generateDraft({ ...ctx(s), expectedRevision: rev });
      if (!live(s)) return;
      if (
        !r ||
        r.conversation_id !== s.id ||
        r.workspace_id !== wid() ||
        typeof r.text !== "string" ||
        !r.text.trim() ||
        r.text.length > MAXTEXT
      )
        throw Error("O servidor devolveu um rascunho inválido. Nada foi exibido.");
      Object.assign(d, {
        phase: "ready",
        text: r.text,
        draftId: r.draft_id ?? null,
        basedOn: r.based_on_revision ?? rev,
        msg: "",
        kind: "",
      });
    } catch (e) {
      if (live(s)) {
        d.phase = e?.code === "unavailable" ? "unavailable" : "error";
        d.msg = msgOf(e, {
          unavailable: "Serviço de IA indisponível no momento. Tente mais tarde.",
          disabled: "A IA está desativada para este negócio.",
        });
        d.kind = "err";
      }
    } finally {
      paintAll();
    }
  }
  const isStale = (s) =>
    s.dr.phase === "ready" &&
    s.dr.basedOn !== null &&
    selected() &&
    selected().revision !== s.dr.basedOn;
  function accept(s) {
    const ta = document.getElementById("ta"),
      d = s.dr;
    if (!ta || isStale(s) || !d.text.trim()) return;
    if (ta.value.trim() && !confirm("O campo de resposta já tem texto. Substituir pelo rascunho?"))
      return;
    ta.value = d.text.slice(0, MAXTEXT);
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    ta.focus();
    d.phase = "accepted";
    d.msg =
      "Rascunho copiado para o campo de resposta. Revise e envie pelo botão normal; nada foi enviado.";
    d.kind = "ok";
    paintAll();
  }
  function draftNode(s) {
    const d = s.dr,
      box = el("section", "sm-assist");
    box.dataset.assistDraft = "true";
    box.setAttribute("aria-label", "Rascunho de resposta por IA");
    const head = el("div", "sm-assist-head");
    head.append(el("strong", "", "Rascunho de resposta (IA)"));
    const on = !!adapters.generateDraft;
    head.append(
      el(
        "span",
        "sm-hub-badge sm-hub-" + (on ? (d.phase === "disabled" ? "off" : "ok") : "off"),
        on ? (d.phase === "disabled" ? "Desativada" : "Disponível") : "Preparado",
      ),
    );
    box.append(head);
    const p = el("p", "sm-hub-detail");
    p.setAttribute("role", "status");
    box.append(p);
    if (!on) {
      p.textContent =
        "Aguardando API de rascunhos. Nenhuma sugestão é gerada ou enviada sem esse serviço.";
      return box;
    }
    const stale = isStale(s);
    if (d.phase === "idle")
      p.textContent =
        "Peça uma sugestão. O texto é só um rascunho: você revisa, edita e decide se envia.";
    else if (d.phase === "generating") p.textContent = "Gerando sugestão…";
    else if (d.phase === "disabled")
      p.textContent = "A IA está desativada para este negócio." + (d.reason ? " " + d.reason : "");
    else if (d.phase === "unavailable" || d.phase === "error") {
      p.textContent = d.msg;
      p.dataset.kind = "err";
    } else if (d.phase === "accepted") {
      p.textContent = d.msg;
      p.dataset.kind = "ok";
    } else if (stale) {
      p.textContent =
        "Resposta desatualizada: a conversa mudou depois que a sugestão foi gerada. Gere de novo.";
      p.dataset.kind = "err";
    } else p.textContent = "Sugestão gerada por IA. Revise antes de usar.";
    if (d.phase === "ready" || d.phase === "accepted") {
      const ta = el("textarea", "sm-assist-text");
      ta.value = d.text;
      ta.rows = 5;
      ta.maxLength = MAXTEXT;
      ta.setAttribute("aria-label", "Rascunho editável da resposta");
      ta.disabled = d.phase === "accepted";
      ta.addEventListener("input", () => {
        d.text = ta.value;
        const b = box.querySelector("[data-draft-accept]");
        if (b) b.disabled = !d.text.trim() || isStale(s);
      });
      box.append(ta);
    }
    const act = el("div", "sm-hub-actions");
    if (d.phase === "ready") {
      const a = btn("Aceitar no campo de resposta", () => accept(s), {
        primary: true,
        disabled: stale || !d.text.trim(),
      });
      a.dataset.draftAccept = "true";
      const x = btn("Descartar", () => {
        s.dr = {
          phase: "idle",
          text: "",
          draftId: null,
          basedOn: null,
          msg: "",
          kind: "",
          reason: "",
        };
        paintAll();
      });
      x.dataset.draftDiscard = "true";
      act.append(
        a,
        x,
        btn("Gerar de novo", () => generate(s)),
      );
    } else if (d.phase !== "generating") {
      const g = btn(
        d.phase === "idle" ? "Gerar sugestão" : "Gerar nova sugestão",
        () => generate(s),
        { primary: true, disabled: !writer() || d.phase === "disabled" },
      );
      g.dataset.draftGenerate = "true";
      act.append(g);
      if (!writer()) act.append(el("span", "sm-hub-detail", "Somente quem atende pode gerar."));
    }
    box.append(act);
    return box;
  }

  /* ---------- montagem (reaproveita o painel de cliente e o composer existentes) ---------- */
  function paintAll() {
    const row = selected();
    if (!row) return;
    const s = S(row.id),
      thread = document.querySelector(".ct");
    if (!thread) return;
    thread
      .querySelectorAll("[data-assist-suggestions],[data-assist-draft]")
      .forEach((n) => n.remove());
    const sug = suggestionsNode(s),
      anchor = thread.querySelector("[data-inbox-customer]");
    if (anchor) anchor.after(sug);
    else thread.querySelector(".ms") ? thread.querySelector(".ms").before(sug) : thread.append(sug);
    const draft = draftNode(s),
      composer = thread.querySelector(".cp");
    if (composer) composer.before(draft);
    else thread.append(draft);
  }
  function mount() {
    const row = selected();
    if (!row) return;
    const s = S(row.id);
    paintAll();
    if (adapters.listCustomerSuggestions && s.cs.phase === "idle")
      loadSuggestions(s); /* só consulta; nunca associa */
  }
  const prior = window.render;
  if (typeof prior === "function")
    window.render = function (...a) {
      const r = prior.apply(this, a);
      mount();
      return r;
    };
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  window.SocialMEIInboxAssist = {
    register,
    slots: Object.freeze([...SLOTS]),
    isStale: () => {
      const r = selected();
      return r ? isStale(S(r.id)) : false;
    },
  };
  mount();
})();
