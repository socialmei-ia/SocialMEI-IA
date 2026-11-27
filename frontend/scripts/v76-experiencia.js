/* SocialMEI-IA · v7.6 · Experiência completa (camada de apresentação).
   Módulos: Meu dia no negócio (início), Primeiros passos, Configurações e perfil.
   Regras desta camada:
   - Só lê os arrays que o app e o v22-backend já preenchem (C, V, PR, F, CL, S.ag). Nenhum endpoint novo.
   - Toda gravação segue pelas ações existentes (A.agok, A.ck, openAction, cobrar…). Nada é confirmado aqui.
   - Dados de demonstração e dados reais são sempre identificados pelo rótulo de origem.
   - Preferências locais usam chaves "smei-v76-*": no modo remoto o bootstrap já as isola por usuário e negócio. */
(() => {
  "use strict";
  if (window.SocialMEIv76) return;
  const ready = () =>
    typeof inicio === "function" && typeof bemvindo === "function" && typeof config === "function" &&
    typeof render === "function" && typeof A === "object" && typeof S === "object" && typeof PR !== "undefined";

  function start() {
    /* ============ utilidades ============ */
    const DAY = 864e5;
    const remote = () => !!window.SocialMEIV22?.remote;
    const role = () => window.SocialMEIAuth?.current?.papel;
    const canWrite = () => !remote() || role() !== "viewer";
    const store = {
      get(k, d) { try { const v = localStorage.getItem("smei-v76-" + k); return v == null ? d : JSON.parse(v); } catch (_) { return d; } },
      set(k, v) { try { localStorage.setItem("smei-v76-" + k, JSON.stringify(v)); return true; } catch (_) { return false; } },
    };
    const today0 = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime(); };
    const dayOf = (ms) => { const d = new Date(ms); d.setHours(0, 0, 0, 0); return d.getTime(); };
    const iso = (ms) => { const d = new Date(ms); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
    const ageDays = (txt) => { const t = typeof pdt === "function" ? pdt(txt) : 0; return t > 0 ? Math.round((today0() - dayOf(t)) / DAY) : null; };
    const rel = (n) => (n == null ? "" : n <= 0 ? "hoje" : n === 1 ? "ontem" : `há ${n} dias`);
    const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
    const first = (s) => String(s || "").trim().split(/\s+/)[0] || "cliente";
    const enc = (s) => encodeURIComponent(String(s));
    const origin = () => (remote() ? ["real", "Dados do seu negócio"] : ["demo", "Dados de exemplo"]);
    const kindOfBusiness = () => {
      const forced = store.get("kind", null);
      if (["produtos", "servicos", "misto"].includes(forced)) return forced;
      const svc = PR.filter((p) => p[9] === "Serviço").length, prd = PR.length - svc;
      if (!PR.length) return "misto";
      return svc && !prd ? "servicos" : prd && !svc ? "produtos" : "misto";
    };
    const inMonth = (txt, offset = 0) => {
      const t = typeof pdt === "function" ? pdt(txt) : 0; if (!t) return false;
      const n = new Date(), ref = new Date(n.getFullYear(), n.getMonth() + offset, 1), d = new Date(t);
      return d.getFullYear() === ref.getFullYear() && d.getMonth() === ref.getMonth() && (offset !== 0 || dayOf(t) <= today0());
    };
    const timeToMin = (hhmm) => { const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || "")); return m ? +m[1] * 60 + +m[2] : null; };
    const nowMin = () => { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); };
    const snoozed = () => { const s = store.get("snooze", {}), t = iso(today0()); return Object.fromEntries(Object.entries(s).filter(([, until]) => until > t)); };

    /* ============ Meu dia: coleta de pendências reais (ou de exemplo) ============ */
    function collect() {
      const items = [], snz = snoozed();
      const push = (it) => { it.snoozed = !!snz[it.key]; items.push(it); };
      const demo = !remote();
      // Conversas aguardando resposta
      const conv = typeof unread === "function" ? C.filter(unread) : [];
      conv.slice(0, 3).forEach((c, n) => push({
        key: "c_" + c[0], kind: "conversa", icon: "chat", tone: "b", score: 82 - n,
        title: "Responder " + first(c[1]), detail: String(typeof prev === "function" ? prev(c) : c[5] || ""),
        href: "/caixa/" + c[0], cta: "Responder", canSnooze: true,
      }));
      if (conv.length > 3) push({ key: "c_mais", kind: "conversa", icon: "chat", tone: "b", score: 60, title: `Mais ${plural(conv.length - 3, "conversa", "conversas")} esperando`, detail: "Abra a Caixa para ver todas.", href: "/caixa", cta: "Abrir Caixa", canSnooze: true });
      // Cobranças pendentes (mais antigas primeiro)
      const pend = (typeof pendV === "function" ? pendV() : []).map(([v, k]) => ({ v, k, age: ageDays(v[4]) }));
      pend.sort((a, b) => (b.age ?? -1) - (a.age ?? -1)).slice(0, 3).forEach(({ v, k, age }) => {
        const late = age != null && age >= 7;
        push({
          key: "v_" + v[0], kind: "cobranca", icon: "cart", tone: late ? "r" : "y", score: late ? 90 : 72,
          title: "Cobrar " + first(v[2]), detail: `${brl(v[6])} · venda ${v[0]}${age != null ? " · " + rel(age) : ""}${late ? " · atrasada" : ""}`,
          href: demo ? null : "/negocio/vendas", act: demo ? "md76cobrar:" + k : null, cta: "Cobrar", canSnooze: true,
        });
      });
      // Estoque
      const low = PR.filter((p) => p[9] !== "Serviço" && p[7] <= stMin(p) && (p[7] > 0 || p[4]));
      low.sort((a, b) => a[7] - b[7]).slice(0, 2).forEach((p) => push({
        key: "e_" + p[1], kind: "estoque", icon: "store", tone: p[7] <= 0 ? "r" : "y", score: p[7] <= 0 ? 76 : 55,
        title: "Repor " + p[0], detail: p[7] <= 0 ? "Está sem estoque" : `Estoque baixo · restam ${p[7]} un. (mínimo ${stMin(p)})`,
        href: "/negocio/produtos", cta: "Ver produto", canSnooze: true,
      }));
      // Compromissos de hoje ainda abertos
      const ag = (S.ag || []).map((a, k) => ({ a, k })).filter(({ a }) => a[0] === "Hoje" && !a[4]);
      const nm = nowMin();
      ag.forEach(({ a, k }) => {
        const m = timeToMin(a[1]), late = m != null && m < nm, soon = m != null && m >= nm && m - nm <= 90;
        if (!late && !soon && ag.length > 2) return;
        push({
          key: "a_" + k + "_" + enc(a[2]).slice(0, 24), kind: "agenda", icon: "cal", tone: late ? "r" : soon ? "y" : "b", score: late ? 85 : soon ? 78 : 58,
          title: a[2], detail: `${a[1] && a[1] !== "—" ? "Hoje às " + a[1] : "Hoje"}${a[3] ? " · " + a[3] : ""}${late ? " · horário passou" : soon ? " · em breve" : ""}`,
          href: "/agenda", act: "agok:" + k, ctaAct: "Feito", cta: "Agenda", canSnooze: true,
        });
      });
      // Oportunidades (somente demonstração: não há fonte real nesta tela)
      if (demo && typeof OP !== "undefined") {
        const ready2 = (OP.find((g) => /fechar/i.test(g[0])) || [0, 0, []])[2][0];
        if (ready2) push({
          key: "o_" + ready2[0], kind: "oportunidade", icon: "bars", tone: "g", score: 62, example: true,
          title: `Fechar com ${first(ready2[1])}`, detail: `${ready2[2]} · ${brl(ready2[3])} · ${ready2[4]}`, href: "/oport", cta: "Ver oportunidade", canSnooze: true,
        });
      }
      // DAS do MEI: regra de calendário (vence dia 20). Quem confirma o pagamento é a própria pessoa.
      if (!store.get("das-off", false) && typeof dasInfo === "function") {
        const d = dasInfo(), ym = iso(today0()).slice(0, 7), paid = store.get("das-paid", {});
        // v7.8: competência atrasada (dias 21–26, mês atual não pago) → "Já paguei" marca ESTE mês, nunca o seguinte.
        const lateDas = new Date().getDate() > 20 && new Date().getDate() <= 26 && !paid[ym];
        const dueMonth = new Date(); dueMonth.setDate(1); if (new Date().getDate() > 20 && !lateDas) dueMonth.setMonth(dueMonth.getMonth() + 1);
        const keyM = lateDas ? ym : dueMonth.getFullYear() + "-" + String(dueMonth.getMonth() + 1).padStart(2, "0");
        if (!paid[keyM] && (d.dias <= 6 || lateDas)) push({
          key: "das_" + keyM, kind: "das", icon: "doc", tone: d.dias <= 2 || lateDas ? "r" : "y", score: lateDas ? 74 : d.dias <= 2 ? 84 : 66,
          title: lateDas ? "DAS do MEI: vencimento passou" : "DAS do MEI vence dia 20",
          detail: lateDas ? "O vencimento é todo dia 20. Confira no Portal do Empreendedor e regularize." : d.dias <= 0 ? "Vence hoje. Confira no Portal do Empreendedor." : `Faltam ${plural(d.dias, "dia", "dias")}. Lembrete de calendário: o app não consulta o pagamento.`,
          act: "md76das:" + keyM, ctaAct: "Já paguei", canSnooze: false, dasMonth: keyM,
        });
      }
      items.sort((a, b) => b.score - a.score);
      return items;
    }

    function pulse() {
      const sales = V.filter((v) => inMonth(v[4])), prevSales = V.filter((v) => inMonth(v[4], -1));
      const fin = F.filter((x) => inMonth(x[0])), prevFin = F.filter((x) => inMonth(x[0], -1));
      const inc = sum(fin.filter((x) => x[3]), (x) => x[4]), out = sum(fin.filter((x) => !x[3]), (x) => x[4]);
      const pend = typeof pendV === "function" ? pendV() : [];
      return {
        hasSales: V.length > 0, hasFin: F.length > 0,
        salesN: sales.length, salesSum: sum(sales, (v) => v[6]), prevSalesSum: sum(prevSales, (v) => v[6]), prevSalesN: prevSales.length,
        inc, out, prevInc: sum(prevFin.filter((x) => x[3]), (x) => x[4]), recN: pend.length, rec: sum(pend, ([v]) => v[6]),
      };
    }
    const delta = (cur, prev) => !prev ? '<span class="md-dl">sem dados no mês anterior</span>' : (() => {
      const pc = Math.round(((cur - prev) / prev) * 100);
      return `<span class="md-dl" data-d="${pc === 0 ? "eq" : pc > 0 ? "up" : "down"}">${pc === 0 ? "igual ao" : (pc > 0 ? "▲ " : "▼ ") + Math.abs(pc) + "% vs."} mês anterior</span>`;
    })();

    /* ============ Meu dia: marcação ============ */
    const row = (it, big) => {
      const act = it.act ? `data-a="${esc(it.act)}"` : "";
      const main = it.href
        ? `<a class="md-go" href="#${esc(it.href)}">${esc(it.cta)}${i("arrow", 16)}</a>`
        : `<button type="button" class="md-go" ${act}>${esc(it.ctaAct || it.cta)}${i("arrow", 16)}</button>`;
      const extra = it.href && it.act ? `<button type="button" class="md-sec" ${act}>${esc(it.ctaAct || "Feito")}</button>` : "";
      const snz = it.canSnooze ? `<button type="button" class="md-snz" data-a="md76snz:${enc(it.key)}" aria-label="Adiar para amanhã: ${esc(it.title)}" title="Adiar para amanhã">${i("cal", 16)}</button>` : "";
      return `<li class="md-it" data-tone="${it.tone}"><span class="md-ic" aria-hidden="true">${i(it.icon, 20)}</span><span class="md-tx"><b>${esc(it.title)}${it.example ? '<em class="md-ex">exemplo</em>' : ""}</b><small>${esc(it.detail)}</small></span><span class="md-ac">${extra}${main}${snz}</span></li>`;
    };
    function nextCard(items) {
      const top = items.find((x) => !x.snoozed);
      if (!top) return `<div class="cs md-next md-clear"><span class="md-kick">Tudo em dia</span><b>Nada urgente por aqui.</b><p>Aproveite para divulgar um produto ou combinar o próximo retorno com um cliente.</p><div class="md-nact"><a class="btn" href="#/divul">${i("mega", 18)}Preparar divulgação</a>${canWrite() ? `<button type="button" class="btn o" data-a="agnew">${i("plus", 18)}Novo lembrete</button>` : ""}</div>${quick()}</div>`;
      const main = top.href ? `<a class="btn" href="#${esc(top.href)}">${esc(top.cta)}${i("arrow", 18)}</a>` : `<button type="button" class="btn" data-a="${esc(top.act)}">${esc(top.ctaAct || top.cta)}${i("arrow", 18)}</button>`;
      return `<div class="cs md-next" data-tone="${top.tone}"><span class="md-kick">${i("bolt", 14)}Faça agora</span><b>${esc(top.title)}</b><p>${esc(top.detail)}</p><div class="md-nact">${main}${top.canSnooze ? `<button type="button" class="btn o" data-a="md76snz:${enc(top.key)}">Adiar para amanhã</button>` : ""}</div>${quick()}</div>`;
    }
    function quick() {
      if (!canWrite()) return "";
      const k = kindOfBusiness();
      const q = [
        ["Registrar venda", "cart", "/negocio/vendas", "venda"],
        ["Novo lembrete", "cal", null, null, "agnew"],
        ["Cadastrar cliente", "users", "/negocio/clientes", "cliente"],
        [k === "servicos" ? "Cadastrar serviço" : "Cadastrar produto", "box", "/negocio/produtos", "produto"],
        ["Lançar entrada ou saída", "doc", "/negocio/financeiro", "lanc"],
      ];
      return `<div class="md-quick" role="group" aria-label="Ações rápidas">${q.map(([l, ic, h, af, a]) => h ? `<a href="#${h}" data-after="${af}">${i(ic, 18)}<span>${l}</span></a>` : `<button type="button" data-a="${a}">${i(ic, 18)}<span>${l}</span></button>`).join("")}</div>`;
    }
    function board(items) {
      const [ot, ol] = origin(), vis = items.filter((x) => !x.snoozed), hid = items.length - vis.length;
      const top = vis.slice(0, 5), more = vis.slice(5);
      const p = pulse(), ag = (S.ag || []).map((a, k) => ({ a, k })), todayAg = ag.filter(({ a }) => a[0] === "Hoje").sort((x, y) => (timeToMin(x.a[1]) ?? 1e4) - (timeToMin(y.a[1]) ?? 1e4));
      const tomorrow = ag.filter(({ a }) => a[0] === "Amanhã" && !a[4]).length;
      const stat = (label, val, sub, href, tone) => `<a class="md-st" href="#${href}"${tone ? ` data-tone="${tone}"` : ""}><small>${label}</small><b>${val}</b>${sub}</a>`;
      const pulseHtml = p.hasSales || p.hasFin
        ? `<div class="md-pulse">${p.hasSales ? stat("Vendas no mês", brl(p.salesSum), `<span class="md-dl">${plural(p.salesN, "venda", "vendas")}</span>${delta(p.salesSum, p.prevSalesSum)}`, "/negocio/vendas") : ""}${p.hasSales ? stat("A receber", brl(p.rec), `<span class="md-dl">${p.recN ? plural(p.recN, "venda pendente", "vendas pendentes") : "nenhuma pendente"}</span>`, "/negocio/vendas", p.recN ? "y" : "") : ""}${p.hasFin ? stat("Entradas no mês", brl(p.inc), delta(p.inc, p.prevInc), "/negocio/financeiro") : ""}${p.hasFin ? stat("Saídas no mês", brl(p.out), `<span class="md-dl">lançamentos pagos</span>`, "/negocio/financeiro", p.out > p.inc && p.inc + p.out > 0 ? "r" : "") : ""}</div><p class="md-note">Soma dos registros do mês. Não é lucro nem saldo do banco.</p>`
        : `<p class="md-empty">Quando houver vendas ou lançamentos, o resumo do mês aparece aqui.</p>`;
      const alert = p.hasFin && p.out > p.inc && p.inc + p.out > 0 ? `<li class="md-it" data-tone="y"><span class="md-ic" aria-hidden="true">${i("doc", 20)}</span><span class="md-tx"><b>Saídas maiores que as entradas neste mês</b><small>${brl(p.out)} saíram e ${brl(p.inc)} entraram. Revise os lançamentos.</small></span><span class="md-ac"><a class="md-go" href="#/negocio/financeiro">Ver financeiro${i("arrow", 16)}</a></span></li>` : "";
      const list = top.map((it) => row(it)).join("") + alert;
      const agHtml = todayAg.length
        ? `<ol class="md-tl">${todayAg.map(({ a, k }) => { const m = timeToMin(a[1]), late = !a[4] && m != null && m < nowMin(); return `<li class="${a[4] ? "done" : ""}${late ? " late" : ""}"><button type="button" class="ckb" role="checkbox" aria-checked="${!!a[4]}" aria-label="Marcar como feito: ${esc(a[2])}" data-a="agok:${k}">${i("check", 16)}</button><span class="md-h">${esc(a[1])}</span><span class="md-tt"><b>${esc(a[2])}</b>${a[3] ? `<small>${esc(a[3])}</small>` : ""}</span></li>`; }).join("")}</ol>`
        : `<p class="md-empty">Nenhum compromisso para hoje.${canWrite() ? ` <button type="button" class="lk" data-a="agnew">Criar lembrete</button>` : ""}</p>`;
      return `<div class="md76" aria-label="Meu dia no negócio">
        <section class="md-main" aria-labelledby="md_t"><header class="md-hd"><h2 id="md_t">Meu dia</h2><span class="md-org" data-o="${ot}">${ol}</span></header>
          ${list ? `<ul class="md-list">${list}</ul>` : `<div class="md-ok">${i("check", 20)}<div><b>Sem pendências por aqui.</b><small>Conversas, cobranças, estoque e compromissos de hoje estão em dia.</small></div></div>`}
          ${more.length ? `<details class="md-more"><summary>Ver mais ${more.length}</summary><ul class="md-list">${more.map((it) => row(it)).join("")}</ul></details>` : ""}
          ${hid ? `<p class="md-hid">${plural(hid, "item adiado", "itens adiados")} para amanhã. <button type="button" class="lk" data-a="md76unsnz">Mostrar de novo</button></p>` : ""}
          ${remote() ? "" : `<p class="md-note">${i("info", 14)} Pendências calculadas a partir dos exemplos desta demonstração.</p>`}
        </section>
        <div class="md-side">
          <section aria-labelledby="md_a"><header class="md-hd"><h2 id="md_a">Agenda de hoje</h2><a class="lk sm" href="#/agenda">Abrir agenda</a></header>${agHtml}${tomorrow ? `<p class="md-note">Amanhã: <a href="#/agenda">${plural(tomorrow, "compromisso", "compromissos")}</a>.</p>` : ""}</section>
          <section aria-labelledby="md_p"><header class="md-hd"><h2 id="md_p">Pulso do mês</h2></header>${pulseHtml}</section>
          <button type="button" class="md-close" data-a="md76resumo">${i("doc", 18)}<span><b>Fechar o dia</b><small>Gerar um resumo para copiar ou enviar a você mesmo</small></span></button>
        </div></div>`;
    }

    /* ============ Início: transforma a saída original sem recriá-la ============ */
    const baseInicio = inicio;
    inicio = function () {
      const html = baseInicio.apply(this, arguments);
      try {
        const tpl = document.createElement("template"); tpl.innerHTML = html;
        const hero = tpl.content.querySelector(".hero"), hl = hero && hero.querySelector(".hl"), phj = hl && hl.querySelector(".phj"), cs = hero && hero.querySelector(".cs");
        if (!hero || !hl || !phj || !cs) return html;
        if (homeStage() !== "operacao") { phj.replaceWith(htmlNode(setupPanel(true))); return tpl.innerHTML; }
        const items = collect();
        phj.remove();
        cs.replaceWith(htmlNode(nextCard(items)));
        hero.classList.add("md-hero");
        hero.insertAdjacentHTML("afterend", board(items));
        return tpl.innerHTML;
      } catch (e) { console.warn("Meu dia indisponível; exibindo o início original."); return html; }
    };
    const htmlNode = (h) => { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstElementChild; };

    /* ============ Ações do Meu dia ============ */
    Object.assign(A, {
      md76snz: (v) => {
        const key = decodeURIComponent(v), s = store.get("snooze", {}), until = iso(today0() + DAY);
        s[key] = until; store.set("snooze", s);
        toast("Adiado para amanhã", "Desfazer", () => { const s2 = store.get("snooze", {}); delete s2[key]; store.set("snooze", s2); S.keepScroll = true; render(); });
      },
      md76unsnz: () => { store.set("snooze", {}); },
      md76cobrar: (v) => { cobrar(+v); return false; },
      md76das: (v) => {
        if (!/^\d{4}-\d{2}$/.test(String(v))) return false;
        const p = store.get("das-paid", {}); p[v] = 1; store.set("das-paid", p);
        toast("Anotado por você. O app não consulta o pagamento do DAS.", "Desfazer", () => { const q = store.get("das-paid", {}); delete q[v]; store.set("das-paid", q); S.keepScroll = true; render(); });
      },
      md76dasoff: () => { store.set("das-off", true); toast("Lembrete do DAS desativado", "Desfazer", () => { store.set("das-off", false); S.keepScroll = true; render(); }); },
      md76resumo: () => { resumoDia(); return false; },
      md76copy: (v, btn) => {
        const t = document.getElementById("md76txt");
        const done = (ok) => { btn.textContent = ok ? "Copiado ✓" : "Selecione o texto e copie (Ctrl+C)"; if (!ok && t) { t.focus(); t.select(); } };
        if (navigator.clipboard?.writeText) navigator.clipboard.writeText(t.value).then(() => done(true), () => done(false)); else done(false);
        return false;
      },
    });

    function resumoDia() {
      const t0 = today0(), vToday = V.filter((v) => { const t = pdt(v[4]); return t > 0 && dayOf(t) === t0; });
      const paidToday = vToday.filter((v) => v[5] === "Pago"), pend = typeof pendV === "function" ? pendV() : [];
      const ag = S.ag || [], doneN = ag.filter((a) => a[0] === "Hoje" && a[4]).length, openA = ag.filter((a) => a[0] === "Hoje" && !a[4]), tomorrow = ag.filter((a) => a[0] === "Amanhã" && !a[4]);
      const conv = typeof unread === "function" ? C.filter(unread).length : 0, ds = new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
      const lines = [
        `Resumo do dia · ${S.biz.nome} · ${ds}`,
        remote() ? "" : "(dados de exemplo da demonstração)",
        "",
        `Vendas registradas hoje: ${vToday.length}${vToday.length ? " (" + brl(sum(vToday, (v) => v[6])) + ")" : ""}`,
        `Registradas como pagas hoje: ${paidToday.length}${paidToday.length ? " (" + brl(sum(paidToday, (v) => v[6])) + ")" : ""}`,
        `Cobranças pendentes: ${pend.length}${pend.length ? " (" + brl(sum(pend, ([v]) => v[6])) + ")" : ""}`,
        `Conversas aguardando resposta: ${conv}`,
        `Compromissos de hoje: ${doneN} feitos, ${openA.length} em aberto${openA.length ? ": " + openA.map((a) => (a[1] !== "—" ? a[1] + " " : "") + a[2]).join("; ") : ""}`,
        tomorrow.length ? `Amanhã: ${tomorrow.map((a) => (a[1] !== "—" ? a[1] + " " : "") + a[2]).join("; ")}` : "Amanhã: nenhum compromisso registrado",
      ].filter((l, n, arr) => !(l === "" && n === 1 && !remote()));
      const d = dlg();
      d.innerHTML = `<form method="dialog" aria-label="Fechar o dia"><h2>Fechar o dia</h2><p class="m sm">Resumo montado só com o que está registrado no app. Nada é enviado: copie e guarde onde preferir.</p><label for="md76txt" class="sr">Resumo do dia</label><textarea id="md76txt" class="in" rows="11" readonly style="margin-top:10px;font-family:inherit"></textarea><div class="acts"><button type="button" class="btn o" data-a="md76copy">Copiar resumo</button><button class="btn">Fechar</button></div></form>`;
      d.querySelector("#md76txt").value = lines.join("\n");
      d.querySelector('[data-a="md76copy"]').onclick = (e) => A.md76copy(null, e.currentTarget);
      d.showModal();
    }

    /* ============ Primeiros passos (modo demonstração e início) ============ */
    const STEP_META = [
      { essential: true, min: 2, after: null, icon: "store" },
      { essential: true, min: 3, after: "produto", icon: "box" },
      { essential: false, min: 2, after: null, icon: "spark" },
      { essential: false, min: 4, after: null, icon: "link" },
      { essential: true, min: 2, after: "venda", icon: "cart" },
    ];
    const stepText = (k, kind) => {
      const svc = kind === "servicos", mix = kind === "misto";
      return [
        ["Conte sobre o seu negócio", "Nome e um contato. É o que aparece para seus clientes."],
        [svc ? "Cadastre seu primeiro serviço" : mix ? "Cadastre seu primeiro produto ou serviço" : "Cadastre seu primeiro produto", svc ? "O que você faz e quanto cobra. Com isso, registrar atendimentos fica rápido." : "Com ele cadastrado, registrar vendas leva segundos."],
        ["Ensine a IA a falar como você", "Escolha o tom das respostas (simpático, direto, formal). Leva 1 minuto."],
        ["Conecte seu WhatsApp", "Opcional agora. Veja em Integrações o que está disponível neste ambiente."],
        [svc ? "Registre seu primeiro atendimento" : "Registre sua primeira venda", "Veja tudo funcionando junto: cliente, valor e pagamento."],
      ][k];
    };
    function setupPanel(compact) {
      const kind = kindOfBusiness(), steps = CK.map((c, k) => ({ k, done: !!S.ck[k], ...STEP_META[k], href: c[2], text: stepText(k, kind) }));
      const ess = steps.filter((s) => s.essential), opt = steps.filter((s) => !s.essential), essDone = ess.filter((s) => s.done).length;
      const next = ess.find((s) => !s.done) || opt.find((s) => !s.done), left = ess.filter((s) => !s.done).reduce((a, s) => a + s.min, 0);
      const pct = Math.round((essDone / ess.length) * 100);
      const item = (s) => `<li class="su-it${s.done ? " ok" : ""}${next && next.k === s.k ? " next" : ""}"><button class="ckb" role="checkbox" aria-checked="${s.done}" aria-label="Marcar como feito: ${esc(s.text[0])}" data-a="ck:${s.k}">${i("check", 16)}</button><span class="su-tx"><b>${esc(s.text[0])}</b><small>${esc(s.text[1])}</small></span><span class="su-min">${s.min} min</span><a class="btn ${next && next.k === s.k ? "" : "o "}sm2" href="#${esc(s.href)}"${s.after ? ` data-after="${s.after}"` : ""}>${s.done ? "Rever" : "Ir"}</a></li>`;
      const head = `<header class="su-hd"><div><span class="su-kick">${esc(S.biz.nome)}</span><h2 id="hj_t">Primeiros passos</h2></div><div class="su-prog"><b>${essDone} de ${ess.length}</b><span>essenciais</span><div class="su-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${ess.length}" aria-valuenow="${essDone}" aria-label="Passos essenciais concluídos"><i style="width:${pct}%"></i></div></div></header>`;
      const kindPick = `<div class="su-kind" role="group" aria-label="O que você oferece?"><span>O que você oferece?</span>${[["produtos", "Produtos"], ["servicos", "Serviços"], ["misto", "Os dois"]].map(([v, l]) => `<button type="button" class="chip${kind === v ? " on" : ""}" aria-pressed="${kind === v}" data-a="md76kind:${v}">${l}</button>`).join("")}</div>`;
      const nextBox = next ? `<p class="su-next">${essDone < ess.length ? `Faltam cerca de <b>${left} min</b> para os passos essenciais.` : "Essenciais concluídos. Os próximos são opcionais."}</p>` : `<p class="su-next">Tudo pronto. Seu espaço está configurado.</p>`;
      const body = `${kindPick}${nextBox}<div class="su-grp"><h3>Essenciais</h3><ol class="su-list">${ess.map(item).join("")}</ol></div><div class="su-grp"><h3>Opcionais <small>faça quando quiser</small></h3><ol class="su-list">${opt.map(item).join("")}</ol></div><p class="md-note">${i("info", 14)} Etapas marcadas por você. Na demonstração o app não verifica o que foi feito.</p>`;
      return `<section class="phj su76${compact ? " compact" : ""}" aria-labelledby="hj_t">${head}${compact ? `<ol class="su-list">${[next].filter(Boolean).map(item).join("")}</ol><a class="lk sm" href="#/bemvindo">Ver todos os passos</a>` : body}</section>`;
    }
    A.md76kind = (v) => { store.set("kind", v); };
    bemvindo = function () {
      return `<div class="pg"><div class="cap">Boas-vindas</div><h1>Vamos começar, ${esc(S.user.nome)}?</h1><p class="m">Três passos essenciais deixam o app pronto para o dia a dia. O resto é opcional.</p>${setupPanel(false)}</div>`;
    };


    /* ============ Configurações e perfil ============ */
    const baseCfgX = typeof cfgX === "function" ? cfgX : null;
    if (baseCfgX) cfgX = function (sec) {
      if (sec !== "seguranca") return baseCfgX.apply(this, arguments);
      const h2 = (t, d) => `<h2 style="font-size:28px">${t}</h2><p class="m">${d}</p>`;
      const sw = (a, t, d, on) => `<div class="sw"><div><b>${t}</b><div class="m sm">${d}</div></div><button class="tg ${on ? "on" : ""}" role="switch" aria-checked="${!!on}" aria-label="${t}" data-a="${a}"></button></div>`;
      const live = remote(), chip = (t, k) => `<span class="cfg-chip" data-k="${k}">${t}</span>`;
      const row2 = (t, d, c) => `<div class="cfg-row"><div><b>${t}</b><small>${d}</small></div>${c}</div>`;
      return { seguranca: `${h2("Segurança e privacidade", "Veja o que está disponível agora. Só aparece como ativo o que realmente funciona.")}
        <div class="cfg-rows">
          ${sw("sg:dados", "Ocultar valores ao abrir", "Mostra ••••• no lugar dos valores até você pedir. Vale só neste navegador.", S.hv)}
          ${row2("Sair dos outros aparelhos", live ? "Encerra as outras sessões abertas com a sua conta. Será pedida a sua senha." : "Disponível apenas com uma conta real conectada.", live ? `<button class="btn o" data-a="sgout">${i("sair")}Sair dos outros</button>` : chip("Indisponível na demonstração", "off"))}
          ${row2("Verificação em duas etapas", "Um código extra ao entrar.", chip("Ainda não disponível", "off"))}
          ${row2("Sair sozinho depois de um tempo parado", "Encerrar a sessão por inatividade.", chip("Ainda não disponível", "off"))}
          ${row2("Baixar meus dados", "Exportar uma cópia das suas informações.", chip("Ainda não disponível", "off"))}
          ${row2("Excluir a conta", "Remoção definitiva dos dados.", chip("Não disponível no app", "off"))}
        </div>
        <p class="m sm" style="margin-top:14px">${i("info", 14)} ${live ? "A sessão é protegida pelo servidor. Itens marcados como indisponíveis ainda não existem nesta versão." : "Demonstração: nenhuma conta real existe aqui, por isso nada de segurança é aplicado de verdade."}</p>` };
    };

    const NAVMAP = [
      ["Meu negócio", [["negocio", "Dados do negócio", "Nome, contato e descrição"], ["equipe", "Equipe", "Quem acessa e com qual permissão"], ["plano", "Plano", "Plano e limites de uso"], ["perfil", "Perfil e cor", "Identidade visual"]]],
      ["Atendimento", [["integracoes", "Integrações", "WhatsApp, Instagram e outros canais"], ["ia", "Perfil da IA", "Tom e regras das respostas"], ["notificacoes", "Notificações", "O que avisar e quando"]]],
      ["Minha conta", [["conta", "Minha conta", "Dados de acesso e negócios"], ["aparencia", "Aparência", "Tema claro, escuro e tamanho"], ["seguranca", "Segurança e privacidade", "Sessões e privacidade"]]],
    ];
    function decorateSettings() {
      const v = document.getElementById("v");
      if (!v || !location.hash.startsWith("#/config")) { dirtyBar(false); return; }
      const g = v.querySelector(".cfg-shell");
      if (!g || g.dataset.v76) return;
      g.dataset.v76 = "1";
      const old = g.firstElementChild, links = [...old.querySelectorAll("a.nv")], used = new Set();
      const nav = document.createElement("nav"); nav.className = "cfg-nav"; nav.setAttribute("aria-label", "Categorias de configuração");
      const mk = (a, desc) => { const c = a.cloneNode(false); c.innerHTML = `<span>${a.textContent}</span>${desc ? `<small>${desc}</small>` : ""}`; return c; };
      NAVMAP.forEach(([title, items]) => {
        const grp = document.createElement("div"); grp.className = "cfg-grp";
        grp.innerHTML = `<div class="cap">${title}</div>`;
        items.forEach(([k, , desc]) => { const a = links.find((l) => l.getAttribute("href") === "#/config/" + k); if (a) { used.add(a); grp.append(mk(a, desc)); } });
        if (grp.children.length > 1) nav.append(grp);
      });
      const rest = links.filter((a) => !used.has(a));
      if (rest.length) { const grp = document.createElement("div"); grp.className = "cfg-grp"; grp.innerHTML = '<div class="cap">Outros</div>'; rest.forEach((a) => grp.append(mk(a, ""))); nav.append(grp); }
      old.replaceWith(nav);
      nav.querySelector("a.on")?.scrollIntoView?.({ block: "nearest", inline: "center" });
      const panel = g.lastElementChild;
      if (panel && !remote()) panel.insertAdjacentHTML("afterbegin", `<p class="cfg-demo">${i("info", 14)} Modo demonstração: o que você ajustar fica só neste navegador.</p>`);
      panel?.querySelectorAll("input:not([type=checkbox]):not([type=radio]),select,textarea").forEach((x) => { x.dataset.v0 = x.value; });
    }
    /* Alterações não salvas */
    let bar = null, saving = null;
    const isDirty = () => !!document.querySelector("#v [data-v0]") && [...document.querySelectorAll("#v [data-v0]")].some((x) => x.value !== x.dataset.v0);
    function dirtyBar(show) {
      if (!show) { bar?.remove(); bar = null; return; }
      if (bar) return;
      bar = document.createElement("div"); bar.className = "cfg-bar"; bar.setAttribute("role", "region"); bar.setAttribute("aria-label", "Alterações não salvas");
      bar.innerHTML = `<span id="cfgmsg" role="status" aria-live="polite"><b>Alterações não salvas</b></span><button type="button" class="btn o" data-cfg="discard">Descartar</button><button type="button" class="btn" data-cfg="save">Salvar alterações</button>`;
      document.body.append(bar);
    }
    const saveBtn = () => document.querySelector('#v button[data-a^="save"]');
    document.addEventListener("input", (e) => { if (e.target.closest?.("#v [data-v0], #v .g2") && e.target.dataset?.v0 !== undefined) dirtyBar(isDirty()); }, true);
    document.addEventListener("change", (e) => { if (e.target.dataset?.v0 !== undefined) dirtyBar(isDirty()); }, true);
    document.addEventListener("click", (e) => {
      const c = e.target.closest?.("[data-cfg]");
      if (c) {
        e.preventDefault();
        if (c.dataset.cfg === "discard") { document.querySelectorAll("#v [data-v0]").forEach((x) => { x.value = x.dataset.v0; }); dirtyBar(false); toast("Alterações descartadas"); }
        else {
          const b = saveBtn(); if (!b) { toast("Use o botão Salvar desta página"); return; }
          const m = document.getElementById("cfgmsg"); if (m) m.innerHTML = "<b>Salvando…</b>"; c.disabled = true;
          clearTimeout(saving); saving = setTimeout(() => { if (bar && m) { m.innerHTML = '<b role="alert">Não foi possível confirmar o salvamento.</b> Confira a mensagem na tela e tente de novo.'; bar.querySelector('[data-cfg="save"]').disabled = false; } }, 6000);
          b.click();
        }
        return;
      }
      const a = e.target.closest?.('a[href^="#/"]');
      if (a && bar && isDirty() && a.getAttribute("href") !== location.hash) {
        e.preventDefault(); e.stopImmediatePropagation();
        const href = a.getAttribute("href"), d = dlg();
        d.innerHTML = `<form method="dialog" aria-label="Alterações não salvas"><h2>Sair sem salvar?</h2><p class="m">Você alterou campos que ainda não foram salvos.</p><div class="acts"><button class="btn o" value="stay" autofocus>Continuar editando</button><button class="btn o" value="drop" type="button" data-x="drop">Descartar e sair</button></div></form>`;
        d.querySelector('[data-x="drop"]').onclick = () => { d.close(); dirtyBar(false); document.querySelectorAll("#v [data-v0]").forEach((x) => { x.value = x.dataset.v0; }); location.hash = href; };
        d.showModal();
      }
    }, true);
    window.addEventListener("beforeunload", (e) => { if (bar && isDirty()) { e.preventDefault(); e.returnValue = ""; } });
    const rr = window.render;
    window.render = function () { dirtyBar(false); clearTimeout(saving); const r = rr.apply(this, arguments); queueMicrotask(decorateSettings); setTimeout(decorateSettings, 80); return r; };
    window.addEventListener("hashchange", () => setTimeout(decorateSettings, 80));
    setTimeout(decorateSettings, 100);

    window.SocialMEIv76 = { version: "7.6", store, collect, remote, canWrite, kindOfBusiness, ui: { pulse, setupPanel, origin, timeToMin, nowMin, plural, enc } }; /* v7.8.2: leitura apenas, usada pela nova tela inicial */
    window.dispatchEvent(new Event("socialmei-v76-ready"));
    if (typeof render === "function") try { render(); } catch (_) {}
  }

  if (ready()) start();
  else { let n = 0; const t = setInterval(() => { if (ready()) { clearInterval(t); start(); } else if (++n > 400) clearInterval(t); }, 25); }
})();
