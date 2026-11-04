/* Existing accounts only; team access belongs to the active workspace. */
(() => {
  const auth = window.SocialMEIAuth;
  if (!auth?.remote || window.SocialMEITeam) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "styles/v22-team-members.css";
  document.head.append(link);
  const roles = {
    owner: "Proprietário",
    admin: "Administrador",
    member: "Operacional",
    viewer: "Leitura",
    report_viewer: "Somente relatórios",
  };
  const el = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const scope = () => auth.current && `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  function mount() {
    if (
      !auth.current ||
      !["owner", "admin"].includes(auth.current.papel) ||
      !location.hash.startsWith("#/config/conta")
    )
      return;
    const view = document.getElementById("v");
    if (!view || view.querySelector("[data-team-members]")) return;
    const expected = scope();
    const panel = el("section");
    panel.className = "sm-team";
    panel.dataset.teamMembers = "true";
    panel.append(el("h2", "Equipe do negócio"));
    panel.append(
      el(
        "p",
        "Autorize somente contas SocialMEI já cadastradas. Este acesso vale apenas para o negócio ativo; nenhum convite ou e-mail será enviado.",
      ),
    );
    const message = el("p", "Carregando equipe…");
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    const list = el("ul");
    panel.append(message, list);
    view.append(panel);
    const alive = () => panel.isConnected && scope() === expected;
    const choices = () => {
      const select = el("select");
      for (const role of ["member", "report_viewer"]) {
        const option = el("option", roles[role]);
        option.value = role;
        select.append(option);
      }
      return select;
    };
    const manage = auth.current.papel === "owner";
    const refresh = async () => {
      const data = await auth.request("/team/members");
      if (!alive()) return;
      list.replaceChildren();
      for (const member of data.items) {
        const row = el("li");
        const details = el("div");
        details.append(
          el("strong", member.nome),
          el("span", member.email),
          el(
            "span",
            `${roles[member.role] || member.role}${member.ativo ? "" : " · conta inativa"}`,
          ),
        );
        row.append(details);
        if (
          manage &&
          member.id !== auth.current.usuario.id &&
          !["owner", "admin"].includes(member.role)
        ) {
          const controls = el("div");
          controls.className = "sm-team-actions";
          const select = choices();
          if (member.role === "viewer") {
            const current = el("option", roles.viewer);
            current.value = "viewer";
            select.prepend(current);
          }
          select.value = member.role;
          select.setAttribute("aria-label", "Acesso de " + member.nome);
          const save = el("button", "Alterar acesso");
          save.type = "button";
          save.className = "btn o";
          save.onclick = async () => {
            if (!alive() || select.value === member.role) return;
            if (
              !confirm(
                "Alterar o acesso desta conta somente neste negócio? As sessões neste negócio serão encerradas.",
              )
            )
              return;
            save.disabled = true;
            try {
              await auth.request("/team/members/" + member.id, "PATCH", {
                role: select.value,
                expected_role: member.role,
              });
              if (alive()) {
                await refresh();
                message.textContent =
                  "Acesso alterado. A pessoa deverá entrar novamente neste negócio.";
              }
            } catch (error) {
              if (alive()) {
                message.textContent = error.message;
                save.disabled = false;
              }
            }
          };
          const revoke = el("button", "Revogar acesso");
          revoke.type = "button";
          revoke.className = "btn o";
          revoke.onclick = async () => {
            if (
              !alive() ||
              !confirm(
                "Revogar o acesso desta conta somente a este negócio? A conta e seus outros negócios serão preservados.",
              )
            )
              return;
            revoke.disabled = true;
            try {
              await auth.request("/team/members/" + member.id, "DELETE", {
                expected_role: member.role,
              });
              if (alive()) {
                await refresh();
                message.textContent = "Acesso revogado neste negócio.";
              }
            } catch (error) {
              if (alive()) {
                message.textContent = error.message;
                revoke.disabled = false;
              }
            }
          };
          controls.append(select, save, revoke);
          row.append(controls);
        }
        list.append(row);
      }
      message.textContent = data.truncated
        ? "Exibindo os primeiros 50 integrantes. Nenhum acesso foi modificado."
        : "A conta de cada pessoa é preservada. Proprietários e administradores não são alterados por esta tela.";
    };
    const update = el("button", "Atualizar equipe");
    update.type = "button";
    update.className = "btn o";
    update.onclick = () =>
      refresh().catch((error) => {
        if (alive()) message.textContent = error.message;
      });
    panel.append(update);
    if (manage) {
      const form = el("form");
      const emailLabel = el("label", "E-mail da conta existente");
      const email = el("input");
      email.type = "email";
      email.required = true;
      email.maxLength = 255;
      email.autocomplete = "off";
      emailLabel.append(email);
      const roleLabel = el("label", "Permissão no negócio");
      const select = choices();
      roleLabel.append(select);
      const grant = el("button", "Adicionar à equipe");
      grant.type = "submit";
      grant.className = "btn";
      form.append(emailLabel, roleLabel, grant);
      form.onsubmit = async (event) => {
        event.preventDefault();
        if (!alive() || grant.disabled || !form.reportValidity()) return;
        grant.disabled = true;
        try {
          const data = await auth.request("/team/members", "POST", {
            email: email.value.trim(),
            role: select.value,
          });
          if (alive()) {
            form.reset();
            await refresh();
            message.textContent = data.already_member
              ? "A conta já possui esse acesso."
              : "Conta adicionada à equipe deste negócio.";
          }
        } catch (error) {
          if (alive()) message.textContent = error.message;
        } finally {
          if (alive()) grant.disabled = false;
        }
      };
      panel.append(
        form,
        el(
          "p",
          "Operacional permite atuar nos módulos disponíveis. Somente relatórios não permite editar CRM, agenda ou vendas. Esta tela não cria usuários nem define senhas.",
        ),
      );
    } else
      panel.append(
        el("p", "Somente o proprietário pode adicionar, alterar ou revogar integrantes."),
      );
    refresh().catch((error) => {
      if (alive()) message.textContent = error.message;
    });
  }
  const previous = window.render;
  if (typeof previous === "function")
    window.render = function (...args) {
      const result = previous.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.SocialMEITeam = { refresh: mount };
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  queueMicrotask(mount);
})();
