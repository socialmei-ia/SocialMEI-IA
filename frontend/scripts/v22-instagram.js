/* Real Instagram connection controls. Native V22 layout and motion stay unchanged. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInstagram) return;
  const state = {
    phase: "loading",
    oauth: false,
    incoming: false,
    connected: false,
    renewAvailable: false,
  };
  let pending = null,
    busy = false;
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
      return state.incoming
        ? "Conta conectada. Recebimento habilitado no servidor; valide um Direct de teste. Publicação pelo site ainda não habilitada."
        : "Conta conectada. Recebimento de Direct e publicação pelo site ainda precisam ser habilitados.";
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
        else if (button.dataset.igAction === "renew") renew();
        else if (button.dataset.igAction === "refresh") refresh().then(details);
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
    const owner = scope();
    pending = (async () => {
      try {
        const ready = await host.request("/integrations/readiness");
        if (ready?.source !== "server" || typeof ready.instagram?.oauth_available !== "boolean")
          throw Error("Invalid readiness");
        let connected = false;
        if (ready.instagram.oauth_available) {
          const connection = await host.request("/instagram/meta/status");
          if (!["connected", "disconnected", "expired"].includes(connection?.status))
            throw Error("Invalid connection");
          connected = connection.status === "connected" && connection.credential_available === true;
        }
        if (scope() !== owner) throw Error("Identity changed");
        Object.assign(state, {
          phase: "ready",
          oauth: ready.instagram.oauth_available,
          incoming: ready.instagram.incoming_available === true,
          renewAvailable: ready.instagram.token_refresh_available === true,
          connected,
        });
      } catch {
        Object.assign(state, {
          phase: "error",
          oauth: false,
          incoming: false,
          connected: false,
          renewAvailable: false,
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
  async function connect() {
    if (busy) return;
    busy = true;
    paintAll();
    let phase = "readiness";
    try {
      await refresh();
      if (!state.oauth || state.phase !== "ready") return details();
      phase = "permission";
      if (!["owner", "admin"].includes(host.identity?.papel))
        throw Error("Somente responsáveis pelo negócio podem conectar a conta.");
      phase = "request";
      const value = await host.request("/instagram/meta/oauth/start", "POST", {});
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
      paintAll();
    }
  }
  async function renew() {
    if (busy) return;
    busy = true;
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
      details();
      toast("Credencial do Instagram renovada. Confira a validade na conexão.");
    } catch (error) {
      const code =
        Number.isInteger(error?.status) && error.status >= 400 && error.status <= 599
          ? "HTTP " + error.status
          : "IG_REFRESH";
      details(code, "renew");
    } finally {
      busy = false;
      paintAll();
    }
  }
  function details(errorCode, operation) {
    const canConnect =
      state.phase === "ready" &&
      state.oauth &&
      !state.connected &&
      ["owner", "admin"].includes(host.identity?.papel);
    const canRenew =
      state.connected &&
      state.renewAvailable &&
      state.phase === "ready" &&
      ["owner", "admin"].includes(host.identity?.papel);
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
      }${
        canConnect
          ? '<button type="button" class="btn" data-ig-action="connect">Conectar Instagram</button>'
          : ""
      }${
        canRenew
          ? '<button type="button" class="btn" data-ig-action="renew">Renovar credencial</button><p class="m sm">A renovação exige token válido emitido há pelo menos 24 horas. Não ativa publicações ou respostas.</p>'
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
      refresh().then(details);
    },
    true,
  );
  const previousRender = render;
  render = () => {
    previousRender();
    paintAll();
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
  refresh().then(() => {
    if (callbackOutcome) {
      details();
      if (callbackOutcome === "failed")
        toast("A última autorização não foi concluída. Confira a situação acima.");
    }
  });
})();
