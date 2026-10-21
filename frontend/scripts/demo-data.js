/* Synthetic view data never attaches to stores or replaces the business state. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIDemoData = api;
})(globalThis, function () {
  const shift = (day, offset) => {
    const value = new Date(day + "T12:00:00Z");
    value.setUTCDate(value.getUTCDate() + offset);
    return value.toISOString().slice(0, 10);
  };
  function dataset(day) {
    const names = [
      "Lia (exemplo)",
      "Bruno (exemplo)",
      "Bia (exemplo)",
      "Ana (exemplo)",
      "Paulo (exemplo)",
      "Leo (exemplo)",
    ];
    const clientes = names.map((nome, i) => ({
      id: 91001 + i,
      nome,
      telefone: "",
      instagram: "",
      status: i === 2 || i === 3 ? "Novo" : "Ativo",
      ultima: shift(day, -i),
      criadoEm: shift(day, [-40, -40, -10, -12, -16, -21][i]),
      total: 0,
      pendente: 0,
      observacao: "Cliente fictício para visualização. Nenhum canal conectado.",
      tags: ["Demonstração"],
    }));
    const produtos = [
      {
        id: 92001,
        nome: "Kit de cuidados · exemplo",
        tipo: "Produto",
        preco: 60,
        custo: 28,
        estoque: 8,
        minimo: 2,
        status: "Ativo",
      },
      {
        id: 92002,
        nome: "Ajuste simples · exemplo",
        tipo: "Serviço",
        preco: 35,
        custo: 10,
        estoque: null,
        minimo: null,
        status: "Ativo",
      },
    ];
    const vendas = [0, 2, 5, 8, 12, 18, 26, 34].map((offset, i) => {
      const client = clientes[i % clientes.length],
        product = produtos[i % 2];
      return {
        id: 93001 + i,
        cliente: client.nome,
        cliente_id: client.id,
        item: product.nome,
        produto_id: product.id,
        quantidade: (i % 3) + 1,
        valor: product.preco * ((i % 3) + 1),
        data: shift(day, -offset),
        pagamento: "Pix",
        status: i === 2 ? "Pendente" : i === 5 ? "Cancelado" : "Pago",
      };
    });
    const financeiro = vendas
      .filter((v) => v.status === "Pago")
      .map((v, i) => ({
        id: 94001 + i,
        descricao: `Venda #${v.id} · exemplo`,
        pessoa: v.cliente,
        tipo: "receita",
        valor: v.valor,
        vencimento: v.data,
        status: "pago",
      }));
    [0, 6, 15, 30].forEach((offset, i) =>
      financeiro.push({
        id: 95001 + i,
        descricao: "Materiais · exemplo",
        pessoa: "Fornecedor fictício",
        tipo: "despesa",
        valor: [25, 45, 30, 55][i],
        vencimento: shift(day, -offset),
        status: "pago",
      }),
    );
    financeiro.push({
      id: 95010,
      descricao: "Material a pagar · exemplo",
      pessoa: "Fornecedor fictício",
      tipo: "despesa",
      valor: 40,
      vencimento: shift(day, 3),
      status: "aberto",
    });
    clientes.forEach((client) => {
      client.total = vendas
        .filter((v) => v.cliente_id === client.id && v.status === "Pago")
        .reduce((n, v) => n + v.valor, 0);
      client.pendente = vendas
        .filter((v) => v.cliente_id === client.id && v.status === "Pendente")
        .reduce((n, v) => n + v.valor, 0);
    });
    const freeze = (value) => {
      Object.values(value).forEach((v) => {
        if (v && typeof v === "object") freeze(v);
      });
      return Object.freeze(value);
    };
    const texts = [
      "Quero comprar o kit. Pode me explicar como pagar?",
      "Quanto custa o serviço de ajuste? Você tem disponibilidade?",
      "Oi, tenho uma dúvida.",
      "O ajuste ficou torto, preciso de ajuda urgente.",
      "Já comprei o kit. Preciso de ajuda com uma cobrança indevida.",
      "Desisti da compra, não quero mais.",
    ];
    const conversations = clientes.map((client, i) => ({
      id: 96001 + i,
      clientId: client.id,
      nome: client.nome,
      iniciais: client.nome.slice(0, 2),
      canal: "whatsapp",
      status: i === 5 ? "resolvido" : "aberto",
      naoLidas: i === 5 ? 0 : 1,
      atualizado: "Exemplo",
      telefone: "",
      mensagens: [{ de: "cliente", texto: texts[i], data: shift(day, -i), hora: "10:00" }],
    }));
    const atividade = vendas.slice(0, 3).map((sale) => ({
      t: "sale",
      a: `Venda #${sale.id} · exemplo`,
      b: sale.cliente,
      v: sale.valor,
      w: sale.data,
    }));
    const notificacoes = [
      { t: "Mensagem de exemplo", s: `${clientes[0].nome} · nenhuma mensagem enviada` },
      { t: "Venda de exemplo", s: `${vendas[0].cliente} · pedido #${vendas[0].id}` },
      { t: "Compromisso de exemplo", s: financeiro.at(-1).descricao },
    ];
    return freeze({
      clientes,
      produtos,
      vendas,
      financeiro,
      conversations,
      atividade,
      notificacoes,
    });
  }
  function preference(storage, getScope) {
    const key = (scope) => "socialmei-view-demo-v1:" + encodeURIComponent(scope);
    return {
      enabled() {
        try {
          const scope = getScope();
          return !!scope && storage.getItem(key(scope)) === "true";
        } catch {
          return false;
        }
      },
      set(enabled) {
        const scope = getScope();
        if (!scope) throw Error("Entre no seu espaço antes de alterar a demonstração.");
        storage.setItem(key(scope), enabled ? "true" : "false");
      },
    };
  }
  let repo, cache, cacheDay;
  const store = () =>
    (repo ||= preference(localStorage, () => SocialMEIBusinessProfile.browserRepository().scope()));
  const enabled = () => {
    try {
      return store().enabled();
    } catch {
      return false;
    }
  };
  const read = (original) => {
    if (!enabled()) return original;
    const day = todayISO();
    if (cacheDay !== day) {
      cache = dataset(day);
      cacheDay = day;
    }
    return { ...cache, prefs: original.prefs };
  };
  return { dataset, preference, enabled, read, set: (value) => store().set(value) };
});

if (typeof document !== "undefined")
  document.addEventListener("DOMContentLoaded", () => {
    const demo = SocialMEIDemoData;
    const writes =
      "[data-edit-profile],[data-edit-observation],[data-add-tag],[data-remove-tag],#newConversationBtn,[data-create],[data-create-sale-client],[data-record-open],[data-sale-paid],[data-sale-duplicate],[data-finance-paid],[data-stock],[data-client-note],[data-client-conversation],[data-open-client],[data-client-id],[data-catalog-add],[data-profile-suggest],[data-profile-custom],[data-row-menu],[data-review-edit],[data-review-delete],[data-review-cancel],[data-sale-register],#exportBackup,#importBackup,[data-nv-delete-account]";
    function decorate() {
      const active = demo.enabled();
      document.getElementById("nvBusinessSteps").hidden =
        active || Number(document.getElementById("nvBusinessBar").value) === 6;
      document.getElementById("nvBusinessBar").hidden =
        active || Number(document.getElementById("nvBusinessBar").value) === 6;
      // The desktop inbox intentionally hides the shell topbar. Reuse the same
      // indicator in its native heading instead of creating a second badge.
      const control = document.getElementById("viewDemoControl"),
        inboxHeading = document.querySelector(".inbox-title-line"),
        tools = document.getElementById("utilityTools");
      if (currentView === "Caixa Unificada" && window.innerWidth > 900) {
        if (control.parentElement !== inboxHeading) inboxHeading.append(control);
      } else if (control.parentElement !== tools.parentElement) tools.before(control);
      document.body.classList.toggle("view-demo-active", active);
      const isolated = currentView === "Oportunidades" && SocialMEIOpportunities.demoActive();
      const visible = active || isolated;
      document.getElementById("viewDemoControl").hidden = !visible;
      document.getElementById("viewDemoNotice").hidden = !visible;
      document.getElementById("viewDemoDescription").textContent = active
        ? "Amostra comercial somente para leitura. Para cadastrar ou editar clientes, vendas, produtos e financeiro, desative os dados de teste. Perfil e preferências continuam disponíveis. Nenhuma conexão é ativada."
        : "Exemplos apenas na análise de clientes. Os outros módulos mantêm seus dados e configurações.";
      document.getElementById("viewDemoToggle").setAttribute("aria-checked", String(active));
      document.querySelectorAll(writes).forEach((control) => {
        if (!(control instanceof HTMLButtonElement)) return;
        if (active && !control.disabled) {
          control.dataset.demoDisabled = "true";
          control.disabled = true;
          control.title =
            "Indisponível na demonstração. Desative os dados de teste para editar seus registros.";
          control.dataset.demoOriginalDescription = control.getAttribute("aria-describedby") || "";
          control.setAttribute(
            "aria-describedby",
            (control.dataset.demoOriginalDescription + " viewDemoDescription").trim(),
          );
        } else if (!active && control.dataset.demoDisabled) {
          delete control.dataset.demoDisabled;
          control.disabled = false;
          control.removeAttribute("title");
          if (control.dataset.demoOriginalDescription)
            control.setAttribute("aria-describedby", control.dataset.demoOriginalDescription);
          else control.removeAttribute("aria-describedby");
          delete control.dataset.demoOriginalDescription;
        }
      });
    }
    let refreshing = false;
    function refresh() {
      if (refreshing) return;
      refreshing = true;
      try {
        document.querySelectorAll(".modal-backdrop.open").forEach((modal) => {
          if (modal.id !== "accountModal") closeModal(modal.id);
        });
        renderCurrentView();
        updateDataOriginNotice();
        decorate();
      } finally {
        refreshing = false;
      }
    }
    document.addEventListener(
      "click",
      (event) => {
        if (event.target.closest("#viewDemoToggle,#viewDemoExit")) {
          try {
            const leaving = !!event.target.closest("#viewDemoExit");
            const next = leaving ? false : !demo.enabled();
            demo.set(next);
            if (!next) SocialMEIOpportunities.resetDemo();
            document.getElementById("viewDemoControl").open = false;
            document.dispatchEvent(new CustomEvent("socialmei-demo-change"));
            toast(next ? "Dados de teste ativados" : "Dados de teste desativados", "", "info");
            if (event.target.closest("#viewDemoExit"))
              document.getElementById("mainContent").focus({ preventScroll: true });
          } catch (error) {
            toast("Preferência não salva", error.message);
          }
          return;
        }
        if (event.target.closest("[data-demo-settings]")) {
          document.getElementById("viewDemoControl").open = false;
          selectedSettingsTab = "dados";
          setView("Configurações");
          document.getElementById("viewDemoToggle").focus({ preventScroll: true });
          document.getElementById("viewDemoToggle").scrollIntoView({
            block: "center",
            behavior: SocialMEIMotion.reduced ? "instant" : "smooth",
          });
          return;
        }
        if (demo.enabled() && event.target.closest("[data-home-conversation]")) {
          event.preventDefault();
          event.stopImmediatePropagation();
          setView("Oportunidades");
          return;
        }
        if (demo.enabled() && event.target.closest(writes)) {
          event.preventDefault();
          event.stopImmediatePropagation();
          toast(
            "Demonstração somente para leitura",
            "Desative os dados de teste para editar seus registros.",
          );
        }
      },
      true,
    );
    document.addEventListener(
      "submit",
      (event) => {
        if (
          demo.enabled() &&
          event.target.matches("#createForm,#recordEditorForm,#recordEditForm")
        ) {
          event.preventDefault();
          event.stopImmediatePropagation();
        }
      },
      true,
    );
    const observer = new MutationObserver((records) => {
      if (!records.some((record) => [...record.addedNodes].some((node) => node.nodeType === 1)))
        return;
      // New controls must expose read-only state before the next interaction.
      decorate();
    });
    observer.observe(
      document.getElementById("appShell") ||
        document.getElementById("mainContent") ||
        document.body,
      { childList: true, subtree: true },
    );
    let owner = SocialMEIBusinessProfile.browserRepository().scope();
    document.addEventListener("socialmei-data-change", () => {
      const next = SocialMEIBusinessProfile.browserRepository().scope();
      if (owner !== next) {
        owner = next;
        refresh();
      } else decorate();
    });
    document.addEventListener("socialmei-view-change", decorate);
    window.addEventListener("resize", decorate, { passive: true });
    document.addEventListener("socialmei-opportunity-demo-change", decorate);
    document.addEventListener("socialmei-demo-change", refresh);
    window.addEventListener("storage", (event) => {
      if (event.key === null || event.key.startsWith("socialmei-view-demo-v1:")) refresh();
    });
    decorate();
  });
