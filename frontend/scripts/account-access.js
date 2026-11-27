/* Acesso e equipe: painel unificado (Equipe + Convites), verificação de e-mail. · v7.1.1
   v7.1.1 (estabilidade multiempresa): o estado de e-mail e de convites pertence a uma "geração" (usuário + empresa).
   Ao trocar de empresa: estado, avisos, filtros, confirmações abertas e o painel (nome, papel, Equipe) são descartados e
   refeitos; respostas e operações da empresa anterior são ignoradas e nunca bloqueiam a consulta da nova.
   Não há contrato conhecido para convites e verificação; a interface fala com adaptadores do frontend,
   registrados na homologação com SocialMEIAccess.register(). Sem adaptador nada é simulado:
   o aviso de e-mail não aparece (não se sabe o estado) e a aba Convites mostra "Indisponível".
   Contrato esperado dos adaptadores (todos recebem { workspaceId }):
     emailStatus() -> { verified: boolean }          resendVerification() -> void
     confirmEmail({token}) -> void  (erro com code "expired" | "invalid")
     listInvites() -> [{id,email,role,status:"pending|accepted|revoked|expired",created_at}]
     createInvite({email,role}) -> void              revokeInvite({id}) -> void
     acceptInvite({token}) -> void (erro com code "expired" | "invalid" | "revoked")
   O que já existe e continua valendo: Equipe → liberar acesso a contas cadastradas (/team/members),
   desenhada em v22-team-members.js dentro do painel criado aqui (SocialMEIAccess.shell()).
   Regra: nenhum convite aparece como enviado e nenhuma permissão como alterada antes da confirmação do servidor. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIAccess) return;
  const SLOTS = ["emailStatus", "resendVerification", "confirmEmail", "listInvites", "createInvite", "revokeInvite", "acceptInvite"];
  const adapters = {};
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const ctx = () => ({ workspaceId: host.identity?.negocio.id });
  const papel = () => host.identity?.papel;
  const node = (t, c, x) => { const n = document.createElement(t); if (c) n.className = c; if (x !== undefined) n.textContent = x; return n; };
  const btn = (label, onClick, { primary = false, disabled = false, cls = "" } = {}) => { const b = node("button", "btn" + (primary ? "" : " o") + (cls ? " " + cls : ""), label); b.type = "button"; b.disabled = disabled; b.addEventListener("click", onClick); return b; };
  const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$/;
  const ROLES = { member: "Operacional", report_viewer: "Somente relatórios" };
  /* O que cada acesso permite: só o que o próprio app já aplica ou descreve. */
  const ROLE_INFO = {
    owner: ["Proprietário", "Dono do negócio. Gerencia a equipe e as conexões dos canais.", "own"],
    admin: ["Administrador", "Gerencia as conexões dos canais e cria convites. Só o proprietário altera ou revoga acessos.", "adm"],
    member: ["Operacional", "Atua nos módulos disponíveis: CRM, agenda e vendas.", "mem"],
    report_viewer: ["Somente relatórios", "Consulta relatórios. Não edita CRM, agenda nem vendas.", "rep"],
    viewer: ["Leitura", "Acesso de leitura de um perfil já existente.", "rep"],
  };
  const ST = { pending: ["partial", "Pendente"], accepted: ["ok", "Aceito"], revoked: ["off", "Revogado"], expired: ["err", "Expirado"] };
  const FILTERS = [["all", "Todos"], ["pending", "Pendentes"], ["accepted", "Aceitos"], ["expired", "Expirados"], ["revoked", "Revogados"]];
  const blankVerify = (owner = "") => ({ owner, state: "unknown", cooldownUntil: 0, msg: "", kind: "" });
  const blankInv = (owner = "") => ({ owner, phase: "idle", items: [], msg: "", kind: "", loading: false, acting: false, seq: 0, filter: "all", formErr: "" });
  let verify = blankVerify(), inv = blankInv();
  let tab = "members";
  let ctxOwner = scope(), gen = 0; /* gen muda a cada troca de contexto: o que vem de gerações antigas é descartado */
  const confirms = new Set();
  const busy = () => inv.loading || inv.acting;
  const shellKey = () => scope() + ":" + papel();
  function closeConfirms() { for (const d of [...confirms]) { try { d.close(); } catch { d.remove(); } } confirms.clear(); }
  function syncScope() {
    const now = scope(); if (now === ctxOwner) return false;
    ctxOwner = now; gen++; verify = blankVerify(); inv = blankInv(); closeConfirms();
    return true;
  }

  function register(impl) {
    if (!impl || typeof impl !== "object") throw Error("Adaptador inválido.");
    for (const [n, fn] of Object.entries(impl)) { if (!SLOTS.includes(n) || typeof fn !== "function") throw Error("Operação desconhecida: " + n); adapters[n] = fn; }
    gen++; verify.owner = ""; inv = blankInv(); route(); mountAll();
  }
  const failText = (e, map) => map[e?.code] || (e?.message ? e.message : "Não foi possível concluir.");
  const ago = (iso) => {
    const t = Date.parse(iso); if (!Number.isFinite(t)) return "";
    const m = Math.round((Date.now() - t) / 60000); if (m < 1) return "agora"; if (m < 60) return "há " + m + " min";
    const h = Math.round(m / 60); if (h < 24) return "há " + h + " h"; const d = Math.round(h / 24); return "há " + d + (d === 1 ? " dia" : " dias");
  };

  /* Confirmação dentro da página: foco inicial em "Cancelar", Esc cancela, mostra o negócio afetado. */
  function confirmDialog({ title, lines, confirmLabel, danger = false }) {
    return new Promise((resolve) => {
      const dlg = node("dialog", "sm-hub-qr sm-acc-dlg"); dlg.setAttribute("aria-labelledby", "sm-acc-cd-t");
      const h = node("h3", "", title); h.id = "sm-acc-cd-t";
      dlg.append(h, node("p", "sm-hub-who", "Negócio: " + (host.identity?.negocio?.nome || "—") + " (#" + (host.identity?.negocio?.id ?? "—") + ")"));
      for (const t of lines) dlg.append(node("p", "sm-hub-detail", t));
      const row = node("div", "sm-hub-actions"); let ok = false;
      const cancel = btn("Cancelar", () => dlg.close()), go = btn(confirmLabel, () => { ok = true; dlg.close(); }, { primary: true, cls: danger ? "sm-hub-danger" : "" });
      row.append(cancel, go); dlg.append(row);
      dlg.addEventListener("close", () => { confirms.delete(dlg); dlg.remove(); resolve(ok); });
      confirms.add(dlg); document.body.append(dlg); dlg.showModal(); cancel.focus();
    });
  }

  /* ---------- verificação de e-mail ---------- */
  async function checkEmail() {
    syncScope();
    if (!adapters.emailStatus || verify.owner === scope()) return;
    const g = gen, who = scope(); verify = { ...verify, owner: who, state: "unknown" };
    try { const r = await adapters.emailStatus(ctx()); if (g !== gen) return; verify.state = r?.verified === true ? "verified" : r?.verified === false ? "pending" : "unknown"; }
    catch { if (g === gen) verify.state = "unknown"; }
    if (g === gen) paintBanner();
  }
  function paintBanner() {
    const view = document.getElementById("v"); if (!view) return;
    view.querySelector("[data-verify-banner]")?.remove();
    if (verify.state !== "pending") return;
    const wait = Math.max(0, Math.ceil((verify.cooldownUntil - Date.now()) / 1000));
    const box = node("div", "sm-verify"); box.dataset.verifyBanner = "true"; box.setAttribute("role", "status");
    box.append(node("strong", "", "Confirme seu e-mail"), node("span", "", verify.msg || "Enviamos um link de confirmação. Verifique a caixa de entrada e o spam."));
    box.dataset.kind = verify.kind;
    const b = btn(wait ? "Reenviar em " + wait + "s" : "Reenviar confirmação", resend, { primary: true, disabled: !adapters.resendVerification || wait > 0 }); b.dataset.verifyResend = "true";
    box.append(b); view.prepend(box);
    if (wait) setTimeout(paintBanner, 1000);
  }
  async function resend() {
    const g = gen; verify.cooldownUntil = Date.now() + 60000; verify.msg = "Enviando…"; verify.kind = ""; paintBanner();
    try { await adapters.resendVerification(ctx()); if (g === gen) { verify.msg = "Se o e-mail estiver correto, o link chega em instantes."; verify.kind = "ok"; } }
    catch (e) { if (g === gen) { verify.cooldownUntil = 0; verify.msg = failText(e, { rate_limited: "Muitos pedidos. Aguarde alguns minutos." }); verify.kind = "err"; } }
    if (g === gen) paintBanner();
  }

  /* ---------- rotas #/verificar-email/<token> e #/convite/<token> ---------- */
  const TOKEN = /^[A-Za-z0-9_-]{20,128}$/;
  function dialog(title, text, kind) {
    document.querySelector("dialog[data-access-dialog]")?.remove();
    const d = node("dialog", "sm-hub-qr"); d.dataset.accessDialog = "true"; d.dataset.kind = kind; d.setAttribute("aria-label", title);
    d.append(node("h3", "", title), node("p", "", text)); const c = btn("Fechar", () => d.close(), { primary: true }); d.append(c);
    d.addEventListener("close", () => d.remove()); document.body.append(d); d.showModal(); c.focus();
  }
  let handled = "";
  async function route() {
    const m = /^#\/(verificar-email|convite)\/([^/?#]*)$/.exec(location.hash); if (!m || handled === location.hash) return;
    handled = location.hash;
    history.replaceState(history.state, "", location.pathname + location.search + "#/inicio"); /* o token sai da barra e do histórico */
    const [, kind, token] = m, op = kind === "convite" ? "acceptInvite" : "confirmEmail";
    const title = kind === "convite" ? "Convite" : "Confirmação de e-mail";
    if (!TOKEN.test(token)) return dialog(title, "Este link é inválido. Peça um novo.", "err");
    if (!adapters[op]) return dialog(title, "Este recurso ainda não está disponível neste ambiente. Seu link não foi consumido.", "err");
    const g = gen, nome = host.identity?.negocio?.nome;
    try {
      await adapters[op]({ ...ctx(), token });
      if (kind === "convite") { if (g === gen) inv.owner = ""; dialog(title, nome ? "Convite aceito para " + nome + ". Você já pode usar este negócio." : "Convite aceito. Você já pode usar este negócio.", "ok"); }
      else { if (g === gen) { verify.state = "verified"; paintBanner(); } dialog(title, "E-mail confirmado. Obrigado!", "ok"); }
    } catch (e) {
      dialog(title, failText(e, { expired: "Este link expirou. Peça um novo.", invalid: "Este link é inválido ou já foi usado.", revoked: "Este convite foi revogado." }), "err");
    }
  }

  /* ---------- painel unificado ---------- */
  const isManager = () => ["owner", "admin"].includes(papel());
  function roleLegend() {
    const d = node("details", "sm-acc-legend");
    d.append(node("summary", "", "Quem pode o quê"));
    const g = node("div", "sm-acc-legend-grid");
    for (const [k, [label, desc, tone]] of Object.entries(ROLE_INFO)) { const c = node("div", "sm-acc-lg sm-acc-r-" + tone); c.dataset.role = k; c.append(node("b", "", label), node("span", "sm-hub-detail", desc)); g.append(c); }
    d.append(g); return d;
  }
  function setTab(next, shell) {
    tab = next;
    for (const t of shell.querySelectorAll("[data-acc-tab]")) { const on = t.dataset.accTab === tab; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; }
    for (const p of shell.querySelectorAll("[data-acc-panel]")) p.hidden = p.dataset.accPanel !== tab;
  }
  function shell() {
    syncScope();
    const view = document.getElementById("v");
    if (!view) return null;
    let root = view.querySelector("[data-acc]");
    if (!location.hash.startsWith("#/config/conta") || !isManager()) { root?.remove(); return null; } /* sem papel de gestão não sobra painel de outra empresa */
    if (root && root.dataset.key !== shellKey()) { root.remove(); root = null; } /* empresa ou papel mudou: o painel é refeito */
    if (!root) {
      root = node("section", "sm-hub sm-acc"); root.dataset.acc = "true"; root.dataset.key = shellKey(); root.setAttribute("aria-label", "Acesso e equipe");
      const company = host.identity?.negocio, info = ROLE_INFO[papel()];
      const top = node("div", "sm-acc-top");
      const t = node("div"); t.append(node("h2", "", "Acesso e equipe"), node("p", "sm-hub-detail", "Quem pode entrar neste negócio e o que cada pessoa pode fazer. Cada alteração só vale depois que o servidor confirma."));
      const chip = node("div", "sm-acc-chip"); chip.append(node("span", "sm-hub-av", (company?.nome || "?").trim().charAt(0).toUpperCase()));
      const ct = node("div"); ct.append(node("span", "sm-hub-nl", "Negócio"), node("b", "", (company?.nome || "—") + " · #" + (company?.id ?? "—")), node("span", "sm-hub-detail", "Seu acesso: " + (info ? info[0] : papel() || "—")));
      chip.append(ct); top.append(t, chip);
      const tabs = node("div", "sm-acc-tabs"); tabs.setAttribute("role", "tablist"); tabs.setAttribute("aria-label", "Seções de acesso e equipe");
      const mk = (key, label) => { const b = node("button", "sm-acc-tab"); b.type = "button"; b.setAttribute("role", "tab"); b.dataset.accTab = key; b.id = "sm-acc-tab-" + key; b.setAttribute("aria-controls", "sm-acc-panel-" + key); b.append(node("span", "", label), node("span", "sm-acc-count")); b.addEventListener("click", () => setTab(key, root)); return b; };
      tabs.append(mk("members", "Equipe"), mk("invites", "Convites"));
      tabs.addEventListener("keydown", (e) => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return; e.preventDefault(); const keys = ["members", "invites"], i = keys.indexOf(tab); const n = e.key === "Home" ? 0 : e.key === "End" ? 1 : (i + (e.key === "ArrowRight" ? 1 : 1) + 2) % 2; setTab(keys[n], root); root.querySelector('[data-acc-tab="' + keys[n] + '"]').focus(); });
      const pm = node("div", "sm-acc-panel"); pm.dataset.accPanel = "members"; pm.id = "sm-acc-panel-members"; pm.setAttribute("role", "tabpanel"); pm.setAttribute("aria-labelledby", "sm-acc-tab-members");
      const pi = node("div", "sm-acc-panel"); pi.dataset.accPanel = "invites"; pi.id = "sm-acc-panel-invites"; pi.setAttribute("role", "tabpanel"); pi.setAttribute("aria-labelledby", "sm-acc-tab-invites");
      const ib = node("section", "sm-inv"); ib.dataset.invites = "true"; const body = node("div"); body.dataset.invBody = "true"; ib.append(body); pi.append(ib);
      root.append(top, roleLegend(), tabs, pm, pi);
      view.append(root); setTab(tab, root);
    }
    return { root, members: root.querySelector('[data-acc-panel="members"]'), invites: root.querySelector("[data-inv-body]") };
  }
  function setCount(key, text) { const c = document.querySelector('[data-acc-tab="' + key + '"] .sm-acc-count'); if (c) { c.textContent = text || ""; c.hidden = !text; } }

  /* ---------- convites ---------- */
  const canCreate = () => isManager(), canRevoke = () => papel() === "owner";
  async function loadInvites(force) {
    syncScope();
    if (!adapters.listInvites) return;
    if (!force && inv.owner === scope()) return;
    if (inv.loading && !force) return;
    const g = gen, tok = ++inv.seq, mine = inv; /* a consulta mais recente da geração atual é a única que vale */
    const live = () => g === gen && inv === mine && tok === inv.seq;
    inv.owner = scope(); inv.phase = "loading"; inv.loading = true; paintInvites();
    try {
      const items = await adapters.listInvites(ctx());
      if (!live()) return;
      if (!Array.isArray(items) || !items.every((i) => i && typeof i.id !== "undefined" && typeof i.email === "string" && ST[i.status] && ROLES[i.role])) throw Error("O servidor devolveu a lista de convites em formato inesperado.");
      inv.items = items; inv.phase = "ready"; if (!force) { inv.msg = ""; inv.kind = ""; }
    } catch (e) { if (live()) { inv.phase = "error"; inv.msg = failText(e, {}); inv.kind = "err"; } }
    finally { if (live()) { inv.loading = false; paintInvites(); } }
  }
  async function act(fn, okMsg) {
    syncScope();
    if (inv.acting) return;
    const g = gen, mine = inv; inv.acting = true; inv.msg = "Aguardando confirmação do servidor…"; inv.kind = ""; paintInvites();
    const live = () => g === gen && inv === mine;
    try { await fn(); if (!live()) return; inv.msg = okMsg; inv.kind = "ok"; inv.acting = false; await loadInvites(true); }
    catch (e) { if (live()) { inv.msg = failText(e, { duplicate: "Já existe um convite pendente para este e-mail." }) + " Nada foi alterado."; inv.kind = "err"; } }
    finally { if (live()) { inv.acting = false; paintInvites(); } }
  }
  function paintInvites() {
    syncScope();
    const body = document.querySelector("[data-inv-body]"); if (!body) return;
    body.replaceChildren();
    const have = !!adapters.listInvites, live = !!adapters.createInvite && canCreate();
    const pend = inv.items.filter((i) => i.status === "pending").length;
    setCount("invites", have && inv.phase === "ready" && pend ? String(pend) : "");
    if (!have) {
      const off = node("div", "sm-acc-off"); off.setAttribute("role", "status");
      off.append(node("b", "", "Convites por e-mail: indisponível por enquanto"), node("span", "sm-hub-detail", "O servidor ainda não oferece esta função, então nada é enviado daqui. Pessoas que já têm conta SocialMEI podem ser adicionadas na aba Equipe."));
      const go = btn("Ir para Equipe", () => { const r = document.querySelector("[data-acc]"); if (r) { setTab("members", r); r.querySelector('[data-acc-tab="members"]').focus(); } });
      off.append(go); body.append(off);
    }
    const form = node("form", "sm-inv-form"); form.noValidate = true;
    const lab = node("label", "sm-acc-field"); lab.append(node("span", "", "E-mail da pessoa"));
    const email = node("input"); email.type = "email"; email.id = "sm-inv-email"; email.placeholder = "nome@empresa.com"; email.autocomplete = "off"; email.maxLength = 254; email.disabled = !live || busy(); email.setAttribute("aria-describedby", "sm-inv-err");
    lab.append(email);
    const rl = node("label", "sm-acc-field"); rl.append(node("span", "", "Acesso"));
    const role = node("select"); role.disabled = !live || busy();
    for (const [v, l] of Object.entries(ROLES)) { const o = node("option", "", l); o.value = v; role.append(o); }
    rl.append(role);
    const hint = node("p", "sm-hub-detail sm-acc-hint", ROLE_INFO.member[1]); role.addEventListener("change", () => { hint.textContent = ROLE_INFO[role.value][1]; });
    const go = node("button", "btn", "Enviar convite"); go.type = "submit"; go.disabled = !live || busy(); go.dataset.invSend = "true";
    const err = node("p", "sm-hub-status", inv.formErr); err.id = "sm-inv-err"; err.setAttribute("role", "alert"); if (inv.formErr) err.dataset.kind = "err";
    form.append(lab, rl, go); form.addEventListener("submit", (e) => {
      e.preventDefault(); const v = email.value.trim().toLowerCase();
      const bad = !EMAIL.test(v) ? "Informe um e-mail válido, como nome@empresa.com." : inv.items.some((i) => i.status === "pending" && i.email.toLowerCase() === v) ? "Já existe um convite pendente para este e-mail." : "";
      inv.formErr = bad; err.textContent = bad; err.dataset.kind = bad ? "err" : ""; email.setAttribute("aria-invalid", String(!!bad));
      if (bad) return email.focus();
      act(() => adapters.createInvite({ ...ctx(), email: v, role: role.value }), "Convite criado pelo servidor.");
    });
    body.append(form, hint, err);
    const st = node("p", "sm-hub-status", inv.phase === "loading" ? "Consultando convites de " + (host.identity?.negocio?.nome || "este negócio") + "…" : inv.msg); st.dataset.kind = inv.kind; st.setAttribute("role", "status"); body.append(st);
    if (have && inv.phase === "error") body.append(btn("Tentar de novo", () => loadInvites(true)));
    if (have && inv.phase === "ready") {
      const chips = node("div", "sm-acc-filters"); chips.setAttribute("role", "group"); chips.setAttribute("aria-label", "Filtrar convites por situação");
      for (const [k, l] of FILTERS) { const n = k === "all" ? inv.items.length : inv.items.filter((i) => i.status === k).length; const c = node("button", "sm-acc-chipf", l + " · " + n); c.type = "button"; c.setAttribute("aria-pressed", String(inv.filter === k)); c.addEventListener("click", () => { inv.filter = k; paintInvites(); }); chips.append(c); }
      body.append(chips);
      const shown = inv.items.filter((i) => inv.filter === "all" || i.status === inv.filter);
      if (!inv.items.length) body.append(node("p", "sm-hub-detail", "Nenhum convite por aqui ainda. Convide alguém pelo e-mail acima."));
      else if (!shown.length) body.append(node("p", "sm-hub-detail", "Nenhum convite nesta situação."));
      const ul = node("ul", "sm-inv-list");
      for (const i of shown) {
        const li = node("li"), [k, t] = ST[i.status]; li.dataset.invId = String(i.id);
        const who = node("div", "sm-inv-who"); who.append(node("span", "sm-inv-mail", i.email), node("span", "sm-hub-detail", ROLES[i.role] + (i.created_at ? " · enviado " + ago(i.created_at) : "")));
        li.append(who, node("span", "sm-hub-badge sm-hub-" + k, t));
        if (i.status === "pending") li.append(btn("Revogar", async () => { if (await confirmDialog({ title: "Revogar este convite?", lines: ["O convite de " + i.email + " deixa de valer. A pessoa não poderá mais entrar por ele."], confirmLabel: "Revogar convite", danger: true })) act(() => adapters.revokeInvite({ ...ctx(), id: i.id }), "Convite revogado pelo servidor."); }, { disabled: !adapters.revokeInvite || !canRevoke() || busy() }));
        ul.append(li);
      }
      body.append(ul);
    }
  }
  function mountInvites() { const s = shell(); if (!s) return; paintInvites(); loadInvites(false); }
  function mountAll() { checkEmail().then(paintBanner); paintBanner(); mountInvites(); }
  try { const prior = render; render = () => { prior(); mountAll(); }; } catch { /* hashchange cobre */ }
  /* Troca de empresa/papel sem recarregar a página: refaz só o que pertencia ao contexto anterior. */
  const shellStale = () => { const r = document.querySelector("[data-acc]"); return !!r && r.dataset.key !== shellKey(); };
  const tick = () => { const changed = syncScope(); if (changed || shellStale()) { mountAll(); window.SocialMEITeam?.refresh?.(); } };
  setInterval(tick, 500);
  document.addEventListener("socialmei-data-change", () => queueMicrotask(tick));
  window.addEventListener("hashchange", () => queueMicrotask(() => { route(); mountAll(); }));
  window.SocialMEIAccess = { register, slots: Object.freeze([...SLOTS]), validEmail: (v) => EMAIL.test(v), shell, setCount, confirmDialog, roleInfo: ROLE_INFO };
  queueMicrotask(() => { route(); mountAll(); });
})();
