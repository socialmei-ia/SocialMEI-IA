/* Native V22 attachments: workspace PDF knowledge and live aggregate reports. */
(() => {
  const bridge = window.SocialMEIV22;
  if (!bridge?.remote || window.SocialMEIKnowledge) return;
  const auth = window.SocialMEIAuth;
  const canManage = ["owner", "admin"].includes(bridge.identity?.papel);
  const style = document.createElement("style");
  style.textContent =
    ".sm-data{margin:22px 0;padding:22px;border:1px solid var(--b);border-radius:16px;background:var(--w);color:var(--t)}" +
    ".sm-data h2{font-size:20px;margin:0 0 6px}.sm-data p{color:var(--m);margin-bottom:14px}" +
    ".sm-data .sm-controls{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:12px 0}" +
    ".sm-data input,.sm-data select{min-height:44px;border:1px solid var(--b);border-radius:10px;padding:10px;max-width:100%;font:inherit;color:var(--t);background:var(--w)}" +
    ".sm-data table{table-layout:fixed;border-collapse:collapse}.sm-data th,.sm-data td{text-align:left;padding:8px 4px;border-bottom:1px solid var(--b);overflow-wrap:anywhere;font-size:14px}.sm-data caption{text-align:left;margin:12px 0}" +
    ".sm-data button{min-height:44px;border-radius:10px;border:1px solid var(--b);background:var(--pl);color:var(--t);padding:9px 14px;cursor:pointer}" +
    ".sm-data button:disabled{opacity:.55;cursor:default}.sm-data ul{padding-left:18px}" +
    ".sm-data li{margin:8px 0;overflow-wrap:anywhere}.sm-data small{color:var(--m)}";
  document.head.appendChild(style);
  let reportsLoaded = false;
  function el(type, textValue) {
    const element = document.createElement(type);
    if (textValue !== undefined) element.textContent = String(textValue);
    return element;
  }
  function currentView() {
    return document.getElementById("v");
  }
  function panel(title, detail) {
    const section = el("section");
    section.className = "sm-data";
    section.append(el("h2", title), el("p", detail));
    return section;
  }
  function status(section) {
    const node = el("p");
    node.setAttribute("role", "status");
    node.setAttribute("aria-live", "polite");
    section.appendChild(node);
    return node;
  }
  async function uploadFile(selected, previous) {
    if (!selected || selected.size > 2097152 || !selected.name.toLowerCase().endsWith(".pdf"))
      throw Error("Selecione um PDF de até 2 MB.");
    const user = bridge.identity;
    const identity = user.usuario.id + ":" + user.negocio.id;
    const response = await fetch(
      "/api/v1/knowledge/pdf" +
        (previous ? "/" + encodeURIComponent(previous.id) : "") +
        "?filename=" +
        encodeURIComponent(selected.name),
      {
        method: previous ? "PUT" : "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "Content-Type": "application/pdf",
          "X-SocialMEI-Client": "browser",
          "X-SocialMEI-CSRF": user.csrf_token,
          "X-SocialMEI-Identity": identity,
          ...(previous ? { "If-Match": previous.sha256 } : {}),
        },
        body: selected,
      },
    );
    const data = await response.json().catch(() => null);
    if (identity !== bridge.identity?.usuario.id + ":" + bridge.identity?.negocio.id)
      throw Error("A conta mudou. Atualize a página.");
    if (!response.ok) throw Error(data?.detail || "Não foi possível processar o PDF.");
    return data;
  }
  async function knowledge(section, result, list) {
    try {
      const data = await bridge.request("/knowledge/pdf");
      list.replaceChildren();
      if (!data.items.length) list.append(el("li", "Nenhum PDF cadastrado."));
      for (const record of data.items) {
        const item = el("li");
        item.appendChild(el("strong", record.filename + " — "));
        item.appendChild(
          el(
            "small",
            record.page_count +
              " página(s) · " +
              (record.status === "indexed" ? "texto indexado" : "sem texto extraível"),
          ),
        );
        if (record.size_bytes)
          item.append(el("small", " · " + Math.ceil(record.size_bytes / 1024) + " KB"));
        if (record.uploaded_at)
          item.append(
            el("small", " · " + new Date(record.uploaded_at).toLocaleDateString("pt-BR")),
          );
        if (record.status === "no_text")
          item.append(
            el(
              "p",
              "Sem texto extraível. Este documento precisa de OCR antes de alimentar as consultas.",
            ),
          );
        if (record.sha256) {
          const download = el("button", "Baixar PDF");
          download.type = "button";
          download.onclick = async () => {
            download.disabled = true;
            try {
              const identity = bridge.identity.usuario.id + ":" + bridge.identity.negocio.id;
              const response = await fetch(
                "/api/v1/knowledge/pdf/" + encodeURIComponent(record.id) + "/download",
                {
                  credentials: "same-origin",
                  cache: "no-store",
                  headers: { "X-SocialMEI-Identity": identity },
                },
              );
              if (
                !section.isConnected ||
                identity !== bridge.identity?.usuario.id + ":" + bridge.identity?.negocio.id
              )
                throw Error("A conta mudou. Atualize a página.");
              if (!response.ok) throw Error("Download não autorizado ou indisponível.");
              const url = URL.createObjectURL(await response.blob());
              const link = el("a");
              link.href = url;
              link.download = record.filename;
              document.body.append(link);
              link.click();
              window.setTimeout(() => {
                URL.revokeObjectURL(url);
                link.remove();
              }, 30000);
            } catch (error) {
              result.textContent = error.message;
            } finally {
              download.disabled = false;
            }
          };
          item.append(download);
        }
        if (canManage && record.sha256) {
          const reprocess = el("button", "Reprocessar");
          reprocess.type = "button";
          reprocess.onclick = async () => {
            reprocess.disabled = true;
            try {
              await bridge.request(
                "/knowledge/pdf/" + encodeURIComponent(record.id) + "/reprocess",
                "POST",
                { sha256: record.sha256 },
              );
              await knowledge(section, result, list);
              result.textContent = "PDF reprocessado.";
            } catch (error) {
              result.textContent = error.message;
            } finally {
              reprocess.disabled = false;
            }
          };
          const replace = el("button", "Substituir PDF");
          replace.type = "button";
          const replacement = el("input");
          replacement.type = "file";
          replacement.accept = "application/pdf,.pdf";
          replacement.hidden = true;
          replacement.setAttribute("aria-label", "Substituir " + record.filename);
          replace.onclick = () => replacement.click();
          replacement.onchange = async () => {
            if (!replacement.files?.length) return;
            replace.disabled = true;
            try {
              await uploadFile(replacement.files[0], record);
              await knowledge(section, result, list);
              result.textContent = "PDF substituído e índice atualizado.";
            } catch (error) {
              result.textContent = error.message;
            } finally {
              replacement.value = "";
              replace.disabled = false;
            }
          };
          item.append(reprocess, replace, replacement);
        }
        if (canManage) {
          const remove = el("button", "Excluir");
          remove.type = "button";
          remove.style.marginLeft = "8px";
          remove.addEventListener("click", async () => {
            if (!confirm("Excluir o PDF deste negócio?")) return;
            try {
              await bridge.request("/knowledge/pdf/" + encodeURIComponent(record.id), "DELETE");
              result.textContent = "PDF excluído.";
              await knowledge(section, result, list);
            } catch (error) {
              result.textContent = error.message || "Não foi possível excluir.";
            }
          });
          item.appendChild(remove);
        }
        list.appendChild(item);
      }
      result.textContent = "Documentos privados deste negócio.";
    } catch (error) {
      result.textContent =
        error.status === 503
          ? "A base de PDFs ainda não foi habilitada no servidor."
          : error.message || "Não foi possível consultar os documentos.";
    }
  }
  function mountKnowledge(view) {
    if (view.querySelector("[data-sm-knowledge]")) return;
    const section = panel(
      "Documentos da IA",
      "Adicione PDFs do seu negócio e consulte os trechos encontrados por página. " +
        "A geração automática de respostas ainda depende de configuração específica.",
    );
    section.dataset.smKnowledge = "true";
    const results = status(section);
    const list = el("ul");
    if (canManage) {
      const controls = el("div");
      controls.className = "sm-controls";
      const file = el("input");
      file.type = "file";
      file.accept = "application/pdf,.pdf";
      file.setAttribute("aria-label", "Selecionar PDF");
      const upload = el("button", "Adicionar PDF");
      upload.type = "button";
      upload.addEventListener("click", async () => {
        const selected = file.files?.[0];
        if (!selected || selected.size > 2097152 || !selected.name.toLowerCase().endsWith(".pdf")) {
          results.textContent = "Selecione um PDF de até 2 MB.";
          return;
        }
        upload.disabled = true;
        results.textContent = "Enviando e indexando PDF…";
        try {
          const data = await uploadFile(selected);
          file.value = "";
          await knowledge(section, results, list);
          results.textContent =
            data.status === "indexed"
              ? "Documento indexado e disponível para consulta."
              : "PDF salvo, mas sem texto extraível. O arquivo pode ser digitalizado.";
        } catch (error) {
          results.textContent = error.message || "Falha no envio.";
        } finally {
          upload.disabled = false;
        }
      });
      controls.append(file, upload);
      section.appendChild(controls);
    }
    const controls = el("div");
    controls.className = "sm-controls";
    const search = el("input");
    search.type = "search";
    search.maxLength = 160;
    search.placeholder = "Pesquisar nos PDFs…";
    search.setAttribute("aria-label", "Pesquisar trechos dos PDFs");
    const button = el("button", "Buscar");
    button.type = "button";
    const matches = el("ul");
    button.addEventListener("click", async () => {
      const q = search.value.trim();
      if (q.length < 2) {
        results.textContent = "Digite pelo menos 2 caracteres.";
        return;
      }
      button.disabled = true;
      try {
        const data = await bridge.request("/knowledge/pdf/search?q=" + encodeURIComponent(q));
        matches.replaceChildren();
        for (const match of data.items) {
          matches.append(
            el("li", match.filename + ", página " + match.page + ": " + match.excerpt),
          );
        }
        if (!data.items.length) matches.append(el("li", "Nenhum trecho encontrado."));
        results.textContent = "Resultados extraídos dos documentos cadastrados.";
      } catch (error) {
        results.textContent = error.message || "Busca indisponível.";
      } finally {
        button.disabled = false;
      }
    });
    controls.append(search, button);
    section.append(controls, matches, list);
    view.appendChild(section);
    knowledge(section, results, list);
  }
  function mountReport(view) {
    if (view.querySelector("[data-sm-reports]")) return;
    const section = panel(
      "Dados do seu negócio",
      "Consulta os registros do negócio desta sessão. Escolha o período deste resumo.",
    );
    section.dataset.smReports = "true";
    const results = status(section);
    const summary = el("div");
    summary.className = "sm-controls";
    const period = el("select");
    period.setAttribute("aria-label", "Período do relatório online");
    for (const [days, label] of [
      [1, "Hoje"],
      [7, "Últimos 7 dias"],
      [30, "Últimos 30 dias"],
      [90, "Últimos 90 dias"],
      [365, "Últimos 365 dias"],
    ]) {
      const option = el("option", label);
      option.value = days;
      period.append(option);
    }
    period.value = "30";
    const rows = el("div");
    const actions = el("div");
    actions.className = "sm-controls";
    const pdfButton = el("button", "Salvar PDF / imprimir");
    pdfButton.type = "button";
    let snapshot = null,
      sequence = 0;
    const identity = () => `${bridge.identity?.usuario.id}:${bridge.identity?.negocio.id}`;
    const scope = identity();
    const amount = (value) => {
      const parts = String(value).split(".");
      return /^-?\d+$/.test(parts[0]) && /^\d{1,2}$/.test(parts[1] || "")
        ? parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + parts[1].padEnd(2, "0")
        : "Indisponível";
    };
    const totals = (data) => [
      ...Object.entries(data.sales_by_status || {}).map(([state, item]) => [
        "Vendas",
        state,
        item.quantidade,
        amount(item.valor),
      ]),
      ...(data.finance_by_type_and_status || []).map((item) => [
        item.tipo === "receita" ? "Receitas" : "Despesas",
        item.status,
        item.quantidade,
        amount(item.valor),
      ]),
      ...(data.attendance || []).map((item) => [
        "Mensagens " + item.channel,
        item.origin === "synthetic" ? "Simuladas" : "Origem: " + item.origin,
        item.messages,
        "—",
      ]),
    ];
    function table(doc, data) {
      const grid = doc.createElement("table");
      grid.style.width = "100%";
      const caption = doc.createElement("caption");
      caption.textContent = "Vendas, financeiro e mensagens recebidas — fontes separadas";
      grid.append(caption);
      const head = doc.createElement("thead"),
        heading = doc.createElement("tr");
      for (const label of ["Origem", "Situação", "Quantidade", "Valor (R$)"]) {
        const cell = doc.createElement("th");
        cell.scope = "col";
        cell.textContent = label;
        heading.append(cell);
      }
      head.append(heading);
      grid.append(head);
      const body = doc.createElement("tbody");
      for (const row of totals(data)) {
        const line = doc.createElement("tr");
        for (const value of row) {
          const cell = doc.createElement("td");
          cell.textContent = value;
          line.append(cell);
        }
        body.append(line);
      }
      grid.append(body);
      return grid;
    }
    const exportButton = el("button", "Exportar CSV");
    exportButton.type = "button";
    exportButton.addEventListener("click", async () => {
      exportButton.disabled = true;
      try {
        if (!snapshot || identity() !== scope)
          throw Error("Recarregue o relatório antes de exportar.");
        const response = await fetch(
          "/api/v1/reporting/overview.csv?days=" + snapshot.period_days,
          {
            credentials: "same-origin",
            cache: "no-store",
            headers: auth.headers(),
          },
        );
        if (!response.ok) throw Error("Exportação não autorizada ou indisponível.");
        if (identity() !== scope) throw Error("A sessão mudou. Recarregue antes de exportar.");
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a");
        link.href = url;
        link.download = "socialmei-relatorio.csv";
        document.body.appendChild(link);
        link.click();
        // Chromium needs the blob URL alive until the download begins.
        window.setTimeout(() => {
          URL.revokeObjectURL(url);
          link.remove();
        }, 30000);
      } catch (error) {
        results.textContent = error.message;
      } finally {
        exportButton.disabled = !snapshot;
      }
    });
    pdfButton.onclick = () => {
      if (!snapshot || identity() !== scope) return;
      document.querySelectorAll("[data-sm-report-print]").forEach((frame) => frame.remove());
      const frame = el("iframe");
      frame.dataset.smReportPrint = "true";
      frame.title = "Impressão do relatório do negócio";
      frame.tabIndex = -1;
      frame.style.cssText = "position:fixed;width:1px;height:1px;opacity:0;bottom:0;border:0";
      document.body.append(frame);
      const doc = frame.contentDocument;
      doc.open();
      doc.write(
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Relatório SocialMEI</title><style>@page{size:A4;margin:18mm}body{font:12pt Arial;color:#111}h1{font-size:20pt}table{border-collapse:collapse;margin-top:20px}th,td{text-align:left;border-bottom:1px solid #ccc;padding:8px}caption{text-align:left;margin:12px 0}p{line-height:1.5}</style></head><body></body></html>',
      );
      doc.close();
      for (const [tag, value] of [
        ["h1", "Relatório do negócio"],
        ["p", bridge.identity.negocio.nome],
        ["p", `Referência: ${snapshot.as_of} · últimos ${snapshot.period_days} dias`],
        ["p", snapshot.description || "Vendas e financeiro são fontes separadas."],
      ]) {
        const node = doc.createElement(tag);
        node.textContent = value;
        doc.body.append(node);
      }
      doc.body.append(table(doc, snapshot));
      frame.contentWindow.addEventListener(
        "afterprint",
        () => {
          frame.remove();
          pdfButton.focus();
        },
        { once: true },
      );
      frame.contentWindow.print();
      window.setTimeout(() => frame.remove(), 60000);
    };
    async function load() {
      const ticket = ++sequence;
      snapshot = null;
      exportButton.disabled = true;
      pdfButton.disabled = true;
      results.textContent = "Consultando o período selecionado…";
      rows.replaceChildren();
      summary.replaceChildren();
      try {
        const data = await bridge.request("/reporting/overview?days=" + period.value);
        if (!section.isConnected || ticket !== sequence || identity() !== scope) return;
        snapshot = data;
        summary.replaceChildren(
          el("strong", data.totals.clientes + " clientes"),
          el("strong", data.totals.itens_ativos + " itens ativos"),
          el("strong", data.totals.estoque_baixo + " com estoque baixo"),
        );
        rows.append(table(document, data));
        if (data.attendance === null)
          rows.append(el("p", "Atendimento ainda não disponível neste ambiente."));
        if (data.attendance_description) rows.append(el("p", data.attendance_description));
        if (!totals(data).length)
          rows.append(el("p", "Nenhuma venda ou lançamento neste período."));
        results.textContent = "Consulta concluída para os últimos " + data.period_days + " dias.";
        exportButton.disabled = false;
        pdfButton.disabled = false;
      } catch (error) {
        if (ticket === sequence)
          results.textContent = error.message || "Relatórios reais indisponíveis.";
      }
    }
    period.onchange = load;
    actions.append(period, exportButton, pdfButton);
    section.append(actions, summary, rows);
    view.appendChild(section);
    load();
  }
  function mount() {
    const view = currentView();
    if (!view) return;
    if (location.hash.startsWith("#/config/ia")) mountKnowledge(view);
    if (location.hash.startsWith("#/relatorios")) mountReport(view);
  }
  const originalRender = window.render;
  if (typeof originalRender === "function") {
    window.render = function (...args) {
      const output = originalRender.apply(this, args);
      queueMicrotask(mount);
      return output;
    };
  }
  window.SocialMEIKnowledge = { refresh: mount };
  queueMicrotask(mount);
  window.addEventListener("hashchange", () => queueMicrotask(mount));
})();
