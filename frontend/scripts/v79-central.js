/* SocialMEI-IA · v7.9 · Central de Atendimento Inteligente (camada de interface da Caixa Unificada).
   Preferências autenticadas são gravadas pelos contratos da Caixa.
   - fotos: se a imagem falhar, voltam as iniciais
   - busca da lista preservada entre atualizações; canal e situação lembrados neste navegador
   - painel do contato: vínculo com o CRM (lê o estado que v22-inbox-customer já consulta), dados cadastrais reais
   - Lia · leitura rápida: regras locais sobre as mensagens abertas (sem IA generativa, nada é enviado)
   - modo do atendimento (bot x humano) lido do contrato existente /whatsapp/bot/conversations/{id}/status
   - mídia: ganchos para SocialMEIMedia, sem anexos inventados */
(function () {
  'use strict';
  if (window.SocialMEI79) return;
  if (typeof render !== 'function' || typeof C === 'undefined' || typeof S === 'undefined') {
    console.warn('v7.9: o app base ainda não está pronto.');
    return;
  }
  var host = window.SocialMEIV22, remote = !!(host && host.remote);
  var FLT = 'smei-v79-flt', LIA = 'smei-v79-lia';
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return [].slice.call((r || document).querySelectorAll(s)); }
  function E(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }
  function ls(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) {} return null; }
  function curId() { var m = /^#\/caixa\/([^/?#]+)/.exec(location.hash); return m ? decodeURIComponent(m[1]) : null; }
  function digits(t) { return String(t || '').replace(/\D/g, ''); }
  function nz(t) { return String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim(); }
  function first(name) { var m = String(name || '').match(/\p{L}[\p{L}'’-]*/u); return m ? m[0] : ''; }
  function svg(n, s) {
    var P = { spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>', x: '<path d="M18 6 6 18M6 6l12 12"/>', down: '<path d="M6 9l6 6 6-6"/>', link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>', warn: '<path d="M12 3 2 21h20L12 3zM12 10v5M12 18v.01"/>' };
    return '<svg viewBox="0 0 24 24" width="' + (s || 16) + '" height="' + (s || 16) + '" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (P[n] || '') + '</svg>';
  }

  /* ---------- 1. fotos: falhou? voltam as iniciais ---------- */
  document.addEventListener('error', function (e) {
    var t = e.target;
    if (t && t.tagName === 'IMG' && t.classList.contains('av-ph')) { if (t.parentNode) t.parentNode.classList.remove('has-ph'); t.remove(); }
  }, true);

  /* ---------- 2. filtros lembrados e busca preservada ---------- */
  var query = '';
  (function restore() {
    try {
      var f = JSON.parse(ls(FLT) || '{}');
      if (f.cc === 'wa' || f.cc === 'ig') S.cc = f.cc;
      if (['Todas', 'Não lidas', 'Aguardando', 'Respondidas', 'Concluídas', 'Adiadas'].indexOf(f.cf) > -1) S.cf = f.cf;
    } catch (e) {}
  })();
  function saveFilters() { ls(FLT, JSON.stringify({ cc: S.cc || '', cf: S.cf || 'Todas' })); }
  document.addEventListener('input', function (e) {
    var t = e.target;
    if (t && t.matches && t.matches('input[data-q=".ci"]')) { query = t.value; syncClear(t); }
  }, true);
  function syncClear(inp) {
    var lab = inp.closest('label'); if (!lab) return;
    var b = $('.cx79-clr', lab);
    if (!b) {
      b = E('button', 'cx79-clr'); b.type = 'button'; b.setAttribute('aria-label', 'Limpar busca'); b.innerHTML = svg('x', 14);
      b.addEventListener('click', function (ev) { ev.preventDefault(); inp.value = ''; query = ''; inp.dispatchEvent(new Event('input', { bubbles: true })); syncClear(inp); inp.focus(); });
      lab.append(b);
    }
    b.hidden = !inp.value;
  }
  function paintSearch() {
    var inp = $('#v input[data-q=".ci"]'); if (!inp) return;
    inp.setAttribute('autocomplete', 'off'); inp.setAttribute('type', 'search'); inp.setAttribute('inputmode', 'search');
    if (query && inp.value !== query) { inp.value = query; if (typeof filt === 'function') filt(inp); }
    syncClear(inp);
    var label = inp.closest('label');
    if (remote && host.hiddenConversations && label && !$('#v [data-v79-restore]')) {
      var restore = E('button', 'btn o sm2', 'Conversas ocultas');
      restore.type = 'button';
      restore.dataset.v79Restore = '1';
      restore.addEventListener('click', showHiddenConversations);
      label.after(restore);
    }
    paintInboxPreferences(label);
  }
  function canEditInbox() {
    return ['owner', 'admin', 'member'].includes(window.SocialMEIAuth?.current?.papel);
  }

  function paintInboxPreferences(label) {
    if (!remote || !host.updateInboxPreferences || !label) return;
    if (!$('#v [data-v79-inbox-archive]')) {
      var archived = E('button', 'btn o sm2', 'Conversas arquivadas');
      archived.type = 'button';
      archived.dataset.v79InboxArchive = '1';
      archived.onclick = () => showInboxSelection(true);
      label.after(archived);
      if (canEditInbox()) {
        var select = E('button', 'btn o sm2', 'Selecionar conversas');
        select.type = 'button';
        select.onclick = () => showInboxSelection(false);
        archived.after(select);
      }
    }
    var menu = $('#v .cx4-pop[data-for="cvmore"]');
    var row = host.conversation(curId());
    if (!menu || !row?.last_inbound_id || !canEditInbox() || $('[data-v79-mark-read]', menu)) return;
    var mark = E('button', 'cx4-mi', row.unread ? 'Marcar como lida' : 'Marcar como não lida');
    mark.type = 'button';
    mark.setAttribute('role', 'menuitem');
    mark.dataset.v79MarkRead = '1';
    menu.prepend(mark);
    mark.onclick = async () => {
      var identity = host.identity;
      mark.disabled = true;
      try {
        await host.updateInboxPreferences(row.unread ? 'read' : 'unread', [row.id],
          row.unread ? row.last_inbound_id : null);
      } catch (error) {
        if (identity === host.identity && mark.isConnected) {
          mark.disabled = false;
          mark.textContent = error.message || 'Não foi possível alterar a leitura.';
        }
      }
    };
  }

  async function showInboxSelection(archived) {
    var dialog = dlg();
    if (dialog.open) return;
    var identity = host.identity;
    var form = E('form'), title = E('h2', '', archived ? 'Conversas arquivadas' : 'Selecionar conversas');
    title.id = 'v79-inbox-selection-title';
    form.method = 'dialog';
    form.setAttribute('aria-labelledby', title.id);
    var live = () => dialog.open && form.isConnected && identity === host.identity;
    var status = E('p', 'm', 'Carregando conversas…');
    status.setAttribute('role', 'status');
    var list = E('ul'), actions = E('div'), close = E('button', 'btn o', 'Fechar');
    var buttons = [];
    function addAction(label, action) {
      var button = E('button', 'btn o', label);
      button.type = 'button';
      button.disabled = true;
      actions.append(button);
      buttons.push(button);
      button.onclick = async () => {
        var checked = $$('input:checked', list);
        var ids = checked.map(input => Number(input.value));
        if (!live() || !ids.length) return;
        if (ids.length > 50) { status.textContent = 'Selecione até 50 conversas por operação.'; return; }
        if (action !== 'unarchive' && !window.confirm(label + ' (' + ids.length + ')?')) return;
        buttons.forEach(b => { b.disabled = true; });
        $$('input', list).forEach(input => { input.disabled = true; });
        try {
          await host.updateInboxPreferences(action, ids);
          if (!live()) return;
          checked.forEach(input => input.closest('li').remove());
          status.textContent = 'Alteração confirmada.';
          if (!archived && ids.some(id => curId() === 'me-' + id)) location.hash = '#/caixa';
          close.focus();
        } catch (error) {
          if (live()) status.textContent = error.message || 'Não foi possível concluir a alteração.';
        } finally {
          if (live()) {
            $$('input', list).forEach(input => { input.disabled = false; });
            buttons.forEach(b => { b.disabled = !$('input:checked', list); });
          }
        }
      };
    }
    if (canEditInbox()) {
      if (archived) addAction('Desarquivar selecionadas', 'unarchive');
      else {
        addAction('Arquivar selecionadas', 'archive');
        addAction('Ocultar selecionadas', 'hide');
      }
    }
    list.onchange = () => { buttons.forEach(b => { b.disabled = !$('input:checked', list); }); };
    form.append(title, status, list, actions, close);
    dialog.replaceChildren(form);
    dialog.showModal();
    try {
      var rows = archived ? await host.archivedConversations() : host.activeInboxPreferences();
      if (!live()) return;
      status.textContent = rows.length ? '' : 'Nenhuma conversa disponível.';
      for (const row of rows) {
        const li = E('li'), label = E('label');
        if (canEditInbox()) {
          const input = E('input');
          input.type = 'checkbox';
          input.value = row.id;
          label.append(input);
        }
        const channel = row.channel === 'instagram' ? 'Instagram' : 'WhatsApp';
        label.append(E('span', '', (row.contact_name || 'Contato') + ' · ' + channel));
        li.append(label);
        list.append(li);
      }
    } catch (error) {
      if (live()) status.textContent = error.message || 'Não foi possível consultar as conversas.';
    }
  }

  async function showHiddenConversations() {
    var dialog = dlg();
    if (dialog.open) return;
    var identity = host.identity;
    var form = E('form'), title = E('h2', '', 'Conversas ocultas');
    form.method = 'dialog';
    title.id = 'v79-restore-title';
    form.setAttribute('aria-labelledby', title.id);
    var status = E('p', 'm', 'Consultando a sua Caixa…');
    status.setAttribute('role', 'status');
    var list = E('ul');
    var close = E('button', 'btn o', 'Fechar');
    form.append(title, status, list, close);
    dialog.replaceChildren(form);
    dialog.showModal();
    var live = () => dialog.open && form.isConnected && identity === host.identity;
    try {
      var rows = await host.hiddenConversations();
      if (!live()) return;
      status.textContent = rows.length ? 'Conversas ocultas por você neste negócio.' : 'Nenhuma conversa oculta.';
      for (const row of rows) {
        const li = E('li');
        li.append(E('span', '', row.contact_name || 'Contato'));
        if (['owner', 'admin', 'member'].includes(window.SocialMEIAuth?.current?.papel)) {
          const button = E('button', 'btn o sm2', 'Restaurar');
          button.type = 'button';
          button.onclick = async () => {
            if (!live()) return;
            button.disabled = true;
            try {
              await host.restoreConversation(row.id);
              if (!live()) return;
              li.remove();
              status.textContent = list.children.length ? 'Conversa restaurada.' : 'Conversa restaurada. Nenhuma conversa oculta.';
              close.focus();
            } catch (error) {
              if (!live()) return;
              status.textContent = error.message || 'Não foi possível restaurar a conversa.';
              button.disabled = false;
            }
          };
          li.append(button);
        }
        list.append(li);
      }
    } catch (error) {
      if (live()) status.textContent = error.message || 'Não foi possível consultar as conversas ocultas.';
    }
  }
  document.addEventListener('keydown', function (e) {
    var t = e.target, typing = t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
    if (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey && /^#\/caixa/.test(location.hash)) {
      var inp = $('#v input[data-q=".ci"]'); if (inp) { e.preventDefault(); inp.focus(); inp.select(); }
    } else if (e.key === 'Escape' && t && t.matches && t.matches('input[data-q=".ci"]') && t.value) {
      e.preventDefault(); e.stopPropagation(); var b = $('.cx79-clr', t.closest('label')); if (b) b.click();
    }
  }, true);

  /* ---------- 3. ir para as mensagens recentes ---------- */
  function paintJump() {
    var ms = $('#v .ct .ms'), ct = $('#v .ct'); if (!ms || !ct) return;
    var b = $('.cx79-jump', ms);
    if (!b) {
      b = E('button', 'cx79-jump'); b.type = 'button'; b.hidden = true; b.setAttribute('aria-label', 'Ir para as mensagens mais recentes'); b.title = 'Mensagens mais recentes';
      b.innerHTML = svg('down', 18);
      b.addEventListener('click', function () {
        var m = $('#v .ct .ms'); if (!m) return;
        m.scrollTo({ top: m.scrollHeight, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
      });
      ms.append(b);
    }
    var upd = function () { b.hidden = ms.scrollHeight - ms.scrollTop - ms.clientHeight < 240; };
    if (!ms.dataset.v79j) { ms.dataset.v79j = '1'; ms.addEventListener('scroll', upd, { passive: true }); }
    upd();
  }

  /* ---------- 4. modo do atendimento (somente leitura) ---------- */
  var modes = new Map();
  function paintMode() {
    var chip = $('[data-v79-mode]'); if (!chip || !remote || !host.conversation) return;
    var id = curId(), row = id && host.conversation(id);
    if (!row || row.origin !== 'waha' || ['owner', 'admin'].indexOf(host.identity && host.identity.papel) < 0) return;
    var c = modes.get(id);
    var show = function (d) {
      var el = $('[data-v79-mode]'); if (!el || curId() !== id) return;
      if (!d || ['menu', 'ask_product', 'human'].indexOf(d.state) < 0 || typeof d.enabled !== 'boolean') { el.hidden = true; return; }
      var human = d.state === 'human';
      if (!human && !d.enabled) { el.hidden = true; return; }
      el.textContent = human ? 'Atendimento humano' : 'Respostas automáticas ativas';
      el.dataset.m = human ? 'human' : 'auto'; el.hidden = false;
    };
    if (c && Date.now() - c.at < 30000) { show(c.d); return; }
    if (c && c.busy) return;
    modes.set(id, { at: 0, busy: true, d: c && c.d });
    host.request('/whatsapp/bot/conversations/' + row.id + '/status').then(function (d) { modes.set(id, { at: Date.now(), d: d }); show(d); }, function () { modes.set(id, { at: Date.now(), d: null }); show(null); });
  }

  /* ---------- 5. painel do contato · CRM ---------- */
  var obs = null;
  function writer() { return ['owner', 'admin', 'member'].indexOf(host && host.identity && host.identity.papel) > -1; }
  function proxy(re) { var src = $('.inbox-customer'); if (!src) return null; return $$('button', src).filter(function (b) { return re.test(b.textContent); })[0] || null; }
  function clientById(id) { var l = (host && host.clients) || []; for (var i = 0; i < l.length; i++) if (l[i].id === id) return l[i]; return null; }
  function similar(meta, name) {
    var l = (host && host.clients) || [], p = digits(meta && meta.phone), out = [];
    if (p.length >= 8) l.forEach(function (c) { if (digits(c.telefone).length >= 8 && digits(c.telefone).slice(-8) === p.slice(-8)) out.push({ c: c, why: 'mesmo telefone' }); });
    if (!out.length && name) { var n = nz(name), m = l.filter(function (c) { return nz(c.nome) === n; }); if (m.length === 1) out.push({ c: m[0], why: 'mesmo nome' }); }
    return out;
  }
  function paintCrm() {
    var box = $('[data-v79-crm]'); if (!box || !remote) return;
    var id = box.dataset.v79Crm, src = $('.inbox-customer'), chip = src && $('.inbox-customer-chip', src), st = chip ? chip.dataset.state : 'load';
    var link = window.SocialMEIInboxCustomer && window.SocialMEIInboxCustomer.linked && window.SocialMEIInboxCustomer.linked(id);
    var c = C.find(function (x) { return x[0] === id; }) || [], meta = c[11] || {};
    var sig = [id, st, link && link.id, link && link.nome, (host.clients || []).length].join('|');
    if (box.dataset.sig === sig) return; box.dataset.sig = sig;
    box.replaceChildren();
    var btn = function (label, fn, primary, dis) { var b = E('button', 'btn sm2 w' + (primary ? '' : ' o'), label); b.type = 'button'; b.disabled = !!dis; b.addEventListener('click', fn); return b; };
    var pill = function (text, tone) { var s = E('span', 'cx79-pill', text); s.dataset.tone = tone; return s; };
    if (!src || st === 'load' || (!link && st !== 'none' && st !== 'err')) { box.append(E('p', 'm sm', 'Consultando vínculo com o CRM…')); return; }
    if (st === 'err') {
      box.append(pill('Vínculo indisponível', 'err'), E('p', 'm sm', 'Não foi possível consultar o cadastro agora. O atendimento continua normalmente.'));
      box.append(btn('Tentar de novo', function () { var r = proxy(/Atualizar|Tentar/); if (r) r.click(); }));
      return;
    }
    if (link) {
      var cl = clientById(link.id) || {}, top = E('div', 'cx79-crmh');
      top.append(E('b', '', link.nome), pill('Cliente confirmado', 'ok')); box.append(top);
      var kv = function (l, v) { if (!v) return; var r = E('div', 'cx4-kv'); r.append(E('span', 'm', l), E('span', '', v)); box.append(r); };
      kv('Telefone', cl.telefone); kv('E-mail', cl.email);
      if (cl.observacao) kv('Observação', String(cl.observacao).slice(0, 140));
      var a = E('a', 'btn sm2 w'); a.href = '#'; a.dataset.a = 'c360x:ver'; a.textContent = 'Ver cliente no CRM'; a.setAttribute('role', 'button'); box.append(a);
      var alt = btn('Alterar vínculo', function () { var b = proxy(/Associar|Alterar/); if (b) b.click(); }, false, !writer()); box.append(alt);
      return;
    }
    box.append(pill('Sem cliente associado', 'none'), E('p', 'm sm', 'Nada é associado automaticamente. Confirme o cliente para ver compras e próximos passos.'));
    var sim = similar(meta, c[1]);
    if (sim.length) {
      var s0 = sim[0];
      box.append(E('p', 'cx79-sim', 'Cadastro com ' + s0.why + ': ' + s0.c.nome));
      box.append(btn('Associar a ' + first(s0.c.nome), function () {
        var b = proxy(/Associar|Alterar/); if (!b) return; b.click();
        var n = 0, t = setInterval(function () { var sel = document.getElementById('f_inbox_customer'); if (sel || ++n > 30) { clearInterval(t); if (sel && [].some.call(sel.options, function (o) { return o.value === String(s0.c.id); })) sel.value = String(s0.c.id); } }, 100);
      }, true, !writer()));
    } else {
      box.append(btn('Escolher cliente existente', function () { var b = proxy(/Associar|Alterar/); if (b) b.click(); }, true, !writer()));
      var nw = E('button', 'lk cx79-new', 'Cadastrar novo cliente'); nw.type = 'button'; nw.dataset.a = 'novo:cliente'; box.append(nw);
    }
  }
  function watchCrm() {
    var src = $('.inbox-customer');
    if (obs) { obs.disconnect(); obs = null; }
    if (!src || !remote) return;
    obs = new MutationObserver(function () { var b = $('[data-v79-crm]'); if (b) { b.dataset.sig = ''; paintCrm(); } });
    obs.observe(src, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['data-state'] });
  }

  /* ---------- 6. Lia · leitura rápida (regras locais, sem IA generativa) ---------- */
  var NEEDS = [
    { k: 'prob', t: 'Problema ou reclamação', re: /\b(problema|reclama\w*|errad\w*|atras\w*|defeit\w*|n[aã]o chegou|insatisf\w*|devolu\w*|troca\w*|cancel\w*)/i, next: 'Responder com prioridade e registrar a solução.', reply: 'Sinto muito pelo transtorno. Pode me contar o que aconteceu? Vou resolver o quanto antes.' },
    { k: 'preco', t: 'Preço ou orçamento', re: /\b(pre[cç]o|valor(es)?|quanto (custa|fica|sai|é)|or[cç]amento|tabela)\b/i, next: 'Informar os valores ou enviar um orçamento.', reply: 'Posso te passar os valores. Me conta qual item ou serviço você tem em mente?' },
    { k: 'pag', t: 'Forma de pagamento', re: /\b(pix|cart[aã]o|pagar|pagamento|parcel\w*|boleto|cr[eé]dito|d[eé]bito)\b/i, next: 'Explicar as formas de pagamento aceitas.', reply: 'Vou te explicar as formas de pagamento. Qual você prefere usar?' },
    { k: 'ent', t: 'Entrega ou retirada', re: /\b(entrega\w*|frete|retirar|retirada|envio|enviam|endere[cç]o|chega)\b/i, next: 'Confirmar prazo e forma de entrega ou retirada.', reply: 'Sobre a entrega ou retirada: qual você prefere? Me diga seu bairro que eu confirmo o prazo.' },
    { k: 'hor', t: 'Horário ou agendamento', re: /\b(hor[aá]rio\w*|agendar|marcar|agenda|dispon[ií]vel|funciona|abre|fecha)\b/i, next: 'Propor um horário e registrar na Agenda.', reply: 'Vamos combinar um horário? Qual dia e período ficam melhores para você?' },
    { k: 'prod', t: 'Interesse em comprar', re: /\b(quero|gostaria|comprar|encomendar|pedido|reservar|kit|produto)\b/i, next: 'Confirmar o item e registrar a venda.', reply: 'Que bom o seu interesse! Me confirma qual item e a quantidade que eu já separo para você.' },
    { k: 'loc', t: 'Localização', re: /\b(onde fica|atende|cidade|bairro|localiza\w*|perto)\b/i, next: 'Informar o local ou a área de atendimento.', reply: 'Me diz sua cidade ou bairro que eu confirmo se atendemos por aí.' }
  ];
  function thread() {
    return $$('#v .ct .ms .cx4-m').map(function (m) {
      var bb = $('.bb', m), t = bb ? bb.textContent.trim() : '';
      return { o: !!$('.mg.o', m), t: t };
    }).filter(function (m) { return m.t; });
  }
  function analyze(th, name) {
    var inc = th.filter(function (m) { return !m.o; }), out = th.length - inc.length, last = th[th.length - 1];
    var tail = inc.slice(-6), needs = [];
    NEEDS.forEach(function (n) { for (var i = tail.length - 1; i >= 0; i--) { if (n.re.test(tail[i].t)) { needs.push({ n: n, ev: tail[i].t }); break; } } });
    return { total: th.length, inc: inc.length, out: out, lastIn: inc[inc.length - 1], waiting: !!last && !last.o, needs: needs, name: first(name) };
  }
  var cut = function (t, n) { t = String(t).replace(/\s+/g, ' '); return t.length > n ? t.slice(0, n - 1) + '…' : t; };
  function replyFor(a) {
    var n = a.needs[0], hi = a.name ? 'Oi, ' + a.name + '! ' : 'Oi! ';
    return hi + (n ? n.n.reply : 'Obrigado pelo contato. Já vou ver e te respondo por aqui.');
  }
  function useDraft(text) {
    var ta = document.getElementById('ta'); if (!ta) return;
    if (ta.value.trim() && !confirm('Substituir o rascunho atual pelo modelo?')) return;
    ta.value = text; ta.dispatchEvent(new Event('input', { bubbles: true })); ta.focus(); ta.setSelectionRange(text.length, text.length);
  }
  function paintLia() {
    var aside = $('#v aside.cx'), id = curId(); if (!aside || !id) return;
    var th = thread(), c = C.find(function (x) { return x[0] === id; }) || [];
    var a = analyze(th, c[1]);
    var sig = [id, th.length, pendingInt.length, a.waiting, a.needs.map(function (n) { return n.n.k; }).join(',')].join('|');
    var old = $('[data-v79-lia]', aside);
    if (old && old.dataset.sig === sig) return;
    var d = E('details', 'cx4-sec cx79-lia'); d.dataset.v79Lia = '1'; d.dataset.sig = sig; d.open = ls(LIA) !== '0';
    var sm = E('summary'), sp = E('span'); sp.innerHTML = svg('spark', 15); sp.append(document.createTextNode(' Lia · leitura rápida'));
    var dn = E('span'); dn.innerHTML = svg('down', 16); sm.append(sp, dn); d.append(sm);
    var b = E('div', 'cx4-sb');
    if (!a.inc) b.append(E('p', 'm sm', 'Ainda não há mensagens do cliente para ler.'));
    else {
      b.append(E('p', 'cx79-sum', (a.name || 'O cliente') + ' enviou ' + a.inc + (a.inc === 1 ? ' mensagem' : ' mensagens') + (a.out ? ' e você respondeu ' + a.out + (a.out === 1 ? ' vez.' : ' vezes.') : '. Ainda não há resposta registrada.')));
      if (a.needs.length) {
        var ul = E('ul', 'cx79-nd');
        a.needs.slice(0, 3).forEach(function (x) { var li = E('li'); li.append(E('b', '', x.n.t), E('span', 'm sm', '“' + cut(x.ev, 80) + '”')); ul.append(li); });
        b.append(E('p', 'cx79-lb', 'O que a pessoa parece querer'), ul);
      } else b.append(E('p', 'm sm', 'Nenhum assunto comercial claro nas últimas mensagens.'));
      b.append(E('p', 'cx79-lb', 'Próximo passo'), E('p', '', a.waiting ? (a.needs[0] ? a.needs[0].n.next : 'Responder à última mensagem.') : 'Aguardar o retorno do cliente.'));
      if (a.waiting) {
        var q = E('blockquote', 'cx79-rp', replyFor(a));
        var u = E('button', 'btn o sm2 w', 'Usar como rascunho'); u.type = 'button'; u.addEventListener('click', function () { useDraft(replyFor(a)); });
        b.append(E('p', 'cx79-lb', 'Modelo de resposta'), q, u);
      }
    }
    if (pendingInt.length) b.append(E('p', 'm sm cx79-note', 'Depende de integração no servidor, ainda não conectada: ' + pendingInt.join(' e ') + '.'));
    b.append(E('p', 'm sm cx79-note', 'Leitura automática por regras, só com as mensagens desta conversa. Não usa IA generativa e nada é enviado.'));
    d.append(b);
    d.addEventListener('toggle', function () { ls(LIA, d.open ? '1' : '0'); });
    if (old) old.replaceWith(d); else { var f = $('details.cx4-sec', aside), v70 = $('.v70-ctx', aside); if (v70) v70.after(d); else if (f) f.parentNode.insertBefore(d, f); else aside.append(d); }
    paintQuick(a);
  }
  function paintQuick(a) {
    var cp = $('#v .ct .cp'); if (!cp) return;
    var old = $('.cx79-qa', cp.parentNode); if (old) old.remove();
    var ta = document.getElementById('ta');
    if (!a.waiting || !a.inc || (ta && ta.value.trim())) return;
    var t = replyFor(a), bar = E('div', 'cx79-qa'), ic = E('span', 'cx79-qi'); ic.innerHTML = svg('spark', 14);
    var tx = E('span', 'cx79-qt', cut(t, 110)), bt = E('button', 'cx79-qb', 'Usar'); bt.type = 'button'; bt.setAttribute('aria-label', 'Usar modelo de resposta da Lia no rascunho'); bt.addEventListener('click', function () { useDraft(t); bar.remove(); });
    var dm = E('button', 'cx79-qx'); dm.type = 'button'; dm.setAttribute('aria-label', 'Dispensar modelo'); dm.innerHTML = svg('x', 14); dm.addEventListener('click', function () { bar.remove(); });
    bar.append(ic, tx, bt, dm); cp.parentNode.insertBefore(bar, cp);
  }

  async function openQuickReplies() {
    if (!remote || !canEditInbox()) return;
    const dialog = dlg();
    const conversation = curId();
    const identity = host.identity;
    const workspace = window.SocialMEIAuth?.current?.negocio.id;
    if (dialog.open || !identity || !conversation || !workspace) return;
    const manage = ['owner', 'admin'].includes(window.SocialMEIAuth.current.papel);
    const form = E('form'), title = E('h2', '', 'Respostas rápidas do negócio');
    title.id = 'v79-quick-replies-title';
    form.method = 'dialog';
    form.setAttribute('aria-labelledby', title.id);
    const status = E('p', 'm', 'Consultando as respostas…');
    status.setAttribute('role', 'status');
    const list = E('ul'), close = E('button', 'btn o', 'Fechar');
    const add = E('button', 'btn o', 'Adicionar');
    const input = E('input', 'in');
    input.type = 'text';
    input.maxLength = 160;
    input.setAttribute('aria-label', 'Nova resposta personalizada');
    add.type = 'button';
    input.disabled = add.disabled = true;
    form.append(title, status, list);
    if (manage) form.append(input, add);
    form.append(close);
    dialog.replaceChildren(form);
    dialog.showModal();
    const isCurrent = () => identity === host.identity && conversation === curId();
    const live = () => dialog.open && form.isConnected && isCurrent();
    let snapshot;
    let saving = false;
    function draw() {
      list.replaceChildren();
      status.textContent = snapshot.items.length ? '' : 'Nenhuma resposta rápida cadastrada.';
      input.disabled = add.disabled = saving || snapshot.items.length >= 20;
      snapshot.items.forEach((text, index) => {
        const item = E('li'), use = E('button', 'btn o sm2', text);
        use.type = 'button';
        use.onclick = () => {
          if (!live()) return;
          const draft = $('#v #ta');
          if (!draft) return;
          draft.value += (draft.value.trim() ? ' ' : '') + text;
          draft.dispatchEvent(new Event('input', {bubbles: true}));
          dialog.close();
          draft.focus();
        };
        item.append(use);
        if (manage) {
          const remove = E('button', 'btn o sm2', 'Remover');
          remove.type = 'button';
          remove.disabled = saving;
          remove.setAttribute('aria-label', 'Remover resposta ' + (index + 1));
          remove.onclick = () => save(snapshot.items.filter((_, offset) => offset !== index));
          item.append(remove);
        }
        list.append(item);
      });
    }
    function accept(result) {
      if (result.workspace_id !== workspace || !Number.isSafeInteger(result.revision) ||
          !Array.isArray(result.items) || !result.items.every(text => typeof text === 'string'))
        throw Error('Respostas indisponíveis para esta sessão.');
      snapshot = result;
    }
    async function save(items) {
      if (!live() || !manage || saving) return;
      saving = true;
      draw();
      try {
        const result = await host.request('/message-enrichment/quick-replies', 'PUT',
          {revision: snapshot.revision, items});
        if (!live()) return;
        accept(result);
        input.value = '';
        saving = false;
        draw();
        status.textContent = 'Respostas atualizadas.';
        if (!input.disabled) input.focus();
      } catch (error) {
        if (!live()) return;
        saving = false;
        draw();
        status.textContent = error.message || 'Não foi possível salvar as respostas.';
      }
    }
    form.onsubmit = event => { event.preventDefault(); if (event.submitter === close) dialog.close(); };
    add.onclick = () => { if (input.value.trim()) save([...snapshot.items, input.value.trim()]); };
    try {
      const result = await host.request('/message-enrichment/quick-replies');
      if (!live()) return;
      accept(result);
      draw();
    } catch (error) {
      if (live()) status.textContent = error.message || 'Não foi possível consultar as respostas.';
    }
  }
  document.addEventListener('click', event => {
    if (event.target.closest?.('[data-v79-replies]')) openQuickReplies();
  });

  /* ---------- 7. mídia: só com adaptador registrado ---------- */
  function paintMedia() {
    var M = window.SocialMEIMedia, id = curId(); if (!M || !M.active || !remote || !id) return;
    var row = host.conversation && host.conversation(id); if (!row) return;
    $$('#v .ct .ms .cx4-m[data-mid]').forEach(function (m) {
      if (m.dataset.v79m) return; m.dataset.v79m = '1';
      var msg = (row.messages || []).filter(function (x) { return String(x.id) === m.dataset.mid; })[0]; if (!msg) return;
      var ds = M.describe(msg, row); if (!ds.length) return;
      var w = E('div', 'v79-media' + (m.querySelector('.mg.o') ? ' o' : ''));
      ds.forEach(function (d) { w.append(M.mount(d)); });
      var mg = $('.mg', m); if (mg) mg.after(w);
    });
  }

  /* ---------- ciclo ---------- */
  var pendingInt = [];
  /* Painéis de integrações ainda não conectadas ocupam a tela: ficam ocultos e viram uma nota no painel da Lia. */
  function foldOff() {
    pendingInt = [];
    $$('#v .ct>[data-assist-suggestions],#v .ct>[data-assist-draft]').forEach(function (n) {
      var off = /não conectado|indispon/i.test(n.textContent);
      n.classList.toggle('v79-off', off);
      if (off) pendingInt.push(n.hasAttribute('data-assist-draft') ? 'rascunhos por IA' : 'sugestão de cliente do CRM');
    });
  }
  function post() {
    if (!/^#\/caixa/.test(location.hash)) return;
    foldOff();
    saveFilters(); paintSearch(); paintJump(); watchCrm(); paintCrm(); paintLia(); paintMode(); paintMedia();
  }
  var rr = window.render;
  window.render = function () { var r = rr.apply(this, arguments); queueMicrotask(post); return r; };
  window.addEventListener('hashchange', function () { queueMicrotask(post); });
  window.addEventListener('online', function () { if (host && host.reloadInbox) host.reloadInbox(); });
  document.documentElement.classList.add('v79');
  window.SocialMEI79 = { refresh: post, analyze: analyze };
  if (/^#\/caixa/.test(location.hash)) { render(); }
})();
