/* Acesso e equipe: verificação de e-mail e convites.
   Não há contrato conhecido para estas operações; a interface fala com adaptadores do frontend,
   registrados na homologação com SocialMEIAccess.register(). Sem adaptador nada é simulado:
   o aviso de e-mail não aparece (não se sabe o estado) e o painel de convites mostra "Aguardando API".
   Contrato esperado dos adaptadores (todos recebem { workspaceId }):
     emailStatus() -> { verified: boolean }          resendVerification() -> void
     confirmEmail({token}) -> void  (erro com code "expired" | "invalid")
     listInvites() -> [{id,email,role,status:"pending|accepted|revoked|expired",created_at}]
     createInvite({email,role}) -> void              revokeInvite({id}) -> void
     acceptInvite({token}) -> void (erro com code "expired" | "invalid" | "revoked")
   O que já existe e continua valendo: Equipe → liberar acesso a contas cadastradas (/team/members). */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIAccess) return;
  const SLOTS = [
    "emailStatus",
    "resendVerification",
    "confirmEmail",
    "listInvites",
    "createInvite",
    "revokeInvite",
    "acceptInvite",
  ];
  const adapters = {};
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const ctx = () => ({ workspaceId: host.identity?.negocio.id });
  const papel = () => host.identity?.papel;
  const node = (t, c, x) => {
    const n = document.createElement(t);
    if (c) n.className = c;
    if (x !== undefined) n.textContent = x;
    return n;
  };
  const btn = (label, onClick, { primary = false, disabled = false } = {}) => {
    const b = node("button", "btn" + (primary ? "" : " o"), label);
    b.type = "button";
    b.disabled = disabled;
    b.addEventListener("click", onClick);
    return b;
  };
  const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$/;
  const ROLES = { member: "Membro", report_viewer: "Somente relatórios" };
  const ST = {
    pending: ["partial", "Pendente"],
    accepted: ["ok", "Aceito"],
    revoked: ["off", "Revogado"],
    expired: ["err", "Expirado"],
  };
  let verify = { owner: "", state: "unknown", cooldownUntil: 0, msg: "", kind: "" };
  let inv = { owner: "", phase: "idle", items: [], msg: "", kind: "", busy: false };

  function register(impl) {
    if (!impl || typeof impl !== "object") throw Error("Adaptador inválido.");
    for (const [n, fn] of Object.entries(impl)) {
      if (!SLOTS.includes(n) || typeof fn !== "function")
        throw Error("Operação desconhecida: " + n);
      adapters[n] = fn;
    }
    verify.owner = "";
    inv.owner = "";
    route();
    mountAll();
  }
  const failText = (e, map) =>
    map[e?.code] || (e?.message ? e.message : "Não foi possível concluir.");

  /* ---------- verificação de e-mail ---------- */
  async function checkEmail() {
    if (!adapters.emailStatus || verify.owner === scope()) return;
    const who = scope();
    verify = { ...verify, owner: who, state: "unknown" };
    try {
      const r = await adapters.emailStatus(ctx());
      if (who !== scope()) return;
      verify.state =
        r?.verified === true ? "verified" : r?.verified === false ? "pending" : "unknown";
    } catch {
      if (who === scope()) verify.state = "unknown";
    }
    paintBanner();
  }
  function paintBanner() {
    const view = document.getElementById("v");
    if (!view) return;
    view.querySelector("[data-verify-banner]")?.remove();
    if (verify.state !== "pending") return;
    const wait = Math.max(0, Math.ceil((verify.cooldownUntil - Date.now()) / 1000));
    const box = node("div", "sm-verify");
    box.dataset.verifyBanner = "true";
    box.setAttribute("role", "status");
    box.append(
      node("strong", "", "Confirme seu e-mail"),
      node(
        "span",
        "",
        verify.msg || "Enviamos um link de confirmação. Verifique a caixa de entrada e o spam.",
      ),
    );
    box.dataset.kind = verify.kind;
    const b = btn(wait ? "Reenviar em " + wait + "s" : "Reenviar confirmação", resend, {
      primary: true,
      disabled: !adapters.resendVerification || wait > 0,
    });
    b.dataset.verifyResend = "true";
    box.append(b);
    view.prepend(box);
    if (wait) setTimeout(paintBanner, 1000);
  }
  async function resend() {
    const who = scope();
    verify.cooldownUntil = Date.now() + 60000;
    verify.msg = "Enviando…";
    verify.kind = "";
    paintBanner();
    try {
      await adapters.resendVerification(ctx());
      if (who === scope()) {
        verify.msg = "Se o e-mail estiver correto, o link chega em instantes.";
        verify.kind = "ok";
      }
    } catch (e) {
      if (who === scope()) {
        verify.cooldownUntil = 0;
        verify.msg = failText(e, { rate_limited: "Muitos pedidos. Aguarde alguns minutos." });
        verify.kind = "err";
      }
    }
    paintBanner();
  }

  /* ---------- rotas #/verificar-email/<token> e #/convite/<token> ---------- */
  const TOKEN = /^[A-Za-z0-9_-]{20,128}$/;
  function dialog(title, text, kind) {
    document.querySelector("dialog[data-access-dialog]")?.remove();
    const d = node("dialog", "sm-hub-qr");
    d.dataset.accessDialog = "true";
    d.dataset.kind = kind;
    d.setAttribute("aria-label", title);
    d.append(node("h3", "", title), node("p", "", text));
    const c = btn("Fechar", () => d.close(), { primary: true });
    d.append(c);
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    c.focus();
  }
  let handled = "";
  async function route() {
    const m = /^#\/(verificar-email|convite)\/([^/?#]*)$/.exec(location.hash);
    if (!m || handled === location.hash) return;
    handled = location.hash;
    history.replaceState(
      history.state,
      "",
      location.pathname + location.search + "#/inicio",
    ); /* o token sai da barra e do histórico */
    const [, kind, token] = m,
      op = kind === "convite" ? "acceptInvite" : "confirmEmail";
    const title = kind === "convite" ? "Convite" : "Confirmação de e-mail";
    if (!TOKEN.test(token)) return dialog(title, "Este link é inválido. Peça um novo.", "err");
    if (!adapters[op])
      return dialog(
        title,
        "Este recurso ainda não está disponível neste ambiente. Seu link não foi consumido.",
        "err",
      );
    try {
      await adapters[op]({ ...ctx(), token });
      if (kind === "convite") {
        inv.owner = "";
        dialog(title, "Convite aceito. Você já pode usar este negócio.", "ok");
      } else {
        verify.state = "verified";
        paintBanner();
        dialog(title, "E-mail confirmado. Obrigado!", "ok");
      }
    } catch (e) {
      dialog(
        title,
        failText(e, {
          expired: "Este link expirou. Peça um novo.",
          invalid: "Este link é inválido ou já foi usado.",
          revoked: "Este convite foi revogado.",
        }),
        "err",
      );
    }
  }

  /* ---------- convites ---------- */
  const canCreate = () => ["owner", "admin"].includes(papel()),
    canRevoke = () => papel() === "owner";
  async function loadInvites(force) {
    if (!adapters.listInvites || inv.busy) return;
    if (!force && inv.owner === scope()) return;
    const who = scope();
    inv = { ...inv, owner: who, phase: "loading", busy: true };
    paintInvites();
    try {
      const items = await adapters.listInvites(ctx());
      if (who !== scope()) return;
      if (
        !Array.isArray(items) ||
        !items.every(
          (i) =>
            i &&
            typeof i.id !== "undefined" &&
            typeof i.email === "string" &&
            ST[i.status] &&
            ROLES[i.role],
        )
      )
        throw Error("O servidor devolveu a lista de convites em formato inesperado.");
      inv.items = items;
      inv.phase = "ready";
      if (!force) {
        inv.msg = "";
        inv.kind = "";
      }
    } catch (e) {
      if (who === scope()) {
        inv.phase = "error";
        inv.msg = failText(e, {});
        inv.kind = "err";
      }
    } finally {
      inv.busy = false;
      paintInvites();
    }
  }
  async function act(fn, okMsg) {
    const who = scope();
    inv.busy = true;
    inv.msg = "Processando…";
    inv.kind = "";
    paintInvites();
    try {
      await fn();
      if (who !== scope()) return;
      inv.msg = okMsg;
      inv.kind = "ok";
      inv.busy = false;
      await loadInvites(true);
    } catch (e) {
      if (who === scope()) {
        inv.msg =
          failText(e, { duplicate: "Já existe um convite pendente para este e-mail." }) +
          " Nada foi alterado.";
        inv.kind = "err";
      }
    } finally {
      inv.busy = false;
      paintInvites();
    }
  }
  function paintInvites() {
    const root = document.querySelector("[data-invites]");
    if (!root) return;
    const body = root.querySelector("[data-inv-body]");
    body.replaceChildren();
    const live = !!adapters.createInvite && canCreate();
    if (!adapters.listInvites)
      body.append(
        node(
          "p",
          "sm-hub-detail",
          "Aguardando API de convites. Enquanto isso, use “liberar acesso” acima para contas já cadastradas.",
        ),
      );
    const form = node("form", "sm-inv-form");
    form.noValidate = true;
    const email = node("input");
    email.type = "email";
    email.placeholder = "e-mail da pessoa";
    email.autocomplete = "off";
    email.maxLength = 254;
    email.setAttribute("aria-label", "E-mail a convidar");
    email.disabled = !live || inv.busy;
    const role = node("select");
    role.setAttribute("aria-label", "Permissão do convite");
    role.disabled = !live || inv.busy;
    for (const [v, l] of Object.entries(ROLES)) {
      const o = node("option", "", l);
      o.value = v;
      role.append(o);
    }
    const go = node("button", "btn", "Enviar convite");
    go.type = "submit";
    go.disabled = !live || inv.busy;
    go.dataset.invSend = "true";
    const err = node("p", "sm-hub-status");
    err.setAttribute("role", "alert");
    form.append(email, role, go);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = email.value.trim().toLowerCase();
      if (!EMAIL.test(v)) {
        err.textContent = "Informe um e-mail válido.";
        err.dataset.kind = "err";
        return email.focus();
      }
      if (inv.items.some((i) => i.status === "pending" && i.email.toLowerCase() === v)) {
        err.textContent = "Já existe um convite pendente para este e-mail.";
        err.dataset.kind = "err";
        return;
      }
      act(
        () => adapters.createInvite({ ...ctx(), email: v, role: role.value }),
        "Convite enviado.",
      );
    });
    body.append(form, err);
    const st = node(
      "p",
      "sm-hub-status",
      inv.phase === "loading" ? "Consultando convites…" : inv.msg,
    );
    st.dataset.kind = inv.kind;
    st.setAttribute("role", "status");
    body.append(st);
    if (inv.phase === "ready" && !inv.items.length)
      body.append(node("p", "sm-hub-detail", "Nenhum convite por aqui ainda."));
    const ul = node("ul", "sm-inv-list");
    for (const i of inv.items) {
      const li = node("li"),
        [k, t] = ST[i.status];
      li.dataset.invId = String(i.id);
      li.append(
        node("span", "sm-inv-mail", i.email),
        node("span", "sm-hub-detail", ROLES[i.role]),
        node("span", "sm-hub-badge sm-hub-" + k, t),
      );
      if (i.status === "pending")
        li.append(
          btn(
            "Revogar",
            () => {
              if (confirm("Revogar o convite de " + i.email + "?"))
                act(() => adapters.revokeInvite({ ...ctx(), id: i.id }), "Convite revogado.");
            },
            { disabled: !adapters.revokeInvite || !canRevoke() || inv.busy },
          ),
        );
      ul.append(li);
    }
    body.append(ul);
  }
  function mountInvites() {
    if (!location.hash.startsWith("#/config/conta") || !["owner", "admin"].includes(papel()))
      return;
    const view = document.getElementById("v");
    if (!view) return;
    if (view.querySelector("[data-invites]")) {
      paintInvites();
      loadInvites(false);
      return;
    }
    const root = node("section", "sm-hub sm-inv");
    root.dataset.invites = "true";
    const body = node("div");
    body.dataset.invBody = "true";
    root.append(
      node("h2", "", "Convites de equipe"),
      node(
        "p",
        "sm-hub-detail",
        "Convide por e-mail. O convite vale só para este negócio e pode ser revogado enquanto estiver pendente.",
      ),
      body,
    );
    view.append(root);
    paintInvites();
    loadInvites(false);
  }
  function mountAll() {
    checkEmail().then(paintBanner);
    paintBanner();
    mountInvites();
  }
  try {
    const prior = render;
    render = () => {
      prior();
      mountAll();
    };
  } catch {
    /* hashchange cobre */
  }
  window.addEventListener("hashchange", () =>
    queueMicrotask(() => {
      route();
      mountAll();
    }),
  );
  window.SocialMEIAccess = {
    register,
    slots: Object.freeze([...SLOTS]),
    validEmail: (v) => EMAIL.test(v),
  };
  queueMicrotask(() => {
    route();
    mountAll();
  });
})();
