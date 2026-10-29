/* Manage the existing scoped catalog credential; never connects or sends to WAHA. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIWhatsAppCatalog) return;
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const owner = () => ["owner", "admin"].includes(host.identity?.papel);
  const node = (tag, text) => {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    return result;
  };
  const style = node("style");
  style.textContent =
    ".sm-wa{margin:18px 0;padding:18px;border:1px solid var(--b);border-radius:16px;background:var(--w);color:var(--t);overflow-wrap:anywhere}.sm-wa h2{font-size:20px}.sm-wa p{margin:10px 0;color:var(--m)}.sm-wa button,.sm-wa input{min-height:44px;font:inherit;border:1px solid var(--b);border-radius:10px;padding:9px 14px;background:var(--w);color:var(--t);max-width:100%}.sm-wa button{cursor:pointer}.sm-wa button:disabled{opacity:.6}.sm-wa li{padding:12px 0;border-top:1px solid var(--b)}.sm-wa .wa-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px}.sm-wa-secret{margin:auto;width:min(540px,calc(100vw - 32px));max-height:calc(100dvh - 32px);overflow:auto;border:1px solid var(--b);border-radius:16px;padding:20px;background:var(--w);color:var(--t)}.sm-wa-secret::backdrop{background:#0008}.sm-wa-secret input{width:100%;min-width:0}.sm-wa-secret button{margin:8px 8px 0 0}";
  document.head.append(style);
  let credentialDialog;
  function showOnce(value) {
    credentialDialog?.close();
    const dialog = node("dialog");
    credentialDialog = dialog;
    dialog.className = "sm-wa sm-wa-secret";
    dialog.setAttribute("aria-label", "Credencial de consulta WhatsApp");
    dialog.append(
      node("h2", "Credencial gerada"),
      node(
        "p",
        "Guarde somente no cofre de credenciais do n8n. Ela autoriza consultas ao catálogo deste canal, não o envio de mensagens. A credencial anterior foi revogada.",
      ),
    );
    const input = node("input");
    input.type = "password";
    input.readOnly = true;
    input.value = value;
    input.setAttribute("aria-label", "Credencial técnica exibida uma única vez");
    input.autocomplete = "off";
    const copy = node("button", "Copiar credencial");
    copy.type = "button";
    const feedback = node("p");
    feedback.setAttribute("role", "status");
    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(input.value);
        feedback.textContent = "Copiada. Guarde em local privado.";
      } catch {
        feedback.textContent =
          "Não foi possível copiar. Gere novamente ao configurar o n8n em um navegador seguro.";
      }
    };
    const close = node("button", "Fechar e ocultar");
    close.type = "button";
    close.onclick = () => dialog.close();
    dialog.addEventListener("close", () => {
      input.value = "";
      dialog.remove();
      if (credentialDialog === dialog) credentialDialog = null;
    });
    dialog.append(input, copy, close, feedback);
    document.body.append(dialog);
    dialog.showModal();
    close.focus();
  }
  function mount() {
    if (!owner() || !location.hash.startsWith("#/config/integracoes")) return;
    const view = document.getElementById("v");
    if (!view || view.querySelector("[data-wa-catalog]")) return;
    const expected = scope(),
      section = node("section");
    section.className = "sm-wa";
    section.dataset.waCatalog = "true";
    section.append(
      node("h2", "WhatsApp — catálogo do negócio"),
      node(
        "p",
        "Consulte o estado cadastrado e prepare o acesso do menu n8n aos produtos, preços e disponibilidade. Isso não conecta um número nem ativa respostas automáticas.",
      ),
    );
    const feedback = node("p", "Consultando canais…");
    feedback.setAttribute("role", "status");
    feedback.setAttribute("aria-live", "polite");
    const refresh = node("button", "Atualizar canais");
    refresh.type = "button";
    const list = node("ul");
    section.append(feedback, refresh, list);
    (view.querySelector(".pg > .g2 > .fl") || view).append(section);
    const current = () => section.isConnected && scope() === expected;
    async function load() {
      refresh.disabled = true;
      try {
        const data = await host.request("/whatsapp/catalog/access");
        if (!current()) return;
        const native = [...view.querySelectorAll(".sw")].find(
          (row) => row.querySelector("b")?.textContent.trim() === "WhatsApp",
        );
        if (native) {
          const badge = native.querySelector(".chip, .st2");
          if (badge) {
            const value = data.channels.some((channel) => channel.active)
              ? "Canal cadastrado"
              : "Aguardando canal";
            const text = [...badge.childNodes].find((child) => child.nodeType === Node.TEXT_NODE);
            if (text) text.textContent = value;
            else badge.appendChild(document.createTextNode(value));
          }
          const button = native.querySelector("button");
          if (button) {
            button.disabled = false;
            button.style.flexShrink = "0";
            button.textContent = "Ver catálogo";
            button.title = "Gerenciar acesso ao catálogo; não conecta um telefone";
            button.onclick = (event) => {
              event.preventDefault();
              event.stopImmediatePropagation();
              section.scrollIntoView({ block: "center", behavior: "instant" });
              refresh.focus({ preventScroll: true });
            };
          }
        }
        feedback.textContent = data.enabled
          ? "Consulta técnica habilitada no servidor. A conexão WAHA precisa ser verificada separadamente."
          : "Consulta técnica desativada no servidor. Credenciais podem ser preparadas; nenhum envio será ativado aqui.";
        list.replaceChildren();
        if (!data.channels.length)
          list.append(
            node(
              "li",
              "Nenhum canal WAHA cadastrado neste negócio. O responsável pela integração precisa vincular a sessão e o número no servidor.",
            ),
          );
        for (const channel of data.channels) {
          const item = node("li");
          item.append(node("strong", channel.name || channel.instance));
          item.append(
            node(
              "p",
              `${channel.active ? "Canal cadastrado como ativo" : "Canal inativo"} · ${channel.enabled ? "consulta autorizada" : "sem credencial de consulta"}. Estado do provedor: ${channel.provider_state || "não verificado"}.`,
            ),
          );
          const actions = node("div");
          actions.className = "wa-actions";
          const issue = node(
            "button",
            channel.credential_configured ? "Trocar credencial" : "Gerar credencial",
          );
          issue.type = "button";
          issue.disabled = !channel.active;
          issue.title = channel.active
            ? "Exibir uma credencial técnica uma única vez"
            : "O canal precisa ser vinculado e ativado pelo responsável";
          issue.onclick = async () => {
            if (
              channel.credential_configured &&
              !confirm(
                "Trocar a credencial invalida a anterior. Atualize o cofre n8n antes de retomar as consultas. Continuar?",
              )
            )
              return;
            issue.disabled = true;
            try {
              const data = await host.request("/whatsapp/catalog/access", "POST", {
                channel_id: channel.channel_id,
              });
              if (!current()) return;
              showOnce(data.token_once);
              await load();
            } catch (error) {
              if (current())
                feedback.textContent = error.message || "Não foi possível gerar a credencial.";
            } finally {
              if (current()) issue.disabled = !channel.active;
            }
          };
          actions.append(issue);
          if (channel.credential_configured) {
            const revoke = node("button", "Revogar acesso");
            revoke.type = "button";
            revoke.onclick = async () => {
              if (!confirm("Revogar as consultas deste canal? Isso não desconecta o WhatsApp."))
                return;
              revoke.disabled = true;
              try {
                await host.request("/whatsapp/catalog/access/" + channel.channel_id, "DELETE");
                if (current()) await load();
              } catch (error) {
                if (current()) {
                  feedback.textContent = error.message || "Não foi possível revogar.";
                  revoke.disabled = false;
                }
              }
            };
            actions.append(revoke);
          }
          item.append(actions);
          list.append(item);
        }
      } catch (error) {
        if (current())
          feedback.textContent = error.message || "Não foi possível consultar os canais.";
      } finally {
        if (current()) refresh.disabled = false;
      }
    }
    refresh.onclick = load;
    load();
  }
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      const result = render.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => {
    credentialDialog?.close();
    queueMicrotask(mount);
  });
  window.SocialMEIWhatsAppCatalog = { refresh: mount };
  queueMicrotask(mount);
})();
