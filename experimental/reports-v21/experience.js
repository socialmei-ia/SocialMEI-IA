/* Presentation adapters only. Native metrics, snapshot, CSV, print and history are reused. */
(() => {
  const before = new URLSearchParams(location.search).get("view") === "before";
  document.documentElement.classList.toggle("reports-v21", !before);
  const q = (selector) => document.querySelector(selector);
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const chartState = new Map();
  const sourceDescriptors = new Map();
  let frame = 0;
  let previewState = "sample";
  let generation = 0;
  let generating = false;
  const nextPaint = () =>
    new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

  async function generate(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (generating) return;
    generating = true;
    const token = ++generation;
    const owner = SocialMEIReportUI.scope();
    const type = q("#reportGenerateType").value;
    const days = q("#reportGeneratePeriod").value;
    const range =
      days === "current"
        ? periodRange()
        : { from: dateShift(todayISO(), -(Number(days) - 1)), to: todayISO() };
    const record = {
      id: crypto.randomUUID(),
      title: SocialMEIReportData.types[type] + " · " + range.from + " a " + range.to,
      createdAt: new Date().toISOString(),
      status: "processing",
      snapshot: null,
      error: "",
    };
    const host = q("#reportGenerateBody");
    const progress = make("progress");
    progress.max = 3;
    progress.value = 0;
    progress.setAttribute("aria-label", "Preparação local do exemplo fictício");
    const status = make("p", "Validar fontes e período");
    status.setAttribute("role", "status");
    const steps = make("ol", undefined, "rv2-progress-steps");
    [
      "Validar fontes e capturar os registros",
      "Preparar e validar o CSV",
      "Guardar a cópia na memória desta prévia",
    ].forEach((label) => steps.append(make("li", label)));
    host.replaceChildren(status, progress, steps);
    q("#reportGenerateTitle").focus();
    const active = () =>
      token === generation &&
      owner === SocialMEIReportUI.scope() &&
      q("#reportGenerateModal").classList.contains("open");
    const history = SocialMEIReportData.history(localStorage, SocialMEIReportUI.scope);
    try {
      await nextPaint();
      if (!active()) return;
      record.snapshot = SocialMEIReportUI.capture(type, range);
      progress.value = 1;
      steps.children[0].classList.add("done");
      status.textContent = "Preparando CSV com os registros capturados";
      await nextPaint();
      if (!active()) return;
      SocialMEIReportData.csv(record.snapshot);
      progress.value = 2;
      steps.children[1].classList.add("done");
      status.textContent = "Guardando uma cópia nesta página";
      await nextPaint();
      if (!active()) return;
      record.status = "ready";
      if (!history.save(record, owner))
        throw Error("Não foi possível guardar a cópia nesta prévia. Tente novamente.");
      progress.value = 3;
      steps.children[2].classList.add("done");
      renderReports();
      q(`#reportHistoryList [data-report-id="${record.id}"]`)
        .closest("article")
        .classList.add("rv2-row-enter");
      q(`#reportHistoryList [data-report-id="${record.id}"][data-report-action="details"]`).click();
      q("#reportGenerateModal")._returnFocus = q("[data-report-generate]");
      q("#previewFeedback").textContent =
        "Relatório fictício preparado e guardado nesta página. CSV e impressão usam a mesma cópia.";
    } catch (error) {
      if (!active()) return;
      record.status = "error";
      record.snapshot = null;
      record.error = error.message;
      history.save(record, owner);
      renderReports();
      q("#reportGenerateTitle").textContent = "Não foi possível concluir";
      host.replaceChildren(make("p", error.message));
      q("#previewFeedback").textContent =
        "Falha na preparação local. Nenhum arquivo foi apresentado como concluído.";
    } finally {
      if (token === generation) generating = false;
    }
  }

  function seed() {
    const names = [
      "Ana Lima",
      "Bruno Alves",
      "Carla Reis",
      "Davi Melo",
      "Elisa Costa",
      "Fábio Luz",
    ];
    const catalog = [
      { id: 101, nome: "Ajuste de vestido", tipo: "Serviço", preco: 90 },
      { id: 102, nome: "Barra de calça", tipo: "Serviço", preco: 45 },
      { id: 103, nome: "Ecobag artesanal", tipo: "Produto", preco: 65 },
      { id: 104, nome: "Confecção sob medida", tipo: "Serviço", preco: 240 },
    ];
    appData.clientes = names.map((nome, i) => ({
      id: i + 1,
      nome,
      tags: [],
      criadoEm: dateShift(todayISO(), -190),
    }));
    appData.produtos = catalog.map((p) => ({
      ...p,
      custo: 0,
      estoque: p.tipo === "Serviço" ? null : 0,
      minimo: 0,
      status: "Ativo",
    }));
    appData.vendas = [];
    appData.financeiro = [];
    let id = 1000;
    for (let day = 179; day >= 0; day--) {
      if (day % 7 === 0) continue;
      for (let j = 0; j < (day % 3 === 0 ? 2 : 1); j++) {
        const product = catalog[(day + j) % catalog.length];
        const status = day % 19 === 0 ? "Cancelado" : day % 11 === 0 ? "Pendente" : "Pago";
        const client = appData.clientes[(day + j) % names.length];
        appData.vendas.push({
          id: id++,
          cliente_id: client.id,
          cliente: client.nome,
          produto_id: product.id,
          item: product.nome,
          quantidade: 1,
          valor: product.preco,
          data: dateShift(todayISO(), -day),
          status,
          pagamento: day % 3 ? "Pix" : "Cartão",
        });
      }
      appData.financeiro.push({
        id: id++,
        tipo: day % 3 ? "receita" : "despesa",
        descricao:
          day % 3 ? "Recebimento de encomenda · fictício" : "Materiais de costura · fictício",
        valor: day % 3 ? 80 + (day % 5) * 20 : 35 + (day % 4) * 10,
        vencimento: dateShift(todayISO(), -day),
        status: "pago",
      });
    }
    // These sentinels must never count or appear in exported reports.
    appData.vendas.push({
      id: 99999,
      valor: 999999,
      status: "Pago",
      data: todayISO(),
      excluida: true,
    });
    sessionData.conversas = [];
    appData.prefs.negocio = { ...appData.prefs.negocio, nome: "Ateliê Aurora · fictício" };
    appData.prefs.conta = {
      ...appData.prefs.conta,
      nome: "Prévia SocialMEI",
      email: "preview@example.invalid",
    };
    const model = SocialMEIBusinessProfile;
    model.browserRepository().save(
      model.normalize({
        businessName: "Ateliê Aurora · fictício",
        segment: "tailoring",
        offers: ["products", "services"],
        completed: true,
      }),
    );
  }

  function stateChange(value) {
    previewState = value;
    for (const store of [SocialMEISales, SocialMEIFinance]) {
      if (!sourceDescriptors.has(store))
        sourceDescriptors.set(store, Object.getOwnPropertyDescriptor(store, "connectionState"));
      Object.defineProperty(
        store,
        "connectionState",
        value === "error" || value === "loading"
          ? { configurable: true, get: () => (value === "error" ? "unavailable" : "loading") }
          : sourceDescriptors.get(store),
      );
    }
    seed();
    if (value === "empty") {
      appData.vendas = [];
      appData.financeiro = [];
      appData.clientes = [];
      appData.produtos = [];
    }
    q("#previewState").value = value;
    renderReports();
    q("#previewFeedback").textContent =
      value === "error"
        ? "Falha de fonte simulada. Nenhuma API foi consultada."
        : value === "loading"
          ? "Estado de carregamento demonstrativo, mantido até você trocar o cenário."
          : value === "empty"
            ? "Cenário sem registros. Nenhum dado real foi apagado."
            : "Exemplo fictício restaurado.";
  }

  function decorate() {
    const report = q("#reportsView");
    q("#reportProfileContext").textContent =
      "Ateliê Aurora · produtos e serviços · exemplo fictício";
    q("#reportsDataSourceStatus").replaceChildren();
    const sourceNote = make("details", undefined, "v21-source-note");
    sourceNote.append(
      make("summary", "Sobre os dados desta prévia"),
      make(
        "p",
        "Dados inteiramente fictícios. Cálculos e exportações usam o motor nativo. O histórico desta prévia fica em memória e desaparece ao recarregar. Nenhuma conta, API ou integração é acessada.",
      ),
    );
    q("#reportsDataSourceStatus").append(sourceNote);
    q("#reportHistoryNotice").textContent =
      "Cópias fictícias desta prévia. Ficam apenas nesta página e desaparecem ao recarregar.";
    q("#reportHistoryTitle").textContent = "Seus relatórios, prontos para consultar";
    report.dataset.previewState = previewState;
    if (before) return;
    q("#nvReportKpis")
      .querySelectorAll("small")
      .forEach((note) => {
        note.title = note.textContent;
        note.textContent = note.textContent.replace("vs. período anterior", "vs. anterior");
      });
    const primary = q("#resultChapter");
    if (primary && !areMoneyValuesHidden && !["error", "loading"].includes(previewState)) {
      const metric = make("p", undefined, "v21-chart-total");
      metric.append(
        make("strong", money(operationalMetrics().revenue)),
        make("span", "em vendas pagas no período"),
      );
      primary.querySelector(".report-section-heading").after(metric);
    }
    q("#reportsView .report-intro h2").textContent = "Seu negócio em perspectiva.";
    q("#reportsView .report-intro p").textContent = "Entenda o resultado. Decida o próximo passo.";
    q("#reportsGrid .rv2-lower-grid > section:last-child h3")?.replaceChildren(
      "Uma leitura com contexto",
    );
    q("#reportsGrid .report-care [data-go]")?.remove();
    report.querySelectorAll("[data-go], [data-record-open]").forEach((button) => {
      button.removeAttribute("data-go");
      button.removeAttribute("data-record-open");
      button.textContent = "Conferir registro";
      button.dataset.previewRecord = "true";
    });
  }

  function points(path) {
    const numbers = (path.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
    return Array.from({ length: numbers.length / 2 }, (_, i) => [
      numbers[i * 2],
      numbers[i * 2 + 1],
    ]);
  }
  function draw(points) {
    return points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  }
  function sample(values, index, length) {
    const position = length === 1 ? 0 : (index / (length - 1)) * (values.length - 1);
    const low = Math.floor(position),
      high = Math.min(values.length - 1, low + 1),
      t = position - low;
    return values[low].map((v, i) => v + (values[high][i] - v) * t);
  }
  function morphCharts() {
    cancelAnimationFrame(frame);
    window.REPORTS_PREVIEW.animating = false;
    const jobs = [];
    q("#reportsView")
      .querySelectorAll(".rv2-trend")
      .forEach((chart) => {
        chart.querySelectorAll(".rv2-line").forEach((path, index) => {
          const end = points(path.getAttribute("d"));
          const key = chart.dataset.source + index;
          const previous = chartState.get(key);
          const signature =
            chart.dataset.series + chart.querySelector("svg").getAttribute("viewBox");
          const entry = { points: end, signature };
          chartState.set(key, entry);
          if (!previous) return; // Native first-entry line draw is already running.
          path.getAnimations().forEach((a) => a.cancel());
          if (SocialMEIMotion.reduced || document.hidden || previous?.signature === signature)
            return;
          const start = previous
            ? end.map((_, i) => sample(previous.points, i, end.length))
            : end.map(([x]) => [x, Math.max(...end.map((p) => p[1]))]);
          entry.points = start;
          path.setAttribute("d", draw(start));
          jobs.push({ path, start, end, entry });
        });
      });
    if (!jobs.length) return;
    window.REPORTS_PREVIEW.animating = true;
    const started = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - started) / 460),
        eased = 1 - (1 - t) ** 3;
      jobs.forEach(({ path, start, end, entry }) => {
        entry.points = end.map((point, i) =>
          point.map((v, axis) => start[i][axis] + (v - start[i][axis]) * eased),
        );
        path.setAttribute("d", draw(entry.points));
      });
      if (t < 1) frame = requestAnimationFrame(tick);
      else window.REPORTS_PREVIEW.animating = false;
    };
    frame = requestAnimationFrame(tick);
  }

  function init() {
    const tools = make("aside", undefined, "preview-toolbar");
    tools.setAttribute("aria-label", "Controles da prévia isolada");
    tools.innerHTML = `<a class="preview-brand" href="${location.pathname}"><span class="socialmei-logo-image" aria-hidden="true"></span><b>SocialMEI<span>.IA</span></b></a><span class="preview-version">${before ? "V2 atual" : "V2.1 experimental"}</span><div class="preview-controls"><label for="previewState">Cenário fictício</label><select id="previewState"><option value="sample">Com registros</option><option value="empty">Sem registros</option><option value="error">Falha de fonte</option><option value="loading">Carregamento</option></select><button type="button" id="previewTheme" aria-label="Alternar tema">Tema escuro</button><a id="previewCompare" href="?view=${before ? "after" : "before"}">${before ? "Ver V2.1" : "Comparar V2"}</a></div>`;
    q("#app").prepend(tools);
    const feedback = make("p", "Prévia isolada · dados fictícios.", "preview-disclosure");
    feedback.id = "previewFeedback";
    feedback.setAttribute("role", "status");
    q("#mainContent").prepend(feedback);
    q("#previewState").addEventListener("change", (event) => stateChange(event.target.value));
    q("#previewTheme").addEventListener("click", () => {
      const dark = document.documentElement.dataset.theme !== "dark";
      SocialMEIThemes.select(dark ? "dark" : "light");
      q("#previewTheme").textContent = dark ? "Tema claro" : "Tema escuro";
    });
    const nativeAfter = SocialMEIReportUI.afterRender;
    SocialMEIReportUI.afterRender = (...args) => {
      nativeAfter(...args);
      decorate();
      if (!before) morphCharts();
    };
    if (!before) {
      const options = q(".report-period-options");
      options.querySelector("summary").textContent = "Ajustar período e opções";
      options.append(q(".management-report-period > .management-card-header"));
      const caption = make("span", undefined, "v21-range");
      caption.dataset.currentPeriod = "";
      q("#reportQuickPeriods").after(caption);
      document.addEventListener(
        "submit",
        (event) => {
          if (event.target.id === "reportGenerateForm") generate(event);
        },
        true,
      );
      const nativeClose = closeModal;
      closeModal = function (id) {
        if (id === "reportGenerateModal" && generating) {
          generation++;
          generating = false;
          q("#previewFeedback").textContent = "Geração cancelada. Nenhuma cópia foi guardada.";
        }
        return nativeClose(id);
      };
    }
    const nativeOpen = openModal;
    openModal = function (id) {
      nativeOpen(id);
      if (!before && ["reportGenerateModal", "periodModal"].includes(id)) {
        SocialMEIMotion.animate(
          q("#" + id + " .modal"),
          [
            { opacity: 0, transform: "translateY(10px) scale(.99)" },
            { opacity: 1, transform: "none" },
          ],
          220,
        );
      }
    };
    getManagementDataOrigin = () => ({
      label: "Dados fictícios",
      description:
        "Exemplo isolado do Ateliê Aurora. Registros e histórico somente na memória desta página, sem sincronização ou conexão externa.",
    });
    const memoryCopy = () => {
      const notice = q("#reportHistoryNotice");
      const text =
        "Cópias fictícias desta prévia. Ficam apenas nesta página e desaparecem ao recarregar.";
      if (notice.textContent !== text) notice.textContent = text;
      q("#reportGenerateBody")
        .querySelectorAll("p")
        .forEach((p) => {
          if (p.textContent.startsWith("Cópia congelada neste navegador."))
            p.textContent =
              "Cópia congelada na memória desta prévia. Recarregar remove o histórico; novos filtros não alteram este relatório.";
          if (p.textContent.startsWith("Um resumo dos indicadores e dos registros datados."))
            p.textContent =
              "Preparação local de dados fictícios. CSV usa o snapshot; PDF utiliza a impressão do navegador. O histórico desta prévia desaparece ao recarregar.";
        });
    };
    new MutationObserver(memoryCopy).observe(q("#reportGenerateBody"), {
      childList: true,
      subtree: true,
    });
    new MutationObserver(memoryCopy).observe(q("#reportHistoryNotice"), { childList: true });
    document.addEventListener(
      "toggle",
      (event) => {
        if (
          !before &&
          event.target.matches(
            "#reportsView .report-detail[open], #reportsView .management-chart-alternative[open]",
          )
        ) {
          const content = event.target.querySelector(".report-detail-body, .table-wrap");
          if (content)
            SocialMEIMotion.animate(
              content,
              [
                { opacity: 0.6, transform: "translateY(-4px)" },
                { opacity: 1, transform: "none" },
              ],
              180,
            );
        }
      },
      true,
    );
    document.addEventListener("click", (event) => {
      if (event.target.closest("[data-preview-record]")) {
        feedback.textContent =
          "Esta prévia mantém os registros fictícios em Relatórios. A edição comercial continua na aplicação oficial.";
        feedback.scrollIntoView({
          block: "nearest",
          behavior: SocialMEIMotion.reduced ? "instant" : "smooth",
        });
      }
    });
    seed();
    selectedPeriod = "30 dias";
    selectedReportTab = "Resumo";
    customRange = null;
    SocialMEIExperience.enterApp("Relatórios");
    SocialMEIThemes.select(
      new URLSearchParams(location.search).get("theme") === "dark" ? "dark" : "light",
    );
    q("#previewTheme").textContent =
      document.documentElement.dataset.theme === "dark" ? "Tema claro" : "Tema escuro";
    document.title = "SocialMEI · Relatórios " + (before ? "V2 atual" : "V2.1 experimental");
    document.documentElement.dataset.previewReady = "true";
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
