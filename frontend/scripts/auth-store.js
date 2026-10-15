/* Real accounts are opt-in; the public Pages demo keeps its local flow. */
const SocialMEIAuth = (() => {
  const config = SOCIALMEI_CONFIG.auth;
  const remote = !!config && config.mode !== "local";
  let current = null,
    problem = "",
    base = "";
  const scopeKey = "socialmei-auth-browser-scope";
  const archivePrefix = "socialmei-account-state-";
  const internal = (key) => key === scopeKey || key.startsWith(archivePrefix);
  const appKey = (key) => /^socialmei[-_]/i.test(key) && !internal(key);
  function bindBrowser(identity) {
    const next = identity ? `${identity.usuario.id}:${identity.negocio.id}` : "";
    const previous = localStorage.getItem(scopeKey) || "";
    if (next === previous) return false;
    const saved = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (appKey(key)) saved[key] = localStorage.getItem(key);
    }
    // Preserve local work before clearing a different account's presentation state.
    const previousArchive = archivePrefix + (previous || "legacy");
    if (previous || localStorage.getItem(previousArchive) === null)
      localStorage.setItem(previousArchive, JSON.stringify(saved));
    const restored = next ? JSON.parse(localStorage.getItem(archivePrefix + next) || "{}") : {};
    for (const key of Object.keys(saved)) localStorage.removeItem(key);
    for (const [key, value] of Object.entries(restored)) {
      if (appKey(key) && typeof value === "string") localStorage.setItem(key, value);
    }
    localStorage.setItem(scopeKey, next);
    for (const key of Object.keys(sessionStorage)) {
      if (/^socialmei[-_]/i.test(key)) sessionStorage.removeItem(key);
    }
    return true;
  }
  function identity(value) {
    if (
      !value ||
      !Number.isSafeInteger(value.usuario?.id) ||
      !Number.isSafeInteger(value.negocio?.id) ||
      typeof value.usuario.email !== "string" ||
      typeof value.negocio.slug !== "string" ||
      !/^[a-f0-9]{64}$/.test(value.csrf_token)
    )
      throw new Error("Resposta de autenticação inválida.");
    return value;
  }
  async function request(path, method = "GET", data) {
    if (!base) throw new Error(problem || "Autenticação não configurada.");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(base + path, {
        method,
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          "X-SocialMEI-Client": "browser",
          ...headers(),
          ...(data ? { "Content-Type": "application/json" } : {}),
        },
        body: data ? JSON.stringify(data) : undefined,
      });
      const body = response.status === 204 ? null : await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(
          typeof body?.detail === "string"
            ? body.detail
            : "Não foi possível concluir. Confira os dados e tente novamente.",
        );
        error.status = response.status;
        throw error;
      }
      return body;
    } finally {
      clearTimeout(timer);
    }
  }
  function headers() {
    return remote && current ? { "X-SocialMEI-CSRF": current.csrf_token } : {};
  }
  async function signIn(path, data) {
    const value = identity(await request(path, "POST", data));
    bindBrowser(value);
    location.reload();
    return value;
  }
  async function bootstrap() {
    try {
      if (config.mode !== "remote") throw new Error("Configuração de autenticação inválida.");
      const url = new URL(config.apiBaseUrl, location.href);
      if (
        url.origin !== location.origin ||
        url.pathname.replace(/\/$/, "") !== "/api/v1" ||
        url.search ||
        url.hash ||
        url.username ||
        url.password
      )
        throw new Error("A autenticação deve usar a API deste mesmo site.");
      base = url.href.replace(/\/$/, "");
      const session = await request("/auth/session");
      const value = session === null ? null : identity(session);
      if (bindBrowser(value)) {
        location.reload();
        return null;
      }
      current = value;
      return current;
    } catch (error) {
      problem = error.message;
      return null;
    }
  }
  const ready = remote ? bootstrap() : Promise.resolve(null);
  return {
    remote,
    ready,
    headers,
    request,
    internalStorageKey: internal,
    get current() {
      return current;
    },
    get problem() {
      return problem;
    },
    login: (data) => signIn("/auth/login", data),
    register: (data) => signIn("/auth/register", data),
    async saveProfile(data) {
      current = identity(await request("/auth/profile", "PATCH", data));
      return current;
    },
    async logout(destination) {
      if (destination !== undefined && destination !== "/frontend/socialmei-app.html")
        throw new Error("Destino de saída inválido.");
      try {
        await request("/auth/logout", "POST", {});
      } catch (error) {
        if (error.status !== 401) throw error;
      }
      current = null;
      try {
        bindBrowser(null);
      } catch (_) {
        // A revoked session must leave the app even if local storage cannot archive drafts.
        // Existing local work remains in place for the next verified bootstrap to handle.
        problem = "Você saiu. Confira o espaço do navegador antes de entrar novamente.";
      }
      if (destination) location.replace(destination);
      else location.reload();
    },
  };
})();
window.SocialMEIAuth = SocialMEIAuth;
