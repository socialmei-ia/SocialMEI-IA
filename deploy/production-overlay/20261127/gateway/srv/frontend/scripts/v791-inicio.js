/* SocialMEI-IA · v7.9.1 · Início restaurado (composição da v7.4).
   Só a rota #/inicio. Recria o hero da v7.4 (saudação, título, busca, "Para hoje" e três atalhos) com os dados atuais
   e mantém abaixo o "Meu dia" da v7.9 (pendências, agenda, resumo do mês, DAS e Lia), sem alterar regras de negócio.
   Se algo falhar, devolve o Início anterior (v7.8.2). */
(() => {
  "use strict";
  if (window.SocialMEIv791) return;
  const ready = () =>
    window.SocialMEIv782 && typeof inicio === "function" && typeof render === "function" && typeof S === "object" &&
    window.SocialMEIv76 && window.SocialMEIv76.ui;

  function start() {
    const K = window.SocialMEIv76, U = K.ui, { collect, canWrite } = K, { origin } = U;
    const prevInicio = inicio;
    const first = (t) => String(t || "").trim().split(/\s+/)[0] || "";
    const greet = () => { const h = new Date().getHours(); return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite"; };
    const safe = (f, d) => { try { return f(); } catch (_) { return d; } };

    function counts() {
      const wait = safe(() => C.filter((c) => (typeof attn === "function" ? attn(c) : unread(c))), []);
      const pend = safe(() => pendV(), []);
      const low = safe(() => PR.filter((p) => p[9] !== "Serviço" && p[7] <= stMin(p) && (p[7] > 0 || p[4])), []);
      return { wait, pend, low, D: { n: wait.length, v: pend.length, e: low.length } };
    }
    function rows(cn, items) {
      const vis = items.filter((x) => !x.snoozed), has = (k) => (it) => it.kind === k && it.href;
      const out = [], used = new Set();
      const add = (r) => { if (r && out.length < 3) { out.push(r); if (r.key) used.add(r.key); } };
      const c = cn.wait[0];
      if (c) add({ ic: "chat", t: "Responder " + esc(first(c[1])), d: esc(safe(() => prev(c), c[5])), h: "/caixa/" + c[0] });
      const v = vis.find(has("cobranca"));
      if (v) add({ key: v.key, ic: "cart", t: esc(v.title), d: esc(v.detail.split(" · ").slice(0, 2).join(" · ")), h: "/negocio/vendas" });
      else if (cn.pend[0]) { const p = cn.pend[0][0]; add({ ic: "cart", t: "Cobrar " + esc(first(p[2])), d: esc(brl(p[6]) + " · venda " + p[0]), h: "/negocio/vendas" }); }
      const e = vis.find(has("estoque"));
      if (e) add({ key: e.key, ic: "store", t: esc(e.title), d: esc(e.detail.replace(/ \(mínimo \d+\)/, "")), h: e.href });
      vis.filter((x) => x.href && !used.has(x.key) && !["conversa", "cobranca", "estoque"].includes(x.kind)).forEach((x) => add({ key: x.key, ic: x.icon || "cal", t: esc(x.title), d: esc(x.detail), h: x.href }));
      return out;
    }
    const org = () => { const [ot, ol] = origin(); return `<span class="cxl-st" role="status" tabindex="0" title="${ot === "demo" ? "Conversas, clientes e vendas desta tela são exemplos para avaliação." : "Informações registradas no seu negócio."}"><span class="dot ${ot === "demo" ? "y" : "g"}" style="margin:0"></span>${esc(ol)}</span>`; };

    inicio = function () {
      try {
        if (homeStage() !== "operacao") return prevInicio.apply(this, arguments);
        const cn = counts(), D = cn.D, items = collect(), r = rows(cn, items), dt = safe(() => diaTxt(D), "");
        const below = new DOMParser().parseFromString(prevInicio.apply(this, arguments), "text/html").querySelector(".hm-grid");
        if (below) { const h = below.querySelector("#hm_f"); if (h && h.firstChild) h.firstChild.textContent = "Meu dia"; }
        const sale = canWrite() ? ' data-after="venda"' : "";
        const hoje = `<section class="phj" aria-labelledby="hj_t"><h2 id="hj_t">Para hoje</h2>${r.length ? r.map((t) => `<a href="#${t.h}"><span class="ti" aria-hidden="true">${i(t.ic, 18)}</span><span class="tx"><b>${t.t}</b><span>${t.d}</span></span>${i("arrow", 18)}</a>`).join("") : `<div class="ok">${i("check", 18)}Tudo em dia por aqui. Bom trabalho!</div>`}</section>`;
        const hero = `<div class="hero"><div class="hl" style="min-width:0"><span class="bar"></span><p class="m" style="font-size:22px">${greet()}, ${esc(S.user.nome)}.</p><h1>Seu negócio,<br><b>mais organizado.</b></h1><p class="m hq" style="font-size:18px;margin-top:10px">${dt || "Por onde começamos?"}</p>${org()}<div class="cmd"><div class="sb">${i("search", 22)}<input id="cmd" role="combobox" aria-expanded="false" aria-controls="cmdl" aria-autocomplete="list" placeholder="Pesquise uma tela ou ação…" autocomplete="off" aria-label="Pesquise uma tela ou ação"><kbd>Ctrl</kbd><kbd>K</kbd></div><ul id="cmdl" class="cmdl" role="listbox" aria-label="Sugestões"></ul></div>${hoje}</div><div class="cs"><a class="hc" href="#/caixa"><span class="ic">${i("chat", 50)}</span><span class="hx"><span class="hn">Atender clientes</span><small class="hs">${D.n ? `<b>${D.n}</b> esperando resposta` : "Nenhuma esperando agora"}</small></span>${i("arrow", 24)}</a><a class="hc" href="#/negocio/vendas"${sale}><span class="ic">${i("cart", 50)}</span><span class="hx"><span class="hn">Registrar uma venda</span><small class="hs">${D.v ? `<b>${D.v}</b> ${D.v > 1 ? "cobranças pendentes" : "cobrança pendente"}` : "Anote o pedido e o pagamento"}</small></span>${i("arrow", 24)}</a><a class="hc y" href="#/divul"><span class="ic">${i("mega", 50)}</span><span class="hx"><span class="hn">Preparar divulgação</span><small class="hs">Textos e ideias para postar</small></span>${i("arrow", 24)}</a></div></div>`;
        return hero + (below ? `<section class="v791-more" aria-label="Meu dia"><div class="hm">${below.outerHTML}</div></section>` : "");
      } catch (e) { console.warn("Início v7.9.1 indisponível; exibindo o início anterior.", e); return prevInicio.apply(this, arguments); }
    };
    window.SocialMEIv791 = { version: "7.9.1" };
    try { render(); } catch (_) {}
  }
  if (ready()) start();
  else { let n = 0; const t = setInterval(() => { if (ready()) { clearInterval(t); start(); } else if (++n > 600) clearInterval(t); }, 25); }
})();
