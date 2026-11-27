/* Central de Conexões (Configurações → Integrações): WhatsApp e Instagram. · v7.6.1 (cartões compactos + painel lateral; ver fim do arquivo)
   v7.1.1
   - v7.1.1 (estabilidade multiempresa): tudo que é assíncrono pertence a uma "geração" (empresa + usuário).
     Ao trocar de empresa o estado, avisos, operações, diálogos (confirmação e QR Code) e a consulta periódica do
     QR são descartados; uma consulta pendente da empresa anterior nunca bloqueia a nova e sua resposta, se
     chegar depois, é ignorada. Uma consulta antiga também deixa de disparar requisições de seguimento.
   - Só lê contratos que o app já usa: /integrations/readiness, /whatsapp/receiving-status,
     /whatsapp/catalog/access, /instagram/meta/status, /instagram/publishing/account.
   - Nunca simula conexão: "conta configurada", "sessão conectada" e "canal operacional" são níveis separados
     e o terceiro só aparece como operacional quando o servidor confirma os dois primeiros e a sessão ao vivo.
   - Operações sem contrato conhecido (provisionar, QR, reconectar, desconectar, ativar automações) ficam
     "Aguardando API": o botão só habilita quando um adaptador é registrado em SocialMEIConnections.register().
   - v7.1: cada canal mostra estado em seis níveis (não configurado, configurado, conectando, conectado,
     operacional, erro), um "próximo passo" guiado derivado dos fatos reais, diagnóstico em linguagem simples,
     confirmações dentro da página e QR Code que consulta o servidor até ele confirmar a sessão.
   Sem segredos: nada de tokens ou chaves aqui. Ações do Instagram reutilizam SocialMEIInstagram. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIConnections) return;

  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const workspace = () => host.identity?.negocio.id;
  const canManage = () => ["owner", "admin"].includes(host.identity?.papel);
  const STALE_MS = 20000, OLD_MS = 5 * 60000, POLL_MS = 4000, POLL_MAX = 30;
  const PAPEL = { owner: "Proprietário", admin: "Administrador", member: "Operacional", viewer: "Leitura", report_viewer: "Somente relatórios" };

  /* ---------- adaptadores (interface do frontend; o mapeamento para a API real é feito na homologação) ---------- */
  const SLOTS = {
    whatsapp: {
      provision: "Provisionar número/sessão do canal",
      pairingQr: "Exibir QR Code de pareamento",
      reconnect: "Reconectar a sessão",
      disconnect: "Desconectar o canal com segurança",
      setAutomation: "Ativar ou desativar automações autorizadas",
    },
    instagram: {
      disconnect: "Desconectar a conta com segurança",
      setAutomation: "Ativar ou desativar automações do Direct",
      webhookHealth: "Consultar a saúde do webhook",
    },
  };
  const WHY = {
    provision: "Cria o vínculo entre o número e este negócio.",
    pairingQr: "Mostra o QR Code para parear o aparelho.",
    reconnect: "Pede ao servidor para reiniciar a sessão.",
    disconnect: "Encerra o atendimento deste canal.",
    setAutomation: "Liga ou desliga respostas automáticas autorizadas.",
    webhookHealth: "Informa se o Instagram está entregando mensagens.",
  };
  const adapters = { whatsapp: {}, instagram: {} };
  function register(channel, impl) {
    if (!SLOTS[channel] || !impl || typeof impl !== "object") throw Error("Adaptador inválido.");
    for (const [name, fn] of Object.entries(impl)) {
      if (!SLOTS[channel][name] || typeof fn !== "function") throw Error("Operação desconhecida: " + name);
      adapters[channel][name] = fn;
    }
    mount(true);
  }

  /* ---------- estado ---------- */
  const fresh = () => ({ owner: scope(), phase: "idle", at: 0, errors: {}, ready: null, receipt: null, catalog: null, ig: null, igAccount: null });
  let state = fresh();
  let busy = null; // nome da operação em andamento (canal:operação)
  let pending = null, pendingOwner = null; // consulta em andamento e a empresa a que ela pertence
  let busyTok = 0; // identifica a operação em andamento: só ela pode liberar o "ocupado"
  const dialogs = new Set(); // diálogos abertos por este módulo (confirmação e QR Code)
  let notice = { text: "", kind: "" };
  const preparedOpen = {};
  let epoch = 0;
  let poll = null; // consulta periódica enquanto o QR Code está aberto

  const isBool = (v) => typeof v === "boolean";
  function validReadiness(r) {
    return r?.source === "server" && isBool(r.whatsapp?.configured) && isBool(r.whatsapp?.receiving_configured) &&
      (r.whatsapp.sending_available === undefined || isBool(r.whatsapp.sending_available)) &&
      isBool(r.instagram?.oauth_available);
  }
  function validReceipt(r) {
    return r?.source === "postgresql" && r.workspace_id === workspace() && Number.isSafeInteger(r.message_count) && r.message_count >= 0 &&
      Number.isSafeInteger(r.conversation_count) && r.conversation_count >= 0 && isBool(r.session_live_verified) &&
      (r.sending_available === undefined || isBool(r.sending_available)) &&
      (r.last_persisted_at === null || Number.isFinite(Date.parse(r.last_persisted_at)));
  }
  const validCatalog = (c) => isBool(c?.enabled) && Array.isArray(c.channels);
  const validIg = (c) => ["connected", "disconnected", "expired"].includes(c?.status);

  async function load(force = false) {
    if (state.owner !== scope()) resetContext();
    if (pending && pendingOwner === scope()) return pending; /* consulta de outra empresa nunca é reaproveitada */
    if (!force && state.phase === "ready" && Date.now() - state.at < STALE_MS) return state;
    const mine = ++epoch, owner = scope();
    const stale = () => mine !== epoch || owner !== scope();
    state.phase = "loading"; paint();
    const job = (async () => {
      const get = (path) => host.request(path);
      const [ready, receipt, catalog] = await Promise.allSettled([get("/integrations/readiness"), get("/whatsapp/receiving-status"), get("/whatsapp/catalog/access")]);
      const next = { ...fresh(), owner, phase: "ready", at: Date.now(), errors: {} };
      const take = (key, res, ok) => {
        if (res.status === "fulfilled" && ok(res.value)) next[key] = res.value;
        else next.errors[key] = res.status === "rejected" ? (res.reason?.status || "rede") : "formato";
      };
      take("ready", ready, validReadiness);
      take("receipt", receipt, validReceipt);
      take("catalog", catalog, validCatalog);
      if (stale()) return state; /* trocou de empresa: não emite mais nenhuma requisição deste ciclo */
      if (next.ready?.instagram.oauth_available) {
        try { const c = await get("/instagram/meta/status"); if (validIg(c)) next.ig = c; else next.errors.ig = "formato"; }
        catch (e) { next.errors.ig = e?.status || "rede"; }
      }
      const igConnected = next.ig?.status === "connected" && next.ig.credential_available === true;
      if (igConnected && next.ready?.instagram.publishing_available === true && !stale()) {
        try { const a = await get("/instagram/publishing/account"); if (typeof a?.username === "string" && /^[A-Za-z0-9._]{1,30}$/.test(a.username)) next.igAccount = a; }
        catch { /* perfil fica "não confirmado" */ }
      }
      if (stale()) return state;
      state = next;
      return state;
    })().finally(() => {
      if (pending === job) { pending = null; pendingOwner = null; }
      if (!stale() && notice.switching) notice = { text: "", kind: "" }; /* o aviso de troca some quando a empresa nova responde */
      paint();
    });
    pending = job; pendingOwner = owner;
    return job;
  }

  /* ---------- derivação (pura, testável) ---------- */
  function whatsappFacts(s = state) {
    const r = s.ready?.whatsapp, rc = s.receipt, ch = s.catalog?.channels || [];
    const configured = r ? r.configured : null;
    const receiving = r ? r.receiving_configured : null;
    const live = rc ? rc.session_live_verified : null;
    const sending = r ? r.sending_available === true && (rc ? rc.sending_available !== false : true) : null;
    const operational = configured === true && receiving === true && live === true;
    const issues = [];
    const add = (level, text, title, fix) => issues.push({ level, text, title, fix });
    if (s.errors.ready) add("err", "Não foi possível consultar a configuração no servidor (" + s.errors.ready + ").", "Não conseguimos falar com o servidor", "Confira sua internet e toque em Atualizar. Se continuar, avise o suporte informando o código " + s.errors.ready + ".");
    if (configured === false) add("warn", "A conta WhatsApp deste negócio não está configurada no servidor.", "O WhatsApp deste negócio ainda não foi ativado", "A ativação é feita pelo responsável pelo servidor. Peça informando o nome do negócio.");
    if (configured && receiving === false) add("warn", "O recebimento de mensagens ainda não foi configurado.", "O recebimento de mensagens ainda não foi ligado", "Peça ao responsável pelo servidor para configurar o recebimento e depois toque em Atualizar.");
    if (s.catalog && !ch.length) add("warn", "Nenhum canal WAHA cadastrado: o responsável precisa vincular a sessão e o número.", "Nenhum número vinculado", "O responsável precisa vincular a sessão e o número a este negócio.");
    if (ch.length && !ch.some((c) => c.active)) add("warn", "Há canal cadastrado, mas nenhum está ativo.", "Há número vinculado, mas nenhum está ativo", "Peça para ativar o canal cadastrado.");
    if (s.errors.receipt) add("err", "Não foi possível consultar o histórico de recebimento (" + s.errors.receipt + ").", "Não conseguimos ver as mensagens recebidas", "Toque em Atualizar. O código do erro é " + s.errors.receipt + ".");
    if (rc && configured && receiving && rc.message_count === 0) add("info", "Nenhuma mensagem recebida ainda. Envie uma mensagem de teste ao número e atualize.", "Ainda não chegou nenhuma mensagem", "Envie um “oi” de outro celular para o número do negócio e toque em Atualizar.");
    if (rc && live === false) add("warn", "A sessão não foi verificada ao vivo pelo servidor; o histórico não prova que ela está conectada agora.", "A sessão não está confirmada agora", "Mensagens antigas não provam que o WhatsApp está conectado. Pareie o aparelho ou peça ao responsável para reconectar a sessão.");
    if (s.errors.catalog) add("err", "Não foi possível consultar os canais cadastrados (" + s.errors.catalog + ").", "Não conseguimos ver os números vinculados", "Toque em Atualizar. O código do erro é " + s.errors.catalog + ".");
    const known = s.ready || s.receipt || s.catalog;
    const overall = !known ? "unknown" : operational ? "ok" : configured ? "partial" : "off";
    const connecting = !!busy && busy.startsWith("whatsapp:");
    const stage = connecting ? "connecting" : s.errors.ready && !s.ready ? "error" : operational ? "operational" : live === true ? "connected" : configured === true ? "configured" : configured === false ? "unconfigured" : "unknown";
    return { configured, receiving, live, sending, operational, channels: ch, problems: issues.map((i) => i.text), issues, overall, stage };
  }
  function instagramFacts(s = state) {
    const r = s.ready?.instagram, c = s.ig;
    const oauth = r ? r.oauth_available : null;
    const status = c ? c.status : null;
    const connected = status === "connected" && c.credential_available === true;
    const issues = [];
    const add = (level, text, title, fix) => issues.push({ level, text, title, fix });
    if (s.errors.ready) add("err", "Não foi possível consultar a configuração no servidor (" + s.errors.ready + ").", "Não conseguimos falar com o servidor", "Confira sua internet e toque em Consultar novamente. Código: " + s.errors.ready + ".");
    if (oauth === false) add("warn", "O aplicativo Meta não está configurado no servidor; a conexão ainda não pode ser iniciada.", "O aplicativo da Meta ainda não está ligado", "Sem ele não dá para conectar o Instagram. O responsável pelo servidor precisa configurá-lo.");
    if (s.errors.ig) add("err", "Não foi possível consultar a conexão (" + s.errors.ig + ").", "Não conseguimos ver a conexão do Instagram", "Toque em Consultar novamente. Código: " + s.errors.ig + ".");
    if (status === "expired") add("err", "A credencial expirou. Reconecte a conta para voltar a receber e responder Direct.", "A autorização do Instagram expirou", "Toque em Reconectar Instagram e autorize de novo para voltar a receber e responder Direct.");
    if (status === "connected" && c.credential_available !== true) add("err", "A conexão consta como ativa, mas a credencial não está disponível no servidor. Reconecte a conta.", "A conexão está incompleta", "A conta consta como conectada, mas falta a credencial no servidor. Reconecte o Instagram.");
    if (connected && r && !r.incoming_available) add("warn", "O recebimento de Direct está desativado no servidor.", "O recebimento de Direct está desligado", "A conta está conectada, mas o servidor não está recebendo Direct. Peça ao responsável para ligar.");
    const overall = !r ? "unknown" : connected ? "ok" : oauth ? "partial" : "off";
    const connecting = !!busy && busy.startsWith("instagram:");
    const incoming = r?.incoming_available === true;
    const stage = connecting ? "connecting" : (s.errors.ready && !s.ready) || status === "expired" || (status === "connected" && !connected) || (s.errors.ig && !c) ? "error" : connected && incoming ? "operational" : connected ? "connected" : oauth === true ? "configured" : oauth === false ? "unconfigured" : "unknown";
    return { oauth, status, connected, incoming, sending: r?.send_enabled === true, publishing: r?.publishing_available === true, renew: r?.token_refresh_available === true, problems: issues.map((i) => i.text), issues, overall, stage };
  }

  /* ---------- DOM ---------- */
  const node = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const svg = (d, size = 20) => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("width", size); s.setAttribute("height", size); s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor"); s.setAttribute("stroke-width", "1.8"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round"); s.setAttribute("aria-hidden", "true"); const p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", d); s.append(p); return s; };
  const ICON = {
    whatsapp: "M3 21l1.6-4.6A8.5 8.5 0 1 1 8 19.6L3 21zM9 8.5c0 3.5 3 6.5 6.5 6.5l1-1.6-2-1-1 .8a4 4 0 0 1-2-2l.8-1-1-2L9 8.5z",
    instagram: "M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4zm5 5.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM17.2 6.8h.01",
    check: "M5 12.5l4.2 4.2L19 7",
    alert: "M12 8v5M12 17h.01M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
    info: "M12 11v5M12 8h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z",
    refresh: "M20 11a8 8 0 0 0-14.9-3M4 5v4h4M4 13a8 8 0 0 0 14.9 3M20 19v-4h-4",
  };
  const LABEL = { ok: "Operacional", partial: "Parcial", off: "Não configurado", unknown: "Não verificado" };
  const STAGE = { unconfigured: "Não configurado", configured: "Configurado", connecting: "Conectando", connected: "Conectado", operational: "Operacional", error: "Erro", unknown: "Não verificado" };
  const STAGE_HINT = {
    unconfigured: "O servidor ainda não tem este canal preparado.",
    configured: "Preparado no servidor, falta conectar.",
    connecting: "Aguardando o servidor confirmar.",
    connected: "Conectado, falta confirmar o recebimento.",
    operational: "Recebendo mensagens de verdade.",
    error: "Algo precisa de atenção.",
    unknown: "Ainda não consultamos o servidor.",
  };
  const TRACK = ["unconfigured", "configured", "connected", "operational"];
  const badge = (kind, text) => node("span", "sm-hub-badge sm-hub-" + kind, text);
  const ago = (t) => {
    const m = Math.round((Date.now() - t) / 60000);
    if (!Number.isFinite(m)) return "";
    if (m < 1) return "agora";
    if (m < 60) return "há " + m + " min";
    const h = Math.round(m / 60);
    if (h < 24) return "há " + h + " h";
    const d = Math.round(h / 24);
    return "há " + d + (d === 1 ? " dia" : " dias");
  };
  const hhmm = (t) => new Date(t).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  function level(title, kind, value, detail) {
    const li = node("li", "sm-hub-level");
    const head = node("div", "sm-hub-lvl-head");
    head.append(node("span", "sm-hub-lvl-title", title), badge(kind, value));
    li.append(head);
    if (detail) li.append(node("p", "sm-hub-detail", detail));
    return li;
  }
  const yn = (v, yes, no) => (v === null ? ["unknown", "Não verificado"] : v ? ["ok", yes] : ["off", no]);

  function button(label, { primary = false, disabled = false, title = "", onClick, name, icon } = {}) {
    const b = node("button", "btn" + (primary ? "" : " o"));
    if (icon) b.append(svg(ICON[icon], 16));
    b.append(document.createTextNode(label));
    b.type = "button";
    b.disabled = disabled || !!busy;
    if (title) b.title = title;
    if (name) b.dataset.hubAction = name;
    if (onClick) b.addEventListener("click", onClick);
    return b;
  }

  /* Diálogo de confirmação dentro da página (foco começa em "Cancelar"; Esc cancela). */
  function confirmDialog({ title, body, confirmLabel, danger = false, ack = "" }) {
    return new Promise((resolve) => {
      const dlg = node("dialog", "sm-hub-qr sm-hub-confirm"); dlg.setAttribute("aria-labelledby", "sm-hub-cd-t");
      const h = node("h3", "", title); h.id = "sm-hub-cd-t";
      const who = node("p", "sm-hub-who", "Negócio: " + (host.identity?.negocio?.nome || "—") + " (#" + (workspace() ?? "—") + ")");
      dlg.append(h, who);
      for (const t of [].concat(body)) dlg.append(node("p", "sm-hub-detail", t));
      let check = null;
      if (ack) { const l = node("label", "sm-hub-ack"); check = node("input"); check.type = "checkbox"; l.append(check, document.createTextNode(" " + ack)); dlg.append(l); }
      const row = node("div", "sm-hub-actions");
      const cancel = node("button", "btn o", "Cancelar"); cancel.type = "button";
      const ok = node("button", "btn" + (danger ? " sm-hub-danger" : ""), confirmLabel); ok.type = "button"; ok.disabled = !!check;
      if (check) check.addEventListener("change", () => { ok.disabled = !check.checked; });
      let answer = false;
      cancel.addEventListener("click", () => dlg.close());
      ok.addEventListener("click", () => { answer = true; dlg.close(); });
      row.append(cancel, ok); dlg.append(row);
      dlg.addEventListener("close", () => { dialogs.delete(dlg); dlg.remove(); resolve(answer); });
      dialogs.add(dlg); document.body.append(dlg); dlg.showModal(); cancel.focus();
    });
  }

  function actionRows(channel, canWrite) {
    const box = node("details", "sm-hub-prepared");
    box.open = preparedOpen[channel] === true; /* o repaint não pode fechar o que a pessoa abriu */
    box.addEventListener("toggle", () => { preparedOpen[channel] = box.open; });
    const avail = Object.keys(SLOTS[channel]).filter((n) => adapters[channel][n]).length;
    box.append(node("summary", "", "Ações do canal · " + avail + " de " + Object.keys(SLOTS[channel]).length + " disponíveis"));
    const ul = node("ul");
    for (const [name, label] of Object.entries(SLOTS[channel])) {
      const li = node("li"), fn = adapters[channel][name];
      const txt = node("div", "sm-hub-act-txt"); txt.append(node("span", "sm-hub-act-name", label), node("small", "sm-hub-detail", fn ? (canWrite ? WHY[name] : "Somente responsáveis pelo negócio podem usar.") : "Indisponível: a interface está pronta, mas falta a API correspondente."));
      const b = button(fn ? "Executar" : "Indisponível", { disabled: !fn || !canWrite, name: channel + ":" + name, onClick: () => runAdapter(channel, name) });
      li.append(txt, badge(fn ? "ok" : "off", fn ? "Disponível" : "Aguardando API"), b);
      ul.append(li);
    }
    box.append(ul);
    return box;
  }

  const CONFIRM = {
    provision: { title: "Provisionar o canal?", body: ["Vai vincular um número e uma sessão de WhatsApp a este negócio."], confirmLabel: "Provisionar" },
    reconnect: { title: "Reconectar a sessão?", body: ["O servidor vai tentar reiniciar a sessão. Mensagens podem demorar a chegar nesse intervalo.", "Nada será marcado como conectado até o servidor confirmar."], confirmLabel: "Reconectar" },
    disconnect: { title: "Desconectar este canal?", body: ["O canal deixa de receber e responder mensagens deste negócio.", "Para voltar a atender será preciso conectar de novo."], confirmLabel: "Desconectar", danger: true, ack: "Entendo que o atendimento por este canal será interrompido." },
  };
  async function runAdapter(channel, name) {
    const fn = adapters[channel][name];
    if (!fn || busy || !canManage()) return;
    const c = CONFIRM[name];
    if (c && !(await confirmDialog({ ...c, title: c.title + " (" + (channel === "whatsapp" ? "WhatsApp" : "Instagram") + ")" }))) return;
    const owner = scope(), key = channel + ":" + name, tok = ++busyTok, workspaceId = workspace();
    busy = key; notice = { text: SLOTS[channel][name] + "…", kind: "" }; paint();
    try {
      const result = await fn({ workspaceId });
      if (owner !== scope() || tok !== busyTok) return; /* a empresa mudou: o resultado não pertence mais a esta tela */
      notice = { text: "Operação concluída pelo servidor. Consultando o estado atual…", kind: "ok" };
      busy = null;
      if (name === "pairingQr" && result) showQr(result);
      await load(true);
      if (owner === scope() && tok === busyTok) notice = { text: "Pronto. O estado abaixo foi confirmado agora pelo servidor.", kind: "ok" };
    } catch (e) {
      if (owner === scope() && tok === busyTok) notice = { text: (e?.message || "Não foi possível concluir a operação.") + " Nada foi marcado como conectado.", kind: "err" };
    } finally { if (tok === busyTok) busy = null; paint(); }
  }

  function stopPoll(only) { if (poll && (!only || poll === only)) { clearInterval(poll.timer); poll = null; } }
  function closeDialogs() { for (const d of [...dialogs]) { try { d.close(); } catch { d.remove(); } } dialogs.clear(); }
  /* Troca de empresa/usuário: descarta tudo o que pertencia ao contexto anterior. */
  function resetContext() {
    const switched = !!state.owner && !/undefined/.test(state.owner) && state.owner !== scope();
    epoch++; busyTok++; state = fresh(); pending = null; pendingOwner = null; busy = null;
    stopPoll(); closeDialogs(); dstate.channel = null;
    const nome = host.identity?.negocio?.nome;
    notice = switched && nome ? { text: "Agora você está vendo " + nome + ". Nada do negócio anterior foi mantido; consultando o servidor…", kind: "", switching: true } : { text: "", kind: "" };
  }
  function syncScope() {
    if (state.owner === scope()) return;
    resetContext(); paint();
    if (document.querySelector("[data-conn-hub]")) load();
  }
  function showQr(r) {
    stopPoll(); for (const d of [...dialogs]) if (d.classList.contains("sm-hub-qrbox")) d.close();
    const ok = typeof r.image_data_url === "string" && /^data:image\/(png|svg\+xml);base64,[A-Za-z0-9+/=]+$/.test(r.image_data_url) && r.image_data_url.length < 400000;
    const dlg = node("dialog", "sm-hub-qr sm-hub-qrbox"); dlg.setAttribute("aria-labelledby", "sm-hub-qr-t");
    const h = node("h3", "", "Pareie o WhatsApp"); h.id = "sm-hub-qr-t";
    dlg.append(h, node("p", "sm-hub-who", "Negócio: " + (host.identity?.negocio?.nome || "—") + " (#" + (workspace() ?? "—") + ")"));
    if (ok) { const frame = node("div", "sm-hub-qrframe"); const img = node("img"); img.alt = "QR Code de pareamento do WhatsApp"; img.src = r.image_data_url; img.width = 240; img.height = 240; frame.append(img); dlg.append(frame); }
    else dlg.append(node("p", "sm-hub-diag", "O servidor não devolveu um QR Code válido. Feche e tente de novo."));
    const ol = node("ol", "sm-hub-qrsteps");
    for (const t of ["No celular do negócio, abra o WhatsApp.", "Toque em Aparelhos conectados → Conectar aparelho.", "Aponte a câmera para este QR Code."]) ol.append(node("li", "", t));
    dlg.append(ol);
    const st = node("p", "sm-hub-qrstatus", ok ? "Aguardando o servidor confirmar a sessão…" : ""); st.setAttribute("role", "status"); st.setAttribute("aria-live", "polite"); dlg.append(st);
    const row = node("div", "sm-hub-actions");
    const check = node("button", "btn", "Já escaneei, verificar agora"); check.type = "button";
    const close = node("button", "btn o", "Fechar"); close.type = "button";
    row.append(check, close); dlg.append(row);
    const owner = scope();
    let mine = null, checking = false; /* mine: a consulta periódica deste diálogo */
    const verify = async (manual) => {
      if (owner !== scope()) { if (mine) stopPoll(mine); return; }
      if (checking) return; /* nunca empilha consultas se o servidor demora */
      checking = true; check.disabled = true;
      try { await load(true); } catch { /* o estado mostra o erro */ }
      checking = false; check.disabled = false;
      if (owner !== scope()) return;
      if (whatsappFacts().live === true) {
        stopPoll(mine); st.dataset.kind = "ok"; st.textContent = "O servidor confirmou a sessão. Pode fechar esta janela."; check.hidden = true; close.textContent = "Concluir"; close.className = "btn";
      } else if (manual) { st.dataset.kind = ""; st.textContent = "O servidor ainda não confirmou a sessão. Confira se escaneou o QR Code e tente de novo."; }
    };
    check.addEventListener("click", () => verify(true));
    close.addEventListener("click", () => dlg.close());
    dlg.addEventListener("close", () => { dialogs.delete(dlg); if (mine) stopPoll(mine); dlg.remove(); });
    dialogs.add(dlg); document.body.append(dlg); dlg.showModal(); close.focus();
    if (ok) {
      let n = 0;
      poll = mine = { timer: setInterval(async () => {
        if (++n > POLL_MAX) { stopPoll(mine); st.textContent = "O servidor não confirmou a sessão. Gere um novo QR Code e tente de novo."; st.dataset.kind = "err"; return; }
        await verify(false);
      }, POLL_MS) };
    }
  }

  /* ---------- etapas guiadas: derivadas só de fatos confirmados ---------- */
  function whatsappSteps(f) {
    const company = host.identity?.negocio?.nome || "este negócio";
    const rc = state.receipt, can = canManage();
    const has = (name) => !!adapters.whatsapp[name];
    const act = (name, label, primary = true) => ({ name: "whatsapp:" + name, label: has(name) ? label : label + " (indisponível)", disabled: !has(name) || !can, why: !has(name) ? "Aguardando API: a interface está pronta, falta a integração." : !can ? "Somente responsáveis pelo negócio." : "", run: () => runAdapter("whatsapp", name), primary });
    return [
      { id: "account", title: "Conta do negócio no servidor", state: f.configured === null ? "unknown" : f.configured ? "done" : "todo", help: "O servidor precisa reconhecer o WhatsApp de " + company + ". Isso é feito pelo responsável pelo servidor; não há botão para isso aqui." },
      { id: "channel", title: "Número vinculado e ativo", state: !state.catalog ? "unknown" : f.channels.some((c) => c.active) ? "done" : "todo", help: "Vincule o número que vai atender os clientes.", action: act("provision", "Provisionar número") },
      { id: "pair", title: "Aparelho pareado", state: f.live === null ? "unknown" : f.live ? "done" : "todo", help: "Mostre o QR Code e escaneie com o WhatsApp do número do negócio. Só vale quando o servidor confirmar a sessão.", action: act("pairingQr", "Mostrar QR Code") },
      { id: "receive", title: "Primeira mensagem recebida", state: !rc ? "unknown" : rc.message_count > 0 ? "done" : "todo", help: "Envie um “oi” de outro celular para o número e toque em Atualizar.", action: { name: "wa-refresh-step", label: "Atualizar estado", run: () => { notice = { text: "", kind: "" }; load(true); }, primary: true } },
      { id: "reply", title: "Respostas pela Caixa (opcional)", optional: true, state: f.sending === null ? "unknown" : f.sending ? "done" : "todo", help: "Respostas saem pela Caixa Unificada, sempre com confirmação humana.", action: { name: "wa-inbox-step", label: "Abrir Caixa Unificada", run: () => { location.hash = "#/caixa"; } } },
    ];
  }
  function instagramSteps(f) {
    const ig = window.SocialMEIInstagram, can = canManage();
    return [
      { id: "app", title: "Aplicativo da Meta no servidor", state: f.oauth === null ? "unknown" : f.oauth ? "done" : "todo", help: "O servidor precisa ter o aplicativo da Meta configurado. É feito pelo responsável pelo servidor." },
      { id: "auth", title: "Autorizar a conta do Instagram", state: f.status === null ? "unknown" : f.connected ? "done" : "todo", help: "Você será levado ao Instagram para autorizar e volta para cá. Use uma conta profissional.", action: f.oauth === true && !f.connected ? { name: "ig-connect-step", label: f.status === "expired" ? "Reconectar Instagram" : "Conectar Instagram", disabled: !can || !ig, why: !can ? "Somente responsáveis pelo negócio." : !ig ? "O conector do Instagram ainda está carregando." : "", run: () => { notice = { text: "Abrindo o Instagram para autorização…", kind: "" }; const t = ++busyTok; busy = "instagram:connect"; paint(); try { ig.connect(); } finally { setTimeout(() => { if (busyTok === t && busy === "instagram:connect") { busy = null; paint(); } }, 8000); } }, primary: true } : null },
      { id: "direct", title: "Direct chegando na Caixa", state: f.status === null ? "unknown" : f.connected && f.incoming ? "done" : "todo", help: "Depois de conectar, o servidor passa a receber o Direct deste perfil.", action: { name: "ig-inbox-step", label: "Abrir Caixa Unificada", run: () => { location.hash = "#/caixa"; } } },
      { id: "publish", title: "Publicação (opcional)", optional: true, state: f.status === null ? "unknown" : f.connected && f.publishing ? "done" : "todo", help: "Publicações sempre pedem revisão e confirmação na Divulgação." },
    ];
  }
  function stepList(steps) {
    const nextIdx = steps.findIndex((s) => !s.optional && s.state !== "done");
    const ol = node("ol", "sm-hub-steps");
    steps.forEach((s, i) => {
      const cur = i === nextIdx, li = node("li", "sm-hub-step sm-hub-step-" + (cur ? "current" : s.state));
      if (cur) li.setAttribute("aria-current", "step");
      const dot = node("span", "sm-hub-sdot"); dot.append(s.state === "done" ? svg(ICON.check, 14) : document.createTextNode(String(i + 1)));
      const body = node("div", "sm-hub-sbody");
      const t = node("div", "sm-hub-stitle"); t.append(node("span", "", s.title), s.state === "done" ? badge("ok", "Feito") : s.state === "unknown" ? badge("unknown", "Não verificado") : s.optional ? badge("off", "Opcional") : cur ? badge("partial", "Agora") : badge("off", "Pendente"));
      body.append(t);
      if (cur || s.state === "unknown") body.append(node("p", "sm-hub-detail", s.help));
      if (cur && s.action) {
        const a = s.action, b = button(a.label, { primary: a.primary, disabled: !!a.disabled, title: a.why || "", name: a.name, onClick: a.run });
        body.append(b);
        if (a.disabled && a.why) body.append(node("small", "sm-hub-detail", a.why));
      }
      li.append(dot, body); ol.append(li);
    });
    return { ol, next: nextIdx > -1 ? steps[nextIdx] : null, done: steps.filter((s) => !s.optional && s.state === "done").length, total: steps.filter((s) => !s.optional).length };
  }
  function track(stage) {
    const ol = node("ol", "sm-hub-track"); ol.setAttribute("aria-label", "Evolução do canal");
    const at = stage === "operational" ? 3 : stage === "connected" ? 2 : stage === "configured" ? 1 : 0;
    TRACK.forEach((k, i) => { const li = node("li", i < at ? "is-done" : i === at ? "is-now" : ""); li.append(node("span", "sm-hub-tdot"), node("span", "sm-hub-tl", STAGE[k])); if (i === at) li.setAttribute("aria-current", "true"); ol.append(li); });
    return ol;
  }
  function stagePill(stage) {
    const p = node("span", "sm-hub-stage sm-hub-stage-" + stage); p.append(node("span", "sm-hub-sd")); p.append(document.createTextNode(STAGE[stage]));
    p.title = STAGE_HINT[stage]; return p;
  }
  function issuesBlock(f) {
    if (!f.issues.length) return null;
    const d = node("div", "sm-hub-diag"); d.append(node("strong", "", "Diagnóstico · " + f.issues.length + (f.issues.length === 1 ? " ponto" : " pontos")));
    const ul = node("ul");
    for (const i of f.issues) { const li = node("li", "sm-hub-issue sm-hub-issue-" + i.level); li.append(svg(i.level === "info" ? ICON.info : ICON.alert, 18)); const t = node("div"); t.append(node("b", "", i.title), node("span", "sm-hub-detail", i.fix)); li.append(t); ul.append(li); }
    d.append(ul); return d;
  }
  function factRow(dl, k, v) { const r = node("div", "sm-hub-fact"); r.append(node("dt", "", k), node("dd", "", v)); dl.append(r); }

  function nextBanner(list, f) {
    const box = node("div", "sm-hub-next"); box.setAttribute("role", "status");
    if (f.stage === "operational" && !list.next) { box.dataset.kind = "ok"; box.append(svg(ICON.check, 20), node("div", "", "Tudo certo: este canal está recebendo mensagens e foi confirmado pelo servidor.")); }
    else if (list.next) {
      box.dataset.kind = f.stage === "error" ? "err" : "todo";
      const t = node("div"); t.append(node("span", "sm-hub-nl", "Próximo passo · " + (list.done + 1 > list.total ? list.total : list.done + 1) + " de " + list.total), node("b", "", list.next.title)); box.append(t);
    } else { box.dataset.kind = "ok"; box.append(svg(ICON.check, 20), node("div", "", "Etapas obrigatórias concluídas.")); }
    return box;
  }

  const PERMS = [["instagram_business_basic", "Perfil básico"], ["instagram_business_manage_messages", "Mensagens (Direct)"], ["instagram_business_content_publish", "Publicação de conteúdo"], ["instagram_business_manage_comments", "Comentários"]];
  /* ---------- cartões compactos + painel lateral (v7.6.1) ---------- */
  const dstate = { channel: null, tab: "geral" };
  let drawer = null;
  const CHNAME = { whatsapp: "WhatsApp", instagram: "Instagram" };
  const factsOf = (ch) => (ch === "whatsapp" ? whatsappFacts() : instagramFacts());
  const stepsOf = (ch, f) => stepList(ch === "whatsapp" ? whatsappSteps(f) : instagramSteps(f));
  const refreshNow = () => { notice = { text: "", kind: "" }; load(true); };
  const closeDrawer = () => { try { drawer?.close(); } catch { /* já fechado */ } };

  function headline(ch, f, list) {
    if (f.stage === "operational" && !list.next) return ch === "whatsapp" ? "Recebendo mensagens, confirmado pelo servidor." : "Recebendo Direct, confirmado pelo servidor.";
    if (f.stage === "error") return STAGE_HINT.error; /* o motivo aparece no aviso logo abaixo */
    if (list.next) return "Próximo passo: " + list.next.title;
    return STAGE_HINT[f.stage];
  }
  function metaChips(ch, f) {
    const rc = state.receipt, out = [];
    if (ch === "whatsapp") {
      out.push(["Mensagens", rc ? (rc.message_count ? rc.message_count + " em " + rc.conversation_count + " conversa(s)" : "Nenhuma ainda") : "—"]);
      out.push(["Sessão", f.live === null ? "Não verificada" : f.live ? "Confirmada" : "Não confirmada"]);
      out.push(["Respostas", f.sending === null ? "Não verificado" : f.sending ? "Habilitadas" : "Indisponíveis"]);
    } else {
      out.push(["Perfil", state.igAccount ? "@" + state.igAccount.username : "Não confirmado"]);
      out.push(["Direct", f.connected ? (f.incoming ? "Recebendo" : "Desligado no servidor") : "Inativo"]);
      out.push(["Publicação", f.connected ? (f.publishing ? "Habilitada" : "Desativada") : "Inativa"]);
    }
    const ul = node("ul", "sm-hub-meta");
    for (const [k, v] of out) { const li = node("li"); li.append(node("span", "", k), node("b", "", v)); ul.append(li); }
    return ul;
  }
  const iconBtn = (name, label, icon, onClick) => {
    const b = button("", { name, icon, onClick }); b.classList.add("sm-hub-icon"); b.setAttribute("aria-label", label); b.title = label; return b;
  };
  const igConnectLabel = (f) => (f.status === "expired" ? "Reconectar Instagram" : "Conectar Instagram");
  const openMedia = () => window.SocialMEIInstagramMedia?.open();

  function channelCard(ch) {
    const f = factsOf(ch), list = stepsOf(ch, f), ig = window.SocialMEIInstagram;
    const card = node("article", "sm-hub-card"); card.dataset.hubChannel = ch; card.dataset.stage = f.stage;
    const head = node("div", "sm-hub-head");
    const ic = node("span", "sm-hub-ic sm-hub-ic-" + ch); ic.append(svg(ICON[ch], 22));
    const tt = node("div", "sm-hub-htxt"); tt.append(node("h3", "", CHNAME[ch]));
    head.append(ic, tt, stagePill(f.stage));
    card.append(head, node("p", "sm-hub-headline", headline(ch, f, list)), track(f.stage), metaChips(ch, f));
    if (f.issues.length) {
      const a = node("button", "sm-hub-alert"); a.type = "button"; a.dataset.hubAction = ch + ":alert"; a.title = "Ver o diagnóstico completo";
      a.append(svg(ICON.alert, 16), node("span", "", f.issues[0].title + (f.issues.length > 1 ? " · +" + (f.issues.length - 1) : "")));
      a.addEventListener("click", () => openDrawer(ch, "geral"));
      card.append(a);
    }
    const act = node("div", "sm-hub-actions");
    const showConnect = ch === "instagram" && f.oauth === true && !f.connected;
    if (showConnect) act.append(button(igConnectLabel(f), { primary: true, name: "ig-connect", disabled: !(canManage() && ig), title: canManage() ? "" : "Somente responsáveis pelo negócio.", onClick: () => ig.connect() }));
    act.append(button(ch === "whatsapp" ? (f.operational ? "Detalhes" : "Configurar") : "Detalhes", { primary: !showConnect && f.stage !== "operational", name: ch + "-open", onClick: () => openDrawer(ch, "geral") }));
    if (ch === "whatsapp") act.append(button("Catálogo e menu", { name: "wa-catalog", onClick: () => openDrawer("whatsapp", "catalogo") }));
    else if (f.connected) act.append(button("Publicações", { name: "ig-media", disabled: !window.SocialMEIInstagramMedia, onClick: openMedia }));
    act.append(iconBtn(ch + "-refresh", "Atualizar " + CHNAME[ch], "refresh", refreshNow));
    card.append(act);
    return card;
  }
  /* n8n: sem contrato de conexão neste app — só informa, nunca simula. */
  function n8nCard() {
    const card = node("article", "sm-hub-card sm-hub-card-quiet"); card.dataset.hubChannel = "n8n"; card.dataset.stage = "unknown";
    const head = node("div", "sm-hub-head");
    const ic = node("span", "sm-hub-ic sm-hub-ic-n8n"); ic.append(svg("M13 2L4 14h7l-1 8 9-12h-7z", 22));
    const tt = node("div", "sm-hub-htxt"); tt.append(node("h3", "", "Automações (n8n)"), node("span", "sm-hub-detail", "Esta tela não conecta o n8n. O acesso do menu ao catálogo é preparado no WhatsApp, em Catálogo e menu."));
    const p = node("span", "sm-hub-stage sm-hub-stage-unknown"); p.append(node("span", "sm-hub-sd"), document.createTextNode("Indisponível"));
    head.append(ic, tt, p); card.append(head);
    return card;
  }

  function factsList(ch, f) {
    const dl = node("dl", "sm-hub-facts"), rc = state.receipt;
    if (ch === "whatsapp") {
      factRow(dl, "Última mensagem recebida", rc ? (rc.message_count && rc.last_persisted_at ? new Date(rc.last_persisted_at).toLocaleString("pt-BR") + " (" + ago(Date.parse(rc.last_persisted_at)) + ")" : "Nenhuma ainda") : "Não consultada");
      factRow(dl, "Volume", rc ? rc.message_count + " mensagem(ns) em " + rc.conversation_count + " conversa(s)" : "—");
      factRow(dl, "Sessão ao vivo", f.live === null ? "Não verificada" : f.live ? "Confirmada pelo servidor" : "Não confirmada");
      factRow(dl, "Respostas pelo painel", f.sending === null ? "Não verificado" : f.sending ? "Habilitadas (com confirmação humana)" : "Indisponíveis");
    } else {
      factRow(dl, "Perfil conectado", state.igAccount ? "@" + state.igAccount.username + " (confirmado pelo servidor)" : "Não confirmado");
      factRow(dl, "Direct", f.connected ? (f.incoming ? "Recebendo" : "Recebimento desligado no servidor") : "Inativo");
      factRow(dl, "Respostas pelo painel", f.sending ? "Habilitadas (com confirmação humana)" : "Desativadas");
      factRow(dl, "Publicação", f.publishing ? "Habilitada" : "Desativada");
      factRow(dl, "Última mensagem", "A API não informa a data da última mensagem do Instagram");
    }
    return dl;
  }

  function geralPanel(ch, f, list) {
    const box = node("div", "sm-hub-dbody"), act = node("div", "sm-hub-actions"), ig = window.SocialMEIInstagram;
    if (ch === "whatsapp") {
      act.append(button("Atualizar estado", { primary: true, name: "wa-refresh", icon: "refresh", onClick: refreshNow }), button("Abrir Caixa Unificada", { name: "wa-inbox", onClick: () => { closeDrawer(); location.hash = "#/caixa"; } }));
    } else {
      const showConnect = f.oauth === true && !f.connected, may = canManage() && !!ig;
      if (showConnect) act.append(button(igConnectLabel(f), { primary: true, name: "ig-connect", disabled: !may, title: canManage() ? "" : "Somente responsáveis pelo negócio.", onClick: () => ig.connect() }));
      if (f.connected && f.renew) act.append(button("Renovar credencial", { name: "ig-renew", disabled: !may, onClick: () => ig.renew() }));
      act.append(button("Consultar novamente", { primary: !showConnect && !(f.connected && f.renew), name: "ig-refresh", icon: "refresh", onClick: refreshNow }));
      if (f.connected) act.append(button("Ver publicações", { name: "ig-media", disabled: !window.SocialMEIInstagramMedia, onClick: openMedia }));
      act.append(button("Abrir Caixa Unificada", { name: "ig-inbox", onClick: () => { closeDrawer(); location.hash = "#/caixa"; } }));
    }
    box.append(act);
    if (!list.next) box.append(nextBanner(list, f)); /* com etapa pendente, o passo a passo já destaca o próximo passo */
    const iss = issuesBlock(f); if (iss) box.append(iss);
    const steps = node("section", "sm-hub-dsec"); steps.append(node("h4", "", "Passo a passo · " + list.done + " de " + list.total + " concluídos"), list.ol);
    box.append(steps, factsList(ch, f));
    return box;
  }
  function tecnicoPanel(ch, f) {
    const box = node("div", "sm-hub-dbody");
    box.append(actionRows(ch, canManage() && (ch === "whatsapp" || f.connected)));
    const ul = node("ul", "sm-hub-levels"), company = host.identity?.negocio;
    if (ch === "whatsapp") {
      if (f.channels.length) {
        const list = node("ul", "sm-hub-channels");
        for (const c of f.channels) list.append(node("li", "", (c.name || c.instance || "Canal") + " · " + (c.active ? "ativo" : "inativo") + " · " + (c.enabled ? "catálogo autorizado" : "sem acesso ao catálogo")));
        box.append(list);
      }
      const [k1, t1] = yn(f.configured, "Configurada no servidor", "Não configurada");
      ul.append(level("1 · Conta configurada", k1, t1, "Empresa: " + (company?.nome || "—") + " (#" + (company?.id ?? "—") + ")" + (state.catalog ? " · " + f.channels.length + " canal(is) cadastrado(s)" : "")));
      const [k2, t2] = yn(f.live, "Verificada ao vivo", "Não verificada");
      ul.append(level("2 · Sessão conectada", k2, t2, f.live === true ? "O servidor confirmou a sessão agora." : "Só é considerada conectada quando o servidor confirma a sessão ao vivo."));
      ul.append(level("3 · Canal operacional", f.operational ? "ok" : f.configured === null ? "unknown" : "off", f.operational ? "Recebendo" : "Não confirmado", f.receiving === null ? "" : f.receiving ? "Recebimento configurado." : "Recebimento não configurado."));
      box.append(ul);
    } else {
      const authText = f.status === "connected" ? (f.connected ? "Autenticado" : "Credencial indisponível") : f.status === "expired" ? "Credencial expirada" : f.status === "disconnected" ? "Não conectado" : "Não verificado";
      const authKind = f.connected ? "ok" : f.status === "expired" || (f.status === "connected" && !f.connected) ? "err" : f.status ? "off" : "unknown";
      ul.append(level("Autenticação", authKind, authText, f.oauth === false ? "Aplicativo Meta não configurado no servidor." : ""));
      ul.append(level("Perfil conectado", state.igAccount ? "ok" : "unknown", state.igAccount ? "@" + state.igAccount.username : "Não confirmado", state.igAccount ? "Confirmado pelo servidor." : "O perfil só é exibido quando o servidor o confirma (exige conexão ativa e publicação habilitada)."));
      box.append(ul);
      const perms = node("div", "sm-hub-perms"); perms.append(node("strong", "", "Permissões solicitadas na autorização"));
      const pl = node("ul"); PERMS.forEach(([, label]) => pl.append(node("li", "", label))); perms.append(pl);
      perms.append(node("p", "sm-hub-detail", "A Meta decide o que foi concedido; esta tela não lê as permissões concedidas."));
      box.append(perms);
    }
    return box;
  }

  /* O catálogo e a prévia do menu são montados por v22-whatsapp-catalog.js (uma única instância, dentro do slot
     oculto da página). O painel só os move para as abas e os devolve ao slot ao fechar: nada é recriado. */
  function parkCatalog() {
    const slot = document.querySelector("[data-wa-catalog-slot]"), sec = document.querySelector("[data-wa-catalog]"), prev = document.querySelector("[data-wa-bot-preview]");
    if (slot && sec) { if (sec.parentNode !== slot) slot.append(sec); if (prev && prev.parentNode !== sec) sec.append(prev); }
  }
  function placeCatalog() {
    if (!drawer || dstate.channel !== "whatsapp") return;
    const catP = drawer.querySelector('[data-panel="catalogo"]'), menuP = drawer.querySelector('[data-panel="menu"]');
    const sec = document.querySelector("[data-wa-catalog]"), prev = document.querySelector("[data-wa-bot-preview]");
    if (!sec) {
      if (!catP.dataset.empty) {
        catP.dataset.empty = "1";
        catP.replaceChildren(node("p", "sm-hub-detail", canManage() ? "Carregando o catálogo…" : "Somente responsáveis pelo negócio podem gerenciar o acesso ao catálogo."));
        if (!canManage()) menuP.append(node("p", "sm-hub-detail", "A prévia do menu fica disponível para os responsáveis pelo negócio."));
      }
      return;
    }
    if (catP.dataset.empty) { delete catP.dataset.empty; catP.replaceChildren(); }
    if (sec.parentNode !== catP) catP.append(sec);
    if (prev && prev.parentNode !== menuP) menuP.append(prev);
    if (dstate.tab === "catalogo" && !sec.__smLoaded) { sec.__smLoaded = true; sec.__smLoad?.(); } /* consulta só quando a aba é aberta */
  }

  function buildDrawer(ch) {
    parkCatalog();
    drawer.replaceChildren();
    drawer.dataset.channel = ch;
    const head = node("header", "sm-drawer-head");
    const ic = node("span", "sm-hub-ic sm-hub-ic-" + ch); ic.append(svg(ICON[ch], 22));
    const tt = node("div", "sm-hub-htxt"); const h = node("h2", "", CHNAME[ch]); h.id = "sm-drawer-t";
    tt.append(h, node("span", "sm-hub-detail", "Negócio ativo: " + (host.identity?.negocio?.nome || "—") + " · #" + (workspace() ?? "—")));
    const pill = node("span", "sm-drawer-pill"); pill.dataset.drawerPill = "true";
    const x = node("button", "btn o sm-hub-icon", ""); x.type = "button"; x.append(svg("M6 6l12 12M18 6L6 18", 18)); x.setAttribute("aria-label", "Fechar"); x.title = "Fechar"; x.addEventListener("click", closeDrawer);
    head.append(ic, tt, pill, x);
    const tabs = ch === "whatsapp" ? [["geral", "Visão geral"], ["catalogo", "Catálogo"], ["menu", "Menu automático"], ["tecnico", "Técnico"]] : [["geral", "Visão geral"], ["tecnico", "Técnico"]];
    const bar = node("div", "sm-drawer-tabs"); bar.setAttribute("role", "tablist"); bar.setAttribute("aria-label", "Seções de " + CHNAME[ch]);
    const body = node("div", "sm-drawer-body");
    for (const [key, label] of tabs) {
      const t = node("button", "sm-drawer-tab", label); t.type = "button"; t.id = "sm-dt-" + key; t.setAttribute("role", "tab"); t.setAttribute("aria-controls", "sm-dp-" + key); t.dataset.tab = key;
      t.addEventListener("click", () => { dstate.tab = key; paintDrawer(); });
      t.addEventListener("keydown", (e) => {
        const ks = [...bar.querySelectorAll("[role=tab]")], i = ks.indexOf(t);
        const to = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? ks.length - 1 : null;
        if (to === null) return; e.preventDefault(); const n = ks[(to + ks.length) % ks.length]; dstate.tab = n.dataset.tab; paintDrawer(); n.focus();
      });
      bar.append(t);
      const p = node("section", "sm-drawer-panel"); p.id = "sm-dp-" + key; p.dataset.panel = key; p.setAttribute("role", "tabpanel"); p.setAttribute("aria-labelledby", "sm-dt-" + key);
      body.append(p);
    }
    if (ch === "whatsapp") {
      body.querySelector('[data-panel="menu"]').append(node("p", "sm-hub-detail", "Atendimento humano: em cada conversa da Caixa Unificada, pause ou retome o menu automático. O estado aparece no painel da própria conversa."));
    }
    drawer.append(head, bar, body);
  }
  function paintDrawer() {
    if (!drawer || !dstate.channel) return;
    const ch = dstate.channel;
    if (drawer.dataset.channel !== ch) buildDrawer(ch);
    const f = factsOf(ch), list = stepsOf(ch, f);
    const act = document.activeElement, keep = drawer.contains(act) ? act.dataset?.hubAction : null;
    const tabKeys = [...drawer.querySelectorAll("[role=tab]")].map((t) => t.dataset.tab);
    if (!tabKeys.includes(dstate.tab)) dstate.tab = "geral";
    drawer.querySelectorAll("[role=tab]").forEach((t) => { const on = t.dataset.tab === dstate.tab; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; });
    drawer.querySelectorAll("[role=tabpanel]").forEach((p) => { p.hidden = p.dataset.panel !== dstate.tab; });
    drawer.querySelector("[data-drawer-pill]").replaceChildren(stagePill(f.stage));
    drawer.setAttribute("aria-busy", String(!!busy));
    drawer.querySelector('[data-panel="geral"]').replaceChildren(geralPanel(ch, f, list));
    drawer.querySelector('[data-panel="tecnico"]').replaceChildren(tecnicoPanel(ch, f));
    placeCatalog();
    if (keep) drawer.querySelector('[data-hub-action="' + keep + '"]')?.focus({ preventScroll: true });
  }
  function openDrawer(ch, tab) {
    dstate.channel = ch; dstate.tab = tab || "geral";
    if (!drawer?.isConnected) {
      if (drawer) dialogs.delete(drawer);
      drawer = node("dialog", "sm-drawer"); drawer.setAttribute("aria-labelledby", "sm-drawer-t");
      const mine = drawer;
      drawer.addEventListener("click", (e) => { if (e.target === mine) mine.close(); }); /* clique no fundo fecha */
      drawer.addEventListener("close", () => { parkCatalog(); dialogs.delete(mine); mine.remove(); if (drawer === mine) { drawer = null; dstate.channel = null; } });
      dialogs.add(drawer);
      (document.querySelector("[data-conn-hub]") || document.body).append(drawer);
    }
    paintDrawer();
    if (!drawer.open) drawer.showModal();
  }

  function skeleton() {
    const wrap = node("div", "sm-hub-skel"); wrap.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 2; i++) { const c = node("div", "sm-hub-card sm-hub-sk"); c.append(node("i"), node("i"), node("i")); wrap.append(c); }
    return wrap;
  }
  function overview() {
    const company = host.identity?.negocio, wa = whatsappFacts(), ig = instagramFacts();
    const box = node("div", "sm-hub-over");
    const who = node("div", "sm-hub-company");
    const av = node("span", "sm-hub-av", (company?.nome || "?").trim().charAt(0).toUpperCase());
    const t = node("div"); t.append(node("b", "", company?.nome || "—"),
      node("span", "sm-hub-detail", "#" + (company?.id ?? "—") + " · " + (PAPEL[host.identity?.papel] || host.identity?.papel || "—") + (canManage() ? " · pode alterar conexões" : " · só visualização")));
    who.append(av, t);
    const known = state.ready || state.receipt || state.catalog;
    const ops = [wa, ig].filter((x) => x.stage === "operational").length;
    const sum = node("div", "sm-hub-sum"); sum.append(node("b", "", known ? ops + " de 2 canais operacionais" : "Canais não verificados"),
      node("span", "sm-hub-detail", state.at ? "Consultado às " + hhmm(state.at) + " · " + ago(state.at) + (Date.now() - state.at > OLD_MS ? " · dados antigos, atualize" : "") : "Ainda não consultado"));
    box.append(who, sum, button("Atualizar", { name: "hub-refresh-all", icon: "refresh", onClick: refreshNow }));
    return box;
  }

  function paint() {
    const root = document.querySelector("[data-conn-hub]");
    if (!root) return;
    if (state.owner !== scope()) { resetContext(); load(); }
    root.setAttribute("aria-busy", String(state.phase === "loading" || !!busy));
    root.dataset.workspace = String(workspace() ?? "");
    root.toggleAttribute("data-switching", !!notice.switching);
    const body = root.querySelector("[data-hub-body]");
    const status = root.querySelector("[data-hub-status]");
    status.textContent = notice.text || (state.phase === "loading" ? "Consultando o servidor…" : "");
    status.dataset.kind = notice.kind;
    const a = document.activeElement;
    const focused = root.contains(a) && !a.closest(".sm-drawer") ? a.dataset?.hubAction : null;
    root.querySelector("[data-hub-over]").replaceChildren(overview());
    const first = state.phase !== "ready" && !state.ready && !state.receipt && !state.catalog && !Object.keys(state.errors).length;
    body.replaceChildren(...(first ? [skeleton()] : [channelCard("whatsapp"), channelCard("instagram"), n8nCard()]));
    if (focused) { const sel = '[data-hub-action="' + focused + '"]'; (body.querySelector(sel) || root.querySelector("[data-hub-over] " + sel))?.focus({ preventScroll: true }); }
    paintDrawer();
  }

  let igTimer = null;
  function watchIg() { /* SocialMEIInstagram carrega depois: religa os botões dele quando chegar */
    if (window.SocialMEIInstagram || igTimer) return;
    let n = 0;
    igTimer = setInterval(() => { if (window.SocialMEIInstagram || ++n > 20) { clearInterval(igTimer); igTimer = null; paint(); } }, 500);
  }

  function mount(force = false) {
    if (!location.hash.startsWith("#/config/integracoes")) return;
    const view = document.getElementById("v");
    if (!view) return;
    if (view.querySelector("[data-conn-hub]")) { if (force) paint(); return; }
    const slot = view.querySelector("[data-cfg-int]");
    if (!slot) return; /* esta tela não tem o painel de Integrações: nada a montar (e nada é inserido fora dele) */
    const root = node("section", "sm-hub"); root.dataset.connHub = "true";
    root.setAttribute("aria-label", "Conexões do negócio");
    const over = node("div"); over.dataset.hubOver = "true";
    const status = node("p", "sm-hub-status"); status.dataset.hubStatus = "true"; status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    const body = node("div", "sm-hub-grid"); body.dataset.hubBody = "true";
    const legend = node("details", "sm-hub-legend");
    legend.append(node("summary", "", "Como ler os estados"), node("p", "sm-hub-detail", "Conta configurada, sessão conectada e canal operacional são níveis diferentes: só aparece como operacional o que o servidor confirmou. Nada aqui simula conexão."));
    root.append(over, status, body, legend);
    slot.querySelector("[data-cfg-int-wait]")?.remove();
    slot.prepend(root);
    paint();
    load();
    watchIg();
    if (dstate.channel) setTimeout(() => { if (root.isConnected && dstate.channel) openDrawer(dstate.channel, dstate.tab); }, 0); /* a tela foi remontada com o painel aberto */
  }
  window.addEventListener("hashchange", () => { if (!location.hash.startsWith("#/config/integracoes")) { closeDrawer(); dstate.channel = null; } });

  try { const prior = render; render = () => { prior(); syncScope(); mount(); }; } catch { /* sem hook: o hashchange abaixo cobre */ }
  window.addEventListener("hashchange", () => queueMicrotask(() => mount()));
  document.addEventListener("socialmei-data-change", syncScope);
  setInterval(syncScope, 500); /* a troca pode não emitir evento: comparação barata de texto, só age se o contexto mudou */
  window.SocialMEIConnections = { register, refresh: () => load(true), facts: { whatsapp: whatsappFacts, instagram: instagramFacts }, get snapshot() { return { ...state }; }, adapters: Object.freeze(Object.fromEntries(Object.entries(SLOTS).map(([k, v]) => [k, Object.keys(v)]))) };
  queueMicrotask(() => mount());
})();
