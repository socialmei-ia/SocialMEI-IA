/* Native V22 account bridge. UI/motion remain in entrada.js. */
(function () {
  "use strict";
  var auth = window.SocialMEIAuth;
  var segments = {
    beleza: "hairdresser",
    comida: "bakery",
    moda: "fashion",
    presentes: "commerce",
    casa: "services",
    saude: "services",
    educacao: "tutor",
    eventos: "photography",
    loja: "commerce",
    digital: "design",
    outra: "other",
  };
  function mappedProfile(value) {
    var offers =
      value.tipo === "produtos"
        ? ["products"]
        : value.tipo === "servicos"
          ? ["services"]
          : ["products", "services"];
    var routine = value.rotina || [];
    var has = function (text) {
      return routine.indexOf(text) !== -1;
    };
    var capabilities = {
      appointments: has("Agendar atendimentos"),
      orders: false,
      deliveries: has("Fazer entregas"),
      inventory: offers.indexOf("products") !== -1 && has("Controlar estoque"),
      team: false,
      walkIns: false,
      quotes: has("Enviar orçamentos"),
      onlineOrders: false,
      recurring: false,
    };
    var modules = ["clients", "inbox", "opportunities", "sales", "finance", "reports"].concat(
      offers,
    );
    Object.keys(capabilities).forEach(function (key) {
      if (capabilities[key]) modules.push(key);
    });
    return {
      version: 1,
      businessName: value.negocio,
      segment: segments[value.area] || "other",
      activity: value.areaLabel || "",
      offers: offers,
      services: offers.indexOf("services") !== -1 ? value.ofertas || [] : [],
      productCategories: offers.indexOf("products") !== -1 ? value.ofertas || [] : [],
      capabilities: capabilities,
      modules: modules,
      ignoredSuggestions: [],
      completed: true,
    };
  }
  window.SocialMEIV22Account = {
    remote: !!auth && auth.remote,
    ready: auth ? auth.ready : Promise.resolve(null),
    auth: auth,
    mappedProfile: mappedProfile,
    areaForSegment: function (segment) {
      return (
        {
          barber: "beleza",
          hairdresser: "beleza",
          manicure: "beleza",
          perfume: "loja",
          cosmetics: "loja",
          beautyReseller: "loja",
          tailoring: "moda",
          fashion: "moda",
          bakery: "comida",
          snack: "comida",
          restaurant: "comida",
          commerce: "loja",
          market: "loja",
          convenience: "loja",
          phoneRepair: "casa",
          electronics: "loja",
          consulting: "digital",
          tutor: "educacao",
          laboratory: "saude",
          photography: "eventos",
          design: "digital",
          services: "casa",
          other: "outra",
        }[segment] || "outra"
      );
    },
    storageKey: function (key) {
      if (
        !auth ||
        !auth.remote ||
        !/^smei(?:-|4_)/.test(key) ||
        key.indexOf("smei-v22-account:") === 0
      )
        return key;
      var user = auth.current;
      return (
        "smei-v22-account:" +
        (user ? user.usuario.id + ":" + user.negocio.id : "anonymous") +
        ":" +
        key
      );
    },
    async loadProfile() {
      if (!auth.current) return null;
      return auth.request("/workspace-profile");
    },
    async saveOnboarding(value, expectedRevision, previousProfile) {
      if (!auth.current) throw Error("Entre na sua conta antes de salvar.");
      if (!Number.isSafeInteger(expectedRevision))
        throw Error("Atualize o perfil antes de salvar.");
      var personName = String(value.nome || "").trim();
      await auth.saveProfile({ nome: personName, nome_negocio: value.negocio });
      var next = mappedProfile(value);
      if (previousProfile) {
        if (value.area === value.originalArea) {
          next.segment = previousProfile.segment;
          next.activity = previousProfile.activity;
        }
        ["orders", "team", "walkIns", "onlineOrders", "recurring"].forEach(function (key) {
          next.capabilities[key] = previousProfile.capabilities[key];
        });
        next.ignoredSuggestions = previousProfile.ignoredSuggestions || [];
        previousProfile.modules.forEach(function (key) {
          if (
            next.modules.indexOf(key) < 0 &&
            ((key === "team" && next.capabilities.team) ||
              (key === "recurring" && next.capabilities.recurring))
          )
            next.modules.push(key);
        });
      }
      return auth.request("/workspace-profile", "PATCH", {
        schema_version: 1,
        expected_revision: expectedRevision,
        profile: next,
      });
    },
    async register(data) {
      var policy = await auth.request("/auth/registration");
      if (policy.mode !== "open" && !data.convite)
        throw Error("O cadastro deste ambiente exige convite. Peça o convite ao administrador.");
      await auth.request("/auth/register", "POST", data);
      location.replace("entrada.html?setup=1#/comecar");
    },
    async login(data) {
      await auth.request("/auth/login", "POST", data);
      location.replace("socialmei-app.html#/inicio");
    },
  };
})();
