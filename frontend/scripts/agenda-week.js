/* SocialMEI-IA · v7.3 · Visão semanal da Agenda.
   Componente de apresentação, sem rede e sem armazenamento próprio: quem chama entrega os dados já
   carregados e recebe os cliques por callbacks. Lembretes e agendamentos de serviços são listas SEPARADAS
   (nunca se misturam nos dados; só se juntam na tela, por horário, com aparência diferente).
   Contrato de entrada (tudo opcional, exceto weekStart/today/items):
     weekStart:'YYYY-MM-DD' (segunda), today:'YYYY-MM-DD',
     items:[{key,iso,time,title,client,notes,status,late}]                 lembretes
     services:[{key,iso,time,end,title,client,resource,status,late,channel}] agendamentos de serviços (somente leitura)
     servicesState:{s:'ok'|'loading'|'error'|'unavailable', msg}             situação da fonte de serviços
     hours:[7 textos] horário comercial por dia (''=fechado, null/ausente=não informado)
     selected:'YYYY-MM-DD' dia aberto no celular
     busy (bloqueia ações), navBusy (bloqueia só a navegação; padrão = busy), canWrite, loading, error,
     onNav(delta), onJump(iso), onToggle(item), onNew(iso), onOpenService(key), onSelect(iso), onRetry()  ->  HTMLElement */
(function () {
  'use strict';
  var DAYS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'];
  var MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  function parse(iso) { var p = String(iso).split('-'); return new Date(+p[0], +p[1] - 1, +p[2], 12); }
  function fmt(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  function addDays(iso, n) { var d = parse(iso); d.setDate(d.getDate() + n); return fmt(d); }
  function mondayOf(v) {
    var d = v instanceof Date ? new Date(v) : parse(v);
    d.setHours(12, 0, 0, 0);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    return fmt(d);
  }
  function range(weekStart) { return { from: weekStart, to: addDays(weekStart, 6) }; }
  /* "29 dez 2026 – 4 jan 2027" na virada de ano; "26 – 30 nov 2026" no mesmo mês. */
  function label(weekStart) {
    var a = parse(weekStart), b = parse(addDays(weekStart, 6));
    var left = a.getDate() + (a.getMonth() !== b.getMonth() || a.getFullYear() !== b.getFullYear() ? ' ' + MONTHS[a.getMonth()] : '') + (a.getFullYear() !== b.getFullYear() ? ' ' + a.getFullYear() : '');
    return left + ' – ' + b.getDate() + ' ' + MONTHS[b.getMonth()] + ' ' + b.getFullYear();
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }
  function longDay(d) { return d.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' }); }
  var STATE_LABEL = { done: 'Concluído', cancelled: 'Cancelado' };

  function build(o) {
    var root = el('section', 'wk');
    var end = addDays(o.weekStart, 6);
    root.setAttribute('aria-label', 'Agenda da semana ' + label(o.weekStart));
    root.setAttribute('aria-busy', String(!!o.loading));
    var inWeek = function (i) { return i.iso >= o.weekStart && i.iso <= end; };
    var items = (o.items || []).filter(inWeek);
    var services = (o.services || []).filter(inWeek).filter(function (s) { return s.status !== 'cancelled'; });
    var pend = items.filter(function (i) { return i.status === 'pending'; }).length;
    var late = items.filter(function (i) { return i.late; }).length;
    var done = items.filter(function (i) { return i.status === 'done'; }).length;
    var sv = o.servicesState || null;
    var selected = o.selected && o.selected >= o.weekStart && o.selected <= end ? o.selected : (o.today >= o.weekStart && o.today <= end ? o.today : o.weekStart);

    /* ---- barra: navegação, título, ir para data, legenda ---- */
    var nb = o.navBusy !== undefined ? o.navBusy : o.busy;
    var bar = el('div', 'wk-bar');
    var nav = el('div', 'wk-nav');
    nav.setAttribute('role', 'group');
    nav.setAttribute('aria-label', 'Navegar entre semanas');
    [['‹', 'Semana anterior', -1], ['Hoje', 'Voltar para a semana de hoje', 0], ['›', 'Próxima semana', 1]].forEach(function (b) {
      var n = el('button', 'wk-b' + (b[2] === 0 ? ' wk-today' : ''), b[0]);
      n.type = 'button';
      n.setAttribute('aria-label', b[1]);
      n.title = b[1] + (b[2] ? ' (seta ' + (b[2] < 0 ? 'esquerda' : 'direita') + ')' : ' (tecla T)');
      n.disabled = !!nb;
      n.onclick = function () { o.onNav(b[2]); };
      nav.append(n);
    });
    var ttl = el('h2', 'wk-t', label(o.weekStart));
    ttl.setAttribute('aria-live', 'polite');
    bar.append(nav, ttl);
    if (o.onJump) {
      var jl = el('label', 'wk-jump');
      jl.append(el('span', '', 'Ir para'));
      var ji = el('input');
      ji.type = 'date';
      ji.value = selected;
      ji.disabled = !!nb;
      ji.setAttribute('aria-label', 'Ir para uma data');
      ji.onchange = function () { if (/^\d{4}-\d{2}-\d{2}$/.test(ji.value)) o.onJump(ji.value); };
      jl.append(ji);
      bar.append(jl);
    }
    var legend = el('p', 'wk-lg');
    legend.setAttribute('aria-label', 'Legenda');
    var l1 = el('span', 'wk-lg-r', 'Lembrete'), l2 = el('span', 'wk-lg-s', 'Serviço agendado');
    legend.append(l1);
    if (sv || services.length) legend.append(l2);
    bar.append(legend);

    var parts = [];
    if (items.length) parts.push(plural(pend, 'lembrete pendente', 'lembretes pendentes'));
    if (late) parts.push(plural(late, 'atrasado', 'atrasados'));
    if (done) parts.push(plural(done, 'feito', 'feitos'));
    if (services.length) parts.push(plural(services.length, 'serviço agendado', 'serviços agendados'));
    var sum = el('p', 'wk-sum',
      o.error ? o.error :
      o.loading ? 'Consultando a semana…' :
      parts.length ? parts.join(' · ') : 'Semana livre' + (o.canWrite && o.onNew ? '. Use o + de um dia para criar um lembrete.' : '.'));
    sum.setAttribute('role', 'status');
    if (o.error) {
      sum.dataset.kind = 'err';
      if (o.onRetry) { var rt = el('button', 'wk-retry', 'Tentar de novo'); rt.type = 'button'; rt.onclick = o.onRetry; sum.append(' ', rt); }
    }
    bar.append(sum);
    if (sv && sv.s && sv.s !== 'ok') {
      var sn = el('p', 'wk-note', sv.s === 'loading' ? 'Consultando agendamentos de serviços…' : sv.msg || 'Agendamentos de serviços indisponíveis. Os lembretes continuam valendo.');
      sn.dataset.s = sv.s;
      sn.setAttribute('role', 'status');
      bar.append(sn);
    }
    root.append(bar);

    /* ---- faixa de dias (celular): um dia por vez ---- */
    var strip = el('div', 'wk-strip');
    strip.setAttribute('role', 'group');
    strip.setAttribute('aria-label', 'Escolher o dia da semana');
    var cols = {};
    function select(iso) {
      selected = iso;
      Object.keys(cols).forEach(function (k) { cols[k].classList.toggle('is-sel', k === iso); });
      [].forEach.call(strip.children, function (b) { b.setAttribute('aria-pressed', String(b.dataset.iso === iso)); });
      if (o.onSelect) o.onSelect(iso);
    }
    for (var s0 = 0; s0 < 7; s0++) {
      var iso0 = addDays(o.weekStart, s0), d0 = parse(iso0);
      var cnt = items.filter(function (i) { return i.iso === iso0; }).length + services.filter(function (i) { return i.iso === iso0; }).length;
      var sb = el('button', 'wk-sd' + (iso0 === o.today ? ' is-today' : ''));
      sb.type = 'button';
      sb.dataset.iso = iso0;
      sb.setAttribute('aria-pressed', String(iso0 === selected));
      sb.setAttribute('aria-label', longDay(d0) + (iso0 === o.today ? ', hoje' : '') + ', ' + (cnt ? plural(cnt, 'compromisso', 'compromissos') : 'livre'));
      sb.append(el('span', 'wk-sdn', DAYS[s0]), el('b', '', String(d0.getDate())), el('i', cnt ? 'wk-dot on' : 'wk-dot'));
      sb.onclick = (function (x) { return function () { select(x); }; })(iso0);
      strip.append(sb);
    }
    root.append(strip);

    /* ---- grade ---- */
    var grid = el('div', 'wk-grid');
    grid.setAttribute('role', 'list');
    for (var k = 0; k < 7; k++) {
      var iso = addDays(o.weekStart, k), d = parse(iso);
      var col = el('section', 'wk-d' + (iso === o.today ? ' is-today' : '') + (iso < o.today ? ' is-past' : '') + (iso === selected ? ' is-sel' : ''));
      cols[iso] = col;
      col.setAttribute('role', 'listitem');
      col.dataset.iso = iso;
      var hid = 'wk-h-' + iso;
      col.setAttribute('aria-labelledby', hid);
      var head = el('header', 'wk-dh');
      var hh = el('h3');
      hh.id = hid;
      hh.append(el('span', 'wk-dn', DAYS[k]), document.createTextNode(' '), el('b', 'wk-dd', String(d.getDate())));
      hh.setAttribute('aria-label', longDay(d) + (iso === o.today ? ', hoje' : ''));
      head.append(hh);
      if (iso === o.today) head.append(el('span', 'wk-tag', 'Hoje'));
      if (o.canWrite && o.onNew) {
        var add = el('button', 'wk-add', '+');
        add.type = 'button';
        add.setAttribute('aria-label', 'Novo lembrete em ' + longDay(d));
        add.title = 'Novo lembrete neste dia';
        add.disabled = !!o.busy;
        add.onclick = (function (x) { return function () { o.onNew(x); }; })(iso);
        head.append(add);
      }
      var hr = o.hours && o.hours[k];
      if (hr === '' || hr) {
        var hs = el('span', 'wk-hr' + (hr === '' ? ' is-closed' : ''), hr === '' ? 'Fechado' : hr);
        hs.title = 'Horário comercial informado no negócio. Não é a disponibilidade para agendar.';
        head.append(hs);
      }
      col.append(head);
      var list = el('div', 'wk-l');
      var day = [];
      items.filter(function (i) { return i.iso === iso; }).forEach(function (i) { day.push({ k: 'r', v: i }); });
      services.filter(function (i) { return i.iso === iso; }).forEach(function (i) { day.push({ k: 's', v: i }); });
      day.sort(function (a, b) { return (a.v.time || '99').localeCompare(b.v.time || '99'); });
      if (!day.length) {
        if (o.canWrite && o.onNew && !o.busy) {
          var fr = el('button', 'wk-e wk-free', hr === '' ? 'Dia fechado · adicionar lembrete' : 'Livre · adicionar');
          fr.type = 'button';
          fr.setAttribute('aria-label', 'Dia livre, criar lembrete em ' + longDay(d));
          fr.onclick = (function (x) { return function () { o.onNew(x); }; })(iso);
          list.append(fr);
        } else list.append(el('p', 'wk-e', hr === '' ? 'Fechado' : 'Livre'));
      }
      day.forEach(function (e) {
        var it = e.v, row;
        if (e.k === 'r') {
          row = el('div', 'wk-i' + (it.status === 'done' ? ' done' : '') + (it.late ? ' late' : ''));
          row.dataset.kind = 'reminder';
          var ck = el('button', 'wk-ck', it.status === 'done' ? '✓' : '');
          ck.type = 'button';
          ck.setAttribute('role', 'checkbox');
          ck.setAttribute('aria-checked', String(it.status === 'done'));
          ck.setAttribute('aria-label', 'Marcar como feito: ' + it.title);
          ck.disabled = !!o.busy || !o.canWrite;
          ck.onclick = function () { o.onToggle(it); };
          var tx = el('div', 'wk-x');
          tx.append(el('time', 'wk-tm', it.time || 'Sem hora'), el('b', 'wk-tt', it.title));
          if (it.client) tx.append(el('small', 'wk-cl', it.client));
          if (it.late) tx.append(el('small', 'wk-late', 'Atrasado'));
          row.append(ck, tx);
        } else {
          row = el('button', 'wk-s' + (it.status === 'done' ? ' done' : '') + (it.late ? ' late' : ''));
          row.type = 'button';
          row.dataset.kind = 'service';
          row.dataset.key = it.key;
          row.setAttribute('aria-label', 'Serviço agendado: ' + it.title + (it.client ? ' para ' + it.client : '') + ', ' + (it.time || '') + (it.end ? ' às ' + it.end : '') + '. Ver na lista de agendamentos.');
          row.disabled = !o.onOpenService;
          var st = el('div', 'wk-x');
          st.append(el('time', 'wk-tm', (it.time || '') + (it.end ? ' – ' + it.end : '')), el('b', 'wk-tt', it.title));
          var who = [it.client, it.resource].filter(Boolean).join(' · ');
          if (who) st.append(el('small', 'wk-cl', who));
          var tag = STATE_LABEL[it.status] || (it.late ? 'Passou do horário' : '');
          if (tag) st.append(el('small', it.late && !STATE_LABEL[it.status] ? 'wk-late' : 'wk-cl', tag));
          row.append(el('span', 'wk-sb'), st);
          row.onclick = function () { o.onOpenService(it.key); };
        }
        list.append(row);
      });
      col.append(list);
      grid.append(col);
    }
    root.append(grid);

    /* ---- teclado: setas trocam de semana, T volta para hoje (fora de campos de texto) ---- */
    root.addEventListener('keydown', function (ev) {
      if (ev.altKey || ev.ctrlKey || ev.metaKey || nb) return;
      var t = ev.target;
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
      if (ev.key === 'ArrowLeft') { ev.preventDefault(); o.onNav(-1); }
      else if (ev.key === 'ArrowRight') { ev.preventDefault(); o.onNav(1); }
      else if (ev.key === 't' || ev.key === 'T') { ev.preventDefault(); o.onNav(0); }
    });
    return root;
  }
  window.SocialMEIAgendaWeek = { build: build, mondayOf: mondayOf, addDays: addDays, range: range, label: label, parse: parse, fmt: fmt };
})();
