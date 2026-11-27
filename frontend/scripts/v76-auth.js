/* SocialMEI-IA v7.6 · acabamento das telas de entrada: aviso sem conexão, resumo de erros com foco e estado de processamento.
   Não altera validações, contratos nem fluxos de entrada.js. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const off = document.createElement("div");
  off.className = "a76-off"; off.hidden = true; off.setAttribute("role", "status");
  off.textContent = "Você está sem conexão. Reconecte para entrar ou criar a conta.";
  document.body.prepend(off);
  const sync = () => { off.hidden = navigator.onLine !== false; };
  addEventListener("online", sync); addEventListener("offline", sync); sync();
  document.addEventListener("submit", (e) => {
    const f = e.target; if (!f?.matches?.("form")) return;
    setTimeout(() => {
      f.querySelector(".a76-sum")?.remove();
      const bad = [...f.querySelectorAll('[aria-invalid="true"]')].filter((x) => x.offsetParent);
      if (!bad.length) return;
      const box = document.createElement("div");
      box.className = "a76-sum"; box.setAttribute("role", "alert"); box.tabIndex = -1;
      const lab = (x) => ($(`label[for="${x.id}"]`, f)?.childNodes[0]?.textContent || x.name || "campo").trim();
      box.innerHTML = `<b>Revise ${bad.length === 1 ? "1 campo" : bad.length + " campos"} para continuar:</b> ` + bad.map((x) => `<a href="#${x.id}">${lab(x)}</a>`).join(", ");
      box.addEventListener("click", (ev) => { const a = ev.target.closest("a"); if (a) { ev.preventDefault(); $("#" + a.getAttribute("href").slice(1))?.focus(); } });
      f.prepend(box); bad[0].focus();
    }, 0);
  }, true);
  document.addEventListener("input", (e) => { const s = e.target.form?.querySelector(".a76-sum"); if (s && e.target.getAttribute("aria-invalid") !== "true") s.querySelector(`a[href="#${e.target.id}"]`)?.remove(); if (s && !s.querySelector("a")) s.remove(); });
})();
