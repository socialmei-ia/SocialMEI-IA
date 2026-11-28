/* SocialMEI-IA · v7.0 · Experiência Conectada.
   Camada de interface sobre o app existente. Não cria endpoints, não grava dados novos no servidor e não envia
   nada: usa apenas o que o app já carrega (clientes, vendas, conversas, lembretes) e os contratos que já existiam
   (GET /opportunities, SocialMEIAgenda.create, vínculo da Caixa com o CRM).
   Partes:
   1. Cliente 360° no painel de Negócio > Clientes
   2. Agenda semanal na demonstração (a Agenda com servidor está em v22-agenda.js)
   3. Ações contextuais: Caixa <-> Clientes <-> Oportunidades <-> Agenda
   4. Ajustes de formulário (valor da venda acompanha produto x quantidade) */
(function () {
  'use strict';
  if (window.SocialMEI70) return;
  if (typeof A === 'undefined' || typeof S === 'undefined' || typeof CL === 'undefined' || typeof render !== 'function') {
    console.warn('v7.0: o app base ainda não está pronto.');
    return;
  }
  var host = window.SocialMEIV22;
  var remote = !!(host && host.remote);
  var W = window.SocialMEIAgendaWeek;
  var OPP_KEY = 'smei-opp-v6'; /* mesma chave da tela de Oportunidades (prefixo por conta é aplicado pelo app) */
  var VIEW_KEY = 'smei-agenda-view';

  /* ---------- utilidades ---------- */
  function E(html) { var t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; }
  var strip = function (n) { return String(n == null ? '' : n).replace(/\(.*\)/, '').trim(); };
  function relDays(ts) {
    var d = Math.round((NOW0.getTime() - ts) / 864e5);
    return d === 0 ? 'hoje' : d === 1 ? 'ontem' : d === -1 ? 'amanhã' : d > 0 ? 'há ' + d + ' dias' : 'em ' + (-d) + ' dias';
  }
  function dShort(ts) { var d = new Date(ts); return d.getDate() + ' ' + MS_[d.getMonth()]; }
  function nameCount(name) {
    var n = norm(strip(name));
    return n ? CL.filter(function (c) { return norm(c[0]) === n; }).length : 0;
  }
  function firstDup(c) { return CL.filter(function (x) { return x[1] === c[1]; }).length > 1; }
  /* Resolve por nome só quando não há dúvida: homônimos nunca são adivinhados. */
  function clientIndexByName(name) {
    var n = norm(strip(name));
    if (!n) return -1;
    var full = CL.map(function (c, k) { return [c, k]; }).filter(function (p) { return norm(p[0][0]) === n; });
    if (full.length) return full.length === 1 ? full[0][1] : -1;
    var firsts = CL.map(function (c, k) { return [c, k]; }).filter(function (p) { return norm(p[0][1]) === n; });
    return firsts.length === 1 ? firsts[0][1] : -1;
  }
  /* ID real do cadastro (negócio conectado) -> posição em CL, que o app monta na mesma ordem de host.clients. */
  function clientIndexById(id) {
    if (!remote || !host.clients || id == null || id === '') return -1;
    var k = host.clients.findIndex(function (x) { return String(x.id) === String(id); });
    return k > -1 && CL[k] && CL[k][0] === host.clients[k].nome ? k : -1;
  }
  function remoteClient(idx) {
    if (!remote || !host.clients) return null;
    var c = CL[idx], rc = host.clients[idx];
    return c && rc && rc.nome === c[0] ? rc : null;
  }
  function resolveClient(p) {
    if (p && p.idx != null && p.idx > -1 && CL[p.idx]) return p.idx;
    if (p && p.cid != null && p.cid !== '') return clientIndexById(p.cid);
    return p && p.cliente ? clientIndexByName(p.cliente) : -1;
  }
  function hostScope() {
    var id = remote && host.identity;
    return id && id.usuario && id.negocio ? id.usuario.id + ':' + id.negocio.id : '';
  }
  var DUPMSG = 'Há clientes com o mesmo nome e este registro guarda só o nome. Diferencie os cadastros para separar o histórico.';
  /* Cada fonte devolve { list, st:{ s: ok|loading|error|partial|unavailable|ambiguous, msg, act } }. */
  function salesOf(idx) {
    var c = CL[idx];
    if (remote) {
      var rc = remoteClient(idx), hs = host.sales;
      if (!rc || !hs) return { list: [], st: { s: 'unavailable', msg: 'Não foi possível ligar as vendas a este cadastro com segurança.' } };
      var owner = {};
      hs.forEach(function (x) { owner[String(x.id)] = String(x.cliente_id); });
      return { list: V.map(function (v, k) { return [v, k]; }).filter(function (p) { return owner[String(p[0][0])] === String(rc.id); }), st: { s: 'ok' } };
    }
    if (nameCount(c[0]) > 1) return { list: [], st: { s: 'ambiguous', msg: DUPMSG } };
    var fd = firstDup(c);
    return { list: V.map(function (v, k) { return [v, k]; }).filter(function (p) { return p[0][2] === c[0] || (!fd && p[0][2] === c[1]); }), st: { s: 'ok' } };
  }
  function toast70(t) { if (typeof toast === 'function') toast(t); }
  function route() { var p = location.hash.slice(1).split('/'); return { r: p[1] || 'inicio', a: p[2] }; }

  /* ---------- Oportunidades (somente leitura, contrato existente) ---------- */
  /* Cache por usuário:negócio. Só o escopo atual é mantido; respostas de um escopo ou de uma versão
     anterior (seq) são descartadas; qualquer escrita em /opportunities, /vendas ou /clientes invalida. */
  var oppStore = {}, oppSeq = 0, OPP_TTL = 60000, OPP_ERR_TTL = 15000, OPP_TIMEOUT = 15000;
  function localOpps() {
    try { var d = JSON.parse(localStorage.getItem(OPP_KEY)); return Array.isArray(d) ? d : []; } catch (e) { return []; }
  }
  function oppStatus() {
    if (!remote) return { s: 'ok' };
    var e = oppStore[hostScope()];
    if (!e) return { s: 'loading' };
    if (e.state === 'error') return { s: 'error', msg: e.err };
    if (e.dirty || !e.items) return { s: 'loading' };
    return { s: 'ok' };
  }
  function oppItem(o) {
    return { title: o.title, level: o.interest_level === 'unknown' ? 'analysis' : o.interest_level, state: o.outcome, value: Number(o.estimated_amount) || 0, follow: o.follow_up_date ? pdt(o.follow_up_date) : null, ts: Date.parse(o.updated_at) || 0 };
  }
  function oppsFor(idx) {
    var c = CL[idx], out = [];
    if (!remote) {
      if (nameCount(c[0]) > 1) return { list: [], st: { s: 'ambiguous', msg: DUPMSG } };
      var fd = firstDup(c);
      localOpps().forEach(function (o) {
        var nm = norm(strip(o.c));
        if (nm === norm(c[0]) || (!fd && nm === norm(c[1]))) out.push({ title: o.w, level: o.i, state: o.r, value: Number(o.v) || 0, follow: o.f || null, ts: o.u });
      });
      return { list: out, st: { s: 'ok' } };
    }
    var rc = remoteClient(idx);
    if (!rc) return { list: [], st: { s: 'unavailable', msg: 'Não foi possível ligar as oportunidades a este cadastro com segurança.' } };
    var e = oppStore[hostScope()], st = oppStatus(), unlinked = 0;
    if (e && e.items) e.items.forEach(function (o) {
      if (o.client_id == null) unlinked++;
      else if (String(o.client_id) === String(rc.id)) out.push(oppItem(o));
    });
    if (st.s === 'ok' && unlinked) st = { s: 'partial', msg: unlinked + (unlinked === 1 ? ' oportunidade sem cliente vinculado não entra' : ' oportunidades sem cliente vinculado não entram') + ' neste resumo.' };
    return { list: out, st: st };
  }
  function loadOpps(force) {
    if (!remote || !host.request) return;
    var sc = hostScope();
    Object.keys(oppStore).forEach(function (k) { if (k !== sc) delete oppStore[k]; });
    if (!sc) return;
    var e = oppStore[sc];
    if (e && e.state === 'loading') return;
    if (!force && e && !e.dirty && Date.now() - e.at < (e.state === 'error' ? OPP_ERR_TTL : OPP_TTL)) return;
    var seq = ++oppSeq, timer;
    oppStore[sc] = { state: 'loading', items: e && e.items ? e.items : null, at: Date.now(), err: '', dirty: !!(e && e.dirty), seq: seq };
    var late = new Promise(function (_, rej) { timer = setTimeout(function () { rej(new Error('As oportunidades demoraram para responder.')); }, OPP_TIMEOUT); });
    var live = function () { var cur = oppStore[sc]; return cur && cur.seq === seq && hostScope() === sc ? cur : null; };
    Promise.race([host.request('/opportunities'), late]).then(function (r) {
      clearTimeout(timer);
      if (!live()) return; /* resposta antiga: descartada */
      if (!r || !Array.isArray(r.items)) throw new Error('Resposta de oportunidades inválida.');
      oppStore[sc] = { state: 'ready', items: r.items, at: Date.now(), err: '', dirty: false, seq: seq };
    }).catch(function (err) {
      clearTimeout(timer);
      var cur = live();
      if (!cur) return;
      oppStore[sc] = { state: 'error', items: cur.items, at: Date.now(), err: (err && err.message) || 'Oportunidades indisponíveis.', dirty: cur.dirty, seq: seq };
    }).then(function () { paint360(); paintCtx(); });
  }
  function invalidateOpps(reload) {
    var sc = hostScope();
    if (!sc) return;
    var e = oppStore[sc];
    oppStore[sc] = { state: 'stale', items: e ? e.items : null, at: 0, err: '', dirty: true, seq: ++oppSeq };
    if (reload) loadOpps();
  }
  /* Escritas feitas pelo quadro de Oportunidades, pela Caixa ou por vendas passam por host.write/request. */
  function watchWrites() {
    if (!remote || !host) return;
    ['write', 'request'].forEach(function (name) {
      var f = host[name];
      if (typeof f !== 'function' || f.v701) return;
      var w = function (path, method) {
        var hit = String(method || 'GET').toUpperCase() !== 'GET' && /^\/(opportunities|vendas|clientes)(\/|$|\?)/.test(String(path));
        if (hit) invalidateOpps(false);
        var res = f.apply(this, arguments);
        if (hit) Promise.resolve(res).then(function () { invalidateOpps(true); }, function () { invalidateOpps(true); });
        return res;
      };
      w.v701 = true;
      try { host[name] = w; } catch (e) { console.warn('v7.0.1: não foi possível observar ' + name + '.'); }
    });
  }
  var LV = { analysis: 'Em análise', cold: 'Frio', warm: 'Morno', hot: 'Quente' };
  /* v7.2: filtro e expansão da linha do tempo (só interface; voltam ao padrão ao trocar de cliente) */
  var c3f = 'todos', c3all = false, c3for = null;
  var KIND = { venda: 'Vendas', oportunidade: 'Oportunidades', lembrete: 'Lembretes', conversa: 'Conversa' };
  /* Regras claras da "situação do relacionamento": só existe quando as vendas foram conferidas por completo. */
  function health(salesOk, nSales, last) {
    if (!salesOk) return null;
    if (!nSales) return { k: 'new', t: 'Sem compras', d: 'Ainda não há compras registradas.' };
    var d = Math.round((NOW0.getTime() - last) / 864e5);
    if (d <= 30) return { k: 'ok', t: 'Ativo', d: 'Comprou nos últimos 30 dias.' };
    if (d <= 60) return { k: 'warn', t: 'Esfriando', d: 'Última compra há ' + d + ' dias (31 a 60).' };
    return { k: 'late', t: 'Inativo', d: 'Última compra há ' + d + ' dias (mais de 60).' };
  }
  /* Outros passos que também se aplicam, além do principal. Cada regra só dispara com a fonte conferida. */
  function moreSteps(m, nx) {
    var out = [], opOk = m.src[1].st.s === 'ok' || m.src[1].st.s === 'partial';
    var openOpps = m.opps.filter(function (o) { return o.state === 'open'; });
    if (m.open.length && nx.act !== 'cobrar') out.push({ t: 'Cobrar ' + brl(m.tOpen) + ' em aberto', d: m.open.length + (m.open.length === 1 ? ' venda pendente.' : ' vendas pendentes.'), act: 'cobrar', k: m.open[0][1], label: 'Preparar cobrança' });
    var due = openOpps.filter(function (o) { return o.follow && o.follow <= NOW0.getTime() + 864e5; })[0];
    if (due && nx.act !== 'opps') out.push({ t: 'Retomar: ' + due.title, d: 'Retorno combinado ' + relDays(due.follow) + '.', act: 'opps', label: 'Ver oportunidades' });
    var pend = m.rems.filter(function (r) { return !r.done; }).sort(function (a, b) { return a.ts - b.ts; })[0];
    if (pend && nx.act !== 'agenda') out.push({ t: 'Lembrete: ' + pend.title, d: (pend.ts < NOW0.getTime() - 864e5 ? 'Atrasado, era ' : 'Para ') + relDays(pend.ts) + '.', act: 'agenda', label: 'Abrir agenda' });
    if (m.salesOk && opOk && m.sales.length && m.last && NOW0.getTime() - m.last <= 60 * 864e5 && !openOpps.length && nx.act !== 'opp')
      out.push({ t: 'Sem oportunidade em andamento', d: 'Cliente com compra recente: vale registrar um novo interesse.', act: 'opp', label: 'Criar oportunidade' });
    if (m.salesOk && m.last && NOW0.getTime() - m.last > 45 * 864e5 && nx.act !== 'lemb' && !pend)
      out.push({ t: 'Combinar um retorno', d: 'Sem comprar há ' + Math.round((NOW0.getTime() - m.last) / 864e5) + ' dias.', act: 'lemb', label: 'Criar lembrete' });
    return out.slice(0, 3);
  }

  /* ---------- lembretes do cliente ---------- */
  var agIso = function (a) { return a[5] || (a[5] = a[0] === 'Hoje' ? AGI(0) : a[0] === 'Amanhã' ? AGI(1) : AGI(2)); };
  function remindersFor(idx) {
    var c = CL[idx];
    if (!remote) {
      if (nameCount(c[0]) > 1) return { list: [], st: { s: 'ambiguous', msg: DUPMSG } };
      return { list: S.ag.filter(function (a) { return a[3] === c[0]; }).map(function (a) {
        return { title: a[2], ts: pdt(agIso(a)), time: /^\d{2}:\d{2}$/.test(a[1]) ? a[1] : '', done: !!a[4] };
      }), st: { s: 'ok' } };
    }
    var rc = remoteClient(idx);
    if (!rc) return { list: [], st: { s: 'unavailable', msg: 'Não foi possível ligar os lembretes a este cadastro com segurança.' } };
    var api = window.SocialMEIAgenda, snap = api && api.snapshot && api.snapshot();
    if (!snap || snap.scope !== hostScope() || snap.phase === 'initial') return { list: [], st: { s: 'partial', msg: 'A Agenda ainda não foi consultada: abra a Agenda para incluir lembretes.', act: 'agenda' } };
    var list = snap.items.filter(function (i) { return String(i.cliente_id) === String(rc.id) && i.status !== 'cancelled'; }).map(function (i) {
      var d = new Date(i.scheduled_for);
      return { title: i.title, ts: new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12).getTime(), time: d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }), done: i.status === 'done' };
    });
    if (snap.phase === 'error') return { list: list, st: { s: 'error', msg: 'Não foi possível consultar a Agenda.' } };
    if (snap.phase === 'loading') return { list: list, st: { s: 'loading' } };
    var range = snap.from && snap.to ? 'Lembretes consultados de ' + dShort(pdt(snap.from)) + ' a ' + dShort(pdt(snap.to)) + '.' : 'Lembretes: só o período já consultado na Agenda.';
    return { list: list, st: { s: 'partial', msg: range, act: 'agenda' } };
  }

  /* ---------- 1. Cliente 360° ---------- */
  function model360(idx) {
    var c = CL[idx]; if (!c) return null;
    var rc = remoteClient(idx);
    var sl = salesOf(idx), op = oppsFor(idx), rm = remindersFor(idx);
    var sales = sl.list, opps = op.list, rems = rm.list;
    var paid = sales.filter(function (p) { return p[0][5] === 'Pago'; });
    var open = sales.filter(function (p) { return p[0][5] !== 'Pago'; });
    var sum = function (l) { return l.reduce(function (t, p) { return t + p[0][6]; }, 0); };
    var last = sales.reduce(function (m, p) { return Math.max(m, pdt(p[0][4])); }, 0);
    var first = sales.reduce(function (m, p) { var t = pdt(p[0][4]); return t && (!m || t < m) ? t : m; }, 0);
    var conv = !remote && c[10] ? C.find(function (x) { return x[0] === c[10]; }) : null;
    var src = [{ k: 'Vendas', st: sl.st }, { k: 'Oportunidades', st: op.st }, { k: 'Lembretes', st: rm.st }];
    var ev = [];
    sales.forEach(function (p) { var v = p[0]; ev.push({ ts: pdt(v[4]), kind: 'venda', ic: 'cart', t: v[0] + ' · ' + v[1], m: v[5] === 'Pago' ? 'Pago' : 'Pendente', warn: v[5] !== 'Pago', val: v[6] }); });
    rems.forEach(function (r) { ev.push({ ts: r.ts, kind: 'lembrete', ic: 'cal', t: r.title, m: (r.done ? 'Feito' : 'Pendente') + (r.time ? ' · ' + r.time : ''), warn: !r.done && r.ts < NOW0.getTime() - 864e5 }); });
    opps.forEach(function (o) { ev.push({ ts: o.ts, kind: 'oportunidade', ic: 'spark', t: o.title, m: o.state === 'open' ? 'Em negociação · ' + (LV[o.level] || '') : o.state === 'won' ? 'Venda realizada' : 'Não avançou', val: o.value }); });
    if (conv) ev.push({ ts: NOW0.getTime(), kind: 'conversa', ic: 'chat', t: 'Conversa no ' + (conv[6] === 'ig' ? 'Instagram' : 'WhatsApp'), m: conv[7], link: conv[0] });
    ev.sort(function (a, b) { return b.ts - a.ts; });
    var salesOk = sl.st.s === 'ok';
    var next = nextStep(open, opps, rems, last, src, salesOk);
    return { health: health(salesOk, sales.length, last), oppSt: op.st, c: c, idx: idx, rc: rc, sales: sales, paid: paid, open: open, tPaid: sum(paid), tOpen: sum(open), last: last, first: first, opps: opps, rems: rems, conv: conv, ev: ev, next: next, src: src, salesOk: salesOk };
  }
  /* "Nada pendente" só aparece quando TODAS as fontes foram conferidas; achados reais valem mesmo com fontes incompletas. */
  function nextStep(open, opps, rems, last, src, salesOk) {
    var gaps = src.filter(function (x) { return x.st.s !== 'ok'; });
    var tail = gaps.length ? ' Algumas informações ainda estão incompletas.' : '';
    if (open.length) {
      var p = open[0];
      return { tone: 'warn', t: 'Cobrar ' + brl(p[0][6]) + ' da venda ' + p[0][0], d: (open.length > 1 ? open.length + ' vendas pendentes no total.' : 'Venda de ' + relDays(pdt(p[0][4])) + '.') + tail, act: 'cobrar', k: p[1], label: 'Preparar cobrança' };
    }
    var due = opps.filter(function (o) { return o.state === 'open' && o.follow && o.follow <= NOW0.getTime() + 864e5; })[0];
    if (due) return { tone: 'warn', t: 'Retomar: ' + due.title, d: 'Retorno combinado ' + relDays(due.follow) + '.' + tail, act: 'opps', label: 'Ver oportunidades' };
    var pend = rems.filter(function (r) { return !r.done; }).sort(function (a, b) { return a.ts - b.ts; })[0];
    if (pend) return { tone: 'info', t: 'Lembrete: ' + pend.title, d: (pend.ts < NOW0.getTime() - 864e5 ? 'Atrasado, era ' : 'Para ') + relDays(pend.ts) + (pend.time ? ', ' + pend.time : '') + '.' + tail, act: 'agenda', label: 'Abrir agenda' };
    if (salesOk && last && NOW0.getTime() - last > 45 * 864e5) return { tone: 'info', t: 'Sem comprar há ' + Math.round((NOW0.getTime() - last) / 864e5) + ' dias', d: 'Que tal combinar um retorno?' + tail, act: 'lemb', label: 'Criar lembrete' };
    if (!gaps.length) return { tone: 'ok', t: 'Nada pendente com este cliente', d: 'Sem cobranças, retornos ou lembretes em aberto.', act: null };
    var by = function (k) { return gaps.filter(function (g) { return g.st.s === k; }); };
    if (by('ambiguous').length) return { tone: 'warn', t: 'Nome repetido no cadastro', d: by('ambiguous')[0].st.msg, da: 'edit:cli', label: 'Diferenciar cadastro' };
    if (by('error').length) return { tone: 'err', t: 'Não deu para conferir tudo', d: by('error').map(function (g) { return g.k + ': ' + g.st.msg; }).join(' '), act: 'retry', label: 'Tentar de novo' };
    if (by('loading').length) return { tone: 'load', t: 'Conferindo pendências…', d: 'Ainda carregando: ' + by('loading').map(function (g) { return g.k.toLowerCase(); }).join(', ') + '.', act: null };
    var ag = gaps.some(function (g) { return g.st.act === 'agenda'; });
    return { tone: 'info', t: 'Nada pendente no que já foi carregado', d: gaps.map(function (g) { return g.st.msg; }).join(' '), act: ag ? 'agenda' : null, label: 'Abrir agenda' };
  }
  function html360(m) {
    var c = m.c, nome = esc(c[0]);
    var tags = '';
    var mx = Math.max.apply(null, CL.map(function (x) { return x[5]; }));
    if (m.tPaid > 0 && c[5] === mx) tags += '<span class="tagv">Melhor cliente</span>';
    if (m.salesOk && !m.sales.length) tags += '<span class="tagv n">Novo</span>';
    if (m.open.length) tags += '<span class="tagv w">Com pendência</span>';
    if (m.health) tags += '<span class="tagv c3-h-' + m.health.k + '" title="' + esc(m.health.d) + '">' + esc(m.health.t) + '</span>';
    var openOpps = m.opps.filter(function (o) { return o.state === 'open'; });
    var linkConv = m.conv
      ? '<a class="btn o sm2" href="#/caixa/' + esc(m.conv[0]) + '">' + i('chat', 16) + 'Abrir conversa</a>'
      : '<button class="btn o sm2" disabled title="' + (remote ? 'A Caixa ainda não permite buscar a conversa a partir do cliente.' : 'Este cliente ainda não tem conversa.') + '">' + i('chat', 16) + 'Sem conversa</button>';
    var kp = function (l, v, s2) { return '<div class="c3-k"><span>' + l + '</span><b>' + v + '</b>' + (s2 ? '<small>' + s2 + '</small>' : '') + '</div>'; };
    var ticket = m.paid.length ? brl(m.tPaid / m.paid.length) : '—';
    var nx = m.next, ok = m.salesOk, na = m.src[0].st.s === 'ambiguous' ? 'Nome repetido' : 'Indisponível';
    var nxBtn = nx.da ? '<button class="btn sm2" data-a="' + nx.da + '">' + esc(nx.label) + '</button>' : nx.act ? '<button class="btn sm2" data-a="c360:' + nx.act + '"' + (nx.k != null ? ' data-k="' + nx.k + '"' : '') + '>' + esc(nx.label) + '</button>' : '';
    var SL = { ok: 'completo', loading: 'carregando', error: 'falhou', partial: 'parcial', unavailable: 'indisponível', ambiguous: 'nome repetido' };
    var srcs = '<ul class="c3-srcs" aria-label="Situação das informações deste resumo">' + m.src.map(function (x) { return '<li class="c3-src" data-s="' + x.st.s + '"><span class="c3-sd" aria-hidden="true"></span>' + x.k + '<small>' + SL[x.st.s] + '</small></li>'; }).join('') + '</ul>';
    if (c3for !== m.idx) { c3for = m.idx; c3f = 'todos'; c3all = false; }
    var kinds = {}; m.ev.forEach(function (e) { kinds[e.kind] = (kinds[e.kind] || 0) + 1; });
    if (c3f !== 'todos' && !kinds[c3f]) c3f = 'todos';
    var evAll = m.ev.filter(function (e) { return c3f === 'todos' || e.kind === c3f; });
    var lim = c3all ? 60 : 8;
    var chips = m.ev.length > 3 ? '<div class="c3-fl" role="group" aria-label="Filtrar linha do tempo">' + [['todos', 'Tudo', m.ev.length]].concat(Object.keys(KIND).filter(function (k) { return kinds[k]; }).map(function (k) { return [k, KIND[k], kinds[k]]; })).map(function (f) { return '<button type="button" class="c3-chip" data-a="c360:fil-' + f[0] + '" aria-pressed="' + (c3f === f[0]) + '">' + f[1] + ' <span>' + f[2] + '</span></button>'; }).join('') + '</div>' : '';
    var evs = evAll.slice(0, lim).map(function (e) {
      var inner = '<span class="c3-ei" aria-hidden="true">' + i(e.ic, 15) + '</span><div class="c3-eb"><b>' + esc(e.t) + '</b><small' + (e.warn ? ' class="w"' : '') + '>' + esc(e.m) + (e.val ? ' · ' + brl(e.val) : '') + '</small></div><time class="c3-ed">' + (e.ts ? dShort(e.ts) : '') + '</time>';
      return '<li class="c3-e c3-' + e.kind + '">' + (e.link ? '<a href="#/caixa/' + esc(e.link) + '">' + inner + '</a>' : inner) + '</li>';
    }).join('');
    var more = evAll.length > 8 ? '<button type="button" class="lk c3-more" data-a="c360:all" aria-expanded="' + c3all + '">' + (c3all ? 'Mostrar menos' : 'Ver todos (' + evAll.length + ')') + '</button>' : '';
    var os = m.src[1].st, oppBody;
    if (os.s === 'loading') oppBody = '<div class="c3-sk" aria-busy="true" role="status"><i></i><i></i><span class="c3-sr">Consultando oportunidades…</span></div>';
    else if (os.s === 'error' || os.s === 'unavailable' || os.s === 'ambiguous') oppBody = '<p class="m sm c3-un" role="status">' + esc(os.msg || 'Oportunidades indisponíveis.') + ' Não significa que o cliente não tenha oportunidades.</p>' + (os.s === 'error' ? '<button type="button" class="btn o sm2" data-a="c360:retry">Tentar de novo</button>' : '');
    else if (!m.opps.length) oppBody = '<p class="m sm">Nenhuma oportunidade vinculada a este cliente' + (os.s === 'partial' ? ' nas informações carregadas' : '') + '.</p>';
    else oppBody = '<ul class="c3-op">' + m.opps.slice().sort(function (a, b) { return (a.state === 'open' ? 0 : 1) - (b.state === 'open' ? 0 : 1) || b.ts - a.ts; }).slice(0, 4).map(function (o) {
      var st = o.state === 'open' ? (LV[o.level] || 'Em andamento') : o.state === 'won' ? 'Venda realizada' : 'Não avançou';
      var fu = o.state === 'open' ? (o.follow ? (o.follow <= NOW0.getTime() + 864e5 ? '<b class="w">Retorno ' + relDays(o.follow) + '</b>' : 'Retorno ' + relDays(o.follow)) : 'Sem retorno marcado') : 'Encerrada ' + relDays(o.ts);
      return '<li class="c3-o" data-st="' + (o.state === 'open' ? o.level : o.state) + '"><div><b>' + esc(o.title) + '</b><small>' + fu + '</small></div><span class="c3-ol">' + st + '</span>' + (o.value ? '<span class="c3-ov">' + brl(o.value) + '</span>' : '') + '</li>';
    }).join('') + '</ul>' + (m.opps.length > 4 ? '<p class="m sm">Mostrando 4 de ' + m.opps.length + ' oportunidades.</p>' : '');
    var oppSec = '<h3 class="c3-h">Oportunidades' + (openOpps.length ? ' <span class="c3-n">' + openOpps.length + ' em andamento · ' + brl(openOpps.reduce(function (t, o) { return t + o.value; }, 0)) + '</span>' : '') + '</h3>' + oppBody +
      '<div class="c3-oa"><button type="button" class="btn o sm2" data-a="c360:opps">Abrir Oportunidades</button><button type="button" class="btn o sm2" data-a="c360:opp">' + i('plus', 14) + 'Nova</button></div>';
    var extra = moreSteps(m, nx);
    var extraHtml = extra.length ? '<div class="c3-ms"><span class="c3-nl">Também vale fazer</span><ul>' + extra.map(function (x) { return '<li><div><b>' + esc(x.t) + '</b><small>' + esc(x.d) + '</small></div><button type="button" class="btn o sm2" data-a="c360:' + x.act + '"' + (x.k != null ? ' data-k="' + x.k + '"' : '') + '>' + esc(x.label) + '</button></li>'; }).join('') + '</ul></div>' : '';
    var limits = [];
    m.src.forEach(function (x) { if (x.st.s !== 'ok' && x.st.msg) limits.push('<b>' + x.k + ':</b> ' + esc(x.st.msg)); });
    if (remote) limits.push('Conversas: a Caixa não oferece busca por cliente; abra a conversa pela Caixa.');
    return '<div class="c3" data-c3="' + m.idx + '">' +
      '<button type="button" class="lk c3-back" data-a="cli:-1">' + i('back', 16) + ' Voltar à lista de clientes</button>' +
      '<div class="row sp"><div class="c3-who"><span class="av" style="width:52px;height:52px;background:' + c[6] + ';color:' + c[7] + '" aria-hidden="true">' + c[2] + '</span><div><h2>' + nome + '</h2><div class="c3-tags">' + tags + '</div></div></div><button class="lk" data-a="cli:-1" aria-label="Fechar detalhes">' + i('x') + '</button></div>' +
      '<p class="m sm c3-sub">' + esc(c[3] || 'Sem e-mail') + (m.first ? ' · Cliente desde ' + dShort(m.first) + ' de ' + new Date(m.first).getFullYear() : '') + '</p>' +
      '<div class="c3-kp" role="list">' + (ok ? kp('Total pago', brl(m.tPaid), m.paid.length + (m.paid.length === 1 ? ' pedido' : ' pedidos')) + kp('Em aberto', brl(m.tOpen), m.open.length ? m.open.length + (m.open.length === 1 ? ' pendente' : ' pendentes') : 'Nada pendente') + kp('Ticket médio', ticket, '') + kp('Última compra', m.last ? relDays(m.last) : '—', m.last ? dShort(m.last) : 'Nenhuma ainda') : kp('Total pago', '—', na) + kp('Em aberto', '—', na) + kp('Ticket médio', '—', na) + kp('Última compra', '—', na)) + '</div>' +
      '<div class="c3-nx" data-tone="' + nx.tone + '" role="status" aria-busy="' + (nx.tone === 'load') + '"><div><span class="c3-nl">Próximo passo</span><b>' + esc(nx.t) + '</b><small>' + esc(nx.d) + '</small></div>' + nxBtn + '</div>' + extraHtml + srcs +
      '<div class="c3-ac" role="group" aria-label="Ações do cliente">' + linkConv +
      '<button class="btn o sm2" data-a="c360:lemb">' + i('cal', 16) + 'Lembrete</button>' +
      '<button class="btn o sm2" data-a="c360:opp">' + i('spark', 16) + 'Oportunidade</button>' +
      '<button class="btn o sm2" data-a="c360:venda">' + i('cart', 16) + 'Nova venda</button>' +
      '<button class="btn o sm2" data-a="edit:cli">' + i('pen', 16) + 'Editar</button>' +
      (c[3] ? '<button class="btn o sm2" data-a="cpm:' + m.idx + '">' + i('copy', 16) + 'Copiar e-mail</button>' : '') + '</div>' +
      oppSec +
      '<h3 class="c3-h">Linha do tempo</h3>' + chips + (evs ? '<ol class="c3-tl">' + evs + '</ol>' + more : '<p class="m">' + (m.src.every(function (x) { return x.st.s === 'ok'; }) ? 'Ainda não há registros deste cliente.' : 'Sem registros nas informações já carregadas.') + '</p>') +
      '<h3 class="c3-h">Observações</h3><div class="row sp"><span>' + esc(c[9] || 'Sem observações.') + '</span><button class="lk" data-a="edit:cli">' + i('pen', 16) + ' Editar</button></div>' +
      (limits.length ? '<details class="c3-lim"><summary>O que este resumo mostra</summary><ul>' + limits.map(function (l) { return '<li>' + l + '</li>'; }).join('') + '</ul></details>' : '') +
      '</div>';
  }
  function paint360() {
    var r = route();
    if (r.r !== 'negocio' || r.a !== 'clientes') return;
    var pn = document.querySelector('#v aside.pn');
    if (!pn) return;
    var m = S.cli >= 0 && CL[S.cli] ? model360(S.cli) : null;
    if (!m) { pn.classList.remove('pn360'); return; }
    var focused = document.activeElement && document.activeElement.closest && document.activeElement.closest('aside.pn') ? document.activeElement.getAttribute('data-a') : null;
    var sc = pn.scrollTop;
    var changed = pn.dataset.c3 !== String(S.cli);
    pn.dataset.c3 = String(S.cli);
    pn.classList.add('pn360');
    pn.innerHTML = html360(m);
    if (changed && window.innerWidth <= 900) pn.scrollIntoView({ block: 'start', behavior: 'auto' });
    pn.scrollTop = sc;
    if (focused) { var f = pn.querySelector('[data-a="' + focused + '"]'); if (f) f.focus(); }
    loadOpps();
  }

  /* ---------- 2. Agenda semanal (demonstração local) ---------- */
  var agView = (function () { try { return localStorage.getItem(VIEW_KEY) === 'week' ? 'week' : 'list'; } catch (e) { return 'list'; } })();
  var agWeek = W ? W.mondayOf(new Date()) : AGI(0);
  var agSel = null; /* dia aberto na faixa de dias do celular (só interface) */
  function agTime(a) { return /^\d{2}:\d{2}$/.test(a[1]) ? a[1] : ''; }
  function agLate(a) {
    if (a[4]) return false;
    var iso = agIso(a), today = AGI(0);
    if (iso < today) return true;
    var now = new Date(), hhmm = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
    return iso === today && !!agTime(a) && agTime(a) < hhmm;
  }
  function agenda70() {
    var items = S.ag.map(function (a, k) { return [a, k]; });
    var today = AGI(0);
    var k1 = items.filter(function (p) { return !p[0][4] && agIso(p[0]) === today; }).length;
    var k2 = items.filter(function (p) { return agLate(p[0]); }).length;
    var k3 = items.filter(function (p) { return !p[0][4]; }).length;
    var k4 = items.filter(function (p) { return p[0][4]; }).length;
    var kpi = [['Hoje', k1, k1 ? 'on' : ''], ['Atrasados', k2, k2 ? 'warn' : ''], ['Pendentes', k3, ''], ['Feitos', k4, '']].map(function (x) { return '<div class="ag-k" data-tone="' + x[2] + '" role="listitem"><span>' + x[0] + '</span><b>' + x[1] + '</b></div>'; }).join('');
    var sw = W ? '<div class="wk-sw" role="group" aria-label="Forma de ver a agenda">' + [['list', 'Lista'], ['week', 'Semana']].map(function (v) { return '<button type="button" data-a="agv:' + v[0] + '" aria-pressed="' + (agView === v[0]) + '">' + v[1] + '</button>'; }).join('') + '</div>' : '';
    var body = '';
    if (agView === 'week' && W) {
      body = '<div id="wk70"></div>';
    } else if (!items.length && total) {
      body = '<div class="ag-empty"><p class="ag-et">Nenhum lembrete em “' + AGF[agFilter] + '”.</p><p class="ag-eh">Use “Ver todos” para voltar à lista completa.</p></div>';
    } else if (!items.length) {
      body = '<div class="ag-empty"><span class="ag-ei" aria-hidden="true">' + i('cal', 28) + '</span><p class="ag-et">Nenhum lembrete por aqui.</p><p class="ag-eh">Comece por um atalho ou crie o seu.</p><div class="ag-ex">' +
        '<button class="btn o sm2" data-a="agnew:amanha">Retorno amanhã</button><button class="btn o sm2" data-a="agnew:cobranca">Cobrar em 3 dias</button><button class="btn" data-a="agnew">' + i('plus') + 'Novo lembrete</button></div></div>';
    } else {
      var sorted = items.slice().sort(function (a, b) { return (agIso(a[0]) + (agTime(a[0]) || '99')).localeCompare(agIso(b[0]) + (agTime(b[0]) || '99')); });
      var groups = [], seen = {};
      sorted.forEach(function (p) {
        var iso = agIso(p[0]);
        if (!seen[iso]) { seen[iso] = { iso: iso, list: [] }; groups.push(seen[iso]); }
        seen[iso].list.push(p);
      });
      var relTag = {}; relTag[AGI(-1)] = 'Ontem'; relTag[AGI(0)] = 'Hoje'; relTag[AGI(1)] = 'Amanhã';
      body = '<div class="ag-list">' + groups.map(function (g) {
        var d = new Date(pdt(g.iso));
        return '<div class="ag-day"><h3>' + esc(d.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })) + (relTag[g.iso] ? '<span class="ag-rel">' + relTag[g.iso] + '</span>' : '') + '</h3>' +
          g.list.map(function (p) {
            var a = p[0], k = p[1];
            return '<div class="agi' + (a[4] ? ' done' : '') + (agLate(a) ? ' late' : '') + '"><button class="ckb" role="checkbox" aria-checked="' + (!!a[4]) + '" aria-label="Marcar como feito: ' + esc(a[2]) + '" data-a="agok:' + k + '">' + (a[4] ? '✓' : '') + '</button><time>' + esc(agTime(a) || '—') + '</time><div class="cks"><strong>' + esc(a[2]) + '</strong>' + (a[3] ? '<p class="ag-meta">Cliente: ' + esc(a[3]) + '</p>' : '') + '</div></div>';
          }).join('') + '</div>';
      }).join('') + '</div>';
    }
    return '<section class="pg sm-agenda" data-agenda="local"><header class="ag-head"><div class="ag-title"><span class="ag-eyebrow">Agenda</span><h1>Seus horários e lembretes</h1><p class="ag-sub">Combine retornos com clientes e não esqueça nada. Lembretes da demonstração ficam só neste navegador.</p></div><button class="btn ag-add" data-a="agnew">Novo lembrete</button></header>' +
      '<div class="ag-kpis" role="list" aria-label="Resumo dos lembretes">' + kpi + '</div>' +
      '<section class="ag-card ag-rem"><div class="ag-ch"><h2>Lembretes</h2><span>' + items.length + (items.length === 1 ? ' lembrete' : ' lembretes') + '</span>' + sw + '</div>' + body + '</section></section>';
  }
  function mountWeek() {
    var box = document.getElementById('wk70');
    if (!box || !W) return;
    var todayIso = AGI(0);
    box.replaceChildren(W.build({
      weekStart: agWeek, today: todayIso, busy: false, canWrite: true, loading: false, error: '',
      items: S.ag.map(function (a, k) { return { key: k, iso: agIso(a), time: agTime(a), title: a[2], client: a[3], status: a[4] ? 'done' : 'pending', late: agLate(a) }; }),
      selected: agSel, onSelect: function (iso) { agSel = iso; },
      onJump: function (iso) { agWeek = W.mondayOf(iso); agSel = iso; S.keepScroll = true; render(); },
      onNav: function (d) { agWeek = d === 0 ? W.mondayOf(new Date()) : W.addDays(agWeek, 7 * d); agSel = null; S.keepScroll = true; render(); },
      onToggle: function (it) { S.ag[it.key][4] = S.ag[it.key][4] ? 0 : 1; S.keepScroll = true; render(); },
      onNew: function (iso) { openLembrete({ date: iso < AGI(0) ? AGI(0) : iso }); }
    }));
  }

  /* ---------- 3. Ações contextuais ---------- */
  function openLembrete(p) {
    p = p || {};
    var idx = resolveClient(p), named = !!(p.cliente || p.cid || (p.idx != null && p.idx > -1));
    if (remote) {
      var api = window.SocialMEIAgenda;
      if (!api || !api.create) { toast70('A Agenda ainda não carregou. Tente de novo em instantes.'); return; }
      var rc = idx > -1 ? remoteClient(idx) : null;
      if (named && !rc) toast70('Não foi possível identificar o cliente com segurança. O lembrete abre sem cliente.');
      api.create({ date: p.date || AGI(1), title: p.title || '', notes: p.notes || '', cliente_id: rc ? rc.id : null });
      return;
    }
    if (idx > -1 && nameCount(CL[idx][0]) > 1) { toast70('Há clientes com o mesmo nome. Escolha o cliente no formulário.'); idx = -1; }
    var names = ['Sem cliente'].concat(CL.map(function (c) { return c[0]; }));
    openForm('Novo lembrete', 'Fica só neste protótipo. Nada é enviado.', [
      { id: 't', label: 'O que lembrar', req: 1, value: p.title || '', max: 160 },
      { id: 'c', label: 'Cliente', type: 'select', options: names, value: idx > -1 ? CL[idx][0] : 'Sem cliente' },
      { id: 'd', label: 'Data', type: 'date', value: p.date || AGI(0), min: AGI(0), req: 1 },
      { id: 'h', label: 'Horário', type: 'time', value: p.time || '09:00' }
    ], function (v) {
      var df = Math.round((pdt(v.d) - pdt(AGI(0))) / 864e5);
      S.ag.push([df === 0 ? 'Hoje' : df === 1 ? 'Amanhã' : 'Depois', v.h || '—', v.t, v.c === 'Sem cliente' ? '' : v.c, 0, v.d]);
      if (W && agView === 'week') agWeek = W.mondayOf(new Date(pdt(v.d)));
      return 'Lembrete criado';
    }, 'Criar');
  }
  var pendingOpp = null;
  function openOportunidade(p) {
    p = p || {};
    var idx = resolveClient(p), c = idx > -1 ? CL[idx] : null;
    if (remote) {
      var rc = c && remoteClient(idx);
      if (!rc) { toast70('Associe a conversa a um cliente do CRM para criar a oportunidade.'); return; }
      pendingOpp = { nome: rc.nome, cid: String(rc.id), titulo: p.titulo || '' };
    } else {
      if (c && nameCount(c[0]) > 1) { toast70('Há clientes com o mesmo nome e a oportunidade guarda só o nome. Diferencie os cadastros antes.'); return; }
      pendingOpp = { nome: c ? c[0] : (p.nome || ''), cid: '', titulo: p.titulo || '' };
    }
    go('/oport');
    flushOpp(0);
  }
  function flushOpp(n) {
    if (!pendingOpp) return;
    var f = document.querySelector('#v iframe');
    if (f && f.contentWindow && f.dataset.ok === '1') {
      try { f.contentWindow.postMessage({ smei70: 1, tipo: 'nova', nome: pendingOpp.nome || '', cid: pendingOpp.cid || '', titulo: pendingOpp.titulo || '' }, location.origin); } catch (e) {}
    }
    if (n < 40) setTimeout(function () { flushOpp(n + 1); }, 300);
    else { pendingOpp = null; }
  }
  function openConversaDe(idx) {
    var c = CL[idx];
    if (!c) return false;
    if (!remote && c[10]) { go('/caixa/' + c[10]); return true; }
    toast70(remote ? 'A Caixa ainda não permite buscar a conversa a partir do cliente. Abra pela Caixa.' : 'Este cliente ainda não tem conversa.');
    return false;
  }
  function ctxFromConversation(id) {
    var c = C.find(function (x) { return x[0] === id; });
    var idx = -1, linked = false, explicit = false;
    if (remote) {
      var lk = window.SocialMEIInboxCustomer && window.SocialMEIInboxCustomer.linked && window.SocialMEIInboxCustomer.linked(id);
      if (lk) { idx = clientIndexById(lk.id); linked = idx > -1; explicit = linked; }
    } else {
      idx = CL.findIndex(function (x) { return x[10] === id; });
      explicit = idx > -1;
      if (idx < 0 && c) idx = clientIndexByName(c[1]);
      linked = idx > -1;
    }
    /* explicit = vínculo confirmado (servidor ou cadastro); linked sem explicit = só coincidência de nome (sugerido). */
    return { c: c, idx: idx, linked: linked, explicit: explicit, contact: c ? c[1] : '' };
  }
  /* v7.2 · cartão do cliente na Caixa: confirmado x sugerido x sem vínculo, com um resumo do 360° já carregado. */
  function ctxCard(x) {
    if (!x.linked) {
      var dups = !remote && x.contact ? nameCount(x.contact) : 0;
      var rem = remote ? 'Use “Associar cliente do CRM” na conversa. Nada é associado automaticamente.' : dups > 1 ? 'Há ' + dups + ' clientes com o nome “' + x.contact + '”. Não associamos sozinho: diferencie os cadastros antes de ligar a conversa.' : 'Este contato ainda não está no cadastro de clientes.';
      return { sig: 'none', html: '<div class="v72-cl" data-state="none"><span class="v72-badge">Sem cliente associado</span><p class="m sm">' + esc(rem) + '</p></div>' };
    }
    var m = model360(x.idx);
    if (!m) return { sig: 'none', html: '' };
    var os = m.src[1].st.s, nOpp = m.opps.filter(function (o) { return o.state === 'open'; }).length;
    var oppTxt = os === 'loading' ? '…' : (os === 'ok' || os === 'partial') ? String(nOpp) : '—';
    var kp = m.salesOk ? [['Pago', brl(m.tPaid)], ['Em aberto', brl(m.tOpen)], ['Oport.', oppTxt]] : [['Pago', '—'], ['Em aberto', '—'], ['Oport.', oppTxt]];
    var confirmed = x.explicit;
    var badge = confirmed ? '<span class="v72-badge ok">' + i('check', 12) + 'Cliente confirmado</span>' : '<span class="v72-badge warn">Sugerido pelo nome</span>';
    var note = confirmed ? '' : '<p class="m sm">Ainda não confirmado: o vínculo foi deduzido do nome do contato, sem confirmação de uma pessoa.</p>';
    var hl = m.health ? '<span class="v72-hl" data-k="' + m.health.k + '" title="' + esc(m.health.d) + '">' + esc(m.health.t) + '</span>' : '';
    var html = '<div class="v72-cl" data-state="' + (confirmed ? 'confirmed' : 'suggested') + '"><div class="v72-top">' + badge + hl + '</div><b class="v72-nm">' + esc(CL[x.idx][0]) + '</b>' + note +
      '<div class="v72-kp" role="list">' + kp.map(function (k) { return '<div role="listitem"><span>' + k[0] + '</span><b>' + esc(k[1]) + '</b></div>'; }).join('') + '</div>' +
      '<p class="v72-nx" data-tone="' + m.next.tone + '"><span>Próximo passo</span> ' + esc(m.next.t) + '</p></div>';
    return { sig: [confirmed, x.idx, kp.join('|'), m.next.t, m.next.tone, m.health && m.health.k].join('~'), html: html };
  }
  function paintCtx() {
    var r = route();
    if (r.r !== 'caixa' || !r.a) return;
    var box = document.querySelector('#v aside.cx');
    if (!box) return;
    var x = ctxFromConversation(r.a);
    var card = ctxCard(x), sig = r.a + '#' + card.sig;
    var old = box.querySelector('.v70-ctx');
    if (old && old.dataset.sig === sig) return;
    var name = x.linked ? CL[x.idx][0] : x.contact;
    var oppOk = !remote || x.linked;
    var node = E('<div class="v70-ctx" role="group" aria-label="Próximos passos com este contato" data-sig="' + esc(sig) + '">' +
      card.html +
      '<b class="v70-ct">Próximos passos</b>' +
      '<button class="btn' + (x.linked ? '' : ' o') + ' sm2 w" data-a="c360x:ver"' + (x.linked ? '' : ' disabled title="Associe esta conversa a um cliente do CRM para ver o resumo."') + '>' + i('users', 16) + (x.linked && !x.explicit ? 'Ver provável cliente 360°' : 'Ver perfil 360°') + '</button>' +
      '<button class="btn o sm2 w" data-a="c360x:lemb">' + i('cal', 16) + 'Lembrete de retorno</button>' +
      '<button class="btn o sm2 w" data-a="c360x:opp"' + (oppOk ? '' : ' disabled title="Associe esta conversa a um cliente do CRM para criar a oportunidade."') + '>' + i('spark', 16) + 'Criar oportunidade</button>' +
      (oppOk ? '' : '<p class="m sm">Para ver o resumo e criar oportunidade, associe a conversa a um cliente do CRM.</p>') + '</div>');
    if (old) old.replaceWith(node);
    else { var first = box.querySelector('details.cx4-sec'); if (first) first.parentNode.insertBefore(node, first); else box.appendChild(node); }
    node.dataset.name = name;
  }

  Object.assign(A, {
    c360: function (v, t) {
      var c = CL[S.cli]; if (!c) return false;
      if (v === 'lemb') { openLembrete({ idx: S.cli, title: 'Retorno: ' + c[1], date: AGI(1) }); return false; }
      if (v === 'opp') { openOportunidade({ idx: S.cli, titulo: '' }); return false; }
      if (v === 'retry') {
        loadOpps(true);
        if (remote && window.SocialMEIAgenda && window.SocialMEIAgenda.refresh) { try { window.SocialMEIAgenda.refresh(); } catch (e) {} }
        setTimeout(paint360, 0);
        return false;
      }
      if (v === 'agenda') { go('/agenda'); return false; }
      if (v === 'opps') { go('/oport'); return false; }
      if (v === 'all') { c3all = !c3all; S.keepScroll = true; paint360(); return false; }
      if (v.indexOf('fil-') === 0) { c3f = v.slice(4); c3all = false; S.keepScroll = true; paint360(); return false; }
      if (v === 'cobrar') { var k = +(t && t.dataset.k); if (V[k]) cobrar(k); return false; }
      if (v === 'venda') {
        openAction('venda');
        var d = document.getElementById('dlg'), sel = d && d.querySelector('#f_c');
        if (sel) {
          var rcv = remote ? remoteClient(S.cli) : null, opts = [].slice.call(sel.options), o;
          if (remote) o = rcv ? opts.filter(function (op) { return op.value === String(rcv.id); })[0] : null;
          else o = nameCount(c[0]) === 1 ? opts.filter(function (op) { return op.textContent === c[0] || op.textContent.indexOf(c[0] + ' ·') === 0; })[0] : null;
          if (o) sel.value = o.value; else toast70('Escolha o cliente no formulário.');
        }
        return false;
      }
      return false;
    },
    c360x: function (v) {
      var id = S.cur, x = ctxFromConversation(id);
      if (v === 'ver') { if (x.linked) { S.cli = x.idx; go('/negocio/clientes'); } return false; }
      if (v === 'lemb') { openLembrete({ idx: x.linked ? x.idx : -1, title: 'Retorno: ' + (x.contact || 'contato'), date: AGI(1) }); return false; }
      if (v === 'opp') { openOportunidade({ idx: x.linked ? x.idx : -1, nome: x.contact, titulo: '' }); return false; }
      return false;
    },
    agv: function (v) { agView = v === 'week' ? 'week' : 'list'; try { localStorage.setItem(VIEW_KEY, agView); } catch (e) {} },
    agok: function (v) { var a = S.ag[+v]; if (a) a[4] = a[4] ? 0 : 1; }
  });
  if (!remote) {
    A.agnew = function (v) {
      var pre = v === 'amanha' ? { date: AGI(1), title: 'Retorno com cliente' } : v === 'cobranca' ? { date: AGI(3), title: 'Cobrar pagamento pendente' } : {};
      openLembrete(pre);
      return false;
    };
    window.agenda = agenda70;
  }

  /* mensagens vindas da tela de Oportunidades (quadro embutido, mesma origem) */
  window.addEventListener('message', function (e) {
    var d = e.data;
    if (e.origin !== location.origin || !d || !d.smei70) return;
    var f = document.querySelector('#v iframe');
    if (!f || e.source !== f.contentWindow) return;
    if (d.tipo === 'nova-ok') { pendingOpp = null; return; }
    var idx = remote ? clientIndexById(d.cid) : clientIndexByName(d.nome);
    var unresolved = function () {
      toast70(remote ? 'Não foi possível identificar este cliente com segurança.' : nameCount(d.nome) > 1 ? 'Há clientes com o mesmo nome. Não dá para escolher um sem risco.' : 'Este nome ainda não está no cadastro de clientes.');
    };
    if (d.tipo === 'cliente') {
      if (idx < 0) { unresolved(); return; }
      S.cli = idx; go('/negocio/clientes');
    } else if (d.tipo === 'conversa') {
      if (idx < 0) { unresolved(); return; }
      openConversaDe(idx);
    } else if (d.tipo === 'lembrete') {
      if (idx < 0 && remote) unresolved();
      openLembrete({ idx: idx, title: 'Retomar: ' + (d.titulo || strip(d.nome)), date: d.follow && /^\d{4}-\d{2}-\d{2}$/.test(d.follow) && d.follow >= AGI(0) ? d.follow : AGI(1) });
    }
  });

  /* ---------- 4. Formulário de venda: total acompanha produto x quantidade ---------- */
  function bindVenda() {
    var d = document.getElementById('dlg');
    if (!d) return;
    var p = d.querySelector('#f_p'), q = d.querySelector('#f_q'), v = d.querySelector('#f_v');
    if (!p || !q || !v || p.tagName !== 'SELECT') return;
    var touched = false;
    v.addEventListener('input', function () { touched = true; });
    var calc = function () {
      if (touched) return;
      var pr = PR.filter(function (x) { return remote ? x[1] === p.value : x[0] === p.value; })[0];
      var n = parseInt(q.value, 10);
      if (!pr || !(n >= 1) || !(Number(pr[3]) >= 0)) return;
      v.value = String((Number(pr[3]) * n).toFixed(2)).replace('.', ',');
    };
    p.addEventListener('change', calc); q.addEventListener('input', calc); calc();
  }
  var openAction0 = window.openAction;
  window.openAction = function (k) {
    var r = openAction0.apply(this, arguments);
    if (k === 'venda') { try { bindVenda(); } catch (e) {} }
    return r;
  };

  /* ---------- ligação ao ciclo de desenho do app ---------- */
  var render0 = window.render;
  window.render = function () {
    var r = render0.apply(this, arguments);
    try {
      var rt = route();
      if (rt.r === 'negocio' && rt.a === 'clientes') paint360();
      else if (rt.r === 'caixa') paintCtx();
      else if (rt.r === 'agenda' && !remote) mountWeek();
    } catch (e) { console.warn('v7.0:', e); }
    return r;
  };
  document.addEventListener('socialmei-agenda-painted', function () { if (location.hash === '#/negocio/clientes') paint360(); });
  watchWrites();
  window.SocialMEI70 = { model360: model360, openLembrete: openLembrete, openOportunidade: openOportunidade, _t: { opps: function () { return oppStore; }, invalidate: invalidateOpps, load: loadOpps } };
  var r0 = route();
  if ((r0.r === 'negocio' && r0.a === 'clientes') || r0.r === 'caixa' || r0.r === 'agenda') render();
})();
