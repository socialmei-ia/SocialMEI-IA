/* One authenticated identity, separate business memberships and local drafts. */
(() => {
  const auth = window.SocialMEIAuth;
  if (!auth?.remote || window.SocialMEIBusinesses) return;
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "styles/v22-businesses.css";
  document.head.append(style);
  const scope = () => auth.current && `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  const el = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const draftKey = () => "socialmei-business-create:" + scope();
  function savedDraft() {
    try {
      const value = JSON.parse(sessionStorage.getItem(draftKey()) || "null");
      return value &&
        typeof value.nome === "string" &&
        typeof value.segmento === "string" &&
        /^[a-f0-9-]{36}$/i.test(value.idempotency_key)
        ? { nome: value.nome, segmento: value.segmento, idempotency_key: value.idempotency_key }
        : null;
    } catch (_) {
      return null;
    }
  }
  function mount() {
    if (!auth.current) return;
    const top = document.querySelector("main > .top .r2");
    if (top && !top.querySelector("[data-business-menu]")) {
      const link = el("a");
      const caption = el("span", "Meus negócios · ");
      caption.className = "sm-business-caption";
      const activeName = el("span", auth.current.negocio.nome);
      link.append(caption, activeName);
      link.href = "#/config/conta";
      link.className = "btn o sm-business-link";
      link.dataset.businessMenu = "true";
      link.title = "Negócio ativo: " + auth.current.negocio.nome;
      link.setAttribute("aria-label", "Meus negócios — ativo: " + auth.current.negocio.nome);
      top.prepend(link);
    }
    const view = document.getElementById("v");
    if (
      !location.hash.startsWith("#/config/conta") ||
      !view ||
      view.querySelector("[data-businesses]")
    )
      return;
    const expectedScope = scope();
    const panel = el("section");
    panel.className = "sm-businesses";
    panel.dataset.businesses = "true";
    panel.append(el("h2", "Meus negócios"));
    panel.append(el("p", "Negócio ativo: " + auth.current.negocio.nome));
    const message = el("p", "Carregando seus negócios…");
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    const list = el("ul");
    panel.append(message, list);
    view.prepend(panel);
    const alive = () => panel.isConnected && scope() === expectedScope;
    const refresh = async () => {
      const result = await auth.request("/auth/workspaces");
      if (!alive()) return;
      list.replaceChildren();
      for (const item of result.items) {
        const row = el("li");
        row.append(
          el("span", item.nome + (item.id === result.active_workspace_id ? " — ativo" : "")),
        );
        if (item.id !== result.active_workspace_id) {
          const choose = el("button", "Acessar " + item.nome);
          choose.type = "button";
          choose.className = "btn o";
          choose.onclick = async () => {
            choose.disabled = true;
            try {
              await auth.switchWorkspace(item.id);
            } catch (error) {
              if (alive()) {
                message.textContent = error.message;
                choose.disabled = false;
              }
            }
          };
          row.append(choose);
        }
        list.append(row);
      }
      message.textContent = result.items.length
        ? "Cada negócio mantém seus próprios clientes, agenda, vendas e conversas."
        : "Você ainda não tem negócios disponíveis.";
    };
    refresh().catch((error) => {
      if (alive()) message.textContent = error.message;
    });
    if (!["owner", "admin"].includes(auth.current.papel)) {
      panel.append(
        el(
          "p",
          "Seu acesso atual permite consultar os negócios autorizados. Para adicionar, use um negócio em que você seja proprietário ou administrador.",
        ),
      );
      return;
    }
    const add = el("button", "Adicionar negócio");
    add.type = "button";
    add.className = "btn";
    const form = el("form");
    form.hidden = true;
    const nameLabel = el("label", "Nome do negócio");
    const name = el("input");
    name.required = true;
    name.maxLength = 160;
    name.autocomplete = "organization";
    nameLabel.append(name);
    const segmentLabel = el("label", "Segmento do negócio");
    const segment = el("input");
    segment.required = true;
    segment.maxLength = 120;
    segment.placeholder = "Ex.: serviços odontológicos ou moda feminina";
    segmentLabel.append(segment);
    const controls = el("div");
    controls.className = "sm-business-actions";
    const submit = el("button", "Criar negócio");
    submit.type = "submit";
    submit.className = "btn";
    const cancel = el("button", "Fechar");
    cancel.type = "button";
    cancel.className = "btn o";
    controls.append(submit, cancel);
    form.append(nameLabel, segmentLabel, controls);
    panel.append(add, form);
    const previousDraft = savedDraft();
    if (previousDraft) {
      name.value = previousDraft.nome || "";
      segment.value = previousDraft.segmento || "";
    }
    const save = () => {
      if (!alive()) return;
      const previous = savedDraft();
      const same =
        previous?.nome === name.value.trim() && previous?.segmento === segment.value.trim();
      sessionStorage.setItem(
        draftKey(),
        JSON.stringify({
          nome: name.value.trim(),
          segmento: segment.value.trim(),
          idempotency_key: same ? previous.idempotency_key : crypto.randomUUID(),
        }),
      );
    };
    const saveInput = () => {
      try {
        save();
      } catch (_) {
        message.textContent =
          "Não foi possível preservar o rascunho neste navegador. Confira o armazenamento antes de criar o negócio.";
      }
    };
    name.addEventListener("input", saveInput);
    segment.addEventListener("input", saveInput);
    add.onclick = () => {
      form.hidden = false;
      name.focus();
    };
    cancel.onclick = () => {
      form.hidden = true;
      add.focus();
    };
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (!alive() || submit.disabled || !form.reportValidity()) return;
      try {
        save();
        submit.disabled = true;
        name.disabled = segment.disabled = true;
        const result = await auth.request("/auth/workspaces", "POST", savedDraft());
        if (!alive()) return;
        sessionStorage.removeItem(draftKey());
        form.reset();
        form.hidden = true;
        try {
          await refresh();
        } catch (_) {
          if (alive())
            message.textContent =
              "Negócio criado. Atualize a página para carregar a lista; não repita o cadastro.";
          return;
        }
        if (alive())
          message.textContent =
            "Negócio " + result.negocio.nome + " criado. Selecione Acessar para começar.";
      } catch (error) {
        if (alive())
          message.textContent =
            error.message ||
            "Não foi possível confirmar. Tente novamente com os mesmos dados para verificar, sem duplicar o cadastro.";
      } finally {
        if (alive()) {
          submit.disabled = false;
          name.disabled = segment.disabled = false;
        }
      }
    };
  }
  window.SocialMEIBusinesses = { refresh: mount };
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      const result = render.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  queueMicrotask(mount);
})();
