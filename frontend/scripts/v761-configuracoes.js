/* Configurações · v7.6.1 — acabamento do painel (idempotente).
   A estrutura (menu em três grupos e um único painel por categoria) é gerada por config() no HTML.
   Aqui só: estado "sem alterações" dos campos, aviso de demonstração, transição entre categorias,
   foco/rolagem do menu no celular e setas do teclado no menu. Nenhuma requisição, nenhum listener repetido. */
(() => {
  "use strict";
  if (window.SocialMEIv761) return;
  const remote = () => !!window.SocialMEIAuth?.remote;
  let lastCat = null, queued = false;

  function decorate() {
    queued = false;
    const panel = document.querySelector("#v .cfg-panel");
    if (!panel || panel.dataset.v761) return;
    panel.dataset.v761 = "1";
    /* base para a barra "Alterações não salvas" (v76) */
    panel.querySelectorAll("input:not([type=checkbox]):not([type=radio]):not([type=file]),select,textarea").forEach((x) => { x.dataset.v0 = x.value; });
    if (!remote() && !panel.querySelector(".cfg-demo")) {
      const p = document.createElement("p");
      p.className = "cfg-demo";
      p.textContent = "Modo demonstração: o que você ajustar fica só neste navegador.";
      panel.prepend(p);
    }
    const cat = panel.dataset.cat;
    if (lastCat !== null && lastCat !== cat) panel.classList.add("is-enter");
    lastCat = cat;
    const on = document.querySelector("#v .cfg-nav .cfg-it.on");
    if (on && matchMedia("(max-width:900px)").matches) {
      const nav = on.closest(".cfg-nav");
      if (nav) nav.scrollLeft = Math.max(0, on.offsetLeft - (nav.clientWidth - on.offsetWidth) / 2);
    }
  }
  const schedule = () => { if (!queued) { queued = true; requestAnimationFrame(decorate); } };
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("hashchange", () => { if (!location.hash.startsWith("#/config")) lastCat = null; });

  /* setas no menu de categorias */
  document.addEventListener("keydown", (e) => {
    const a = e.target.closest?.(".cfg-nav .cfg-it");
    if (!a || !["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
    const items = [...a.closest(".cfg-nav").querySelectorAll(".cfg-it")], i = items.indexOf(a);
    const next = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : i + (e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1);
    if (items[next]) { e.preventDefault(); items[next].focus(); }
  });

  window.SocialMEIv761 = { version: "7.6.1" };
  schedule();
})();
