/* Presentation only: inbox widths and consecutive-message rhythm. */
(() => {
  const host = window.SocialMEIV22;
  if (!host || window.SocialMEIInboxLayout) return;
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "styles/v22-inbox-layout.css";
  document.head.append(style);
  const defaults = { list: 24, context: 23 };
  const key = () => {
    const identity = host.identity;
    return identity
      ? `socialmei-inbox-layout:${identity.usuario.id}:${identity.negocio.id}`
      : "socialmei-inbox-layout:demo";
  };
  function read() {
    try {
      const saved = JSON.parse(localStorage.getItem(key()));
      return Object.fromEntries(
        Object.entries(defaults).map(([name, fallback]) => [
          name,
          Number.isInteger(saved?.[name]) && saved[name] >= 20 && saved[name] <= 28
            ? saved[name]
            : fallback,
        ]),
      );
    } catch {
      return { ...defaults };
    }
  }
  function apply(shell, values) {
    for (const name of Object.keys(defaults))
      shell.style.setProperty(`--inbox-${name}-width`, `${values[name]}%`);
  }
  function group(shell) {
    shell
      .querySelectorAll(".inbox-message-grouped")
      .forEach((row) => row.classList.remove("inbox-message-grouped"));
    const id = /^#\/caixa\/([^/]+)$/.exec(location.hash)?.[1];
    const conversation = id && host.conversation?.(id);
    if (!conversation?.messages) return;
    const messages = [
      ...conversation.messages,
      ...(window.SocialMEIInstagramDirect?.confirmed(id) || []),
      ...(window.SocialMEIWhatsAppReplies?.confirmed(id) || []),
    ].sort((a, b) => new Date(a.occurred_at) - new Date(b.occurred_at));
    const rows = [...shell.querySelectorAll(".ms > div")].filter((row) =>
      row.querySelector(".mg .bb"),
    );
    if (rows.length !== messages.length) return;
    rows.forEach((row, index) => {
      const message = messages[index],
        previous = messages[index - 1];
      const gap = previous && new Date(message.occurred_at) - new Date(previous.occurred_at);
      const sameDay =
        previous &&
        new Date(message.occurred_at).toDateString() ===
          new Date(previous.occurred_at).toDateString();
      const grouped =
        previous &&
        sameDay &&
        gap >= 0 &&
        gap <= 300000 &&
        message.direction === previous.direction &&
        ["sender_id", "sender_ref", "author_id"].every(
          (name) => message[name] === previous[name],
        ) &&
        row.querySelector(".bb").textContent === message.text;
      row.classList.toggle("inbox-message-grouped", Boolean(grouped));
    });
  }
  function mount() {
    const shell = document.querySelector("#v .cv");
    if (!shell) return;
    shell.classList.add("inbox-layout");
    group(shell);
    if (shell.querySelector(".inbox-layout-settings")) return;
    const list = shell.querySelector(".cl");
    if (!list) return;
    const values = read();
    const scope = key(),
      identity = host.identity;
    const current = () => shell.isConnected && scope === key() && identity === host.identity;
    apply(shell, values);
    const settings = document.createElement("details");
    settings.className = "inbox-layout-settings";
    settings.innerHTML =
      '<summary>Ajustar colunas</summary><p class="m sm">Ajuste o espaço para ler as mensagens.</p>';
    for (const [name, label] of [
      ["list", "Conversas"],
      ["context", "Contexto do cliente"],
    ]) {
      const field = document.createElement("label");
      field.textContent = label;
      const input = document.createElement("input");
      input.type = "range";
      input.min = "20";
      input.max = "28";
      input.value = String(values[name]);
      input.setAttribute("aria-label", `Largura: ${label}`);
      input.oninput = () => {
        if (!current()) return;
        values[name] = Number(input.value);
        apply(shell, values);
      };
      input.onchange = () => {
        if (!current()) return;
        try {
          localStorage.setItem(scope, JSON.stringify(values));
        } catch {}
      };
      field.append(input);
      settings.append(field);
    }
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "lk";
    reset.textContent = "Restaurar larguras";
    reset.onclick = () => {
      if (!current()) return;
      Object.assign(values, defaults);
      apply(shell, values);
      settings
        .querySelectorAll("input")
        .forEach((input, index) => (input.value = String(Object.values(defaults)[index])));
      try {
        localStorage.removeItem(scope);
      } catch {}
    };
    settings.append(reset);
    list.querySelector(".row")?.after(settings);
  }
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      const result = render.apply(this, args);
      mount();
      return result;
    };
  window.SocialMEIInboxLayout = { refresh: mount };
  mount();
})();
