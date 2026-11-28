/* Landing v2: "uma conversa, cinco registros" e demonstração por ramo.
   Sem rede, sem armazenamento, nada é enviado. Depende de window.SMEI_LANDING. */
(function () {
  'use strict';
  var D = window.SMEI_LANDING; if (!D) return;
  function el(t, c, x) { var e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; }

  /* ---- história: abas (setas do teclado, sem rodízio automático) ---- */
  var hist = document.getElementById('hist');
  if (hist) {
    var tabs = hist.querySelector('.h-tabs'), panel = hist.querySelector('.h-panel'), btns = [];
    var show = function (i, focus) {
      var s = D.historia[i];
      btns.forEach(function (b, n) { b.setAttribute('aria-selected', n === i); b.tabIndex = n === i ? 0 : -1; b.classList.toggle('done', n < i); });
      panel.innerHTML = ''; panel.setAttribute('aria-labelledby', 'ht-' + s.id);
      panel.appendChild(el('span', 'chip', s.area)); panel.appendChild(el('h3', '', s.titulo));
      var dl = el('dl', 'h-rows'); s.linhas.forEach(function (l) { var r = el('div'); r.appendChild(el('dt', '', l[0])); r.appendChild(el('dd', '', l[1])); dl.appendChild(r); });
      panel.appendChild(dl); panel.appendChild(el('p', 'm', s.nota));
      if (focus) btns[i].focus();
    };
    D.historia.forEach(function (s, i) {
      var b = el('button', 'h-tab'); b.type = 'button'; b.id = 'ht-' + s.id; b.setAttribute('role', 'tab'); b.setAttribute('aria-controls', 'h-panel');
      b.appendChild(el('i')); b.appendChild(el('span', '', s.rotulo));
      b.addEventListener('click', function () { show(i); });
      b.addEventListener('keydown', function (e) {
        var k = e.key, n = k === 'ArrowDown' || k === 'ArrowRight' ? i + 1 : k === 'ArrowUp' || k === 'ArrowLeft' ? i - 1 : null;
        if (n === null) return; e.preventDefault(); show((n + btns.length) % btns.length, true);
      });
      btns.push(b); tabs.appendChild(b);
    });
    show(0);
  }

  /* ---- demonstração por ramo ---- */
  var demo = document.getElementById('ramoDemo');
  if (demo) {
    var chips = demo.querySelector('.r-chips'), chat = demo.querySelector('.ph-body'), cur = D.ramos[0], op = [];
    var draw = function () {
      chat.innerHTML = ''; op = [];
      chat.appendChild(el('div', 'bub in', cur.msg));
      var sug = el('button', 'btn o sm', 'Ver sugestão de resposta'); sug.type = 'button'; chat.appendChild(sug);
      sug.addEventListener('click', function () {
        sug.remove();
        var b = el('div', 'bub sg'); b.appendChild(el('small', '', 'Sugestão · você revisa antes de usar')); b.appendChild(el('span', '', cur.sug)); chat.appendChild(b);
        var r = el('button', 'btn sm', 'Registrar como oportunidade'); r.type = 'button'; chat.appendChild(r);
        r.addEventListener('click', function () {
          r.remove(); var c = el('div', 'op'); c.appendChild(el('b', '', cur.cliente + ' · ' + cur.item)); c.appendChild(el('span', '', 'Interesse: quente · ' + cur.valor));
          chat.appendChild(c); chat.appendChild(el('p', 'tag-ex', 'Demonstração: nada foi enviado nem salvo.'));
        });
      });
      demo.querySelector('.ph-name').textContent = cur.cliente + ' (exemplo)';
    };
    D.ramos.forEach(function (r, i) {
      var b = el('button', 'r-chip', r.nome); b.type = 'button'; b.setAttribute('aria-pressed', i === 0);
      b.addEventListener('click', function () { cur = r; chips.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', x === b); }); draw(); });
      chips.appendChild(b);
    });
    draw();
  }
})();
