/* SocialMEI-IA · v7.4 · Automações em linguagem simples.
   Só interface. NÃO existe motor de execução nem API de automações: nenhuma rotina roda de verdade.
   O que é real aqui: a escolha "ligada/pausada", as rotinas criadas e as edições ficam guardadas NESTE NAVEGADOR
   (por negócio) e só são confirmadas depois de gravadas e relidas. Execução e histórico real: indisponíveis. */
(() => {
  "use strict";
  /* o código principal do app roda depois deste arquivo ser lido: esperar o documento terminar de carregar */
  const start = () => {
  if (typeof automacoes !== "function" || typeof RT === "undefined" || typeof S === "undefined" || typeof A === "undefined") return;
  const BASE_N = 4;
  const BASE = JSON.parse(JSON.stringify(RT.slice(0, BASE_N)));
  const DEFAULT_ON = [1, 1, 0, 0];
  const KEY = "smei-automacoes-v74:";
  const NEEDS = { 1: "canal" }; /* "Conversa sem resposta" depende de WhatsApp ou Instagram */
  const PURPOSE = { Financeiro: "Receber em dia", Atendimento: "Não deixar ninguém esperando", Vendas: "Vender mais", Clientes: "Manter clientes por perto" };
  const remote = () => !!window.SocialMEIV22?.remote;
  const ident = () => window.SocialMEIV22?.identity;
  const scopeKey = () => (remote() && ident() ? `${ident().usuario.id}:${ident().negocio.id}` : "demo");
  const canEdit = () => !remote() || ["owner", "admin"].includes(ident()?.papel);
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const hhmm = (t) => new Date(t).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const str = (v, n = 240) => (typeof v === "string" ? v.slice(0, n) : "");
  const color = (v, d) => (/^#[0-9a-f]{3,8}$/i.test(v || "") ? v : d);
  const lower = (t) => (t ? t.charAt(0).toLowerCase() + t.slice(1) : t);

  /* ---------- guardar e reler (confirmação de verdade) ---------- */
  const customOf = () => RT.slice(BASE_N).map(clone);
  const editsOf = () => {
    const out = {};
    for (let k = 0; k < Math.min(BASE_N, RT.length); k++) if (RT[k][0] !== BASE[k][0] || RT[k][2] !== BASE[k][2] || RT[k][6] !== BASE[k][6]) out[k] = [RT[k][0], RT[k][2], RT[k][6]];
    return out;
  };
  const sig = () => JSON.stringify([customOf(), editsOf()]);
  function persist() {
    const k = KEY + S.rtScope;
    try {
      const text = JSON.stringify({ v: 1, on: RT.map((_, i) => (S.on[i] ? 1 : 0)), custom: customOf(), edits: editsOf(), at: S.rtAt || {} });
      localStorage.setItem(k, text);
      if (localStorage.getItem(k) !== text) throw Error("O navegador não confirmou a gravação.");
      S.rtSig = sig();
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e?.message || "Armazenamento do navegador indisponível." };
    }
  }
  function load() {
    const sc = scopeKey();
    S.rtScope = sc; S.rtAt = {}; S.rtErr = {}; S.autoMsg = null; S.test = false; S.hist = []; S.au74q = ""; S.rf = "Todas";
    RT.length = 0;
    BASE.forEach((r) => RT.push(clone(r)));
    S.on = DEFAULT_ON.slice();
    S.rot = 0;
    let raw = null;
    try { raw = localStorage.getItem(KEY + sc); } catch (_) { S.autoMsg = { k: "err", t: "Este navegador não deixa guardar as rotinas. Você vê os modelos, mas nada será lembrado." }; }
    if (raw) {
      try {
        const p = JSON.parse(raw);
        if (!p || p.v !== 1) throw Error("formato");
        for (const [k, e] of Object.entries(p.edits || {})) if (RT[+k] && Array.isArray(e)) { RT[+k][0] = str(e[0], 80) || RT[+k][0]; RT[+k][2] = str(e[1]) || RT[+k][2]; RT[+k][6] = str(e[2], 400) || RT[+k][6]; RT[+k][7][0] = RT[+k][2]; }
        for (const c of Array.isArray(p.custom) ? p.custom.slice(0, 40) : []) {
          if (!Array.isArray(c) || !Array.isArray(c[7]) || c.length < 9) continue;
          RT.push([str(c[0], 80), str(c[1], 40), str(c[2]), "bolt", color(c[4], "#e8f0ff"), color(c[5], "#0a5cf5"), str(c[6], 400), c[7].slice(0, 3).map((x) => str(x)), str(c[8], 400)]);
        }
        S.on = RT.map((_, k) => (p.on && k in p.on ? (p.on[k] ? 1 : 0) : DEFAULT_ON[k] || 0));
        S.rtAt = p.at && typeof p.at === "object" ? p.at : {};
      } catch (_) {
        S.autoMsg = { k: "err", t: "Não consegui ler as rotinas guardadas neste navegador. Mostrando os modelos originais; ao salvar de novo elas serão substituídas." };
      }
    }
    S.rtSig = sig();
  }
  /* rotinas criadas/editadas pelos formulários antigos passam a ser guardadas e relidas */
  function sync() {
    if (S.rtScope !== scopeKey()) load();
    while (S.on.length < RT.length) S.on.push(0);
    if (S.rtSig !== sig()) {
      const r = persist();
      if (!r.ok) S.autoMsg = { k: "err", t: "A rotina aparece nesta tela, mas não foi guardada (" + r.error + "). Ela pode se perder ao recarregar." };
    }
  }

  /* ---------- estados ---------- */
  /* Dois níveis, sempre separados: CONFIGURAÇÃO (real, guardada neste navegador) e EXECUÇÃO (indisponível: não há motor). */
  const cfgOn = () => `<span class="st2 au74-cfg"><i></i>Ligada</span>`;
  const exNo = (t) => `<span class="au74-ex" title="Nenhuma rotina roda de verdade: o motor de automações não está conectado.">${t || "Não executa"}</span>`;
  function channelRule(k) { return NEEDS[k] === "canal"; }
  function stateOf(k) {
    if (S.rtErr[k]) return { id: "error", chip: dt("r", "Com erro"), line: S.rtErr[k], hint: S.rtErr[k] };
    if (channelRule(k) && !remote()) return { id: "unavailable", chip: dt("g", "Indisponível"), line: "Precisa de WhatsApp ou Instagram conectado. Nesta demonstração nenhum canal está conectado.", hint: "nenhum canal (WhatsApp ou Instagram) está conectado nesta demonstração." };
    if (S.on[k]) return { id: "on", chip: cfgOn(), line: "Ligada só na configuração. Não executa: o motor de automações não está conectado.", hint: "" };
    return { id: "off", chip: dt("y", "Pausada"), line: "Pausada. Ao ligar, só a configuração fica pronta; nada passa a rodar.", hint: "" };
  }
  const msg = (k, t) => { S.autoMsg = { k, t }; };
  function toggle(k) {
    S.rot = k; S.test = false;
    const r = RT[k]; if (!r) return;
    if (!canEdit()) return msg("err", "Seu perfil só permite consultar as automações. Peça a um responsável pelo negócio.");
    const st = stateOf(k);
    if (st.id === "unavailable") return msg("warn", `“${r[0]}” está indisponível: ${st.hint}`);
    const prev = S.on[k] ? 1 : 0, next = prev ? 0 : 1;
    S.on[k] = next; S.rtAt[k] = Date.now();
    const res = persist();
    if (!res.ok) {
      S.on[k] = prev; delete S.rtAt[k]; S.rtErr[k] = "Não foi possível guardar a mudança (" + res.error + ").";
      return msg("err", `Nada foi alterado em “${r[0]}”: ${S.rtErr[k]}`);
    }
    delete S.rtErr[k];
    msg("info", next ? `“${r[0]}” foi ligada na configuração (guardada neste navegador às ${hhmm(S.rtAt[k])}). Isso não inicia nenhuma execução: o motor de automações não está conectado.` : `“${r[0]}” foi pausada na configuração (guardada neste navegador às ${hhmm(S.rtAt[k])}).`);
  }

  /* ---------- tela ---------- */
  const flowIcon = ["cal", "doc", "check"], flowName = ["Quando", "O SocialMEI prepara", "Você confere"];
  const sentence = (r) => `Quando ${lower(r[7][0])}, o SocialMEI prepara “${r[7][1]}”. Antes de usar, você confere: ${lower(r[7][2])}.`;
  function card(k, sel) {
    const r = RT[k], st = stateOf(k), id = "au74-s" + k, na = st.id === "unavailable" || !canEdit();
    return `<article class="rt au74c ${k === S.rot ? "on" : ""}" data-st="${st.id}"><span class="ico" style="background:${r[4]};color:${r[5]}" aria-hidden="true">${i(r[3], 22)}</span>
<button type="button" class="au74-sel" data-a="rot:${k}" aria-current="${k === S.rot}"><b>${esc(r[0])}</b><span class="m sm">${esc(r[2])}</span><span class="au74-line sm" id="${id}">${esc(st.line)}</span></button>
<span class="au74-chip">${st.chip}${st.id === "unavailable" ? "" : exNo()}</span>
<button type="button" class="tg ${S.on[k] && st.id !== "unavailable" ? "on" : ""}" role="switch" aria-checked="${!!S.on[k] && st.id !== "unavailable"}" aria-disabled="${na}" aria-describedby="${id}" data-a="tg:${k}" aria-label="${esc(r[0])}"></button></article>`;
  }
  function detail(k0) {
    const r = RT[k0], st = stateOf(k0), name = esc(r[0]), at = S.rtAt[k0];
    const flow = r[7].map((s, n) => `<li><span class="cap" ${n === 2 ? 'style="color:#b07800"' : ""}>${n + 1} · ${flowName[n]}</span>${i(flowIcon[n], 24)}<b class="sm">${esc(s)}</b></li>`).join("");
    const hist = S.hist.length ? S.hist.map((h) => `<p class="sm" style="margin-top:8px"><b>${h[0]}</b> · ${esc(h[1])}<br><span class="m">${esc(h[2])}</span></p>`).join("") : '<p class="m sm" style="margin-top:8px">Nenhum teste realizado.</p>';
    const ops = [["Execução automática das rotinas", "Faz a rotina rodar sozinha quando o gatilho acontecer."], ["Registro de execuções", "Mostra quando a rotina rodou e o resultado."], ["Canais autorizados", "Define por quais canais a rotina pode avisar."]]
      .map((o) => `<li><span><b class="sm">${o[0]}</b><br><span class="m sm">${o[1]}</span></span><span class="au74-na">Aguardando API</span><button class="btn o" disabled title="Interface pronta; falta a API correspondente.">Indisponível</button></li>`).join("");
    return `<div class="card au74d" style="padding:20px"><div class="cap">Rotina selecionada</div>
<div class="row sp wr" style="margin:6px 0"><div class="row wr"><h2 style="font-size:24px">${name}</h2>${st.chip}${st.id === "unavailable" ? "" : exNo()}</div><button class="btn o" data-a="edit:rot" ${canEdit() ? "" : "disabled"}>${i("pen")}Editar</button></div>
<p class="m">${esc(r[6])}</p>
<div class="au74-say" aria-label="Resumo em linguagem simples"><span class="cap">Em linguagem simples</span><p>${esc(sentence(r))}</p></div>
<h3 class="au74-h">Como funciona</h3><ol class="au74-flow">${flow}</ol>
<h3 class="au74-h">Situação</h3>
<dl class="au74-dl"><dt>Configuração</dt><dd>${st.chip}${st.id === "unavailable" ? `<br><span class="m sm">${esc(st.hint)}</span>` : ""}${st.id === "error" ? `<br><span class="m sm">${esc(st.hint)} <button class="lk" data-a="tg:${k0}">Tentar de novo</button></span>` : ""}</dd>
<dt>Execução</dt><dd>${exNo("Indisponível")}<br><span class="m sm">O motor de automações não está conectado: esta rotina não roda sozinha e não há registro de execuções. Ligar só deixa a configuração pronta.</span></dd>
<dt>Última alteração</dt><dd>${at ? "Guardada neste navegador às " + hhmm(at) : "Sem alterações guardadas"}</dd></dl>
<div class="row sp wr" style="margin-top:18px;border-top:1px solid var(--b);padding-top:16px"><div><h3 class="au74-h" style="margin:0">Teste com um exemplo</h3><div class="m sm">Confira o texto antes de usar. Nada será enviado.</div></div><button class="btn" data-a="testar">${i("play", 16)}Testar rotina</button></div>
<div class="card" style="background:var(--s);padding:20px;text-align:center;margin-top:12px" aria-live="polite">${S.test ? `<div class="cap" style="margin-bottom:10px">Resultado do teste</div><div class="phone" style="max-width:340px;margin:0 auto;text-align:left"><div class="phh">${ch("wa")}WhatsApp · simulação</div><div class="phb sim" style="min-height:96px"><span class="typing"><i></i><i></i><i></i></span><div class="bb">${esc(r[8])}</div></div></div><p class="m sm" style="margin-top:10px">Nada foi enviado.</p>` : '<span style="color:var(--p)">' + i("doc", 26) + '</span><br><b>Seu resultado aparece aqui.</b><div class="m sm">Nenhum teste realizado.</div>'}</div>
<h3 class="au74-h">Histórico de execuções</h3><p class="au74-nohist sm"><b>Indisponível.</b> O servidor ainda não informa execuções reais, por isso nada é listado aqui. Os testes abaixo são simulações feitas neste navegador.</p>
<details class="dt" style="margin-top:10px"><summary>Histórico de testes (${S.hist.length})</summary>${hist}</details>
<details class="dt au74-adv" style="margin-top:10px"><summary>Configurações avançadas</summary><p class="sm m" style="margin-top:8px">Área: ${esc(r[1])}<br>Origem: ${k0 < BASE_N ? "modelo do SocialMEI" : "criada por você"}<br>Onde fica guardada: só neste navegador${remote() ? ", neste negócio" : ""}<br>Execução automática: não conectada</p><p class="cap" style="margin-top:12px">Ainda dependem de API</p><ul class="au74-ops">${ops}</ul></details></div>`;
  }
  function view() {
    sync();
    const q = (S.au74q || "").trim().toLowerCase();
    const all = RT.map((x, k) => [x, k]);
    const sts = all.map(([, k]) => stateOf(k).id);
    const n = { on: sts.filter((s) => s === "on").length, off: sts.filter((s) => s === "off").length, un: sts.filter((s) => s === "unavailable").length, er: sts.filter((s) => s === "error").length };
    const F = { Todas: () => 1, Ligadas: (s) => s === "on", Pausadas: (s) => s === "off", Indisponíveis: (s) => s === "unavailable" || s === "error" };
    if (!F[S.rf]) S.rf = "Todas";
    const rows = all.filter(([x, k]) => F[S.rf](stateOf(k).id) && (!q || (x[0] + " " + x[2] + " " + x[6]).toLowerCase().includes(q)));
    const groups = [...new Set(rows.map(([x]) => x[1]))];
    const k0 = RT[S.rot] ? S.rot : 0;
    const tabs = [["Todas", all.length], ["Ligadas", n.on], ["Pausadas", n.off], ["Indisponíveis", n.un + n.er]];
    const m = S.autoMsg;
    return `<div class="pg au74"><div class="row sp wr"><div><div class="row wr"><h1>Automações</h1><span class="pill" style="background:var(--yl);border-color:#f1dba0"><span class="dot y" style="margin:0"></span>Configuração disponível · execução indisponível</span></div><p class="m" style="margin-top:6px">Prepare as rotinas do que se repete, explicadas em linguagem simples. Hoje você configura; ainda não executa.</p></div><button class="btn" data-a="novo:rotina" ${canEdit() ? "" : "disabled"}>${i("plus")}Nova rotina</button></div>
<p class="au74-live ${m ? "au74-" + m.k : ""}" role="status" aria-live="polite">${m ? esc(m.t) : ""}</p>
<div class="au74-real" role="note" aria-label="O que funciona hoje"><div class="au74-lv" data-k="ok"><span class="au74-lh">${i("check", 16)}Configuração<em>Disponível</em></span><span>Ligar, pausar, editar e criar rotinas. Fica guardado só neste navegador${remote() ? ", neste negócio" : ""}.</span></div><div class="au74-lv" data-k="off"><span class="au74-lh">${i("info", 16)}Execução<em>Indisponível</em></span><span>Nenhuma rotina roda de verdade: o motor de automações não está conectado. Nada é enviado, lembrado nem registrado.</span></div></div>
${canEdit() ? "" : '<p class="au74-ro sm">Seu acesso é só de leitura: você pode consultar as automações, mas não alterá-las.</p>'}
<div class="kp au wr" style="margin:14px 0">${[["Ligadas", n.on], ["Pausadas", n.off], ["Indisponíveis", n.un], ["Com erro", n.er]].map((c) => `<div><span class="m">${c[0]}</span><b>${c[1]}</b></div>`).join("")}<div title="O servidor ainda não informa execuções reais"><span class="m">Execuções reais</span><b>—</b></div></div>
<div class="g2 au74-grid" style="--c:minmax(0,1.1fr) minmax(0,1fr)"><div class="card" style="padding:18px"><h2 style="font-size:26px">Sua biblioteca</h2>
<div class="row wr" style="margin:14px 0"><label class="in m" style="flex:1;min-width:0">${i("search")}<input id="au74q" value="${esc(S.au74q || "")}" placeholder="Buscar rotina" aria-label="Buscar rotina" style="flex:1;min-width:0;border:0;outline:0;background:transparent;font:inherit;color:var(--t)"></label></div>
<div class="tabs" style="gap:18px;margin-bottom:6px" role="group" aria-label="Filtrar por situação">${tabs.map((t) => `<button class="${S.rf === t[0] ? "on" : ""}" data-a="rf:${t[0]}" aria-pressed="${S.rf === t[0]}">${t[0]} <span class="n">${t[1]}</span></button>`).join("")}</div>
${groups.map((g) => `<section class="au74-g" aria-label="${esc(PURPOSE[g] || g)}"><h3 class="au74-gh">${esc(PURPOSE[g] || g)}</h3>${rows.filter(([x]) => x[1] === g).map(([, k]) => card(k)).join("")}</section>`).join("")}
${rows.length ? "" : `<div class="empty" style="display:block;padding:24px 0;text-align:center"><b style="display:block;color:var(--t);margin-bottom:4px">Nenhuma rotina nesta visão</b>${q || S.rf !== "Todas" ? '<button class="btn o" data-a="rf:Todas" style="margin-top:10px">Ver todas</button>' : ""}</div>`}
<button class="card row sp" data-a="novo:rotina" ${canEdit() ? "" : "disabled"} style="padding:16px;margin-top:14px;width:100%;text-align:left;cursor:pointer"><div class="row">${i("bulb", 26)}<div><b>Criar uma nova rotina</b><div class="m sm">Novas rotinas começam pausadas.</div></div></div>${i("right")}</button></div>
${detail(k0)}</div></div>`;
  }

  automacoes = view; /* a rota "automacoes" do app lê esta função a cada desenho */
  Object.assign(A, {
    tg: (v) => { toggle(+v); },
    rot: (v) => { S.rot = +v; S.test = false; },
    rf: (v) => { S.rf = v; },
  });
  document.addEventListener("input", (e) => {
    if (e.target?.id !== "au74q") return;
    S.au74q = e.target.value;
    const pos = e.target.selectionStart;
    render();
    const n = document.getElementById("au74q");
    if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (_) {} }
  });
  window.SocialMEIAutomations = { stateOf, sentence, KEY, scopeKey };
  if (/^#\/automacoes/.test(location.hash)) render();
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
