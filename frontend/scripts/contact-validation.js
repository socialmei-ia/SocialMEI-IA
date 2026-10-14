/* CONTACT INPUTS */
(() => {
  const areaCodes = new Set(
    "11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 41 42 43 44 45 46 47 48 49 51 53 54 55 61 62 63 64 65 66 67 68 69 71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 91 92 93 94 95 96 97 98 99".split(
      " ",
    ),
  );

  function phone(value, required = false) {
    const text = String(value ?? "").trim();
    if (!text || text === "—") {
      return {
        valid: !required,
        value: "",
        message: required ? "Informe o telefone com DDD." : "",
      };
    }
    if (!/^\+?[\d\s().-]+$/.test(text)) {
      return { valid: false, message: "Use um telefone, não um nome ou @usuário." };
    }
    let digits = text.replace(/\D/g, "");
    const international = text.startsWith("+");
    const brazil = !international || digits.startsWith("55");
    if (international && brazil) digits = digits.slice(2);
    if (brazil) {
      if (!areaCodes.has(digits.slice(0, 2))) {
        return { valid: false, message: "Confira o DDD brasileiro (por exemplo, 11 ou 81)." };
      }
      const subscriber = digits.slice(2);
      if (!/^(?:9\d{8}|[2-5]\d{7})$/.test(subscriber)) {
        return {
          valid: false,
          message: "Use DDD + celular com 9 dígitos, ou telefone fixo com 8 dígitos.",
        };
      }
      const split = subscriber.length - 4;
      const formatted = `(${digits.slice(0, 2)}) ${subscriber.slice(0, split)}-${subscriber.slice(split)}`;
      return {
        valid: true,
        value: (international ? "+55 " : "") + formatted,
        international: "+55" + digits,
      };
    }
    if (!/^[1-9]\d{7,14}$/.test(digits) || /^(\d)\1+$/.test(digits)) {
      return {
        valid: false,
        message: "Para outro país, use +código do país e número completo (8 a 15 dígitos).",
      };
    }
    return { valid: true, value: "+" + digits, international: "+" + digits };
  }

  function instagram(value, required = false) {
    const text = String(value ?? "").trim();
    if (!text || text === "—") {
      return {
        valid: !required,
        value: "",
        message: required ? "Informe o @usuário do Instagram." : "",
      };
    }
    const username = text.replace(/^@/, "");
    if (
      !/^(?!.*\.\.)(?!\.)(?!.*\.$)[A-Za-z0-9._]{1,30}$/.test(username) ||
      (/^\d+$/.test(username) && !text.startsWith("@"))
    ) {
      return {
        valid: false,
        message: "Use o @usuário do Instagram, sem espaços, links ou telefone.",
      };
    }
    return { valid: true, value: "@" + username };
  }

  function fieldType(input) {
    if (input.dataset.contactType) return input.dataset.contactType;
    if (input.type === "tel" || input.name === "telefone") return "phone";
    if (input.name === "instagram") return "instagram";
    return null;
  }

  function validateField(input, normalize = false) {
    const type = fieldType(input);
    if (!type) return true;
    const result = (type === "phone" ? phone : instagram)(input.value, input.required);
    input.setCustomValidity(result.valid ? "" : result.message);
    input.setAttribute("aria-invalid", String(!result.valid));
    if (normalize && result.valid && input.value.trim() !== "—") input.value = result.value;
    const status = document.getElementById(input.dataset.contactStatus || "");
    if (status) status.textContent = result.valid ? "" : result.message;
    return result.valid;
  }

  function validateForm(form) {
    const inputs = [...form.querySelectorAll("input")].filter(fieldType);
    const results = inputs.map((input) => validateField(input, true));
    const invalid = inputs.find((_, index) => !results[index]);
    if (invalid) {
      invalid.focus();
      invalid.reportValidity();
    }
    return !invalid;
  }

  document.addEventListener("input", (event) => {
    const input = event.target;
    if (input instanceof HTMLInputElement && fieldType(input)) {
      input.setCustomValidity("");
      input.removeAttribute("aria-invalid");
      const status = document.getElementById(input.dataset.contactStatus || "");
      if (status) status.textContent = "";
    }
  });
  document.addEventListener(
    "blur",
    (event) => {
      if (event.target instanceof HTMLInputElement && fieldType(event.target))
        validateField(event.target, true);
    },
    true,
  );
  document.addEventListener(
    "submit",
    (event) => {
      if (event.target instanceof HTMLFormElement && !validateForm(event.target)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true,
  );

  function confirmPhone(value) {
    return new Promise((resolve) => {
      const previousFocus = document.activeElement;
      const dialog = document.createElement("dialog");
      dialog.className = "contact-confirmation";
      dialog.setAttribute("aria-labelledby", "contactConfirmationTitle");
      dialog.innerHTML = `<form method="dialog"><span class="contact-confirmation-symbol" aria-hidden="true"><svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="7" y="2" width="10" height="20" rx="3"/><path d="M10 5h4M11 19h2"/></svg></span><p class="contact-eyebrow">CONFIRA SEU CONTATO</p><h2 id="contactConfirmationTitle">Este número está correto?</h2><p>Ele será salvo no seu perfil. Confira o país, o DDD e o número antes de continuar.</p><strong class="contact-confirmation-number"></strong><p class="contact-confirmation-note">Esta etapa não envia SMS nem verifica a titularidade do número.</p><div class="contact-confirmation-actions"><button class="btn" value="edit" autofocus>Editar número</button><button class="btn pr" value="confirm">Sim, continuar</button></div></form>`;
      const contact = phone(value);
      dialog.querySelector(".contact-confirmation-number").textContent = contact.value.startsWith(
        "+",
      )
        ? contact.value
        : "+55 " + contact.value;
      dialog.addEventListener(
        "close",
        () => {
          const accepted = dialog.returnValue === "confirm";
          dialog.remove();
          previousFocus?.focus();
          resolve(accepted);
        },
        { once: true },
      );
      document.body.append(dialog);
      dialog.showModal();
    });
  }
  window.SocialMEIContacts = Object.freeze({
    phone,
    instagram,
    validateField,
    validateForm,
    confirmPhone,
  });
})();
