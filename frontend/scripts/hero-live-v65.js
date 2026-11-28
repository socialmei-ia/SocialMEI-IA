/* SocialMEI-IA · v6.5.1 · Hero: legenda que acompanha os módulos + brilho que segue o cursor.
   Substitui o feed de avisos flutuantes da v6.5 (cobria cartões do mural e competia com a leitura).
   Não toca no mural (movimento contínuo, sem pausa no hover, sem abrir imagens). A legenda sempre deixa claro que são
   telas ilustrativas. Movimento reduzido/modo calmo: legenda fixa e sem brilho animado. */
(function () {
  'use strict';
  var hero = document.querySelector('.hero.hx'); if (!hero) return;
  var root = document.documentElement, mq = matchMedia('(prefers-reduced-motion: reduce)');
  var calm = function () { return root.classList.contains('calm') || mq.matches; };

  /* ---- legenda ---- */
  var cap = hero.querySelector('.tag-ex');
  if (cap) {
    var LINES = ['Telas ilustrativas do app', 'Caixa Unificada: responda sem trocar de app', 'Clientes: o histórico de cada pessoa', 'Vendas: pedido e pagamento no mesmo lugar', 'Divulgação: ideia de Story pronta'];
    var txt = document.createElement('span'); txt.className = 'hl-cap'; txt.textContent = LINES[0];
    cap.textContent = ''; cap.appendChild(txt);
    var n = 0, t = 0;
    var next = function () {
      if (calm() || document.hidden) return;
      txt.classList.add('out');
      setTimeout(function () { n = (n + 1) % LINES.length; txt.textContent = LINES[n]; txt.classList.remove('out'); }, 320);
    };
    var loop = function () { clearInterval(t); if (!calm()) t = setInterval(next, 4600); };
    loop(); document.addEventListener('visibilitychange', loop);
    if (mq.addEventListener) mq.addEventListener('change', function () { loop(); if (calm()) { txt.textContent = LINES[0]; } });
  }

  /* ---- brilho que segue o cursor (só com mouse; leve: 1 variável CSS por quadro) ---- */
  if (!matchMedia('(hover:hover) and (pointer:fine)').matches) return;
  var raf = 0, px = 0, py = 0;
  hero.addEventListener('pointermove', function (e) {
    if (calm()) return;
    px = e.clientX; py = e.clientY;
    if (!raf) raf = requestAnimationFrame(function () {
      raf = 0; var r = hero.getBoundingClientRect();
      hero.style.setProperty('--gx', (px - r.left).toFixed(0) + 'px'); hero.style.setProperty('--gy', (py - r.top).toFixed(0) + 'px'); hero.classList.add('hl-glow');
    });
  }, { passive: true });
  hero.addEventListener('pointerleave', function () { hero.classList.remove('hl-glow'); });
})();
