/* Execute the unchanged V22 application only after the server identity is known. */
(async () => {
  const auth = window.SocialMEIAuth;
  await auth.ready;
  if (auth.remote && !auth.current) {
    if (!auth.problem && localStorage.getItem("socialmei-auth-browser-scope")) return;
    location.replace("/frontend/entrada.html" + (location.hash ? "#/entrar" : ""));
    return;
  }
  if (auth.remote) {
    if (location.pathname !== "/frontend/socialmei-app.html") {
      location.replace("/frontend/socialmei-app.html" + location.search + location.hash);
      return;
    }
    const prefix = `smei-v22-account:${auth.current.usuario.id}:${auth.current.negocio.id}:`;
    for (const method of ["getItem", "setItem", "removeItem"]) {
      const original = Storage.prototype[method];
      Storage.prototype[method] = function (key, ...args) {
        const mapped =
          this === localStorage &&
          /^smei(?:-|4_)/.test(String(key)) &&
          !String(key).startsWith("smei-v22-account:")
            ? prefix + key
            : key;
        return original.call(this, mapped, ...args);
      };
    }
  }
  document.getElementById("app").hidden = auth.remote;
  const original = document.getElementById("v22-native-source");
  const run = document.createElement("script");
  run.textContent = original.textContent;
  document.body.appendChild(run);
  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "scripts/v22-backend.js";
    script.onload = resolve;
    script.onerror = reject;
    document.body.appendChild(script);
  });
  await window.SocialMEIV22.ready;
  if (auth.remote) {
    const knowledge = document.createElement("script");
    knowledge.src = "scripts/v22-knowledge-reporting.js";
    knowledge.onerror = () => console.warn("Gestão de conhecimento indisponível.");
    document.body.appendChild(knowledge);
  }
  if (auth.remote) {
    const instagram = document.createElement("script");
    instagram.src = "scripts/v22-instagram.js";
    instagram.onerror = () => console.warn("Controles Instagram indisponíveis.");
    instagram.onload = () => {
      const publishing = document.createElement("script");
      publishing.src = "scripts/v22-instagram-publisher.js";
      publishing.onerror = () => console.warn("Publicação Instagram indisponível.");
      document.body.appendChild(publishing);
    };
    document.body.appendChild(instagram);
  }
  if (!auth.remote) {
    const profile = document.createElement("script");
    profile.src = "scripts/app-perfil.js";
    document.body.appendChild(profile);
  }
})().catch(() => {
  document.getElementById("app").textContent =
    "Não foi possível carregar sua sessão. Atualize a página para tentar novamente.";
});
