/* Vendas: fonte explícita, sem escrita local como fallback da API. */
const SocialMEISales = (() => {
  const config = SOCIALMEI_CONFIG.vendas || { mode: "local" };
  const remote = config.mode !== "local";
  const fields = [
    "cliente_id",
    "produto_id",
    "data",
    "quantidade",
    "preco",
    "desconto",
    "pagamento",
    "observacao",
    "status",
  ];

  let localSales = [],
    ready = !remote,
    busy = false,
    problem = "",
    pendingImport = null;
  let base = "",
    scope = "";
  try {
    if (remote) {
      if (config.mode !== "remote" || !config.apiBaseUrl || !config.workspaceKey)
        throw new Error("Configuração remota de Vendas incompleta.");
      const url = new URL(config.apiBaseUrl, location.href);
      if (!/^https?:$/.test(url.protocol) || url.username || url.password || url.search || url.hash)
        throw new Error("Endereço da API de Vendas inválido.");
      base = url.href.replace(/\/$/, "");
      scope = base + "|" + config.workspaceKey;
      for (const name of ["clientes", "produtos"]) {
        const linked = SOCIALMEI_CONFIG[name];
        if (
          linked?.mode !== "remote" ||
          linked.workspaceKey !== config.workspaceKey ||
          new URL(linked.apiBaseUrl, location.href).href.replace(/\/$/, "") !== base
        )
          throw new Error("Vendas exige Clientes e Catálogo remotos na mesma API e workspace.");
      }
    }
  } catch (error) {
    problem = error.message;
    base = "";
  }
  function stored(key, fallback = null) {
    try {
      return JSON.parse(localStorage.getItem(key)) ?? fallback;
    } catch (_) {
      return fallback;
    }
  }
  function persist(key, value) {
    if (!socialmeiStorageSet(key, JSON.stringify(value), "a identidade de importação"))
      throw new Error("Não foi possível preservar a identidade da operação neste navegador.");
  }
  function newOrigin() {
    return SocialMEIClients.newId();
  }
  function payload(sale) {
    return Object.fromEntries(
      fields.filter((k) => sale[k] !== undefined).map((k) => [k, cloneData(sale[k])]),
    );
  }
  function normalize(sale) {
    if (
      !sale ||
      !Number.isSafeInteger(sale.id) ||
      !Number.isSafeInteger(sale.versao) ||
      sale.versao < 1 ||
      typeof sale.cliente !== "string" ||
      typeof sale.item !== "string" ||
      !Number.isFinite(sale.valor) ||
      sale.valor < 0 ||
      !Number.isSafeInteger(sale.quantidade) ||
      sale.quantidade < 1 ||
      !["Pago", "Pendente", "Cancelado", "Rascunho"].includes(sale.status) ||
      typeof sale.data !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(sale.data)
    )
      throw new Error("Resposta inválida da API de Vendas.");
    return { ...sale };
  }
  async function request(path, method = "GET", data) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(base + path, {
        method,
        headers: {
          Accept: "application/json",
          ...(typeof SocialMEIAuth !== "undefined" ? SocialMEIAuth.headers() : {}),
          ...(data ? { "Content-Type": "application/json" } : {}),
        },
        body: data ? JSON.stringify(data) : undefined,
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
      });
      if (!response.ok) {
        const error = new Error(
          response.status === 409
            ? "Há um conflito de versão, estoque ou importação. Recarregue e confira antes de salvar."
            : response.status === 422
              ? "A API recusou os campos enviados. Confira os dados e os limites do cadastro."
              : `API de Vendas indisponível (HTTP ${response.status}).`,
        );
        if ([409, 422].includes(response.status)) {
          const body = await response.json().catch(() => null);
          if (typeof body?.detail === "string") error.message = body.detail.slice(0, 800);
        }
        error.status = response.status;
        throw error;
      }
      return response.status === 204 ? null : await response.json();
    } finally {
      clearTimeout(timer);
    }
  }
  function status() {
    const host = document.getElementById("salesSourceStatus");
    if (!host) return;
    host.hidden = !remote;
    const pending = stored("socialmei-sale-operation-pending-v1");
    host.innerHTML = remote
      ? `<div class="management-settings-row"><div><b>Vendas compartilhadas · ${busy ? "aguarde…" : ready ? "conectado" : "indisponível"}</b><p>${escapeHtml(problem ? problem + " A lista exibida pode estar desatualizada; recarregue." : "Vendas e estoque são salvos juntos. " + (SocialMEIFinance.remote ? "O Financeiro compartilhado registra os recebimentos separadamente." : "O financeiro continua separado e local."))}</p></div><button class="management-button" data-sales-reload ${busy ? "disabled" : ""}>Recarregar</button><button class="management-button" data-sales-import ${busy || !ready ? "disabled" : ""}>Importar vendas locais</button>${pending?.scope === scope ? `<button class="management-button" data-sales-recover ${busy ? "disabled" : ""}>Recuperar operação pendente</button>` : ""}</div>`
      : "";
  }
  function changed() {
    document.dispatchEvent(new CustomEvent("socialmei-data-change"));
    renderCurrentView();
    status();
  }
  async function run(action, needsReady = true) {
    if (busy) {
      toast("Aguarde", "Uma operação de Vendas está em andamento.");
      return null;
    }
    if (!base || (needsReady && !ready)) {
      toast("Vendas indisponível", problem || "Recarregue a lista antes de salvar.");
      return null;
    }
    busy = true;
    status();
    const controls = needsReady
      ? [
          ...document.querySelectorAll(
            "#createForm input, #createForm select, #createForm textarea, #createSubmit, #reviewConfirmAction, #confirmSaleImport, [data-sale-paid], [data-sale-duplicate], [data-sale-register]",
          ),
        ].map((element) => [element, element.disabled])
      : [];
    controls.forEach(([element]) => {
      element.disabled = true;
    });
    try {
      const result = await action();
      problem = "";
      return result;
    } catch (error) {
      problem =
        error.name === "AbortError"
          ? "A API demorou para responder. Confira os dados antes de tentar novamente."
          : error.message || "Não foi possível acessar a API de Vendas.";
      if (error.status !== 422) ready = false;
      toast("Operação não concluída", problem);
      return null;
    } finally {
      busy = false;
      controls.forEach(([element, disabled]) => {
        if (element.isConnected) element.disabled = disabled;
      });
      status();
    }
  }
  async function loadRemote() {
    const list = await request("/vendas");
    if (!Array.isArray(list)) throw new Error("Lista de Vendas inválida.");
    const next = list.map(normalize);
    if (new Set(next.map((v) => v.id)).size !== next.length)
      throw new Error("IDs repetidos na resposta de Vendas.");
    appData.vendas = next;
    ready = true;
    changed();
  }
  async function refresh() {
    if (typeof SocialMEIAuth !== "undefined" && SocialMEIAuth.remote) {
      await SocialMEIAuth.ready;
      if (!SocialMEIAuth.current) return null;
      scope = base + "|" + SocialMEIAuth.current.negocio.slug;
    }
    return run(async () => {
      await loadRemote();
      return true;
    }, false);
  }
  async function operation(path, method, data, recovering = false) {
    return run(async () => {
      const key = "socialmei-sale-operation-pending-v1";
      let pending = stored(key);
      const signature = JSON.stringify({ path, method, data });
      if (!recovering && pending && (pending.scope !== scope || pending.signature !== signature))
        throw new Error(
          "Existe uma operação sem confirmação. Use Recuperar operação pendente antes de salvar outra.",
        );
      if (!pending) {
        pending = { scope, path, method, data, signature, operation_id: newOrigin() };
        persist(key, pending);
      }
      let result;
      try {
        result = normalize(
          await request(pending.path, pending.method, {
            ...pending.data,
            operation_id: pending.operation_id,
          }),
        );
      } catch (error) {
        if ([404, 409, 422].includes(error.status)) persist(key, null);
        throw error;
      }
      persist(key, null);
      appData.vendas = result.excluida
        ? appData.vendas.filter((v) => v.id !== result.id)
        : [result, ...appData.vendas.filter((v) => v.id !== result.id)];
      changed();
      // A operação já foi aceita; falha de leitura posterior não a desfaz.
      try {
        await loadRemote();
      } catch (_) {
        ready = false;
        problem = "Operação salva. Recarregue para conferir a lista atual.";
      }
      await SocialMEIProducts.refresh();
      return result;
    }, !recovering);
  }
  function create(sale) {
    return operation("/vendas", "POST", payload(sale));
  }
  function update(sale, changes) {
    const data = payload(changes);
    delete data.status;
    return operation(`/vendas/${sale.id}`, "PATCH", { ...data, expected_version: sale.versao });
  }
  function transition(sale, action) {
    return operation(`/vendas/${sale.id}/${action}`, "POST", { expected_version: sale.versao });
  }
  function remove(sale) {
    return transition(sale, "excluir");
  }
  function recover() {
    const pending = stored("socialmei-sale-operation-pending-v1");
    if (pending?.scope === scope)
      return operation(pending.path, pending.method, pending.data, true);
  }
  function duplicate(sale) {
    if (!sale.cliente_id || !sale.produto_id) {
      toast("Vínculos ausentes", "Crie uma venda selecionando cliente e item atuais.");
      return Promise.resolve(null);
    }
    return create({
      cliente_id: sale.cliente_id,
      produto_id: sale.produto_id,
      data: todayISO(),
      quantidade: sale.quantidade,
      preco: sale.preco ?? Math.round(((sale.valor + sale.desconto) / sale.quantidade) * 100) / 100,
      desconto: sale.desconto || 0,
      pagamento: sale.pagamento || "Pix",
      observacao: sale.observacao || "",
      status: "Rascunho",
    });
  }
  function mappedLegacyId(kind, name) {
    const local =
      kind === "client"
        ? SocialMEIClients.localData(appData).clientes
        : SocialMEIProducts.localData(appData).produtos;
    const matches = local.filter((r) => r.nome.toLowerCase() === String(name || "").toLowerCase());
    if (matches.length !== 1) return null;
    return stored(`socialmei-${kind}-links-v1`, {})[scope]?.[matches[0].id] ?? null;
  }
  async function previewImport() {
    return run(async () => {
      if (!localSales.length) throw new Error("Não há vendas no snapshot local para importar.");
      if (localSales.length > 500)
        throw new Error("Este fluxo importa até 500 vendas. Divida o dataset antes de continuar.");
      let origem = stored("socialmei-sale-origin-v1");
      if (!origem) {
        origem = newOrigin();
        persist("socialmei-sale-origin-v1", origem);
      }
      const lote = {
        origem,
        itens: localSales.map((c) => ({
          local_id: c.id,
          venda: {
            cliente: c.cliente,
            item: c.item || "",
            data: c.data,
            quantidade: c.quantidade ?? 1,
            preco: c.preco ?? null,
            desconto: c.desconto ?? 0,
            valor: c.valor,
            status: c.status,
            pagamento: c.pagamento || "Não informado",
            observacao: c.observacao || "",
            cliente_id: mappedLegacyId("client", c.cliente),
            produto_id: mappedLegacyId("product", c.item),
          },
          extras: Object.fromEntries([["original_local", cloneData(c)]]),
        })),
      };
      const preview = await request("/vendas/importacoes/preview", "POST", lote);
      const counts = preview.itens.reduce((n, r) => ({ ...n, [r.acao]: (n[r.acao] || 0) + 1 }), {});
      pendingImport = preview.pode_importar ? lote : null;
      $("saleImportSummary").textContent =
        `${counts.criar || 0} novos · ${counts.existente || 0} já importados · ${counts.conflito || 0} conflitos · ${counts.excluido || 0} excluídos. Histórico preservado sem movimentar estoque. Importe Clientes e Catálogo antes para mapear os vínculos.`;
      $("confirmSaleImport").disabled = !pendingImport;
      openModal("saleImportModal");
      return true;
    });
  }
  async function confirmImport() {
    if (!pendingImport) return;
    const done = await run(async () => {
      const result = await request("/vendas/importacoes/confirmar", "POST", pendingImport);
      const links = stored("socialmei-sale-links-v1", {});
      links[scope] = {
        ...(links[scope] || {}),
        ...Object.fromEntries(result.itens.map((r) => [r.local_id, r.venda_id])),
      };
      persist("socialmei-sale-links-v1", links);
      pendingImport = null;
      return true;
    });
    if (done) {
      await closeModal("saleImportModal");
      await refresh();
    }
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-sales-reload]")) refresh();
    if (event.target.closest("[data-sales-import]")) previewImport();
    if (event.target.closest("#confirmSaleImport")) confirmImport();
    if (event.target.closest("[data-sales-recover]")) recover();
    const register = event.target.closest("[data-sale-register]");
    if (register) {
      const sale = appData.vendas.find((v) => v.id === Number(register.dataset.saleRegister));
      if (sale)
        transition(sale, "registrar").then((saved) => {
          if (saved) {
            openRecord("sales", saved.id);
            toast("Venda registrada", "Estoque aplicado uma única vez.");
          }
        });
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    status();
    if (remote) refresh();
  });
  return {
    remote,
    refresh,
    create,
    update,
    remove,
    transition,
    duplicate,
    recover,
    attach(data) {
      localSales = cloneData(data.vendas);
      if (remote) data.vendas = [];
    },
    localData(data) {
      return remote ? { ...data, vendas: cloneData(localSales) } : data;
    },
    matchesClient(sale, client) {
      return remote
        ? sale.cliente_id === client.id
        : normalizedText(sale.cliente) === normalizedText(client.nome);
    },
    matchesProduct(sale, product) {
      return remote
        ? sale.produto_id === product.id
        : normalizedText(sale.item) === normalizedText(product.nome);
    },
    backup() {
      return remote
        ? {
            source: scope,
            vendas: cloneData(appData.vendas),
            exportedAt: new Date().toISOString(),
          }
        : null;
    },
  };
})();
