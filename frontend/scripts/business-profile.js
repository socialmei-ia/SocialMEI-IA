/* Business preferences are local, scoped and independent of account credentials. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIBusinessProfile = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  const segments = {
    barber: {
      label: "Barbearia",
      offers: ["services"],
      services: ["Corte masculino", "Barba", "Sobrancelha"],
      products: ["Cosméticos", "Produtos para cabelo"],
    },
    perfume: {
      label: "Perfumaria",
      offers: ["products"],
      services: [],
      products: ["Perfumes", "Cosméticos", "Cuidados pessoais"],
    },
    tailoring: {
      label: "Costura e confecção",
      offers: ["services"],
      services: ["Ajustes", "Confecção sob encomenda", "Reparos em roupas"],
      products: ["Roupas", "Acessórios"],
    },
    commerce: {
      label: "Comércio",
      offers: ["products"],
      services: [],
      products: ["Alimentos", "Bebidas", "Utilidades"],
    },
    services: {
      label: "Prestação de serviços",
      offers: ["services"],
      services: ["Consultoria", "Instalação", "Manutenção"],
      products: [],
    },
    other: { label: "Outro segmento", offers: [], services: [], products: [] },
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
    scope,
    repository,
    browserRepository,
  };
});
