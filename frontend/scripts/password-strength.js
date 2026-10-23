/* PASSWORD STRENGTH — feedback local; a validação continua com o formulário/API. */
(() => {
  "use strict";

  const commonPassword =
    /^(?:password|passw0rd|qwerty|letmein|welcome|admin|iloveyou|monkey|dragon|abc123|111111|123123|123456)/i;
  const repeatedCharacters = /(.)\1{3,}/u;
  const predictableSequence =
    /(?:0123|1234|2345|3456|4567|5678|6789|abcd|bcde|cdef|defg|qwer|wert|erty|asdf)/i;
  const labels = ["Defina sua senha", "Fraca", "Razoável", "Boa", "Forte"];

  function evaluatePassword(value, minimumLength = 8) {
    const rules = [
      {
        id: "length",
        label: `${minimumLength} caracteres ou mais`,
        met: value.length >= minimumLength,
      },
      {
        id: "case",
        label: "Letras maiúsculas e minúsculas",
        met: /\p{Ll}/u.test(value) && /\p{Lu}/u.test(value),
      },
      { id: "digit", label: "Um número", met: /\d/.test(value) },
      { id: "symbol", label: "Um símbolo", met: /[\p{P}\p{S}]/u.test(value) },
    ];
    const guessable =
      value.length > 0 &&
      (commonPassword.test(value) ||
        repeatedCharacters.test(value) ||
        predictableSequence.test(value));
    const passed = rules.filter((rule) => rule.met).length;
    const tooShort = value.length > 0 && !rules[0].met;
    const score = !value ? 0 : guessable || tooShort ? 1 : Math.max(1, passed);
    return {
      score,
      max: rules.length,
      label: tooShort ? "Muito curta" : labels[score],
      rules,
      guessable,
    };
  }

  if (typeof document === "undefined") {
    if (typeof module !== "undefined") module.exports = { evaluatePassword };
    return;
  }

  const fieldSelector = "#registerPassword, #accountNewPassword";
  const mounted = new Map();

  function mount(input) {
    if (mounted.has(input)) return;
    const root = document.createElement("div");
    root.className = "password-strength";
    root.id = `${input.id}Strength`;
    root.innerHTML = `
      <div class="password-strength-meter" role="meter" aria-label="Força estimada da senha" aria-valuemin="0" aria-valuemax="4" aria-valuenow="0">
        <span><i></i></span><span><i></i></span><span><i></i></span><span><i></i></span>
      </div>
      <div class="password-strength-heading"><b></b><span class="password-strength-warning" hidden>Padrão previsível</span></div>
      <details class="password-strength-details">
        <summary>Sugestões para uma senha mais forte</summary>
        <ul class="password-strength-rules"></ul>
      </details>
      <p class="password-strength-help">Estimativa local. Não altera os requisitos do cadastro nem garante segurança.</p>
      <p class="sr-only" aria-live="polite" aria-atomic="true"></p>
    `;
    const container = input.closest(".experience-password") || input.closest("label") || input;
    container.after(root);
    const originalDescriptions = input.getAttribute("aria-describedby") || "";
    const meter = root.querySelector('[role="meter"]');
    const bars = [...meter.querySelectorAll("i")];
    const label = root.querySelector(".password-strength-heading b");
    const warning = root.querySelector(".password-strength-warning");
    const ruleList = root.querySelector(".password-strength-rules");
    const announcement = root.querySelector('[aria-live="polite"]');
    label.id = `${root.id}Summary`;
    root.querySelector(".password-strength-help").id = `${root.id}Help`;
    input.setAttribute(
      "aria-describedby",
      [originalDescriptions, label.id, `${root.id}Help`].filter(Boolean).join(" "),
    );
    let announcementTimer;
    let currentMinimum;

    function update() {
      clearTimeout(announcementTimer);
      const minimum = input.minLength > 0 ? input.minLength : 8;
      const state = evaluatePassword(input.value, minimum);
      if (currentMinimum !== minimum) {
        ruleList.replaceChildren();
        state.rules.forEach((rule) => {
          const item = document.createElement("li");
          item.dataset.passwordRule = rule.id;
          const icon = document.createElement("span");
          icon.className = "password-rule-icon";
          icon.setAttribute("aria-hidden", "true");
          icon.innerHTML =
            '<svg viewBox="0 0 12 12" fill="none"><path d="M2 6.2 4.7 8.9 10 3.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
          const text = document.createElement("span");
          text.textContent = rule.label;
          const status = document.createElement("span");
          status.className = "sr-only";
          item.append(icon, text, status);
          ruleList.append(item);
        });
        currentMinimum = minimum;
      }
      root.dataset.strength = String(state.score);
      meter.setAttribute("aria-valuenow", String(state.score));
      meter.setAttribute("aria-valuetext", state.label);
      label.textContent = state.label;
      warning.hidden = !state.guessable;
      bars.forEach((bar, index) => bar.classList.toggle("is-filled", index < state.score));
      state.rules.forEach((rule) => {
        const item = ruleList.querySelector(`[data-password-rule="${rule.id}"]`);
        item.classList.toggle("is-met", rule.met);
        item.querySelector(".sr-only").textContent = rule.met ? "atendida" : "não atendida";
      });
      if (!input.value) {
        announcement.textContent = "";
        return;
      }
      const suggestions = state.rules
        .filter((rule) => !rule.met)
        .map((rule) => rule.label.toLowerCase());
      const message = [
        `Força estimada da senha: ${state.label.toLowerCase()}.`,
        state.guessable ? "Evite padrões previsíveis." : "",
        suggestions.length ? `Sugestões: ${suggestions.join(", ")}.` : "Sugestões atendidas.",
      ]
        .filter(Boolean)
        .join(" ");
      announcementTimer = setTimeout(() => {
        if (input.isConnected) announcement.textContent = message;
      }, 700);
    }

    const reset = () => queueMicrotask(update);
    const form = input.form;
    input.addEventListener("input", update);
    input.addEventListener("change", update);
    form?.addEventListener("reset", reset);
    mounted.set(input, () => {
      clearTimeout(announcementTimer);
      input.removeEventListener("input", update);
      input.removeEventListener("change", update);
      form?.removeEventListener("reset", reset);
      if (originalDescriptions) input.setAttribute("aria-describedby", originalDescriptions);
      else input.removeAttribute("aria-describedby");
      root.remove();
    });
    update();
  }

  document.querySelectorAll(fieldSelector).forEach(mount);
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "attributes" && record.target.matches(fieldSelector)) {
        record.target.dispatchEvent(new Event("input"));
      }
      record.addedNodes.forEach((node) => {
        if (!(node instanceof Element)) return;
        if (node.matches(fieldSelector)) mount(node);
        node.querySelectorAll(fieldSelector).forEach(mount);
      });
    }
    for (const [input, cleanup] of mounted) {
      if (!input.isConnected) {
        cleanup();
        mounted.delete(input);
      }
    }
  });
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["minlength"],
  });
  window.addEventListener("pagehide", (event) => {
    if (event.persisted) return;
    for (const cleanup of mounted.values()) cleanup();
    mounted.clear();
    observer.disconnect();
  });
})();
