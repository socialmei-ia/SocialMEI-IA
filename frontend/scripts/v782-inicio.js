/* SocialMEI-IA · v7.8.2 · Refinamento da tela inicial.
   Substitui apenas a marcação do Início (rota #/inicio). Nenhuma regra de negócio é alterada:
   - lê as pendências de SocialMEIv76.collect() (conversas, cobranças, estoque, agenda, DAS);
   - toda ação continua nas ações existentes (agok, md76snz, md76cobrar, md76das, md76resumo, agnew…);
   - se algo falhar, devolve o Início anterior (v7.6). */
(() => {
  "use strict";
  if (window.SocialMEIv782) return;
  const ready = () =>
    typeof inicio === "function" && typeof render === "function" && typeof A === "object" && typeof S === "object" &&
    window.SocialMEIv76 && window.SocialMEIv76.ui;

  function start() {
    const K = window.SocialMEIv76, U = K.ui;
    const { collect, remote, canWrite, store } = K;
    const { pulse, setupPanel, origin, timeToMin, nowMin, plural, enc } = U;
    const prevInicio = inicio;

    const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
    const greet = () => (typeof GRT !== "undefined" ? GRT : "Olá");
    const dateTxt = () => cap(new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" }));

    /* ---------- ação principal de cada pendência ---------- */
    const go = (it, lead) => {
      const cls = "hm-go" + (lead ? " lead" : ""), a = it.act ? `data-a="${esc(it.act)}"` : "";
      if (it.act && (it.kind === "agenda" || !it.href)) return `<button type="button" class="${cls}" ${a}>${esc(it.ctaAct || it.cta || "Feito")}</button>`;
      return `<a class="${cls}" href="#${esc(it.href)}">${esc(it.cta)}</a>`;
    };
    const item = (it, n) => {
      const snz = it.canSnooze
        ? `<button type="button" class="hm-snz" data-a="md76snz:${enc(it.key)}" aria-label="Adiar para amanhã: ${esc(it.title)}" title="Adiar para amanhã">${i("clock", 16)}</button>` : "";
      return `<li class="hm-it${n === 0 ? " is-lead" : ""}" data-tone="${it.tone}"><span class="hm-dot" aria-hidden="true"></span><span class="hm-tx"><b>${esc(it.title)}${it.example ? '<em class="hm-ex">exemplo</em>' : ""}</b><small>${esc(it.detail)}</small></span><span class="hm-ac">${go(it, n === 0)}${snz}</span></li>`;
    };

    /* ---------- blocos ---------- */
    function focus(items) {
      const vis = items.filter((x) => !x.snoozed), hid = items.length - vis.length, top = vis.slice(0, 4), more = vis.slice(4);
      const body = top.length
        ? `<ul class="hm-list">${top.map(item).join("")}</ul>`
        : `<div class="hm-clear"><b>Nada urgente por aqui.</b><span>Que tal divulgar um produto ou combinar o próximo retorno com um cliente?</span><span class="hm-clear-a"><a class="hm-go" href="#/divul">Preparar divulgação</a>${canWrite() ? `<button type="button" class="hm-go" data-a="agnew">Novo lembrete</button>` : ""}</span></div>`;
      return `<section class="hm-sec" aria-labelledby="hm_f"><header class="hm-h"><h2 id="hm_f">Para hoje${vis.length ? `<span class="hm-n">${vis.length}</span>` : ""}</h2><button type="button" class="hm-lk" data-a="md76resumo">Resumo do dia</button></header>${body}
        ${more.length ? `<details class="hm-more"><summary>Ver mais ${more.length}</summary><ul class="hm-list">${more.map((it) => item(it, 1)).join("")}</ul></details>` : ""}
        ${hid ? `<p class="hm-quiet">${plural(hid, "item adiado", "itens adiados")} para amanhã. <button type="button" class="hm-lk" data-a="md76unsnz">Mostrar de novo</button></p>` : ""}</section>`;
    }
    function agenda() {
      const ag = (S.ag || []).map((a, k) => ({ a, k })).filter(({ a }) => a[0] === "Hoje").sort((x, y) => (timeToMin(x.a[1]) ?? 1e4) - (timeToMin(y.a[1]) ?? 1e4));
      const shown = ag.slice(0, 4), rest = ag.length - shown.length;
      const list = shown.length
        ? `<ol class="hm-ag">${shown.map(({ a, k }) => { const m = timeToMin(a[1]), late = !a[4] && m != null && m < nowMin();
            return `<li class="${a[4] ? "done" : ""}${late ? " late" : ""}"><button type="button" class="hm-ck" role="checkbox" aria-checked="${!!a[4]}" aria-label="Marcar como feito: ${esc(a[2])}" data-a="agok:${k}">${i("check", 14)}</button><span class="hm-h2">${esc(a[1] && a[1] !== "—" ? a[1] : "Hoje")}</span><span class="hm-tx"><b>${esc(a[2])}</b>${a[3] ? `<small>${esc(a[3])}</small>` : ""}</span></li>`; }).join("")}</ol>${rest > 0 ? `<a class="hm-lk" href="#/agenda">+ ${rest} na agenda</a>` : ""}`
        : `<p class="hm-quiet">Nenhum compromisso hoje.${canWrite() ? ` <button type="button" class="hm-lk" data-a="agnew">Criar lembrete</button>` : ""}</p>`;
      return `<section class="hm-sec" aria-labelledby="hm_a"><header class="hm-h"><h2 id="hm_a">Agenda</h2><a class="hm-lk" href="#/agenda">Abrir</a></header>${list}</section>`;
    }
    function month() {
      const p = pulse();
      if (!p.hasSales && !p.hasFin) return "";
      const dl = (c, pv) => { if (!pv) return ""; const pc = Math.round(((c - pv) / pv) * 100); return `<small class="hm-dl" data-d="${pc === 0 ? "eq" : pc > 0 ? "up" : "down"}">${pc === 0 ? "igual ao mês anterior" : (pc > 0 ? "▲ " : "▼ ") + Math.abs(pc) + "% vs. mês anterior"}</small>`; };
      const row = (l, v, href, sub, tone) => `<a class="hm-fg" href="#${href}"${tone ? ` data-tone="${tone}"` : ""}><span>${l}${sub || ""}</span><b class="big">${v}</b></a>`;
      const rows = [
        p.hasSales ? row("Vendas", brl(p.salesSum), "/negocio/vendas", dl(p.salesSum, p.prevSalesSum)) : "",
        p.hasSales ? row("A receber", brl(p.rec), "/negocio/vendas", `<small>${p.recN ? plural(p.recN, "venda pendente", "vendas pendentes") : "nenhuma pendente"}</small>`, p.recN ? "y" : "") : "",
        p.hasFin ? row("Saídas", brl(p.out), "/negocio/financeiro", "", p.out > p.inc && p.inc + p.out > 0 ? "r" : "") : "",
      ].join("");
      return `<section class="hm-sec" aria-labelledby="hm_m"><header class="hm-h"><h2 id="hm_m">Este mês</h2></header><div class="hm-fig">${rows}</div><p class="hm-quiet" style="margin-top:10px">Soma dos registros do mês. Não é lucro nem saldo do banco.</p></section>`;
    }
    const lia = () => window.SocialMEILia
      ? `<div class="hm-lia"><span class="hm-lia-i" aria-hidden="true">${i("spark", 16)}</span><span>Quer ajuda para organizar o dia?</span><button type="button" class="hm-lk" data-hm-lia>Pedir à Lia</button></div>` : "";

    function head(sub, o) {
      const [ot, ol] = o || origin();
      return `<header class="hm-top"><div class="hm-meta"><span>${esc(dateTxt())}</span><span class="hm-org" data-o="${ot}" title="${ot === "demo" ? "Conversas, clientes e vendas desta tela são exemplos para avaliação." : "Informações registradas no seu negócio."}"><i></i>${esc(ol)}</span></div><h1>${esc(greet())}, ${esc(S.user.nome)}</h1><p class="hm-sub">${sub}</p></header>`;
    }

    inicio = function () {
      try {
        if (homeStage() !== "operacao") {
          const prep = homeStage() === "preparacao";
          return `<div class="hm hm-setup">${head(prep ? "Seu negócio está tomando forma. Continue de onde parou." : "Vamos montar o seu espaço, um passo de cada vez.")}<div class="hm-setup-b">${setupPanel(true)}</div></div>`;
        }
        const items = collect().filter((x) => x.kind !== "agenda"), n = items.filter((x) => !x.snoozed).length;
        const sub = n > 4 ? "Veja o que mais importa agora." : n ? `${plural(n, "coisa pede", "coisas pedem")} a sua atenção.` : "Está tudo em dia. Bom trabalho!";
        return `<div class="hm">${head(sub)}<div class="hm-grid"><div class="hm-col">${focus(items)}${lia()}</div><div class="hm-col hm-side">${agenda()}${month()}</div></div></div>`;
      } catch (e) { console.warn("Início v7.8.2 indisponível; exibindo o início anterior.", e); return prevInicio.apply(this, arguments); }
    };

    document.addEventListener("click", (e) => {
      const b = e.target.closest && e.target.closest("[data-hm-lia]"); if (!b) return;
      const L = window.SocialMEILia; if (!L) return;
      try { L.open(); setTimeout(() => { try { L.ask("Organizar meu dia"); } catch (_) {} }, 60); } catch (_) {}
    });

    window.SocialMEIv782 = { version: "7.8.2" };
    try { render(); } catch (_) {}
  }

  if (ready()) start();
  else { let n = 0; const t = setInterval(() => { if (ready()) { clearInterval(t); start(); } else if (++n > 600) clearInterval(t); }, 25); }
})();
