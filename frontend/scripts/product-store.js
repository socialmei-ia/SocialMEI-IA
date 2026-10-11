/* Catálogo: fonte explícita, sem escrita local como fallback da API. */
const SocialMEIProducts = (() => {
  const config = SOCIALMEI_CONFIG.produtos || { mode: "local" };
  const remote = config.mode !== "local";
  const fields = ["nome", "tipo", "preco", "custo", "estoque", "minimo", "status"];

  let localProducts = [],
    ready = !remote,
    busy = false,
    problem = "",
    pendingImport = null;
  let base = "",
    scope = "";
  try {
    if (remote) {
      if (config.mode !== "remote" || !config.apiBaseUrl || !config.workspaceKey)
        throw new Error("Configuração remota de Catálogo incompleta.");
      const url = new URL(config.apiBaseUrl, location.href);
      if (!/^https?:$/.test(url.protocol) || url.username || url.password || url.search || url.hash)
        throw new Error("Endereço da API de Catálogo inválido.");
      base = url.href.replace(/\/$/, "");
      scope = base + "|" + config.workspaceKey;
    }
  } catch (error) {
    problem = error.message;
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
  function payload(product) {
    return Object.fromEntries(
      fields.filter((k) => product[k] !== undefined).map((k) => [k, cloneData(product[k])]),
    );
  }
  function normalize(product) {
    if (
      !product ||
      !Number.isSafeInteger(product.id) ||
      !Number.isSafeInteger(product.versao) ||
      product.versao < 1 ||
      typeof product.nome !== "string" ||
      !["Produto", "Serviço"].includes(product.tipo) ||
      !Number.isFinite(product.preco) ||
      product.preco < 0 ||
      !Number.isFinite(product.custo) ||
      product.custo < 0 ||
      (product.tipo === "Produto"
        ? ![product.estoque, product.minimo].every((n) => Number.isSafeInteger(n) && n >= 0)
        : product.estoque !== null || product.minimo !== null)
    )
      throw new Error("Resposta inválida da API de catálogo.");
    return { ...product };
  }
  async function request(path, method = "GET", data) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(base + path, {
        method,
        headers: {
          Accept: "application/json",
          ...(data ? { "Content-Type": "application/json" } : {}),
        },
        body: data ? JSON.stringify(data) : undefined,
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
      if (!response.ok) {
        const error = new Error(
          response.status === 409
            ? "Os dados mudaram ou há um conflito de importação. Recarregue e confira antes de salvar."
            : response.status === 422
              ? "A API recusou os campos enviados. Confira os dados e os limites do cadastro."
              : `API de Catálogo indisponível (HTTP ${response.status}).`,
        );
        error.status = response.status;
        throw error;
      }
      return response.status === 204 ? null : await response.json();
    } finally {
      clearTimeout(timer);
    }
  }
  function status() {
    const host = document.getElementById("productsSourceStatus");
    if (!host) return;
    host.hidden = !remote;
    host.innerHTML = remote
      ? `<div class="management-settings-row"><div><b>Catálogo compartilhado · ${busy ? "aguarde…" : ready ? "conectado" : "indisponível"}</b><p>${escapeHtml(problem ? problem + " A lista exibida pode estar desatualizada; recarregue." : "O catálogo é salvo na API. Vendas continuam locais e não movimentam este estoque automaticamente.")}</p></div><button class="management-button" data-products-reload ${busy ? "disabled" : ""}>Recarregar</button><button class="management-button" data-products-import ${busy || !ready ? "disabled" : ""}>Importar catálogo local</button></div>`
      : "";
  }
  function changed() {
    document.dispatchEvent(new CustomEvent("socialmei-data-change"));
    renderCurrentView();
    status();
  }
  async function run(action, needsReady = true) {
    if (busy) {
      toast("Aguarde", "Uma operação de Catálogo está em andamento.");
      return null;
    }
    if (!base || (needsReady && !ready)) {
      toast("Catálogo indisponível", problem || "Recarregue a lista antes de salvar.");
      return null;
    }
    busy = true;
    status();
    const controls = needsReady
      ? [
          ...document.querySelectorAll(
            "#createForm input, #createForm select, #createForm textarea, #createSubmit, #reviewConfirmAction, #confirmProductImport, [data-adjust-stock], [data-stock]",
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
          : error.message || "Não foi possível acessar a API de Catálogo.";
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
  async function refresh() {
    return run(async () => {
      const list = await request("/produtos");
      if (!Array.isArray(list)) throw new Error("Lista de Catálogo inválida.");
      const next = list.map(normalize);
      if (new Set(next.map((c) => c.id)).size !== next.length)
        throw new Error("IDs repetidos na resposta de Catálogo.");
      appData.produtos = next;
      ready = true;
      changed();
      return true;
    }, false);
  }
  async function create(product) {
    return run(async () => {
      const data = payload(product);
      const key = "socialmei-product-create-pending-v1";
      let pending = stored(key);
      if (
        pending &&
        (pending.scope !== scope || JSON.stringify(pending.data) !== JSON.stringify(data))
      )
        throw new Error(
          "Há um cadastro anterior sem confirmação. Reenvie os mesmos dados para recuperar o resultado antes de criar outro.",
        );
      if (!pending) {
        pending = { scope, data, origem: newOrigin() };
        persist(key, pending);
      }
      // Uma origem estável por cadastro torna seguro repetir após perda da resposta.
      let result;
      try {
        result = await request("/produtos/importacoes/confirmar", "POST", {
          origem: pending.origem,
          itens: [{ local_id: 0, produto: data }],
        });
      } catch (error) {
        if (error.status === 422) persist(key, null);
        throw error;
      }
      const id = result.itens?.[0]?.produto_id;
      if (!Number.isSafeInteger(id)) throw new Error("Mapeamento de criação inválido.");
      const saved = normalize(await request("/produtos/" + id));
      appData.produtos = [saved, ...appData.produtos.filter((c) => c.id !== id)];
      persist(key, null);
      changed();
      return saved;
    });
  }
  async function update(product, changes) {
    return run(async () => {
      const saved = normalize(
        await request("/produtos/" + product.id, "PATCH", {
          ...payload(changes),
          expected_version: product.versao,
        }),
      );
      appData.produtos = appData.produtos.map((c) => (c.id === saved.id ? saved : c));
      changed();
      return saved;
    });
  }
  async function remove(product) {
    return run(async () => {
      await request(`/produtos/${product.id}?expected_version=${product.versao}`, "DELETE");
      appData.produtos = appData.produtos.filter((c) => c.id !== product.id);
      changed();
      return true;
    });
  }
  async function adjustStock(product, delta) {
    return run(async () => {
      const saved = normalize(
        await request(`/produtos/${product.id}/estoque`, "POST", {
          delta,
          expected_version: product.versao,
        }),
      );
      appData.produtos = appData.produtos.map((p) => (p.id === saved.id ? saved : p));
      changed();
      return saved;
    });
  }
  async function previewImport() {
    return run(async () => {
      if (!localProducts.length)
        throw new Error("Não há produtos no snapshot local para importar.");
      if (localProducts.length > 500)
        throw new Error(
          "Este fluxo importa até 500 produtos. Divida o dataset antes de continuar.",
        );
      let origem = stored("socialmei-product-origin-v1");
      if (!origem) {
        origem = newOrigin();
        persist("socialmei-product-origin-v1", origem);
      }
      const lote = {
        origem,
        itens: localProducts.map((c) => ({
          local_id: c.id,
          produto: payload(c),
          extras: Object.fromEntries(
            Object.entries(c).filter(([k]) => k !== "id" && !fields.includes(k)),
          ),
        })),
      };
      const preview = await request("/produtos/importacoes/preview", "POST", lote);
      const counts = preview.itens.reduce((n, r) => ({ ...n, [r.acao]: (n[r.acao] || 0) + 1 }), {});
      pendingImport = preview.pode_importar ? lote : null;
      $("productImportSummary").textContent =
        `${counts.criar || 0} novos · ${counts.existente || 0} já importados · ${counts.conflito || 0} conflitos · ${counts.excluido || 0} excluídos. O snapshot local será preservado.`;
      $("confirmProductImport").disabled = !pendingImport;
      openModal("productImportModal");
      return true;
    });
  }
  async function confirmImport() {
    if (!pendingImport) return;
    const done = await run(async () => {
      const result = await request("/produtos/importacoes/confirmar", "POST", pendingImport);
      const links = stored("socialmei-product-links-v1", {});
      links[scope] = {
        ...(links[scope] || {}),
        ...Object.fromEntries(result.itens.map((r) => [r.local_id, r.produto_id])),
      };
      persist("socialmei-product-links-v1", links);
      pendingImport = null;
      return true;
    });
    if (done) {
      await closeModal("productImportModal");
      await refresh();
    }
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-products-reload]")) refresh();
    if (event.target.closest("[data-products-import]")) previewImport();
    if (event.target.closest("#confirmProductImport")) confirmImport();
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
    adjustStock,
    attach(data) {
      localProducts = cloneData(data.produtos);
      if (remote) data.produtos = [];
    },
    localData(data) {
      return remote ? { ...data, produtos: cloneData(localProducts) } : data;
    },
    backup() {
      return remote
        ? {
            source: scope,
            produtos: cloneData(appData.produtos),
            exportedAt: new Date().toISOString(),
          }
        : null;
    },
  };
})();
