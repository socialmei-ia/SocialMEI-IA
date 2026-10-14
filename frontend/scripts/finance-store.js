/* Financeiro: fonte explícita, sem escrita local como fallback da API. */
const SocialMEIFinance = (() => {
  const config = SOCIALMEI_CONFIG.financeiro || { mode: "local" };
  const remote = config.mode !== "local";
  const fields = ["cliente_id", "descricao", "pessoa", "tipo", "valor", "vencimento", "status"];

  let localEntries = [],
    ready = !remote,
    busy = false,
    problem = "",
    pendingImport = null;
  let base = "",
    scope = "";
  try {
    if (remote) {
      if (config.mode !== "remote" || !config.apiBaseUrl || !config.workspaceKey)
        throw new Error("Configuração remota de Financeiro incompleta.");
      const url = new URL(config.apiBaseUrl, location.href);
      if (!/^https?:$/.test(url.protocol) || url.username || url.password || url.search || url.hash)
        throw new Error("Endereço da API de Financeiro inválido.");
      base = url.href.replace(/\/$/, "");
      scope = base + "|" + config.workspaceKey;
      for (const name of ["clientes"]) {
        const linked = SOCIALMEI_CONFIG[name];
        if (
          linked?.mode !== "remote" ||
          linked.workspaceKey !== config.workspaceKey ||
          new URL(linked.apiBaseUrl, location.href).href.replace(/\/$/, "") !== base
        )
          throw new Error("Financeiro exige Clientes remotos na mesma API e workspace.");
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
  function payload(entry) {
    return Object.fromEntries(
      fields.filter((k) => entry[k] !== undefined).map((k) => [k, cloneData(entry[k])]),
    );
  }
  function normalize(entry) {
    if (
      !entry ||
      !Number.isSafeInteger(entry.id) ||
      !Number.isSafeInteger(entry.versao) ||
      entry.versao < 1 ||
      typeof entry.descricao !== "string" ||
      typeof entry.pessoa !== "string" ||
      !["receita", "despesa"].includes(entry.tipo) ||
      !Number.isFinite(entry.valor) ||
      entry.valor < 0 ||
      !["pago", "aberto", "atrasado"].includes(entry.status) ||
      typeof entry.vencimento !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(entry.vencimento)
    )
      throw new Error("Resposta inválida da API de Financeiro.");
    return { ...entry };
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
            ? "Há um conflito de versão ou importação. Recarregue e confira antes de salvar."
            : response.status === 422
              ? "A API recusou os campos enviados. Confira os dados e os limites do cadastro."
              : `API de Financeiro indisponível (HTTP ${response.status}).`,
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
    document.dispatchEvent(new CustomEvent("socialmei-source-status"));
    const host = document.getElementById("financeSourceStatus");
    if (!host) return;
    host.hidden = !remote;
    const pending = stored("socialmei-finance-operation-pending-v1");
    host.innerHTML = remote
      ? `<div class="management-settings-row"><div><b>Financeiro compartilhado · ${busy ? "aguarde…" : ready ? "conectado" : "indisponível"}</b><p>${escapeHtml(problem ? problem + " A lista exibida pode estar desatualizada; recarregue." : "Entradas e saídas são compartilhadas. Registrar um pagamento não altera vendas nem estoque.")}</p></div><button class="management-button" data-finance-reload ${busy ? "disabled" : ""}>Recarregar</button><button class="management-button" data-finance-import ${busy || !ready ? "disabled" : ""}>Importar lançamentos locais</button>${pending?.scope === scope ? `<button class="management-button" data-finance-recover ${busy ? "disabled" : ""}>Recuperar operação pendente</button>` : ""}</div>`
      : "";
  }
  function changed() {
    document.dispatchEvent(new CustomEvent("socialmei-data-change"));
    renderCurrentView();
    status();
  }
  async function run(action, needsReady = true) {
    if (busy) {
      toast("Aguarde", "Uma operação de Financeiro está em andamento.");
      return null;
    }
    if (!base || (needsReady && !ready)) {
      toast("Financeiro indisponível", problem || "Recarregue a lista antes de salvar.");
      return null;
    }
    busy = true;
    status();
    const controls = needsReady
      ? [
          ...document.querySelectorAll(
            "#createForm input, #createForm select, #createForm textarea, #createSubmit, #reviewConfirmAction, #confirmFinanceImport, [data-finance-paid]",
          ),
        ].map((element) => [element, element.disabled])
      : [];
    controls.forEach(([element]) => {
      element.disabled = true;
    });
    try {
      const result = await action();
      return result;
    } catch (error) {
      problem =
        error.name === "AbortError"
          ? "A API demorou para responder. Confira os dados antes de tentar novamente."
          : error.message || "Não foi possível acessar a API de Financeiro.";
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
    const list = await request("/financeiro");
    if (!Array.isArray(list)) throw new Error("Lista de Financeiro inválida.");
    const next = list.map(normalize);
    if (new Set(next.map((v) => v.id)).size !== next.length)
      throw new Error("IDs repetidos na resposta de Financeiro.");
    appData.financeiro = next;
    ready = true;
    problem = "";
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
      const key = "socialmei-finance-operation-pending-v1";
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
      appData.financeiro = result.excluida
        ? appData.financeiro.filter((v) => v.id !== result.id)
        : [result, ...appData.financeiro.filter((v) => v.id !== result.id)];
      changed();
      // A operação já foi aceita; falha de leitura posterior não a desfaz.
      try {
        await loadRemote();
      } catch (_) {
        ready = false;
        problem = "Operação salva. Recarregue para conferir a lista atual.";
      }
      return result;
    }, !recovering);
  }
  function create(entry) {
    return operation("/financeiro", "POST", payload(entry));
  }
  function update(entry, changes) {
    const data = payload(changes);
    delete data.status;
    return operation(`/financeiro/${entry.id}`, "PATCH", {
      ...data,
      expected_version: entry.versao,
    });
  }
  function transition(entry, action) {
    return operation(`/financeiro/${entry.id}/${action}`, "POST", {
      expected_version: entry.versao,
    });
  }
  function remove(entry) {
    return transition(entry, "excluir");
  }
  function recover() {
    const pending = stored("socialmei-finance-operation-pending-v1");
    if (pending?.scope === scope)
      return operation(pending.path, pending.method, pending.data, true);
  }
  function mappedLegacyId(name) {
    const local = SocialMEIClients.localData(appData).clientes;
    const matches = local.filter((r) => r.nome.toLowerCase() === String(name || "").toLowerCase());
    if (matches.length !== 1) return null;
    return stored("socialmei-client-links-v1", {})[scope]?.[matches[0].id] ?? null;
  }
  async function previewImport() {
    return run(async () => {
      if (!localEntries.length)
        throw new Error("Não há lançamentos no snapshot local para importar.");
      if (localEntries.length > 500)
        throw new Error(
          "Este fluxo importa até 500 lançamentos. Divida o dataset antes de continuar.",
        );
      let origem = stored("socialmei-finance-origin-v1");
      if (!origem) {
        origem = newOrigin();
        persist("socialmei-finance-origin-v1", origem);
      }
      const lote = {
        origem,
        itens: localEntries.map((c) => ({
          local_id: c.id,
          lancamento: {
            descricao: c.descricao,
            pessoa: c.pessoa || "",
            tipo: c.tipo,
            valor: c.valor,
            vencimento: c.vencimento,
            status: c.status,
            data_pagamento: c.data_pagamento ?? null,
            cliente_id: mappedLegacyId(c.pessoa),
          },
          extras: Object.fromEntries([["original_local", cloneData(c)]]),
        })),
      };
      const preview = await request("/financeiro/importacoes/preview", "POST", lote);
      const counts = preview.itens.reduce((n, r) => ({ ...n, [r.acao]: (n[r.acao] || 0) + 1 }), {});
      pendingImport = preview.pode_importar ? lote : null;
      $("financeImportSummary").textContent =
        `${counts.criar || 0} novos · ${counts.existente || 0} já importados · ${counts.conflito || 0} conflitos · ${counts.excluido || 0} excluídos. Histórico preservado sem alterar vendas ou estoque. Importe Clientes antes para mapear os vínculos.`;
      $("confirmFinanceImport").disabled = !pendingImport;
      openModal("financeImportModal");
      return true;
    });
  }
  async function confirmImport() {
    if (!pendingImport) return;
    const done = await run(async () => {
      const result = await request("/financeiro/importacoes/confirmar", "POST", pendingImport);
      const links = stored("socialmei-finance-links-v1", {});
      links[scope] = {
        ...(links[scope] || {}),
        ...Object.fromEntries(result.itens.map((r) => [r.local_id, r.lancamento_id])),
      };
      persist("socialmei-finance-links-v1", links);
      pendingImport = null;
      return true;
    });
    if (done) {
      await closeModal("financeImportModal");
      await refresh();
    }
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-finance-reload]")) refresh();
    if (event.target.closest("[data-finance-import]")) previewImport();
    if (event.target.closest("#confirmFinanceImport")) confirmImport();
    if (event.target.closest("[data-finance-recover]")) recover();
  });
  document.addEventListener("DOMContentLoaded", () => {
    status();
    if (remote) refresh();
  });
  return {
    remote,
    get connectionState() {
      return !remote ? "local" : ready ? "ready" : busy ? "loading" : "unavailable";
    },
    refresh,
    create,
    update,
    remove,
    transition,
    recover,
    attach(data) {
      localEntries = cloneData(data.financeiro);
      if (remote) data.financeiro = [];
    },
    localData(data) {
      return remote ? { ...data, financeiro: cloneData(localEntries) } : data;
    },
    matchesClient(entry, client) {
      return remote
        ? entry.cliente_id === client.id
        : normalizedText(entry.pessoa) === normalizedText(client.nome);
    },
    backup() {
      return remote
        ? {
            source: scope,
            financeiro: cloneData(appData.financeiro),
            exportedAt: new Date().toISOString(),
          }
        : null;
    },
  };
})();
