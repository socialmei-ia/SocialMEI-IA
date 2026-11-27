/* Equipe do negócio · v7.1. Somente contas já cadastradas; o acesso vale só para o negócio ativo.
   Contratos inalterados: GET/POST /team/members, PATCH/DELETE /team/members/:id (com expected_role).
   Nada aparece como alterado antes da resposta do servidor: durante a chamada a linha fica
   "aguardando confirmação"; só depois do sucesso a lista é recarregada do servidor. */
(() => {
  const auth = window.SocialMEIAuth;
  if (!auth?.remote || window.SocialMEITeam) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "styles/v22-team-members.css";
  document.head.append(link);
  const roles = { owner: "Proprietário", admin: "Administrador", member: "Operacional", viewer: "Leitura", report_viewer: "Somente relatórios" };
  const tone = { owner: "own", admin: "adm", member: "mem", viewer: "rep", report_viewer: "rep" };
  const blurb = {
    member: "Atua nos módulos disponíveis: CRM, agenda e vendas.",
    report_viewer: "Consulta relatórios. Não edita CRM, agenda nem vendas.",
  };
  const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$/;
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const scope = () => auth.current && `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  const initials = (name) => String(name || "?").trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase() || "?";
  const confirmDlg = (o) => window.SocialMEIAccess?.confirmDialog ? window.SocialMEIAccess.confirmDialog(o) : Promise.resolve(confirm([o.title, ...o.lines].join("\n")));
  let tries = 0;

  function mount() {
    if (!auth.current || !["owner", "admin"].includes(auth.current.papel) || !location.hash.startsWith("#/config/conta")) return;
    const view = document.getElementById("v");
    if (!view || view.querySelector("[data-team-members]")) return;
    /* o painel unificado vem de account-access.js; espera um pouco por ele antes de montar sozinho */
    const shell = window.SocialMEIAccess?.shell?.();
    if (!shell && window.SocialMEIAccess === undefined && tries++ < 20) return void setTimeout(mount, 100);
    const expected = scope();
    const panel = el("section", undefined, "sm-team sm-team-v71");
    panel.dataset.teamMembers = "true";
    (shell ? shell.members : view).append(panel);
    const manage = auth.current.papel === "owner";
    const alive = () => panel.isConnected && scope() === expected;
    let members = null, phase = "loading", filter = "";
    const note = el("p", "", "sm-hub-status");
    note.setAttribute("role", "status");
    note.setAttribute("aria-live", "polite");
    const say = (text, kind = "") => { note.textContent = text; note.dataset.kind = kind; };

    panel.append(el("p", "Autorize somente contas SocialMEI que já existem. Este acesso vale apenas para este negócio. Nenhum e-mail é enviado por esta tela.", "sm-hub-detail"));

    /* ---------- adicionar conta existente ---------- */
    if (manage) {
      const form = el("form", undefined, "sm-acc-add");
      form.noValidate = true;
      const f1 = el("label", undefined, "sm-acc-field");
      f1.append(el("span", "E-mail da conta existente"));
      const email = el("input");
      email.type = "email"; email.maxLength = 255; email.autocomplete = "off"; email.placeholder = "nome@empresa.com";
      email.setAttribute("aria-describedby", "sm-team-err");
      f1.append(email);
      const f2 = el("label", undefined, "sm-acc-field");
      f2.append(el("span", "Acesso no negócio"));
      const role = el("select");
      for (const r of ["member", "report_viewer"]) { const o = el("option", roles[r]); o.value = r; role.append(o); }
      f2.append(role);
      const grant = el("button", "Adicionar à equipe", "btn");
      grant.type = "submit";
      const hint = el("p", blurb.member, "sm-hub-detail sm-acc-hint");
      role.addEventListener("change", () => { hint.textContent = blurb[role.value]; });
      const err = el("p", "", "sm-hub-status");
      err.id = "sm-team-err"; err.setAttribute("role", "alert");
      form.append(f1, f2, grant);
      form.onsubmit = async (event) => {
        event.preventDefault();
        if (!alive() || grant.disabled) return;
        const value = email.value.trim();
        if (!EMAIL.test(value)) { err.textContent = "Informe um e-mail válido, como nome@empresa.com."; err.dataset.kind = "err"; email.setAttribute("aria-invalid", "true"); return email.focus(); }
        err.textContent = ""; err.dataset.kind = ""; email.removeAttribute("aria-invalid");
        grant.disabled = true; say("Aguardando confirmação do servidor…");
        try {
          const data = await auth.request("/team/members", "POST", { email: value, role: role.value });
          if (alive()) {
            form.reset(); hint.textContent = blurb.member;
            await refresh();
            say(data.already_member ? "A conta já possui esse acesso." : "Conta adicionada à equipe deste negócio.", "ok");
          }
        } catch (error) {
          if (alive()) say(error.message + " Nada foi alterado.", "err");
        } finally {
          if (alive()) grant.disabled = false;
        }
      };
      panel.append(form, hint, err);
    } else panel.append(el("p", "Somente o proprietário pode adicionar, alterar ou revogar integrantes. Você pode consultar a equipe abaixo.", "sm-acc-off"));

    /* ---------- lista ---------- */
    const bar = el("div", undefined, "sm-acc-bar");
    const count = el("b", "Equipe");
    const search = el("input");
    search.type = "search"; search.placeholder = "Buscar por nome ou e-mail"; search.setAttribute("aria-label", "Buscar integrante"); search.hidden = true;
    search.addEventListener("input", () => { filter = search.value.trim().toLowerCase(); paint(); });
    const update = el("button", "Atualizar equipe", "btn o");
    update.type = "button";
    update.onclick = () => { say("Consultando equipe…"); refresh().then(() => alive() && say("Equipe atualizada.", "ok")).catch(fail); };
    bar.append(count, search, update);
    const list = el("ul", undefined, "sm-acc-list");
    panel.append(bar, note, list);
    const fail = (error) => { if (alive()) { phase = "error"; paint(); say(error.message, "err"); } };

    function memberRow(m) {
      const li = el("li", undefined, "sm-acc-member");
      li.dataset.memberId = String(m.id);
      const you = m.id === auth.current.usuario.id;
      const av = el("span", initials(m.nome), "sm-acc-av sm-acc-r-" + (tone[m.role] || "rep"));
      av.setAttribute("aria-hidden", "true");
      const who = el("div", undefined, "sm-acc-who");
      const line = el("div", undefined, "sm-acc-name");
      line.append(el("strong", m.nome));
      if (you) line.append(el("span", "Você", "sm-hub-badge sm-hub-ok"));
      if (!m.ativo) line.append(el("span", "Conta inativa", "sm-hub-badge sm-hub-off"));
      const badge = el("span", roles[m.role] || m.role, "sm-acc-role sm-acc-r-" + (tone[m.role] || "rep"));
      badge.title = window.SocialMEIAccess?.roleInfo?.[m.role]?.[1] || "";
      who.append(line, el("span", m.email, "sm-hub-detail"), badge);
      li.append(av, who);
      if (manage && !you && !["owner", "admin"].includes(m.role)) {
        const controls = el("div", undefined, "sm-acc-actions");
        const select = el("select");
        const opts = m.role === "viewer" ? ["viewer", "member", "report_viewer"] : ["member", "report_viewer"];
        for (const r of opts) { const o = el("option", roles[r]); o.value = r; select.append(o); }
        select.value = m.role;
        select.setAttribute("aria-label", "Acesso de " + m.nome);
        const save = el("button", "Alterar acesso", "btn o");
        save.type = "button";
        const revoke = el("button", "Revogar acesso", "btn o sm-acc-revoke");
        revoke.type = "button";
        const busyRow = (on, text) => { li.setAttribute("aria-busy", String(on)); for (const c of [select, save, revoke]) c.disabled = on; if (text) say(text); };
        save.onclick = async () => {
          if (!alive() || select.value === m.role) { if (select.value === m.role) say("Escolha um acesso diferente do atual para alterar."); return; }
          const ok = await confirmDlg({
            title: "Alterar o acesso de " + m.nome + "?",
            lines: ["De " + roles[m.role] + " para " + roles[select.value] + ", somente neste negócio.", "As sessões desta pessoa neste negócio serão encerradas e ela precisará entrar de novo."],
            confirmLabel: "Alterar acesso",
          });
          if (!ok || !alive()) return;
          busyRow(true, "Aguardando confirmação do servidor…");
          try {
            await auth.request("/team/members/" + m.id, "PATCH", { role: select.value, expected_role: m.role });
            if (alive()) { await refresh(); say("Acesso alterado. A pessoa deverá entrar novamente neste negócio.", "ok"); }
          } catch (error) {
            if (alive()) { say(error.message + " Nada foi alterado.", "err"); busyRow(false); }
          }
        };
        revoke.onclick = async () => {
          if (!alive()) return;
          const ok = await confirmDlg({
            title: "Revogar o acesso de " + m.nome + "?",
            lines: ["A pessoa perde o acesso somente a este negócio.", "A conta dela e os outros negócios dela são preservados."],
            confirmLabel: "Revogar acesso", danger: true,
          });
          if (!ok || !alive()) return;
          busyRow(true, "Aguardando confirmação do servidor…");
          try {
            await auth.request("/team/members/" + m.id, "DELETE", { expected_role: m.role });
            if (alive()) { await refresh(); say("Acesso revogado neste negócio.", "ok"); }
          } catch (error) {
            if (alive()) { say(error.message + " Nada foi alterado.", "err"); busyRow(false); }
          }
        };
        controls.append(select, save, revoke);
        li.append(controls);
      }
      return li;
    }
    const order = { owner: 0, admin: 1 };
    function paint() {
      list.replaceChildren();
      list.setAttribute("aria-busy", String(phase === "loading"));
      if (phase === "loading" && !members) {
        for (let i = 0; i < 3; i++) { const s = el("li", undefined, "sm-acc-member sm-acc-skel"); s.append(el("i"), el("i")); list.append(s); }
        return;
      }
      if (phase === "error" && !members) {
        const li = el("li", undefined, "sm-acc-off");
        li.append(el("b", "Não foi possível carregar a equipe"), el("span", "Nada foi alterado. Tente de novo em instantes.", "sm-hub-detail"));
        const retry = el("button", "Tentar de novo", "btn");
        retry.type = "button"; retry.onclick = () => { phase = "loading"; paint(); refresh().catch(fail); };
        li.append(retry); list.append(li); return;
      }
      const all = (members || []).slice().sort((a, b) => (order[a.role] ?? 2) - (order[b.role] ?? 2) || String(a.nome).localeCompare(String(b.nome), "pt-BR"));
      const shown = all.filter((m) => !filter || (m.nome + " " + m.email).toLowerCase().includes(filter));
      count.textContent = all.length + (all.length === 1 ? " pessoa" : " pessoas") + " com acesso";
      search.hidden = all.length <= 5;
      if (!shown.length) {
        const li = el("li", undefined, "sm-acc-off");
        li.append(el("b", filter ? "Ninguém encontrado" : "Só você por enquanto"), el("span", filter ? "Tente outro nome ou e-mail." : manage ? "Adicione uma conta já cadastrada acima para dividir o trabalho." : "Ainda não há outras pessoas neste negócio.", "sm-hub-detail"));
        list.append(li); return;
      }
      for (const m of shown) list.append(memberRow(m));
      if (!filter && all.length === 1 && all[0].id === auth.current.usuario.id) {
        const li = el("li", undefined, "sm-acc-off");
        li.append(el("b", "Só você por enquanto"), el("span", manage ? "Adicione uma conta já cadastrada acima para dividir o trabalho." : "Ainda não há outras pessoas neste negócio.", "sm-hub-detail"));
        list.append(li);
      }
    }
    async function refresh() {
      const data = await auth.request("/team/members");
      if (!alive()) return;
      members = data.items; phase = "ready";
      paint();
      window.SocialMEIAccess?.setCount?.("members", String(data.items.length));
      if (data.truncated) say("Exibindo os primeiros 50 integrantes. Nenhum acesso foi modificado.");
      else if (!note.textContent || note.dataset.kind === "") say("Proprietários e administradores não são alterados por esta tela. A conta de cada pessoa é preservada.");
    }
    paint();
    refresh().catch(fail);
  }
  const previous = window.render;
  if (typeof previous === "function")
    window.render = function (...args) {
      const result = previous.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.SocialMEITeam = { refresh: mount };
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  queueMicrotask(mount);
})();
