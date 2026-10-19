/* Profile-driven presentation; commercial writes remain in the native catalog flow. */
const SocialMEIPersonalization = (() => {
  const model = window.SocialMEIBusinessProfile;
  const store = model.browserRepository();
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const button = (label, action, value, className = "management-button") => {
    const element = node("button", label, className);
    element.type = "button";
    element.dataset[action] = value;
    element.dataset.profileScope = store.scope() || "";
    return element;
  };
  function configure() {
    selectedSettingsTab = "perfil";
    setView("Configurações");
    document.querySelector('[data-settings-tab="perfil"]')?.focus();
  }
  function navigate(id) {
    const route = model.featureRoutes[id];
    if (!route) return;
    if (route.type) {
      document.getElementById("productsTypeFilter").value = route.type;
      document.getElementById("productsSearch").value = "";
      isCatalogLowStockOnly = false;
    }
    setView(route.view);
  }
  function renderHome() {
    const host = document.getElementById("homeProfileShortcuts");
    if (!host) return;
    const profile = store.read().profile;
    document.getElementById("homeDefaultShortcuts").hidden = !!profile;
    host.hidden = !profile;
    host.replaceChildren();
    const intro = document.getElementById("homeProfileContext");
    const limits = document.getElementById("homeProfileLimits");
    limits.replaceChildren();
    limits.hidden = !profile;
    const source = document.getElementById("homeDataSource");
    source.textContent = SocialMEIAuth.remote
      ? "Perfil adaptativo local neste navegador. Os registros seguem a fonte configurada de cada módulo."
      : "Demonstração local: há exemplos fictícios e cadastros deste navegador. Não são dados sincronizados.";
    if (!profile) {
      intro.textContent =
        "Comece por um próximo passo. Prepare seu perfil para encontrar atalhos do seu negócio.";
      host.hidden = false;
      host.append(button("Preparar meu perfil", "profileConfigure", "", "lk"));
      return;
    }
    const activity =
      profile.segment === "other"
        ? profile.activity || "Seu negócio"
        : model.segments[profile.segment].label;
    intro.textContent = `${activity} · ${profile.offers.includes("services") && profile.offers.includes("products") ? "seus serviços e produtos no mesmo lugar" : profile.offers.includes("services") ? "seus serviços e clientes no mesmo lugar" : "seus produtos e vendas no mesmo lugar"}.`;
    const tools = model.contextualTools(profile);
    tools.active
      .slice(0, 6)
      .forEach((tool) => host.append(button(tool.label + " →", "profileRoute", tool.id, "")));
    host.append(button("Configurar atalhos", "profileConfigure", "", ""));

    if (tools.future.length)
      limits.append(
        node(
          "span",
          `${tools.future.map((tool) => tool.label).join(", ")}: ainda sem módulo operacional. Configure seus atalhos para escolher ferramentas disponíveis.`,
        ),
      );
    if (!sessionData.conversas.length) {
      const now = document.getElementById("homeNow");
      now.replaceChildren(
        node("span", "SEU PRÓXIMO PASSO", "chapter-label"),
        node(
          "h3",
          profile.offers.includes("services")
            ? "Apresente o que você faz."
            : "Comece pelo que você vende.",
        ),
        node(
          "p",
          "Confira as sugestões do seu perfil ou cadastre uma opção própria. Nada é adicionado sem sua confirmação.",
          "home-empty-note",
        ),
      );
      now.append(button("Abrir Produtos e Serviços →", "profileCatalog", "", "btn"));
    }
  }
  function renderCatalog() {
    const host = document.getElementById("catalogProfileSuggestions");
    if (!host) return;
    host.replaceChildren();
    const state = store.read(),
      profile = state.profile;
    const heading = node(
      "h3",
      profile ? "Sugestões para o seu negócio" : "Seu catálogo, do seu jeito",
    );
    heading.id = "catalogProfileTitle";
    heading.tabIndex = -1;
    host.append(heading);
    if (!profile) {
      host.append(
        node(
          "p",
          state.status === "unavailable"
            ? "Seu perfil local não está disponível. Confira a sessão ou cadastre um item pelo formulário existente."
            : "Prepare seu perfil para ver sugestões pertinentes. Você também pode cadastrar qualquer produto ou serviço.",
          "management-note",
        ),
        button("Preparar meu perfil", "profileConfigure", ""),
      );
      return;
    }
    host.append(
      node(
        "p",
        "Sugestões do perfil local, não são itens cadastrados. Você define o nome do produto, preço e demais dados no formulário.",
        "management-note",
      ),
    );
    const type = document.getElementById("productsTypeFilter").value;
    const suggestions = model
      .catalogSuggestions(profile, appData.produtos)
      .filter((item) => type === "all" || item.kind === type);
    if (suggestions.length) {
      const list = node("ul", undefined, "profile-catalog-suggestions");
      suggestions.forEach((item) => {
        const row = node("li");
        const text = node("div");
        text.append(
          node("small", item.kind === "Serviço" ? "Serviço sugerido" : "Categoria de produtos"),
          node("b", item.label),
        );
        row.append(
          text,
          button("Usar sugestão", "profileSuggest", item.id),
          button("Ignorar", "profileIgnore", item.id, "lk"),
        );
        list.append(row);
      });
      host.append(list);
    } else
      host.append(
        node(
          "p",
          "Nenhuma sugestão pendente nesta seleção. Você pode cadastrar uma opção própria.",
          "management-note",
        ),
      );
    const actions = node("div", undefined, "profile-catalog-actions");
    actions.append(button("Cadastrar opção própria", "profileCustom", ""));
    if (profile.ignoredSuggestions.length)
      actions.append(button("Rever sugestões ignoradas", "profileRestore", "", "lk"));
    host.append(actions);
  }
  function openSuggestion(id) {
    const item = model
      .catalogSuggestions(store.read().profile, appData.produtos)
      .find((item) => item.id === id);
    if (!item) return;
    openCreate("produto", { nome: item.name, tipo: item.kind });
    const note = node(
      "p",
      item.kind === "Serviço"
        ? `Sugestão do seu perfil: ${item.label}. Confira o nome e informe seu preço. Nada foi salvo.`
        : `Categoria sugerida: ${item.label}. Informe o nome do produto específico e seu preço. Nenhum produto ou estoque foi cadastrado.`,
      "management-note full",
    );
    note.id = "profileSuggestionNote";
    document.getElementById("createFields").prepend(note);
    for (const id of ["f_preco", "f_custo", "f_estoque", "f_minimo"]) {
      const input = document.getElementById(id);
      if (input && !input.disabled) input.value = "";
    }
  }
  document.addEventListener("click", (event) => {
    const control = event.target.closest(
      "[data-profile-route],[data-profile-configure],[data-profile-catalog],[data-profile-suggest],[data-profile-ignore],[data-profile-restore],[data-profile-custom]",
    );
    if (!control) return;
    if ((store.scope() || "") !== control.dataset.profileScope) {
      renderHome();
      renderCatalog();
      toast("Perfil alterado", "Confira as sugestões da sessão atual.");
      return;
    }
    if (control.hasAttribute("data-profile-configure")) return configure();
    if (control.hasAttribute("data-profile-route")) return navigate(control.dataset.profileRoute);
    if (control.hasAttribute("data-profile-catalog")) {
      document.getElementById("productsTypeFilter").value = "all";
      return setView("Produtos e Serviços");
    }
    if (control.hasAttribute("data-profile-suggest"))
      return openSuggestion(control.dataset.profileSuggest);
    if (control.hasAttribute("data-profile-custom")) {
      const profile = store.read().profile;
      const filter = document.getElementById("productsTypeFilter").value;
      const service =
        filter === "Serviço" ||
        (filter === "all" && profile?.offers.length === 1 && profile.offers[0] === "services");
      return openCreate("produto", { tipo: service ? "Serviço" : "Produto" });
    }
    const profile = store.read().profile;
    if (!profile) return;
    if (control.hasAttribute("data-profile-restore")) profile.ignoredSuggestions = [];
    else if (
      model
        .catalogSuggestions(profile, appData.produtos)
        .some((item) => item.id === control.dataset.profileIgnore)
    )
      profile.ignoredSuggestions.push(control.dataset.profileIgnore);
    else return;
    if (!store.save(profile, control.dataset.profileScope)) {
      toast("Não foi possível salvar", "Confira a sessão e o armazenamento deste navegador.");
      return;
    }
    renderCatalog();
    document.getElementById("catalogProfileTitle")?.focus();
  });
  document.addEventListener("socialmei-business-profile-change", () => {
    renderHome();
    renderCatalog();
  });
  return { renderHome, renderCatalog };
})();
