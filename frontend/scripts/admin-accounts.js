(async () => {
  const status = document.getElementById("adminStatus");
  const identity = await SocialMEIAuth.ready;
  if (!SocialMEIAuth.remote || !identity) {
    status.textContent = "Entre na sua conta pelo site para continuar.";
    return;
  }
  if (!identity.usuario.administrador_plataforma) {
    status.textContent = "Acesso reservado ao administrador do projeto.";
    return;
  }
  async function loadUsers() {
    const users = await SocialMEIAuth.request("/admin/users");
    const host = document.getElementById("adminUsers");
    host.replaceChildren();
    for (const user of users) {
      const row = document.createElement("tr");
      for (const value of [
        user.nome,
        user.email,
        user.administrador_plataforma ? "Administrador do projeto" : "MEI",
        user.ativo ? "Ativa" : "Desativada",
      ]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      }
      const action = document.createElement("td");
      if (user.ativo && !user.administrador_plataforma) {
        const button = document.createElement("button");
        button.className = "management-button";
        button.type = "button";
        button.textContent = "Desativar";
        button.addEventListener("click", async () => {
          if (!confirm(`Desativar a conta de ${user.nome}? As sessões serão encerradas.`)) return;
          button.disabled = true;
          try {
            await SocialMEIAuth.request(`/admin/users/${user.id}/disable`, "POST", {});
            await loadUsers();
            status.textContent = "Conta desativada. Dados preservados.";
          } catch (error) {
            status.textContent = error.message;
            button.disabled = false;
          }
        });
        action.append(button);
      }
      row.append(action);
      host.append(row);
    }
  }
  document.getElementById("adminInviteForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.target.querySelector("button");
    button.disabled = true;
    document.getElementById("inviteCode").value = "";
    try {
      const value = await SocialMEIAuth.request("/admin/invites", "POST", {
        email: document.getElementById("inviteEmail").value.trim(),
      });
      document.getElementById("inviteCode").value = value.convite;
      status.textContent = `Convite criado para ${value.email}, válido por ${value.validade_dias} dias.`;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  try {
    await loadUsers();
    document.getElementById("adminContent").hidden = false;
    status.textContent = "Administração disponível.";
  } catch (error) {
    status.textContent = error.message;
  }
})();
