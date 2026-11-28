/* SocialMEI-IA · v7.9.11 · Esmaecido lateral só quando há mais itens para rolar.
   Apresentação apenas: marca data-more="start|end|both" em faixas roláveis; não lê nem grava dados. */
window.SocialMEIVersion = "7.9.11";
(function () {
  "use strict";
  var SEL = ".lia-chips, .filters.ov, .g75-chips, .tabs, .ag-fl";
  var seen = new WeakSet();
  function mark(el) {
    var max = el.scrollWidth - el.clientWidth, x = Math.abs(el.scrollLeft);
    var more = max > 2 ? (x <= 2 ? "end" : x >= max - 2 ? "start" : "both") : "";
    if (more) { if (el.getAttribute("data-more") !== more) el.setAttribute("data-more", more); }
    else if (el.hasAttribute("data-more")) el.removeAttribute("data-more");
  }
  function bind(el) {
    if (seen.has(el)) { mark(el); return; }
    seen.add(el);
    el.addEventListener("scroll", function () { mark(el); }, { passive: true });
    if (window.ResizeObserver) new ResizeObserver(function () { mark(el); }).observe(el);
    mark(el);
  }
  var queued = false;
  function scan() { queued = false; document.querySelectorAll(SEL).forEach(bind); }
  function queue() { if (!queued) { queued = true; requestAnimationFrame(scan); } }
  new MutationObserver(queue).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("resize", queue, { passive: true });
  queue();
})();

/* Caixa: atalhos de teclado (apresentação/navegação; não altera conversas). J/K percorrem a lista, "/" busca. */
(function () {
  "use strict";
  function typing(t) { return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)); }
  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;
    if (!/^#\/caixa/.test(location.hash) || document.querySelector(".lia-panel.open, [role=dialog]:not([hidden])")) return;
    var rows = Array.prototype.slice.call(document.querySelectorAll(".cx4-rows a.ci"));
    if (e.key === "/") {
      var q = document.querySelector(".cx4-sr input");
      if (q) { e.preventDefault(); q.focus(); }
      return;
    }
    if (e.key !== "j" && e.key !== "k" || !rows.length) return;
    var i = rows.indexOf(document.activeElement);
    i = e.key === "j" ? Math.min(rows.length - 1, i + 1) : i < 0 ? 0 : Math.max(0, i - 1);
    e.preventDefault(); rows[i].focus(); rows[i].scrollIntoView({ block: "nearest" });
  });
  /* dica discreta no painel vazio da Caixa */
  new MutationObserver(function () {
    var w = document.querySelector(".cx4-wi");
    if (w && !w.querySelector(".v797-keys")) {
      var p = document.createElement("p");
      p.className = "m sm v797-keys";
      p.innerHTML = "Atalhos: <kbd>J</kbd> <kbd>K</kbd> percorrem as conversas, <kbd>/</kbd> busca.";
      w.appendChild(p);
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
