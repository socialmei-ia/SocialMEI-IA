/* Native Reports V2: presentation, frozen local history and local file preparation. */
const SocialMEIReportUI = (() => {
  const data = window.SocialMEIReportData;
  const profileStore = window.SocialMEIBusinessProfile.browserRepository();
  const sourceKeys = ["clientes", "produtos", "vendas", "financeiro"];
  const scope = () => {
    const identity = profileStore.scope();
    if (!identity) return null;
    return (
      identity +
      "|reports-v1|" +
      JSON.stringify(
        sourceKeys.map((key) => {
          const config = SOCIALMEI_CONFIG[key] || { mode: "local" };
          return [key, config.mode, config.apiBaseUrl || "", config.workspaceKey || ""];
        }),
      )
    );
  };
  const history = data.history(
    {
      getItem: (key) => localStorage.getItem(key),
      setItem: (key, value) => localStorage.setItem(key, value),
    },
    scope,
  );
  const state = {
    scope: null,
    records: [],
    transient: [],
    values: new Map(),
    bars: new Map(),
    charts: new Map(),
    frame: 0,
    periodX: 0,
    periodWidth: 0,
    generation: 0,
    owner: null,
    busy: false,
  };
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const ready = (store) => ["local", "ready"].includes(store.connectionState);
  function sync() {
    const current = scope();
    if (current !== state.scope) {
      state.scope = current;
      state.transient = [];
      state.values.clear();
      state.bars.clear();
      state.charts.clear();
      state.generation++;
      cancelAnimationFrame(state.frame);
      if (document.getElementById("reportGenerateModal")?.classList.contains("open")) {
        closeModal("reportGenerateModal");
        document.getElementById("reportGenerateBody").replaceChildren();
      }
      document.body.classList.remove("report-print-active");
      document.getElementById("reportPrintDocument")?.replaceChildren();
    }
    const result = history.read();
    state.records = result.records;
    return result;
  }
  function capture(type = "geral", range = periodRange()) {
    if (!scope()) throw Error("A sessão ou o armazenamento não está disponível para este espaço.");
    if (areMoneyValuesHidden)
      throw Error("Exiba os valores antes de gerar ou exportar um relatório.");
    const previousRange = getPreviousReportRange(range);
    return data.snapshot({
      type,
      range,
      previousRange,
      current: operationalMetrics(range),
      previous: operationalMetrics(previousRange),
      sales: appData.vendas,
      ledger: appData.financeiro,
      ready: { sales: ready(SocialMEISales), finance: ready(SocialMEIFinance) },
      business: getBusinessLabel(),
      source:
        (SocialMEIAuth.remote
          ? "Conta autenticada. "
          : "Demonstração local: pode incluir exemplos fictícios. ") +
        getManagementDataOrigin().description,
      comparisonEnabled: isReportComparisonEnabled,
      createdAt: new Date().toISOString(),
    });
  }
  function fail(error) {
    toast(
      "Relatório não concluído",
      error.message || "Não foi possível preparar o arquivo. Tente novamente.",
    );
  }
  function download(snapshot) {
    if (areMoneyValuesHidden) throw Error("Exiba os valores para exportar este relatório.");
    const blob = new Blob([data.csv(snapshot)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    try {
      const link = el("a");
      link.href = url;
      link.download = `socialmei-relatorio-${snapshot.type}-${snapshot.range.from}-${snapshot.range.to}.csv`;
      document.body.append(link);
      link.click();
      link.remove();
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }
  function exportCurrent() {
    try {
      download(capture());
    } catch (error) {
      fail(error);
    }
  }
  function metricRows(snapshot) {
    return Object.entries(data.definitions)
      .filter(([key]) => snapshot.current[key] !== null)
      .map(([key, [label, format]]) => [
        label,
        formatValue(snapshot.current[key], format),
        snapshot.comparisonEnabled ? formatValue(snapshot.previous[key], format) : "Desativada",
      ]);
  }
  function formatValue(value, format = "number") {
    return value === null
      ? "Indisponível"
      : format === "money"
        ? money(value)
        : Number(value).toLocaleString("pt-BR");
  }
  function table(headers, rows) {
    const node = el("table"),
      head = el("thead"),
      body = el("tbody"),
      top = el("tr");
    headers.forEach((header) => top.append(el("th", header)));
    head.append(top);
    rows.forEach((row) => {
      const tr = el("tr");
      row.forEach((value) => tr.append(el("td", String(value ?? "Não informado"))));
      body.append(tr);
    });
    node.append(head, body);
    return node;
  }
  function print(snapshot) {
    if (areMoneyValuesHidden) throw Error("Exiba os valores para imprimir este relatório.");
    if (!data.validSnapshot(snapshot)) throw Error("Relatório inválido.");
    const host = document.getElementById("reportPrintDocument");
    host.replaceChildren();
    host.append(
      el("h1", "SocialMEI.IA · " + data.types[snapshot.type]),
      el("h2", snapshot.business),
      el("p", `${snapshot.range.from} a ${snapshot.range.to} · Gerado em ${snapshot.createdAt}`),
      el("p", snapshot.source),
      el(
        "p",
        snapshot.comparisonEnabled
          ? `Período anterior: ${snapshot.previousRange.from} a ${snapshot.previousRange.to}.`
          : "Comparação desativada.",
      ),
      table(["Indicador", "Atual", "Anterior"], metricRows(snapshot)),
      el(
        "p",
        `Comparação: ${snapshot.comparison.sales ? "vendas com registro anterior ao início da janela anterior" : "vendas com histórico anterior insuficiente"}; ${snapshot.comparison.finance ? "financeiro com registro anterior ao início da janela anterior" : "financeiro com histórico anterior insuficiente"}.`,
      ),
      el("p", snapshot.notes),
    );
    if (snapshot.sales.length)
      host.append(
        el("h2", "Vendas registradas"),
        table(
          ["Pedido", "Data", "Cliente", "Item", "Situação", "Valor"],
          snapshot.sales.map((row) => [
            row.id,
            row.data,
            row.cliente,
            row.item,
            row.status,
            money(row.valor),
          ]),
        ),
      );
    if (snapshot.ledger.length)
      host.append(
        el("h2", "Lançamentos financeiros"),
        table(
          ["Tipo", "Descrição", "Vencimento", "Situação", "Valor"],
          snapshot.ledger.map((row) => [
            row.tipo,
            row.descricao,
            row.vencimento,
            row.status,
            money(row.valor),
          ]),
        ),
      );
    document.body.classList.add("report-print-active");
    try {
      window.print();
    } catch (error) {
      document.body.classList.remove("report-print-active");
      throw error;
    }
  }
  function printCurrent() {
    try {
      print(capture());
    } catch (error) {
      fail(error);
    }
  }
  window.addEventListener("afterprint", () =>
    document.body.classList.remove("report-print-active"),
  );
  function records() {
    return [
      ...state.transient,
      ...state.records.filter((record) => !state.transient.some((item) => item.id === record.id)),
    ];
  }
  function renderHistory(newId) {
    const result = sync(),
      host = document.getElementById("reportHistoryList");
    if (!host) return;
    const search = document
        .getElementById("reportHistorySearch")
        .value.trim()
        .toLocaleLowerCase("pt-BR"),
      status = document.getElementById("reportHistoryStatus").value;
    const rows = records().filter(
      (record) =>
        (status === "all" || record.status === status) &&
        record.title.toLocaleLowerCase("pt-BR").includes(search),
    );
    document.getElementById("reportHistoryNotice").textContent =
      (result.status === "invalid"
        ? "O histórico local está incompatível e não foi carregado. "
        : result.status === "unavailable"
          ? "O histórico não está disponível para esta sessão ou navegador. "
          : "") +
      "Histórico local deste usuário/negócio, sem sincronização entre dispositivos. Limpar os dados do navegador remove o histórico e suas cópias. Até 20 relatórios; os mais antigos deixam esta lista.";
    host.replaceChildren();
    rows.forEach((record) => {
      const row = el(
        "article",
        undefined,
        "rv2-history-row" + (record.id === newId ? " rv2-row-enter" : ""),
      );
      const summary = el("div");
      summary.append(
        el("b", record.title),
        el(
          "small",
          new Date(record.createdAt).toLocaleString("pt-BR") +
            (state.transient.includes(record)
              ? " · somente nesta página"
              : " · salvo neste navegador"),
        ),
      );
      row.append(
        summary,
        el(
          "span",
          record.status === "ready"
            ? "Concluído"
            : record.status === "processing"
              ? "Preparando"
              : "Com falha",
          "pill " +
            (record.status === "ready" ? "green" : record.status === "error" ? "red" : "draft"),
        ),
      );
      const actions = el("div", undefined, "rv2-actions");
      for (const [action, label] of [
        ["details", "Detalhes"],
        ["csv", "CSV"],
        ["print", "Imprimir / PDF"],
      ]) {
        const button = el("button", label, "management-button");
        button.type = "button";
        button.dataset.reportId = record.id;
        button.dataset.reportAction = action;
        button.dataset.reportScope = state.scope || "";
        button.disabled = record.status !== "ready" && action !== "details";
        actions.append(button);
      }
      row.append(actions);
      host.append(row);
    });
    if (!rows.length)
      host.append(
        el(
          "p",
          records().length
            ? "Nenhum relatório corresponde à busca ou situação escolhida."
            : "Nenhum relatório gerado neste espaço. Use Gerar relatório para guardar um resumo dos seus registros.",
          "rv2-empty",
        ),
      );
  }
  function beginDialog(title) {
    sync();
    state.generation++;
    state.owner = scope();
    document.getElementById("reportGenerateTitle").textContent = title;
    document.getElementById("reportGenerateBody").replaceChildren();
    document.getElementById("reportGenerateFooter").replaceChildren();
    document.getElementById("reportGenerateFooter").hidden = true;
    openModal("reportGenerateModal");
  }
  function preview() {
    const host = document.getElementById("reportGenerationPreview");
    try {
      const snapshot = capture(
        document.getElementById("reportGenerateType").value,
        generationRange(),
      );
      host.textContent = `${snapshot.range.from} a ${snapshot.range.to} · ${snapshot.sales.length} vendas e ${snapshot.ledger.length} lançamentos datados. Valores congelados na geração; não há processamento em servidor.`;
    } catch (error) {
      host.textContent = error.message;
    }
  }
  function generationRange() {
    const choice = document.getElementById("reportGeneratePeriod").value;
    if (choice === "current") return periodRange();
    const days = Number(choice);
    return { from: dateShift(todayISO(), -(days - 1)), to: todayISO() };
  }
  function openGenerator() {
    beginDialog("Gerar relatório");
    const host = document.getElementById("reportGenerateBody"),
      form = el("form");
    form.id = "reportGenerateForm";
    const fields = el("div", undefined, "rv2-form-fields");
    for (const [id, label, options] of [
      ["reportGenerateType", "Tipo", Object.entries(data.types)],
      [
        "reportGeneratePeriod",
        "Período",
        [
          ["current", "Seleção atual · " + rangeCaption()],
          ["7", "Últimos 7 dias"],
          ["30", "Últimos 30 dias"],
          ["90", "Últimos 90 dias"],
        ],
      ],
    ]) {
      const field = el("div", undefined, "form-group"),
        name = el("label", label),
        select = el("select", undefined, "form-control");
      name.htmlFor = id;
      select.id = id;
      options.forEach(([value, text]) => {
        const option = el("option", text);
        option.value = value;
        select.append(option);
      });
      field.append(name, select);
      fields.append(field);
      select.addEventListener("change", preview);
    }
    const hint = el("p", undefined, "rv2-generation-preview");
    hint.id = "reportGenerationPreview";
    const note = el(
      "p",
      "Um resumo dos indicadores e dos registros datados. CSV é baixado localmente; PDF utiliza Imprimir / salvar como PDF do navegador. O histórico é local e não sincroniza.",
      "management-note",
    );
    const submit = el("button", "Gerar neste navegador", "management-button pr");
    submit.type = "submit";
    const status = el("p", undefined, "management-note");
    status.id = "reportGenerationStatus";
    status.setAttribute("role", "status");
    form.append(fields, hint, note, submit, status);
    host.append(form);
    form.addEventListener("submit", generate);
    preview();
  }
  const nextPaint = () =>
    new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  async function generate(event) {
    event.preventDefault();
    if (state.busy) return;
    const owner = state.owner,
      type = document.getElementById("reportGenerateType").value,
      range = generationRange();
    const token = ++state.generation;
    state.busy = true;
    const record = {
      id: crypto.randomUUID(),
      title: data.types[type] + " · " + range.from + " a " + range.to,
      createdAt: new Date().toISOString(),
      status: "processing",
      snapshot: null,
      error: "",
    };
    const body = document.getElementById("reportGenerateBody"),
      list = el("ol", undefined, "rv2-progress-steps"),
      bar = el("progress");
    bar.max = 3;
    bar.value = 0;
    bar.setAttribute("aria-label", "Preparação local do relatório");
    [
      "Validar fontes e período",
      "Organizar dados e validar CSV",
      "Guardar uma cópia no navegador",
    ].forEach((label) => list.append(el("li", label)));
    const status = el("p", "Preparação local dos registros disponíveis.");
    status.setAttribute("role", "status");
    body.replaceChildren(status, bar, list);
    document.getElementById("reportGenerateTitle").focus();
    state.transient.unshift(record);
    renderHistory();
    try {
      await nextPaint();
      if (scope() !== owner || token !== state.generation)
        throw Error("A sessão mudou. Gere novamente no espaço atual.");
      record.snapshot = capture(type, range);
      bar.value = 1;
      list.children[0].classList.add("done");
      await nextPaint();
      data.csv(record.snapshot);
      bar.value = 2;
      list.children[1].classList.add("done");
      await nextPaint();
      if (scope() !== owner || token !== state.generation)
        throw Error("A sessão mudou. Gere novamente no espaço atual.");
      record.status = "ready";
      const saved = history.save(record, owner);
      bar.value = 3;
      list.children[2].classList.add("done");
      if (saved) state.transient = state.transient.filter((item) => item.id !== record.id);
      state.busy = false;
      renderHistory(record.id);
      if (
        token === state.generation &&
        document.getElementById("reportGenerateModal").classList.contains("open")
      )
        showRecord(record, !saved);
    } catch (error) {
      state.busy = false;
      if (scope() !== owner) {
        sync();
        fail(error);
        return;
      }
      record.status = "error";
      record.snapshot = null;
      record.error = error.message;
      if (history.save(record, owner))
        state.transient = state.transient.filter((item) => item.id !== record.id);
      renderHistory(record.id);
      if (
        token === state.generation &&
        document.getElementById("reportGenerateModal").classList.contains("open")
      )
        showRecord(record, false);
    }
  }
  function showRecord(record, temporary = false) {
    if (scope() !== state.owner) return;
    const host = document.getElementById("reportGenerateBody");
    host.replaceChildren();
    document.getElementById("reportGenerateTitle").textContent =
      record.status === "ready" ? "Relatório pronto" : "Não foi possível concluir";
    if (record.status !== "ready") {
      host.append(el("p", record.error || "A preparação local ainda não terminou."));
      return;
    }
    const snapshot = record.snapshot;
    host.append(
      el("p", `${snapshot.range.from} a ${snapshot.range.to} · ${snapshot.business}`),
      el("p", snapshot.source, "management-note"),
      el(
        "p",
        snapshot.comparisonEnabled
          ? `Período anterior: ${snapshot.previousRange.from} a ${snapshot.previousRange.to}.`
          : "Comparação desativada.",
      ),
      table(["Indicador", "Atual", "Anterior"], metricRows(snapshot)),
      el("p", snapshot.notes, "management-note"),
    );
    host.append(
      el(
        "p",
        temporary
          ? "Gerado, mas não salvo no histórico. Baixe agora: esta cópia desaparece ao sair ou recarregar."
          : "Cópia congelada neste navegador. Novos registros não alteram os números deste relatório.",
        "rv2-generation-preview",
      ),
    );
    if (!snapshot.comparison.sales || !snapshot.comparison.finance)
      host.append(
        el(
          "p",
          "Comparações sem histórico anterior suficiente ficam indisponíveis. Valores anteriores mostrados são somente registros encontrados, sem garantia de cobertura completa.",
          "management-note",
        ),
      );
    const actions = el("div", undefined, "rv2-actions");
    for (const [action, label] of [
      ["csv", "Baixar CSV"],
      ["print", "Imprimir / salvar PDF"],
    ]) {
      const button = el("button", label, "management-button" + (action === "csv" ? " pr" : ""));
      button.type = "button";
      button.dataset.reportId = record.id;
      button.dataset.reportAction = action;
      button.dataset.reportScope = state.owner;
      actions.append(button);
    }
    const footer = document.getElementById("reportGenerateFooter");
    footer.replaceChildren(actions);
    footer.hidden = false;
    document.getElementById("reportGenerateTitle").focus();
  }
  function context() {
    const profile = profileStore.read().profile;
    return profile
      ? `${profile.segment === "other" ? profile.activity || "Seu negócio" : SocialMEIBusinessProfile.segments[profile.segment].label} · ${profile.offers.includes("products") && profile.offers.includes("services") ? "produtos e serviços" : profile.offers.includes("services") ? "serviços, vendas e financeiro" : "produtos, estoque e vendas"}. Indicadores disponíveis para qualquer segmento; entregas e atendimentos concluídos não são inferidos.`
      : "Indicadores dos registros disponíveis. Configure seu perfil em Configurações para contextualizar esta visão.";
  }
  function updateIndicator() {
    const wrap = document.getElementById("reportQuickPeriods"),
      active = wrap.querySelector(`[data-report-quick="${selectedPeriod}"]`),
      pill = document.getElementById("reportPeriodIndicator");
    wrap
      .querySelectorAll("button")
      .forEach((button) => button.setAttribute("aria-pressed", String(button === active)));
    pill.hidden = !active;
    if (!active) return;
    const x = active.offsetLeft,
      width = active.offsetWidth;
    pill.style.width = width + "px";
    pill.style.transform = `translateX(${x}px)`;
    state.periodX = x;
    state.periodWidth = width;
  }
  function animateMetrics(metrics, salesReady, financeReady) {
    cancelAnimationFrame(state.frame);
    const nodes = [...document.querySelectorAll("#nvReportKpis .management-kpi b")];
    const values = [metrics.revenue, metrics.ticket, metrics.paidSales.length, metrics.balance];
    const jobs = [];
    const allowed = !SocialMEIMotion.reduced && !document.hidden;
    nodes.forEach((node, index) => {
      const format = index === 2 ? "number" : "money",
        key = ["revenue", "ticket", "count", "balance"][index],
        end = values[index];
      if (
        !(index === 3 ? financeReady : salesReady) ||
        (format === "money" && areMoneyValuesHidden)
      ) {
        state.values.delete(key);
        return;
      }
      const start = state.values.get(key) ?? 0;
      node.setAttribute("aria-label", formatValue(end, format));
      if (!allowed || Math.abs(start - end) < 0.001) {
        state.values.set(key, end);
        return;
      }
      jobs.push({ node, key, start, end, format });
      node.textContent = formatValue(start, format);
    });
    const root = document.getElementById("nvReportKpis"),
      status = document.getElementById("reportUpdateStatus");
    root.setAttribute("aria-busy", String(!!jobs.length));
    status.textContent = jobs.length
      ? "Atualizando os valores para " + rangeCaption() + ". Indicadores em transição."
      : "Dados atualizados · " + rangeCaption();
    if (!jobs.length) return;
    const startTime = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - startTime) / 680),
        ease = 1 - (1 - t) ** 3;
      jobs.forEach((job) => {
        if (job.node.isConnected) {
          const value = job.start + (job.end - job.start) * ease;
          state.values.set(job.key, value);
          job.node.textContent = formatValue(
            job.format === "number" ? Math.round(value) : value,
            job.format,
          );
        }
      });
      if (t < 1) state.frame = requestAnimationFrame(tick);
      else {
        root.setAttribute("aria-busy", "false");
        status.textContent = "Dados atualizados · " + rangeCaption();
      }
    };
    state.frame = requestAnimationFrame(tick);
  }
  function afterRender(metrics, salesReady, financeReady) {
    sync();
    const periodKey = JSON.stringify(periodRange());
    if (state.periodKey !== periodKey)
      document.querySelector("#reportsView .report-period-options").open = false;
    state.periodKey = periodKey;
    document.getElementById("reportProfileContext").textContent = context();
    document
      .getElementById("reportsDataSourceStatus")
      .append(
        el(
          "span",
          SocialMEIAuth.remote
            ? "Conta autenticada · sem amostra sintética V2."
            : "Demonstração local: pode conter exemplos existentes; não são dados sincronizados.",
        ),
      );
    state.chartMobile = innerWidth <= 600;
    animateMetrics(metrics, salesReady, financeReady);
    updateIndicator();
    renderHistory();
    const needed =
      selectedReportTab === "Financeiro"
        ? financeReady
        : selectedReportTab === "Atendimento"
          ? true
          : salesReady;
    if (!needed) {
      document
        .getElementById("reportsGrid")
        .replaceChildren(
          el("h3", "Leitura do relatório indisponível"),
          el(
            "p",
            "A fonte está carregando ou indisponível. Recarregue no módulo de origem antes de consultar estes valores.",
          ),
        );
      return;
    }
    document.querySelectorAll("#reportsView .rv2-trend").forEach((chart) => {
      const key = chart.dataset.source,
        signature = chart.dataset.series;
      const changed = state.charts.get(key) !== signature;
      state.charts.set(key, signature);
      if (changed && !SocialMEIMotion.reduced && !document.hidden)
        chart.querySelectorAll(".rv2-line").forEach((path) => {
          const length = path.getTotalLength();
          SocialMEIMotion.animate(
            path,
            [
              { strokeDasharray: String(length), strokeDashoffset: length },
              { strokeDasharray: String(length), strokeDashoffset: 0 },
            ],
            740,
          );
        });
      const tip = chart.querySelector(".rv2-chart-tooltip"),
        readout = chart.querySelector(".rv2-chart-readout");
      chart.querySelectorAll(".rv2-point").forEach((point) => {
        const show = () => {
          const text = point.getAttribute("aria-label");
          tip.textContent = text;
          readout.textContent = text;
          tip.hidden = false;
        };
        point.addEventListener("pointerenter", show);
        point.addEventListener("focus", show);
        point.addEventListener("click", show);
        point.addEventListener("keydown", (event) => {
          if (["Enter", " "].includes(event.key)) {
            event.preventDefault();
            show();
          }
          if (event.key === "Escape") tip.hidden = true;
        });
        point.addEventListener("blur", () => {
          tip.hidden = true;
        });
        point.addEventListener("pointerleave", () => {
          tip.hidden = true;
        });
      });
    });
    document.querySelectorAll("#reportsView [data-report-bar]").forEach((bar) => {
      const key = bar.dataset.reportBar,
        end = Number(bar.dataset.value),
        start = state.bars.get(key) ?? 0;
      state.bars.set(key, end);
      if (start !== end && !SocialMEIMotion.reduced)
        SocialMEIMotion.animate(bar, [{ width: start + "%" }, { width: end + "%" }], 690);
    });
  }
  function trend(series) {
    const mobile = innerWidth <= 600;
    const w = mobile ? Math.max(230, Math.min(460, innerWidth - 72)) : 670;
    const h = mobile ? 220 : 250,
      L = mobile ? 42 : 50,
      R = 18,
      T = 22,
      B = 40,
      n = series.labels.length;
    const max = Math.max(1, ...series.r, ...series.d);
    const x = (i) => L + (n === 1 ? 0 : (i * (w - L - R)) / (n - 1));
    const y = (v) => T + (1 - v / max) * (h - T - B);
    const path = (values) =>
      values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const sales = series.source === "sales",
      labelStep = Math.ceil(n / (mobile ? 5 : 7));
    const ticks = [0, 0.5, 1]
      .map(
        (value) =>
          `<line x1="${L}" x2="${w - R}" y1="${y(max * value)}" y2="${y(max * value)}" stroke="var(--ln)"/><text x="${L - 6}" y="${y(max * value) + 4}" text-anchor="end" fill="var(--mt)" font-size="${mobile ? 11 : 14}">${(max * value).toLocaleString("pt-BR", { notation: "compact", maximumFractionDigits: 1 })}</text>`,
      )
      .join("");
    return `<div class="management-chart rv2-trend" data-source="${series.source}" data-series="${escapeHtml(JSON.stringify(series))}"><svg viewBox="0 0 ${w} ${h}" role="group" aria-label="${sales ? "Faturamento das vendas pagas" : "Receitas e despesas pagas"}, em reais. Percorra os pontos com Tab.">${ticks}<path class="rv2-line" d="${path(series.r)}" fill="none" stroke="var(--brand-primary)" stroke-width="2.5" vector-effect="non-scaling-stroke"/>${sales ? "" : `<path class="rv2-line" d="${path(series.d)}" fill="none" stroke="var(--brand-accent)" stroke-width="2.5" vector-effect="non-scaling-stroke"/>`}${series.labels.map((label, i) => `<g class="rv2-point management-chart-column" role="button" tabindex="0" aria-label="${escapeHtml(label + ": " + (sales ? "faturamento " : "entrou ") + money(series.r[i]) + (sales ? "" : "; saiu " + money(series.d[i])))}"><circle cx="${x(i)}" cy="${y(series.r[i])}" r="12" fill="transparent"/><circle cx="${x(i)}" cy="${y(series.r[i])}" r="${mobile ? 5 : 4}" fill="var(--sf)" stroke="var(--brand-primary)" stroke-width="2" vector-effect="non-scaling-stroke"/></g>${i % labelStep === 0 || i === n - 1 ? `<text x="${x(i)}" y="${h - 12}" text-anchor="middle" fill="var(--mt)" font-size="${mobile ? 12 : 16}">${escapeHtml(label)}</text>` : ""}`).join("")}</svg><p class="rv2-chart-tooltip" hidden></p><p class="rv2-chart-readout management-note" role="status">Passe o mouse ou use Tab nos pontos para conferir valores.</p></div>`;
  }
  function statusPanel(metrics) {
    const total = metrics.sales.length;
    return `<h3>Situação das vendas</h3><p class="management-note">${total} registros no período. Pago não significa entregue.</p><div class="rv2-stacked" role="img" aria-label="Distribuição por situação da venda">${[
      "Pago",
      "Pendente",
      "Cancelado",
      "Rascunho",
    ]
      .map((status, index) => {
        const count = metrics.sales.filter((sale) => sale.status === status).length,
          percent = total ? (count / total) * 100 : 0;
        return `<span data-report-bar="status-${status}" data-value="${percent}" style="width:${percent}%;background:${["var(--brand-primary)", "var(--brand-accent)", "var(--chart-5)", "var(--surface-secondary)"][index]}"></span>`;
      })
      .join(
        "",
      )}</div><dl class="rv2-status-list">${["Pago", "Pendente", "Cancelado", "Rascunho"].map((status) => `<div><dt>${status}</dt><dd>${metrics.sales.filter((sale) => sale.status === status).length}</dd></div>`).join("")}</dl>`;
  }
  function linkedItems(metrics) {
    if (!ready(SocialMEIProducts) || SocialMEIProducts.remote !== SocialMEISales.remote)
      return "<p>O ranking por tipo requer catálogo disponível na mesma fonte das vendas.</p>";
    const rows = new Map();
    metrics.paidSales.forEach((sale) => {
      if (
        !Number.isSafeInteger(sale.produto_id) ||
        !Number.isFinite(sale.quantidade) ||
        sale.quantidade <= 0
      )
        return;
      const product = appData.produtos.find((item) => item.id === sale.produto_id);
      if (!product) return;
      const prior = rows.get(product.id) || {
        name: sale.item || product.nome,
        type: product.tipo,
        quantity: 0,
      };
      prior.quantity += sale.quantidade;
      rows.set(product.id, prior);
    });
    const profile = profileStore.read().profile;
    const preferred =
      profile?.offers.length === 1
        ? profile.offers[0] === "services"
          ? "Serviço"
          : "Produto"
        : null;
    const sorted = [...rows.values()]
        .sort(
          (a, b) =>
            (preferred ? Number(b.type === preferred) - Number(a.type === preferred) : 0) ||
            b.quantity - a.quantity,
        )
        .slice(0, 5),
      max = Math.max(1, ...sorted.map((item) => item.quantity));
    return sorted.length
      ? (preferred
          ? `<p class="management-note">${preferred === "Serviço" ? "Serviços" : "Produtos"} primeiro, conforme seu perfil. Os demais tipos continuam nos detalhes.</p>`
          : "") +
          sorted
            .map(
              (row, index) =>
                `<div class="rv2-product-item"><div><span>${escapeHtml(row.name)} <small>· ${escapeHtml(row.type)}</small></span><b>${row.quantity.toLocaleString("pt-BR")} un.</b></div><div class="rv2-product-track"><span data-report-bar="item-${index}-${escapeHtml(row.name)}" data-value="${(row.quantity / max) * 100}" style="width:${(row.quantity / max) * 100}%"></span></div></div>`,
            )
            .join("")
      : '<p class="management-note">Sem vendas pagas com vínculo por ID e quantidade ao catálogo. Não é seguro separar produtos físicos e serviços a partir de nomes informados livremente.</p>';
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-report-generate]")) {
      openGenerator();
      return;
    }
    const quick = event.target.closest("[data-report-quick]");
    if (quick) {
      if (selectedPeriod === quick.dataset.reportQuick) return;
      selectedPeriod = quick.dataset.reportQuick;
      customRange = null;
      updatePeriodLabel();
      renderReports();
      quick.focus();
      return;
    }
    const control = event.target.closest("[data-report-action]");
    if (!control) return;
    if (control.dataset.reportScope !== (scope() || "")) {
      sync();
      renderHistory();
      fail(Error("O espaço da sessão mudou. Abra um relatório do usuário atual."));
      return;
    }
    sync();
    const record = records().find((item) => item.id === control.dataset.reportId);
    if (!record) {
      renderHistory();
      fail(Error("Este relatório não está disponível no histórico atual."));
      return;
    }
    if (control.dataset.reportAction === "details") {
      beginDialog(record.title);
      showRecord(record, state.transient.includes(record));
      return;
    }
    if (record.status !== "ready") return;
    try {
      if (control.dataset.reportAction === "csv") download(record.snapshot);
      else print(record.snapshot);
    } catch (error) {
      fail(error);
    }
  });
  document.getElementById("reportHistorySearch").addEventListener("input", () => renderHistory());
  document.getElementById("reportHistoryStatus").addEventListener("change", () => renderHistory());
  window.addEventListener("resize", () => {
    if (currentView === "Relatórios") {
      if (state.chartMobile !== innerWidth <= 600) renderReports();
      else updateIndicator();
    }
  });
  document.addEventListener("socialmei-business-profile-change", () => {
    if (currentView === "Relatórios") renderReports();
  });
  document.addEventListener("socialmei-motion-change", () => {
    cancelAnimationFrame(state.frame);
    if (typeof currentView !== "undefined" && currentView === "Relatórios") renderReports();
  });
  return {
    afterRender,
    trend,
    statusPanel,
    linkedItems,
    exportCurrent,
    printCurrent,
    scope,
    capture,
  };
})();
