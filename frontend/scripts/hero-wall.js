/* Hero v3 · mural de telas de exemplo subindo continuamente (3 colunas, todas para cima, sem pausa no hover, sem clique).
   Tudo ilustrativo: dados fictícios, sem rede, nada é enviado. Depende de: #wall, .hero, .hfx, .wall-w, .mega.
   Versão anterior (com lightbox e pausa): hero-original/scripts/hero-wall.js */
(function () {
  'use strict';
  var wall = document.getElementById('wall'); if (!wall) return;
  var ww = wall.parentNode;                                  /* .wall-w: recebe --mx/--my/--sy */
  var root = document.documentElement;
  var hero = document.querySelector('.hero');
  var reduceMQ = matchMedia('(prefers-reduced-motion: reduce)');
  var calm = function () { return root.classList.contains('calm') || reduceMQ.matches; };

  /* ---------- peças ---------- */
  function ic(n, s) { s = s || 18; return '<svg class="i" width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="#i-' + n + '"/></svg>'; }
  function av(i, bg, fg) { return '<span class="av" style="background:' + bg + ';color:' + fg + '">' + i + '</span>'; }
  var L = av('E', '#e4dcff', '#4a3aa8'), B = av('R', '#dbe8ff', '#1d4fb8'), A = av('L', '#dcf3df', '#1e6a31'), J = av('M', '#fde4cf', '#9a4a0a'), BI = av('T', '#fbe0ec', '#a3235c');
  function bars(h) { return '<div class="bars">' + h.map(function (v, n) { return '<i style="height:' + v + '%;--n:' + n + '"></i>'; }).join('') + '</div>'; }

  /* ---------- ramo: os mesmos exemplos, com as palavras do negócio da pessoa (v22) ----------
     O texto-base fala de presentes e artesanato. Cada ramo troca só as palavras; a estrutura da tela é a mesma.
     A escolha fica em smei-ramo (mesmos ids da lista de áreas do onboarding, que já vem marcada). */
  var RAMOS = {
    presentes: null,
    comida: { quero: 'Quero encomendar o bolo.', separo: 'Separo o bolo para você?', leg: 'Caixa de doces do mês: brigadeiros, bolo de pote e docinhos. Chame no direct!', mes: 'Caixa de doces do mês', gift: 'Caixa de doces', cuid: 'Bolo de pote', esp: 'Caixa de brigadeiros', p1: 'Bolo de pote', p2: 'Brigadeiros', p2l: 'brigadeiros', post: 'Post dos brigadeiros', story: 'Story dos doces', div: 'Preparar a divulgação dos doces', pag: 'pagamento da encomenda', oKit: 'o bolo', doKit: 'do bolo', kit: 'bolo', ret: 'na retirada', retiro: 'Perfeito, busco amanhã!', conf: 'Confirmar retirada', ask: 'Ainda tem bolo de pote para sábado?', ans: 'Temos sim! Separo um para você?' },
    beleza: { quero: 'Quero marcar um horário.', separo: 'Reservo o horário para você?', leg: 'Pacote de beleza do mês: escova, hidratação e manicure. Chame no direct!', mes: 'Pacote de beleza do mês', gift: 'Pacote de beleza', cuid: 'Hidratação', esp: 'Pacote especial', p1: 'Escova e hidratação', p2: 'Esmalte gel', p2l: 'esmaltes', post: 'Post das unhas', story: 'Story da agenda', div: 'Preparar a divulgação da agenda', pag: 'pagamento do atendimento', oKit: 'o horário', doKit: 'do horário', kit: 'horário', ret: 'no dia', retiro: 'Perfeito, até amanhã!', conf: 'Confirmar horário', ask: 'Tem horário livre no sábado?', ans: 'Tenho às 14h. Reservo para você?' },
    moda: { quero: 'Quero comprar o conjunto.', separo: 'Separo o conjunto para você?', leg: 'Look de verão do mês: vestido, bolsa e sandália. Chame no direct!', mes: 'Look de verão do mês', gift: 'Look de verão', cuid: 'Vestido de linho', esp: 'Conjunto especial', p1: 'Vestido de linho', p2: 'Bolsa de palha', p2l: 'bolsa de palha', post: 'Post da bolsa', story: 'Story do look', div: 'Preparar a divulgação da coleção', pag: 'pagamento do conjunto', oKit: 'o conjunto', doKit: 'do conjunto', kit: 'conjunto', ret: 'na retirada', retiro: 'Perfeito, retiro amanhã!', conf: 'Confirmar retirada' },
    casa: { quero: 'Quero um orçamento.', separo: 'Reservo o horário para você?', leg: 'Serviço da semana: pintura, reparos e instalação. Chame no direct!', mes: 'Serviço da semana', gift: 'Pintura', cuid: 'Reparo elétrico', esp: 'Serviço especial', p1: 'Pintura de sala', p2: 'Tinta branca', p2l: 'tinta branca', post: 'Post do antes e depois', story: 'Story do antes e depois', div: 'Preparar a divulgação dos serviços', pag: 'pagamento do serviço', oKit: 'o serviço', doKit: 'do serviço', kit: 'serviço', ret: 'no dia do serviço', retiro: 'Perfeito, te espero amanhã!', conf: 'Confirmar visita', ask: 'Você consegue vir na sexta?', ans: 'Consigo sim, às 10h. Reservo para você?' }
  };
  var ramoId = (function () { try { var v = localStorage.getItem('smei-ramo'); return v && RAMOS[v] ? v : 'presentes'; } catch (e) { return 'presentes'; } })();
  function regras(r) {
    var a = [
      [/Quero comprar o kit\./g, r.quero], [/Separo o kit para você\?/g, r.separo],
      [/Kit de presente do mês: vela, sabonete e caixa artesanal/g, r.leg], [/Kit de presente do mês/g, r.mes],
      [/Kit de presente/g, r.gift], [/Kit de cuidados/g, r.cuid], [/Kit especial/g, r.esp], [/Kit presente/g, r.p1],
      [/Repor vela artesanal/g, 'Repor ' + r.p2l], [/Vela artesanal/g, r.p2], [/Post da vela/g, r.post],
      [/Story do kit/g, r.story], [/Preparar a divulgação do kit/g, r.div], [/pagamento do kit/g, r.pag],
      [/sobre o kit/g, 'sobre ' + r.oKit], [/do kit/g, r.doKit],
      [/na retirada/g, r.ret], [/Perfeito, retiro amanhã!/g, r.retiro], [/Confirmar retirada/g, r.conf], [/\bkit\b/g, r.kit]
    ];
    if (r.ask) a.push([/Ainda tem a camisa azul no M\?/g, r.ask], [/Ainda temos no M\. Separo uma para você\?/g, r.ans]);
    return a;
  }
  var regrasCache = {};
  function R(str) {
    var r = RAMOS[ramoId]; if (!r || str == null) return str;
    var a = regrasCache[ramoId] || (regrasCache[ramoId] = regras(r));
    for (var k = 0; k < a.length; k++) str = String(str).replace(a[k][0], a[k][1]);
    return str;
  }

  /* ---------- telas do mural (16 variações, 5 categorias) ---------- */
  var T = [
    /* conversas */
    { k: 'conversas', i: 'chat', n: 'Caixa Unificada', d: 'Responda sem trocar de app', h: '<div class="cd-h">' + L + 'Emilly<small>WhatsApp</small></div><div class="bb q1">Quero comprar o kit. Como pago?</div><div class="bb t q2">Pode ser Pix ou na retirada.</div><div class="bb q3">Perfeito, retiro amanhã!</div><div class="bb t q4">Combinado! Separo para você.</div>' },
    { k: 'conversas', i: 'chat', n: 'Atendimento', d: 'Tire dúvidas em segundos', h: '<div class="cd-h">' + A + 'Lyly<small>Instagram</small></div><div class="bb q1">Você atende na minha cidade?</div><div class="bb t q2">Atendo sim! Entrego no centro.</div><div class="bb q3">E qual o prazo?</div><div class="bb t q4">Até 2 dias úteis.</div>' },
    { k: 'conversas', i: 'spark', n: 'Assistente', d: 'Você revisa antes de enviar', h: '<div class="cd-h">' + J + 'Maiccon<small>Instagram</small></div><div class="bb">Ainda tem a camisa azul no M?</div><div class="ia"><b>Sugestão da IA</b>Oi, Maiccon! Ainda temos no M. Separo uma para você?<span class="a-shine">Revisar e enviar</span></div>' },
    { k: 'conversas', i: 'home', n: 'Início', d: 'O que merece atenção hoje', h: '<div class="cd-h">Para hoje</div><div class="ro"><i class="tk2 a-tick"></i><b>Responder a Emilly</b></div><div class="ro"><i class="tk2 ok"></i><b>Cobrar a Tawanny, R$ 180</b></div><div class="ro"><i class="tk2 a-tick" style="--n:1"></i><div><b>Repor vela artesanal</b><small>Restam 4 un.</small></div></div>' },
    /* clientes */
    { k: 'clientes', i: 'users', n: 'Clientes', d: 'O histórico de cada pessoa', h: '<div class="cd-h">Clientes<small>3 de 48</small></div><div class="ro a-row" style="--n:0">' + A + '<div><b>Lyly</b><small>Última compra R$ 120</small></div></div><div class="ro a-row" style="--n:1">' + BI + '<div><b>Tawanny</b><small>2 compras</small></div></div><div class="ro a-row" style="--n:2">' + B + '<div><b>Richard</b><small>Pediu orçamento</small></div></div>' },
    { k: 'clientes', i: 'bolt', n: 'Oportunidades', d: 'Quem merece um retorno hoje', h: '<div class="cd-h">Oportunidades</div><div class="ro">' + L + '<div><b>Emilly</b><small>Kit de presente</small></div><em class="y a-pulse">Quente</em></div><div class="ro">' + B + '<div><b>Richard</b><small>Orçamento</small></div><em class="b">Morno</em></div><div class="ro">' + A + '<div><b>Lyly</b><small>Perguntou o bairro</small></div><em style="background:var(--h2);color:var(--m)">Frio</em></div>' },
    { k: 'clientes', i: 'users', n: 'Perfil do cliente', d: 'Interesse e próximo passo', h: '<div class="cd-h">' + L + 'Emilly<small>3 compras</small></div><div class="m">Interesse</div><div class="ro"><b>Kit de cuidados</b></div><div class="m">Próximo passo</div><div class="ro"><b>Confirmar retirada</b><em class="b">Amanhã</em></div><div class="ro" style="margin-top:auto"><b>Cliente desde março</b></div>' },
    /* vendas */
    { k: 'vendas', i: 'cart', n: 'Vendas', d: 'Do pedido ao recebido', h: '<div class="cd-h">Venda #1042<small>Pix</small></div><div class="big">R$ 180,00</div><div class="ro"><div><b>Kit presente</b><small>1 un.</small></div><em>R$ 260</em></div><div class="ro"><div><b>Vela artesanal</b><small>2 un.</small></div><em class="b">R$ 120</em></div><div class="ro" style="margin-top:auto"><b>Recebido</b><em class="a-pulse">Pago</em></div>' },
    { k: 'vendas', i: 'cart', n: 'Cobranças', d: 'Quem ainda não pagou', h: '<div class="cd-h">Venda #1043<small>Pendente</small></div><div class="big">R$ 180,00</div><div class="ro">' + BI + '<div><b>Tawanny</b><small>Kit especial · 3 itens</small></div><em class="y">Pendente</em></div><div class="ia" style="margin-top:auto"><b>Lembrete pronto</b>Oi, Tawanny! Passando para lembrar do pagamento do kit.<span>Revisar lembrete</span></div>' },
    { k: 'vendas', i: 'check', n: 'Recibo', d: 'Pronto para conferir', h: '<div class="cd-h">Recibo<small>#1042</small></div><div class="rcp"><div><span>Kit presente</span><b>R$ 260,00</b></div><div><span>Vela artesanal</span><b>R$ 120,00</b></div><div><span>Pagamento</span><b>Pix</b></div></div><div class="ro" style="margin-top:auto"><b>Total</b><em class="a-pulse">R$ 180</em></div>' },
    /* dinheiro */
    { k: 'dinheiro', i: 'bars', n: 'Financeiro', d: 'Como o mês está indo', h: '<div class="cd-h">Este mês</div><div class="m">Saldo</div><div class="big">R$ 260</div><div class="ro"><b>Entrou</b><em>R$ 640</em></div><div class="ro"><b>Saiu</b><em class="y">R$ 380</em></div>' + bars([38, 55, 30, 70, 100, 62]) },
    { k: 'dinheiro', i: 'bars', n: 'A receber', d: 'O que ainda vai entrar', h: '<div class="cd-h">A receber<small>2 cobranças</small></div><div class="big">R$ 250</div><div class="ro">' + BI + '<div><b>Tawanny</b><small>Vence amanhã</small></div><em class="y">R$ 180</em></div><div class="ro">' + B + '<div><b>Richard</b><small>Vence sexta</small></div><em class="b">R$ 70</em></div>' },
    { k: 'dinheiro', i: 'bars', n: 'Resumo da semana', d: 'Seus dias de venda', h: '<div class="cd-h">Esta semana</div><div class="m">Entrou</div><div class="big">R$ 640</div>' + bars([30, 46, 62, 40, 88, 100, 54]) + '<div class="dw"><span>S</span><span>T</span><span>Q</span><span>Q</span><span>S</span><span>S</span><span>D</span></div>' },
    /* divulgação */
    { k: 'divulgacao', i: 'mega', n: 'Divulgação', d: 'Ideia de Story pronta', h: '<div class="cd-h">Ideia de hoje<small>Rascunho</small></div><div class="tile a-drift"><small>Story</small>Kit de presente do mês</div><div class="ro"><b>Revisar texto</b><em class="b">Abrir</em></div>' },
    { k: 'divulgacao', i: 'mega', n: 'Legenda pronta', d: 'Texto para você ajustar', h: '<div class="cd-h">Legenda<small>Rascunho</small></div><div class="ia"><b>Sugestão da IA</b>Kit de presente do mês: vela, sabonete e caixa artesanal. Chame no direct!</div><div class="sk"><i></i><i></i><i></i></div><div class="ro" style="margin-top:auto"><b>Revisar texto</b><em class="b">Abrir</em></div>' },
    { k: 'divulgacao', i: 'cal', n: 'Agenda de posts', d: 'A semana organizada', h: '<div class="cd-h">Esta semana</div><div class="ro"><em class="b">Qua</em><div><b>Story do kit</b><small>Rascunho</small></div></div><div class="ro"><em class="b">Sex</em><div><b>Post da vela</b><small>Rascunho</small></div></div><div class="ro"><em class="b">Sáb</em><div><b>Bastidores</b><small>Ideia</small></div></div>' }
  ];

  /* ---------- mural: 3 colunas em 3 profundidades (fundo, frente, meio), todas subindo ---------- */
  var ROLE = ['bk', 'fr', 'md'], DUR = { bk: 104, md: 84, fr: 68 }, OFF = [0, 29, 17];
  var ORDEM = [[0, 5, 8, 12, 15, 3], [10, 2, 7, 13, 4, 9], [11, 6, 1, 14, 8, 4]];   /* conversa → cliente → venda → dinheiro → divulgação */
  function item(t, ex, r) { return '<figure class="it" data-k="' + t.k + '" style="--r:' + r + '"' + (ex ? ' aria-hidden="true"' : '') + '><div class="cd">' + R(t.h) + '</div><figcaption class="ct"><span class="ci">' + ic(t.i) + '</span><b>' + t.n + '</b><span>' + t.d + '</span></figcaption></figure>'; }
  function buildWall() {
  var html = '';
  ORDEM.forEach(function (idx, c) {
    var a = idx.map(function (n, r) { return item(T[n], false, r); }).join('');
    var b = idx.map(function (n, r) { return item(T[n], true, r); }).join('');
    html += '<div class="trk ' + ROLE[c] + '" style="--ci:' + c + ';--dur:' + DUR[ROLE[c]] + 's;--dl:-' + OFF[c] + 's"><div class="cp">' + a + '</div><div class="cp" aria-hidden="true">' + b + '</div></div>';
  });
  wall.innerHTML = '<div class="wt">' + html + '</div>';
  }
  buildWall();
  /* API pública (premium-v5.js): trocar o ramo reescreve as palavras do mural. A subida continua; só o texto muda. */
  window.SMEI_RAMO = {
    get: function () { return ramoId; },
    R: function (str) { return R(str); },
    set: function (id) {
      var novo = RAMOS[id] ? id : 'presentes';
      if (novo === ramoId) return;
      ramoId = novo;
      if (calm()) { buildWall(); return; }
      wall.style.transition = 'opacity .18s'; wall.style.opacity = '0';
      setTimeout(function () { buildWall(); wall.style.opacity = '1'; }, 190);
    }
  };


  /* ---------- luz que segue o mouse (só atualiza o .hfx, que não tem filhos) e parallax leve na rolagem ---------- */
  var fx = hero && hero.querySelector('.hfx');
  if (hero && fx && matchMedia('(pointer:fine)').matches) {
    var raf = 0;
    hero.addEventListener('pointermove', function (e) {
      if (calm() || raf) return;
      raf = requestAnimationFrame(function () {
        raf = 0; var r = hero.getBoundingClientRect();
        fx.style.setProperty('--mx', Math.round(e.clientX - r.left) + 'px');
        fx.style.setProperty('--my', Math.round(e.clientY - r.top) + 'px');
      });
    }, { passive: true });
  }
  /* fora da tela, a animação do mural pausa (economiza GPU); isso não tem relação com o mouse */
  if (hero && 'IntersectionObserver' in window) new IntersectionObserver(function (e) { hero.classList.toggle('off', !e[0].isIntersecting); }).observe(hero);
  var sk = 0;
  addEventListener('scroll', function () {
    if (sk || calm()) return;
    sk = requestAnimationFrame(function () { sk = 0; if (scrollY < 1000) ww.style.translate = '0 ' + (-scrollY * 0.07).toFixed(1) + 'px'; });
  }, { passive: true });

  /* marca gigante do rodapé: letras sobem uma a uma */
  var mg = document.querySelector('.mega span');
  if (mg) mg.innerHTML = mg.textContent.split('').map(function (ch, n) { return '<i style="--n:' + n + '">' + ch + '</i>'; }).join('');
})();
