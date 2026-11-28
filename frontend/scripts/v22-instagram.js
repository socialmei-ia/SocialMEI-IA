/* Real Instagram connection controls. Native V22 layout and motion stay unchanged. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInstagram) return;
  const state = {
    phase: "loading",
    oauth: false,
    incoming: false,
    sending: false,
    publishing: false,
    connected: false,
    renewAvailable: false,
    expired: false,
  };
  let pending = null,
    busy = false,
    busyKind = null,
    started = false,
    igDlg = null,
    view = {};
  /* v7.6.1: sem linha "Instagram" para pintar, não consulta sozinho (connect/renew/refresh continuam consultando sob demanda) */
  const wantsRows = () => [...document.querySelectorAll(".sw, #cg .cn")].some((row) => row.querySelector("b")?.textContent.trim() === "Instagram");
  const ensure = () => { if (!started && wantsRows()) refresh(); };
  const bound = new WeakSet(),
    frames = new WeakSet();
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const text = (element, value) => {
    if (!element || element.textContent === value) return;
    if (element.matches(".st2")) {
      const current = [...element.childNodes].find((node) => node.nodeType === Node.TEXT_NODE);
      if (current) current.textContent = value;
      else element.appendChild(element.ownerDocument.createTextNode(value));
    } else element.textContent = value;
  };
  function label() {
    if (state.phase === "loading") return "Consultando…";
    if (state.phase === "error") return "Indisponível";
    if (!state.oauth) return "Não configurado";
    return state.connected ? "Conectado" : "Não conectado";
  }
  function description() {
    if (state.connected)
      return (
        "Conta conectada. " +
        (state.incoming
          ? "Recebimento de Direct habilitado no servidor. "
          : "Recebimento de Direct desativado. ") +
        (state.sending
          ? "Respostas pelo painel habilitadas; exigem confirmação. "
          : "Respostas pelo painel desativadas. ") +
        (state.publishing
          ? "Publicações pelo site habilitadas; exigem revisão e confirmação."
          : "Publicações pelo site desativadas.")
      );
    if (state.phase === "error")
      return "Não foi possível confirmar a conexão. Confira a sessão e consulte novamente.";
    return state.oauth
      ? "Autorize o Instagram para vincular uma conta profissional a este negócio. Nenhuma mensagem será enviada."
      : "A conexão depende da configuração segura do aplicativo Meta no servidor. Nenhuma conta foi conectada.";
  }
  function paint(doc) {
    const rows = [...doc.querySelectorAll(".sw, #cg .cn")];
    for (const row of rows) {
      if (row.querySelector("b")?.textContent.trim() !== "Instagram") continue;
      const badge = row.querySelector(".chip, .st2");
      text(badge, label());
      if (badge?.matches(".chip")) {
        badge.classList.remove("c-ok", "c-wa", "c-mu", "c-er");
        badge.classList.add(state.connected ? "c-ok" : state.phase === "error" ? "c-er" : "c-mu");
      }
      if (badge?.matches(".st2")) {
        badge.classList.toggle("s-g", !state.connected);
        badge.classList.toggle("s-ok", state.connected);
      }
      if (row.matches(".cn")) text(row.querySelector("p"), description());
      const button = row.querySelector("button");
      if (!button) continue;
      button.dataset.igAction = state.oauth && !state.connected ? "connect" : "details";
      button.disabled = busy || state.phase === "loading";
      button.title = "Consultar ou conectar a conta deste negócio";
      text(
        button,
        state.connected ? "Ver conexão" : state.oauth ? "Conectar Instagram" : "Ver pendências",
      );
    }
    if (doc === document && S.cfg === "integracoes") {
      for (const note of doc.querySelectorAll(".fl > p.m.sm"))
        if (note.textContent.includes("Nenhuma integração está ativa."))
          text(
            note,
            "Conectar Instagram não ativa respostas automáticas nem publicações. Os demais canais dependem de configuração.",
          );
    }
  }
  function bind(doc) {
    if (!doc || bound.has(doc)) return;
    bound.add(doc);
    doc.addEventListener(
      "click",
      (event) => {
        const button = event.target.closest?.("[data-ig-action]");
        if (!button) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (busy) return;
        if (button.dataset.igAction === "connect") connect();
        else if (button.dataset.igAction === "authorize") connect(button.dataset.igScope);
        else if (button.dataset.igAction === "renew") renew();
        else if (button.dataset.igAction === "refresh") {
          const open = igDlg?.dlg.open;
          const p = refresh();
          if (open) renderDialog();
          p.then(() => details());
        }
        else details();
      },
      true,
    );
    const cards = doc.getElementById("cg");
    if (cards)
      new MutationObserver(() => paint(doc)).observe(cards, { childList: true, subtree: true });
  }
  function paintAll() {
    bind(document);
    paint(document);
    if (igDlg?.dlg.open) renderDialog();
    for (const frame of document.querySelectorAll("iframe")) {
      if (!frames.has(frame)) {
        frames.add(frame);
        frame.addEventListener("load", paintAll);
      }
      try {
        const doc = frame.contentDocument;
        if (doc?.getElementById("cg")) {
          bind(doc);
          paint(doc);
        }
      } catch {}
    }
  }
  async function refresh() {
    if (pending) return pending;
    started = true;
    const owner = scope();
    pending = (async () => {
      try {
        const ready = await host.request("/integrations/readiness");
        if (ready?.source !== "server" || typeof ready.instagram?.oauth_available !== "boolean")
          throw Error("Invalid readiness");
        let connected = false,
          connection_expired = false;
        if (ready.instagram.oauth_available) {
          const connection = await host.request("/instagram/meta/status");
          if (!["connected", "disconnected", "expired"].includes(connection?.status))
            throw Error("Invalid connection");
          connected = connection.status === "connected" && connection.credential_available === true;
          connection_expired = connection.status === "expired";
        }
        if (scope() !== owner) throw Error("Identity changed");
        Object.assign(state, {
          phase: "ready",
          oauth: ready.instagram.oauth_available,
          incoming: ready.instagram.incoming_available === true,
          sending: ready.instagram.send_enabled === true,
          publishing: ready.instagram.publishing_available === true,
          renewAvailable: ready.instagram.token_refresh_available === true,
          connected,
          expired: connection_expired,
        });
      } catch {
        Object.assign(state, {
          phase: "error",
          oauth: false,
          incoming: false,
          sending: false,
          publishing: false,
          connected: false,
          renewAvailable: false,
          expired: false,
        });
      } finally {
        pending = null;
        paintAll();
      }
      return { ...state };
    })();
    return pending;
  }
  function authorization(value) {
    if (typeof value?.authorization_url !== "string" || value.authorization_url.length > 8192)
      throw Error("URL de autorização inválida.");
    const url = new URL(value.authorization_url),
      keys = [...url.searchParams.keys()];
    const allowed = new Set([
      "client_id",
      "redirect_uri",
      "response_type",
      "scope",
      "force_reauth",
      "enable_fb_login",
      "state",
    ]);
    const scopes = new Set(url.searchParams.get("scope")?.split(",") || []);
    const permissions = new Set([
      "instagram_business_basic",
      "instagram_business_manage_messages",
      "instagram_business_content_publish",
      "instagram_business_manage_comments",
    ]);
    if (
      url.protocol !== "https:" ||
      !["instagram.com", "www.instagram.com"].includes(url.hostname) ||
      url.username ||
      url.password ||
      url.hash ||
      (url.port && url.port !== "443") ||
      url.pathname.replace(/\/$/, "") !== "/oauth/authorize" ||
      new Set(keys).size !== keys.length ||
      keys.some((key) => !allowed.has(key)) ||
      !/^\d+$/.test(url.searchParams.get("client_id") || "") ||
      url.searchParams.get("redirect_uri") !==
        location.origin + "/api/v1/instagram/meta/oauth/return" ||
      url.searchParams.get("response_type") !== "code" ||
      !/^[A-Za-z0-9_-]{32,160}$/.test(value.state || "") ||
      url.searchParams.get("state") !== value.state ||
      !scopes.has("instagram_business_basic") ||
      [...scopes].some((scope) => !permissions.has(scope))
    )
      throw Error("URL de autorização não permitida.");
    return url.href;
  }
  async function connect(confirmedScope) {
    if (busy) return;
    const startingScope = scope();
    busy = true;
    busyKind = "connect";
    paintAll();
    let phase = "readiness";
    try {
      await refresh();
      if (scope() !== startingScope) return;
      if (!state.oauth || state.phase !== "ready") return details();
      phase = "permission";
      if (!["owner", "admin"].includes(host.identity?.papel))
        throw Error("Somente responsáveis pelo negócio podem conectar a conta.");
      if (!confirmedScope) {
        info(
          "Vincular Instagram",
          `<p>Confirme o vínculo com <strong>${esc(host.identity.negocio.nome)}</strong>.</p><button type="button" class="btn" data-ig-action="authorize" data-ig-scope="${esc(startingScope)}">Confirmar negócio e autorizar</button>`,
        );
        return;
      }
      if (confirmedScope !== startingScope) return;
      phase = "request";
      const value = await host.request("/instagram/meta/oauth/start", "POST", {});
      if (scope() !== startingScope) return;
      phase = "validation";
      const url = authorization(value);
      phase = "navigation";
      location.assign(url);
    } catch (error) {
      const code =
        Number.isInteger(error?.status) && error.status >= 400 && error.status <= 599
          ? "HTTP " + error.status
          : {
              readiness: "IG_READINESS",
              permission: "IG_PERMISSION",
              request: "IG_REQUEST",
              validation: "IG_AUTH_URL",
              navigation: "IG_NAVIGATION",
            }[phase];
      details(code);
    } finally {
      busy = false;
      busyKind = null;
      paintAll();
    }
  }
  async function renew() {
    if (busy) return;
    busy = true;
    busyKind = "renew";
    paintAll();
    try {
      await refresh();
      if (!state.renewAvailable || !state.connected || state.phase !== "ready") {
        details("IG_REFRESH_UNAVAILABLE", "renew");
        return;
      }
      if (!["owner", "admin"].includes(host.identity?.papel)) {
        details("IG_PERMISSION", "renew");
        return;
      }
      const result = await host.request("/instagram/meta/connection/refresh-token", "POST", {});
      if (result?.status !== "refreshed") throw Error("Unexpected renewal response");
      await refresh();
      details(undefined, "renew", "renewed");
    } catch (error) {
      const code =
        Number.isInteger(error?.status) && error.status >= 400 && error.status <= 599
          ? "HTTP " + error.status
          : "IG_REFRESH";
      details(code, "renew");
    } finally {
      busy = false;
      busyKind = null;
      paintAll();
    }
  }
  /* Diálogo de conexão no padrão da Central de Conexões. Só reflete o que o servidor informou; não inventa estados. */
  const can = () => ["owner", "admin"].includes(host.identity?.papel);
  const stateTone = () =>
    state.phase === "loading" ? "busy" : state.phase === "error" || state.expired ? "err" : state.connected ? "ok" : state.oauth ? "info" : "warn";
  const stateLabel = () => (state.expired ? "Autorização expirada" : label());
  function track() {
    const items = [
      ["Aplicativo da Meta no servidor", state.phase !== "ready" ? "todo" : state.oauth ? "done" : "warn", state.oauth ? "Configurado." : "Falta o responsável pelo servidor configurar."],
      [
        "Conta profissional autorizada",
        state.expired ? "err" : state.connected ? "done" : "todo",
        state.connected ? "Autorizada para este negócio." : state.expired ? "A autorização expirou. Reconecte a conta." : "Você autoriza no Instagram e volta para cá.",
      ],
    ];
    const ol = document.createElement("ol");
    ol.className = "sm-igd-track";
    items.forEach(([title, st, help], i) => {
      const li = document.createElement("li");
      li.dataset.state = st;
      const dot = document.createElement("span");
      dot.className = "sm-igd-dot";
      dot.textContent = st === "done" ? "✓" : st === "err" || st === "warn" ? "!" : String(i + 1);
      const tx = document.createElement("div");
      const b = document.createElement("b");
      b.textContent = title;
      const p = document.createElement("span");
      p.textContent = help;
      tx.append(b, p);
      li.append(dot, tx);
      ol.append(li);
    });
    return ol;
  }
  function capabilities() {
    const wrap = document.createElement("ul");
    wrap.className = "sm-igd-caps";
    wrap.setAttribute("aria-label", "O que está habilitado no servidor");
    for (const [name, on] of [
      ["Receber Direct", state.incoming],
      ["Responder pelo painel", state.sending],
      ["Publicar pelo site", state.publishing],
    ]) {
      const li = document.createElement("li");
      li.dataset.on = String(!!on);
      li.textContent = name + " · " + (on ? "habilitado" : "desativado");
      wrap.append(li);
    }
    return wrap;
  }
  function renderDialog() {
    if (!igDlg) return;
    const ui = window.SocialMEIAtendimentoUI;
    const dlg = igDlg.dlg;
    const keep = document.activeElement?.dataset?.igAction;
    const working = busy || !!pending || state.phase === "loading";
    const body = document.createElement("div");
    body.className = "sm-dlg-body";
    const pill = document.createElement("span");
    pill.className = "sm-igd-pill";
    pill.dataset.tone = stateTone();
    pill.textContent = stateLabel();
    body.append(pill);
    if (state.phase === "ready") body.append(track());
    const desc = document.createElement("p");
    desc.className = "sm-igd-desc";
    desc.textContent = description();
    body.append(desc);
    if (state.connected && state.phase === "ready") body.append(capabilities());
    const live = document.createElement("div");
    live.className = "sm-igd-live";
    live.setAttribute("aria-live", "polite");
    if (working) {
      live.dataset.tone = "busy";
      live.append(
        ui.spinner(),
        document.createTextNode(
          " " +
            (busyKind === "connect"
              ? "Abrindo o Instagram para autorização…"
              : busyKind === "renew"
                ? "Renovando a credencial…"
                : "Consultando a conexão…"),
        ),
      );
    } else if (typeof view.errorCode === "string" && /^(HTTP [45][0-9]{2}|IG_[A-Z_]+)$/.test(view.errorCode)) {
      live.dataset.tone = "err";
      live.setAttribute("role", "alert");
      const t = document.createElement("b");
      t.textContent = view.operation === "renew" ? "Não foi possível renovar a credencial." : "Não foi possível iniciar a autorização.";
      const x = document.createElement("span");
      x.textContent = "Confira a sessão" + (view.operation === "renew" ? "" : " e a configuração com o responsável") + " e tente de novo.";
      const ref = document.createElement("small");
      ref.textContent = "Referência: " + view.errorCode;
      live.append(t, x, ref);
    } else if (view.ok === "callback_failed") {
      live.dataset.tone = "err";
      live.setAttribute("role", "alert");
      live.textContent = "A última autorização não foi concluída. Confira a situação acima e tente de novo.";
    } else if (view.ok === "renewed") {
      live.dataset.tone = "ok";
      live.textContent = "Credencial renovada pelo servidor. Isso não ativa publicações nem respostas.";
    }
    body.append(live);
    const foot = document.createElement("footer");
    foot.className = "sm-dlg-foot sm-igd-foot";
    const act = (text, name, cls) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = cls;
      b.dataset.igAction = name;
      b.textContent = text;
      b.disabled = working;
      return b;
    };
    const canConnect = state.phase === "ready" && state.oauth && !state.connected && can();
    const canRenew = state.connected && state.renewAvailable && state.phase === "ready" && can();
    if (canConnect) foot.append(act(state.expired ? "Reconectar Instagram" : "Conectar Instagram", "connect", "btn"));
    if (canRenew) foot.append(act("Renovar credencial", "renew", "btn"));
    foot.append(act("Consultar novamente", "refresh", canConnect || canRenew ? "btn o" : "btn"));
    const close = document.createElement("button");
    close.type = "button";
    close.className = "btn o";
    close.textContent = "Fechar";
    close.onclick = () => dlg.close();
    foot.append(close);
    if (state.phase === "ready" && !can() && !state.connected && state.oauth) {
      const n = document.createElement("p");
      n.className = "sm-igd-note";
      n.textContent = "Somente responsáveis pelo negócio podem conectar a conta.";
      body.append(n);
    }
    if (canRenew) {
      const n = document.createElement("p");
      n.className = "sm-igd-note";
      n.textContent = "A renovação exige token válido emitido há pelo menos 24 horas.";
      body.append(n);
    }
    const head = igDlg.inner.querySelector(".sm-dlg-head");
    igDlg.inner.replaceChildren(head, body, foot);
    const again = keep && foot.querySelector('[data-ig-action="' + keep + '"]:not(:disabled)');
    if (again) again.focus();
    else if (!dlg.contains(document.activeElement)) (foot.querySelector("button:not(:disabled)") || close).focus();
  }
  function details(errorCode, operation, ok) {
    const ui = window.SocialMEIAtendimentoUI;
    if (!ui) return legacyDetails(errorCode, operation);
    view = { errorCode, operation, ok };
    if (!igDlg?.dlg.isConnected) {
      const shell = ui.shell({ label: "Conexão do Instagram", cls: "sm-dlg-ig" });
      shell.inner.append(ui.header(shell, "link", "Conexão do Instagram", host.identity?.negocio?.nome || "", "info"));
      shell.dlg.addEventListener("close", () => {
        if (igDlg === shell) igDlg = null;
      });
      igDlg = shell;
      renderDialog();
      shell.show();
      shell.dlg.querySelector("[data-ig-action]:not(:disabled)")?.focus();
    } else renderDialog();
  }
  function legacyDetails(errorCode, operation) {
    const failureText =
      operation === "renew"
        ? "Não foi possível renovar a credencial. Confira a sessão e tente novamente."
        : "Não foi possível iniciar a autorização. Confira a sessão e a configuração com o responsável.";
    info(
      "Conexão Instagram",
      `<p>${label()}</p><p>${description()}</p>${
        typeof errorCode === "string" && /^(HTTP [45][0-9]{2}|IG_[A-Z_]+)$/.test(errorCode)
          ? '<p role="alert">' + failureText + "</p><p>Referência: " + errorCode + "</p>"
          : ""
      }<button type="button" class="btn o" data-ig-action="refresh">Consultar novamente</button>`,
    );
  }
  document.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest?.('[data-ig-action="refresh"]');
      if (!button) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const p = refresh();
      if (igDlg?.dlg.open) renderDialog();
      p.then(() => details());
    },
    true,
  );
  const previousRender = render;
  render = () => {
    previousRender();
    paintAll();
    ensure();
  };
  window.SocialMEIInstagram = {
    refresh,
    connect,
    renew,
    authorization,
    get status() {
      return { ...state };
    },
  };
  // Bootstrap consumes the callback fragment before the native router starts.
  // Use the one-time result only for a message, never as proof of a connection.
  const legacyReturn = /^#instagram=(connected|failed)$/.exec(location.hash);
  const callbackOutcome =
    legacyReturn?.[1] ||
    (["connected", "failed"].includes(window.__socialmeiInstagramCallbackOutcome)
      ? window.__socialmeiInstagramCallbackOutcome
      : null);
  delete window.__socialmeiInstagramCallbackOutcome;
  if (legacyReturn) go("/config/integracoes");
  paintAll();
  (callbackOutcome || wantsRows() ? refresh() : Promise.resolve()).then(() => {
    if (callbackOutcome) details(undefined, undefined, callbackOutcome === "failed" ? "callback_failed" : undefined);
  });
})();
