/* SocialMEI-IA · v7.7 · Lia — assistente global.
   Dois modos, decididos pela página:
     • público (entrada.html): responde SOMENTE com o conteúdo público já escrito na própria página. Não lê nenhum dado do app.
     • aplicativo (socialmei-app.html): navega, orienta, abre formulários existentes e lê dados JÁ carregados na tela.
   Regras (v7.7):
     - Frontend apenas. Sem endpoints novos, sem chave de API, sem rede própria. IA generativa só via lia-adapter.js (desativada).
     - A Lia não grava, não envia, não cobra e não publica. Ela abre telas/formulários existentes; quem salva é o formulário.
     - Preenchimento assistido só preenche campos do formulário aberto; nada é salvo até a pessoa confirmar nele.
     - Contexto e conversa ficam só em memória e são descartados ao trocar de negócio/usuário ou sair.
     - Cada ação é verificada antes de ser confirmada em texto ("Abri…" só aparece se a tela realmente mudou). */
(() => {
  "use strict";
  if (window.SocialMEILia) return;
  const KB = window.SocialMEILiaKB;
  const Adapter = window.SocialMEILiaAdapter;
  const isPublicPage = !!document.getElementById("v-site");
  const isAppPage = !!document.getElementById("app") && !isPublicPage;
  if (!KB || (!isPublicPage && !isAppPage)) return;
  const MODE = isPublicPage ? "public" : "app";
  const VERSION = "7.7";

  /* ───────── utilidades ───────── */
  const safe = (fn, d) => { try { const v = fn(); return v === undefined ? d : v; } catch (_) { return d; } };
  const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9@.$,]+/g, " ").replace(/(?<![0-9])[.,$]+|[.,$]+(?![0-9])/g, " ").replace(/\s+/g, " ").trim();
  const STOP = new Set("a o as os de do da dos das em no na nos nas um uma uns umas para pra por com sem meu minha meus minhas me eu voce quero queria gostaria preciso poderia pode favor por favor que qual quais e ou ao aos se ja la isso essa esse esta este tem ter mais muito pouco tambem so aqui ali onde como".split(" "));
  const tokens = (s) => norm(s).split(" ").filter(Boolean);
  const content = (s) => tokens(s).filter((t) => !STOP.has(t));
  function lev(a, b, max) {
    if (Math.abs(a.length - b.length) > max) return max + 1;
    let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      const cur = [i];
      let min = i;
      for (let j = 1; j <= b.length; j++) {
        cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        if (cur[j] < min) min = cur[j];
      }
      if (min > max) return max + 1;
      prev = cur;
    }
    return prev[b.length];
  }
  const sameWord = (a, b) => {
    if (a === b) return 1;
    const m = Math.min(a.length, b.length);
    if (m < 5) return 0;
    let p = 0;
    while (p < m && a[p] === b[p]) p++;
    if (p >= Math.max(5, m - 2)) return 0.85;
    return lev(a, b, m >= 8 ? 2 : 1) <= (m >= 8 ? 2 : 1) ? 0.7 : 0;
  };
  const brlFmt = (n) => safe(() => (typeof brl === "function" ? brl(n) : null), null) || "R$ " + Number(n || 0).toFixed(2).replace(".", ",");
  const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
  const first = (s) => String(s || "").trim().split(/\s+/)[0] || "";
  const titleCase = (s) => s.replace(/\p{L}[\p{L}'’-]*/gu, (w) => (/^(d[aeo]s?|e)$/i.test(w) ? w.toLowerCase() : w[0].toUpperCase() + w.slice(1).toLowerCase()));
  const reduced = () => document.documentElement.classList.contains("calm") || safe(() => matchMedia("(prefers-reduced-motion: reduce)").matches, false);
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  async function waitFor(fn, timeout = 1500, step = 40) {
    const t0 = Date.now();
    for (;;) {
      const v = safe(fn, null);
      if (v) return v;
      if (Date.now() - t0 > timeout) return null;
      await wait(step);
    }
  }
  const visible = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";

  /* ───────── ambiente (app) ───────── */
  const auth = () => window.SocialMEIAuth;
  const remote = () => !!auth()?.remote;
  const identity = () => auth()?.current || null;
  const role = () => identity()?.papel || "";
  const signedIn = () => (MODE === "public" ? false : remote() ? !!identity() : true);
  const canWrite = () => !remote() || ["owner", "admin", "member"].includes(role());
  const isManager = () => !remote() || ["owner", "admin"].includes(role());
  const scopeKey = () => (MODE === "public" ? "public" : remote() ? (identity() ? `${identity().usuario.id}:${identity().negocio.id}` : "") : "demo");
  /* v7.8 · contexto de operação: toda ação assíncrona captura (época, escopo) e descarta o resultado se mudou empresa/usuário/sessão. */
  let epoch = 0, liveCtl = null;
  const ctxNow = () => ({ ep: epoch, sk: scopeKey() });
  const stale = (c) => !c || c.ep !== epoch || scopeKey() !== c.sk;
  const bizName = () => safe(() => (remote() ? identity()?.negocio?.nome : S.biz.nome), "") || "";
  const dataOrigin = () => (remote() ? "Dados do seu negócio, lidos da tela agora" : "Dados de exemplo desta demonstração");
  const appReady = () => MODE === "app" && typeof window.render === "function" && typeof S === "object" && document.querySelector("#app .top");
  const routeInfo = () => {
    const raw = location.hash.replace(/^#\/?/, "").split("?")[0].split("/");
    const r = raw[0] || "inicio";
    const key = r === "negocio" || r === "config" ? `${r}/${raw[1] || (r === "negocio" ? "resumo" : "negocio")}` : r;
    const entry = KB.screens.find((s) => s.path === "/" + key) || KB.screens.find((s) => s.path === "/" + r);
    const title = entry ? entry.title : safe(() => TT[r], "") || "esta tela";
    return { r, key, entry, title, inConversation: r === "caixa" && !!raw[1] };
  };

  /* ───────── catálogo efetivo (respeita permissões) ───────── */
  const FORM_SCREEN = { venda: "vendas", cliente: "clientes", produto: "produtos", lanc: "financeiro", conversa: "caixa", rotina: "automacoes" };
  const SPECIALS = [
    { id: "q-dia", kind: "special", title: "Organizar meu dia", hint: "Prioridades do Meu dia", kw: ["organizar meu dia", "organizar o dia", "meu dia", "o que fazer hoje", "prioridades", "por onde comeco", "plano do dia", "pendencias de hoje", "o que tenho para fazer", "o que fazer agora", "organizar minhas tarefas"] },
    { id: "q-pendentes", kind: "special", title: "Mostrar vendas pendentes", hint: "Abre Vendas só com pendentes", kw: ["vendas pendentes", "mostrar pendentes", "mostre pendentes", "vendas nao pagas", "vendas em aberto", "pagamentos pendentes", "minhas vendas pendentes", "pendentes"] },
    { id: "q-receber", kind: "special", title: "Quanto tenho a receber?", hint: "Soma das vendas pendentes", kw: ["quanto tenho a receber", "a receber", "valores pendentes", "quanto falta receber", "total pendente", "dinheiro pendente"] },
    { id: "q-devendo", kind: "special", title: "Quem está me devendo?", hint: "Clientes com pagamento pendente", kw: ["quem esta devendo", "quem me deve", "quem deve", "clientes devendo", "inadimplentes", "quem esta me devendo", "clientes com pendencia", "atrasados"] },
    { id: "q-conversas", kind: "special", title: "Conversas esperando resposta", hint: "Quantas e quais", kw: ["conversas esperando", "conversas sem resposta", "mensagens nao respondidas", "quantas conversas", "nao respondidas", "quem esta esperando resposta", "mensagens pendentes", "conversas pendentes"] },
    { id: "q-estoque", kind: "special", title: "Produtos com estoque baixo", hint: "O que repor", kw: ["estoque baixo", "produtos acabando", "falta de estoque", "repor estoque", "o que repor", "sem estoque", "produtos com estoque baixo", "acabando"] },
    { id: "q-agenda", kind: "special", title: "Agenda de hoje", hint: "Compromissos abertos de hoje", kw: ["agenda de hoje", "o que tenho hoje", "compromissos de hoje", "agenda hoje", "o que tem na agenda", "meus compromissos"] },
    { id: "q-contas", kind: "special", title: "Contas em atraso", hint: "Pagamentos e recebimentos vencidos", kw: ["contas em atraso", "contas vencidas", "pagamentos em atraso", "recebimentos vencidos"] },
    { id: "q-caixa", kind: "special", title: "Resumo do fluxo de caixa", hint: "Movimentações registradas", kw: ["fluxo de caixa", "resumo financeiro", "entradas e saidas", "saldo registrado"] },
    { id: "q-oportunidades", kind: "special", title: "Oportunidades para acompanhar", hint: "Retornos vencidos ou marcados para hoje", kw: ["oportunidades para acompanhar", "oportunidades atrasadas", "negociacoes com retorno", "retornos comerciais"] },
    { id: "s-aqui", kind: "special", title: "Ajuda desta tela", hint: "O que dá para fazer aqui", kw: ["ajuda desta tela", "o que posso fazer aqui", "ajuda aqui", "como usar esta tela", "o que essa tela faz", "explicar esta tela", "para que serve esta tela"] },
    { id: "s-lia", kind: "special", title: "O que a Lia faz?", hint: "Minhas capacidades e limites", kw: ["o que a lia faz", "o que voce faz", "quem e voce", "o que voce pode fazer", "como voce pode ajudar", "lia", "suas funcoes", "seus comandos", "o que sabe fazer"] },
  ];
  function appIndex() {
    const out = [];
    for (const s of KB.screens) if (!s.manager || isManager()) out.push({ ...s, kind: "screen" });
    if (canWrite()) for (const f of KB.forms) out.push({ ...f, kind: "form" });
    for (const g of Object.values(KB.guides)) out.push({ ...g, kind: "guide" });
    for (const q of SPECIALS) out.push(q);
    return out;
  }

  /* ───────── intenção e busca ───────── */
  const RX = {
    create: /\b(cadastr\w*|cri(ar|e|a)|nov[oa]|registr\w*|adicion\w*|lanc\w*|incluir|inclua|anotar|anota|quero fazer)\b/,
    open: /\b(abr\w*|ir|va|vai|leve|levar|mostr\w*|ver|veja|acess\w*|navegar|exib\w*)\b/,
    how: /\b(como|onde|qual|quais|ensin\w*|tutorial|passo|explic\w*|ajuda|configur\w*|conect\w*|o que e|para que serve)\b/,
    query: /\b(quanto\w*|quantas?|tenho|devo|falta\w*|atrasad\w*|resum\w*|situacao|quem)\b/,
  };
  function faqScore(e, q) {
    let s = 0, matched = 0;
    for (const t of q.content) {
      let bq = 0, ba = 0;
      for (const w of e.qWords) { const m = sameWord(t, w); if (m > bq) bq = m; }
      for (const w of e.aWords) { const m = sameWord(t, w); if (m > ba) ba = m; }
      const v = Math.max(bq * 2, ba);
      if (v > 0.6) { matched++; s += v; }
    }
    if (!matched || (q.content.length >= 3 && matched < 2)) return 0;
    const ratio = matched / q.content.length;
    return Math.min(s + ratio * 1.5, ratio === 1 && q.content.length >= 3 ? 6 : 4.2);
  }
  function score(entry, q) {
    if (entry.kind === "faq") return faqScore(entry, q);
    const qn = q.norm, qt = q.content, qa = qn.split(" ");
    let s = 0;
    for (const phrase of entry.kw) {
      const pn = norm(phrase);
      if (!pn) continue;
      const all = pn.split(" ");
      const nonstop = all.filter((w) => !STOP.has(w));
      if (!nonstop.length) continue;
      const words = nonstop.length >= 2 ? nonstop : all.length > 1 ? all : nonstop;
      if ((" " + qn + " ").includes(" " + pn + " ")) { s = Math.max(s, 3 + words.length * 0.8); continue; }
      let hit = 0;
      for (const w of words) {
        let best = 0;
        for (const t of nonstop.length >= 2 || all.length === 1 ? qt : qa) { const m = sameWord(t, w); if (m > best) best = m; }
        hit += best;
      }
      if (words.length) { const part = (hit / words.length) * (words.length > 1 ? 2.4 + words.length * 0.35 : 2.6); if (hit / words.length >= 0.6) s = Math.max(s, part); }
    }
    for (const w of content(entry.title)) for (const t of qt) { const m = sameWord(t, w); if (m) { s += 0.5 * m; break; } }
    if (entry.kind === "form" && q.create) s += 1.8;
    if (entry.kind === "screen" && q.open && !q.create) s += 0.8;
    if (entry.kind === "special" && /^q-/.test(entry.id) && q.query) s += 0.9;
    if (entry.kind === "guide" && q.how) s += 0.8;
    if (entry.kind === "form" && !q.create && !q.how && !q.open) s -= 0.6;
    return s;
  }
  function prepare(text) {
    const n = norm(text);
    return { raw: text, norm: n, content: content(text), create: RX.create.test(n), open: RX.open.test(n), how: RX.how.test(n), query: RX.query.test(n) };
  }
  function search(text, limit = 5) {
    const q = prepare(text);
    if (!q.content.length) return [];
    const list = MODE === "app" ? appIndex() : publicIndex(q);
    return list.map((e) => ({ e, s: score(e, q) })).filter((x) => x.s >= 1.8).sort((a, b) => b.s - a.s).slice(0, limit);
  }

  /* ───────── extração para preenchimento assistido ───────── */
  const MONEY = /(?:r\$\s*)(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)|(\d+(?:[.,]\d{1,2})?)\s*reais/i;
  const money = (t) => { const m = MONEY.exec(t); if (!m) return ""; let v = (m[1] || m[2]).replace(/\.(?=\d{3}\b)/g, ""); v = v.replace(".", ","); return v; };
  const cutName = (s) => {
    let v = s.split(/\s+(?:com|e-?mail|email|telefone|whatsapp|tel|que|por|a|no|na|custando|custa|pre[cç]o|valor|de r\$|r\$)\b|[,;@]|\d/i)[0].trim();
    v = v.replace(/^(?:chamad[oa]|de nome|nome|o|a|um|uma)\s+/i, "").trim();
    const words = v.split(/\s+/).filter(Boolean).slice(0, 4);
    return words.length ? titleCase(words.join(" ")) : "";
  };
  function extract(formId, raw) {
    const v = {};
    const text = raw.replace(/\s+/g, " ").trim();
    const n = norm(text);
    const email = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/.exec(text);
    if (formId === "f-cliente") {
      const m = /\b(?:cliente|contato)\s+(?:chamad[oa]\s+|de nome\s+|nome\s+)?(.+)/i.exec(text);
      const name = m ? cutName(m[1]) : "";
      if (name && !/^(novo|nova|um|uma)$/i.test(name)) v.n = name;
      if (email) v.e = email[0];
    } else if (formId === "f-produto") {
      const m = /\b(?:produto|servi[cç]o)\s+(?:chamad[oa]\s+|de nome\s+|nome\s+)?(.+)/i.exec(text);
      const name = m ? cutName(m[1]) : "";
      if (name && !/^(novo|nova|um|uma)$/i.test(name)) v.n = name;
      const p = money(text); if (p) v.p = p;
      const st = /estoque\s*(?:de\s*)?(\d+)|(\d+)\s*(?:unidades|un\b|itens)/i.exec(text); if (st) v.e = st[1] || st[2];
      if (/servi[cç]o/i.test(text)) v.t = "Serviço"; else if (/produto/i.test(text)) v.t = "Produto";
    } else if (formId === "f-lanc") {
      const val = money(text); if (val) v.v = val;
      if (/\b(despesa|gasto|saida|paguei|comprei|conta de)\b/.test(n)) v.t = "Saída";
      else if (/\b(entrada|recebi|receita|ganhei)\b/.test(n)) v.t = "Entrada";
      const d = /\b(?:despesa|gasto|lan[cç]amento|entrada|sa[ií]da|paguei|comprei|recebi)\s+(?:de |com |da |do |no valor de )?([^\d,R$]{3,40}?)(?:\s+(?:no valor|de|por|r\$)|\s*\d|$)/i.exec(text);
      if (d) { const desc = d[1].trim(); if (desc && !/^(novo|nova|um|uma)$/i.test(desc)) v.d = desc[0].toUpperCase() + desc.slice(1); }
    } else if (formId === "f-venda") {
      const prods = safe(() => PR.map((p) => p[0]), []);
      const hit = prods.filter((p) => n.includes(norm(p))).sort((a, b) => b.length - a.length)[0];
      if (hit) v.p = hit;
      const clients = safe(() => CL.map((c) => c[0]), []);
      const ch = clients.filter((c) => n.includes(norm(c))).sort((a, b) => b.length - a.length)[0] || clients.find((c) => c.length > 3 && n.split(" ").includes(norm(first(c))));
      if (ch) v.c = ch;
      const q = /(\d+)\s*(?:x|un\b|unid\w*|itens?|pe[cç]as?)\b|\bx\s*(\d+)/i.exec(text); if (q) v.q = q[1] || q[2];
      if (/\b(pendente|fiado|a prazo|paga depois|pagar depois)\b/.test(n)) v.s = "Pendente";
      else if (/\b(pago|pagou|paga|ja pagou|a vista)\b/.test(n)) v.s = "Pago";
    } else if (formId === "f-conversa") {
      const m = /\b(?:com|para|cliente|contato)\s+(?:a |o )?([\p{L}'’ -]{2,40})/iu.exec(text);
      const name = m ? cutName(m[1]) : ""; if (name) v.n = name;
      if (/instagram|direct/.test(n)) v.k = "Instagram"; else if (/whats/.test(n)) v.k = "WhatsApp";
    }
    return v;
  }

  /* ───────── conteúdo público (lido da própria página, nunca inventado) ───────── */
  const PUB = [
    { id: "historia", title: "A história do SocialMEI-IA", kw: ["historia", "como nasceu", "por que existe", "para que serve", "o que e o socialmei", "o que e socialmei", "o que e isso", "o que faz", "sobre o socialmei", "quem e socialmei", "socialmei"], sel: "#historia" },
    { id: "produto", title: "Produto: cada parte do negócio", kw: ["produto", "funcionalidades", "recursos", "o que tem", "o que inclui", "caixa unificada", "clientes", "vendas", "financeiro", "oportunidades", "divulgacao", "telas", "modulos"], sel: "#produto" },
    { id: "paramei", title: "Para quem é MEI", kw: ["mei", "microempreendedor", "serve para mim", "para quem e", "sou mei", "autonomo", "pequeno negocio", "meu dia", "sozinho"], sel: "#paramei" },
    { id: "como", title: "Como funciona", kw: ["como funciona", "como comeco", "comecar", "passos", "como usar", "como criar", "primeiros passos"], sel: "#como" },
    { id: "demo", title: "Experimente", kw: ["experimentar", "demonstracao", "demo", "testar", "ver funcionando", "exemplo", "ramo"], sel: "#demo" },
    { id: "precos", title: "Planos", kw: ["planos", "plano", "precos", "preco", "quanto custa", "gratis", "gratuito", "mensalidade", "valor", "assinatura", "pagar", "cartao"], sel: "#precos" },
    { id: "perguntas", title: "Perguntas frequentes", kw: ["perguntas frequentes", "duvidas", "faq", "perguntas"], sel: "#perguntas" },
  ];
  function publicIndex() {
    const out = PUB.map((s) => ({ ...s, kind: "pubsec", hint: "Seção do site" }));
    document.querySelectorAll("#perguntas details.faq").forEach((d, i) => {
      const qs = (d.querySelector("summary")?.textContent || "").trim();
      const a = (d.querySelector(".fa")?.textContent || "").trim();
      if (qs && a) out.push({ id: "faq-" + i, kind: "faq", title: qs, hint: "Pergunta frequente", kw: [], qWords: content(qs).filter((w) => w.length > 2), aWords: [...new Set(content(a).filter((w) => w.length > 4))].slice(0, 40), answer: a, el: d });
    });
    out.push({ id: "p-signup", kind: "cta", title: "Criar meu espaço", hint: "Começar no plano Grátis", kw: ["criar conta", "cadastrar", "comecar agora", "quero usar", "criar meu espaco", "abrir conta", "me cadastrar", "quero comecar", "criar espaco"], href: "#/cadastro" });
    out.push({ id: "p-login", kind: "cta", title: "Entrar", hint: "Acessar sua conta", kw: ["entrar", "login", "acessar minha conta", "fazer login", "ja tenho conta"], href: "#/entrar" });
    out.push({ id: "s-lia", kind: "special", title: "O que a Lia faz?", hint: "Minhas capacidades e limites", kw: ["o que a lia faz", "o que voce faz", "quem e voce", "o que voce pode fazer", "como voce pode ajudar", "lia", "suas funcoes", "seus comandos"] });
    return out;
  }
  const PRIVATE_ASK = /\b(meu|minha|meus|minhas)\b.*\b(vendas?|clientes?|conversas?|mensagens?|agenda|financeiro|estoque|pedidos|saldo|pagamentos?|negocio|empresa|conta)\b/;

  /* ───────── dados autorizados (somente leitura, já carregados na tela) ───────── */
  const arr = (fn) => { const v = safe(fn, null); return Array.isArray(v) ? v : null; };
  const dataReady = () => MODE === "app" && !!appReady() && !document.getElementById("app")?.hidden;
  const pending = () => arr(() => pendV()) || arr(() => V.map((v, k) => [v, k]).filter(([v]) => v[5] !== "Pago"));
  const unreadList = () => arr(() => C.filter(unread));
  const lowStock = () => arr(() => PR.filter((p) => p[9] !== "Serviço" && p[7] <= (typeof stMin === "function" ? stMin(p) : 3) && (p[7] > 0 || p[4])).sort((a, b) => a[7] - b[7]));
  const todayAgenda = () => arr(() => S.ag.filter((a) => a[0] === "Hoje" && !a[4]));

  /* ───────── ações verificadas ───────── */
  const sleepFrame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  async function navigate(path) {
    if (MODE !== "app") return false;
    const target = "#" + path;
    if (location.hash === target) return true;
    const c = ctxNow();
    if (!signedIn()) return false;
    try { if (typeof window.go === "function") window.go(path); else location.hash = target; } catch (_) { location.hash = target; }
    await sleepFrame();
    if (stale(c)) return false;
    return location.hash === target || location.hash.startsWith(target + "/");
  }
  async function showPending() {
    if (!signedIn()) return { ok: false, reason: "auth" };
    safe(() => { if ("vf" in S) S.vf = "Pendentes"; }, null);
    const c = ctxNow();
    const ok = await navigate("/negocio/vendas");
    if (stale(c)) return { ok: false, reason: "stale" };
    if (!ok) return { ok: false, reason: "nav" };
    if (typeof window.render === "function" && location.hash === "#/negocio/vendas") safe(() => { S.keepScroll = true; window.render(); }, null);
    await wait(80);
    if (stale(c)) return { ok: false, reason: "stale" };
    let chip = document.querySelector('[data-a="vf:Pendentes"]');
    const pressed = () => chip && chip.getAttribute("aria-pressed") === "true";
    if (chip && !pressed()) { chip.click(); await wait(80); if (stale(c)) return { ok: false, reason: "stale" }; chip = document.querySelector('[data-a="vf:Pendentes"]'); }
    return { ok: true, filtered: !!chip && chip.getAttribute("aria-pressed") === "true" };
  }
  const fieldFor = (dlg, key, rx) => {
    const byId = dlg.querySelector("#f_" + key);
    const lab = (el) => (el ? (dlg.querySelector(`label[for="${el.id}"]`)?.textContent || "") : "");
    if (byId && rx.test(lab(byId))) return byId;
    for (const l of dlg.querySelectorAll("label[for]")) if (rx.test(l.textContent)) return dlg.querySelector("#" + CSS.escape(l.htmlFor));
    return byId && !lab(byId) ? byId : null;
  };
  async function openFormFor(form, values) {
    if (!signedIn()) return { ok: false, reason: "auth" };
    if (!canWrite()) return { ok: false, reason: "role" };
    if (typeof window.openAction !== "function") return { ok: false, reason: "missing" };
    const c = ctxNow();
    try { window.openAction(form.action); } catch (_) { return { ok: false, reason: "error" }; }
    const dlg = await waitFor(() => { const d = document.querySelector("dialog[open]"); return d && d.querySelector("form") ? d : null; }, 1800);
    /* revalida contexto, sessão e permissão depois da espera: se mudou, não preenche nada */
    if (stale(c) || !signedIn() || !canWrite()) { if (dlg && dlg.isConnected && stale(c)) safe(() => dlg.close(), null); return { ok: false, reason: stale(c) ? "stale" : !signedIn() ? "auth" : "role" }; }
    if (!dlg || !dlg.isConnected) return { ok: false, reason: "noform" };
    const filled = [];
    for (const [key, rx] of form.fields) {
      const val = values && values[key];
      if (val == null || val === "") continue;
      const el = fieldFor(dlg, key, rx);
      if (!el) continue;
      if (el.tagName === "SELECT") {
        const want = norm(val);
        const opt = [...el.options].find((o) => norm(o.textContent) === want) || [...el.options].find((o) => norm(o.textContent).includes(want) && want.length > 2);
        if (!opt) continue;
        el.value = opt.value;
      } else el.value = String(val);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      filled.push((dlg.querySelector(`label[for="${el.id}"]`)?.textContent || key).replace(/\(opcional\)/i, "").trim());
    }
    const ctl = [...dlg.querySelectorAll("input:not([type=hidden]):not([type=checkbox]),select,textarea")];
    const target = ctl.find((c) => !c.value) || ctl[0];
    if (target) safe(() => target.focus({ preventScroll: true }), null);
    return { ok: true, filled, title: dlg.querySelector("h2")?.textContent || form.title };
  }
  let ring = [];
  function clearRing() { ring.forEach((r) => r.remove()); ring = []; }
  async function showWhere(entry) {
    clearRing();
    if (!entry || !entry.where || !entry.where.length) return false;
    const find = () => {
      const found = [];
      for (const sel of entry.where) { const n = [...document.querySelectorAll(sel)].filter(visible); if (n.length) found.push(n[0]); }
      return found.length ? found : null;
    };
    let els = find();
    if (!els && entry.path) { const c = ctxNow(); await navigate(entry.path); els = stale(c) ? null : await waitFor(find, 1400); if (stale(c)) return false; }
    if (!els) return false;
    els.slice(0, 2).forEach((el, i) => {
      safe(() => el.scrollIntoView({ block: "nearest", inline: "center", behavior: reduced() ? "auto" : "smooth" }), null);
      const draw = () => {
        const r = el.getBoundingClientRect();
        const d = document.createElement("div");
        d.className = "lia-ring";
        d.setAttribute("aria-hidden", "true");
        d.style.cssText = `left:${r.left - 5}px;top:${r.top - 5}px;width:${r.width + 10}px;height:${r.height + 10}px`;
        document.body.appendChild(d);
        ring.push(d);
        setTimeout(() => d.remove(), 4800);
      };
      setTimeout(draw, reduced() ? 0 : 260 + i * 80);
    });
    return true;
  }
  addEventListener("hashchange", clearRing);
  addEventListener("resize", clearRing, { passive: true });

  /* ───────── estado e DOM ───────── */
  const st = { open: false, thread: [], scope: null, busy: false, active: -1, results: [], opener: null, lastKey: "" };
  let root, panel, scrim, body, input, resBox, chips, badge, ctxEl, foot, form;
  const h = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "html") e.innerHTML = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat(Infinity)) { if (kid == null || kid === false) continue; e.append(kid.nodeType ? kid : document.createTextNode(String(kid))); }
    return e;
  };
  const rich = (text) => { const f = document.createDocumentFragment(); String(text).split(/\*\*(.+?)\*\*/g).forEach((p, i) => f.append(i % 2 ? h("strong", null, p) : document.createTextNode(p))); return f; };
  const ICON = {
    glyph: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M11 2.6c.62 4.6 2.9 6.9 7.5 7.5-4.6.62-6.88 2.9-7.5 7.5-.62-4.6-2.9-6.88-7.5-7.5 4.6-.6 6.88-2.9 7.5-7.5z" fill="currentColor"/><path d="M18.6 14.4c.26 1.9 1.2 2.84 3.1 3.1-1.9.26-2.84 1.2-3.1 3.1-.26-1.9-1.2-2.84-3.1-3.1 1.9-.26 2.84-1.2 3.1-3.1z" fill="currentColor" opacity=".8"/></svg>',
    send: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 12l16-8-6 17-3-7-7-2z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
    close: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
    clear: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 7h14M10 7V5h4v2m-7 0l1 12h8l1-12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    go: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 12h14m-5-5l5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    plus: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
    help: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M9.6 9.5a2.5 2.5 0 114 2c-.9.6-1.6 1-1.6 2.1M12 16.8h.01" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
    chart: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 19V9m7 10V5m7 14v-7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    where: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 3v3m0 12v3M3 12h3m12 0h3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  };
  const icon = (n, cls) => h("span", { class: "lia-ic" + (cls ? " " + cls : ""), html: ICON[n] });
  const glyph = (cls) => h("span", { class: "lia-glyph" + (cls ? " " + cls : ""), html: ICON.glyph, "aria-hidden": "true" });

  /* blocos de mensagem */
  const B = {
    text: (t) => ({ t: "text", text: t }),
    steps: (items) => ({ t: "steps", items }),
    list: (items) => ({ t: "list", items }),
    acts: (items) => ({ t: "acts", items }),
    note: (t) => ({ t: "note", text: t }),
    src: (t) => ({ t: "src", text: t }),
    draft: (d) => ({ t: "draft", ...d }),
  };
  const act = (label, run, o = {}) => ({ label, run, ...o });
  function btn(a) {
    const b = h("button", { type: "button", class: "lia-b" + (a.primary ? " p" : ""), "data-lia-act": a.id || "" }, a.icon ? icon(a.icon) : null, h("span", null, a.label));
    b.addEventListener("click", async () => {
      if (b.disabled) return;
      b.disabled = true;
      const c = ctxNow();
      try { await a.run(); } catch (_) { if (!stale(c)) say([B.text("Algo deu errado ao executar isso. Nada foi alterado.")]); } finally { b.disabled = false; }
    });
    return b;
  }
  function renderBlock(b) {
    switch (b.t) {
      case "text": return h("p", { class: "lia-p" }, rich(b.text));
      case "note": return h("p", { class: "lia-note" }, rich(b.text));
      case "src": return h("p", { class: "lia-src" }, b.text);
      case "steps": return h("ol", { class: "lia-steps" }, b.items.map((s) => h("li", null, rich(s))));
      case "acts": return h("div", { class: "lia-acts" }, b.items.map(btn));
      case "list": return h("ul", { class: "lia-list" }, b.items.map((it) => {
        const inner = [h("span", { class: "lia-dot", "data-tone": it.tone || "b", "aria-hidden": "true" }), h("span", { class: "lia-li-t" }, h("b", null, it.title), it.detail ? h("small", null, it.detail) : null), it.run ? icon("go", "lia-li-go") : null];
        if (!it.run) return h("li", null, h("div", { class: "lia-li" }, inner));
        const el = h("button", { type: "button", class: "lia-li" }, inner);
        el.addEventListener("click", async () => { try { await it.run(); } catch (_) {} });
        return h("li", null, el);
      }));
      case "draft": return h("div", { class: "lia-draft" },
        h("p", { class: "lia-p" }, rich(b.title)),
        h("dl", null, b.rows.map(([k, v]) => [h("dt", null, k), h("dd", null, v)])),
        h("div", { class: "lia-acts" }, b.items.map(btn)),
        h("p", { class: "lia-note" }, "Nada é salvo até você confirmar no próprio formulário."));
      default: return null;
    }
  }
  const scrollEnd = () => { if (body) body.scrollTo({ top: body.scrollHeight, behavior: reduced() ? "auto" : "smooth" }); };
  function addMsg(msg) {
    st.thread.push(msg);
    if (st.thread.length > 40) st.thread.shift();
    if (!body) return;
    body.querySelector(".lia-welcome")?.remove();
    const node = msg.role === "user"
      ? h("div", { class: "lia-m u" }, h("p", null, msg.text))
      : h("div", { class: "lia-m l" }, glyph("sm"), h("div", { class: "lia-mc" }, msg.blocks.map(renderBlock)));
    body.appendChild(node);
    scrollEnd();
  }
  const say = (blocks) => addMsg({ role: "lia", blocks });
  const sayAndClose = (blocks, keepOpen) => { say(blocks); if (!keepOpen) close({ restore: false }); };
  function setBusy(on, label) {
    st.busy = on;
    body.querySelector(".lia-typing")?.remove();
    if (on) { body.appendChild(h("div", { class: "lia-m l lia-typing", role: "status" }, glyph("sm pulse"), h("div", { class: "lia-mc" }, h("p", { class: "lia-p" }, h("span", { class: "lia-dots", "aria-hidden": "true" }, h("i"), h("i"), h("i")), h("span", { class: "lia-sr-t" }, label || "Lia está pensando…"))))); scrollEnd(); }
    form.setAttribute("aria-busy", on ? "true" : "false");
  }

  /* ───────── sugestões, recentes, status ───────── */
  const PUB_SUGGEST = ["O que é o SocialMEI-IA?", "Quanto custa?", "Funciona com meu WhatsApp?", "Como eu começo?", "Serve para quem é MEI?"];
  function suggestions() {
    if (MODE === "public") return PUB_SUGGEST;
    const ri = routeInfo();
    let list = KB.suggestionsByRoute[ri.key] || KB.suggestionsByRoute[ri.r] || KB.suggestionsByRoute.default;
    if (!canWrite()) list = list.filter((s) => !/cadastr|registrar|nova |novo |quero/i.test(s));
    if (!isManager()) list = list.filter((s) => !/equipe/i.test(s));
    return list.length ? list : KB.suggestionsByRoute.default;
  }
  const RKEY = "smei-lia-recent";
  const recents = () => (MODE !== "app" ? [] : safe(() => JSON.parse(localStorage.getItem(RKEY) || "[]"), []).filter((x) => typeof x === "string").slice(0, 6));
  function pushRecent(id) {
    if (MODE !== "app" || !id) return;
    const next = [id, ...recents().filter((x) => x !== id)].slice(0, 6);
    safe(() => localStorage.setItem(RKEY, JSON.stringify(next)), null);
  }
  function renderChips() {
    if (!chips) return;
    chips.replaceChildren(...suggestions().map((t) => h("button", { type: "button", class: "lia-chip", onclick: () => handle(t) }, t)));
  }
  function statusInfo() {
    const a = Adapter ? Adapter.status(MODE) : { available: false, reason: "disabled" };
    if (a.available) return { cls: "ai", text: "IA · " + a.label, tip: "Respostas de IA generativa são sugestões. Confira antes de agir." };
    if (typeof navigator !== "undefined" && navigator.onLine === false) return { cls: "off", text: "Sem internet · modo local", tip: "Sem conexão. Navegação, orientação e comandos continuam funcionando neste dispositivo." };
    if (a.reason && a.reason !== "disabled") return { cls: "off", text: "IA indisponível · modo local", tip: "A IA não está disponível agora. Sigo com a assistência local." };
    return { cls: "local", text: "Assistência local", tip: "IA generativa não conectada nesta versão. Navegação, orientação e comandos funcionam neste dispositivo." };
  }
  function renderStatus() {
    if (!badge) return;
    const s = statusInfo();
    badge.className = "lia-badge " + s.cls;
    badge.textContent = s.text;
    badge.title = s.tip;
    foot.textContent = s.cls === "ai" ? "Respostas de IA são sugestões: confira antes de agir. A Lia nunca salva, envia, cobra ou publica sozinha." : "Assistência local: navega, orienta e abre formulários. IA generativa não conectada nesta versão. A Lia nunca salva, envia, cobra ou publica sozinha.";
  }
  function renderContext() {
    if (!ctxEl) return;
    ctxEl.textContent = MODE === "public" ? "Site público · só informações abertas" : [bizName(), routeInfo().title].filter(Boolean).join(" · ");
  }
  function renderWelcome() {
    if (st.thread.length || !body) return;
    body.querySelector(".lia-welcome")?.remove();
    const rec = recents().map((id) => appIndex().find((e) => e.id === id)).filter(Boolean).slice(0, 4);
    const who = MODE === "app" ? safe(() => first(identity()?.usuario?.nome || S.user.nome), "") : "";
    body.prepend(h("div", { class: "lia-welcome" },
      glyph("lg"),
      h("h2", null, who ? `Oi, ${who}. Como posso ajudar?` : "Como posso ajudar?"),
      h("p", null, MODE === "public" ? "Tire dúvidas sobre o SocialMEI-IA. Só falo do que é público neste site: nunca vejo dados de ninguém." : `Estou com você em ${routeInfo().title}. Peça uma tela, uma ação ou uma orientação, do seu jeito.`),
      rec.length ? h("div", { class: "lia-rec" }, h("small", null, "Seus atalhos recentes"), h("div", null, rec.map((e) => h("button", { type: "button", class: "lia-chip r", onclick: () => handle(e.title) }, e.title)))) : null,
      h("p", { class: "lia-tip" }, "Dica: ", h("kbd", null, /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl"), " + ", h("kbd", null, "Shift"), " + ", h("kbd", null, "L"), " abre a Lia de qualquer tela.")));
  }

  /* ───────── respostas ───────── */
  const goBtn = (label, path, o = {}) => act(label, async () => {
    const c = ctxNow();
    const ok = await navigate(path);
    if (stale(c)) return;
    say([B.text(ok ? `Abri **${o.title || label.replace(/^Abrir\s+/i, "")}**.` : "Não consegui abrir essa tela agora. Use o menu lateral.")]);
    if (ok && matchMedia("(max-width:720px)").matches) close({ restore: false });
  }, { primary: o.primary, icon: "go" });
  const whereBtn = (entry) => act("Mostrar onde", async () => {
    if (matchMedia("(max-width:720px)").matches) close({ restore: false });
    const c = ctxNow();
    const ok = await showWhere(entry);
    if (stale(c)) return;
    if (!ok) say([B.text("Não encontrei esse item visível na tela agora. Abra o menu lateral e procure por **" + entry.title + "**.")]);
  }, { icon: "where" });
  const askBtn = (text, label) => act(label || text, () => handle(text), { icon: "help" });
  const whereText = (e) => (e.path.startsWith("/negocio/") ? `**Negócio › ${e.title}** (menu lateral)` : e.path.startsWith("/config/") ? `**${e.title.replace("Configurações · ", "Configurações › ")}**` : `**${e.title}** (menu lateral)`);
  const reasonMsg = (r) => ({
    role: "Seu acesso é de leitura, então não abro formulários de cadastro. Posso levar você às telas para consultar.",
    auth: "Entre na sua conta para eu poder ajudar com isso.",
    missing: "Não consegui abrir o formulário agora. Use o botão da própria tela.",
    noform: "O formulário não abriu a tempo. Nada foi alterado; use o botão da própria tela.",
    error: "Não consegui abrir o formulário agora. Nada foi alterado.",
    nav: "Não consegui abrir essa tela agora. Use o menu lateral.",
  }[r] || "Não consegui concluir isso agora. Nada foi alterado.");

  async function runForm(form, values) {
    const r = await openFormFor(form, values);
    if (r.reason === "stale") return;
    if (!r.ok) return say([B.text(reasonMsg(r.reason))]);
    const f = r.filled;
    sayAndClose([B.text(`Abri **${r.title}**${f.length ? ` com ${f.length === 1 ? "o campo" : "os campos"} ${f.join(", ")} preenchido${f.length === 1 ? "" : "s"}` : ""}. Nada foi salvo: revise e confirme no formulário.`)]);
  }
  function draftFor(entry, values, raw) {
    const dlgLabels = { n: "Nome", e: entry.id === "f-produto" ? "Estoque" : "E-mail", p: entry.id === "f-venda" ? "Produto" : "Preço de venda", c: "Cliente", q: "Quantidade", v: "Valor (R$)", s: "Pagamento", t: "Tipo", d: "Descrição", k: "Canal" };
    const rows = Object.entries(values).map(([k, v]) => [dlgLabels[k] || k, v]);
    return B.draft({ title: `Vou abrir **${entry.title}** com o que entendi:`, rows, items: [act("Abrir preenchido", () => runForm(entry, values), { primary: true, icon: "plus", id: "draft-open" }), act("Abrir vazio", () => runForm(entry, null), { id: "draft-blank" })] });
  }
  function answerScreen(e, q) {
    const where = /\b(onde|como)\b/.test(q.norm) && !q.open;
    if (where) return say([B.text(`${e.title.startsWith("Configurações") ? "Isso fica em" : "Você encontra isso em"} ${whereText(e)}.`), B.acts([goBtn("Abrir " + e.title, e.path, { primary: true, title: e.title }), whereBtn(e)])]);
    return navigate(e.path).then((ok) => {
      say([B.text(ok ? `Abri **${e.title}**.` : "Não consegui abrir essa tela agora. Use o menu lateral."), ...(ok && e.hint ? [B.note(e.hint + ".")] : [])]);
      if (ok && matchMedia("(max-width:720px)").matches) close({ restore: false });
    });
  }
  function answerForm(e, q) {
    const scr = KB.screens.find((s) => s.id === FORM_SCREEN[e.action]);
    if (/\b(onde|como)\b/.test(q.norm) && scr) return say([B.text(`Você faz isso em ${whereText(scr)}. Se preferir, eu abro o formulário agora.`), B.acts([act("Abrir formulário", () => runForm(e, null), { primary: true, icon: "plus" }), goBtn("Ir para " + scr.title, scr.path, { title: scr.title }), whereBtn(scr)])]);
    const values = extract(e.id, q.raw);
    if (Object.keys(values).length) return say([draftFor(e, values, q.raw)]);
    return runForm(e, null);
  }
  function answerGuide(g) {
    const e = { title: g.title, path: g.path, where: (KB.screens.find((s) => s.path === g.path) || {}).where };
    const acts = [g.filter ? act(g.cta, async () => { const r = await showPending(); say([B.text(r.ok ? (r.filtered ? "Abri **Vendas** só com as pendentes." : "Abri **Vendas**, mas não achei o filtro de pendentes nesta tela; use os filtros da lista.") : reasonMsg(r.reason))]); }, { primary: true, icon: "go" }) : goBtn(g.cta, g.path, { primary: true, title: (KB.screens.find((s) => s.path === g.path) || {}).title }), whereBtn(e)];
    say([B.text(`**${g.title}**`), B.steps(g.steps), ...(g.note ? [B.note(g.note)] : []), B.acts(acts)]);
  }
  const noData = () => say([B.text("Os dados deste negócio ainda não terminaram de carregar. Tente de novo em instantes."), B.acts([goBtn("Abrir Início", "/inicio", { title: "Início" })])]);
  async function consultBusiness(id) {
    const bridge = window.SocialMEIV22;
    if (!remote() || !bridge?.request) return say([B.text("Entre em um negócio conectado para consultar os registros.")]);
    const context = ctxNow();
    const workspace = identity()?.negocio.id;
    setBusy(true, "Consultando registros do negócio…");
    try {
      const isOpportunity = id === "q-oportunidades";
      const result = await bridge.request(isOpportunity ? "/opportunities" : "/reporting/finance");
      if (stale(context)) return;
      if (result.workspace_id !== workspace) throw Error();
      if (isOpportunity) {
        const today = new Date().toLocaleDateString("sv-SE");
        const due = result.items.filter((row) => row.outcome === "open" &&
          typeof row.follow_up_date === "string" && row.follow_up_date <= today)
          .sort((a, b) => a.follow_up_date.localeCompare(b.follow_up_date));
        return say([
          B.text(due.length ? "Oportunidades da lista com retorno vencido ou marcado para hoje." : "Nenhum retorno vencido ou marcado para hoje na lista consultada."),
          ...(due.length ? [B.list(due.slice(0, 5).map((row) => ({ title: row.title, detail: row.follow_up_date, tone: "y" })))] : []),
          B.acts([goBtn("Abrir Oportunidades", "/oport", { title: "Oportunidades" })]),
        ]);
      }
      const amount = (value) => {
        if (typeof value !== "string" || !/^-?\d+\.\d{2}$/.test(value)) throw Error();
        return brlFmt(Number(value));
      };
      const rows = id === "q-contas"
        ? [
            { title: "A receber em atraso", detail: amount(result.overdue.incoming) },
            { title: "A pagar em atraso", detail: amount(result.overdue.outgoing) },
          ]
        : [
            { title: "Entradas registradas", detail: amount(result.paid.incoming) },
            { title: "Saídas registradas", detail: amount(result.paid.outgoing) },
            { title: "Saldo dos lançamentos pagos", detail: amount(result.paid.balance) },
          ];
      return say([
        B.text(id === "q-contas" ? "Posição registrada em " + result.overdue.as_of + "." :
          "Período de " + result.period.start + " a " + result.period.end + "."),
        B.list(rows), B.src("Relatório financeiro do negócio ativo"),
        B.acts([goBtn("Abrir Relatórios", "/relatorios", { title: "Relatórios" })]),
      ]);
    } catch {
      if (!stale(context)) say([B.text("Não foi possível confirmar os registros. Confira a tela correspondente.")]);
    } finally {
      if (!stale(context)) setBusy(false);
    }
  }

  async function special(e) {
    switch (e.id) {
      case "q-contas":
      case "q-caixa":
      case "q-oportunidades":
        return consultBusiness(e.id);
      case "q-dia": {
        const items = dataReady() ? safe(() => window.SocialMEIv76?.collect?.(), null) : null;
        if (!items) return noData();
        const open = items.filter((i) => !i.snoozed);
        if (!open.length) return say([B.text("Não encontrei pendências nos registros carregados. Se quiser, aproveite para divulgar ou cadastrar algo."), B.src(dataOrigin()), B.acts([goBtn("Abrir Divulgação", "/divul", { title: "Divulgação" }), goBtn("Abrir Meu dia", "/inicio", { title: "Início · Meu dia" })])]);
        const top = open.slice(0, 4);
        return say([B.text(`Encontrei **${plural(open.length, "coisa", "coisas")}** pedindo atenção. Sugiro começar por **${top[0].title}**.`), B.list(top.map((i) => ({ title: i.title + (i.example ? " (exemplo)" : ""), detail: i.detail, tone: i.tone, run: () => navigate(i.href || "/inicio").then((ok) => ok && matchMedia("(max-width:720px)").matches && close({ restore: false })) }))), B.src(dataOrigin()), B.acts([goBtn("Abrir Meu dia", "/inicio", { primary: true, title: "Início · Meu dia" })]), B.note("Cobranças e envios são feitos por você, nas ações do Meu dia.")]);
      }
      case "q-pendentes": {
        const c0 = ctxNow();
        const r = await showPending();
        if (stale(c0) || r.reason === "stale") return;
        const p = pending();
        const tot = p ? p.reduce((t, [v]) => t + (Number(v[6]) || 0), 0) : null;
        if (!r.ok) return say([B.text(reasonMsg(r.reason))]);
        say([B.text(r.filtered ? `Abri **Vendas** só com as pendentes${p ? `: ${plural(p.length, "venda", "vendas")}, ${brlFmt(tot)}` : ""}.` : "Abri **Vendas**, mas não achei o filtro de pendentes nesta tela. Use os filtros da lista."), ...(p ? [B.src(dataOrigin())] : [])]);
        if (matchMedia("(max-width:720px)").matches) close({ restore: false });
        return;
      }
      case "q-receber": {
        const p = dataReady() ? pending() : null;
        if (!p) return noData();
        const tot = p.reduce((t, [v]) => t + (Number(v[6]) || 0), 0);
        if (!p.length) return say([B.text("Não há vendas pendentes nos registros carregados."), B.src(dataOrigin())]);
        return say([B.text(`Você tem **${brlFmt(tot)}** a receber em **${plural(p.length, "venda pendente", "vendas pendentes")}**.`), B.src(dataOrigin()), B.acts([act("Ver vendas pendentes", () => special({ id: "q-pendentes" }), { primary: true, icon: "go" }), askBtn("Quem está me devendo?")])]);
      }
      case "q-devendo": {
        const p = dataReady() ? pending() : null;
        if (!p) return noData();
        if (!p.length) return say([B.text("Ninguém aparece com pagamento pendente nos registros carregados."), B.src(dataOrigin())]);
        const g = new Map();
        for (const [v] of p) { const k = String(v[2] || "Cliente avulso"); const c = g.get(k) || { n: 0, t: 0 }; c.n++; c.t += Number(v[6]) || 0; g.set(k, c); }
        const rows = [...g.entries()].sort((a, b) => b[1].t - a[1].t).slice(0, 5);
        return say([B.text(`**${plural(g.size, "cliente", "clientes")}** com pagamento pendente, somando ${brlFmt(p.reduce((t, [v]) => t + (Number(v[6]) || 0), 0))}.`), B.list(rows.map(([n, c]) => ({ title: n, detail: `${brlFmt(c.t)} · ${plural(c.n, "venda", "vendas")}`, tone: "y", run: () => special({ id: "q-pendentes" }) }))), B.src(dataOrigin())]);
      }
      case "q-conversas": {
        const u = dataReady() ? unreadList() : null;
        if (!u) return noData();
        if (!u.length) return say([B.text("Nenhuma conversa esperando resposta nos registros carregados."), B.src(dataOrigin()), B.acts([goBtn("Abrir Caixa Unificada", "/caixa", { title: "Caixa Unificada" })])]);
        return say([B.text(`**${plural(u.length, "conversa espera", "conversas esperam")}** resposta.`), B.list(u.slice(0, 3).map((c) => ({ title: String(c[1] || "Contato"), tone: "b", run: () => navigate("/caixa/" + c[0]).then((ok) => ok && matchMedia("(max-width:720px)").matches && close({ restore: false })) }))), B.src(dataOrigin()), B.acts([goBtn("Abrir Caixa Unificada", "/caixa", { primary: true, title: "Caixa Unificada" })]), B.note("A Lia não responde clientes nem envia mensagens.")]);
      }
      case "q-estoque": {
        const l = dataReady() ? lowStock() : null;
        if (!l) return noData();
        if (!l.length) return say([B.text("Nenhum produto com estoque baixo nos registros carregados."), B.src(dataOrigin())]);
        return say([B.text(`**${plural(l.length, "produto precisa", "produtos precisam")}** de reposição.`), B.list(l.slice(0, 5).map((p) => ({ title: String(p[0]), detail: p[7] <= 0 ? "Sem estoque" : `Restam ${p[7]} un.`, tone: p[7] <= 0 ? "r" : "y", run: () => navigate("/negocio/produtos") }))), B.src(dataOrigin()), B.acts([goBtn("Abrir Produtos e serviços", "/negocio/produtos", { primary: true, title: "Produtos e serviços" })])]);
      }
      case "q-agenda": {
        const a = dataReady() ? todayAgenda() : null;
        if (!a) return noData();
        if (!a.length) return say([B.text("Não há compromissos em aberto para hoje nos registros carregados."), B.src(dataOrigin()), B.acts([goBtn("Abrir Agenda", "/agenda", { title: "Agenda" })])]);
        return say([B.text(`Hoje você tem **${plural(a.length, "compromisso em aberto", "compromissos em aberto")}**.`), B.list(a.slice(0, 5).map((x) => ({ title: String(x[2]), detail: x[1] && x[1] !== "—" ? "Às " + x[1] : "Sem horário", tone: "b", run: () => navigate("/agenda") }))), B.src(dataOrigin()), B.acts([goBtn("Abrir Agenda", "/agenda", { primary: true, title: "Agenda" })])]);
      }
      case "s-aqui": {
        const ri = routeInfo();
        return say([B.text(`Você está em **${ri.title}**${ri.entry?.hint ? ": " + ri.entry.hint.toLowerCase() : ""}.${ri.inConversation ? " Há uma conversa aberta." : ""}`), B.text("Daqui eu posso:"), B.acts(suggestions().filter((s) => !/ajuda desta/i.test(s)).slice(0, 4).map((s) => askBtn(s)))]);
      }
      case "s-lia":
        return say(MODE === "public"
          ? [B.text("Sou a **Lia**, assistente do SocialMEI-IA. Aqui no site eu respondo dúvidas com o que está escrito na própria página: planos, como funciona, perguntas frequentes."), B.note("Não vejo dados de ninguém e ainda não uso IA generativa: respondo com regras locais."), B.acts([askBtn("Quanto custa?"), askBtn("Como eu começo?")])]
          : [B.text("Sou a **Lia**, assistente do SocialMEI-IA. Eu:"), B.steps(["levo você a qualquer tela, pelo jeito que você falar;", "abro formulários existentes e preencho campos com o que você disser (você revisa e confirma no formulário);", "leio números já carregados na tela: a receber, estoque, agenda, conversas;", "explico como fazer as coisas e mostro onde fica cada item."]), B.note("Não uso IA generativa nesta versão: respondo com regras locais. Nunca salvo, envio, cobro ou publico nada sozinha."), B.acts([askBtn("Organizar meu dia"), askBtn("Ajuda desta tela")])]);
      default: return null;
    }
  }
  /* respostas públicas, sempre a partir do DOM da página */
  const blurb = (sel) => (document.querySelector(sel + " .sx-sub, " + sel + " .sub")?.textContent || document.querySelector(sel + " .sx-hist-text p")?.textContent || "").replace(/\s+/g, " ").trim();
  const goSection = (id, faq) => {
    if (matchMedia("(max-width:720px)").matches) close({ restore: false });
    if (faq) faq.open = true;
    const a = document.querySelector(`a[data-go="${id}"]`);
    if (a && !faq) a.click();
    else (faq || document.getElementById(id))?.scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: faq ? "center" : "start" });
  };
  const signupActs = () => B.acts([act("Criar meu espaço", () => { location.hash = "#/cadastro"; close({ restore: false }); }, { primary: true, icon: "go" }), act("Entrar", () => { location.hash = "#/entrar"; close({ restore: false }); })]);
  function answerPublic(e) {
    if (e.kind === "faq") return say([B.text(e.answer), B.note("Resposta da seção Perguntas do site."), B.acts([act("Ver na página", () => goSection("perguntas", e.el), { icon: "where" })])]);
    if (e.kind === "cta") return say([B.text(e.id === "p-signup" ? "Para começar, abra o cadastro. Os detalhes do que cada plano inclui estão na seção Planos." : "Para entrar, abra o acesso à sua conta."), signupActs()]);
    if (e.id === "precos") {
      const plans = [...document.querySelectorAll("#precos article.plan")].map((p) => {
        const name = p.querySelector("h3")?.textContent.trim() || "";
        const head = (p.querySelector(".plan-h")?.textContent || "").replace(name, "").replace(/\s+/g, " ").trim();
        const tag = p.querySelector("p.m")?.textContent.trim() || "";
        const li = [...p.querySelectorAll("li")].map((x) => x.textContent.trim()).slice(0, 3);
        return { title: name + (head ? " · " + head : ""), detail: [tag, li.join(", ")].filter(Boolean).join(": ") };
      }).filter((p) => p.title);
      const sub = blurb("#precos");
      return say([B.text(sub || "Estes são os planos que aparecem no site."), ...(plans.length ? [B.list(plans.map((p) => ({ ...p, tone: "g" })))] : []), B.src("Informações da seção Planos do site."), B.acts([act("Ver planos na página", () => goSection("precos"), { icon: "where" }), act("Criar meu espaço", () => { location.hash = "#/cadastro"; close({ restore: false }); }, { primary: true, icon: "go" })])]);
    }
    if (e.kind === "pubsec") { const t = blurb(e.sel); return say([B.text(`**${e.title}**${t ? ": " + t : ""}`), B.acts([act("Ir para a seção", () => goSection(e.id), { primary: true, icon: "where" })])]); }
    if (e.kind === "special") return special(e);
  }
  async function fallback(text, q) {
    const near = (MODE === "app" ? appIndex() : publicIndex()).map((e) => ({ e, s: score(e, q) })).filter((x) => x.s >= 0.9 && x.e.kind !== "faq").sort((a, b) => b.s - a.s).slice(0, 3);
    const ad = Adapter ? Adapter.status(MODE) : { available: false };
    if (ad.available) {
      const c = ctxNow();
      liveCtl = new AbortController();
      const myCtl = liveCtl;
      setBusy(true);
      try {
        const ri = MODE === "app" ? routeInfo() : { key: "publico", title: "Site público" };
        const out = await Adapter.ask(MODE, { signal: myCtl.signal, text, context: { mode: MODE, route: ri.key, title: ri.title, role: MODE === "app" ? role() || "local" : "visitante", locale: "pt-BR", features: MODE === "app" ? appIndex().map((e) => e.id) : [] }, history: st.thread.filter((m) => m.role === "user").slice(-4).map((m) => m.text) });
        if (liveCtl === myCtl) liveCtl = null;
        if (stale(c) || myCtl.signal.aborted) { syncScope(); return; } /* resposta de outro contexto: descartada em silêncio */
        setBusy(false);
        const acts = [];
        for (const a of out.actions) {
          if (MODE === "app" && a && a.type === "nav" && typeof a.path === "string") { const s = KB.screens.find((x) => x.path === a.path && (!x.manager || isManager())); if (s) acts.push(goBtn("Abrir " + s.title, s.path, { title: s.title })); }
          else if (MODE === "app" && a && a.type === "form" && canWrite()) { const f = KB.forms.find((x) => x.id === a.id); if (f) acts.push(act(f.title, () => runForm(f, null), { icon: "plus" })); }
        }
        return say([{ t: "text", text: out.text.replace(/\*\*/g, "") }, B.note(`Resposta de IA (${out.label}). Confira antes de agir; nada foi alterado.`), ...(acts.length ? [B.acts(acts)] : [])]);
      } catch (e) {
        if (liveCtl === myCtl) liveCtl = null;
        if (stale(c) || myCtl.signal.aborted) { syncScope(); return; }
        setBusy(false);
        say([B.text(e.code === "timeout" ? "A IA demorou demais e não respondeu. Sigo com a assistência local." : "A IA não respondeu agora. Sigo com a assistência local.")]);
      }
    }
    const acts = near.map(({ e }) => askBtn(e.title)).concat(MODE === "app" ? [goBtn("Abrir Ajuda", "/ajuda", { title: "Ajuda" })] : [act("Ver perguntas do site", () => goSection("perguntas"), { icon: "where" })]);
    return say([B.text(MODE === "public" ? "Não encontrei isso nas informações públicas do site." : "Ainda não sei fazer isso sozinha. Minha assistência local cobre navegação, orientação e comandos."), ...(ad.available ? [] : [B.note("A IA generativa não está conectada nesta versão, por isso não improviso respostas.")]), ...(near.length ? [B.text("Quem sabe você quis dizer:")] : []), B.acts(acts)]);
  }
  function greet() {
    const hr = new Date().getHours();
    const g = hr < 12 ? "Bom dia" : hr < 18 ? "Boa tarde" : "Boa noite";
    const who = MODE === "app" ? safe(() => first(identity()?.usuario?.nome || S.user.nome), "") : "";
    say([B.text(`${g}${who ? ", " + who : ""}! O que você precisa?`), B.acts(suggestions().slice(0, 3).map((s) => askBtn(s)))]);
  }
  function guardApp() {
    if (MODE === "app" && !signedIn()) { say([B.text("Entre na sua conta para usar a Lia no aplicativo.")]); return false; }
    return true;
  }
  async function dispatchEntry(e, q) {
    if (MODE === "app") pushRecent(e.id);
    if (MODE === "public") return answerPublic(e);
    if (e.kind === "screen") return answerScreen(e, q);
    if (e.kind === "form") return answerForm(e, q);
    if (e.kind === "guide") return answerGuide(e);
    if (e.kind === "special") return special(e);
  }
  async function handle(text) {
    text = String(text || "").replace(/\s+/g, " ").trim().slice(0, 400);
    if (!text || st.busy) return;
    syncScope();
    if (!st.open) open();
    addMsg({ role: "user", text });
    clearInput();
    if (!guardApp()) return;
    const q = prepare(text), n = q.norm;
    if (/^(oi|ola|opa|e ai|bom dia|boa tarde|boa noite|hey|hello)\b/.test(n) && q.content.length <= 2) return greet();
    if (/\b(obrigad[oa]|valeu|brigad[oa]|agradeco)\b/.test(n) && q.content.length <= 3) return say([B.text("Por nada! Se precisar, é só chamar.")]);
    if (/^(limpar|apagar|zerar|resetar)\b.*\b(conversa|historico|chat)\b/.test(n)) { hardReset(true); return; }
    if (MODE === "public" && PRIVATE_ASK.test(n)) return say([B.text("Aqui no site eu só falo do que é público. Para ver ou usar os seus dados, entre na sua conta."), signupActs()]);
    if (MODE === "app" && !canWrite() && q.create) {
      const f = KB.forms.map((e) => ({ e: { ...e, kind: "form" }, s: 0 })).map((x) => ({ ...x, s: score(x.e, q) })).sort((a, b) => b.s - a.s)[0];
      if (f && f.s >= 3.5) return say([B.text(reasonMsg("role")), B.acts([askBtn("Mostrar vendas pendentes"), askBtn("Organizar meu dia")])]);
    }
    const res = search(text, 4);
    if (!res.length) return fallback(text, q);
    return dispatchEntry(res[0].e, q);
  }

  /* ───────── contexto: troca de negócio/usuário e saída ───────── */
  function hardReset(keepOpen) {
    epoch++;
    if (liveCtl) { safe(() => liveCtl.abort(), null); liveCtl = null; }
    if (st.busy && body) setBusy(false);
    st.thread = [];
    st.results = [];
    st.active = -1;
    clearRing();
    if (body) { body.replaceChildren(); renderWelcome(); }
    if (input) input.value = "";
    renderResults();
    if (!keepOpen) close({ restore: false });
    renderContext(); renderChips(); renderStatus();
  }
  function syncScope() {
    const s = scopeKey();
    if (st.scope === null) { st.scope = s; return true; }
    if (s !== st.scope) { st.scope = s; hardReset(false); return false; }
    return true;
  }

  /* ───────── busca ao digitar (paleta) ───────── */
  const KIND_ICON = { screen: "go", form: "plus", guide: "help", special: "chart", faq: "help", pubsec: "where", cta: "go" };
  const KIND_LABEL = { screen: "Ir para", form: "Abrir formulário", guide: "Guia", special: "Consulta", faq: "Pergunta frequente", pubsec: "Seção do site", cta: "Ação" };
  function renderResults() {
    if (!resBox) return;
    resBox.replaceChildren();
    const open = st.results.length > 0;
    resBox.hidden = !open;
    input.setAttribute("aria-expanded", String(open));
    if (!open) { input.removeAttribute("aria-activedescendant"); return; }
    st.results.forEach((r, i) => {
      const li = h("li", { role: "option", id: "lia-opt-" + i, class: "lia-opt" + (i === st.active ? " on" : ""), "aria-selected": String(i === st.active) }, icon(KIND_ICON[r.e.kind] || "go"), h("span", { class: "lia-opt-t" }, h("b", null, r.e.title), h("small", null, r.e.kind === "faq" ? KIND_LABEL.faq : (r.e.hint || KIND_LABEL[r.e.kind]))), h("span", { class: "lia-opt-k" }, KIND_LABEL[r.e.kind]));
      li.addEventListener("mousedown", (ev) => ev.preventDefault());
      li.addEventListener("click", () => pick(i));
      resBox.append(li);
    });
    if (st.active >= 0) input.setAttribute("aria-activedescendant", "lia-opt-" + st.active); else input.removeAttribute("aria-activedescendant");
  }
  function onType() {
    const v = input.value.trim();
    const r = v.length >= 2 ? search(v, 5) : [];
    st.results = r.filter((x) => x.s >= r[0].s * 0.6);
    st.active = -1;
    renderResults();
  }
  function pick(i) {
    const r = st.results[i];
    if (!r || st.busy) return;
    const text = input.value.trim();
    addMsg({ role: "user", text });
    clearInput();
    if (!guardApp()) return;
    dispatchEntry(r.e, prepare(text));
  }
  function clearInput() { input.value = ""; st.results = []; st.active = -1; renderResults(); }

  /* ───────── painel, abertura e teclado ───────── */
  const isNarrow = () => matchMedia("(max-width:720px)").matches;
  function buildPanel() {
    scrim = h("div", { class: "lia-scrim", hidden: true, onclick: () => close() });
    body = h("div", { class: "lia-body", role: "log", "aria-live": "polite", "aria-relevant": "additions", "aria-label": "Conversa com a Lia", tabindex: "0" });
    input = h("input", { type: "text", class: "lia-in", id: "lia-in", role: "combobox", "aria-autocomplete": "list", "aria-expanded": "false", "aria-controls": "lia-res", "aria-label": "Pergunte ou peça algo à Lia", placeholder: MODE === "public" ? "Pergunte sobre o SocialMEI-IA…" : "Peça uma tela, uma ação ou ajuda…", autocomplete: "off", enterkeyhint: "send", maxlength: "400" });
    resBox = h("ul", { class: "lia-res", id: "lia-res", role: "listbox", "aria-label": "Resultados sugeridos", hidden: true });
    chips = h("div", { class: "lia-chips", role: "group", "aria-label": "Sugestões" });
    badge = h("span", { class: "lia-badge local", tabindex: "0", role: "note" });
    ctxEl = h("small", { class: "lia-ctx" });
    foot = h("p", { class: "lia-foot" });
    form = h("form", { class: "lia-form", novalidate: true }, input, h("button", { type: "submit", class: "lia-send", "aria-label": "Enviar" }, icon("send")));
    form.addEventListener("submit", (e) => { e.preventDefault(); handle(input.value); });
    input.addEventListener("input", onType);
    input.addEventListener("keydown", (e) => {
      if (e.isComposing) return;
      const n = st.results.length;
      if (e.key === "ArrowDown" && n) { e.preventDefault(); st.active = (st.active + 1) % n; renderResults(); }
      else if (e.key === "ArrowUp" && n) { e.preventDefault(); st.active = st.active <= 0 ? n - 1 : st.active - 1; renderResults(); }
      else if (e.key === "Enter" && st.active >= 0) { e.preventDefault(); pick(st.active); }
      else if (e.key === "Escape") { if (n || input.value) { e.preventDefault(); e.stopPropagation(); clearInput(); } }
    });
    panel = h("section", { class: "lia-panel", role: "dialog", "aria-label": "Lia, assistente", "aria-modal": "false", hidden: true, tabindex: "-1" },
      h("header", { class: "lia-hd" }, glyph("md"), h("div", { class: "lia-id" }, h("b", null, "Lia"), ctxEl), badge,
        h("button", { type: "button", class: "lia-ib", "aria-label": "Limpar conversa", title: "Limpar conversa", onclick: () => hardReset(true) }, icon("clear")),
        h("button", { type: "button", class: "lia-ib", "aria-label": "Fechar a Lia", title: "Fechar (Esc)", onclick: () => close() }, icon("close"))),
      body, chips, h("div", { class: "lia-dock" }, resBox, form), foot);
    panel.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !e.defaultPrevented) { e.preventDefault(); close(); }
      else if (e.key === "Tab" && isNarrow()) {
        const f = [...panel.querySelectorAll("button:not([disabled]),input,[tabindex='0']")].filter(visible);
        if (!f.length) return;
        const a = f[0], z = f[f.length - 1];
        if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
        else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
      }
    });
    root = h("div", { class: "lia-root", "data-mode": MODE }, scrim, panel);
    document.body.appendChild(root);
  }
  function layoutViewport() {
    const vv = window.visualViewport;
    if (vv && isNarrow() && st.open) { root.style.setProperty("--lia-vh", vv.height + "px"); root.style.setProperty("--lia-kb", Math.max(0, innerHeight - vv.height - vv.offsetTop) + "px"); }
    else { root.style.removeProperty("--lia-vh"); root.style.removeProperty("--lia-kb"); }
  }
  function syncLaunchers() { document.querySelectorAll("[data-lia-launch]").forEach((b) => b.setAttribute("aria-expanded", String(st.open))); }
  function open() {
    if (!root) return;
    if (MODE === "app" && !(signedIn() && appReady())) return;
    syncScope();
    if (st.open) { input.focus(); return; }
    st.opener = document.activeElement;
    st.open = true;
    panel.hidden = false;
    scrim.hidden = !isNarrow();
    renderContext(); renderStatus(); renderChips(); renderWelcome(); syncLaunchers(); layoutViewport();
    requestAnimationFrame(() => root.classList.add("is-open"));
    safe(() => input.focus({ preventScroll: true }), null);
  }
  function close(o = {}) {
    if (!st.open) return;
    st.open = false;
    root.classList.remove("is-open");
    const done = () => { if (!st.open) { panel.hidden = true; scrim.hidden = true; } };
    if (reduced()) done(); else setTimeout(done, 220);
    syncLaunchers(); layoutViewport();
    if (o.restore !== false) {
      const t = st.opener && document.contains(st.opener) && visible(st.opener) ? st.opener : document.querySelector("[data-lia-launch]");
      safe(() => t && t.focus({ preventScroll: true }), null);
    }
  }
  const toggle = () => (st.open ? close() : open());
  function makeLauncher() {
    return h("button", { type: "button", class: "lia-launch", "data-lia-launch": "", "aria-haspopup": "dialog", "aria-expanded": String(st.open), "aria-keyshortcuts": "Control+Shift+L Meta+Shift+L", title: "Lia, assistente (Ctrl+Shift+L)", "aria-label": "Abrir a Lia, assistente", onclick: toggle }, glyph("sm"), h("span", { class: "lia-launch-t" }, "Lia"));
  }
  function ensureLauncher() {
    if (MODE === "public") {
      const host = document.querySelector(".nav-act");
      if (host && !host.querySelector("[data-lia-launch]")) host.prepend(makeLauncher());
      return;
    }
    const ok = signedIn() && appReady();
    if (!ok) { document.querySelectorAll("[data-lia-launch]").forEach((b) => b.remove()); if (st.open) close({ restore: false }); return; }
    const host = document.querySelector("#app .top .r2");
    if (host && !host.querySelector("[data-lia-launch]")) host.prepend(makeLauncher());
  }
  function onGlobalKey(e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || !e.shiftKey || e.key.toLowerCase() !== "l") return;
    if (MODE === "app" && !(signedIn() && appReady())) return;
    if (document.querySelector("dialog[open]") && !root.contains(e.target)) return;
    e.preventDefault();
    toggle();
  }
  let tick = 0;
  function onShellChange() {
    if (tick) return;
    tick = requestAnimationFrame(() => {
      tick = 0;
      syncScope();
      ensureLauncher();
      const k = MODE === "app" ? routeInfo().key : "pub";
      if (k !== st.lastKey) { st.lastKey = k; if (st.open) { renderContext(); renderChips(); renderWelcome(); } }
    });
  }
  function boot() {
    buildPanel();
    renderStatus(); renderContext(); renderChips();
    document.addEventListener("keydown", onGlobalKey);
    addEventListener("hashchange", onShellChange);
    addEventListener("online", renderStatus);
    addEventListener("offline", renderStatus);
    addEventListener("socialmei-lia-adapter-change", renderStatus);
    addEventListener("resize", () => { layoutViewport(); if (st.open) scrim.hidden = !isNarrow(); }, { passive: true });
    if (window.visualViewport) { visualViewport.addEventListener("resize", layoutViewport); visualViewport.addEventListener("scroll", layoutViewport); }
    if (MODE === "app") {
      const app = document.getElementById("app");
      new MutationObserver(onShellChange).observe(app, { childList: true, attributes: true, attributeFilter: ["hidden"] });
      setInterval(() => { if (!document.hidden) onShellChange(); }, 1500);
    }
    ensureLauncher();
    st.scope = scopeKey();
    st.lastKey = MODE === "app" ? routeInfo().key : "pub";
  }
  window.SocialMEILia = Object.freeze({
    version: VERSION, mode: MODE, open, close, toggle, ask: handle, reset: () => hardReset(false),
    registerAdapter: Adapter ? Adapter.register : undefined,
    state: () => ({ open: st.open, messages: st.thread.length, scope: st.scope }),
    _t: Object.freeze({ search: (t) => search(t, 5).map((x) => ({ id: x.e.id, kind: x.e.kind, s: +x.s.toFixed(2) })), extract, norm }),
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true }); else boot();
})();
