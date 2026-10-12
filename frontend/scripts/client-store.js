/* Clientes: fonte explícita, sem escrita local como fallback da API. */
const SocialMEIClients = (() => {
  const config = SOCIALMEI_CONFIG.clientes || { mode: "local" };
  const remote = config.mode !== "local";
  const fields = [
    "nome",
    "telefone",
    "email",
    "instagram",
    "status",
    "observacao",
    "tags",
    "cidade",
    "desde",
    "categoria",
    "criadoEm",
    "observacaoAtualizada",
    "avatarUrl",
    "foto",
    "ultima",
    "total",
    "pendente",
  ];
  let localClients = [],
    ready = !remote,
    busy = false,
    problem = "",
    pendingImport = null;
  let base = "",
    scope = "";
  try {
    if (remote) {
      if (config.mode !== "remote" || !config.apiBaseUrl || !config.workspaceKey)
        throw new Error("Configuração remota de Clientes incompleta.");
      const url = new URL(config.apiBaseUrl, location.href);
      if (!/^https?:$/.test(url.protocol) || url.username || url.password || url.search || url.hash)
        throw new Error("Endereço da API de Clientes inválido.");
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
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    // getRandomValues também funciona em HTTP numa rede local; Math.random não serve.
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  function payload(client) {
    return Object.fromEntries(
      fields.filter((k) => client[k] !== undefined).map((k) => [k, cloneData(client[k])]),
    );
  }
  function normalize(client) {
    if (
      !client ||
      !Number.isSafeInteger(client.id) ||
      !Number.isSafeInteger(client.versao) ||
      client.versao < 1 ||
      typeof client.nome !== "string" ||
      !Array.isArray(client.tags)
    )
      throw new Error("Resposta inválida da API de Clientes.");
    return {
      ...client,
      telefone: client.telefone || "—",
      instagram: client.instagram || "—",
      observacao: client.observacao || "",
      ultima: client.ultima || "—",
      total: client.total ?? 0,
      pendente: client.pendente ?? 0,
    };
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
            ? "Os dados mudaram ou há um conflito de importação. Recarregue e confira antes de salvar."
            : response.status === 422
              ? "A API recusou os campos enviados. Confira os dados e os limites do cadastro."
              : `API de Clientes indisponível (HTTP ${response.status}).`,
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
    const host = document.getElementById("clientsSourceStatus");
    if (!host) return;
    host.hidden = !remote;
    host.innerHTML = remote
      ? `<div class="management-settings-row"><div><b>Clientes compartilhados · ${busy ? "aguarde…" : ready ? "conectado" : "indisponível"}</b><p>${escapeHtml(problem ? problem + " A lista exibida pode estar desatualizada; recarregue." : "Clientes são salvos na API. Confira a conexão dos demais módulos para identificar os dados compartilhados.")}</p></div><button class="management-button" data-clients-reload ${busy ? "disabled" : ""}>Recarregar</button><button class="management-button" data-clients-import ${busy || !ready ? "disabled" : ""}>Importar clientes locais</button></div>`
      : "";
  }
  function changed() {
    document.dispatchEvent(new CustomEvent("socialmei-data-change"));
    renderCurrentView();
    status();
  }
  async function run(action, needsReady = true) {
    if (busy) {
      toast("Aguarde", "Uma operação de Clientes está em andamento.");
      return null;
    }
    if (!base || (needsReady && !ready)) {
      toast("Clientes indisponíveis", problem || "Recarregue a lista antes de salvar.");
      return null;
    }
    busy = true;
    status();
    const controls = [
      ...document.querySelectorAll(
        "#createForm input, #createForm select, #createForm textarea, #createSubmit, #inboxModalForm input, #inboxModalForm select, #inboxModalForm textarea, #inboxModalSubmit, #reviewConfirmAction, #confirmClientImport, #tagCreateForm input, #tagCreateForm button",
      ),
    ].map((element) => [element, element.disabled]);
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
          : error.message || "Não foi possível acessar a API de Clientes.";
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
    if (typeof SocialMEIAuth !== "undefined" && SocialMEIAuth.remote) {
      await SocialMEIAuth.ready;
      if (!SocialMEIAuth.current) return null;
      scope = base + "|" + SocialMEIAuth.current.negocio.slug;
    }
    return run(async () => {
      const list = await request("/clientes");
      if (!Array.isArray(list)) throw new Error("Lista de Clientes inválida.");
      const next = list.map(normalize);
      if (new Set(next.map((c) => c.id)).size !== next.length)
        throw new Error("IDs repetidos na resposta de Clientes.");
      appData.clientes = next;
      ready = true;
      changed();
      return true;
    }, false);
  }
  async function create(client) {
    return run(async () => {
      const data = payload(client);
      const key = "socialmei-client-create-pending-v1";
      let pending = stored(key);
      if (!data.criadoEm && pending?.data?.criadoEm) data.criadoEm = pending.data.criadoEm;
      if (
        pending &&
        (pending.scope !== scope || JSON.stringify(pending.data) !== JSON.stringify(data))
      )
        throw new Error(
          "Há um cadastro anterior sem confirmação. Reenvie os mesmos dados para recuperar o resultado antes de criar outro.",
        );
      if (!pending) {
        data.criadoEm ||= new Date().toISOString();
        pending = { scope, data, origem: newOrigin() };
        persist(key, pending);
      }
      // Uma origem estável por cadastro torna seguro repetir após perda da resposta.
      let result;
      try {
        result = await request("/clientes/importacoes/confirmar", "POST", {
          origem: pending.origem,
          itens: [{ local_id: 0, cliente: data }],
        });
      } catch (error) {
        if (error.status === 422) persist(key, null);
        throw error;
      }
      const id = result.itens?.[0]?.cliente_id;
      if (!Number.isSafeInteger(id)) throw new Error("Mapeamento de criação inválido.");
      const saved = normalize(await request("/clientes/" + id));
      appData.clientes = [saved, ...appData.clientes.filter((c) => c.id !== id)];
      persist(key, null);
      changed();
      return saved;
    });
  }
  async function update(client, changes) {
    return run(async () => {
      const saved = normalize(
        await request("/clientes/" + client.id, "PATCH", {
          ...payload(changes),
          expected_version: client.versao,
        }),
      );
      if (
        !SocialMEISales.remote &&
        saved.nome !== client.nome &&
        appData.clientes.filter((c) => c.nome.toLowerCase() === client.nome.toLowerCase())
          .length === 1
      ) {
        appData.vendas
          .filter((s) => s.cliente.toLowerCase() === client.nome.toLowerCase())
          .forEach((s) => {
            s.cliente = saved.nome;
          });
        (SocialMEIFinance.remote ? [] : appData.financeiro)
          .filter((e) => (e.pessoa || "").toLowerCase() === client.nome.toLowerCase())
          .forEach((e) => {
            e.pessoa = saved.nome;
          });
        // A escrita remota já foi aceita; uma falha local não desfaz o servidor.
        if (!saveAppData())
          toast(
            "Cliente salvo na API",
            "Os vínculos locais não puderam ser salvos. Exporte um backup.",
          );
      }
      appData.clientes = appData.clientes.map((c) => (c.id === saved.id ? saved : c));
      changed();
      return saved;
    });
  }
  async function remove(client) {
    return run(async () => {
      await request(`/clientes/${client.id}?expected_version=${client.versao}`, "DELETE");
      appData.clientes = appData.clientes.filter((c) => c.id !== client.id);
      changed();
      return true;
    });
  }
  function conversationClient(c) {
    if (!remote)
      return (
        appData.clientes.find((x) => x.id === c.clientId) ||
        appData.clientes.find((x) => x.nome.toLowerCase() === c.nome.toLowerCase())
      );
    const state = inboxLocalState[`state:${conversationKey(c)}`];
    let id = c.remoteClients?.[scope] ?? state?.remoteClients?.[scope];
    if (id == null) {
      const mapping = stored("socialmei-client-links-v1", {})[scope] || {};
      const candidates = localClients.filter((x) => x.nome.toLowerCase() === c.nome.toLowerCase());
      const localId = c.clientId ?? (candidates.length === 1 ? candidates[0].id : null);
      id = mapping[localId];
    }
    return appData.clientes.find((x) => x.id === id);
  }
  function link(c, client) {
    if (remote) c.remoteClients = { ...(c.remoteClients || {}), [scope]: client.id };
    else c.clientId = client.id;
    persistConversationState(c);
  }
  async function previewImport() {
    return run(async () => {
      if (!localClients.length) throw new Error("Não há clientes no snapshot local para importar.");
      if (localClients.length > 500)
        throw new Error(
          "Este fluxo importa até 500 clientes. Divida o dataset antes de continuar.",
        );
      let origem = stored("socialmei-client-origin-v1");
      if (!origem) {
        origem = newOrigin();
        persist("socialmei-client-origin-v1", origem);
      }
      const lote = {
        origem,
        itens: localClients.map((c) => ({
          local_id: c.id,
          cliente: payload(c),
          extras: Object.fromEntries(
            Object.entries(c).filter(([k]) => k !== "id" && !fields.includes(k)),
          ),
        })),
      };
      const preview = await request("/clientes/importacoes/preview", "POST", lote);
      const counts = preview.itens.reduce((n, r) => ({ ...n, [r.acao]: (n[r.acao] || 0) + 1 }), {});
      pendingImport = preview.pode_importar ? lote : null;
      $("clientImportSummary").textContent =
        `${counts.criar || 0} novos · ${counts.existente || 0} já importados · ${counts.conflito || 0} conflitos · ${counts.excluido || 0} excluídos. O snapshot local será preservado.`;
      $("confirmClientImport").disabled = !pendingImport;
      openModal("clientImportModal");
      return true;
    });
  }
  async function confirmImport() {
    if (!pendingImport) return;
    const done = await run(async () => {
      const result = await request("/clientes/importacoes/confirmar", "POST", pendingImport);
      const links = stored("socialmei-client-links-v1", {});
      links[scope] = {
        ...(links[scope] || {}),
        ...Object.fromEntries(result.itens.map((r) => [r.local_id, r.cliente_id])),
      };
      persist("socialmei-client-links-v1", links);
      pendingImport = null;
      return true;
    });
    if (done) {
      await closeModal("clientImportModal");
      await refresh();
    }
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-clients-reload]")) refresh();
    if (event.target.closest("[data-clients-import]")) previewImport();
    if (event.target.closest("#confirmClientImport")) confirmImport();
  });
  document.addEventListener("DOMContentLoaded", () => {
    status();
    if (remote) refresh();
  });
  return {
    newId: newOrigin,
    remote,
    refresh,
    create,
    update,
    remove,
    conversationClient,
    link,
    attach(data) {
      localClients = cloneData(data.clientes);
      if (remote) data.clientes = [];
    },
    localData(data) {
      return remote ? { ...data, clientes: cloneData(localClients) } : data;
    },
    backup() {
      return remote
        ? {
            source: scope,
            clientes: cloneData(appData.clientes),
            exportedAt: new Date().toISOString(),
          }
        : null;
    },
  };
})();
