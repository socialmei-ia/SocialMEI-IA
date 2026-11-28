/* SocialMEI-IA · v6.5.1 · "Cada parte do negócio": avanço automático com controle da pessoa.
   - 8 s por módulo (tempo de leitura), só enquanto a seção está visível e a aba ativa.
   - Pausa enquanto o mouse está sobre a seção; qualquer clique, toque, tecla ou foco pausa e mantém pausado.
   - Botão "Pausar/Retomar avanço automático" sempre disponível (aria-pressed); a pessoa decide.
   - Não captura a rolagem. Com movimento reduzido ou modo calmo não há avanço automático (e nem botão). */
(function () {
  'use strict';
  var pv = document.getElementById('pvx'); if (!pv) return;
  var root = document.documentElement, mq = matchMedia('(prefers-reduced-motion: reduce)');
  if (root.classList.contains('calm') || mq.matches) return;
  var tabs = Array.prototype.slice.call(pv.querySelectorAll('.pv-t')), stage = pv.querySelector('.pv-stage'), idx = pv.querySelector('.pv-idx');
  if (tabs.length < 2 || !stage) return;
  var DUR = 8000, timer = 0, visible = false, paused = false, hover = false;

  var ctl = document.createElement('button'); ctl.type = 'button'; ctl.className = 'pv-ctl';
  var ICON_P = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';
  var ICON_R = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>';
  function paintCtl() { ctl.setAttribute('aria-pressed', String(paused)); ctl.innerHTML = (paused ? ICON_R : ICON_P) + '<span>' + (paused ? 'Retomar avanço automático' : 'Pausar avanço automático') + '</span>'; }
  stage.insertAdjacentElement('afterend', ctl);

  function cur() { for (var i = 0; i < tabs.length; i++) if (tabs[i].getAttribute('aria-selected') === 'true') return i; return 0; }
  function reveal(t) { if (idx && idx.scrollWidth > idx.clientWidth) idx.scrollLeft = Math.max(0, t.offsetLeft - (idx.clientWidth - t.offsetWidth) / 2); }
  function arm() {
    clearTimeout(timer);
    var run = !paused && !hover && visible && !document.hidden;
    pv.classList.toggle('auto', run); if (!run) return;
    pv.style.setProperty('--pv-dur', DUR + 'ms');
    timer = setTimeout(function () { var t = tabs[(cur() + 1) % tabs.length]; t.dataset.auto = '1'; t.click(); reveal(t); arm(); }, DUR);
  }
  function pause() { if (paused) return; paused = true; paintCtl(); arm(); }
  ctl.addEventListener('click', function () { paused = !paused; paintCtl(); arm(); });
  ['pointerdown', 'keydown', 'focusin', 'touchstart'].forEach(function (e) {
    pv.addEventListener(e, function (ev) { if (ev.target === ctl || ctl.contains(ev.target)) return; if (ev.target && ev.target.dataset && ev.target.dataset.auto) return; pause(); }, true);
  });
  pv.addEventListener('pointerenter', function (e) { if (e.pointerType === 'mouse') { hover = true; arm(); } });
  pv.addEventListener('pointerleave', function (e) { if (e.pointerType === 'mouse') { hover = false; arm(); } });
  tabs.forEach(function (t) { t.addEventListener('click', function () { delete t.dataset.auto; }); });
  if ('IntersectionObserver' in window) new IntersectionObserver(function (es) { visible = es[0].isIntersecting && es[0].intersectionRatio > .45; arm(); }, { threshold: [0, .45, .7] }).observe(stage);
  document.addEventListener('visibilitychange', arm);
  paintCtl();
})();
