/* Owner requests are durable; session mutations and pairing stay operator-controlled. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIWhatsAppManagement) return;
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const node = (tag, text) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const labels = {
    not_connected: "Não conectado",
    configuration_pending: "Configuração pendente",
    connecting: "Conectando",
    connected: "Conectado",
    attention: "Requer atenção",
    disconnected: "Desconectado",
  };
  let ticket = 0;
  async function mount() {
    if (
      !location.hash.startsWith("#/config/integracoes") ||
      !["owner", "admin"].includes(host.identity?.papel)
    )
      return;
    const view = document.getElementById("v");
    if (!view || view.querySelector("[data-whatsapp-management]")) return;
    const expected = scope(),
      generation = ++ticket;
    const panel = node("section");
    panel.className = "sm-wa";
    panel.dataset.whatsappManagement = "true";
    const heading = node("h2", "Conexão WhatsApp por negócio");
    const message = node("p", "Consultando o estado do servidor…");
    message.setAttribute("role", "status");
    const body = node("div");
    panel.append(heading, message, body);
    view.append(panel);
    const alive = () => panel.isConnected && scope() === expected && generation === ticket;
    let data = null,
      pendingPacket = null,
      loading = false;
    async function load() {
      if (!alive() || loading) return;
      loading = true;
      try {
        const result = await host.request("/whatsapp/connection");
        if (!alive()) return;
        if (
          result?.source !== "server" ||
          result.workspace_id !== host.identity.negocio.id ||
          !Number.isSafeInteger(result.revision) ||
          !labels[result.connection_state]
        )
          throw Error("Não foi possível conferir este vínculo.");
        data = result;
        paint();
      } catch (error) {
        if (alive()) message.textContent = error.message;
      } finally {
        loading = false;
      }
    }
    function button(text, action) {
      const el = node("button", text);
      el.type = "button";
      el.className = "btn o";
      el.onclick = async () => {
        if (!alive() || el.disabled) return;
        el.disabled = true;
        try {
          await action();
        } catch (error) {
          if (alive()) message.textContent = error.message;
        } finally {
          if (el.isConnected && alive()) el.disabled = false;
        }
      };
      return el;
    }
    function paint() {
      if (!alive() || !data) return;
      body.replaceChildren();
      message.textContent = labels[data.connection_state];
      body.append(
        node(
          "p",
          `${data.session_live_verified ? "Sessão conferida recentemente." : "Sessão ao vivo ainda não confirmada."} ${data.receiving_messages ? "Recebendo mensagens recentes." : "Sem comprovação de recebimento recente nesta sessão."} ${data.sending_enabled ? "Envio humano habilitado." : "Envio não confirmado."}`,
        ),
      );
      body.append(
        node(
          "p",
          "Integração experimental WAHA. O caminho oficial WhatsApp Business Platform é separado e ainda não está disponível nesta tela.",
        ),
      );
      if (data.request)
        body.append(
          node(
            "p",
            `Solicitação aguardando conferência da equipe: ${{ connect: "conexão", reconnect: "reconexão", disconnect: "desconexão" }[data.request.action] || "alteração"}${data.request.phone_hint ? " · " + data.request.phone_hint : ""}. A sessão ainda não foi alterada.`,
          ),
        );
      body.append(button("Atualizar estado salvo", load));
      if (host.identity.papel !== "owner") {
        body.append(node("p", "Somente o proprietário pode solicitar alterações."));
        return;
      }
      if (data.probe_available)
        body.append(
          button("Conferir sessão no provedor", async () => {
            const result = await host.request("/whatsapp/connection/inspect", "POST", {});
            if (!alive()) return;
            if (
              result?.source !== "server" ||
              result.workspace_id !== host.identity.negocio.id ||
              !labels[result.connection_state]
            )
              throw Error("O negócio mudou durante a consulta.");
            data = result;
            paint();
          }),
        );
      body.append(
        node(
          "p",
          "O pareamento será liberado somente após provisionamento autorizado. Chaves e operações administrativas permanecem no servidor; esta tela não mostra um QR de demonstração.",
        ),
      );
      if (!data.management_available) {
        body.append(node("p", "Solicitações ainda não habilitadas neste ambiente."));
        return;
      }
      const form = node("form");
      const actionLabel = node("label", "O que deseja solicitar?");
      const action = node("select");
      const options = data.private_binding_verified ? ["reconnect", "disconnect"] : ["connect"];
      if (data.request) options.push("cancel");
      for (const key of options) {
        const option = node(
          "option",
          {
            connect: "Conectar um número",
            reconnect: "Reconectar sessão",
            disconnect: "Desconectar sessão",
            cancel: "Cancelar solicitação pendente",
          }[key],
        );
        option.value = key;
        action.append(option);
      }
      actionLabel.append(action);
      const phoneLabel = node("label", "Número com DDD e código do país");
      const phone = node("input");
      phone.type = "tel";
      phone.maxLength = 40;
      phone.autocomplete = "tel";
      phoneLabel.append(phone);
      const consentLabel = node("label");
      const consent = node("input");
      consent.type = "checkbox";
      consent.required = true;
      consentLabel.append(
        consent,
        document.createTextNode(
          " Sou responsável por este negócio e autorizo a equipe a avaliar a solicitação. Nada será conectado ou desconectado automaticamente.",
        ),
      );
      const send = node(
        "button",
        pendingPacket ? "Conferir a mesma solicitação" : "Registrar solicitação",
      );
      send.type = "submit";
      send.className = "btn";
      const update = () => {
        phoneLabel.hidden = action.value !== "connect";
        phone.required = action.value === "connect";
      };
      action.onchange = update;
      update();
      if (pendingPacket) {
        action.value = pendingPacket.action;
        phone.value = pendingPacket.phone || "";
        action.disabled = true;
        phone.readOnly = true;
        consent.checked = true;
        update();
      }
      form.append(actionLabel, phoneLabel, consentLabel, send);
      form.onsubmit = async (event) => {
        event.preventDefault();
        if (!alive() || send.disabled || !form.reportValidity()) return;
        send.disabled = true;
        try {
          if (!pendingPacket)
            pendingPacket = {
              operation_id: crypto.randomUUID(),
              expected_revision: data.revision,
              action: action.value,
              confirmed: true,
              ...(action.value === "connect" ? { phone: phone.value.trim() } : {}),
            };
          action.disabled = true;
          phone.readOnly = true;
          const result = await host.request("/whatsapp/connection/requests", "POST", pendingPacket);
          if (!alive()) return;
          if (result?.accepted !== true || result.executed !== false)
            throw Error("Não foi possível conferir a solicitação.");
          pendingPacket = null;
          await load();
          message.textContent =
            result.status === "cancelled"
              ? "Solicitação cancelada. Nenhuma sessão foi alterada."
              : "Solicitação registrada. A equipe precisa conferir titularidade, capacidade e respondedor único antes de executá-la.";
        } catch (error) {
          if (alive()) {
            if ([400, 403, 409, 422].includes(error.status)) {
              pendingPacket = null;
              action.disabled = false;
              phone.readOnly = false;
              send.textContent = "Registrar solicitação";
              message.textContent = error.message;
              if (error.status === 409) await load();
            } else {
              message.textContent =
                error.message + " Você pode conferir novamente a mesma solicitação.";
              send.textContent = "Conferir a mesma solicitação";
            }
          }
        } finally {
          if (alive() && send.isConnected) send.disabled = false;
        }
      };
      body.append(form, node("p", data.next_step));
    }
    await load();
  }
  const prior = render;
  render = () => {
    prior();
    mount();
  };
  window.addEventListener("hashchange", mount);
  window.SocialMEIWhatsAppManagement = { mount };
  mount();
})();
