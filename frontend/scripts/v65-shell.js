/* SocialMEI-IA · v6.5 · Casca do app: marca, título da aba e barra lateral que "espia" ao passar o mouse.
   - Barra recolhida: ao parar o mouse sobre ela (≈130 ms) ou focar com o teclado, expande por cima da página
     SEM empurrar o conteúdo; sai ao tirar o mouse/foco. Não roda em toque nem com movimento reduzido no hover.
   - Marca: ícone no topo no celular (onde a logo lateral não aparece) e frase curta na logo expandida.
   - O título da aba é fixo e curto ("SocialMEI-IA | Seu negócio, mais simples"), definido no HTML. */
(function () {
  'use strict';
  var app = document.getElementById('app'); if (!app) return;
  var fine = matchMedia('(hover:hover) and (pointer:fine)');
  /* ---------- barra lateral: espiar com intenção, sem pulos ----------
     `col` é a preferência (recolhida); `peek` só abre a barra POR CIMA do conteúdo e nunca mexe no layout.
     Entrada com pequena espera (passar de raspão não abre) e saída com folga (sair e voltar rápido não pisca).
     Um aparelho de ponteiro fino e a tela larga são exigidos; toque usa só o botão de recolher/expandir. */
  var IN = 130, OUT = 240;
  var tIn = 0, tOut = 0, hover = false, focused = false, quiet = false, cur = null, free = 0;
  function side() { var a = app.firstElementChild; while (a && !(a.tagName === 'ASIDE' && !a.classList.contains('pn') && !a.classList.contains('cx'))) a = a.nextElementSibling; return a; }
  function wide() { return fine.matches && innerWidth > 900; }
  function held(a) { return !!a.querySelector('[aria-expanded="true"]:not(.mais)'); }
  function open() {
    clearTimeout(tIn); tIn = 0; clearTimeout(tOut); tOut = 0;
    var a = cur; if (!a || !a.classList.contains('col') || a.classList.contains('peek') || quiet || !wide()) return;
    a.classList.add('peek');
  }
  function close(force) {
    clearTimeout(tIn); tIn = 0; clearTimeout(tOut); tOut = 0;
    var a = cur; if (!a || !a.classList.contains('peek')) return;
    if (!force && (hover || focused || held(a))) return;
    a.classList.remove('peek');
  }
  function later() { clearTimeout(tOut); tOut = setTimeout(function () { tOut = 0; close(false); }, OUT); }
  function inside(t) { return !!(cur && t && t.nodeType === 1 && cur.contains(t)); }
  app.addEventListener('pointerover', function (e) {
    if (e.pointerType !== 'mouse' || !cur || !inside(e.target)) return;
    hover = true; clearTimeout(tOut); tOut = 0;
    if (quiet || tIn || !cur.classList.contains('col') || cur.classList.contains('peek') || !wide()) return;
    tIn = setTimeout(function () { tIn = 0; if (hover) open(); }, IN);
  }, { passive: true });
  app.addEventListener('pointerout', function (e) {
    if (e.pointerType !== 'mouse' || !cur || !inside(e.target) || inside(e.relatedTarget)) return;
    hover = false; quiet = false; clearTimeout(tIn); tIn = 0;
    if (cur.classList.contains('peek')) later();
  }, { passive: true });
  app.addEventListener('focusin', function (e) {
    if (!inside(e.target)) return;
    if (e.target.matches && e.target.matches(':focus-visible')) { focused = true; quiet = false; open(); }
  });
  app.addEventListener('focusout', function (e) {
    if (!inside(e.target) || inside(e.relatedTarget)) return;
    focused = false; if (cur.classList.contains('peek')) later();
  });
  app.addEventListener('click', function (e) { if (inside(e.target) && e.target.closest('a.nv')) { quiet = true; close(true); } });
  document.addEventListener('click', function () { if (cur && cur.classList.contains('peek') && !hover && !focused) later(); }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && cur && cur.classList.contains('peek')) { hover = false; focused = false; close(true); } });
  addEventListener('blur', function () { hover = false; if (cur && cur.classList.contains('peek')) later(); });
  /* sem trabalho em segundo plano: aba oculta fecha o que estiver espiando */
  document.addEventListener('visibilitychange', function () { if (document.hidden) { hover = false; close(true); } });

  /* O app redesenha #app inteiro a cada render e cria uma barra nova. Esta ponte devolve o estado
     (espiar em curso) ou anima a mudança (recolhimento automático da Caixa) em vez de "teletransportar". */
  function still(a, fn) { a.classList.add('sb-still'); fn(); void a.offsetWidth; a.classList.remove('sb-still'); }
  function adopt() {
    var a = side(), old = cur;
    if (a === old) return;
    cur = a;
    if (!a || !old || !wide()) return;
    var was = old.classList.contains('col'), want = a.classList.contains('col');
    if (old.classList.contains('peek') && want && hover) { still(a, function () { a.classList.add('peek'); }); return; }
    if (was !== want) {
      still(a, function () { a.classList.toggle('col', was); });
      void a.offsetWidth;
      a.classList.toggle('col', want);
    }
  }
  /* chamada pelo botão de recolher/expandir: limpa o espiar e evita reabrir logo após o clique */
  function toggled(a, isCol) {
    clearTimeout(tIn); clearTimeout(tOut); tIn = tOut = 0; quiet = true;
    if (a) a.classList.remove('peek');
    if (!wide()) return;
    var v = document.getElementById('v'), f = v && v.querySelector('iframe');
    if (!f) return;
    /* telas embutidas: congelar a largura final do quadro enquanto a barra anda (evita refazer a tela a cada quadro) */
    var p = document.createElement('i'); p.style.cssText = 'position:absolute;width:100px;height:0;visibility:hidden'; app.appendChild(p);
    var k = p.getBoundingClientRect().width / 100 || 1; p.remove();
    var w = app.getBoundingClientRect().width - (isCol ? 68 : 236) * k;
    if (w > 200) { f.style.width = Math.round(w) + 'px'; clearTimeout(free); free = setTimeout(function () { f.style.width = '100%'; }, 560); }
  }
  window.SMEISidebar = { toggled: toggled, peek: function () { return !!(cur && cur.classList.contains('peek')); } };
  cur = side();
  new MutationObserver(function () { adopt(); }).observe(app, { childList: true });
  matchMedia('(max-width:900px)').addEventListener('change', function () { if (cur) cur.classList.remove('peek'); });

  function paint() {
    var top = app.querySelector('.top');
    if (top && !top.querySelector('.top-mark')) {
      var m = new Image(); m.className = 'top-mark'; m.src = 'assets/icon-192.png'; m.alt = ''; m.width = 26; m.height = 26; m.setAttribute('aria-hidden', 'true');
      top.insertBefore(m, top.firstChild);
    }
    var lg = app.querySelector('aside .logo-l');
    if (lg && !lg.querySelector('.logo-tag')) { var s = document.createElement('span'); s.className = 'logo-tag'; s.textContent = 'Seu negócio, mais simples'; lg.appendChild(s); }
  }
  var raf = 0;
  new MutationObserver(function () { if (!raf) raf = requestAnimationFrame(function () { raf = 0; paint(); }); }).observe(app, { childList: true, subtree: true });
  /* ---------- aviso global de conexão (qualquer tela) ---------- */
  var ob = null, obT = 0;
  function net() {
    var off = navigator.onLine === false;
    if (off && !ob) {
      clearTimeout(obT);
      ob = document.createElement('div'); ob.className = 'sm-off'; ob.setAttribute('role', 'status');
      ob.textContent = 'Sem conexão com a internet. O que depende do servidor pode não ser salvo até a conexão voltar.';
      document.body.appendChild(ob);
    } else if (!off && ob) {
      var o = ob; ob = null; o.classList.add('ok'); o.textContent = 'Conexão restabelecida.';
      obT = setTimeout(function () { o.remove(); }, 2600);
    }
  }
  addEventListener('offline', net); addEventListener('online', net); net();
  /* ---------- "?" abre a lista de atalhos ---------- */
  var KEYS = [
    ['Ctrl K', 'Busca e ações rápidas em todo o app'],
    ['/', 'Buscar conversa (na Caixa)'],
    ['Alt ↑ ↓', 'Conversa anterior / seguinte'],
    ['Ctrl Enter', 'Salvar a resposta escrita'],
    ['Esc', 'Fechar menus e painéis abertos'],
    ['?', 'Mostrar esta lista']
  ];
  document.addEventListener('keydown', function (e) {
    if (e.key !== '?' || e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target; if (t && (/^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable)) return;
    if (document.querySelector('dialog.sm-keys[open]')) return;
    e.preventDefault();
    var d = document.createElement('dialog'); d.className = 'sm-keys'; d.setAttribute('aria-labelledby', 'sm-keys-h');
    var h = document.createElement('h2'); h.id = 'sm-keys-h'; h.textContent = 'Atalhos do teclado'; d.appendChild(h);
    var ul = document.createElement('ul');
    KEYS.forEach(function (k) {
      var li = document.createElement('li'), kb = document.createElement('span'), tx = document.createElement('span');
      k[0].split(' ').forEach(function (part, i) { if (part === '/' && i && k[0].indexOf('Alt') > -1) { var s = document.createElement('i'); s.textContent = 'ou'; kb.appendChild(s); return; } var c = document.createElement('kbd'); c.textContent = part; kb.appendChild(c); });
      tx.textContent = k[1]; li.append(kb, tx); ul.appendChild(li);
    });
    var b = document.createElement('button'); b.type = 'button'; b.className = 'btn o'; b.textContent = 'Fechar';
    b.addEventListener('click', function () { d.close(); });
    d.append(ul, b); document.body.appendChild(d);
    d.addEventListener('close', function () { d.remove(); });
    if (d.showModal) d.showModal(); else d.setAttribute('open', '');
    b.focus();
  });
  paint();
})();
