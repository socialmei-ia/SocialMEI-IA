/* Seções abaixo do hero: miniaturas vivas nos cards, passos sincronizados e brilho que segue o mouse.
   Tudo ilustrativo e local. O modo calmo e prefers-reduced-motion desligam as animações via CSS. */
(function () {
  'use strict';
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var av = function (t, bg, fg) { return '<span class="av" style="background:' + bg + ';color:' + fg + ';width:26px;height:26px;font-size:12px">' + t + '</span>'; };

  /* 1) Produto: uma miniatura animada em cada card */
  var V = [
    '<div class="bb q1">Quero o kit. Como pago?</div><div class="bb t q2">Pode ser Pix!</div><span class="tp" aria-hidden="true"><i></i><i></i><i></i></span>',
    '<div class="avs">' + av('A', '#dcf3df', '#2a7a3a') + av('B', '#fbe0ec', '#a3235c') + av('L', '#e4dcff', '#4a3aa8') + av('J', '#fde4cf', '#9a4a0a') + '<span class="more">+44</span></div><div class="ro a-row"><b>Histórico completo</b><em class="b">Abrir</em></div>',
    '<div class="trail"><span class="a-tick" style="--n:0"><i></i>Pedido</span><span class="a-tick" style="--n:.7"><i></i>Pix</span><span class="a-tick" style="--n:1.4"><i></i>Recebido</span></div>',
    '<div class="bars"><i style="height:38%;--n:0"></i><i style="height:55%;--n:1"></i><i style="height:30%;--n:2"></i><i style="height:70%;--n:3"></i><i style="height:100%;--n:4"></i><i style="height:62%;--n:5"></i><i style="height:80%;--n:6"></i></div>',
    '<div class="ro">' + av('L', '#e4dcff', '#4a3aa8') + '<div><b>Lia</b><small>Kit de presente</small></div><span class="cyc"><em>Frio</em><em class="b">Morno</em><em class="y">Quente</em></span></div>',
    '<div class="tile a-drift mini-t"><small>Story</small>Kit do mês</div>'
  ];
  $$('#produto .grid3 .card').forEach(function (c, i) {
    if (!V[i]) return;
    var v = document.createElement('div'); v.className = 'vis'; v.setAttribute('aria-hidden', 'true'); v.innerHTML = V[i];
    var f = c.lastElementChild;
    if (f && f.tagName === 'DIV') c.insertBefore(v, f); else c.appendChild(v);
  });

  /* 2) Como funciona: cada passo mostra o que acontece, em sequência (3s cada) */
  var D = [
    '<div class="fl"><i style="--w:72%;--n:0"></i></div><div class="fl"><i style="--w:90%;--n:1"></i></div><div class="fl"><i style="--w:50%;--n:2"></i></div><div class="bt">Criar meu espaço</div>',
    '<div class="chs"><span class="ch" style="--n:0">Roupas</span><span class="ch" style="--n:1">Doces</span><span class="ch" style="--n:2">Serviços</span></div><div class="sws"><i style="--n:3;background:#2f6bff"></i><i style="--n:4;background:#16a34a"></i><i style="--n:5;background:#f59e0b"></i><i style="--n:6;background:#a855f7"></i></div>',
    '<div class="ro in" style="--n:0"><i class="tk2 a-tick"></i><b>Responder a Lia</b></div><div class="ro in" style="--n:1"><i class="tk2 a-tick" style="--n:1"></i><b>Cobrar a Bia</b></div><div class="ro in" style="--n:2"><i class="tk2 a-tick" style="--n:2"></i><b>Repor vela</b></div>'
  ];
  $$('#como .step').forEach(function (s, i) {
    s.style.setProperty('--k', i);
    if (!D[i]) return;
    var d = document.createElement('div'); d.className = 'sdemo'; d.setAttribute('aria-hidden', 'true'); d.innerHTML = D[i]; s.appendChild(d);
  });

  /* 3) brilho que segue o mouse nos cards */
  $$('.grid3 .card, .steps .step').forEach(function (el) {
    el.addEventListener('pointermove', function (e) {
      var r = el.getBoundingClientRect();
      el.style.setProperty('--cx', (e.clientX - r.left) + 'px'); el.style.setProperty('--cy', (e.clientY - r.top) + 'px');
    });
  });

  /* 4) economiza bateria: pausa as animações das seções fora da tela */
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (es) { es.forEach(function (x) { x.target.classList.toggle('idle', !x.isIntersecting); }); }, { rootMargin: '80px' });
    $$('#produto, #paramei, #como').forEach(function (s) { io.observe(s); });
  }
})();
