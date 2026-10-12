(async () => {
  const el = (id) => document.getElementById(id);
  function show(message, state = "info") {
    el("adminStatus").textContent = message;
    el("adminStatus").dataset.state = state;
  }
  function syncThemeLabel() {
    const dark = SocialMEIThemes.current().base === "dark";
    el("adminThemeToggle").textContent = dark ? "Tema claro" : "Tema escuro";
    el("adminThemeToggle").setAttribute(
      "aria-label",
      dark ? "Ativar tema claro" : "Ativar tema escuro",
    );
  }
  syncThemeLabel();
  el("adminThemeToggle").addEventListener("click", () => {
    SocialMEIThemes.select(SocialMEIThemes.current().base === "dark" ? "light" : "dark");
    syncThemeLabel();
  });
  window.addEventListener("socialmei-theme-change", syncThemeLabel);
  const identity = await SocialMEIAuth.ready;
  if (!SocialMEIAuth.remote || !identity || !identity.usuario.administrador_plataforma) {
    const message = identity
      ? "Acesso reservado ao administrador do projeto."
      : SocialMEIAuth.problem || "Entre na sua conta pelo site para continuar.";
    show(message, "error");
    el("adminAccessMessage").textContent = message;
    el("adminAccessHelp").hidden = false;
    return;
  }
  const initials = (name) =>
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0] || "")
      .join("")
      .toUpperCase() || "SM";
  el("adminName").textContent = identity.usuario.nome;
  el("adminEmail").textContent = identity.usuario.email;
  el("adminAvatar").textContent = initials(identity.usuario.nome);
  el("adminLogout").hidden = false;
  el("adminLogout").addEventListener("click", async () => {
    const button = el("adminLogout");
    button.disabled = true;
    button.textContent = "Saindo…";
    try {
      await SocialMEIAuth.logout("/frontend/socialmei-app.html");
    } catch (error) {
      show(error.message, "error");
      button.disabled = false;
      button.textContent = "Sair da conta";
    }
  });
  let accounts = [],
    selectedUser = null,
    selectedButton = null;
  const fold = (text) =>
    text
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  function renderUsers() {
    const host = el("adminUsers");
    host.replaceChildren();
    const query = fold(el("adminSearch").value.trim());
    const filter = el("adminFilter").value;
    const visible = accounts.filter(
      (user) =>
        (!query || fold(user.nome + " " + user.email).includes(query)) &&
        (filter === "all" || (filter === "active" ? user.ativo : !user.ativo)),
    );
    for (const user of visible) {
      const row = node("tr");
      const person = node("div", undefined, "account-person");
      const names = node("div");
      names.append(node("b", user.nome), node("small", user.email));
      person.append(node("span", initials(user.nome), "account-avatar"), names);
      const personCell = node("td");
      personCell.append(person);
      row.append(personCell);
      const role = node("td");
      role.append(
        node(
          "span",
          user.administrador_plataforma ? "Administrador" : "MEI",
          "account-badge" + (user.administrador_plataforma ? " account-badge-admin" : ""),
        ),
      );
      row.append(role);
      const state = node("td");
      state.append(
        node(
          "span",
          user.ativo ? "Ativo" : "Desativado",
          "account-badge" + (user.ativo ? " account-badge-active" : ""),
        ),
      );
      row.append(state);
      const action = node("td");
      if (user.ativo && !user.administrador_plataforma) {
        const button = node("button", "Desativar", "account-button account-button-quiet");
        button.type = "button";
        button.setAttribute("aria-label", "Desativar acesso de " + user.nome);
        button.addEventListener("click", () => {
          selectedUser = user;
          selectedButton = button;
          el("disableAccountText").textContent =
            `Você vai desativar o acesso de ${user.nome} (${user.email}).`;
          el("disableAccountDialog").returnValue = "";
          el("disableAccountDialog").showModal();
          el("disableAccountForm").querySelector("[value=cancel]").focus();
        });
        action.append(button);
      } else
        action.append(
          node(
            "span",
            user.administrador_plataforma ? "Acesso protegido" : "Sem acesso",
            "account-admin-mark",
          ),
        );
      row.append(action);
      host.append(row);
    }
    if (!visible.length) {
      const row = node("tr"),
        cell = node(
          "td",
          accounts.length ? "Nenhuma conta corresponde à busca." : "Nenhuma conta cadastrada.",
        );
      cell.colSpan = 4;
      row.append(cell);
      host.append(row);
    }
    el("adminListSummary").textContent =
      `${visible.length} de ${accounts.length} contas exibidas${accounts.length === 500 ? " · limite de 500 contas nesta lista" : ""}.`;
    el("adminTotal").textContent = accounts.length;
    el("adminActive").textContent = accounts.filter((user) => user.ativo).length;
    el("adminDisabled").textContent = accounts.filter((user) => !user.ativo).length;
  }
  async function loadUsers() {
    const users = await SocialMEIAuth.request("/admin/users");
    if (!Array.isArray(users)) throw new Error("Não foi possível conferir a lista de contas.");
    accounts = users;
    renderUsers();
  }
  el("adminSearch").addEventListener("input", renderUsers);
  el("adminFilter").addEventListener("change", renderUsers);
  el("adminReload").addEventListener("click", async () => {
    el("adminReload").disabled = true;
    try {
      await loadUsers();
      show("Lista de contas atualizada.", "success");
    } catch (error) {
      show(error.message, "error");
    } finally {
      el("adminReload").disabled = false;
    }
  });
  el("disableAccountDialog").addEventListener("close", async () => {
    if (el("disableAccountDialog").returnValue !== "disable" || !selectedUser) {
      selectedUser = null;
      return;
    }
    const user = selectedUser,
      button = selectedButton;
    selectedUser = null;
    button.disabled = true;
    button.textContent = "Desativando…";
    try {
      await SocialMEIAuth.request(`/admin/users/${user.id}/disable`, "POST", {});
      await loadUsers();
      show("Conta desativada. As sessões foram encerradas e os dados preservados.", "success");
      el("adminReload").focus();
    } catch (error) {
      show(error.message, "error");
      button.disabled = false;
      button.textContent = "Desativar";
    }
  });
  el("adminInviteForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.target.querySelector("button");
    button.disabled = true;
    button.textContent = "Preparando convite…";
    el("inviteCode").value = "";
    el("inviteResult").hidden = true;
    try {
      const value = await SocialMEIAuth.request("/admin/invites", "POST", {
        email: el("inviteEmail").value.trim(),
      });
      el("inviteCode").value = value.convite;
      el("inviteResultSummary").textContent =
        `Para ${value.email} · válido por ${value.validade_dias} dias.`;
      el("inviteResult").hidden = false;
      show("Convite gerado. Copie o código e entregue à pessoa convidada.", "success");
      el("copyInvite").focus();
    } catch (error) {
      show(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = "Gerar convite ↗";
    }
  });
  el("copyInvite").addEventListener("click", async () => {
    if (!el("inviteCode").value) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(el("inviteCode").value);
      show("Código copiado. Compartilhe apenas com a pessoa convidada.", "success");
    } catch (_) {
      el("inviteCode").focus();
      el("inviteCode").select();
      show("Selecione o código e use a opção de copiar do navegador.");
    }
  });
  try {
    await loadUsers();
    el("adminContent").hidden = false;
    show("Seu acesso administrativo está ativo.", "success");
  } catch (error) {
    show(error.message, "error");
    el("adminAccessHelp").hidden = false;
    el("adminAccessMessage").textContent = error.message;
  }
})();
