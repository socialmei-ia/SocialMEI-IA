/* SocialMEI-IA v7.6 · Relatórios de acompanhamento (perfil report_viewer).
   Usa apenas GET /reporting/overview?days=N, /reporting/overview.csv, /auth/workspaces e /auth/workspaces/switch.
   Comparação de períodos: diferença entre as consultas de 2N e N dias, sempre rotulada como calculada. */
(() => {
  "use strict";
  const auth = window.SocialMEIAuth;
  const $ = (id) => document.getElementById(id);
  const el = (t, c, txt) => { const n = document.createElement(t); if (c) n.className = c; if (txt !== undefined) n.textContent = String(txt); return n; };
  const brl = (n) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(n);
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
  const pct = (cur, prev) => (prev ? Math.round(((cur - prev) / Math.abs(prev)) * 100) : null);
  const status = $("status"), say = (m, k) => { status.textContent = m; status.dataset.k = k || ""; };
  const state = { days: 30, compare: false, seq: 0 };
  const lc = (s) => String(s || "").toLowerCase();

  /* tema */
  const themeKey = "smei-v76-report-theme";
  const applyTheme = (t) => { if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; const dark = (t || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark"; $("theme").setAttribute("aria-pressed", String(dark)); $("theme").textContent = dark ? "Tema claro" : "Tema escuro"; };
  try { applyTheme(localStorage.getItem(themeKey)); } catch (_) { applyTheme(null); }
  $("theme").onclick = () => { const dark = $("theme").getAttribute("aria-pressed") === "true", t = dark ? "light" : "dark"; applyTheme(t); try { localStorage.setItem(themeKey, t); } catch (_) {} };

  /* dados */
  function valid(r) {
    return r && r.totals && typeof r.totals === "object" && r.sales_by_status && typeof r.sales_by_status === "object" && Array.isArray(r.finance_by_type_and_status);
  }
  function agg(r) {
    const sales = Object.entries(r.sales_by_status).map(([k, x]) => ({ k, q: num(x?.quantidade), v: num(x?.valor) }));
    const fin = r.finance_by_type_and_status.map((x) => ({ tipo: lc(x.tipo), status: lc(x.status), q: num(x.quantidade), v: num(x.valor) }));
    const sum = (a, f) => a.filter(f).reduce((s, x) => s + x.v, 0);
    const okSale = (x) => !/cancel/.test(lc(x.k));
    return {
      t: { clientes: num(r.totals.clientes), itens: num(r.totals.itens_ativos), baixo: num(r.totals.estoque_baixo) },
      sales, fin,
      salesN: sales.filter(okSale).reduce((s, x) => s + x.q, 0), salesV: sum(sales, okSale),
      pendV: sum(sales, (x) => /pend/.test(lc(x.k))), pendN: sales.filter((x) => /pend/.test(lc(x.k))).reduce((s, x) => s + x.q, 0),
      rec: sum(fin, (x) => x.tipo.startsWith("receita") && x.status === "pago"), des: sum(fin, (x) => x.tipo.startsWith("despesa") && x.status === "pago"),
    };
  }
  const diff = (big, small) => { // período anterior = (2N dias) − (N dias), somente totais acumulados
    const m = (a, b, key) => { const o = {}; for (const x of a) o[key(x)] = { ...x }; for (const y of b) { const k = key(y); o[k] = o[k] || { ...y, q: 0, v: 0 }; o[k].q = Math.max(0, (o[k].q || 0) - y.q); o[k].v = Math.max(0, (o[k].v || 0) - y.v); } return Object.values(o); };
    const sales = m(big.sales, small.sales, (x) => x.k), fin = m(big.fin, small.fin, (x) => x.tipo + "|" + x.status);
    const sum = (a, f) => a.filter(f).reduce((s, x) => s + x.v, 0);
    return { sales, fin, salesN: sales.filter((x) => !/cancel/.test(lc(x.k))).reduce((s, x) => s + x.q, 0), salesV: sum(sales, (x) => !/cancel/.test(lc(x.k))), rec: sum(fin, (x) => x.tipo.startsWith("receita") && x.status === "pago"), des: sum(fin, (x) => x.tipo.startsWith("despesa") && x.status === "pago") };
  };
  const get = (days) => auth.request("/reporting/overview?days=" + encodeURIComponent(days));

  /* apresentação */
  function kpi(label, value, sub, cls) { const k = el("div", "kpi" + (cls ? " " + cls : "")); k.append(el("small", "", label), el("span", "v", value)); if (sub) { const d = el("span", "d" + (sub.cls ? " " + sub.cls : ""), sub.text); k.append(d); } return k; }
  const delta = (cur, prev, prevOk, money) => { if (!prevOk) return null; const p = pct(cur, prev); if (p === null) return { text: prev === 0 && cur === 0 ? "igual ao anterior" : "sem base no período anterior" }; return { text: `${p > 0 ? "▲" : p < 0 ? "▼" : "="} ${Math.abs(p)}% vs. anterior (${money ? brl(prev) : prev})`, cls: p > 0 ? "up" : p < 0 ? "down" : "" }; };
  function barsCard(title, desc, rows, prevRows, fmt) {
    const c = el("section", "card"); c.append(el("h2", "", title), el("p", "", desc));
    const max = Math.max(1, ...rows.map((r) => r.v), ...(prevRows || []).map((r) => r.v));
    const list = el("div", "bars"); list.setAttribute("role", "list");
    if (!rows.length) { c.append(el("div", "empty", "Nenhum movimento neste período.")); return c; }
    rows.forEach((r) => {
      const prev = prevRows?.find((p) => p.label === r.label);
      const row = el("div", "br"); row.setAttribute("role", "listitem");
      const t = el("div", "t"), i = el("i"); i.style.width = Math.max(2, (r.v / max) * 100) + "%"; t.append(i);
      if (prevRows) { const j = el("i", "prev"); j.style.width = Math.max(2, ((prev?.v || 0) / max) * 100) + "%"; t.append(j); }
      row.append(el("span", "", r.label), t, el("b", "", fmt(r)));
      row.setAttribute("aria-label", `${r.label}: ${fmt(r)}${prevRows ? `; período anterior ${prev ? fmt(prev) : "sem registro"}` : ""}`);
      list.append(row);
    });
    c.append(list);
    if (prevRows) { const l = el("div", "legend"); l.append(el("span", "", "Período atual"), el("span", "p", "Período anterior (calculado)")); c.append(l); }
    return c;
  }
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  function table(caption, head, rows) {
    const wrap = el("div", "tw"), t = el("table"); t.append(el("caption", "sr", caption));
    const th = el("tr"); head.forEach((h, i) => { const c = el("th", i ? "n" : "", h); c.scope = "col"; th.append(c); }); const hd = el("thead"); hd.append(th); t.append(hd);
    const b = el("tbody"); rows.forEach((r) => { const tr = el("tr"); r.forEach((c, i) => tr.append(el("td", i ? "n" : "", c))); b.append(tr); }); t.append(b); wrap.append(t); return wrap;
  }
  function render(cur, prev, cmpErr) {
    const a = agg(cur), ok = !!prev, pv = prev;
    const ov = $("overview"); ov.replaceChildren(); ov.setAttribute("aria-busy", "false");
    ov.append(
      kpi("Vendas registradas", String(a.salesN), delta(a.salesN, pv?.salesN, ok) || { text: "no período" }),
      kpi("Valor vendido", brl(a.salesV), delta(a.salesV, pv?.salesV, ok, true) || { text: "soma das vendas, exceto canceladas" }),
      kpi("A receber (vendas pendentes)", brl(a.pendV), { text: `${a.pendN} ${a.pendN === 1 ? "venda" : "vendas"}` }, a.pendV > 0 ? "warn" : ""),
      kpi("Receitas pagas", brl(a.rec), delta(a.rec, pv?.rec, ok, true) || { text: "lançamentos financeiros pagos" }),
      kpi("Despesas pagas", brl(a.des), delta(a.des, pv?.des, ok, true) || { text: "lançamentos financeiros pagos" }),
      kpi("Resultado registrado", brl(a.rec - a.des), delta(a.rec - a.des, pv ? pv.rec - pv.des : 0, ok, true) || { text: "receitas pagas − despesas pagas" }),
      kpi("Clientes", String(a.t.clientes), { text: "cadastrados agora" }),
      kpi("Itens ativos", String(a.t.itens), { text: "à venda agora" }),
      kpi("Estoque baixo", String(a.t.baixo), { text: a.t.baixo ? "itens para repor" : "nenhum item em alerta" }, a.t.baixo ? "warn" : ""),
    );
    const ins = el("ul", "insight"), L = (t) => ins.append(el("li", "", t));
    if (!a.salesN && !a.fin.length) L("Não há vendas nem lançamentos neste período. Tente um período maior.");
    else {
      L(`Nos últimos ${state.days} dias foram registradas ${a.salesN} ${a.salesN === 1 ? "venda" : "vendas"}, somando ${brl(a.salesV)}.`);
      if (a.pendV > 0) L(`${brl(a.pendV)} ainda estão pendentes de recebimento.`);
      if (a.fin.length) L(a.rec >= a.des ? `As receitas pagas (${brl(a.rec)}) cobriram as despesas pagas (${brl(a.des)}).` : `As despesas pagas (${brl(a.des)}) superaram as receitas pagas (${brl(a.rec)}).`);
      if (a.t.baixo) L(`${a.t.baixo} ${a.t.baixo === 1 ? "item está" : "itens estão"} com estoque baixo.`);
      if (cmpErr) L("A comparação com o período anterior não está disponível agora. Os valores acima são do período atual.");
    }
    const insBox = $("insights"); insBox.replaceChildren(); insBox.append(ins);
    const charts = $("charts"); charts.replaceChildren();
    const sRows = a.sales.map((x) => ({ label: cap(x.k), v: x.v, q: x.q })), sPrev = pv ? pv.sales.map((x) => ({ label: cap(x.k), v: x.v, q: x.q })) : null;
    charts.append(barsCard("Vendas por situação", "Valor somado de cada situação no período.", sRows, sPrev, (r) => `${brl(r.v)} · ${r.q}`));
    const fRows = a.fin.map((x) => ({ label: `${cap(x.tipo)} ${x.status}`, v: x.v, q: x.q })), fPrev = pv ? pv.fin.map((x) => ({ label: `${cap(x.tipo)} ${x.status}`, v: x.v, q: x.q })) : null;
    charts.append(barsCard("Financeiro por tipo e situação", "Receitas e despesas, pagas ou pendentes.", fRows, fPrev, (r) => `${brl(r.v)} · ${r.q}`));
    const tb = $("tables"); tb.replaceChildren(); tb.hidden = !(a.sales.length || a.fin.length);
    if (!tb.hidden) {
      tb.append(el("h2", "", "Tabela de valores"), el("p", "", "Os mesmos números dos gráficos, em formato de tabela."));
      tb.append(table("Vendas por situação", ["Vendas", "Quantidade", "Valor"], a.sales.map((x) => [cap(x.k), x.q, brl(x.v)])));
      if (a.fin.length) tb.append(table("Financeiro por tipo e situação", ["Financeiro", "Quantidade", "Valor"], a.fin.map((x) => [`${cap(x.tipo)} · ${x.status}`, x.q, brl(x.v)])));
    }
    const att = cur.attendance; // indicador opcional: só aparece se o servidor o enviar
    if (att === null || att === undefined) { const n = el("p", "meta", cur.attendance_description || "Indicadores de atendimento ainda não estão disponíveis neste ambiente."); n.style.marginTop = "10px"; charts.after(n); n.id = "attnote"; }
    $("printhead").textContent = `${auth.current.negocio.nome} · últimos ${state.days} dias · consultado em ${new Date().toLocaleString("pt-BR")}`;
    const hora = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    say(`Dados reais do negócio “${auth.current.negocio.nome}”, consultados às ${hora}. Valores agregados, sem dados individuais.${ok ? " Comparação calculada." : ""}`);
  }
  function loading() { $("error").replaceChildren(); $("attnote")?.remove(); const ov = $("overview"); ov.replaceChildren(); ov.setAttribute("aria-busy", "true"); for (let i = 0; i < 6; i++) ov.append(el("div", "sk")); $("insights").replaceChildren(); $("charts").replaceChildren(); $("tables").hidden = true; say("Consultando dados…"); }
  function failure(e, retry) {
    $("overview").replaceChildren(); $("overview").setAttribute("aria-busy", "false"); $("insights").replaceChildren(); $("charts").replaceChildren(); $("tables").hidden = true;
    const b = el("div", "banner"); b.setAttribute("role", "alert"); b.append(el("span", "", (e?.message || "Não foi possível carregar o relatório.") + " Os dados exibidos antes não foram mantidos."));
    const r = el("button", "", "Tentar de novo"); r.type = "button"; r.onclick = retry; b.append(r); $("error").replaceChildren(b); say("Falha ao consultar.", "err"); r.focus();
  }
  async function load() {
    const id = ++state.seq, ws = auth.current?.negocio?.id, days = state.days;
    loading();
    try {
      const cur = await get(days);
      if (id !== state.seq || ws !== auth.current?.negocio?.id) return; // resposta antiga: descartada
      if (!valid(cur)) throw new Error("O servidor devolveu uma resposta inesperada para este relatório.");
      let prev = null, cmpErr = false;
      if (state.compare) {
        try {
          const big = await get(days * 2);
          if (id !== state.seq) return;
          if (!valid(big)) throw 0;
          prev = diff(agg(big), agg(cur));
        } catch (_) { if (id !== state.seq) return; cmpErr = true; }
      }
      render(cur, prev, cmpErr);
    } catch (e) { if (id === state.seq) failure(e, load); }
  }

  async function boot() {
    await auth.ready;
    // Se o navegador acabou de associar a sessão a este negócio, o auth-store recarrega a página: aguardar evita redirecionar antes.
    if (auth.remote && !auth.current) await new Promise((r) => setTimeout(r, 700));
    const account = auth.current;
    if (!auth.remote || !account) { location.replace("entrada.html#/entrar"); return; }
    if (account.papel !== "report_viewer") { location.replace("socialmei-app.html#/relatorios"); return; }
    $("exit").onclick = async () => { try { await auth.logout(); } catch (e) { say(e.message || "Não foi possível sair.", "err"); } };
    try {
      const data = await auth.request("/auth/workspaces"), sel = $("workspace");
      for (const row of data.items) { const o = el("option", "", row.nome); o.value = String(row.id); o.selected = row.id === data.active_workspace_id; sel.append(o); }
      $("wsinfo").textContent = data.items.length > 1 ? "Você acompanha mais de um negócio autorizado." : "Você acompanha este negócio.";
      const sync = () => { $("change").disabled = Number(sel.value) === data.active_workspace_id; };
      sel.onchange = sync; sync();
      $("change").onclick = async () => {
        const b = $("change"); b.disabled = true; sel.disabled = true; say("Alternando de negócio…");
        state.seq++; // invalida qualquer consulta em andamento do negócio anterior
        try {
          const r = await auth.request("/auth/workspaces/switch", "POST", { workspace_id: Number(sel.value) });
          location.replace(r.papel === "report_viewer" ? "relatorios-leitura.html" : "socialmei-app.html#/relatorios");
        } catch (e) { say(e.message || "Não foi possível trocar de negócio.", "err"); sel.disabled = false; sync(); load(); }
      };
    } catch (e) { $("wsinfo").textContent = "Não foi possível listar os negócios autorizados."; }
    document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => { state.days = Number(b.dataset.days); document.querySelectorAll(".seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); load(); }));
    $("compare").onchange = (e) => { state.compare = e.target.checked; load(); };
    $("refresh").onclick = load;
    $("print").onclick = () => window.print();
    $("csv").onclick = async () => {
      const b = $("csv"); b.disabled = true;
      try {
        const r = await fetch("/api/v1/reporting/overview.csv?days=" + encodeURIComponent(state.days), { credentials: "same-origin", cache: "no-store" });
        if (!r.ok) throw Error("Exportação não autorizada ou indisponível.");
        const url = URL.createObjectURL(await r.blob()), a = el("a"); a.href = url; a.download = "socialmei-relatorio.csv"; document.body.append(a); a.click();
        setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 30000); say("CSV exportado (período atual).");
      } catch (e) { say(e.message, "err"); } finally { b.disabled = false; }
    };
    await load();
  }
  boot().catch(() => say("Não foi possível carregar o relatório.", "err"));
})();
