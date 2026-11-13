/* Capture capabilities before rendering; keep tokens only in this closure. */
(() => {
  "use strict";
  const match = /^#(verificar|convite)\/([A-Za-z0-9_-]{43})$/.exec(location.hash);
  let token = match?.[2] || null;
  const purpose = match?.[1];
  if (location.hash) history.replaceState(history.state, "", location.pathname + location.search);
  document.addEventListener("DOMContentLoaded", async () => {
    const auth = window.SocialMEIAuth;
    const message = document.getElementById("message");
    const actions = document.getElementById("actions");
    const title = document.getElementById("title");
    const node = (tag, text) => {
      const el = document.createElement(tag);
      if (text) el.textContent = text;
      return el;
    };
    const button = (text, callback) => {
      const el = node("button", text);
      el.type = "button";
      el.className = "primary";
      el.onclick = async () => {
        if (el.disabled) return;
        el.disabled = true;
        try {
          await callback();
        } catch (error) {
          message.textContent = error.message;
        } finally {
          if (el.isConnected) el.disabled = false;
        }
      };
      actions.append(el);
      return el;
    };
    const field = (form, label, name, type, required = true) => {
      const wrap = node("label", label);
      const input = node("input");
      input.name = name;
      input.type = type;
      input.required = required;
      input.maxLength = type === "password" ? 128 : 255;
      input.autocomplete = type === "password" ? "new-password" : name;
      wrap.append(input);
      form.append(wrap);
      return input;
    };
    const formSubmit = (form, label, handler) => {
      const submit = node("button", label);
      submit.type = "submit";
      submit.className = "primary";
      form.append(submit);
      form.onsubmit = async (event) => {
        event.preventDefault();
        if (submit.disabled || !form.reportValidity()) return;
        submit.disabled = true;
        try {
          await handler();
        } catch (error) {
          message.textContent = error.message;
        } finally {
          if (submit.isConnected) submit.disabled = false;
        }
      };
      actions.append(form);
    };
    try {
      if (!auth?.remote)
        throw new Error("Ativação por e-mail disponível somente no ambiente conectado.");
      await auth.ready;
      if (purpose === "verificar" && token) {
        message.textContent = "Confirme abaixo para verificar o e-mail desta conta.";
        button("Confirmar meu e-mail", async () => {
          await auth.request("/auth/verification/confirm", "POST", { token });
          token = null;
          actions.replaceChildren();
          message.textContent = "E-mail confirmado. Sua conta foi ativada.";
        });
      } else if (purpose === "convite" && token) {
        const preview = await auth.request("/auth/invitations/inspect", "POST", { token });
        title.textContent = "Convite para " + preview.business_name;
        const role =
          {
            admin: "Administrador",
            member: "Operacional",
            viewer: "Leitura",
            report_viewer: "Somente relatórios",
          }[preview.role] || "Integrante";
        message.textContent =
          "Convite para " +
          preview.email_hint +
          ". Acesso: " +
          role +
          ". Confira o negócio antes de aceitar.";
        const form = node("form");
        const email = field(form, "E-mail que recebeu o convite", "email", "email");
        let name, password;
        if (auth.current) email.value = auth.current.usuario.email;
        else {
          name = field(form, "Seu nome", "name", "text");
          name.maxLength = 160;
          password = field(form, "Senha para sua nova conta", "password", "password");
          password.minLength = 8;
          form.append(
            node(
              "p",
              "Se você já tem conta, entre nela e abra novamente o link recebido por e-mail. O convite não altera sua senha.",
            ),
          );
        }
        formSubmit(form, "Aceitar acesso a este negócio", async () => {
          const packet = { token, email: email.value.trim() };
          if (!auth.current) {
            packet.nome = name.value.trim();
            packet.senha = password.value;
          }
          try {
            const result = await auth.request("/auth/invitations/accept", "POST", packet);
            token = null;
            actions.replaceChildren();
            message.textContent = result.message;
          } finally {
            if (password) password.value = "";
          }
        });
      } else {
        if (!auth.current)
          throw new Error("Entre na sua conta para reenviar a verificação ou corrigir seu e-mail.");
        const status = await auth.request("/auth/verification/status");
        if (!status.required || status.verified) {
          message.textContent = "Sua conta está disponível. Continue a configuração do negócio.";
          return;
        }
        message.textContent =
          "Confira a mensagem enviada a " +
          status.email +
          ", inclusive no spam. Seu acesso será liberado após a confirmação.";
        button("Reenviar e-mail", async () => {
          message.textContent = (
            await auth.request("/auth/verification/resend", "POST", {})
          ).message;
        });
        const form = node("form");
        form.append(node("h2", "Corrigir meu e-mail"));
        const email = field(form, "E-mail correto", "email", "email");
        const password = field(form, "Sua senha atual", "password", "password");
        password.autocomplete = "current-password";
        formSubmit(form, "Corrigir e enviar nova verificação", async () => {
          try {
            message.textContent = (
              await auth.request("/auth/verification/email", "POST", {
                email: email.value.trim(),
                atual: password.value,
              })
            ).message;
          } finally {
            password.value = "";
          }
        });
      }
    } catch (error) {
      message.textContent = error.message;
    }
  });
})();
