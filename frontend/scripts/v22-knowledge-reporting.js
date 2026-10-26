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
    ".sm-data input{min-height:44px;border:1px solid var(--b);border-radius:10px;padding:10px;max-width:100%}" +
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
  async function knowledge(section, result, list) {
    try {
      const data = await bridge.request("/knowledge/pdf");
      list.replaceChildren();
      if (!data.items.length) list.append(el("li", "Nenhum PDF cadastrado."));
      for (const record of data.items) {
        const item = el("li");
        item.appendChild(el("strong", record.filename + " — "));
        item.appendChild(
          el("small", record.page_count + " página(s) · " +
            (record.status === "indexed" ? "texto indexado" : "sem texto extraível")),
        );
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
      result.textContent = error.status === 503
        ? "A base de PDFs ainda não foi habilitada no servidor."
        : error.message || "Não foi possível consultar os documentos.";
    }
  }
  function mountKnowledge(view) {
    if (view.querySelector('[data-sm-knowledge]')) return;
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
          const user = bridge.identity;
          const url = "/api/v1/knowledge/pdf?filename=" + encodeURIComponent(selected.name);
          const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
            headers: {
              "Content-Type": "application/pdf",
              "X-SocialMEI-Client": "browser",
              "X-SocialMEI-CSRF": user.csrf_token,
              "X-SocialMEI-Identity": user.usuario.id + ":" + user.negocio.id,
            },
            body: selected,
          });
          const data = await response.json().catch(() => null);
          if (!response.ok) throw Error(data?.detail || "Não foi possível processar o PDF.");
          file.value = "";
          await knowledge(section, results, list);
          results.textContent = data.status === "indexed"
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
          matches.append(el("li", match.filename + ", página " + match.page + ": " + match.excerpt));
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
    if (view.querySelector('[data-sm-reports]')) return;
    const section = panel(
      "Dados reais do PostgreSQL",
      "Indicadores por negócio. As informações de demonstração não entram nesta consulta.",
    );
    section.dataset.smReports = "true";
    const results = status(section);
    const summary = el("div");
    summary.className = "sm-controls";
    const exportButton = el("button", "Exportar CSV");
    exportButton.type = "button";
    exportButton.addEventListener("click", async () => {
      exportButton.disabled = true;
      try {
        const response = await fetch("/api/v1/reporting/overview.csv?days=30", {
          credentials: "same-origin", cache: "no-store",
        });
        if (!response.ok) throw Error("Exportação não autorizada ou indisponível.");
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a");
        link.href = url;
        link.download = "socialmei-relatorio.csv";
        link.click();
        URL.revokeObjectURL(url);
      } catch (error) {
        results.textContent = error.message;
      } finally {
        exportButton.disabled = false;
      }
    });
    section.append(summary, exportButton);
    view.appendChild(section);
    bridge.request("/reporting/overview?days=30").then((data) => {
      summary.replaceChildren(
        el("strong", data.totals.clientes + " clientes"),
        el("strong", data.totals.itens_ativos + " itens ativos"),
        el("strong", data.totals.estoque_baixo + " com estoque baixo"),
      );
      results.textContent = "Consulta concluída para os últimos " + data.period_days + " dias.";
    }).catch((error) => {
      results.textContent = error.message || "Relatórios reais indisponíveis.";
      exportButton.disabled = true;
    });
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
