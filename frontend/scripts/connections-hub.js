/* Central de Conexões (Configurações → Integrações): WhatsApp e Instagram.
   - Só lê contratos que o app já usa: /integrations/readiness, /whatsapp/receiving-status,
     /whatsapp/catalog/access, /instagram/meta/status, /instagram/publishing/account.
   - Nunca simula conexão: "conta configurada", "sessão conectada" e "canal operacional" são níveis separados
     e o terceiro só aparece como operacional quando o servidor confirma os dois primeiros e a sessão ao vivo.
   - Operações sem contrato conhecido (provisionar, QR, reconectar, ativar automações, desconectar) ficam
     "Preparadas": o botão só habilita quando um adaptador é registrado em SocialMEIConnections.register().
   Sem segredos: nada de tokens ou chaves aqui. Ações do Instagram reutilizam SocialMEIInstagram. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIConnections) return;

  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const workspace = () => host.identity?.negocio.id;
  const canManage = () => ["owner", "admin"].includes(host.identity?.papel);
  const STALE_MS = 20000;

  /* ---------- adaptadores (interface do frontend; o mapeamento para a API real é feito na homologação) ---------- */
  const SLOTS = {
    whatsapp: {
      provision: "Provisionar número/sessão do canal",
      pairingQr: "Exibir QR Code de pareamento",
      reconnect: "Reconectar a sessão",
      setAutomation: "Ativar ou desativar automações autorizadas",
    },
    instagram: {
      disconnect: "Desconectar a conta com segurança",
      setAutomation: "Ativar ou desativar automações do Direct",
      webhookHealth: "Consultar a saúde do webhook",
    },
  };
  const adapters = { whatsapp: {}, instagram: {} };
  function register(channel, impl) {
    if (!SLOTS[channel] || !impl || typeof impl !== "object") throw Error("Adaptador inválido.");
    for (const [name, fn] of Object.entries(impl)) {
      if (!SLOTS[channel][name] || typeof fn !== "function")
        throw Error("Operação desconhecida: " + name);
      adapters[channel][name] = fn;
    }
    mount(true);
  }

  /* ---------- estado ---------- */
  const fresh = () => ({
    owner: scope(),
    phase: "idle",
    at: 0,
    errors: {},
    ready: null,
    receipt: null,
    catalog: null,
    ig: null,
    igAccount: null,
  });
  let state = fresh();
  let busy = null; // nome da operação em andamento
  let pending = null;
  let notice = { text: "", kind: "" };
  const preparedOpen = {};
  let epoch = 0;

  const isBool = (v) => typeof v === "boolean";
  function validReadiness(r) {
    return (
      r?.source === "server" &&
      isBool(r.whatsapp?.configured) &&
      isBool(r.whatsapp?.receiving_configured) &&
      (r.whatsapp.sending_available === undefined || isBool(r.whatsapp.sending_available)) &&
      isBool(r.instagram?.oauth_available)
    );
  }
  function validReceipt(r) {
    return (
      r?.source === "postgresql" &&
      r.workspace_id === workspace() &&
      Number.isSafeInteger(r.message_count) &&
      r.message_count >= 0 &&
      Number.isSafeInteger(r.conversation_count) &&
      r.conversation_count >= 0 &&
      isBool(r.session_live_verified) &&
      (r.sending_available === undefined || isBool(r.sending_available)) &&
      (r.last_persisted_at === null || Number.isFinite(Date.parse(r.last_persisted_at)))
    );
  }
  const validCatalog = (c) => isBool(c?.enabled) && Array.isArray(c.channels);
  const validIg = (c) => ["connected", "disconnected", "expired"].includes(c?.status);

  async function load(force = false) {
    if (state.owner !== scope()) {
      state = fresh();
      epoch++;
    }
    if (pending) return pending;
    if (!force && state.phase === "ready" && Date.now() - state.at < STALE_MS) return state;
    const mine = ++epoch,
      owner = scope();
    state.phase = "loading";
    paint();
    pending = (async () => {
      const get = (path) => host.request(path);
      const [ready, receipt, catalog] = await Promise.allSettled([
        get("/integrations/readiness"),
        get("/whatsapp/receiving-status"),
        get("/whatsapp/catalog/access"),
      ]);
      const next = { ...fresh(), owner, phase: "ready", at: Date.now(), errors: {} };
      const take = (key, res, ok) => {
        if (res.status === "fulfilled" && ok(res.value)) next[key] = res.value;
        else
          next.errors[key] = res.status === "rejected" ? res.reason?.status || "rede" : "formato";
      };
      take("ready", ready, validReadiness);
      take("receipt", receipt, validReceipt);
      take("catalog", catalog, validCatalog);
      if (next.ready?.instagram.oauth_available) {
        try {
          const c = await get("/instagram/meta/status");
          if (validIg(c)) next.ig = c;
          else next.errors.ig = "formato";
        } catch (e) {
          next.errors.ig = e?.status || "rede";
        }
      }
      const igConnected = next.ig?.status === "connected" && next.ig.credential_available === true;
      if (igConnected && next.ready?.instagram.publishing_available === true) {
        try {
          const a = await get("/instagram/publishing/account");
          if (typeof a?.username === "string" && /^[A-Za-z0-9._]{1,30}$/.test(a.username))
            next.igAccount = a;
        } catch {
          /* perfil fica "não confirmado" */
        }
      }
      if (mine !== epoch || owner !== scope()) return state;
      state = next;
      return state;
    })().finally(() => {
      pending = null;
      paint();
    });
    return pending;
  }

  /* ---------- derivação (pura, testável) ---------- */
  function whatsappFacts(s = state) {
    const r = s.ready?.whatsapp,
      rc = s.receipt,
      ch = s.catalog?.channels || [];
    const configured = r ? r.configured : null;
    const receiving = r ? r.receiving_configured : null;
    const live = rc ? rc.session_live_verified : null;
    const sending = r
      ? r.sending_available === true && (rc ? rc.sending_available !== false : true)
      : null;
    const operational = configured === true && receiving === true && live === true;
    const problems = [];
    if (s.errors.ready)
      problems.push(
        "Não foi possível consultar a configuração no servidor (" + s.errors.ready + ").",
      );
    if (configured === false)
      problems.push("A conta WhatsApp deste negócio não está configurada no servidor.");
    if (configured && receiving === false)
      problems.push("O recebimento de mensagens ainda não foi configurado.");
    if (s.catalog && !ch.length)
      problems.push(
        "Nenhum canal WAHA cadastrado: o responsável precisa vincular a sessão e o número.",
      );
    if (ch.length && !ch.some((c) => c.active))
      problems.push("Há canal cadastrado, mas nenhum está ativo.");
    if (s.errors.receipt)
      problems.push(
        "Não foi possível consultar o histórico de recebimento (" + s.errors.receipt + ").",
      );
    if (rc && configured && receiving && rc.message_count === 0)
      problems.push(
        "Nenhuma mensagem recebida ainda. Envie uma mensagem de teste ao número e atualize.",
      );
    if (rc && live === false)
      problems.push(
        "A sessão não foi verificada ao vivo pelo servidor; o histórico não prova que ela está conectada agora.",
      );
    if (s.errors.catalog)
      problems.push("Não foi possível consultar os canais cadastrados (" + s.errors.catalog + ").");
    const known = s.ready || s.receipt || s.catalog;
    const overall = !known ? "unknown" : operational ? "ok" : configured ? "partial" : "off";
    return { configured, receiving, live, sending, operational, channels: ch, problems, overall };
  }
  function instagramFacts(s = state) {
    const r = s.ready?.instagram,
      c = s.ig;
    const oauth = r ? r.oauth_available : null;
    const status = c ? c.status : null;
    const connected = status === "connected" && c.credential_available === true;
    const problems = [];
    if (s.errors.ready)
      problems.push(
        "Não foi possível consultar a configuração no servidor (" + s.errors.ready + ").",
      );
    if (oauth === false)
      problems.push(
        "O aplicativo Meta não está configurado no servidor; a conexão ainda não pode ser iniciada.",
      );
    if (s.errors.ig) problems.push("Não foi possível consultar a conexão (" + s.errors.ig + ").");
    if (status === "expired")
      problems.push(
        "A credencial expirou. Reconecte a conta para voltar a receber e responder Direct.",
      );
    if (status === "connected" && c.credential_available !== true)
      problems.push(
        "A conexão consta como ativa, mas a credencial não está disponível no servidor. Reconecte a conta.",
      );
    if (connected && r && !r.incoming_available)
      problems.push("O recebimento de Direct está desativado no servidor.");
    const overall = !r ? "unknown" : connected ? "ok" : oauth ? "partial" : "off";
    return {
      oauth,
      status,
      connected,
      incoming: r?.incoming_available === true,
      sending: r?.send_enabled === true,
      publishing: r?.publishing_available === true,
      renew: r?.token_refresh_available === true,
      problems,
      overall,
    };
  }

  /* ---------- DOM ---------- */
  const node = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const LABEL = {
    ok: "Operacional",
    partial: "Parcial",
    off: "Não configurado",
    unknown: "Não verificado",
  };
  const badge = (kind, text) => node("span", "sm-hub-badge sm-hub-" + kind, text);
  function level(title, kind, value, detail) {
    const li = node("li", "sm-hub-level");
    const head = node("div", "sm-hub-lvl-head");
    head.append(node("span", "sm-hub-lvl-title", title), badge(kind, value));
    li.append(head);
    if (detail) li.append(node("p", "sm-hub-detail", detail));
    return li;
  }
  const yn = (v, yes, no) =>
    v === null ? ["unknown", "Não verificado"] : v ? ["ok", yes] : ["off", no];

  function button(label, { primary = false, disabled = false, title = "", onClick, name } = {}) {
    const b = node("button", "btn" + (primary ? "" : " o"), label);
    b.type = "button";
    b.disabled = disabled || !!busy;
    if (title) b.title = title;
    if (name) b.dataset.hubAction = name;
    if (onClick) b.addEventListener("click", onClick);
    return b;
  }

  function preparedBlock(channel, canWrite) {
    const box = node("details", "sm-hub-prepared");
    box.open = preparedOpen[channel] === true; /* o repaint não pode fechar o que a pessoa abriu */
    box.addEventListener("toggle", () => {
      preparedOpen[channel] = box.open;
    });
    const sum = node("summary", "", "Operações preparadas (dependem da API)");
    box.append(sum);
    const ul = node("ul");
    for (const [name, label] of Object.entries(SLOTS[channel])) {
      const li = node("li");
      const fn = adapters[channel][name];
      li.append(node("span", "", label));
      const st = badge(fn ? "ok" : "off", fn ? "Disponível" : "Aguardando API");
      const b = button(fn ? "Executar" : "Indisponível", {
        disabled: !fn || !canWrite,
        name: channel + ":" + name,
        title: !fn
          ? "Interface pronta; falta a API ou a infraestrutura correspondente."
          : !canWrite
            ? "Somente responsáveis pelo negócio."
            : "",
        onClick: () => runAdapter(channel, name),
      });
      li.append(st, b);
      ul.append(li);
    }
    box.append(ul);
    return box;
  }

  async function runAdapter(channel, name) {
    const fn = adapters[channel][name];
    if (!fn || busy || !canManage()) return;
    const destructive = name === "disconnect" || name === "reconnect" || name === "provision";
    if (destructive && !confirm(SLOTS[channel][name] + ". Continuar?")) return;
    const owner = scope(),
      key = channel + ":" + name;
    busy = key;
    notice = { text: SLOTS[channel][name] + "…", kind: "" };
    paint();
    try {
      const result = await fn({ workspaceId: workspace() });
      if (owner !== scope()) return;
      notice = {
        text: "Operação concluída pelo servidor. Consultando o estado atual…",
        kind: "ok",
      };
      if (name === "pairingQr" && result) showQr(result);
      await load(true);
    } catch (e) {
      if (owner === scope())
        notice = {
          text:
            (e?.message || "Não foi possível concluir a operação.") +
            " Nada foi marcado como conectado.",
          kind: "err",
        };
    } finally {
      busy = null;
      paint();
    }
  }
  function showQr(r) {
    const ok =
      typeof r.image_data_url === "string" &&
      /^data:image\/(png|svg\+xml);base64,[A-Za-z0-9+/=]+$/.test(r.image_data_url) &&
      r.image_data_url.length < 400000;
    const dlg = node("dialog", "sm-hub-qr");
    dlg.setAttribute("aria-label", "QR Code de pareamento do WhatsApp");
    dlg.append(node("h3", "", "Pareie o WhatsApp"));
    if (ok) {
      const img = node("img");
      img.alt = "QR Code de pareamento";
      img.src = r.image_data_url;
      img.width = 240;
      img.height = 240;
      dlg.append(img);
    } else dlg.append(node("p", "", "O servidor não devolveu um QR Code válido."));
    dlg.append(
      node(
        "p",
        "sm-hub-detail",
        "No celular: WhatsApp → Aparelhos conectados → Conectar aparelho. A conexão só vale quando o servidor confirmar a sessão.",
      ),
    );
    const close = button("Fechar", { onClick: () => dlg.close() });
    close.disabled = false;
    dlg.append(close);
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
  }

  function whatsappCard() {
    const f = whatsappFacts(),
      card = node("article", "sm-hub-card");
    card.dataset.hubChannel = "whatsapp";
    const head = node("div", "sm-hub-head");
    head.append(node("h3", "", "WhatsApp"), badge(f.overall, LABEL[f.overall]));
    card.append(head);
    const company = host.identity?.negocio;
    const ul = node("ul", "sm-hub-levels");
    const [k1, t1] = yn(f.configured, "Configurada no servidor", "Não configurada");
    ul.append(
      level(
        "1 · Conta configurada",
        k1,
        t1,
        "Empresa: " +
          (company?.nome || "—") +
          " (#" +
          (company?.id ?? "—") +
          ")" +
          (state.catalog ? " · " + f.channels.length + " canal(is) cadastrado(s)" : ""),
      ),
    );
    const [k2, t2] = yn(f.live, "Verificada ao vivo", "Não verificada");
    ul.append(
      level(
        "2 · Sessão conectada",
        k2,
        t2,
        f.live === true
          ? "O servidor confirmou a sessão agora."
          : "Só é considerada conectada quando o servidor confirma a sessão ao vivo.",
      ),
    );
    const opK = f.operational ? "ok" : f.configured === null ? "unknown" : "off";
    const rc = state.receipt;
    ul.append(
      level(
        "3 · Canal operacional",
        opK,
        f.operational ? "Recebendo" : "Não confirmado",
        (f.receiving === null
          ? ""
          : f.receiving
            ? "Recebimento configurado. "
            : "Recebimento não configurado. ") +
          (rc
            ? rc.message_count
              ? rc.message_count +
                " mensagem(ns) em " +
                rc.conversation_count +
                " conversa(s); última em " +
                new Date(rc.last_persisted_at).toLocaleString("pt-BR") +
                ". "
              : "Nenhuma mensagem recebida ainda. "
            : "") +
          (f.sending === null
            ? ""
            : f.sending
              ? "Envio de respostas habilitado (exige confirmação humana)."
              : "Envio de respostas indisponível."),
      ),
    );
    card.append(ul);
    if (f.channels.length) {
      const list = node("ul", "sm-hub-channels");
      for (const c of f.channels)
        list.append(
          node(
            "li",
            "",
            (c.name || c.instance || "Canal") +
              " · " +
              (c.active ? "ativo" : "inativo") +
              " · " +
              (c.enabled ? "catálogo autorizado" : "sem acesso ao catálogo"),
          ),
        );
      card.append(list);
    }
    if (f.problems.length) {
      const d = node("div", "sm-hub-diag");
      d.append(node("strong", "", "Diagnóstico"));
      const pl = node("ul");
      f.problems.forEach((p) => pl.append(node("li", "", p)));
      d.append(pl);
      card.append(d);
    }
    const act = node("div", "sm-hub-actions");
    act.append(
      button("Atualizar estado", {
        primary: true,
        name: "wa-refresh",
        onClick: () => {
          notice = { text: "", kind: "" };
          load(true);
        },
      }),
      button("Abrir Caixa Unificada", {
        name: "wa-inbox",
        onClick: () => {
          location.hash = "#/caixa";
        },
      }),
      button("Configurar catálogo", {
        name: "wa-catalog",
        onClick: () =>
          document
            .querySelector("[data-wa-catalog]")
            ?.scrollIntoView({ block: "start", behavior: "smooth" }),
      }),
      button("Prévia do menu automático", {
        name: "wa-menu",
        onClick: () =>
          document
            .querySelector("[data-wa-bot-preview]")
            ?.scrollIntoView({ block: "center", behavior: "smooth" }),
      }),
    );
    card.append(act);
    card.append(
      node(
        "p",
        "sm-hub-detail",
        "Atendimento humano: em cada conversa da Caixa Unificada, pause ou retome o menu automático. O estado aparece no painel da própria conversa.",
      ),
    );
    card.append(preparedBlock("whatsapp", canManage()));
    return card;
  }

  const PERMS = [
    ["instagram_business_basic", "Perfil básico"],
    ["instagram_business_manage_messages", "Mensagens (Direct)"],
    ["instagram_business_content_publish", "Publicação de conteúdo"],
    ["instagram_business_manage_comments", "Comentários"],
  ];
  function instagramCard() {
    const f = instagramFacts(),
      card = node("article", "sm-hub-card");
    card.dataset.hubChannel = "instagram";
    const head = node("div", "sm-hub-head");
    head.append(node("h3", "", "Instagram"), badge(f.overall, LABEL[f.overall]));
    card.append(head);
    const ul = node("ul", "sm-hub-levels");
    const authText =
      f.status === "connected"
        ? f.connected
          ? "Autenticado"
          : "Credencial indisponível"
        : f.status === "expired"
          ? "Credencial expirada"
          : f.status === "disconnected"
            ? "Não conectado"
            : "Não verificado";
    const authKind = f.connected
      ? "ok"
      : f.status === "expired" || (f.status === "connected" && !f.connected)
        ? "err"
        : f.status
          ? "off"
          : "unknown";
    ul.append(
      level(
        "Autenticação",
        authKind,
        authText,
        f.oauth === false ? "Aplicativo Meta não configurado no servidor." : "",
      ),
    );
    ul.append(
      level(
        "Perfil conectado",
        state.igAccount ? "ok" : "unknown",
        state.igAccount ? "@" + state.igAccount.username : "Não confirmado",
        state.igAccount
          ? "Confirmado pelo servidor."
          : "O perfil só é exibido quando o servidor o confirma (exige conexão ativa e publicação habilitada).",
      ),
    );
    ul.append(
      level(
        "Atendimento pelo Direct",
        f.connected && f.incoming ? "ok" : "off",
        f.connected && f.incoming ? "Recebendo" : "Inativo",
        (f.incoming ? "Recebimento habilitado. " : "Recebimento desativado. ") +
          (f.sending
            ? "Respostas pelo painel habilitadas (exigem confirmação)."
            : "Respostas pelo painel desativadas."),
      ),
    );
    ul.append(
      level(
        "Publicação",
        f.connected && f.publishing ? "ok" : "off",
        f.publishing ? "Habilitada" : "Desativada",
        "Publicações exigem revisão e confirmação na Divulgação.",
      ),
    );
    card.append(ul);
    const perms = node("div", "sm-hub-perms");
    perms.append(node("strong", "", "Permissões solicitadas na autorização"));
    const pl = node("ul");
    PERMS.forEach(([, label]) => pl.append(node("li", "", label)));
    perms.append(pl);
    perms.append(
      node(
        "p",
        "sm-hub-detail",
        "A Meta decide o que foi concedido; esta tela não lê as permissões concedidas.",
      ),
    );
    card.append(perms);
    if (f.problems.length) {
      const d = node("div", "sm-hub-diag");
      d.append(node("strong", "", "Diagnóstico"));
      const dl = node("ul");
      f.problems.forEach((p) => dl.append(node("li", "", p)));
      d.append(dl);
      card.append(d);
    }
    const ig = window.SocialMEIInstagram,
      act = node("div", "sm-hub-actions");
    const showConnect = f.oauth === true && !f.connected,
      mayConnect = canManage() && !!ig;
    if (showConnect)
      act.append(
        button(f.status === "expired" ? "Reconectar Instagram" : "Conectar Instagram", {
          primary: true,
          name: "ig-connect",
          disabled: !mayConnect,
          title: canManage() ? "" : "Somente responsáveis pelo negócio.",
          onClick: () => ig.connect(),
        }),
      );
    if (f.connected && f.renew)
      act.append(
        button("Renovar credencial", {
          name: "ig-renew",
          disabled: !mayConnect,
          onClick: () => ig.renew(),
        }),
      );
    act.append(
      button("Consultar novamente", {
        primary: !showConnect,
        name: "ig-refresh",
        onClick: () => {
          notice = { text: "", kind: "" };
          load(true);
        },
      }),
      button("Abrir Caixa Unificada", {
        name: "ig-inbox",
        onClick: () => {
          location.hash = "#/caixa";
        },
      }),
    );
    card.append(act);
    card.append(preparedBlock("instagram", canManage() && f.connected));
    return card;
  }

  function paint() {
    const root = document.querySelector("[data-conn-hub]");
    if (!root) return;
    root.setAttribute("aria-busy", String(state.phase === "loading" || !!busy));
    const body = root.querySelector("[data-hub-body]");
    const status = root.querySelector("[data-hub-status]");
    status.textContent =
      notice.text ||
      (state.phase === "loading"
        ? "Consultando o servidor…"
        : state.phase === "ready"
          ? "Estado consultado às " +
            new Date(state.at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) +
            ". Nada aqui simula conexão."
          : "");
    status.dataset.kind = notice.kind;
    const focused = document.activeElement?.dataset?.hubAction;
    body.replaceChildren(whatsappCard(), instagramCard());
    if (focused)
      body.querySelector('[data-hub-action="' + focused + '"]')?.focus({ preventScroll: true });
  }

  function mount(force = false) {
    if (!location.hash.startsWith("#/config/integracoes")) return;
    const view = document.getElementById("v");
    if (!view) return;
    if (view.querySelector("[data-conn-hub]")) {
      if (force) paint();
      return;
    }
    const root = node("section", "sm-hub");
    root.dataset.connHub = "true";
    root.setAttribute("aria-label", "Central de Conexões");
    const head = node("div", "sm-hub-top");
    head.append(
      node("h2", "", "Central de Conexões"),
      node(
        "p",
        "sm-hub-detail",
        "Estado real dos canais deste negócio, consultado no servidor. Conta configurada, sessão conectada e canal operacional são coisas diferentes.",
      ),
    );
    const status = node("p", "sm-hub-status");
    status.dataset.hubStatus = "true";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const body = node("div", "sm-hub-grid");
    body.dataset.hubBody = "true";
    root.append(head, status, body);
    const anchor = view.querySelector("p.m") || view.firstElementChild;
    anchor ? anchor.after(root) : view.prepend(root);
    paint();
    load();
    setTimeout(paint, 1200); /* SocialMEIInstagram carrega depois: religa os botões dele */
  }

  try {
    const prior = render;
    render = () => {
      prior();
      mount();
    };
  } catch {
    /* sem hook: o hashchange abaixo cobre */
  }
  window.addEventListener("hashchange", () => queueMicrotask(() => mount()));
  document.addEventListener("socialmei-data-change", () => {
    if (state.owner !== scope()) state = fresh();
  });
  window.SocialMEIConnections = {
    register,
    refresh: () => load(true),
    facts: { whatsapp: whatsappFacts, instagram: instagramFacts },
    get snapshot() {
      return { ...state };
    },
    adapters: Object.freeze(
      Object.fromEntries(Object.entries(SLOTS).map(([k, v]) => [k, Object.keys(v)])),
    ),
  };
  queueMicrotask(() => mount());
})();
