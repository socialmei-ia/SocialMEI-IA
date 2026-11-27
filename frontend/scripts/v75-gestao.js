/* SocialMEI-IA · v7.5 · Gestão comercial e financeira.
   Reescreve só a APRESENTAÇÃO de Vendas, Produtos e Financeiro e acrescenta pequenos recursos de interface.
   - Os dados continuam vindo dos mesmos arrays (V, PR, F) que o app e o v22-backend preenchem; nada de endpoint novo.
   - Toda gravação segue pelas ações existentes (A.vt, A.fx, openAction, editAction): no modo remoto o resultado só
     aparece depois da resposta do servidor. Nada aqui confirma pagamento por conta própria.
   - Dados de demonstração continuam identificados como tal pelo cabeçalho do Negócio. */
(() => {
  "use strict";
  if (window.SocialMEIGestao) return;
  const ready = () => typeof vendas === "function" && typeof produtos === "function" && typeof financeiro === "function" && typeof A === "object" && typeof S === "object";
  function start() {

  /* ---------- utilidades ---------- */
  const host = () => window.SocialMEIV22;
  const remote = () => !!host()?.remote;
  const canWrite = () => !remote() || window.SocialMEIAuth?.current?.papel !== "viewer";
  const DAY = 864e5;
  const G = { vper: "Tudo", ptype: "Todos", lastV: [], lastP: [], lastF: [], busy: new Set() };
  const today0 = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime(); };
  const dayStart = (ms) => { const d = new Date(ms); d.setHours(0, 0, 0, 0); return d.getTime(); };
  const ageDays = (txt) => { const t = pdt(txt); return t > 0 ? Math.round((today0() - dayStart(t)) / DAY) : null; };
  const rel = (n) => (n == null ? "" : n <= 0 ? "hoje" : n === 1 ? "ontem" : `há ${n} dias`);
  const idn = (v) => parseInt(String(v[0]).replace(/\D/g, ""), 10) || 0;
  const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
  const fmtIn = (n) => n.toFixed(2).replace(".", ",");
  const kpi = (label, value, sub, tone, extra) =>
    `<div class="g75-k"${tone ? ` data-tone="${tone}"` : ""}><span>${label}</span><b>${value}</b>${sub ? `<small>${sub}</small>` : ""}${extra || ""}</div>`;
  const split = (a, b, label) => {
    const t = a + b, pa = t ? Math.round((a / t) * 100) : 0;
    return `<div class="g75-split" role="img" aria-label="${label}"><i style="width:${pa}%"></i><i class="b" style="width:${t ? 100 - pa : 0}%"></i></div>`;
  };
  const roNote = () => (canWrite() ? "" : `<style>.nhfab{display:none!important}</style><p class="g75-ro" role="status">Seu acesso é só de leitura: você pode consultar, mas não registrar nem alterar.</p>`);
  const clearEmpty = (title, body, btn) => `<div class="empty g75-empty" style="display:block"><b>${title}</b>${body}${btn || ""}</div>`;

  function csv(rows, name) {
    const q = (s) => '"' + (/^[\s]*[=+\-@]/.test(String(s)) ? "'" : "") + String(s).replace(/"/g, '""') + '"';
    if (rows.length < 2) return toast("Nada para exportar nesta visão");
    const blob = new Blob(["\ufeff" + rows.map((r) => r.map(q).join(";")).join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
    toast(`Arquivo CSV gerado (${rows.length - 1} linhas)`);
  }

  /* ---------- VENDAS ---------- */
  const PERV = { Tudo: 0, "7 dias": 7, "30 dias": 30 };
  const VSORT = {
    "Mais recentes": (a, b) => pdt(b.v[4]) - pdt(a.v[4]) || idn(b.v) - idn(a.v),
    "Maior valor": (a, b) => b.v[6] - a.v[6],
    Cliente: (a, b) => String(a.v[2]).localeCompare(String(b.v[2]), "pt-BR"),
    "Pendentes primeiro": (a, b) => a.paid - b.paid || pdt(a.v[4]) - pdt(b.v[4]),
  };
  function vendasView() {
    const w = canWrite(), rem = remote();
    const vf = ["Todas", "Pagas", "Pendentes"].includes(S.vf) ? S.vf : "Todas";
    const vso = VSORT[S.vso] ? S.vso : "Mais recentes";
    const days = PERV[G.vper] || 0;
    const rows = V.map((v, k) => ({ v, k, age: ageDays(v[4]), paid: v[5] === "Pago" }));
    const base = rows.filter((r) => !days || r.age == null || r.age < days);
    const cn = (k) => base.filter((r) => k === "Todas" || (k === "Pagas" ? r.paid : !r.paid)).length;
    const f = base.filter((r) => vf === "Todas" || (vf === "Pagas" ? r.paid : !r.paid)).sort(VSORT[vso]);
    G.lastV = f.map((r) => r.v);
    const tot = sum(base, (r) => r.v[6]), paidT = sum(base.filter((r) => r.paid), (r) => r.v[6]), penT = tot - paidT;
    const np = base.filter((r) => !r.paid).length;
    const oldest = Math.max(-1, ...base.filter((r) => !r.paid && r.age != null).map((r) => r.age));
    const avg = base.length ? tot / base.length : 0;
    const kpis = `<div class="g75-kpis">${kpi("Total registrado", brl(tot), plural(base.length, "venda", "vendas") + (days ? ` em ${G.vper}` : ""), "", split(paidT, penT, `Recebido ${brl(paidT)} e a receber ${brl(penT)}`))}${kpi("Pago", brl(paidT), plural(base.length - np, "venda paga", "vendas pagas"), "ok")}${kpi("Pendente", brl(penT), np ? plural(np, "venda aguardando", "vendas aguardando") + (oldest > 0 ? ` · a mais antiga ${rel(oldest)}` : "") : "Nada pendente", np ? "warn" : "")}${kpi("Ticket médio", brl(avg), "Total ÷ vendas registradas")}</div>`;
    const nudge = np && vf !== "Pendentes"
      ? `<div class="g75-nudge" role="status">${i("info", 18)}<span><b>${plural(np, "venda pendente", "vendas pendentes")}</b> somam ${brl(penT)}${oldest > 0 ? `; a mais antiga está ${rel(oldest)}` : ""}.</span><button class="lk" data-a="vf:Pendentes">Ver pendentes</button></div>`
      : "";
    const chip = (key, val, label, on) => `<button class="chip sm3${on ? " on" : ""}" data-a="${key}:${val}" aria-pressed="${on}">${label}</button>`;
    const toolbar = `<div class="row sp wr g75-tb">${search(".tb tr:has(td)", "Buscar cliente ou número")}<div class="seg" role="group" aria-label="Filtrar vendas">${["Todas", "Pagas", "Pendentes"].map((k) => `<button class="${vf === k ? "on" : ""}" data-a="vf:${k}" aria-pressed="${vf === k}" style="all:unset;cursor:pointer;padding:9px 16px;${vf === k ? "background:var(--pl);font-weight:700;color:var(--p)" : ""}">${k} <span class="n">${cn(k)}</span></button>`).join("")}</div></div>
<div class="row wr stp g75-chips" role="group" aria-label="Período e ordem das vendas"><span class="m sm">Período:</span>${Object.keys(PERV).map((k) => chip("g75", "vper=" + k, k, G.vper === k)).join("")}<span class="m sm" style="margin-left:auto">Ordenar:</span>${Object.keys(VSORT).map((k) => chip("vso", k, k, vso === k)).join("")}</div>`;
    const table = f.length
      ? `<table class="tb h rc rtv g75-vt"><tr><th>Venda</th><th>Cliente</th><th>Data</th><th>Pagamento</th><th class="r">Valor</th><th></th></tr>${f.map((r) => {
          const v = r.v, late = !r.paid && r.age != null && r.age >= 7;
          const ageChip = !r.paid && r.age != null && r.age > 0 ? `<span class="g75-age${late ? " late" : ""}">${late ? "Atrasada · " : ""}${rel(r.age)}</span>` : "";
          const pend = !r.paid;
          const actions = w
            ? `${pend ? `<button class="lk sm cb" data-a="cobrar:${r.k}" title="Mostra a mensagem de cobrança para copiar. Não registra pagamento.">${i("pix", 14)}Preparar cobrança</button>` : ""}${pend && G.busy.has("vt:" + v[0]) ? `<button class="lk sm g75-pay" data-a="vt:${r.k}" disabled aria-live="polite">Aguardando o servidor…</button>` : `<button class="lk sm${pend ? " g75-pay" : ""}" data-a="vt:${r.k}" ${pend ? 'data-pay="1" data-armtext="Confirmar ' + brl(v[6]) + '?"' : ""} ${!pend && rem ? "hidden" : ""}>${pend ? "Confirmar pagamento" : "Voltar a pendente"}</button>`}`
            : `<button class="lk sm" data-a="vt:${r.k}" hidden></button>`;
          return `<tr class="${pend ? "hl" : ""}" data-sx="${esc(v[1] + " " + v[5])}"><td><b>${esc(v[0])}</b><div class="m sm">${esc(v[1])}</div></td><td><span class="av" style="width:36px;height:36px;background:var(--h2);margin-right:10px;font-size:12px" aria-hidden="true">${esc(v[3])}</span>${esc(v[2] || "Cliente avulso")}</td><td class="vd">${esc(v[4])}<div class="m sm">${rel(r.age)}</div></td><td>${pay(v[5])}${ageChip}</td><td class="r">${brl(v[6])}</td><td><div class="acr">${actions}</div></td></tr>`;
        }).join("")}</table><div class="empty">Nenhuma venda encontrada para essa busca.</div><p class="m sm" style="margin-top:14px">${cnt("Mostrando {n} de {t} vendas", f.length, V.length)}</p>`
      : V.length
        ? clearEmpty("Nenhuma venda nesta visão", "Mude o filtro ou o período para continuar.<br>", `<button class="btn o" data-a="g75:vclr" style="margin-top:12px">Limpar filtros</button>`)
        : clearEmpty("Nenhuma venda registrada ainda", w ? "Registre a primeira venda para acompanhar o que entrou e o que falta receber.<br>" : "Quando houver vendas registradas, elas aparecem aqui.", w ? `<button class="btn" data-a="novo:venda" style="margin-top:12px">${i("plus")}Registrar venda</button>` : "");
    const note = rem
      ? "Pagamento só é marcado como pago depois da resposta do servidor."
      : "Demonstração: o registro e a baixa de pagamento acontecem só neste navegador.";
    return `<div class="pg g75" style="padding-top:18px"><div class="row sp wr"><div><h1 style="font-size:30px">Vendas</h1><p class="m">Registre, cobre e acompanhe o que já foi pago e o que falta receber.</p></div><div class="row wr"><button class="btn o" data-a="g75:vexp">${i("dl", 16)}Exportar visão</button></div></div>${roNote()}${kpis}${nudge}${toolbar}${table}<p class="m sm g75-foot">${note} <span class="g75-hint">Atalhos: <kbd>N</kbd> nova venda · <kbd>/</kbd> buscar</span></p></div>`;
  }

  /* ---------- PRODUTOS E SERVIÇOS ---------- */
  const isSvc = (p) => p[9] === "Serviço";
  const isOut = (p) => !isSvc(p) && (p[7] || 0) <= 0;
  const isLow = (p) => !isSvc(p) && stLow(p);
  const PFL = {
    Todos: () => 1,
    "Disponíveis": (p) => p[4],
    Indisponíveis: (p) => !p[4],
    Esgotados: (p) => isOut(p),
    "Estoque baixo": (p) => isLow(p),
  };
  const marginOf = (p) => (p[6] > 0 && p[3] > 0 ? (p[3] - p[6]) / p[3] : -Infinity);
  const PSORT = {
    Nome: (a, b) => a[0].localeCompare(b[0], "pt-BR"),
    "Menor preço": (a, b) => a[3] - b[3],
    "Maior preço": (a, b) => b[3] - a[3],
    "Menor estoque": (a, b) => (isSvc(a) ? 1e9 : a[7] || 0) - (isSvc(b) ? 1e9 : b[7] || 0),
    "Maior margem": (a, b) => marginOf(b) - marginOf(a),
  };
  const stockUi = (p) => {
    if (isSvc(p)) return `<span class="g75-nostock">Sem controle de estoque</span>`;
    const n = p[7] || 0, min = stMin(p), scale = Math.max(n, min * 2, 1);
    const st = n <= 0 ? "out" : n <= min ? "low" : "ok";
    const label = n <= 0 ? "Esgotado" : st === "low" ? `Baixo · ${n} un.` : `${n} un.`;
    return `<div class="g75-stk" data-s="${st}"><span class="g75-stl">${label}</span><div class="g75-meter" role="img" aria-label="Estoque: ${n} unidades; aviso quando restar ${min} ou menos"><i style="width:${Math.min(100, (n / scale) * 100)}%"></i><u style="left:${Math.min(100, (min / scale) * 100)}%"></u></div></div>`;
  };
  const salesOf = (p) => {
    const mine = V.filter((v) => String(v[1]).split(" · ")[0] === p[0]);
    const qtyOf = (v) => parseInt(String(v[1]).split(" · ")[1], 10) || 1;
    return { mine, units: sum(mine, qtyOf), paid: sum(mine.filter((v) => v[5] === "Pago"), (v) => v[6]), pend: sum(mine.filter((v) => v[5] !== "Pago"), (v) => v[6]) };
  };
  function produtosView() {
    const w = canWrite();
    const pst = PFL[S.pst] ? S.pst : "Todos", pso = PSORT[S.pso] ? S.pso : "Nome";
    const ptype = ["Todos", "Produtos", "Serviços"].includes(G.ptype) ? G.ptype : "Todos";
    const tf = (p) => ptype === "Todos" || (ptype === "Serviços" ? isSvc(p) : !isSvc(p));
    const cats = ["Todas", ...new Set(PR.map((p) => p[2]).filter(Boolean))];
    const pcat = cats.includes(S.pcat) ? S.pcat : "Todas";
    const PF = PR.map((x, k) => [x, k]).filter(([x]) => tf(x) && (pcat === "Todas" || x[2] === pcat) && PFL[pst](x)).sort((a, b) => PSORT[pso](a[0], b[0]));
    G.lastP = PF.map(([x]) => x);
    const phys = PR.filter((p) => !isSvc(p)), svcs = PR.filter(isSvc);
    const repor = phys.filter((p) => p[4] && (isOut(p) || isLow(p)));
    const costed = phys.filter((p) => p[6] > 0 && (p[7] || 0) > 0);
    const stockVal = sum(costed, (p) => p[6] * p[7]);
    const kpis = `<div class="g75-kpis">${kpi("Itens cadastrados", String(PR.length), `${plural(phys.length, "produto", "produtos")} · ${plural(svcs.length, "serviço", "serviços")}`)}${kpi("Disponíveis", String(PR.filter((p) => p[4]).length), plural(PR.filter((p) => !p[4]).length, "indisponível", "indisponíveis"), "")}${kpi("Para repor", String(repor.length), repor.length ? `${repor.filter(isOut).length} esgotados · ${repor.filter(isLow).length} com estoque baixo` : "Nada pedindo atenção", repor.length ? "warn" : "ok")}${kpi("Estoque ao custo", costed.length ? brl(stockVal) : "—", costed.length ? `Só itens com custo informado (${costed.length} de ${phys.length})` : "Informe o custo dos produtos para ver")}</div>`;
    const restock = repor.length
      ? `<div class="g75-nudge" role="status">${i("info", 18)}<span><b>${plural(repor.length, "item pede", "itens pedem")} reposição:</b> ${repor.slice(0, 3).map((p) => esc(p[0])).join(", ")}${repor.length > 3 ? ` e mais ${repor.length - 3}` : ""}.</span><button class="lk" data-a="g75:restock">${i("copy", 14)}Copiar lista de reposição</button></div>`
      : "";
    const chip = (key, val, label, on, n) => `<button class="chip sm3${on ? " on" : ""}" data-a="${key}:${val}" aria-pressed="${on}">${label}${n == null ? "" : ` <span class="n">${n}</span>`}</button>`;
    const p = PR[S.prod], im = S.img[S.prod];
    let panel = `<p class="m" style="padding:40px 0;text-align:center">Escolha um item para ver os detalhes.</p>`;
    if (p) {
      const sv = salesOf(p);
      const last = sv.mine.slice(0, 3).map((v) => `<li><span>${esc(v[0])} · ${esc(v[2] || "Cliente avulso")}</span><span>${pay(v[5])} ${brl(v[6])}</span></li>`).join("");
      panel = `<div class="row sp"><h2 style="font-size:26px">${esc(p[0])}</h2><button class="lk" data-a="prod:-1" aria-label="Fechar detalhes">${i("x")}</button></div><p class="m">${esc(p[1])} · <span class="g75-type" data-t="${isSvc(p) ? "svc" : "prd"}">${isSvc(p) ? "Serviço" : "Produto"}</span></p><h3 style="margin:22px 0 10px">Dados</h3><div class="g2" style="--c:130px 1fr;--gp:10px"><span class="m">Categoria</span><span>${esc(p[2] || "—")}</span><span class="m">Preço de venda</span><span>${brl(p[3])}</span><span class="m">Custo</span><span>${p[6] > 0 ? brl(p[6]) : "Não informado"}</span><span class="m">Margem</span><span>${mgBadge(p)}</span>${isSvc(p) ? "" : `<span class="m">Estoque</span><span>${stPanel(p)}</span>`}<span class="m">Situação</span><span>${p[4] ? dt("", "Disponível") : dt("g", "Indisponível")}</span></div>${isSvc(p) ? `<p class="m sm" style="margin-top:12px">Serviços não têm controle de estoque.</p>` : ""}<h3 style="margin:20px 0 6px;border-top:1px solid var(--b);padding-top:18px">Vendas deste item</h3>${sv.mine.length ? `<p class="m sm">${plural(sv.units, "unidade", "unidades")} em ${plural(sv.mine.length, "venda", "vendas")}: ${brl(sv.paid)} pagos${sv.pend ? ` e ${brl(sv.pend)} pendentes` : ""}.</p><ul class="g75-mini">${last}</ul>` : `<p class="m sm">Nenhuma venda registrada para este item.</p>`}<h3 style="margin:20px 0 6px;border-top:1px solid var(--b);padding-top:18px">Descrição</h3><p>${esc(p[5] || "Sem descrição.")}</p><label class="dz">${im ? `<img src="${im}" alt="Foto de ${esc(p[0])}">` : `<span class="m">${i("img", 36)}</span>`}<div><b>${im ? "Trocar foto" : "Adicionar foto"}</b><div class="m sm">Use uma foto real do item.</div></div><input type="file" accept="image/*" data-s="foto" aria-label="Escolher foto"${w ? "" : " disabled"}></label>${w ? `<button class="btn o w" data-a="edit:prod">${i("pen")}Editar</button>` : ""}`;
    }
    const list = PF.length
      ? `<div class="g75-list" role="list">${PF.map(([x, k]) => {
          const m = mgPct(x[3], x[6]);
          return `<div class="g75-prod${k === S.prod ? " sl" : ""}${x[4] ? "" : " off"}" role="listitem" data-a="prod:${k}" tabindex="0" aria-label="${esc(x[0])}, ${brl(x[3])}"><span class="th">${S.img[k] ? `<img src="${S.img[k]}" alt="">` : i(isSvc(x) ? "cal" : "img", 22)}</span><div class="g75-pn"><b>${esc(x[0])}</b><div class="m sm">${esc(x[1])}${x[2] ? " · " + esc(x[2]) : ""}${x[4] ? "" : " · Indisponível"}</div></div><span class="g75-type" data-t="${isSvc(x) ? "svc" : "prd"}">${isSvc(x) ? "Serviço" : "Produto"}</span><div class="g75-pp"><b>${brl(x[3])}</b>${m == null ? "" : `<span class="mgt ${mgLv(m)}">${m}%</span>`}</div><div class="g75-ps">${stockUi(x)}</div><span class="chv">${i("right")}</span></div>`;
        }).join("")}</div><div class="empty">Nenhum item encontrado para essa busca.</div><p class="m sm" style="margin-top:14px">${cnt("Mostrando {n} de {t} itens.", PF.length, PR.length)}</p>`
      : PR.length
        ? clearEmpty("Nenhum item neste filtro", "Mude os filtros para ver outros itens.<br>", `<button class="btn o" data-a="g75:pclr" style="margin-top:12px">Limpar filtros</button>`)
        : clearEmpty("Nada cadastrado ainda", w ? "Cadastre produtos (com estoque) e serviços (sem estoque) para vendê-los.<br>" : "Quando houver itens cadastrados, eles aparecem aqui.", w ? `<button class="btn" data-a="novo:produto" style="margin-top:12px">${i("plus")}Cadastrar item</button>` : "");
    return `<div class="two g75"><section><div class="row sp wr"><div><h1 style="font-size:30px">Produtos e serviços</h1><p class="m">Preços, disponibilidade e estoque dos produtos; serviços ficam sem estoque.</p></div><button class="btn o" data-a="g75:pexp">${i("dl", 16)}Exportar visão</button></div>${roNote()}${kpis}${restock}<div class="row wr pf1 g75-tb" style="margin:6px 0">${search(".g75-prod", "Buscar nome ou código")}<select class="sel" data-s="pcat" aria-label="Categoria">${cats.map((c) => `<option ${c === pcat ? "selected" : ""} value="${esc(c)}">${c === "Todas" ? "Todas as categorias" : esc(c)}</option>`).join("")}</select></div><div class="row wr g75-chips" role="group" aria-label="Tipo, situação e ordem">${["Todos", "Produtos", "Serviços"].map((k) => chip("g75", "ptype=" + k, k, ptype === k)).join("")}<span class="g75-sep" aria-hidden="true"></span>${Object.keys(PFL).map((k) => chip("pst", k, k, pst === k, PR.filter((x) => tf(x) && PFL[k](x)).length)).join("")}</div><div class="row wr g75-chips" role="group" aria-label="Ordem"><span class="m sm">Ordenar:</span>${Object.keys(PSORT).map((k) => chip("pso", k, k, pso === k)).join("")}</div>${list}<p class="m sm g75-foot"><span class="g75-hint">Atalhos: <kbd>N</kbd> novo item · <kbd>/</kbd> buscar</span></p></section><aside class="pn">${panel}</aside></div>`;
  }

  /* ---------- FINANCEIRO ---------- */
  const FP = { "Todo o período": 0, "Últimos 3 dias": 3, "Últimos 7 dias": 7, "Últimos 30 dias": 30 };
  const catLabel = (c) => ({ receita: "Receitas", despesa: "Despesas" }[c] || c);
  const FSORT = {
    "Mais recentes": (a, b) => pdt(b.x[0]) - pdt(a.x[0]),
    "Maior valor": (a, b) => b.x[4] - a.x[4],
    "Menor valor": (a, b) => a.x[4] - b.x[4],
  };
  const dayKey = (txt) => { const t = pdt(txt); return t > 0 ? dayStart(t) : 0; };
  function flowChart(fs) {
    const by = new Map();
    fs.forEach((x) => { const t = dayKey(x[0]); if (!t) return; const o = by.get(t) || [0, 0]; o[x[3] ? 0 : 1] += x[4]; by.set(t, o); });
    const days = [...by.keys()].sort((a, b) => a - b).slice(-14);
    if (!days.length) return "";
    const mx = Math.max(1, ...days.map((d) => Math.max(...by.get(d))));
    const H = 150, top = 14, bw = 14, step = 46, W = days.length * step + 10;
    const lab = (t) => new Date(t).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
    const bars = days.map((d, n) => {
      const [e, s] = by.get(d), x0 = 10 + n * step, he = (e / mx) * H, hs = (s / mx) * H;
      return `<g><title>${lab(d)}: entradas ${brl(e)}, saídas ${brl(s)}</title><rect class="g75-i" x="${x0}" y="${top + H - he}" width="${bw}" height="${Math.max(he, e ? 2 : 0)}" rx="3"/><rect class="g75-o" x="${x0 + bw + 3}" y="${top + H - hs}" width="${bw}" height="${Math.max(hs, s ? 2 : 0)}" rx="3"/><text x="${x0 + bw}" y="${top + H + 16}" text-anchor="middle">${lab(d)}</text></g>`;
    }).join("");
    const table = days.map((d) => `<tr><td>${lab(d)}</td><td class="r">${brl(by.get(d)[0])}</td><td class="r">${brl(by.get(d)[1])}</td></tr>`).join("");
    return `<div class="g75-card"><div class="row sp wr"><h2 style="font-size:20px">Entradas e saídas por dia</h2><span class="g75-leg"><i class="g75-i"></i>Entradas<i class="g75-o"></i>Saídas</span></div><div class="g75-chart" tabindex="0" role="img" aria-label="Gráfico de barras com entradas e saídas dos últimos ${days.length} dias com movimento. Valor máximo ${brl(mx)}."><svg viewBox="0 0 ${W} ${top + H + 24}" style="width:100%;min-width:${W}px;max-width:${Math.round(W * 1.8)}px;height:auto" preserveAspectRatio="xMinYMid meet"><line x1="0" x2="${W}" y1="${top + H}" y2="${top + H}" class="ax"/><text x="2" y="10" class="mx">${brl(mx)}</text>${bars}</svg></div><details class="dt"><summary>Ver dados em tabela</summary><table class="tb"><tr><th>Dia</th><th class="r">Entradas</th><th class="r">Saídas</th></tr>${table}</table></details></div>`;
  }
  function catBars(fs, inflow, title) {
    const by = new Map();
    fs.filter((x) => !!x[3] === inflow).forEach((x) => by.set(catLabel(x[2]), (by.get(catLabel(x[2])) || 0) + x[4]));
    if (by.size < 2) return "";
    const rows = [...by.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6), total = sum(rows, (r) => r[1]), mx = rows[0][1];
    return `<div class="g75-card"><h2 style="font-size:20px">${title}</h2><ul class="g75-cats" data-k="${inflow ? "in" : "out"}">${rows.map(([n, v]) => `<li><span class="n">${esc(n)}</span><div class="g75-meter"><i style="width:${(v / mx) * 100}%"></i></div><span class="v">${brl(v)} <small>${Math.round((v / total) * 100)}%</small></span></li>`).join("")}</ul></div>`;
  }
  function financeiroView() {
    const w = canWrite(), rem = remote();
    const fdy = FP[S.fper] != null ? FP[S.fper] : 0, fper = FP[S.fper] != null ? S.fper : "Todo o período";
    const inP = (x) => (rem ? host().inFinancialPeriod(x[0], fdy) : fdy === 0 || (ageDays(x[0]) ?? 0) < fdy);
    const all = F.map((x, k) => ({ x, k })).filter((r) => inP(r.x));
    const cats = ["Todas", ...new Set(F.map((x) => x[2]).filter(Boolean))];
    const fcat = cats.includes(S.fcat) ? S.fcat : "Todas", ff = ["Todos", "Entradas", "Saídas"].includes(S.ff) ? S.ff : "Todos", fso = FSORT[S.fso] ? S.fso : "Mais recentes";
    const f = all.filter((r) => (ff === "Todos" || (ff === "Entradas" ? r.x[3] : !r.x[3])) && (fcat === "Todas" || r.x[2] === fcat)).sort(FSORT[fso]);
    G.lastF = f.map((r) => r.x);
    const fs = all.map((r) => r.x);
    const ein = sum(fs.filter((x) => x[3]), (x) => x[4]), eout = sum(fs.filter((x) => !x[3]), (x) => x[4]), res = ein - eout;
    const pendS = V.filter((v) => v[5] !== "Pago"), pendT = sum(pendS, (v) => v[6]);
    const hero = `<div class="g75-hero"><div class="g75-k g75-res" data-tone="${res >= 0 ? "ok" : "bad"}"><span>Resultado do período</span><b>${res < 0 ? "− " : ""}${brl(Math.abs(res))}</b><small>Entradas − saídas dos lançamentos${fper !== "Todo o período" ? " · " + fper.toLowerCase() : ""}. Não é saldo bancário.</small>${split(ein, eout, `Entradas ${brl(ein)} e saídas ${brl(eout)}`)}<div class="g75-legrow"><span><i class="g75-i"></i>Entradas <b>${brl(ein)}</b></span><span><i class="g75-o"></i>Saídas <b>${brl(eout)}</b></span></div></div><div class="g75-k g75-recv" data-tone="${pendS.length ? "warn" : ""}"><span>A receber · vendas pendentes</span><b>${brl(pendT)}</b><small>${pendS.length ? `${plural(pendS.length, "venda", "vendas")} ainda não paga${pendS.length > 1 ? "s" : ""}. Fica fora do resultado até o pagamento ser registrado.` : "Nenhuma venda pendente."}</small>${pendS.length ? `<button class="lk" data-a="g75:vpend">Ver vendas pendentes →</button>` : ""}</div></div>`;
    const charts = fs.length ? `<div class="g75-charts">${flowChart(fs)}${catBars(fs, false, "Para onde foi o dinheiro")}${catBars(fs, true, "De onde veio")}</div>` : "";
    const chip = (key, val, label, on) => `<button class="chip sm3${on ? " on" : ""}" data-a="${key}:${val}" aria-pressed="${on}">${label}</button>`;
    const quick = w ? `<div class="row wr"><button class="btn" data-a="g75:lanc=Entrada">${i("plus")}Entrada</button><button class="btn o" data-a="g75:lanc=Saída">${i("plus")}Saída</button></div>` : "";
    const table = f.length
      ? `<table class="tb rc rtf g75-ft"><tr><th>Data</th><th>Descrição</th><th>Categoria</th><th>Tipo</th><th class="r">Valor</th><th></th></tr>${f.map((r) => { const x = r.x; return `<tr><td>${esc(x[0])}</td><td>${esc(x[1])}</td><td>${esc(catLabel(x[2]))}</td><td>${x[3] ? dt("", "Entrada") : dt("r", "Saída")}</td><td class="r ${x[3] ? "ok" : "no"}">${x[3] ? "" : "− "}${brl(x[4])}</td><td>${w ? (G.busy.has("fx:" + x[0] + x[1]) ? `<button class="lk g75-del" data-a="fx:${r.k}" disabled aria-label="Excluindo">Excluindo…</button>` : `<button class="lk g75-del" data-a="fx:${r.k}" data-armtext="Excluir mesmo?" aria-label="Excluir lançamento">${i("trash", 18)}</button>`) : ""}</td></tr>`; }).join("")}</table><div class="empty">Nenhum lançamento encontrado para essa busca.</div>`
      : F.length
        ? clearEmpty("Nenhum lançamento nesta visão", "Tente outro filtro ou período.<br>", `<button class="btn o" data-a="g75:fclr" style="margin-top:12px">Limpar filtros</button>`)
        : clearEmpty("Nenhum lançamento ainda", w ? "Registre uma entrada ou saída para ver o resultado do seu negócio.<br>" : "Quando houver lançamentos, eles aparecem aqui.", w ? `<button class="btn" data-a="novo:lanc" style="margin-top:12px">${i("plus")}Novo lançamento</button>` : "");
    const shown = f.length && (ff !== "Todos" || fcat !== "Todas") ? `<p class="m sm" style="margin-top:10px">Nesta visão: ${brl(sum(f.filter((r) => r.x[3]), (r) => r.x[4]))} de entradas e ${brl(sum(f.filter((r) => !r.x[3]), (r) => r.x[4]))} de saídas em ${plural(f.length, "lançamento", "lançamentos")}.</p>` : "";
    return `<div class="pg g75" style="padding-top:18px"><div class="row sp wr"><div><h1 style="font-size:30px">Financeiro</h1><p class="m">O que entrou, o que saiu e o que ainda falta receber.</p></div><div class="row wr"><button class="btn o" data-a="g75:fexp">${i("dl", 16)}Exportar visão</button>${quick}</div></div>${roNote()}${hero}${charts}<h2 style="border-top:1px solid var(--b);padding-top:18px;margin-top:22px">Lançamentos</h2><div class="row sp wr g75-tb" style="margin:12px 0"><div class="row wr ff1" style="flex:1;min-width:0">${search(".g75-ft tr:has(td)", "Buscar lançamento")}<div class="seg" role="group" aria-label="Filtrar lançamentos">${["Todos", "Entradas", "Saídas"].map((k) => `<button data-a="ff:${k}" aria-pressed="${ff === k}" style="all:unset;cursor:pointer;padding:9px 16px;${ff === k ? "background:var(--pl);font-weight:700;color:var(--p)" : ""}">${k}</button>`).join("")}</div></div><select class="sel" data-s="fcat" aria-label="Categoria">${cats.map((c) => `<option ${c === fcat ? "selected" : ""} value="${esc(c)}">${c === "Todas" ? "Todas as categorias" : esc(catLabel(c))}</option>`).join("")}</select></div><div class="row wr stp g75-chips" role="group" aria-label="Período e ordem"><span class="m sm">Período:</span>${Object.keys(FP).map((k) => chip("fper", k, k, fper === k)).join("")}<span class="m sm" style="margin-left:auto">Ordenar:</span>${Object.keys(FSORT).map((k) => chip("fso", k, k, fso === k)).join("")}</div>${table}${shown}<p class="m sm g75-foot">${rem ? "Lançamentos e exclusões só aparecem depois da resposta do servidor." : "Demonstração: lançamentos ficam só neste navegador."} <span class="g75-hint">Atalhos: <kbd>N</kbd> novo lançamento · <kbd>/</kbd> buscar</span></p></div>`;
  }

  /* ---------- ações ---------- */
  const copyText = async (t) => {
    try { await navigator.clipboard.writeText(t); return true; } catch (_) {
      const a = document.createElement("textarea"); a.value = t; a.style.cssText = "position:fixed;opacity:0"; document.body.appendChild(a); a.select();
      let ok = false; try { ok = document.execCommand("copy"); } catch (__) {} a.remove(); return ok;
    }
  };
  A.g75 = (arg) => {
    const [k, val] = String(arg).split("=");
    if (k === "vper") { G.vper = PERV[val] != null ? val : "Tudo"; return; }
    if (k === "ptype") { G.ptype = val; return; }
    if (k === "vclr") { S.vf = "Todas"; G.vper = "Tudo"; return; }
    if (k === "pclr") { S.pst = "Todos"; S.pcat = "Todas"; G.ptype = "Todos"; return; }
    if (k === "fclr") { S.ff = "Todos"; S.fcat = "Todas"; S.fper = "Todo o período"; return; }
    if (k === "vpend") { S.vf = "Pendentes"; G.vper = "Tudo"; go("/negocio/vendas"); return false; }
    if (k === "vexp") { csv([["Venda", "Item", "Cliente", "Data", "Situação", "Valor"], ...G.lastV.map((v) => [v[0], v[1], v[2] || "", v[4], v[5], fmtIn(v[6])])], "socialmei-vendas-visao.csv"); return false; }
    if (k === "pexp") { csv([["Item", "Código", "Tipo", "Categoria", "Preço", "Custo", "Estoque", "Aviso em", "Disponível"], ...G.lastP.map((p) => [p[0], p[1], isSvc(p) ? "Serviço" : "Produto", p[2] || "", fmtIn(p[3]), p[6] > 0 ? fmtIn(p[6]) : "", isSvc(p) ? "" : p[7] || 0, isSvc(p) ? "" : stMin(p), p[4] ? "Sim" : "Não"])], "socialmei-produtos-visao.csv"); return false; }
    if (k === "fexp") { csv([["Data", "Descrição", "Categoria", "Tipo", "Valor"], ...G.lastF.map((x) => [x[0], x[1], catLabel(x[2]), x[3] ? "Entrada" : "Saída", fmtIn(x[4])])], "socialmei-financeiro-visao.csv"); return false; }
    if (k === "restock") {
      const L = PR.filter((p) => !isSvc(p) && p[4] && (isOut(p) || isLow(p)));
      copyText(`Reposição de estoque\n${L.map((p) => `• ${p[0]} — ${isOut(p) ? "esgotado" : "restam " + p[7]} (aviso em ${stMin(p)})`).join("\n")}`).then((ok) => toast(ok ? "Lista de reposição copiada." : "Não foi possível copiar. Selecione e copie manualmente."));
      return false;
    }
    if (k === "lanc") {
      if (!canWrite()) return false;
      openAction("lanc");
      const t = document.querySelector("#dlg #f_t");
      if (t) { t.value = val; t.dispatchEvent(new Event("change", { bubbles: true })); }
      return false;
    }
  };

  /* confirmação em dois toques para ações que não se desfazem (pagar venda, excluir lançamento) */
  let armed = null;
  const disarm = () => { if (!armed) return; const { b, html, t } = armed; clearTimeout(t); armed = null; if (b.isConnected) { b.innerHTML = html; b.classList.remove("armed"); delete b.dataset.armed; } };
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("[data-armtext]");
    if (!b || !b.closest("#v")) { if (armed && !(e.target.closest && e.target.closest("[data-armtext]"))) disarm(); return; }
    if (b.dataset.armed === "1") {
      disarm();
      const [kind, idx] = b.dataset.a.split(":"), n = +idx;
      const key = kind === "vt" ? V[n] && "vt:" + V[n][0] : F[n] && "fx:" + F[n][0] + F[n][1];
      const orig = A[kind];
      if (key && remote() && typeof orig === "function") {
        /* a ação remota é assíncrona e o app redesenha logo: guarda o "aguardando" até o servidor responder */
        A[kind] = function () {
          A[kind] = orig;
          G.busy.add(key);
          const r = orig.apply(this, arguments);
          const done = () => { G.busy.delete(key); try { if (/^#\/negocio\/(vendas|financeiro)/.test(location.hash)) render(); } catch (_) {} };
          Promise.resolve(r).catch(() => {}).finally(done);
          setTimeout(() => { if (G.busy.delete(key)) done(); }, 20000);
          return r;
        };
        setTimeout(() => { if (A[kind] !== orig && A[kind].name === "") A[kind] = orig; }, 0);
      }
      return;
    }
    e.preventDefault(); e.stopImmediatePropagation();
    disarm();
    armed = { b, html: b.innerHTML, t: setTimeout(disarm, 5000) };
    b.dataset.armed = "1"; b.classList.add("armed"); b.textContent = b.dataset.armtext;
  }, true);
  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (e.key === "Escape") disarm();
    if ((e.key === "Enter" || e.key === " ") && t.classList?.contains("g75-prod")) { e.preventDefault(); t.click(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || !/^#\/negocio\/(vendas|produtos|financeiro)/.test(location.hash)) return;
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable || document.querySelector("dialog[open]")) return;
    if (e.key === "/") { const q = document.querySelector("#v [data-q]"); if (q) { e.preventDefault(); q.focus(); } }
    else if ((e.key === "n" || e.key === "N") && canWrite()) { const b = document.querySelector("#v .nhfab, .nhfab"); if (b) { e.preventDefault(); b.click(); } }
  });

  /* ---------- formulários: total ao vivo na venda, tipo no produto ---------- */
  function enhanceSale(d) {
    const p = d.querySelector("#f_p"), q = d.querySelector("#f_q"), val = d.querySelector("#f_v"), acts = d.querySelector(".acts");
    if (!p || !q || !acts) return;
    const box = document.createElement("div"); box.className = "g75-sum"; box.setAttribute("aria-live", "polite"); acts.before(box);
    let touched = false; val?.addEventListener("input", () => { touched = true; });
    const prodOf = () => { const o = p.selectedOptions[0]; return o ? PR.find((x) => String(x[1]) === o.value) || PR.find((x) => x[0] === o.value || x[0] === o.textContent.trim()) : null; };
    const up = () => {
      const pr = prodOf(), raw = q.value.trim(), n = parseInt(raw, 10), okq = /^\d+$/.test(raw) && n >= 1;
      const lines = [];
      if (!okq) lines.push(`<span class="bad">Use um número inteiro de 1 em diante.</span>`);
      if (pr && okq) {
        const total = pr[3] * n;
        if (val && !touched) val.value = fmtIn(total);
        lines.push(`<b>Total: ${brl(val && touched && num(val.value) > 0 ? num(val.value) : total)}</b> <span class="m">(${plural(n, "unidade", "unidades")} × ${brl(pr[3])})</span>`);
      }
      if (pr && !isSvc(pr)) {
        const st = pr[7] || 0;
        lines.push(st <= 0 ? `<span class="warn">Sem estoque registrado deste produto.</span>` : okq && n > st ? `<span class="warn">Atenção: há só ${plural(st, "unidade", "unidades")} em estoque.</span>` : `<span class="m">Em estoque: ${st}.</span>`);
      } else if (pr) lines.push(`<span class="m">Serviço: sem controle de estoque.</span>`);
      lines.push(`<span class="m">${remote() ? "A venda entra como pendente; o pagamento só é confirmado depois, com resposta do servidor." : "Demonstração: registro só neste navegador."}</span>`);
      box.innerHTML = lines.map((l) => `<div>${l}</div>`).join("");
    };
    p.addEventListener("change", () => { touched = false; up(); }); q.addEventListener("input", up); up();
  }
  function enhanceProduct(d) {
    const t = d.querySelector("#f_t"); if (!t) return;
    const apply = () => {
      const svc = t.value === "Serviço";
      for (const id of ["e", "m"]) {
        const el = d.querySelector("#f_" + id); if (!el) continue;
        [el.previousElementSibling, el, el.nextElementSibling].forEach((n) => { if (n) n.style.display = svc ? "none" : ""; });
      }
      let note = d.querySelector(".g75-svcnote");
      if (svc && !note) { note = document.createElement("p"); note.className = "m sm g75-svcnote"; note.textContent = "Serviços não têm estoque: nada a controlar aqui."; d.querySelector(".acts")?.before(note); }
      else if (!svc && note) note.remove();
    };
    t.addEventListener("change", apply); apply();
  }
  const seen = new WeakSet();
  const scan = () => {
    const d = document.getElementById("dlg"), f = d && d.querySelector("form");
    if (!f || seen.has(f)) return; seen.add(f);
    const title = f.getAttribute("aria-label") || "";
    if (title === "Nova venda") enhanceSale(d); else if (/produto/i.test(title)) enhanceProduct(d);
  };
  new MutationObserver((m) => { if (m.some((r) => r.type === "childList")) scan(); }).observe(document.body, { childList: true });
  const hookDlg = () => { const d = document.getElementById("dlg"); if (d && !d.dataset.g75) { d.dataset.g75 = "1"; new MutationObserver(scan).observe(d, { childList: true }); } };
  new MutationObserver(hookDlg).observe(document.body, { childList: true }); hookDlg();

  /* ---------- RELATÓRIOS: comparação com o período anterior e leitura guiada ---------- */
  function bounds() {
    if (remote()) {
      const end = new Date(); end.setHours(23, 59, 59, 999); const start = new Date(end);
      if (S.rp === 0) start.setDate(1); else if (S.rp === 1) start.setDate(start.getDate() - 6); else if (S.rp === 2) start.setDate(start.getDate() - 2);
      else { start.setDate(1); end.setDate(Math.min(10, end.getDate())); }
      start.setHours(0, 0, 0, 0); return [start.getTime(), end.getTime()];
    }
    const p = PER[S.rp]; return p ? [p[1], p[2]] : null;
  }
  const delta = (cur, prev, invert) => {
    if (!cur && !prev) return `<span class="g75-d">Sem movimento nos dois períodos</span>`;
    if (!prev) return `<span class="g75-d">Sem dados no período anterior para comparar</span>`;
    const pc = Math.round(((cur - prev) / prev) * 100);
    return `<span class="g75-d" data-dir="${pc === 0 ? "eq" : pc > 0 ? "up" : "down"}">${pc === 0 ? "Igual ao" : (pc > 0 ? "▲ " : "▼ ") + Math.abs(pc) + "% vs."} período anterior (${brl(prev)})</span>`;
  };
  function enhanceReport() {
    const root = document.getElementById("rp"); if (!root) return;
    root.querySelectorAll(".g75-d,.g75-how").forEach((n) => n.remove());
    const b = bounds(), vt = S.rt === "Vendas";
    if (b && document.getElementById("rpc")?.style.display !== "none") {
      const len = b[1] - b[0] + 1, pb = [b[0] - len, b[0] - 1];
      const inB = (txt, r) => { const t = pdt(txt); return t >= r[0] && t <= r[1]; };
      const cards = root.querySelectorAll("#rpc .kp > div");
      let cur, prev;
      if (vt) {
        const c = V.filter((v) => inB(v[4], b)), p = V.filter((v) => inB(v[4], pb));
        cur = [sum(c, (v) => v[6]), sum(c.filter((v) => v[5] === "Pago"), (v) => v[6]), sum(c.filter((v) => v[5] !== "Pago"), (v) => v[6])];
        prev = [sum(p, (v) => v[6]), sum(p.filter((v) => v[5] === "Pago"), (v) => v[6]), sum(p.filter((v) => v[5] !== "Pago"), (v) => v[6])];
      } else {
        const c = F.filter((x) => inB(x[0], b)), p = F.filter((x) => inB(x[0], pb)), e = (a) => sum(a.filter((x) => x[3]), (x) => x[4]), s = (a) => sum(a.filter((x) => !x[3]), (x) => x[4]);
        cur = [e(c), s(c), e(c) - s(c)]; prev = [e(p), s(p), e(p) - s(p)];
      }
      cards.forEach((el, n) => { if (n < 3) el.insertAdjacentHTML("beforeend", delta(cur[n], prev[n])); });
    }
    const how = vt
      ? "<b>Como ler.</b> “Vendas registradas” soma todas as vendas pela data do registro. “Pagamentos registrados” são as vendas marcadas como pagas e “A receber” são as pendentes. Nenhum desses valores é lucro nem saldo do banco. A comparação usa um período do mesmo tamanho logo antes do escolhido, só com os registros que existem."
      : "<b>Como ler.</b> “Entradas” e “Saídas” somam os lançamentos do período; o resultado é a diferença entre elas e não é saldo bancário. Vendas pendentes ainda não entraram aqui. A comparação usa um período do mesmo tamanho logo antes do escolhido, só com os registros que existem.";
    const anchor = root.querySelector("#rpc"); if (anchor) anchor.insertAdjacentHTML("afterbegin", `<p class="m sm g75-how" style="margin:12px 0 0">${how}</p>`);
  }
  if (typeof repApply === "function") { const base = repApply; repApply = function (first) { const r = base.apply(this, arguments); try { enhanceReport(); } catch (_) {} return r; }; }

  /* ---------- troca das visões ---------- */
  vendas = vendasView; produtos = produtosView; financeiro = financeiroView;
  window.SocialMEIGestao = { version: "7.5" };
  }
  /* o script do app pode terminar de definir as telas depois deste arquivo: espera, sem trabalho se nunca chegar */
  if (ready()) start();
  else { let n = 0; const t = setInterval(() => { if (ready()) { clearInterval(t); start(); } else if (++n > 200) clearInterval(t); }, 25); }
})();
