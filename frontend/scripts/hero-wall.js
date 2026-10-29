/* Hero da porta de entrada · v20 "balcão vivo"
   Mural de telas de exemplo + cena protagonista + campo que "digita".
   Tudo ilustrativo: dados fictícios, sem rede, sem armazenamento, nada é enviado.
   Depende de: #wall, .chips [data-f], #hwToast, #cmdT, .hero, .mega, .wall-w (+ #stage, .cmd).
   Para reverter para a v19: restaure o arquivo anterior (hero-wall.js) e a marcação do hero. */
(function () {
  'use strict';
  var wall = document.getElementById('wall'); if (!wall) return;
  var ww = wall.parentNode;                                  /* .wall-w: recebe --mx/--my/--sy */
  var root = document.documentElement;
  var hero = document.querySelector('.hero');
  var stage = document.getElementById('stage');
  var tb = document.getElementById('hwToast');
  var el = document.getElementById('cmdT');
  var cmd = document.querySelector('.cmd');
  var reduceMQ = matchMedia('(prefers-reduced-motion: reduce)');
  var calm = function () { return root.classList.contains('calm') || reduceMQ.matches; };
  var paused = function () { return document.hidden || (hero && hero.classList.contains('off')); };

  /* ---------- peças ---------- */
  function ic(n, s) { s = s || 18; return '<svg class="i" width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="#i-' + n + '"/></svg>'; }
  function av(i, bg, fg) { return '<span class="av" style="background:' + bg + ';color:' + fg + '">' + i + '</span>'; }
  var L = av('L', '#e4dcff', '#4a3aa8'), B = av('B', '#dbe8ff', '#1d4fb8'), A = av('A', '#dcf3df', '#2a7a3a'), J = av('J', '#fde4cf', '#9a4a0a'), BI = av('B', '#fbe0ec', '#a3235c');
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
    { k: 'conversas', i: 'chat', n: 'Caixa Unificada', d: 'Responda sem trocar de app', h: '<div class="cd-h">' + L + 'Lia<small>WhatsApp</small></div><div class="bb q1">Quero comprar o kit. Como pago?</div><div class="bb t q2">Pode ser Pix ou na retirada.</div><div class="bb q3">Perfeito, retiro amanhã!</div><div class="bb t q4">Combinado! Separo para você.</div>' },
    { k: 'conversas', i: 'chat', n: 'Atendimento', d: 'Tire dúvidas em segundos', h: '<div class="cd-h">' + A + 'Ana<small>Instagram</small></div><div class="bb q1">Você atende na minha cidade?</div><div class="bb t q2">Atendo sim! Entrego no centro.</div><div class="bb q3">E qual o prazo?</div><div class="bb t q4">Até 2 dias úteis.</div>' },
    { k: 'conversas', i: 'spark', n: 'Assistente', d: 'Você revisa antes de enviar', h: '<div class="cd-h">' + J + 'Juliana<small>Instagram</small></div><div class="bb">Ainda tem a camisa azul no M?</div><div class="ia"><b>Sugestão da IA</b>Oi, Juliana! Ainda temos no M. Separo uma para você?<span class="a-shine">Revisar e enviar</span></div>' },
    { k: 'conversas', i: 'home', n: 'Início', d: 'O que merece atenção hoje', h: '<div class="cd-h">Para hoje</div><div class="ro"><i class="tk2 a-tick"></i><b>Responder a Lia</b></div><div class="ro"><i class="tk2 ok"></i><b>Cobrar a Bia, R$ 180</b></div><div class="ro"><i class="tk2 a-tick" style="--n:1"></i><div><b>Repor vela artesanal</b><small>Restam 4 un.</small></div></div>' },
    /* clientes */
    { k: 'clientes', i: 'users', n: 'Clientes', d: 'O histórico de cada pessoa', h: '<div class="cd-h">Clientes<small>3 de 48</small></div><div class="ro a-row" style="--n:0">' + A + '<div><b>Ana</b><small>Última compra R$ 120</small></div></div><div class="ro a-row" style="--n:1">' + BI + '<div><b>Bia</b><small>2 compras</small></div></div><div class="ro a-row" style="--n:2">' + B + '<div><b>Bruno</b><small>Pediu orçamento</small></div></div>' },
    { k: 'clientes', i: 'bolt', n: 'Oportunidades', d: 'Quem merece um retorno hoje', h: '<div class="cd-h">Oportunidades</div><div class="ro">' + L + '<div><b>Lia</b><small>Kit de presente</small></div><em class="y a-pulse">Quente</em></div><div class="ro">' + B + '<div><b>Bruno</b><small>Orçamento</small></div><em class="b">Morno</em></div><div class="ro">' + A + '<div><b>Ana</b><small>Perguntou o bairro</small></div><em style="background:var(--h2);color:var(--m)">Frio</em></div>' },
    { k: 'clientes', i: 'users', n: 'Perfil do cliente', d: 'Interesse e próximo passo', h: '<div class="cd-h">' + L + 'Lia<small>3 compras</small></div><div class="m">Interesse</div><div class="ro"><b>Kit de cuidados</b></div><div class="m">Próximo passo</div><div class="ro"><b>Confirmar retirada</b><em class="b">Amanhã</em></div><div class="ro" style="margin-top:auto"><b>Cliente desde março</b></div>' },
    /* vendas */
    { k: 'vendas', i: 'cart', n: 'Vendas', d: 'Do pedido ao recebido', h: '<div class="cd-h">Venda #1042<small>Pix</small></div><div class="big">R$ 380,00</div><div class="ro"><div><b>Kit presente</b><small>1 un.</small></div><em>R$ 260</em></div><div class="ro"><div><b>Vela artesanal</b><small>2 un.</small></div><em class="b">R$ 120</em></div><div class="ro" style="margin-top:auto"><b>Recebido</b><em class="a-pulse">Pago</em></div>' },
    { k: 'vendas', i: 'cart', n: 'Cobranças', d: 'Quem ainda não pagou', h: '<div class="cd-h">Venda #1043<small>Pendente</small></div><div class="big">R$ 180,00</div><div class="ro">' + BI + '<div><b>Bia</b><small>Kit especial · 3 itens</small></div><em class="y">Pendente</em></div><div class="ia" style="margin-top:auto"><b>Lembrete pronto</b>Oi, Bia! Passando para lembrar do pagamento do kit.<span>Revisar lembrete</span></div>' },
    { k: 'vendas', i: 'check', n: 'Recibo', d: 'Pronto para conferir', h: '<div class="cd-h">Recibo<small>#1042</small></div><div class="rcp"><div><span>Kit presente</span><b>R$ 260,00</b></div><div><span>Vela artesanal</span><b>R$ 120,00</b></div><div><span>Pagamento</span><b>Pix</b></div></div><div class="ro" style="margin-top:auto"><b>Total</b><em class="a-pulse">R$ 380</em></div>' },
    /* dinheiro */
    { k: 'dinheiro', i: 'bars', n: 'Financeiro', d: 'Como o mês está indo', h: '<div class="cd-h">Este mês</div><div class="m">Saldo</div><div class="big">R$ 260</div><div class="ro"><b>Entrou</b><em>R$ 640</em></div><div class="ro"><b>Saiu</b><em class="y">R$ 380</em></div>' + bars([38, 55, 30, 70, 100, 62]) },
    { k: 'dinheiro', i: 'bars', n: 'A receber', d: 'O que ainda vai entrar', h: '<div class="cd-h">A receber<small>2 cobranças</small></div><div class="big">R$ 250</div><div class="ro">' + BI + '<div><b>Bia</b><small>Vence amanhã</small></div><em class="y">R$ 180</em></div><div class="ro">' + B + '<div><b>Bruno</b><small>Vence sexta</small></div><em class="b">R$ 70</em></div>' },
    { k: 'dinheiro', i: 'bars', n: 'Resumo da semana', d: 'Seus dias de venda', h: '<div class="cd-h">Esta semana</div><div class="m">Entrou</div><div class="big">R$ 640</div>' + bars([30, 46, 62, 40, 88, 100, 54]) + '<div class="dw"><span>S</span><span>T</span><span>Q</span><span>Q</span><span>S</span><span>S</span><span>D</span></div>' },
    /* divulgação */
    { k: 'divulgacao', i: 'mega', n: 'Divulgação', d: 'Ideia de Story pronta', h: '<div class="cd-h">Ideia de hoje<small>Rascunho</small></div><div class="tile a-drift"><small>Story</small>Kit de presente do mês</div><div class="ro"><b>Revisar texto</b><em class="b">Abrir</em></div>' },
    { k: 'divulgacao', i: 'mega', n: 'Legenda pronta', d: 'Texto para você ajustar', h: '<div class="cd-h">Legenda<small>Rascunho</small></div><div class="ia"><b>Sugestão da IA</b>Kit de presente do mês: vela, sabonete e caixa artesanal. Chame no direct!</div><div class="sk"><i></i><i></i><i></i></div><div class="ro" style="margin-top:auto"><b>Revisar texto</b><em class="b">Abrir</em></div>' },
    { k: 'divulgacao', i: 'cal', n: 'Agenda de posts', d: 'A semana organizada', h: '<div class="cd-h">Esta semana</div><div class="ro"><em class="b">Qua</em><div><b>Story do kit</b><small>Rascunho</small></div></div><div class="ro"><em class="b">Sex</em><div><b>Post da vela</b><small>Rascunho</small></div></div><div class="ro"><em class="b">Sáb</em><div><b>Bastidores</b><small>Ideia</small></div></div>' }
  ];

  /* ---------- mural: 5 colunas em 3 camadas (fundo, meio, frente) ---------- */
  var ROLE = ['bk', 'md', 'fr', 'md', 'bk'], DUR = { bk: 112, md: 90, fr: 72 }, OFF = [0, 37, 14, 52, 26];
  function item(t, ex, cls, r) { return '<figure class="it' + cls + '" data-k="' + t.k + '" style="--r:' + r + '"' + (ex ? ' aria-hidden="true"' : '') + '><div class="cd">' + R(t.h) + '</div><figcaption class="ct"><span class="ci">' + ic(t.i) + '</span><b>' + t.n + '</b><span>' + t.d + '</span></figcaption></figure>'; }
  function listFor(f, c) {
    var out = [], k, idx = [];
    if (f === 'tudo') { for (k = 0; k < 6; k++) idx.push([(c * 5 + k * 7) % T.length, '']); }
    else {
      var M = [], O = [];
      T.forEach(function (t, n) { (t.k === f ? M : O).push(n); });
      for (k = 0; k < 3; k++) idx.push([M[(c + k) % M.length], ' hot']);
      for (k = 0; k < 3; k++) idx.push([O[(c * 3 + k * 4) % O.length], ' dim']);
    }
    idx.forEach(function (x, r) { out.push([T[x[0]], x[1], r]); });
    return out;
  }
  function cols(f) {
    var html = '';
    for (var c = 0; c < 5; c++) {
      var list = listFor(f, c);
      var a = list.map(function (x) { return item(x[0], false, x[1], x[2]); }).join('');
      var b = list.map(function (x) { return item(x[0], true, x[1], x[2]); }).join('');
      html += '<div class="trk ' + ROLE[c] + (c % 2 ? ' rv2' : '') + '" style="--ci:' + c + ';--dur:' + DUR[ROLE[c]] + 's;--dl:' + (f === 'tudo' ? '-' + OFF[c] + 's' : '0s') + '"><div class="cp">' + a + '</div><div class="cp" aria-hidden="true">' + b + '</div></div>';
    }
    return html;
  }
  wall.innerHTML = '<div class="wt">' + cols('tudo') + '</div>';
  var wt = wall.firstChild, curF = 'tudo', dealT = 0;

  /* troca de filtro: o mural se redistribui (as telas da categoria sobem, as outras recuam) */
  function deal(f) {
    clearTimeout(dealT);
    if (calm()) { wt.innerHTML = cols(f); return; }
    wall.classList.add('out');
    dealT = setTimeout(function () {
      wt.classList.remove('deal'); wt.innerHTML = cols(f); void wt.offsetWidth;
      wt.classList.add('deal'); wall.classList.remove('out');
      dealT = setTimeout(function () { wt.classList.remove('deal'); }, 2000);
    }, 200);
  }

  /* ---------- cena protagonista: conta a história e responde ao que o campo "digita" ---------- */
  var DW = 5600;                                              /* tempo de cada cena (ms) */
  function head(l, a, b) { return '<div class="sg-t">' + (l || '') + '<b>' + a + '</b><span>' + b + '</span></div>'; }
  function ok(t, s) { return '<div class="sg-ok sb" style="--t:' + s + 's"><span class="sg-ck">' + ic('check', 13) + '</span>' + t + '</div>'; }
  var SC = [
    { cat: 'conversas', say: ['Responder a Lia sobre o kit', 'Quem está esperando resposta?'], pre: true, toast: ['chat', 'Nova mensagem', 'Lia perguntou do kit · exemplo'],
      h: function () { return head(L, 'Lia', 'WhatsApp') + '<div class="bb sb" style="--t:.2s">Quero comprar o kit. Como pago?</div><div class="sg-slot"><div class="sg-d sb-x" style="--t:.9s"><i></i><i></i><i></i></div><div class="ia sb" style="--t:2.1s"><b>' + ic('spark', 13) + ' Sugestão da IA</b>Pode ser Pix ou na retirada. Separo o kit para você?<span class="a-shine">Revisar e enviar</span></div></div>'; } },
    { cat: 'vendas', say: ['Registrar venda de R$ 180', 'Anotar a venda da Lia'], toast: ['cart', 'Venda registrada', 'R$ 180,00 · exemplo'],
      h: function () { return head('', 'Venda #1042', 'Pix') + '<div class="big sb" style="--t:.15s">R$ 180,00</div><div class="ro sb" style="--t:.45s"><div><b>Kit presente</b><small>1 un.</small></div><em class="b">R$ 180</em></div><div class="ro sb" style="--t:.65s">' + L + '<div><b>Lia</b><small>Cliente</small></div></div>' + ok('Venda registrada', 1.3); } },
    { cat: 'vendas', say: ['Preparar o recibo da Lia', 'Gerar o recibo'], toast: ['check', 'Recibo pronto', 'Para você revisar · exemplo'],
      h: function () { return head('', 'Recibo', '#1042') + '<div class="rcp sb" style="--t:.15s"><div><span>Kit presente</span><b>R$ 180,00</b></div><div><span>Pagamento</span><b>Pix</b></div><div><span>Cliente</span><b>Lia</b></div><i class="sg-stamp">Pago</i></div><div class="ia sb" style="--t:1.5s"><b>' + ic('check', 13) + ' Recibo pronto</b>Você confere antes de enviar.</div>'; } },
    { cat: 'clientes', say: ['Lembrar a Bia amanhã', 'Avisar a Bia do pagamento'], toast: ['cal', 'Lembrete pronto', 'Avisar a Bia amanhã · exemplo'],
      h: function () { return head('', 'Lembrete', 'Agenda') + '<div class="ro sb" style="--t:.2s">' + BI + '<div><b>Bia</b><small>Pagamento de R$ 180</small></div><em class="y">Amanhã, 9h</em></div><div class="ia sb" style="--t:1s"><b>' + ic('spark', 13) + ' Rascunho para revisar</b>Oi, Bia! Passando para lembrar do pagamento do kit.<span class="a-shine">Revisar lembrete</span></div>'; } },
    { cat: 'divulgacao', say: ['Criar um Story para o fim de semana', 'Preparar a divulgação do kit'], toast: ['mega', 'Ideia pronta', 'Story do fim de semana · exemplo'],
      h: function () { return head('', 'Ideia de hoje', 'Rascunho') + '<div class="tile a-drift sb" style="--t:.2s"><small>Story</small>Kit de presente do mês</div><div class="sk sb" style="--t:.9s"><i></i><i></i></div><div class="ro sb" style="--t:1.2s"><b>Revisar texto</b><em class="b">Abrir</em></div>'; } },
    { cat: 'dinheiro', say: ['Quanto entrou este mês?', 'Como está o saldo?'], toast: ['bars', 'Saldo atualizado', 'R$ 260 este mês · exemplo'],
      h: function () { return head('', 'Este mês', 'Resumo') + '<div class="m sb" style="--t:.1s">Saldo</div><div class="big sb" style="--t:.2s">R$ 260</div><div class="ro sb" style="--t:.5s"><b>Entrou</b><em>R$ 640</em></div><div class="ro sb" style="--t:.65s"><b>Saiu</b><em class="y">R$ 380</em></div>' + bars([38, 55, 30, 70, 100, 62]); } }
  ];
  function frame(sc, say, i, n) {
    var p = ''; for (var k = 0; k < n; k++) p += '<i class="' + (k < i ? 'd' : k === i ? 'a' : '') + '"></i>';
    return '<div class="sg-in" style="--dw:' + DW + 'ms"><div class="sg-p">' + p + '</div><div class="sg-q">' + ic('spark', 14) + '<span>' + say + '</span></div>' + R(sc.h()) + '<div class="sg-f">Exemplo com dados fictícios: nada é enviado.</div></div>';
  }

  var tok = 0, list = SC, idx = 0, said = {};
  function go(t, fn, ms) {                                    /* espera ms e só segue se o hero está visível */
    setTimeout(function () { (function chk() { if (t !== tok) return; if (paused()) return void setTimeout(chk, 400); fn(); })(); }, ms);
  }
  function toast(n) {
    if (!tb) return;
    tb.className = 'hwt'; void tb.offsetWidth;
    tb.innerHTML = '<span class="ti">' + ic(n[0], 20) + '</span><div><b>' + R(n[1]) + '</b><small>' + R(n[2]) + '</small></div>';
  }
  function toastOut(t) { go(t, function () { if (tb) tb.classList.add('bye'); }, 3300); }
  function type(text, t, done) {
    var n = 0; el.textContent = ''; el.classList.add('typing');
    (function s() {
      if (t !== tok) return; if (paused()) return void setTimeout(s, 300);
      n++; el.textContent = text.slice(0, n);
      if (n < text.length) setTimeout(s, 32 + Math.random() * 34); else done();
    })();
  }
  function erase(t, done) {
    (function e() {
      if (t !== tok) return; var s = el.textContent;
      if (!s.length) { el.classList.remove('typing'); return done(); }
      el.textContent = s.slice(0, -1); setTimeout(e, 12);
    })();
  }
  function play(t) {
    if (t !== tok) return;
    var i = idx % list.length, sc = list[i]; idx++;
    var say = R(sc.say[(said[sc.cat] = (said[sc.cat] || 0)) % sc.say.length]); said[sc.cat]++;
    if (sc.pre && tb) { toast(sc.toast); toastOut(t); }
    type(say, t, function () {
      if (cmd) { cmd.classList.remove('sent'); void cmd.offsetWidth; cmd.classList.add('sent'); }
      if (stage) { stage.className = 'sg'; stage.innerHTML = frame(sc, say, i, list.length); }
      if (!sc.pre) go(t, function () { toast(sc.toast); toastOut(t); }, 900);
      go(t, function () {
        if (stage) stage.classList.add('out');
        if (tb && !tb.classList.contains('bye')) tb.classList.add('bye');
        erase(t, function () { go(t, function () { play(t); }, 380); });
      }, DW);
    });
  }
  function start(f, delay) {
    tok++; var t = tok; idx = 0;
    list = f === 'tudo' ? SC : SC.filter(function (s) { return s.cat === f; });
    if (!el) return;
    if (stage) { stage.className = 'sg out'; }
    if (tb) tb.classList.add('bye');
    el.textContent = ''; el.classList.remove('typing');
    go(t, function () { play(t); }, delay);
  }
  /* modo estático (modo calmo ou movimento reduzido): tudo parado e legível */
  function still() {
    tok++; if (!el) return;
    el.classList.remove('typing'); el.textContent = 'O que vamos cuidar hoje?';
    var sc = SC[0]; list = SC; if (stage) { stage.className = 'sg'; stage.innerHTML = frame(sc, R(sc.say[0]), 0, SC.length); }
    if (tb) { toast(sc.toast); }
  }

  /* ---------- filtros ---------- */
  document.querySelector('.chips').addEventListener('click', function (e) {
    var b = e.target.closest('[data-f]'); if (!b) return;
    var f = b.dataset.f;
    document.querySelectorAll('.chips [data-f]').forEach(function (x) { x.setAttribute('aria-pressed', x === b); });
    if (f === curF) return;
    curF = f; deal(f);
    if (calm()) still(); else start(f, 700);
  });

  /* ---------- ramo (v22): troca as palavras do mural e da cena, e lembra a escolha ---------- */
  var selRamo = document.getElementById('ramo');
  if (selRamo) {
    selRamo.value = ramoId;
    selRamo.addEventListener('change', function () {
      ramoId = RAMOS.hasOwnProperty(selRamo.value) ? selRamo.value : 'presentes';
      try { localStorage.setItem('smei-ramo', ramoId); } catch (e) {}
      deal(curF);
      if (calm()) still(); else start(curF, 700);
    });
  }

  /* ---------- lista de ramos própria (v24): o seletor do navegador não aceita estilo ----------
     O <select> continua no HTML como base (e funciona sozinho se este script falhar);
     aqui ele ganha uma lista bonita por cima e os dois ficam sincronizados. */
  if (selRamo) (function () {
    var wrap = selRamo.parentNode, ops = [].slice.call(selRamo.options), ativo = 0, aberto = false, busca = '', buscaT = 0;
    wrap.classList.add('rs-on'); selRamo.tabIndex = -1; selRamo.setAttribute('aria-hidden', 'true');
    var cb = document.createElement('div');
    cb.className = 'rs-b'; cb.tabIndex = 0; cb.setAttribute('role', 'combobox'); cb.setAttribute('aria-haspopup', 'listbox');
    cb.setAttribute('aria-expanded', 'false'); cb.setAttribute('aria-controls', 'ramoList'); cb.setAttribute('aria-labelledby', 'ramoL ramoV');
    var val = document.createElement('span'); val.id = 'ramoV'; val.className = 'rs-v'; cb.appendChild(val);
    var ul = document.createElement('ul');
    ul.id = 'ramoList'; ul.className = 'rs-l'; ul.setAttribute('role', 'listbox'); ul.setAttribute('aria-labelledby', 'ramoL'); ul.hidden = true;
    ops.forEach(function (o, i) {
      var li = document.createElement('li');
      li.id = 'ramoO' + i; li.className = 'rs-o'; li.setAttribute('role', 'option'); li.dataset.i = i;
      var tx = document.createElement('span'); tx.className = 'rs-x';
      var t = document.createElement('span'); t.className = 'rs-t'; t.textContent = o.text; tx.appendChild(t);
      if (o.dataset.d) { var d = document.createElement('small'); d.textContent = o.dataset.d; tx.appendChild(d); }
      li.appendChild(tx);
      li.insertAdjacentHTML('beforeend', '<svg class="i rs-ck" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="#i-check"/></svg>');
      ul.appendChild(li);
    });
    wrap.appendChild(cb); wrap.appendChild(ul);
    var lis = [].slice.call(ul.children);

    function atual() { return Math.max(0, selRamo.selectedIndex); }
    function pintar() {
      var a = atual(); val.textContent = ops[a].text;
      lis.forEach(function (li, i) { li.setAttribute('aria-selected', i === a); li.dataset.on = (aberto && i === ativo) ? 'true' : 'false'; });
      if (aberto) { cb.setAttribute('aria-activedescendant', 'ramoO' + ativo); var el = lis[ativo]; if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' }); }
      else cb.removeAttribute('aria-activedescendant');
    }
    function abrir() {
      if (aberto) return; aberto = true; ativo = atual(); ul.hidden = false; ul.classList.remove('rs-up'); cb.setAttribute('aria-expanded', 'true'); pintar();
      /* sem espaço embaixo (a tela ou o herói acabam antes), abre para cima */
      var hero = wrap.closest('.hero') || document.documentElement, r = ul.getBoundingClientRect(), c = cb.getBoundingClientRect();
      var limite = Math.min(window.innerHeight, hero.getBoundingClientRect().bottom) - 10;
      if (r.bottom > limite && c.top - 10 - r.height >= 8) ul.classList.add('rs-up');
    }
    function fechar() { if (!aberto) return; aberto = false; ul.hidden = true; cb.setAttribute('aria-expanded', 'false'); pintar(); }
    function escolher(i) {
      if (i !== atual()) { selRamo.selectedIndex = i; selRamo.dispatchEvent(new Event('change', { bubbles: true })); }
      fechar(); pintar();
    }
    selRamo.addEventListener('change', pintar);                 /* o seletor original manda: tudo que mudar nele aparece aqui */

    cb.addEventListener('click', function () { aberto ? fechar() : abrir(); });
    ul.addEventListener('mousedown', function (e) { e.preventDefault(); });   /* o foco fica no campo, a lista não "rouba" */
    ul.addEventListener('click', function (e) { var li = e.target.closest('.rs-o'); if (li) escolher(+li.dataset.i); });
    ul.addEventListener('mousemove', function (e) { var li = e.target.closest('.rs-o'); if (li && ativo !== +li.dataset.i) { ativo = +li.dataset.i; pintar(); } });
    cb.addEventListener('blur', fechar);
    document.addEventListener('pointerdown', function (e) { if (aberto && !wrap.contains(e.target)) fechar(); });
    cb.addEventListener('keydown', function (e) {
      var k = e.key, n = ops.length;
      if (k === 'ArrowDown' || k === 'ArrowUp') {
        e.preventDefault();
        if (!aberto) { abrir(); if (k === 'ArrowUp') { ativo = n - 1; pintar(); } return; }
        ativo = (ativo + (k === 'ArrowDown' ? 1 : -1) + n) % n; pintar();
      } else if (k === 'Home' || k === 'End') { if (!aberto) abrir(); e.preventDefault(); ativo = k === 'Home' ? 0 : n - 1; pintar(); }
      else if (k === 'Enter' || k === ' ') { e.preventDefault(); aberto ? escolher(ativo) : abrir(); }
      else if (k === 'Escape') { if (aberto) { e.preventDefault(); fechar(); } }
      else if (k === 'Tab') { fechar(); }
      else if (k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {                 /* digitar a inicial salta para o ramo */
        clearTimeout(buscaT); busca += k.toLowerCase(); buscaT = setTimeout(function () { busca = ''; }, 600);
        var i = ops.findIndex(function (o) { return o.text.toLowerCase().indexOf(busca) === 0; });
        if (i > -1) { if (!aberto) abrir(); ativo = i; pintar(); }
      }
    });
    pintar();
  })();

  /* ---------- reação ao mouse, rolagem e visibilidade ---------- */
  if (hero && matchMedia('(pointer:fine)').matches) {
    var raf = 0;
    hero.addEventListener('pointermove', function (e) {
      if (calm() || raf) return;
      raf = requestAnimationFrame(function () {
        raf = 0; var r = hero.getBoundingClientRect();
        ww.style.setProperty('--mx', ((e.clientX - r.left) / r.width - .5).toFixed(3));
        ww.style.setProperty('--my', ((e.clientY - r.top) / r.height - .5).toFixed(3));
      });
    });
  }
  if (hero && 'IntersectionObserver' in window) new IntersectionObserver(function (e) { hero.classList.toggle('off', !e[0].isIntersecting); }).observe(hero);
  var sk = 0;
  addEventListener('scroll', function () {
    if (sk || calm()) return;
    sk = requestAnimationFrame(function () { sk = 0; if (scrollY < 1000) ww.style.setProperty('--sy', scrollY); });
  }, { passive: true });

  /* marca gigante do rodapé: letras sobem uma a uma */
  var mg = document.querySelector('.mega span');
  if (mg) mg.innerHTML = mg.textContent.split('').map(function (ch, n) { return '<i style="--n:' + n + '">' + ch + '</i>'; }).join('');

  /* ---------- início e reação ao modo calmo ---------- */
  var was = null;
  function apply() { var c = calm(); if (c === was) return; was = c; if (c) still(); else start(curF, 1500); }
  apply();
  new MutationObserver(apply).observe(root, { attributes: true, attributeFilter: ['class'] });
  if (reduceMQ.addEventListener) reduceMQ.addEventListener('change', apply);
})();
