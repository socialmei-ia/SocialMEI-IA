/* SocialMEI-IA · v6.2 · rede de segurança da narrativa da landing.
   Garante que nada fique escondido ou "pela metade" quando a pessoa rola depressa
   (End, arrastar a barra, fling no celular): tudo o que já entrou na tela ou ficou para trás é revelado.
   Não usa rede nem armazenamento. Respeita movimento reduzido. */
(function () {
  "use strict";
  var raf = 0;
  function pend() {
    return Array.prototype.slice.call(document.querySelectorAll(".rv:not(.on)"));
  }
  function flush() {
    raf = 0;
    var vh = window.innerHeight,
      list = pend();
    if (!list.length) {
      removeEventListener("scroll", onScroll);
      return;
    }
    list.forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.top < vh - 24) el.classList.add("on");
    });
  }
  function onScroll() {
    if (!raf) raf = requestAnimationFrame(flush);
  }
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("hashchange", onScroll);
  document.addEventListener("visibilitychange", onScroll);
  flush();
})();
