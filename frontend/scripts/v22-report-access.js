/* V22 workspace report collaborators (only existing registered accounts). */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIReportAccess) return;
  const owner = () => ["owner", "admin"].includes(host.identity?.papel);
  const style = document.createElement("style");
  style.textContent =
    ".sm-collab{margin:18px 0;padding:18px;border:1px solid var(--b);border-radius:16px;background:var(--w);color:var(--t)}" +
    ".sm-collab h2{font-size:20px;margin:0 0 8px}.sm-collab p{margin:8px 0;color:var(--m)}" +
    ".sm-collab .sm-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}" +
    ".sm-collab input,.sm-collab select{height:44px;border-radius:10px;border:1px solid var(--b);padding:10px;background:var(--w);color:var(--t);font:inherit}" +
    ".sm-collab button{height:44px;border:1px solid var(--b);border-radius:10px;background:var(--pl);color:var(--t);padding:8px 14px;cursor:pointer}";
  document.head.append(style);
  const element = (type, value) => {
    const node = document.createElement(type);
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  function status(panel) {
    const node = element("p");
    node.setAttribute("role", "status");
    node.setAttribute("aria-live", "polite");
    panel.append(node);
    return node;
  }
  async function mountWorkspace(view) {
    if (view.querySelector('[data-sm-switch]')) return;
    const panel = element("section");
    panel.className = "sm-collab";
    panel.dataset.smSwitch = "true";
    panel.append(element("h2", "Acessar outro negócio"));
    const description = element("p", "Alterar negócio só é permitido para contas às quais você já tem acesso.");
    const message = status(panel);
    const controls = element("div");
    controls.className = "sm-actions";
    const select = element("select");
    select.setAttribute("aria-label", "Escolher negócio");
    const change = element("button", "Trocar de negócio");
    change.type = "button";
    controls.append(select, change);
    panel.insertBefore(description, message);
    panel.append(controls);
    view.append(panel);
    try {
      const data = await host.request("/auth/workspaces");
      if (!panel.isConnected) return;
      select.replaceChildren();
      for (const item of data.items) {
        const option = element("option", item.nome + " (" + item.role + ")");
        option.value = item.id;
        option.selected = item.id === data.active_workspace_id;
        select.append(option);
      }
      if (data.items.length < 2) {
        change.disabled = true;
        message.textContent = "Você tem acesso a apenas um negócio.";
      }
    } catch (error) {
      message.textContent = error.message || "Negócios indisponíveis.";
      change.disabled = true;
    }
    change.addEventListener("click", async () => {
      change.disabled = true;
      try {
        await host.request("/auth/workspaces/switch", "POST", {
          workspace_id: Number(select.value),
        });
        location.replace("/frontend/socialmei-app.html#/relatorios");
      } catch (error) {
        message.textContent = error.message || "Não foi possível trocar de negócio.";
        change.disabled = false;
      }
    });
  }
  async function mountViewers(view) {
    if (!owner() || view.querySelector('[data-sm-viewers]')) return;
    const panel = element("section");
    panel.className = "sm-collab";
    panel.dataset.smViewers = "true";
    panel.append(element("h2", "Visualizadores de relatórios"));
    panel.append(element("p", "Autorize alguém que já criou uma conta SocialMEI. Essa pessoa poderá consultar este negócio, mas não editar seus dados."));
    const message = status(panel);
    const controls = element("div");
    controls.className = "sm-actions";
    const email = element("input");
    email.type = "email";
    email.maxLength = 255;
    email.placeholder = "email@exemplo.com";
    email.setAttribute("aria-label", "E-mail da conta SocialMEI");
    const add = element("button", "Dar acesso de leitura");
    add.type = "button";
    controls.append(email, add);
    const list = element("ul");
    panel.append(controls, list);
    view.append(panel);
    const refresh = async () => {
      const data = await host.request("/reporting/access");
      if (!panel.isConnected) return;
      list.replaceChildren();
      if (!data.items.length) list.append(element("li", "Nenhum visualizador autorizado."));
      for (const entry of data.items) {
        const item = element("li");
        item.append(element("span", entry.nome + " — " + entry.email + " "));
        const remove = element("button", "Revogar");
        remove.type = "button";
        remove.addEventListener("click", async () => {
          if (!confirm("Revogar o acesso deste visualizador?")) return;
          remove.disabled = true;
          try {
            await host.request("/reporting/access/" + entry.id, "DELETE");
            message.textContent = "Acesso revogado.";
            await refresh();
          } catch (error) {
            message.textContent = error.message || "Falha ao revogar.";
            remove.disabled = false;
          }
        });
        item.append(remove);
        list.append(item);
      }
    };
    add.addEventListener("click", async () => {
      if (!email.validity.valid || !email.value.trim()) {
        message.textContent = "Informe um e-mail válido.";
        return;
      }
      add.disabled = true;
      try {
        const data = await host.request("/reporting/access", "POST", {
          email: email.value.trim(),
        });
        message.textContent = data.granted
          ? "Acesso de leitura concedido. A pessoa poderá trocar para este negócio."
          : "A conta já tem acesso ao negócio.";
        email.value = "";
        await refresh();
      } catch (error) {
        message.textContent = error.message || "Não foi possível autorizar.";
      } finally {
        add.disabled = false;
      }
    });
    refresh().catch((error) => {
      message.textContent = error.message || "Visualizadores indisponíveis.";
    });
  }
  function mount() {
    const view = document.getElementById("v");
    if (!view) return;
    if (location.hash.startsWith("#/config/conta")) mountWorkspace(view);
    if (location.hash.startsWith("#/relatorios")) mountViewers(view);
  }
  const previous = window.render;
  if (typeof previous === "function") {
    window.render = function (...args) {
      const result = previous.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  }
  window.SocialMEIReportAccess = { refresh: mount };
  queueMicrotask(mount);
  window.addEventListener("hashchange", () => queueMicrotask(mount));
})();
