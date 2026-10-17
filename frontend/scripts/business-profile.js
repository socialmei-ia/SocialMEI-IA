/* Business preferences are local, scoped and independent of account credentials. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIBusinessProfile = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  // Family groups keep the one-question onboarding short while allowing precise specialties.
  // Legacy segment IDs and the local profile schema (version 1) remain unchanged.
  const segments = {
    barber: {
      label: "Barbearia",
      family: "Beleza e cuidados",
      description: "Cortes masculinos, barba e cuidados da barbearia.",
      offers: ["services"],
      services: ["Corte masculino", "Barba", "Sobrancelha", "Pigmentação de barba"],
      products: ["Cosméticos", "Produtos para cabelo", "Pomadas modeladoras"],
    },
    hairdresser: {
      label: "Cabeleireiro e salão",
      family: "Beleza e cuidados",
      description: "Cortes, escovas, coloração e tratamentos capilares.",
      offers: ["services"],
      services: ["Escova", "Corte feminino", "Coloração", "Hidratação capilar"],
      products: ["Shampoo", "Máscaras capilares", "Finalizadores"],
    },
    manicure: {
      label: "Manicure e unhas",
      family: "Beleza e cuidados",
      description: "Unhas, esmaltação e atendimentos com horário.",
      offers: ["services"],
      services: ["Manicure", "Pedicure", "Alongamento de unhas", "Esmaltação em gel"],
      products: ["Esmaltes", "Cuidados para unhas"],
    },
    perfume: {
      label: "Perfumaria",
      family: "Beleza e cuidados",
      description: "Perfumes, fragrâncias e cuidados pessoais.",
      offers: ["products"],
      services: [],
      products: ["Perfumes", "Cosméticos", "Cuidados pessoais", "Kits de presente"],
    },
    cosmetics: {
      label: "Loja de cosméticos",
      family: "Beleza e cuidados",
      description: "Maquiagens, skincare, cabelo e beleza.",
      offers: ["products"],
      services: [],
      products: ["Maquiagem", "Skincare", "Produtos capilares", "Acessórios de beleza"],
    },
    beautyReseller: {
      label: "Revenda de beleza",
      family: "Beleza e cuidados",
      description: "Revenda por catálogo, encomenda ou pronta entrega.",
      offers: ["products"],
      services: [],
      products: ["Produtos de catálogo", "Kits de beleza", "Perfumes", "Maquiagem"],
    },
    tailoring: {
      label: "Costura e confecção",
      family: "Moda e confecção",
      description: "Ajustes, reparos e peças feitas sob encomenda.",
      offers: ["services"],
      services: ["Ajustes", "Confecção sob encomenda", "Reparos em roupas", "Barras"],
      products: ["Roupas", "Acessórios"],
    },
    fashion: {
      label: "Loja de roupas",
      family: "Moda e confecção",
      description: "Peças por tamanho, modelo ou coleção.",
      offers: ["products"],
      services: [],
      products: ["Camisetas", "Vestidos", "Calças", "Moda infantil", "Acessórios"],
    },
    bakery: {
      label: "Confeitaria e doces",
      family: "Alimentação",
      description: "Bolos, doces, festas e pedidos antecipados.",
      offers: ["products"],
      services: [],
      products: ["Bolos", "Docinhos", "Sobremesas", "Encomendas para festas"],
    },
    snack: {
      label: "Lanchonete",
      family: "Alimentação",
      description: "Lanches, bebidas e pedidos para retirada ou entrega.",
      offers: ["products"],
      services: [],
      products: ["Sanduíches", "Salgados", "Sucos", "Combos"],
    },
    restaurant: {
      label: "Restaurante e marmitas",
      family: "Alimentação",
      description: "Refeições, marmitas e pedidos do dia.",
      offers: ["products"],
      services: [],
      products: ["Marmitas", "Pratos feitos", "Refeições", "Bebidas"],
    },
    commerce: {
      label: "Comércio em geral",
      family: "Comércio e varejo",
      description: "Venda de mercadorias variadas.",
      offers: ["products"],
      services: [],
      products: ["Alimentos", "Bebidas", "Utilidades", "Acessórios"],
    },
    market: {
      label: "Mercadinho",
      family: "Comércio e varejo",
      description: "Produtos de consumo diário, estoque e reposição.",
      offers: ["products"],
      services: [],
      products: ["Mercearia", "Hortifruti", "Limpeza", "Bebidas"],
    },
    convenience: {
      label: "Loja de conveniência",
      family: "Comércio e varejo",
      description: "Compra rápida, bebidas, snacks e itens de emergência.",
      offers: ["products"],
      services: [],
      products: ["Snacks", "Bebidas geladas", "Conveniência", "Itens rápidos"],
    },
    phoneRepair: {
      label: "Assistência de celular",
      family: "Tecnologia e reparos",
      description: "Consertos, peças, orçamentos e aparelhos para retirada.",
      offers: ["services"],
      services: ["Troca de tela", "Troca de bateria", "Diagnóstico", "Reparo de conector"],
      products: ["Capinhas", "Películas", "Carregadores"],
    },
    electronics: {
      label: "Loja de eletrônicos",
      family: "Tecnologia e reparos",
      description: "Venda de equipamentos, acessórios e componentes.",
      offers: ["products"],
      services: [],
      products: ["Celulares", "Fones", "Acessórios", "Cabos e carregadores"],
    },
    consulting: {
      label: "Consultoria e serviços autônomos",
      family: "Serviços profissionais",
      description: "Orientações, projetos, propostas e reuniões com clientes.",
      offers: ["services"],
      services: ["Consultoria", "Diagnóstico", "Projeto", "Acompanhamento"],
      products: [],
    },
    tutor: {
      label: "Professor particular",
      family: "Serviços profissionais",
      description: "Aulas individuais, pacotes de aulas e horários.",
      offers: ["services"],
      services: ["Aula particular", "Reforço escolar", "Preparação para provas"],
      products: ["Material didático"],
    },
    laboratory: {
      label: "Serviços químicos ou laboratoriais",
      family: "Serviços profissionais",
      description: "Análises, consultorias e serviços técnicos especializados.",
      offers: ["services"],
      services: ["Análise técnica", "Laudo", "Consultoria técnica", "Coleta programada"],
      products: [],
    },
    photography: {
      label: "Fotografia",
      family: "Serviços profissionais",
      description: "Ensaios, cobertura de eventos e entrega de fotos.",
      offers: ["services"],
      services: ["Ensaio fotográfico", "Eventos", "Foto de produto", "Edição de fotos"],
      products: ["Fotolivro", "Impressões"],
    },
    design: {
      label: "Design e criação",
      family: "Serviços profissionais",
      description: "Identidade visual, peças digitais e projetos criativos.",
      offers: ["services"],
      services: ["Identidade visual", "Artes para redes sociais", "Logotipo", "Diagramação"],
      products: ["Templates", "Materiais digitais"],
    },
    services: {
      label: "Prestação de serviços",
      family: "Serviços profissionais",
      description: "Atendimentos, instalações ou manutenção em geral.",
      offers: ["services"],
      services: ["Consultoria", "Instalação", "Manutenção", "Atendimento em domicílio"],
      products: [],
    },
    other: {
      label: "Outra atividade",
      family: "Outras atividades",
      description: "Descreva sua atividade e escolha as ofertas que combinam com ela.",
      offers: [],
      services: [],
      products: [],
    },
  };
  const modules = {
    clients: "Clientes",
    inbox: "Caixa Unificada",
    opportunities: "Oportunidades",
    products: "Produtos",
    services: "Serviços",
    appointments: "Agenda",
    orders: "Encomendas",
    deliveries: "Entregas",
    inventory: "Estoque",
    team: "Equipe",
    sales: "Vendas",
    finance: "Financeiro",
    reports: "Relatórios",
  };
  const capabilities = {
    appointments: "Agendo atendimentos",
    orders: "Recebo encomendas",
    deliveries: "Faço entregas",
    inventory: "Preciso controlar estoque",
    team: "Trabalho com equipe",
  };
  const clean = (value) => (typeof value === "string" ? value.trim().slice(0, 120) : "");
  const list = (value) =>
    Array.isArray(value)
      ? [
          ...new Set(
            value
              .filter((v) => typeof v === "string")
              .map(clean)
              .filter(Boolean),
          ),
        ].slice(0, 30)
      : [];
  function normalize(value = {}) {
    if (!value || typeof value !== "object" || Array.isArray(value)) value = {};
    const offers = list(value.offers).filter((id) => ["products", "services"].includes(id));
    const caps = Object.fromEntries(
      Object.keys(capabilities).map((id) => [id, value.capabilities?.[id] === true]),
    );
    if (!offers.includes("products")) caps.inventory = false;
    if (!offers.includes("services")) caps.appointments = false;
    const profile = {
      version: 1,
      businessName: clean(value.businessName),
      segment: Object.hasOwn(segments, value.segment) ? value.segment : "other",
      activity: clean(value.activity),
      offers,
      services: offers.includes("services") ? list(value.services) : [],
      productCategories: offers.includes("products") ? list(value.productCategories) : [],
      capabilities: caps,
      modules: list(value.modules).filter((id) => Object.hasOwn(modules, id)),
      ignoredSuggestions: Array.isArray(value.ignoredSuggestions)
        ? [
            ...new Set(
              value.ignoredSuggestions
                .filter((id) => typeof id === "string")
                .map((id) => id.slice(0, 160)),
            ),
          ].slice(0, 60)
        : [],
      completed: value.completed === true,
    };
    profile.modules = profile.modules.filter((id) => availableModules(profile).includes(id));
    return profile;
  }
  function availableModules(profile) {
    return Object.keys(modules).filter((id) => {
      if (["products", "services"].includes(id)) return profile.offers.includes(id);
      if (Object.hasOwn(capabilities, id)) return profile.capabilities[id];
      return true;
    });
  }
  function recommendedModules(profile) {
    return availableModules(profile).filter((id) => !["reports", "team"].includes(id));
  }
  const featureRoutes = {
    products: { label: "Produtos", view: "Produtos e Serviços", type: "Produto" },
    services: { label: "Serviços", view: "Produtos e Serviços", type: "Serviço" },
    inventory: { label: "Estoque", view: "Produtos e Serviços", type: "Produto" },
    clients: { label: "Clientes", view: "Clientes" },
    sales: { label: "Vendas", view: "Vendas" },
    finance: { label: "Financeiro", view: "Financeiro" },
    inbox: { label: "Caixa Unificada", view: "Caixa Unificada" },
    opportunities: { label: "Oportunidades", view: "Oportunidades" },
    reports: { label: "Relatórios", view: "Relatórios" },
  };
  const futureFeatures = {
    appointments: "Agenda",
    orders: "Encomendas",
    deliveries: "Entregas",
    team: "Gestão operacional de equipe",
  };
  function contextualTools(value) {
    const profile = normalize(value);
    const order = [
      ...(profile.offers.includes("services") ? ["services"] : []),
      ...(profile.offers.includes("products") ? ["products", "inventory"] : []),
      "clients",
      "sales",
      "finance",
      "opportunities",
      "inbox",
      "reports",
    ];
    return {
      active: order
        .filter((id) => profile.modules.includes(id))
        .map((id) => ({ id, ...featureRoutes[id] })),
      future: Object.keys(futureFeatures)
        .filter((id) => profile.modules.includes(id))
        .map((id) => ({ id, label: futureFeatures[id] })),
    };
  }
  const catalogText = (text) =>
    String(text)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .replace(/\s+/g, " ")
      .toLowerCase();
  function catalogSuggestions(value, catalog = []) {
    const profile = normalize(value),
      segment = segments[profile.segment];
    const items = [];
    for (const [offer, kind, chosen, fallback] of [
      ["services", "Serviço", profile.services, segment.services],
      ["products", "Produto", profile.productCategories, segment.products],
    ]) {
      if (!profile.offers.includes(offer)) continue;
      for (const label of chosen.length ? chosen : fallback) {
        const id = kind + ":" + catalogText(label);
        if (items.some((item) => item.id === id)) continue;
        if (profile.ignoredSuggestions.includes(id)) continue;
        if (
          kind === "Serviço" &&
          catalog.some(
            (item) =>
              !item.excluida && item.tipo === kind && catalogText(item.nome) === catalogText(label),
          )
        )
          continue;
        items.push({ id, label, kind, name: kind === "Serviço" ? label : "" });
      }
    }
    return items;
  }
  function scope(auth, demoIdentity = "preview", boundScope = "") {
    if (auth?.remote === false)
      return (
        "demo:" +
        ((typeof demoIdentity === "string"
          ? demoIdentity.trim().slice(0, 254).toLowerCase()
          : "preview") || "preview")
      );
    if (auth?.remote !== true) return null;
    const user = auth?.current?.usuario?.id,
      workspace = auth?.current?.negocio?.id;
    if (
      !Number.isSafeInteger(user) ||
      !Number.isSafeInteger(workspace) ||
      boundScope !== `${user}:${workspace}`
    )
      return null;
    return `account:${user}:workspace:${workspace}`;
  }
  function repository(storage, getScope) {
    const key = (id) => "socialmei-business-profile-v1:" + encodeURIComponent(id);
    return {
      scope() {
        try {
          return getScope();
        } catch (_) {
          return null;
        }
      },
      read() {
        try {
          const id = getScope();
          if (!id) return { status: "unavailable", profile: null };
          const raw = storage.getItem(key(id));
          if (!raw) return { status: "empty", profile: null };
          const saved = JSON.parse(raw);
          if (saved?.version !== 1 || saved.scope !== id || saved.profile?.completed !== true)
            return { status: "invalid", profile: null };
          const profile = normalize(saved.profile);
          if (!profile.businessName || !profile.offers.length)
            return { status: "invalid", profile: null };
          return { status: "saved", profile };
        } catch (_) {
          return { status: "unavailable", profile: null };
        }
      },
      save(value, expectedScope = this.scope()) {
        try {
          const id = getScope();
          if (!id || id !== expectedScope) return false;
          const profile = normalize(value);
          if (!profile.completed || !profile.offers.length || !profile.businessName) return false;
          storage.setItem(key(id), JSON.stringify({ version: 1, scope: id, profile }));
          return true;
        } catch (_) {
          return false;
        }
      },
    };
  }
  function browserRepository() {
    return repository(
      {
        getItem: (key) => localStorage.getItem(key),
        setItem: (key, value) => localStorage.setItem(key, value),
      },
      () =>
        scope(
          window.SocialMEIAuth,
          sessionStorage.getItem("socialmei-business-demo-identity") || "preview",
          localStorage.getItem("socialmei-auth-browser-scope") || "",
        ),
    );
  }
  return {
    segments,
    modules,
    capabilities,
    normalize,
    availableModules,
    recommendedModules,
    contextualTools,
    catalogSuggestions,
    featureRoutes,
    futureFeatures,
    scope,
    repository,
    browserRepository,
  };
});
