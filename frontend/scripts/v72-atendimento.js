/* SocialMEI-IA · v7.2 · Atendimento: navegação por teclado na Caixa.
   Só interface: não cria endpoints, não envia nada e não grava dados.
   Alt+↓ / Alt+↑ abrem a próxima / anterior conversa da lista visível (respeitando filtros e a aba "Atenção").
   O foco do campo de resposta e os rascunhos não são tocados: a troca é a mesma navegação por link da lista. */
(function () {
  'use strict';
  if (window.SocialMEI72) return;
  function rows() { return [].slice.call(document.querySelectorAll('#v .cx4-rows a.ci')); }
  function go(dir) {
    var list = rows();
    if (!list.length) return false;
    var cur = list.findIndex(function (a) { return a.getAttribute('aria-current') === 'true'; });
    var next = cur < 0 ? (dir > 0 ? 0 : list.length - 1) : cur + dir;
    if (next < 0 || next >= list.length) return false;
    list[next].click();
    return true;
  }
  document.addEventListener('keydown', function (e) {
    if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || (e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) return;
    if (!/^#\/caixa(\/|$)/.test(location.hash)) return;
    if (document.querySelector('dialog[open]')) return;
    if (go(e.key === 'ArrowDown' ? 1 : -1)) e.preventDefault();
  });
  window.SocialMEI72 = { next: function () { return go(1); }, prev: function () { return go(-1); } };
})();
