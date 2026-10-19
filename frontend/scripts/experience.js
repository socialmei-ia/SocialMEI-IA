/* EXPERIENCE */
(function () {
  const experienceRoot = document.getElementById("experienceRoot");
  if (!experienceRoot) {
    return;
  }
  const screens = [...experienceRoot.querySelectorAll("[data-xp-screen]")];
  let onboardingStep = 1;
  let authMode = "register";
  const businessModel = window.SocialMEIBusinessProfile;
  const businessStore = businessModel.browserRepository();
  let businessDraft = businessModel.normalize();
  let businessEditing = false;
  let businessScope = null;
  let businessToolsChosen = false;
  let businessSegmentChosen = false;
  let businessOffersChosen = false;
  let activeBusinessFamily = null;
  let onboardingReviewReturn = false;
  let onboardingTransition = 0;
  const registrationOnboardingKey = "onboarding-after-registration";
  const PROFILE_KEY = "socialmei-experience-profile-v1";
  function loadExperienceProfile() {
    const fallback = {
      name: "",
      business: "Meu negócio",
      email: "",
      phone: "",
      instagram: "",
      segment: "",
      city: "",
      cnpj: "",
      channels: ["WhatsApp", "Instagram"],
      focus: "Atendimento",
    };
    try {
      const saved = JSON.parse(localStorage.getItem(PROFILE_KEY) || "null");
      if (!saved || typeof saved !== "object" || Array.isArray(saved)) {
        return fallback;
      }
      const result = {
        ...fallback,
      };
      Object.keys(fallback)
        .filter((k) => k !== "channels")
        .forEach((k) => {
          if (typeof saved[k] === "string") {
            result[k] = saved[k];
          }
        });
      if (Array.isArray(saved.channels)) {
        result.channels = saved.channels.filter((c) => ["WhatsApp", "Instagram"].includes(c));
      }
      if (!["Atendimento", "Vendas", "Financeiro", "Automação"].includes(result.focus)) {
        result.focus = fallback.focus;
      }
      return result;
    } catch (_) {
      return fallback;
    }
  }
  const profile = loadExperienceProfile();
  function refreshExperienceProfile() {
    Object.assign(profile, loadExperienceProfile());
    const account = appData.prefs.conta;
    const business = appData.prefs.negocio;
    if (account) {
      if (typeof account.nome === "string") {
        profile.name = account.nome;
      }
      if (typeof account.email === "string") {
        profile.email = account.email;
      }
      if (typeof account.telefone === "string") {
        profile.phone = account.telefone;
      }
    }
    if (typeof business?.nome === "string") {
      profile.business = business.nome;
    }
    if (typeof business?.cnpj === "string") {
      profile.cnpj = business.cnpj;
    }
    if (SocialMEIAuth.remote && SocialMEIAuth.current) {
      const identity = SocialMEIAuth.current;
      Object.assign(profile, {
        name: identity.usuario.nome,
        email: identity.usuario.email,
        phone: identity.usuario.telefone || "",
        business: identity.negocio.nome,
        cnpj: identity.negocio.configuracao?.cnpj || "",
      });
    }
  }
  refreshExperienceProfile();
  document.addEventListener("socialmei-data-change", (event) => {
    if (event.detail?.settingsSaved) {
      refreshExperienceProfile();
    }
  });
  function persistExperienceProfile() {
    profile.name = typeof profile.name === "string" ? profile.name.trim() : "";
    try {
      socialmeiStorageSet(PROFILE_KEY, JSON.stringify(profile), "o perfil da experiência");
    } catch (_) {}
    const first =
      String(profile.name || "")
        .trim()
        .split(/\s+/)[0] || "";
    const initials = initialsFromName(profile.name, "SM");
    if (typeof sessionData !== "undefined" && sessionData.usuario) {
      sessionData.usuario.nome = String(profile.name || "").trim();
      sessionData.usuario.primeiro = first;
      sessionData.usuario.iniciais = initials;
    }
  }
  persistExperienceProfile();

  const q = (s, base = document) => base.querySelector(s);

  const qa = (s, base = document) => [...base.querySelectorAll(s)];
  let registrationAvailable = !SocialMEIAuth.remote;
  if (SocialMEIAuth.remote) {
    const field = document.createElement("div");
    field.className = "experience-field";
    field.hidden = true;
    field.innerHTML =
      '<label for="registerInvite">Código do convite</label><input id="registerInvite" disabled minlength="64" maxlength="64" pattern="[A-Za-z0-9_-]{64}" autocomplete="off" aria-describedby="registerInviteStatus"><small class="experience-field-status" id="registerInviteStatus">Use o convite recebido do administrador.</small>';
    q("#xpRegisterForm [type=submit]").before(field);
    q("#xpRegisterForm [type=submit]").disabled = true;
    const retry = document.createElement("button");
    retry.id = "registrationRetry";
    retry.type = "button";
    retry.className = "btn";
    retry.textContent = "Tentar consultar novamente";
    retry.hidden = true;
    retry.addEventListener("click", loadRegistrationPolicy);
    q("#xpRegisterForm").append(retry);
    q("#registerPassword").minLength = 12;
    q("#registerPassword").maxLength = 128;
    q("#registerPassword").placeholder = "12 caracteres ou mais";
    q("#registerPasswordStatus").textContent = "Use 12 ou mais caracteres.";
    q("#xpRegisterForm .experience-form-hint").textContent =
      "Consultando a disponibilidade do cadastro…";
    q("#xpLoginForm .experience-form-hint").textContent =
      "Use seu e-mail e sua senha cadastrados para acessar seu negócio.";
    qa(".landing-social-login,.authentication-or").forEach((element) => {
      element.hidden = true;
    });
    const remember = q("#xpLoginForm .landing-login-help input");
    remember.id = "loginRemember";
    remember.disabled = false;
    remember.removeAttribute("aria-disabled");
    remember.parentElement.removeAttribute("aria-disabled");
    remember.parentElement.querySelector("small")?.remove();
    const recovery = document.createElement("section");
    recovery.className = "account-recovery-note";
    recovery.id = "accountRecoveryHelp";
    recovery.hidden = true;
    recovery.setAttribute("aria-label", "Recuperar acesso");
    recovery.innerHTML =
      '<b>Vamos recuperar seu acesso</b><p>A recuperação por e-mail está em preparação. Por enquanto, peça ao administrador do projeto para redefinir sua senha pelo procedimento privado.</p><button class="account-button account-button-quiet" type="button" data-close-recovery>Voltar ao login</button>';
    q("#xpLoginForm").append(recovery);
    q(".landing-login-disabled-link").setAttribute("aria-controls", "accountRecoveryHelp");
    q(".landing-login-disabled-link").setAttribute("aria-expanded", "false");
    q(".landing-login-disabled-link").disabled = false;
    q(".landing-login-disabled-link").removeAttribute("aria-disabled");
    q(".landing-login-disabled-link small")?.remove();
  }
  let screenRequest = 0;
  async function showScreen(name) {
    const request = ++screenRequest;
    const previous = q(".experience-screen.is-active");
    if (previous?.dataset.xpScreen === "landing" && name !== "landing") {
      await window.SocialMEIMotion.animate(
        q(".landing-hero-copy"),
        [
          {
            opacity: 1,
            transform: "none",
          },
          {
            opacity: 0,
            transform: "translateY(-6px)",
          },
        ],
        150,
        "ease-exit",
      );
    }
    if (request !== screenRequest) {
      return;
    }
    document.body.classList.add("experience-public");
    document.body.classList.remove("experience-app");
    syncAppTimers();
    document.dispatchEvent(new CustomEvent("socialmei-view-change"));
    applyPublicTheme(document.documentElement.dataset.publicTheme || "light");
    screens.forEach((s) => s.classList.toggle("is-active", s.dataset.xpScreen === name));
    window.scrollTo({
      top: 0,
      behavior: "instant",
    });
    if (name === "auth") {
      syncAuth();
      updatePreview();
    }
    const shell = q(
      ".experience-screen.is-active .authentication-shell,.experience-screen.is-active .onboarding-shell",
    );
    if (shell) {
      motion.animate(
        shell,
        [
          {
            opacity: 0,
            transform: "scale(.985)",
          },
          {
            opacity: 1,
            transform: "none",
          },
        ],
        280,
      );
      motion.animate(
        shell.querySelector(".authentication-form-wrap"),
        [
          {
            opacity: 0.7,
            filter: "blur(4px)",
          },
          {
            opacity: 1,
            filter: "blur(0)",
          },
        ],
        220,
      );
    }
    if (name !== "landing") {
      const heading = q(".experience-screen.is-active h1");
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({
          preventScroll: true,
        });
        motion.animate(
          heading,
          [
            {
              opacity: 0.65,
              transform: "translateY(6px)",
            },
            {
              opacity: 1,
              transform: "none",
            },
          ],
          "motion-medium",
          "ease-enter",
        );
      }
    } else {
      window.SocialMEIPublicMotion?.refresh();
    }
    if (name === "onboarding") {
      hydrateOnboarding();
      syncOnboarding();
      updateOnboardingPreview();
    }
  }
  function enterApp(restoredView = "Início") {
    if (SocialMEIAuth.remote && !SocialMEIAuth.current) {
      authMode = "login";
      showScreen("auth");
      return;
    }
    refreshExperienceProfile();
    persistExperienceProfile();
    if (window.SocialMEIThemes) {
      SocialMEIThemes.applyTokens(document.documentElement, SocialMEIThemes.current());
      document.documentElement.dataset.theme = SocialMEIThemes.current().base;
      document.documentElement.dataset.activeTheme = SocialMEIThemes.active;
      updateThemeButton();
    }
    restoredView =
      {
        "Ferramentas de IA": "Assistente",
        Preferências: "Configurações",
        "Automações / Rotinas": "Automações",
        "Meu negócio": "Visão Geral",
      }[restoredView] || restoredView;
    const first =
      String(profile.name || "")
        .trim()
        .split(/\s+/)[0] || "";
    const initials = initialsFromName(profile.name, "SM");
    if (typeof sessionData !== "undefined" && sessionData.usuario) {
      sessionData.usuario.nome = String(profile.name || "").trim();
      sessionData.usuario.primeiro = first;
      sessionData.usuario.iniciais = initials;
    }
    const foot = document.querySelector(".sb-foot b");
    if (foot) {
      foot.textContent = profile.business || "Meu negócio";
    }
    document.body.classList.remove("experience-public");
    document.body.classList.add("experience-app");
    experienceRoot
      .querySelectorAll(".experience-screen")
      .forEach((s) => s.classList.remove("is-active"));
    if (typeof setView === "function") {
      setView(
        document.querySelector(`[data-view="${CSS.escape(restoredView)}"]`)
          ? restoredView
          : "Início",
      );
    }
    if (typeof renderHeader === "function") {
      renderHeader();
    }
    if (typeof renderClientHome === "function") {
      renderClientHome();
    }
    try {
      sessionStorage.setItem("socialmei-experience-screen", "app");
    } catch (_) {}
    syncAppTimers();
    startN8nSync();
    motion.animate(
      document.querySelector("#app"),
      [
        {
          opacity: 0.4,
        },
        {
          opacity: 1,
        },
      ],
      "motion-medium",
    );
    window.scrollTo({
      top: 0,
      behavior: "instant",
    });
  }
  let logoutBusy = false;
  async function logout() {
    if (logoutBusy) return;
    logoutBusy = true;
    const controls = qa('[data-account-logout],[data-profile-action="sair"]');
    const labels = controls.map((button) => [
      button,
      button.querySelector(".account-exit-label"),
      button.querySelector(".account-exit-label")?.textContent,
    ]);
    controls.forEach((button) => {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    });
    labels.forEach(([, label]) => {
      if (label) label.textContent = "Saindo…";
    });
    try {
      if (typeof saveCurrentDraft === "function") saveCurrentDraft();
      if (SocialMEIAuth.remote) {
        await SocialMEIAuth.logout();
        return;
      }
      try {
        sessionStorage.removeItem("socialmei-experience-screen");
        sessionStorage.removeItem("socialmei-current-view");
        sessionStorage.removeItem("socialmei-business-demo-identity");
      } catch (_) {}
      try {
        document.querySelector("#profileDd")?.classList.remove("open");
      } catch (error) {}
      showScreen("landing");
    } catch (error) {
      toast("Saída não concluída", error.message);
    } finally {
      logoutBusy = false;
      controls.forEach((button) => {
        button.disabled = false;
        button.removeAttribute("aria-busy");
      });
      labels.forEach(([, label, original]) => {
        if (label) label.textContent = original;
      });
    }
  }
  window.SocialMEIExperience = {
    showScreen,
    enterApp,
    logout,
  };
  /* ==================================================
AUTENTICAÇÃO — JAVASCRIPT
================================================== */
  function syncAuth() {
    q(".authentication-tabs").style.setProperty("--auth-index", authMode === "login" ? 1 : 0);
    q(".authentication-panels").dataset.authMode = authMode;
    q(".authentication-shell").dataset.authMode = authMode;
    updatePreview();
    qa("[data-auth-tab]").forEach((b) => {
      const active = b.dataset.authTab === authMode;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-selected", String(active));
      b.tabIndex = active ? 0 : -1;
    });
    qa("[data-auth-panel]").forEach((p) => {
      const active = p.dataset.authPanel === authMode;
      p.classList.toggle("is-active", active);
      p.inert = !active;
      p.setAttribute("aria-hidden", String(!active));
    });
    q("#authConfirmation").textContent = "";
  }
  /* ==================================================
ONBOARDING — JAVASCRIPT
================================================== */
  function renderBusinessOptions(host, name, options, selected) {
    host.replaceChildren();
    const group = document.createElement("div");
    group.className = "business-profile-options";
    options.forEach(([value, label]) => {
      const item = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = name;
      input.value = value;
      input.checked = selected.includes(value);
      item.append(input, document.createTextNode(label));
      group.append(item);
    });
    host.append(group);
  }
  function selectedBusinessValues(name) {
    return qa(`input[name="${name}"]:checked`).map((input) => input.value);
  }
  function renderBusinessSegmentOptions() {
    const select = q("#obSegment");
    const selected = select.value;
    const groups = new Map();
    for (const [id, item] of Object.entries(businessModel.segments)) {
      if (!groups.has(item.family)) groups.set(item.family, document.createElement("optgroup"));
      const option = document.createElement("option");
      option.value = id;
      option.textContent = item.label;
      groups.get(item.family).label = item.family;
      groups.get(item.family).append(option);
    }
    select.replaceChildren(...groups.values());
    select.value = Object.hasOwn(businessModel.segments, selected) ? selected : "other";
  }
  renderBusinessSegmentOptions();
  const businessFamilyCards = [
    {
      id: "Beleza e cuidados",
      title: "Beleza e cuidados",
      symbol: "✂",
      detail: "Cabelo, unhas e produtos de beleza",
      families: ["Beleza e cuidados"],
    },
    {
      id: "Moda e confecção",
      title: "Moda e confecção",
      symbol: "◈",
      detail: "Costura, ajustes e roupas",
      families: ["Moda e confecção"],
    },
    {
      id: "Alimentação",
      title: "Alimentação",
      symbol: "☕",
      detail: "Doces, lanches e refeições",
      families: ["Alimentação"],
    },
    {
      id: "Comércio e varejo",
      title: "Comércio e varejo",
      symbol: "▦",
      detail: "Lojas, mercadinhos e vendas",
      families: ["Comércio e varejo"],
    },
    {
      id: "Tecnologia e reparos",
      title: "Tecnologia e reparos",
      symbol: "⌘",
      detail: "Celulares, eletrônicos e consertos",
      families: ["Tecnologia e reparos"],
    },
    {
      id: "Serviços e outros",
      title: "Serviços e outros",
      symbol: "✳",
      detail: "Autônomos, profissionais e outras atividades",
      families: ["Serviços profissionais", "Outras atividades"],
    },
  ];
  const businessSearchAliases = {
    barber: "barbeiro",
    hairdresser: "cabeleireira cabeleireiro",
    tailoring: "costureira costureiro",
    bakery: "boleira bolos confeiteira",
    phoneRepair: "conserto celular manutenção telefone",
    laboratory: "química químico",
    manicure: "nail designer",
  };
  function businessSearchText(value) {
    return String(value)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR")
      .trim();
  }
  function familyForSegment(segment) {
    const family = businessModel.segments[segment]?.family;
    return businessFamilyCards.find((card) => card.families.includes(family))?.id || null;
  }
  function renderBusinessPicker() {
    const query = businessSearchText(q("#businessSegmentSearch").value);
    const familyHost = q("#businessFamilyChoices");
    familyHost.hidden = !!query;
    q(".business-discovery").classList.toggle("is-searching", !!query);
    qa("button[data-family]", familyHost).forEach((button) => {
      const active = button.dataset.family === activeBusinessFamily;
      button.setAttribute("aria-pressed", String(active));
      button.classList.toggle("is-active", active);
    });
    const choices = Object.entries(businessModel.segments).filter(([id, segment]) =>
      query
        ? businessSearchText(
            [
              segment.label,
              segment.family,
              segment.description,
              businessSearchAliases[id] || "",
            ].join(" "),
          ).includes(query)
        : businessFamilyCards
            .find((card) => card.id === activeBusinessFamily)
            ?.families.includes(segment.family),
    );
    const section = q("#businessSpecialtySection");
    const empty = q("#businessSpecialtyEmpty");
    section.hidden = !choices.length;
    empty.hidden = !(query && !choices.length);
    empty.textContent =
      query && !choices.length
        ? "Não encontramos essa atividade. Tente outro termo ou escolha Serviços e outros."
        : "";
    q("#businessSpecialtyCount").textContent = query
      ? `${choices.length} ${choices.length === 1 ? "atividade encontrada" : "atividades encontradas"}`
      : choices.length
        ? `${choices.length} opções em ${activeBusinessFamily}`
        : "";
    q("#businessSelectionSummary").textContent = businessSegmentChosen
      ? `Atividade escolhida: ${businessModel.segments[businessDraft.segment].label}`
      : "";
    const host = q("#businessSpecialtyChoices");
    host.replaceChildren();
    choices.forEach(([id, segment]) => {
      const label = document.createElement("label");
      label.className = "business-specialty-choice";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "businessSpecialty";
      input.value = id;
      input.checked = businessSegmentChosen && businessDraft.segment === id;
      const description = document.createElement("span");
      const title = document.createElement("b");
      title.textContent = segment.label;
      const detail = document.createElement("small");
      detail.textContent = segment.description;
      description.append(title, detail);
      label.append(input, description);
      input.addEventListener("change", () => {
        if (!input.checked) return;
        chooseBusinessSegment(id, true);
      });
      host.append(label);
    });
  }
  function chooseBusinessSegment(id, focusSpecialty = false) {
    if (!Object.hasOwn(businessModel.segments, id)) return;
    const changed = businessDraft.segment !== id;
    businessDraft.segment = id;
    businessSegmentChosen = true;
    activeBusinessFamily = familyForSegment(id);
    q("#obSegment").value = id;
    // Segment defaults never replace explicit offers or a recovered profile.
    if (changed && !businessOffersChosen)
      businessDraft.offers = [...businessModel.segments[id].offers];
    q("#businessPickerFeedback").textContent = "";
    renderBusinessFields();
    if (focusSpecialty) {
      const picked = q("#businessSpecialtyChoices input:checked");
      picked?.focus({ preventScroll: true });
    }
  }
  const businessFamilyHost = q("#businessFamilyChoices");
  businessFamilyCards.forEach((family) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "business-family-card";
    button.dataset.family = family.id;
    button.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-controls", "businessSpecialtyChoices");
    const symbol = document.createElement("span");
    symbol.className = "business-family-icon";
    symbol.setAttribute("aria-hidden", "true");
    const paths = {
      "Beleza e cuidados":
        '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="m9 8 12 13M9 16 21 3M12 12l9-9"/>',
      "Moda e confecção": '<path d="M9 5a3 3 0 0 1 6 0c0 3-3 3-3 6l9 7H3l9-7"/>',
      Alimentação:
        '<path d="M4 7h13v8a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V7Zm13 1h2a3 3 0 0 1 0 6h-2M7 3v1m5-1v1M2 22h20"/>',
      "Comércio e varejo":
        '<path d="m3 8 2-5h14l2 5M3 8v3a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0V8H3Zm2 6v7h14v-7M9 21v-6h6v6"/>',
      "Tecnologia e reparos":
        '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="m8 11 3 3 5-6M10 19h4"/>',
      "Serviços e outros": '<path d="m14 6 4-4 4 4-4 4-3-1-7 7 1 3-4 3-3-3 3-4 3 1 7-7-1-3Z"/>',
    };
    symbol.innerHTML = `<svg viewBox="0 0 24 24">${paths[family.id]}</svg>`;
    const title = document.createElement("strong");
    title.textContent = family.title;
    const description = document.createElement("small");
    description.textContent = family.detail;
    const mark = document.createElement("span");
    mark.className = "business-family-mark";
    mark.setAttribute("aria-hidden", "true");
    mark.textContent = "✓";
    button.append(symbol, title, description, mark);
    button.addEventListener("click", () => {
      activeBusinessFamily = family.id;
      q("#businessSegmentSearch").value = "";
      renderBusinessPicker();
      q("#businessSpecialtySection")
        .getAnimations()
        .forEach((animation) => animation.cancel());
      motion.animate(
        q("#businessSpecialtySection"),
        [
          { opacity: 0.65, transform: "translateY(4px)" },
          { opacity: 1, transform: "none" },
        ],
        180,
      );
    });
    businessFamilyHost.append(button);
  });
  q("#businessSegmentSearch").addEventListener("input", renderBusinessPicker);
  function renderBusinessFields() {
    const segment = businessModel.segments[businessDraft.segment];
    q("#businessSegmentHint").textContent =
      segment.description + " Você pode escolher mais de um tipo de oferta.";
    q("#businessActivityOther").hidden = businessDraft.segment !== "other";
    q("#obActivity").value = businessDraft.activity;
    qa('input[name="businessOffer"]').forEach((input) => {
      input.checked = businessDraft.offers.includes(input.value);
    });
    const host = q("#businessOfferDetails");
    host.replaceChildren();
    for (const [offer, key, label, suggestions] of [
      ["services", "services", "Quais serviços você realiza?", segment.services],
      ["products", "productCategories", "Que tipos de produtos comercializa?", segment.products],
    ]) {
      if (!businessDraft.offers.includes(offer)) continue;
      const group = document.createElement("fieldset");
      group.className = "business-profile-group";
      const legend = document.createElement("legend");
      legend.textContent = label + " (opcional)";
      const options = document.createElement("div");
      const items = [...new Set([...suggestions, ...businessDraft[key]])];
      renderBusinessOptions(
        options,
        "business-" + key,
        items.map((item) => [item, item]),
        businessDraft[key],
      );
      const customLabel = document.createElement("label");
      customLabel.htmlFor = "businessCustom-" + key;
      customLabel.textContent =
        offer === "services" ? "Adicionar outro serviço" : "Adicionar outra categoria";
      const custom = document.createElement("input");
      custom.id = customLabel.htmlFor;
      custom.maxLength = 80;
      custom.setAttribute("aria-describedby", "obValidation");
      custom.placeholder =
        offer === "services" ? "Ex.: atendimento em domicílio" : "Ex.: perfumes artesanais";
      const field = document.createElement("div");
      field.className = "experience-field";
      field.append(customLabel, custom);
      const add = document.createElement("button");
      add.type = "button";
      add.className = "landing-button";
      add.dataset.businessAdd = key;
      add.setAttribute(
        "aria-label",
        offer === "services" ? "Adicionar serviço" : "Adicionar categoria",
      );
      add.textContent = "+";
      const row = document.createElement("div");
      row.className = "business-custom-row";
      row.append(field, add);
      const count = document.createElement("p");
      count.className = "business-choice-count";
      count.dataset.businessCount = key;
      count.textContent = `${businessDraft[key].length} selecionados`;
      group.append(legend, options, count, row);
      host.append(group);
    }
    const caps = businessModel.routineOptions(businessDraft);
    const capsHost = q("#businessCapabilities");
    capsHost.replaceChildren();
    for (const [title, ids] of [
      ["Atendimentos", ["appointments", "walkIns", "recurring"]],
      ["Pedidos e entregas", ["orders", "deliveries", "onlineOrders", "quotes"]],
      ["Estrutura", ["inventory", "team"]],
    ]) {
      const options = caps.filter(([id]) => ids.includes(id));
      if (!options.length) continue;
      const fieldset = document.createElement("fieldset");
      fieldset.className = "business-routine-group";
      const legend = document.createElement("legend");
      legend.textContent = title;
      const choices = document.createElement("div");
      renderBusinessOptions(
        choices,
        "businessCapability",
        options,
        options.filter(([id]) => businessDraft.capabilities[id]).map(([id]) => id),
      );
      fieldset.append(legend, choices);
      capsHost.append(fieldset);
    }
    const teamNote = document.createElement("p");
    teamNote.className = "management-note";
    teamNote.textContent =
      "Sem equipe selecionada, consideramos que você trabalha sozinho. Você pode ajustar depois.";
    capsHost.append(teamNote);
    const modules = businessModel.availableModules(businessDraft);
    const modulesHost = q("#businessModules");
    const futureOpen = modulesHost.querySelector("details")?.open || false;
    modulesHost.replaceChildren();
    const availableTitle = document.createElement("h3");
    availableTitle.textContent = "Disponíveis no aplicativo";
    const available = document.createElement("div");
    renderBusinessOptions(
      available,
      "businessModule",
      modules
        .filter((id) => !businessModel.futureFeatures[id])
        .map((id) => [id, businessModel.modules[id]]),
      businessDraft.modules,
    );
    modulesHost.append(availableTitle, available);
    const future = modules.filter((id) => businessModel.futureFeatures[id]);
    if (future.length) {
      const details = document.createElement("details");
      details.className = "business-future";
      details.open = futureOpen;
      const summary = document.createElement("summary");
      summary.textContent = "Para o futuro · ainda em desenvolvimento";
      const note = document.createElement("p");
      note.textContent = "Marque apenas seu interesse. Isso não libera uma funcionalidade.";
      const choices = document.createElement("div");
      renderBusinessOptions(
        choices,
        "businessModule",
        future.map((id) => [id, businessModel.modules[id] + " (em desenvolvimento)"]),
        businessDraft.modules,
      );
      details.append(summary, note, choices);
      modulesHost.append(details);
    }
    renderBusinessPicker();
  }
  function suggestedOnboardingModules() {
    const eligible = businessModel.availableModules(businessDraft);
    return [
      ...(businessDraft.offers.includes("services") ? ["services"] : []),
      ...(businessDraft.offers.includes("products") ? ["products"] : []),
      "clients",
      "sales",
      "finance",
    ].filter((id) => eligible.includes(id));
  }
  function startBusinessOnboarding(editing = false) {
    onboardingTransition++;
    onboardingBusy = false;
    onboardingReviewReturn = false;
    businessEditing = editing;
    businessScope = businessStore.scope();
    const saved = businessStore.read();
    businessDraft = saved.profile || businessModel.normalize();
    businessToolsChosen = !!saved.profile;
    businessSegmentChosen = !!saved.profile;
    businessOffersChosen = !!saved.profile;
    q("#businessPickerFeedback").textContent = "";
    activeBusinessFamily = saved.profile ? familyForSegment(businessDraft.segment) : null;
    if (!saved.profile) businessDraft.modules = suggestedOnboardingModules();
    q("#businessSegmentAlternative").open = false;
    q(".onboarding-optional").open = false;
    q("#businessSegmentSearch").value = "";
    onboardingStep = editing ? 2 : 1;
    if (editing) refreshExperienceProfile();
    showScreen("onboarding");
    q("#obSegment").value = businessDraft.segment;
    q("#obBusiness").value =
      businessDraft.businessName ||
      (editing || SocialMEIAuth.remote ? profile.business : "Meu negócio");
    q("#obBusiness").disabled = SocialMEIAuth.remote;
    for (const id of ["obName", "obEmail", "obPhone"]) q("#" + id).readOnly = SocialMEIAuth.remote;
    q("#businessProfileStorageNotice").textContent = SocialMEIAuth.remote
      ? "Preferências deste usuário e negócio, apenas neste navegador. Ainda não sincronizam com o servidor ou outros dispositivos."
      : "Demonstração local · preferências apenas neste navegador. Nenhuma conta é criada no servidor.";
    q("[data-business-cancel]").hidden = !editing;
    q('[data-review-edit-step="1"]').hidden = editing || SocialMEIAuth.remote;
    renderBusinessFields();
    updateOnboardingPreview();
    const heading = q(".onboarding-panel.is-active h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
    q(".onboarding-main").scrollIntoView({ block: "start", behavior: "instant" });
  }
  function collectBusinessStep() {
    if (onboardingStep === 2) {
      businessDraft.businessName = q("#obBusiness").value.trim();
      businessDraft.segment = q("#obSegment").value;
      businessDraft.activity = q("#obActivity").value.trim();
      businessDraft.offers = selectedBusinessValues("businessOffer");
      businessOffersChosen ||= businessDraft.offers.length > 0;
    }
    if (onboardingStep === 3) {
      const choices = readBusinessOfferChoices();
      if (!choices) return false;
      Object.assign(businessDraft, choices);
    }
    if (onboardingStep === 4) {
      const enabled = selectedBusinessValues("businessCapability");
      Object.keys(businessDraft.capabilities).forEach((id) => {
        businessDraft.capabilities[id] = enabled.includes(id);
      });
    }
    if (onboardingStep === 5) {
      businessDraft.modules = selectedBusinessValues("businessModule");
      businessToolsChosen = true;
    }
    businessDraft = businessModel.normalize(businessDraft);
    if (!businessToolsChosen) businessDraft.modules = suggestedOnboardingModules();
    renderBusinessFields();
    renderBusinessReview();
    return true;
  }
  function renderBusinessReview() {
    const host = q("#businessProfileReview");
    host.replaceChildren();
    q("#xpReadySegment").textContent =
      businessDraft.segment === "other" && businessDraft.activity
        ? businessDraft.activity
        : businessModel.segments[businessDraft.segment].label;
    const title = q("#xpReadyTitle");
    if (title) {
      title.textContent = profile.name.trim()
        ? `Seu negócio está quase pronto, ${profile.name.trim().split(/\s+/)[0]}.`
        : "Seu negócio está quase pronto.";
    }
    const business = q("#xpReadyBusiness");
    if (business) {
      business.textContent = profile.business || "Meu negócio";
    }
    const channels = q("#xpReadyChannels");
    if (channels) {
      channels.textContent =
        qa('.experience-choice.is-selected[data-choice-group="channel"]')
          .map((x) => x.dataset.choice)
          .join(", ") || "Você pode conectar depois";
    }
    const focus = q("#xpReadyFocus");
    if (focus) {
      focus.textContent =
        qa('.experience-choice.is-selected[data-choice-group="focus"]')
          .map((x) => x.dataset.choice)
          .join(", ") || "Organizar minha rotina";
    }
    const rows = [
      ["Seus dados", [profile.name, profile.email, profile.phone].filter(Boolean).join(" · ")],
      [
        "Atividade",
        businessDraft.segment === "other"
          ? businessDraft.activity || "A definir"
          : businessModel.segments[businessDraft.segment].label,
      ],
      [
        "Ofertas",
        businessDraft.offers.map((id) => (id === "products" ? "Produtos" : "Serviços")).join(" e "),
      ],
      ["Serviços sugeridos", businessDraft.services.join(", ") || "Nenhum selecionado"],
      ["Categorias sugeridas", businessDraft.productCategories.join(", ") || "Nenhuma selecionada"],
      [
        "Rotina",
        Object.keys(businessDraft.capabilities)
          .filter((id) => businessDraft.capabilities[id])
          .map((id) => businessModel.capabilities[id])
          .join(" · ") || "Sem necessidades adicionais informadas",
      ],
      [
        "Ferramentas de interesse",
        businessDraft.modules
          .map(
            (id) =>
              businessModel.modules[id] +
              (businessModel.futureFeatures[id] ? " (em desenvolvimento)" : ""),
          )
          .join(", ") || "Escolher depois",
      ],
    ];
    rows.forEach(([label, value]) => {
      const row = document.createElement("div"),
        title = document.createElement("small"),
        text = document.createElement("b");
      title.textContent = label;
      text.textContent = value;
      row.append(title, text);
      host.append(row);
    });
  }
  function finishBusinessOnboarding() {
    businessDraft.completed = true;
    if (!businessStore.save(businessDraft, businessScope)) {
      q("#obValidation").textContent =
        "Não foi possível salvar neste navegador. Confira a sessão e a permissão de armazenamento e tente novamente. Suas respostas continuam nesta tela.";
      return false;
    }
    if (!SocialMEIAuth.remote) {
      appData.prefs.conta = {
        ...(appData.prefs.conta || {}),
        nome: profile.name,
        email: profile.email,
        telefone: profile.phone,
      };
      appData.prefs.negocio = {
        ...(appData.prefs.negocio || {}),
        nome: profile.business,
        cnpj: profile.cnpj,
        telefone: profile.phone,
      };
      saveAppData();
    }
    persistExperienceProfile();
    document.dispatchEvent(new CustomEvent("socialmei-business-profile-change"));
    return true;
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-business-profile-edit]")) startBusinessOnboarding(true);
    if (event.target.closest("[data-business-cancel]")) {
      if (onboardingBusy) return;
      onboardingTransition++;
      refreshExperienceProfile();
      enterApp("Configurações");
    }
  });
  q("#obSegment").addEventListener("change", () => {
    q("#businessSegmentSearch").value = "";
    chooseBusinessSegment(q("#obSegment").value);
  });
  experienceRoot.addEventListener("change", (event) => {
    if (event.target.matches('input[name="businessOffer"]')) {
      businessOffersChosen = true;
      businessDraft.activity = q("#obActivity").value.trim();
      businessDraft.offers = selectedBusinessValues("businessOffer");
      businessDraft = businessModel.normalize(businessDraft);
      renderBusinessFields();
    }
  });
  function hydrateOnboarding() {
    for (const [id, key] of [
      ["obName", "name"],
      ["obEmail", "email"],
      ["obPhone", "phone"],
      ["obBusiness", "business"],
      ["obSegment", "segment"],
      ["obInstagram", "instagram"],
      ["obCity", "city"],
      ["obCnpj", "cnpj"],
    ]) {
      const element = q("#" + id);
      if (element) {
        element.value = profile[key] || "";
      }
    }
    qa(".experience-choice").forEach((element) => {
      const selected =
        element.dataset.choiceGroup === "channel"
          ? profile.channels.includes(element.dataset.choice)
          : element.dataset.choice === profile.focus;
      element.classList.toggle("is-selected", selected);
      element.setAttribute("aria-pressed", String(selected));
    });
  }
  function syncOnboarding() {
    const steps = ["Você", "Negócio", "Ofertas", "Rotina", "Ferramentas", "Revisão"];
    const nextLabel = steps[onboardingStep];
    q(".onboarding-screen").dataset.onboardingStep = onboardingStep;
    q("#xpOnboardingStepStatus").textContent =
      `Etapa ${onboardingStep} de 6 · ${steps[onboardingStep - 1]}` +
      (nextLabel ? ` · Próxima: ${nextLabel}` : " · Última etapa");
    const bar = q("#xpOnboardingProgress span");
    if (bar) {
      bar.style.transform = `scaleX(${Math.min(1, (onboardingStep - 1) / 5)})`;
    }
    q("#xpOnboardingProgress").setAttribute("role", "progressbar");
    q("#xpOnboardingProgress").setAttribute("aria-label", "Configuração do espaço");
    q("#xpOnboardingProgress").setAttribute("aria-valuemin", "0");
    q("#xpOnboardingProgress").setAttribute("aria-valuemax", "6");
    q("#xpOnboardingProgress").setAttribute("aria-valuenow", onboardingStep);
    q("#xpOnboardingProgress").setAttribute(
      "aria-valuetext",
      `Etapa ${onboardingStep} de 6: ${steps[onboardingStep - 1]}`,
    );
    qa("[data-onboard-panel]").forEach((p) => {
      const active = Number(p.dataset.onboardPanel) === onboardingStep;
      p.classList.toggle("is-active", active);
      p.inert = !active;
      p.setAttribute("aria-hidden", String(!active));
    });
    qa("[data-onboard-step]").forEach((s) => {
      const n = Number(s.dataset.onboardStep);
      s.classList.toggle("is-current", n === onboardingStep);
      s.classList.toggle("is-done", n < onboardingStep);
      s.setAttribute("aria-current", n === onboardingStep ? "step" : "false");
      const canRevisit = n < onboardingStep && n >= (businessEditing ? 2 : 1);
      s.disabled = !canRevisit;
      s.setAttribute(
        "aria-label",
        canRevisit ? `Voltar para ${steps[n - 1]}` : `Etapa ${n}: ${steps[n - 1]}`,
      );
      const mark = s.querySelector("span");
      if (mark) {
        mark.textContent = n < onboardingStep ? "✓" : n;
      }
    });
    q("[data-onboard-back]").classList.toggle("show", onboardingStep > (businessEditing ? 2 : 1));
    q("[data-business-skip]").hidden = ![3, 4, 5].includes(onboardingStep);
    q("[data-onboard-next]").textContent =
      onboardingReviewReturn && onboardingStep !== 6
        ? "Aplicar e voltar à revisão"
        : onboardingStep === 5
          ? "Revisar escolhas"
          : onboardingStep === 6
            ? "Salvar e entrar no SocialMEI"
            : "Continuar";
  }
  function collectStep() {
    if (onboardingStep === 1) {
      profile.name = q("#obName")?.value.trim() || profile.name;
      profile.email = q("#obEmail")?.value.trim() || profile.email;
      profile.phone = q("#obPhone")?.value.trim() || "";
    }
    if (onboardingStep === 2) {
      profile.business = q("#obBusiness")?.value.trim() || profile.business;
      profile.cnpj = q("#obCnpj")?.value.trim() || "";
      profile.segment = q("#obSegment")?.value || "";
      profile.instagram = q("#obInstagram")?.value.trim() || "";
      profile.city = q("#obCity")?.value.trim() || "";
    }
    if (onboardingStep === 5) {
      profile.channels = qa('.experience-choice.is-selected[data-choice-group="channel"]').map(
        (x) => x.dataset.choice,
      );
      profile.focus =
        qa('.experience-choice.is-selected[data-choice-group="focus"]').map(
          (x) => x.dataset.choice,
        )[0] || "Atendimento";
    }
  }
  experienceRoot.addEventListener("click", (event) => {
    const completedStep = event.target.closest("button[data-onboard-step]");
    if (completedStep) {
      const target = Number(completedStep.dataset.onboardStep);
      if (!onboardingBusy && target >= (businessEditing ? 2 : 1) && target < onboardingStep) {
        collectStep();
        if (!collectBusinessStep()) return;
        stepTransition(target);
      }
      return;
    }
    const reviewEdit = event.target.closest("[data-review-edit-step]");
    if (reviewEdit && onboardingStep === 6 && !onboardingBusy) {
      onboardingReviewReturn = true;
      stepTransition(Number(reviewEdit.dataset.reviewEditStep));
      return;
    }
    const go = event.target.closest("[data-xp-go]");
    if (go) {
      onboardingTransition++;
      const dest = go.dataset.xpGo;
      if (dest === "app") {
        enterApp();
      } else {
        showScreen(dest);
      }
      return;
    }
    const auth = event.target.closest("[data-auth-tab]");
    if (auth) {
      authMode = auth.dataset.authTab;
      syncAuth();
      return;
    }
    const start = event.target.closest("[data-start-signup]");
    if (start) {
      authMode = "register";
      showScreen("auth");
      return;
    }
    const login = event.target.closest("[data-start-login]");
    if (login) {
      authMode = "login";
      showScreen("auth");
      return;
    }
    const scroll = event.target.closest("[data-scroll-to]");
    if (scroll) {
      event.preventDefault();
      document.getElementById(scroll.dataset.scrollTo)?.scrollIntoView({
        behavior: window.SocialMEIMotion.reduced ? "auto" : "smooth",
        block: "start",
      });
      return;
    }
    const choice = event.target.closest(".experience-choice");
    if (choice) {
      const group = choice.dataset.choiceGroup;
      if (group === "channel") {
        choice.classList.toggle("is-selected");
      } else {
        qa(`.experience-choice[data-choice-group="${group}"]`).forEach((x) =>
          x.classList.remove("is-selected"),
        );
        choice.classList.add("is-selected");
      }
      qa(".experience-choice").forEach((c) =>
        c.setAttribute("aria-pressed", String(c.classList.contains("is-selected"))),
      );
      updateOnboardingPreview();
      return;
    }
    const skip = event.target.closest("[data-business-skip]");
    if (skip && !onboardingBusy && [3, 4, 5].includes(onboardingStep)) {
      collectStep();
      if (!collectBusinessStep()) return;
      navigateOnboardingForward();
      return;
    }
    const next = event.target.closest("[data-onboard-next]");
    if (next) {
      if (onboardingBusy) return;
      if (!validateOnboard()) {
        return;
      }
      collectStep();
      if (!collectBusinessStep()) return;
      if (onboardingStep < 6) {
        navigateOnboardingForward();
      } else if (finishBusinessOnboarding()) {
        enterApp(businessEditing ? "Configurações" : "Início");
      }
      return;
    }
    const back = event.target.closest("[data-onboard-back]");
    if (back && !onboardingBusy && onboardingStep > (businessEditing ? 2 : 1)) {
      collectStep();
      if (!collectBusinessStep()) return;
      stepTransition(onboardingStep - 1);
      return;
    }
  });
  experienceRoot.addEventListener("submit", async (event) => {
    if (!event.target.matches("#xpRegisterForm,#xpLoginForm")) {
      return;
    }
    event.preventDefault();
    if (submitBusy) {
      return;
    }
    const fields = [...event.target.querySelectorAll("input")].filter(
      (element) => element.type !== "checkbox",
    );
    if (!fields.map(validateAuth).every(Boolean)) {
      fields.find((element) => !element.validity.valid)?.focus();
      return;
    }
    const submitScreenRequest = screenRequest;
    submitBusy = true;
    const button = event.target.querySelector('[type="submit"]');
    const label = button.textContent;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "Preparando seu espaço…";
    try {
      if (event.target.id === "xpRegisterForm") {
        button.textContent = "Confira seu número…";
        if (!(await SocialMEIContacts.confirmPhone(q("#registerPhone").value))) {
          q("#registerPhone").focus();
          return;
        }
        if (screenRequest !== submitScreenRequest) return;
        button.textContent = "Preparando seu espaço…";
      }
      if (SocialMEIAuth.remote) {
        if (event.target.id === "xpLoginForm") {
          await SocialMEIAuth.login({
            email: q("#loginEmail").value.trim(),
            senha: q("#loginPassword").value,
            lembrar: q("#loginRemember").checked,
          });
        } else {
          if (!registrationAvailable) {
            throw new Error("Recarregue a página para conferir a disponibilidade do cadastro.");
          }
          sessionStorage.setItem(
            registrationOnboardingKey,
            q("#registerEmail").value.trim().toLowerCase(),
          );
          await SocialMEIAuth.register({
            nome: q("#registerName").value.trim(),
            email: q("#registerEmail").value.trim(),
            telefone: q("#registerPhone").value.trim(),
            senha: q("#registerPassword").value,
            ...(!q("#registerInvite").disabled
              ? { convite: q("#registerInvite").value.trim() }
              : {}),
          });
        }
        return;
      }
      await wait(motion.reduced ? 0 : motion.ms("motion-medium"));
      button.textContent = "✓ Pronto";
      await wait(motion.reduced ? 0 : motion.ms("motion-fast"));
      await motion.animate(
        q(".authentication-form-wrap"),
        [
          {
            opacity: 1,
            transform: "none",
          },
          {
            opacity: 0,
            transform: "scale(.985) translateX(8px)",
          },
        ],
        "motion-instant",
        "ease-exit",
      );
      if (
        screenRequest !== submitScreenRequest ||
        !event.target.closest(".experience-screen.is-active")
      ) {
        return;
      }
      if (event.target.id === "xpLoginForm") {
        profile.email = q("#loginEmail").value.trim();
        sessionStorage.setItem("socialmei-business-demo-identity", profile.email.toLowerCase());
        persistExperienceProfile();
        enterApp();
      } else {
        profile.name = q("#registerName").value.trim() || profile.name;
        profile.email = q("#registerEmail").value.trim();
        profile.phone = q("#registerPhone").value.trim();
        persistExperienceProfile();
        sessionStorage.setItem("socialmei-business-demo-identity", profile.email.toLowerCase());
        // Reutiliza os dados do cadastro no preenchimento inicial do onboarding.
        q("#obName").value = profile.name;
        q("#obEmail").value = profile.email;
        q("#obPhone").value = profile.phone;
        startBusinessOnboarding();
      }
      q("#registerPassword").value = "";
      q("#loginPassword").value = "";
      qa("#registerPassword,#loginPassword").forEach((element) => {
        element.type = "password";
        element.removeAttribute("aria-invalid");
        element
          .closest(".experience-field")
          .classList.remove("is-valid", "is-invalid", "is-filled");
        q("#" + element.id + "Status").textContent =
          element.id === "registerPassword" ? "Use 8 ou mais caracteres." : " ";
        element.dataset.visited = "";
        const toggle = q(`[data-password-toggle="${element.id}"]`);
        toggle.textContent = "Mostrar";
        toggle.setAttribute("aria-pressed", "false");
        toggle.setAttribute("aria-label", "Mostrar senha");
      });
    } catch (error) {
      sessionStorage.removeItem(registrationOnboardingKey);
      const feedback = q("#authConfirmation");
      feedback.textContent = error.message || "Não foi possível entrar. Tente novamente.";
      feedback.tabIndex = -1;
      feedback.focus();
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = label;
      submitBusy = false;
    }
  });
  /* LANDING — JAVASCRIPT
  Controla reveals e parallax com observador compartilhado e frames acionados por eventos. */
  const motion = window.SocialMEIMotion;
  const publicTokens = getComputedStyle(q(".landing-page"));
  const publicMs = (name) => {
    const value = publicTokens.getPropertyValue("--" + name).trim();
    return parseFloat(value) * (value.endsWith("ms") ? 1 : 1000);
  };
  const MOTION = Object.freeze({
    stagger: motion.ms("stagger"),
    reveal: publicMs("motion-reveal"),
    display: publicMs("motion-display"),
    parallaxLimit: 18,
  });
  const hero = q("#xpHero");
  const nav = q(".landing-navigation");
  const desktop = matchMedia("(min-width:1001px) and (pointer:fine)");
  const parallax = qa("[data-parallax]", experienceRoot);
  const liveParallax = new Set();
  const pending = new Set();
  const cleanupTimers = new Set();
  const icon = q(".hero-live-icon");
  const icons = icon ? [...icon.children] : [];
  let scrollFrame = 0;
  let revealObserver = null;
  let heroStarted = false;
  let heroInView = false;
  let iconTimer = 0;
  let iconIndex = 0;
  let iconBusy = false;
  let previousScroll = scrollY;
  let previousTime = performance.now();
  let resizeNeeded = true;
  qa('[data-reveal="stagger"]', experienceRoot).forEach((group) => {
    [...group.children].forEach((element, i) => {
      if (!element.dataset.reveal) {
        element.dataset.reveal = "up";
      }
      if (!element.style.getPropertyValue("--reveal-delay")) {
        element.style.setProperty("--reveal-delay", Math.min(i, 5) * MOTION.stagger + "ms");
      }
    });
  });
  const targets = qa("[data-reveal]", experienceRoot).filter(
    (element) => element.dataset.reveal !== "stagger",
  );
  targets.forEach((element) => pending.add(element));
  function later(callback, milliseconds) {
    const id = setTimeout(() => {
      cleanupTimers.delete(id);
      callback();
    }, milliseconds);
    cleanupTimers.add(id);
    return id;
  }
  function isLanding() {
    return (
      document.body.classList.contains("experience-public") &&
      q('[data-xp-screen="landing"].is-active')
    );
  }
  function calibrateHero() {
    const copy = q(".landing-hero-copy");
    const stage = q(".landing-hero-visual");
    if (!copy || !stage || !isLanding()) {
      return;
    }
    const copyBottom = copy.offsetTop + copy.offsetHeight;
    const cardHeight = q(".landing-showcase-card:nth-child(3)")?.offsetHeight || stage.offsetHeight;
    hero.style.setProperty(
      "--hero-stage-gap",
      Math.round(Math.max(32, innerHeight - copyBottom - cardHeight * 0.24)) + "px",
    );
    resizeNeeded = false;
  }
  function reveal(element, immediate = false) {
    if (element.classList.contains("is-visible")) {
      return;
    }
    pending.delete(element);
    const delay = parseFloat(getComputedStyle(element).getPropertyValue("--reveal-delay")) || 0;
    if (immediate || motion.reduced) {
      element.style.transition = "none";
      element.style.transitionDelay = "0ms";
    } else {
      element.style.willChange =
        element.dataset.reveal === "blur" ? "opacity, transform, filter" : "opacity, transform";
      later(
        () => {
          element.style.removeProperty("will-change");
          element.style.setProperty("--reveal-delay", "0ms");
        },
        MOTION.display + delay + 80,
      );
    }
    element.classList.add("is-visible");
    if (!element.hasAttribute("data-parallax")) {
      revealObserver?.unobserve(element);
    }
    // A rotina finita controla o fluxo; o reveal apenas apresenta a superfície.
  }
  function heroArrival(immediate = false) {
    if (heroStarted) {
      return;
    }
    heroStarted = true;
    qa("[data-hero-reveal]", experienceRoot).forEach((element) => {
      if (immediate || motion.reduced) {
        element.style.transition = "none";
        element.style.transitionDelay = "0ms";
      } else {
        element.style.willChange = element.closest(".hero-line")
          ? "opacity, transform, filter"
          : "opacity, transform";
        const delay = parseFloat(element.style.getPropertyValue("--hero-delay")) || 0;
        later(
          () => {
            element.style.removeProperty("will-change");
            element.style.setProperty("--hero-delay", "0ms");
          },
          MOTION.display + delay + 80,
        );
      }
      element.classList.add("is-visible");
    });
  }
  function stopIcon() {
    clearTimeout(iconTimer);
    iconTimer = 0;
  }
  function iconAllowed() {
    return icons.length > 1 && heroInView && !document.hidden && !motion.reduced && isLanding();
  }
  function scheduleIcon() {
    stopIcon();
    if (!iconAllowed() || iconBusy) {
      return;
    }
    iconTimer = setTimeout(async () => {
      iconTimer = 0;
      if (!iconAllowed()) {
        return;
      }
      iconBusy = true;
      const previous = icons[iconIndex];
      const nextIndex = (iconIndex + 1) % icons.length;
      const next = icons[nextIndex];
      previous.classList.remove("is-current");
      next.classList.add("is-current");
      iconIndex = nextIndex;
      await Promise.all([
        motion.animate(
          previous,
          [
            {
              opacity: 1,
              filter: "blur(0)",
              transform: "scale(1)",
            },
            {
              opacity: 0,
              filter: "blur(5px)",
              transform: "scale(.84)",
            },
          ],
          260,
        ),
        motion.animate(
          next,
          [
            {
              opacity: 0,
              filter: "blur(5px)",
              transform: "scale(.84)",
            },
            {
              opacity: 1,
              filter: "blur(0)",
              transform: "scale(1)",
            },
          ],
          260,
        ),
      ]);
      iconBusy = false;
      scheduleIcon();
    }, 2200);
  }
  function resetParallax() {
    cancelAnimationFrame(scrollFrame);
    scrollFrame = 0;
    parallax.forEach((element) => {
      element.style.removeProperty("--scroll-drift");
      element.style.removeProperty("--mockup-progress");
    });
  }
  function updateScroll() {
    scrollFrame = 0;
    if (document.hidden || !isLanding()) {
      return;
    }
    if (resizeNeeded) {
      calibrateHero();
    }
    const now = performance.now();
    const distanceMoved = Math.abs(scrollY - previousScroll);
    const velocity = distanceMoved / Math.max(16, now - previousTime);
    previousTime = now;
    previousScroll = scrollY;
    nav?.classList.toggle("is-scrolled", scrollY > 20);
    const height = innerHeight;
    const arrivals = [];
    const drifts = []; // O observador cuida das entradas normais; a varredura atende saltos rápidos de rolagem.
    if (velocity > 1.5 || distanceMoved > height * 0.45) {
      pending.forEach((element) => {
        const box = element.getBoundingClientRect();
        if (!box.width || !box.height) {
          return;
        }
        if (box.bottom <= 76) {
          arrivals.push([element, true]);
        } else if (box.top < height * 0.95 && box.bottom > 76) {
          arrivals.push([element, velocity > 1.5]);
        }
      });
    }
    if (desktop.matches && !motion.reduced) {
      liveParallax.forEach((element) => {
        const box = element.getBoundingClientRect();
        if (box.bottom < 0 || box.top > height) {
          return;
        }
        const progress = Math.max(
          -1,
          Math.min(1, (height / 2 - (box.top + box.height / 2)) / ((height + box.height) / 2)),
        );
        const distance = Math.max(
          -MOTION.parallaxLimit,
          Math.min(MOTION.parallaxLimit, Number(element.dataset.parallax) || 0),
        );
        drifts.push([element, (progress * distance).toFixed(2) + "px"]);
        if (element.dataset.scrollProgress === "mockup") {
          drifts.push([
            element,
            Math.max(0, Math.min(1, (height - box.top) / (height * 0.75 + box.height * 0.25))),
            "progress",
          ]);
        }
      });
    }
    arrivals.forEach(([element, instant]) => reveal(element, instant));
    drifts.forEach(([element, value, type]) =>
      element.style.setProperty(
        type === "progress" ? "--mockup-progress" : "--scroll-drift",
        value,
      ),
    );
    if (scrollY > hero.offsetHeight) {
      heroArrival(true);
    }
  }
  function queueScroll() {
    if (!scrollFrame && !document.hidden) {
      scrollFrame = requestAnimationFrame(updateScroll);
    }
  }
  window.addEventListener("scroll", queueScroll, {
    passive: true,
  });
  window.addEventListener(
    "resize",
    () => {
      resizeNeeded = true;
      queueScroll();
    },
    {
      passive: true,
    },
  );
  desktop.addEventListener("change", () => {
    resetParallax();
    resizeNeeded = true;
    queueScroll();
  });
  if ("IntersectionObserver" in window) {
    revealObserver = new IntersectionObserver(
      (entries) => {
        const arrivals = [];
        entries.forEach(({ target, isIntersecting }) => {
          if (target === hero && isIntersecting) {
            heroArrival(scrollY > hero.offsetHeight);
          }
          if (target === icon) {
            heroInView = isIntersecting;
            scheduleIcon();
          }
          if (target.hasAttribute("data-parallax")) {
            if (isIntersecting) {
              liveParallax.add(target);
            } else {
              liveParallax.delete(target);
            }
          }
          if (isIntersecting && target.hasAttribute("data-reveal")) {
            arrivals.push(target);
          }
        });
        arrivals.forEach((target) => reveal(target));
        queueScroll();
      },
      {
        threshold: 0.12,
        rootMargin: "0px 0px -7% 0px",
      },
    );
    revealObserver.observe(hero);
    if (icon) {
      revealObserver.observe(icon);
    }
    new Set([...targets, ...parallax]).forEach((element) => revealObserver.observe(element));
  } else {
    targets.forEach((element) => reveal(element, true));
    heroArrival(true);
  }
  function revealCurrentView(immediate = false) {
    if (!isLanding()) {
      return;
    }
    const height = innerHeight;
    const arrivals = [];
    pending.forEach((element) => {
      const box = element.getBoundingClientRect();
      if (box.width && box.height && box.top < height * 0.95) {
        arrivals.push([element, immediate || box.bottom <= 76]);
      }
    });
    arrivals.forEach(([element, instant]) => reveal(element, instant));
    if (scrollY > hero.offsetHeight) {
      heroArrival(true);
    }
    resizeNeeded = true;
    queueScroll();
    scheduleIcon();
  }
  document.addEventListener("visibilitychange", () => {
    document.documentElement.classList.toggle("tab-hidden", document.hidden);
    if (document.hidden) {
      stopIcon();
      resetParallax();
    } else {
      revealCurrentView(true);
    }
  });
  document.addEventListener("socialmei-motion-change", () => {
    stopIcon();
    if (motion.reduced) {
      resetParallax();
      targets.forEach((element) => reveal(element, true));
      heroArrival(true);
    } else {
      queueScroll();
      scheduleIcon();
    }
  });
  document.addEventListener("socialmei-view-change", () =>
    queueMicrotask(() => {
      if (!isLanding()) {
        stopIcon();
        resetParallax();
      } else {
        revealCurrentView();
      }
    }),
  );
  window.addEventListener("pageshow", () => {
    revealCurrentView(scrollY > 0);
  });
  window.addEventListener("pagehide", (event) => {
    stopIcon();
    resetParallax();
    if (!event.persisted) {
      revealObserver?.disconnect();
      cleanupTimers.forEach(clearTimeout);
      cleanupTimers.clear();
    }
  });
  window.SocialMEIPublicMotion = {
    refresh: revealCurrentView,
  };
  document.documentElement.classList.add("js-motion-ready");
  calibrateHero();
  requestAnimationFrame(() => {
    heroArrival(scrollY > hero.offsetHeight);
    revealCurrentView(scrollY > 0);
  });
  document.fonts?.ready.then(() => {
    resizeNeeded = true;
    queueScroll();
  });
  experienceRoot.addEventListener("click", (event) => {
    const button = event.target.closest("[data-module-test]");
    if (!button) {
      return;
    }
    const card = button.closest(".landing-module");
    const active = !card.classList.contains("is-demo-active");
    card.classList.toggle("is-demo-active", active);
    button.setAttribute("aria-pressed", String(active));
    button.setAttribute(
      "aria-label",
      (active ? "Recomeçar exemplo de " : "Ver exemplo de ") +
        card.querySelector(".landing-kicker").textContent,
    );
    button.textContent = active ? "Recomeçar →" : "Ver exemplo →";
    card.querySelector(".landing-module-state").textContent = active
      ? button.dataset.moduleTest
      : "Prévia ilustrativa";
    const status = card.querySelector("[data-sale-preview]");
    if (status) {
      status.textContent = active ? "Pago" : "Pendente";
      status.classList.toggle("blue", !active);
    }
  });
  experienceRoot.addEventListener("keydown", (event) => {
    const gallery = event.target.closest(".landing-gallery-window");
    if (
      !gallery ||
      event.target !== gallery ||
      !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
    ) {
      return;
    }
    event.preventDefault();
    const behavior = motion.reduced ? "auto" : "smooth";
    if (event.key === "Home" || event.key === "End") {
      gallery.scrollTo({
        left: event.key === "Home" ? 0 : gallery.scrollWidth,
        behavior,
      });
    } else {
      gallery.scrollBy({
        left: (event.key === "ArrowRight" ? 1 : -1) * gallery.clientWidth * 0.8,
        behavior,
      });
    }
  });

  /* Demonstrações ilustrativas: dados locais, sem chamadas de API ou gravações. */
  const demoChannels = {
    wa: {
      name: "Ana Paula",
      initials: "AP",
      channel: "WhatsApp",
      question: "Tem no azul tamanho M? Quero duas peças.",
      answer: "Sim! Temos no azul e no areia. Posso separar as duas para você.",
      sale: "Venda #1042 · Ana Paula",
      value: "R$ 380,00",
      status: "Pix recebido",
      history: "2 pedidos",
      tag: "Moda",
      note: "Prefere tamanho M. Gosta de receber novidades em azul.",
      next: "Retornar em 7 dias para saber como ficaram as peças.",
    },
    ig: {
      name: "João Mendes",
      initials: "JM",
      channel: "Instagram",
      question: "Vi seu trabalho no Instagram. Consegue fazer um orçamento de duas peças?",
      answer: "Claro, João! Vou organizar os itens e te enviar o orçamento por aqui.",
      sale: "Orçamento · João Mendes",
      value: "R$ 380,00",
      status: "Em conversa",
      history: "Primeiro contato",
      tag: "Orçamento",
      note: "Conheceu o ateliê pelo Instagram. Quer duas peças.",
      next: "Enviar orçamento e confirmar os tamanhos.",
    },
  };
  function setDemoChannel(channel) {
    const data = demoChannels[channel];
    if (!data) {
      return;
    }
    qa("[data-demo-channel]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.demoChannel === channel)),
    );
    qa("[data-demo-name]").forEach((element) => (element.textContent = data.name));
    qa("[data-demo-avatar]").forEach((element) => (element.textContent = data.initials));
    const ids = {
      ChannelLabel: "channel",
      Question: "question",
      Answer: "answer",
      Sale: "sale",
      Value: "value",
      Status: "status",
      History: "history",
      Tag: "tag",
      Note: "note",
      Next: "next",
    };
    Object.entries(ids).forEach(([id, key]) => (q("#smDemo" + id).textContent = data[key]));
    q(".landing-thread-item.active .landing-person small").textContent = data.question;
    q(".landing-thread-item.active .landing-channel-mark").setAttribute("aria-label", data.channel);
    q(".landing-thread-item.active use").setAttribute("href", "#landing-logo-" + channel);
    q("#smDemoStatus").classList.toggle("blue", channel === "ig");
    q(".landing-inbox-context .landing-person small").textContent =
      channel === "ig" ? "Primeiro contato" : "Cliente recorrente";
    q(".landing-inbox-context .landing-tags span").textContent =
      channel === "ig" ? "Novo contato" : "Cliente recorrente";
    motion.animate(
      q(".landing-messages"),
      [
        {
          opacity: 0.6,
          transform: "translateY(4px)",
        },
        {
          opacity: 1,
          transform: "none",
        },
      ],
      "motion-base",
    );
  }
  const aiExamples = {
    reply: [
      "Sugestão · revise antes de enviar",
      "Sim, Juliana! Ainda temos a camisa azul no tamanho M. Quer que eu reserve uma para você?",
    ],
    summary: [
      "Resumo da conversa",
      "Juliana veio do Instagram, procura a camisa azul no tamanho M e quer reservar uma unidade. O próximo passo é confirmar a disponibilidade.",
    ],
    follow: [
      "Próxima ação sugerida",
      "Confirmar a reserva com Juliana e combinar a retirada. Se ela não responder, preparar um retorno com o contexto da camisa azul, tamanho M.",
    ],
  };
  const demoSteps = [
    [
      "Primeiro, um “olá”.",
      [
        ["Seu nome", "Beatriz Souza"],
        ["E-mail", "beatriz@exemplo.com"],
        ["WhatsApp", "(81) 99999-0000"],
        ["Seu espaço", "Começa por você"],
      ],
    ],
    [
      "Agora, o seu negócio.",
      [
        ["Nome do negócio", "Beatriz · Studio de unhas"],
        ["Segmento", "Beleza e serviços"],
        ["Cidade", "Belo Jardim · PE"],
        ["Instagram", "@studio.exemplo"],
      ],
    ],
    [
      "O que merece atenção?",
      [
        ["Canais escolhidos", "WhatsApp e Instagram"],
        ["Primeiro foco", "Atendimento e vendas"],
        ["Próximo passo", "Preparar meu espaço"],
        ["Integrações", "Conectar depois"],
      ],
    ],
  ];
  let demoStep = 1;
  function setDemoStep(step, focus = false) {
    demoStep = Math.max(1, Math.min(3, step));
    const data = demoSteps[demoStep - 1];
    qa("[data-demo-step]").forEach((button) => {
      const active = Number(button.dataset.demoStep) === demoStep;
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
      if (active && focus) {
        button.focus();
      }
    });
    q("#smSetupPanel").setAttribute("aria-labelledby", "smSetupTab" + demoStep);
    q("#smSetupLabel").textContent = "Etapa " + demoStep + " de 3";
    q("#smSetupHeading").textContent = data[0];
    q(".landing-setup-progress").style.setProperty("--setup-progress", demoStep / 3);
    q("#smSetupFields").replaceChildren(
      ...data[1].map(([label, value]) => {
        const box = document.createElement("div");
        const small = document.createElement("small");
        const b = document.createElement("b");
        small.textContent = label;
        b.textContent = value;
        box.append(small, b);
        return box;
      }),
    );
    q("#smSetupNext").textContent = demoStep === 3 ? "Criar meu espaço →" : "Próxima etapa →";
    // Atualiza o conteúdo da prévia de configuração; o controlador central cuida da entrada.
  }
  experienceRoot.addEventListener("click", (event) => {
    const channel = event.target.closest("[data-demo-channel]");
    if (channel) {
      setDemoChannel(channel.dataset.demoChannel);
    }
    const ai = event.target.closest("[data-demo-ai]");
    if (ai) {
      qa("[data-demo-ai]").forEach((button) =>
        button.setAttribute("aria-pressed", String(button === ai)),
      );
      const result = q("#smAIResult");
      const example = aiExamples[ai.dataset.demoAi];
      result.querySelector("small").textContent = example[0];
      result.querySelector("span").textContent = example[1];
      // Atualiza o estado legível da demonstração de IA.
    }
    const step = event.target.closest("[data-demo-step]");
    if (step) {
      setDemoStep(Number(step.dataset.demoStep));
    }
    if (event.target.closest("#smSetupNext")) {
      if (demoStep < 3) {
        setDemoStep(demoStep + 1);
      } else {
        authMode = "register";
        showScreen("auth");
      }
    }
  });
  experienceRoot.addEventListener("keydown", (event) => {
    const tab = event.target.closest("[data-demo-step]");
    if (
      !tab ||
      !["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)
    ) {
      return;
    }
    event.preventDefault();
    let next = Number(tab.dataset.demoStep);
    if (event.key === "Home") {
      next = 1;
    } else if (event.key === "End") {
      next = 3;
    }
    if (["ArrowRight", "ArrowDown"].includes(event.key)) {
      next = (Number(tab.dataset.demoStep) % 3) + 1;
    }
    if (["ArrowLeft", "ArrowUp"].includes(event.key)) {
      next = ((Number(tab.dataset.demoStep) + 1) % 3) + 1;
    }
    setDemoStep(next, true);
  });
  let previewTimer = 0;
  let submitBusy = false;
  let onboardingBusy = false;
  function updatePreview() {
    const name = q("#registerName").value.trim();
    const first = name.split(/\s+/)[0].slice(0, 28);
    q("#authPreviewGreeting").textContent =
      authMode === "login"
        ? "Seu dia continua aqui."
        : first
          ? `Olá, ${first}.`
          : "Seu espaço começa aqui.";
    q("#authPreviewDescription").textContent =
      authMode === "login"
        ? "Uma conversa para responder. Uma venda para registrar. Seu próximo passo está à mão."
        : "Conversa, cliente e próxima ação. Tudo encontra seu lugar.";
    q("#previewName").textContent = name || "Seu perfil";
    q("#previewEmail").textContent = q("#registerEmail").value.trim() || "Seu e-mail aparece aqui";
    const digits = q("#registerPhone").value.replace(/\D/g, "");
    const phoneResult = SocialMEIContacts.phone(q("#registerPhone").value, true);
    const domesticDigits =
      digits.startsWith("55") && q("#registerPhone").value.startsWith("+")
        ? digits.slice(2)
        : digits;
    q("#previewPhone").textContent = phoneResult.valid
      ? q("#registerPhone").value.startsWith("+") && !digits.startsWith("55")
        ? `+… ••••-${digits.slice(-4)}`
        : `(${domesticDigits.slice(0, 2)}) •••••-${digits.slice(-4)}`
      : "Um canal para conversar";
    for (const [id, built] of [
      [
        "previewProfile",
        !!name && q("#registerEmail").validity.valid && !!q("#registerEmail").value,
      ],
      ["previewChannel", phoneResult.valid],
      ["previewSecurity", q("#registerPassword").value.length >= (SocialMEIAuth.remote ? 12 : 8)],
    ]) {
      const element = q("#" + id);
      const changed = element.classList.contains("is-built") !== built;
      element.classList.toggle("is-built", built);
      if (changed && built) {
        motion.animate(
          element,
          [
            {
              opacity: 0.6,
              transform: "translateX(-8px)",
            },
            {
              opacity: 1,
              transform: "none",
            },
          ],
          "motion-medium",
        );
      }
    }
    const values = [
      !!name,
      q("#registerEmail").validity.valid && !!q("#registerEmail").value,
      phoneResult.valid,
      q("#registerPassword").value.length >= (SocialMEIAuth.remote ? 12 : 8),
    ];
    q("#authBuildProgress").textContent =
      `Prévia local · ${values.filter(Boolean).length} de 4 dados`;
    qa(".landing-build-track i").forEach((element, i) =>
      element.classList.toggle("is-complete", values[i]),
    );
    q("#previewSecurityText").textContent = values[3]
      ? SocialMEIAuth.remote
        ? "Senha protegida no servidor"
        : "Senha pronta · não será salva"
      : "Defina sua senha para continuar";
    qa(".authentication-flow").forEach(
      (element) =>
        (element.querySelector(":scope>span").textContent = element.classList.contains("is-built")
          ? "✓"
          : "＋"),
    );
  }
  function maskPhone(element) {
    const result = SocialMEIContacts.phone(element.value);
    if (result.valid) element.value = result.value;
  }
  function validateAuth(input) {
    if (input.id === "registerEmail" || input.id === "loginEmail") {
      const email = input.value.trim();
      input.setCustomValidity(
        !email || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
          ? ""
          : "Informe um e-mail completo, como voce@empresa.com.",
      );
    }
    if (input.id === "registerName") {
      input.setCustomValidity(input.value.trim() ? "" : "Informe seu nome.");
    }
    if (input.id === "registerPhone") {
      SocialMEIContacts.validateField(input, true);
    }
    const valid = input.validity.valid;
    const field = input.closest(".experience-field");
    const status = q("#" + input.id + "Status");
    field.classList.toggle("is-valid", valid);
    field.classList.toggle("is-invalid", !valid);
    input.setAttribute("aria-invalid", String(!valid));
    if (status) {
      status.textContent = valid
        ? input.id === "registerPassword"
          ? `✓ ${SocialMEIAuth.remote ? 12 : 8}+ caracteres`
          : "✓ Tudo certo"
        : input.validity.valueMissing
          ? "Preencha este campo."
          : input.validity.typeMismatch
            ? "Use um e-mail como voce@empresa.com."
            : input.id === "registerPassword"
              ? `Use pelo menos ${SocialMEIAuth.remote ? 12 : 8} caracteres.`
              : input.validationMessage;
    }
    return valid;
  }
  qa("#xpRegisterForm input,#xpLoginForm input")
    .filter((element) => element.type !== "checkbox")
    .forEach((element) => {
      element.addEventListener("blur", () => {
        element.dataset.visited = "1";
        validateAuth(element);
      });
      element.addEventListener("input", () => {
        element.closest(".experience-field").classList.toggle("is-filled", !!element.value);
        if (element.dataset.visited) {
          validateAuth(element);
        }
        clearTimeout(previewTimer);
        previewTimer = setTimeout(updatePreview, motion.ms("motion-fast"));
      });
    });
  q("#obPhone").addEventListener("blur", (event) => maskPhone(event.target));
  experienceRoot.addEventListener("keydown", (event) => {
    const tab = event.target.closest("[data-auth-tab]");
    if (tab && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      authMode =
        event.key === "Home"
          ? "register"
          : event.key === "End"
            ? "login"
            : tab.dataset.authTab === "register"
              ? "login"
              : "register";
      syncAuth();
      q(`[data-auth-tab="${authMode}"]`).focus();
    }
  });
  experienceRoot.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-password-toggle]");
    if (toggle) {
      const input = q("#" + toggle.dataset.passwordToggle);
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.textContent = show ? "Ocultar" : "Mostrar";
      toggle.setAttribute("aria-pressed", String(show));
      toggle.setAttribute("aria-label", show ? "Ocultar senha" : "Mostrar senha");
    }
    if (event.target.closest(".landing-social-login")) {
      q("#authConfirmation").textContent = SocialMEIAuth.remote
        ? "Login com Google não está disponível. Use sua conta do piloto."
        : "Demonstração: o login com Google não está conectado. Use o formulário para explorar seu espaço.";
    }
    if (event.target.closest(".landing-login-help a")) {
      event.preventDefault();
      q("#authConfirmation").textContent =
        "Demonstração: recuperação de senha ainda não está conectada.";
    }
    if (SocialMEIAuth.remote && event.target.closest(".landing-login-disabled-link")) {
      q("#accountRecoveryHelp").hidden = false;
      q(".landing-login-disabled-link").setAttribute("aria-expanded", "true");
      q("#accountRecoveryHelp [data-close-recovery]").focus();
    }
  });
  experienceRoot.addEventListener("click", (event) => {
    if (!event.target.closest("[data-close-recovery]")) return;
    q("#accountRecoveryHelp").hidden = true;
    q(".landing-login-disabled-link").setAttribute("aria-expanded", "false");
    q(".landing-login-disabled-link").focus();
  });
  qa(".experience-choice").forEach((choice) =>
    choice.setAttribute("aria-pressed", String(choice.classList.contains("is-selected"))),
  );
  function updateOnboardingPreview() {
    const tools = q("#obPreviewTools");
    tools.replaceChildren();
    for (const id of selectedBusinessValues("businessModule").filter(
      (id) => !businessModel.futureFeatures[id],
    )) {
      const item = document.createElement("li");
      item.textContent = businessModel.modules[id];
      tools.append(item);
    }
    const name = q("#obName").value.trim() || profile.name;
    const business = q("#obBusiness").value.trim() || profile.business;
    q("#obPreviewBusiness").textContent = business;
    q("#obPreviewPerson").textContent = name;
    q("#obPreviewAvatar").textContent = initialsFromName(business, "SM");
    q("#obPreviewChannels").textContent =
      qa('.experience-choice.is-selected[data-choice-group="channel"]')
        .map((x) => x.dataset.choice)
        .join(", ") || "Escolher depois";
    q("#obPreviewFocus").textContent =
      qa('.experience-choice.is-selected[data-choice-group="focus"]')
        .map((x) => x.dataset.choice)
        .join(", ") || "Organizar minha rotina";
  }
  function validateOnboard() {
    if (onboardingStep === 2 && !businessSegmentChosen) {
      const message = "Escolha uma área e uma atividade para continuar.";
      q("#obValidation").textContent = message;
      q("#businessPickerFeedback").textContent = message;
      const target = q("#businessSegmentSearch").value
        ? q("#businessSegmentSearch")
        : q("#businessSpecialtyChoices input") || q("#businessFamilyChoices button");
      target?.focus();
      return false;
    }
    if (onboardingStep === 2 && !selectedBusinessValues("businessOffer").length) {
      q("#obValidation").textContent = "Escolha produtos, serviços ou ambos para continuar.";
      q('input[name="businessOffer"]').focus();
      return false;
    }
    const fields = qa(".onboarding-panel.is-active input,.onboarding-panel.is-active select");
    fields.forEach((element) => {
      let message = "";
      const value = element.value.trim();
      if (element.required && !value) {
        message = "Preencha este campo antes de continuar.";
      }
      if (element.id === "obPhone" && value) {
        const contact = SocialMEIContacts.phone(value);
        if (!contact.valid) message = contact.message;
      }
      if (element.id === "obCnpj" && value && !isValidCnpj(value)) {
        message = "Confira os 14 dígitos do CNPJ ou deixe em branco.";
      }
      element.setCustomValidity(message);
      const feedback = q("#" + element.id + "Feedback");
      if (feedback)
        feedback.textContent =
          message ||
          (element.validity.valid
            ? ""
            : element.type === "email"
              ? "Informe um e-mail válido."
              : "Confira este campo.");
    });
    const invalid = fields.find((element) => !element.checkValidity());
    fields.forEach((element) =>
      element.setAttribute("aria-invalid", String(!element.validity.valid)),
    );
    if (invalid) {
      q("#obValidation").textContent = "Confira o campo indicado antes de continuar.";
      for (let parent = invalid.parentElement; parent; parent = parent.parentElement) {
        if (parent.matches("details")) parent.open = true;
      }
      invalid.focus();
      invalid.scrollIntoView({ block: "center", behavior: "instant" });
      return false;
    }
    return true;
  }
  qa(".onboarding-screen input,.onboarding-screen select").forEach((element) => {
    element.addEventListener("input", () => {
      element.setCustomValidity("");
      element.removeAttribute("aria-invalid");
      q("#obValidation").textContent = "";
      const feedback = q("#" + element.id + "Feedback");
      if (feedback) feedback.textContent = "";
      updateOnboardingPreview();
    });
    element.addEventListener("blur", () => {
      if (!element.closest(".onboarding-panel.is-active") || element.readOnly || element.disabled)
        return;
      const feedback = q("#" + element.id + "Feedback");
      if (!feedback) return;
      let message = "";
      if (element.required && !element.value.trim())
        message = "Preencha este campo antes de continuar.";
      else if (element.type === "email" && !element.validity.valid)
        message = "Informe um e-mail válido.";
      else if (
        element.id === "obPhone" &&
        element.value &&
        !SocialMEIContacts.phone(element.value).valid
      )
        message = SocialMEIContacts.phone(element.value).message;
      else if (element.id === "obCnpj" && element.value && !isValidCnpj(element.value))
        message = "Confira os 14 dígitos do CNPJ ou deixe em branco.";
      feedback.textContent = message;
      element.setAttribute("aria-invalid", String(!!message));
    });
    element.addEventListener("change", updateOnboardingPreview);
  });
  function navigateOnboardingForward() {
    const target = onboardingReviewReturn ? 6 : onboardingStep + 1;
    if (onboardingReviewReturn) {
      const current = onboardingStep;
      for (let step = businessEditing ? 2 : 1; step < 6; step++) {
        onboardingStep = step;
        syncOnboarding();
        if (!validateOnboard()) {
          q(".onboarding-panel.is-active [aria-invalid=true]")?.focus();
          return;
        }
      }
      onboardingStep = current;
      syncOnboarding();
    }
    stepTransition(target);
  }
  async function stepTransition(nextStep) {
    if (onboardingBusy || nextStep === onboardingStep) return;
    onboardingBusy = true;
    const transition = ++onboardingTransition;
    const direction = nextStep > onboardingStep ? 1 : -1;
    const old = q(".onboarding-panel.is-active");
    const controls = qa(
      ".onboarding-actions button,[data-onboard-step],[data-xp-screen='onboarding'] [data-xp-go]",
    );
    controls.forEach((button) => (button.disabled = true));
    old.inert = true;
    try {
      await motion.animate(
        old,
        [
          { opacity: 1, transform: "none" },
          { opacity: 0, transform: `translateX(${-direction * 8}px)` },
        ],
        160,
        "ease-exit",
      );
      if (
        transition !== onboardingTransition ||
        !q(".onboarding-screen").classList.contains("is-active")
      )
        return;
      onboardingStep = nextStep;
      if (nextStep === 6) onboardingReviewReturn = false;
      syncOnboarding();
      updateOnboardingPreview();
      q("#obValidation").textContent = "";
      const next = q(".onboarding-panel.is-active");
      const title = next.querySelector("h1,h2");
      // The panel remains inert until entrance settles, preventing input loss mid-transition.
      next.inert = true;
      controls.forEach((button) => (button.disabled = true));
      q(".onboarding-main").scrollIntoView({ block: "start", behavior: "instant" });
      await motion.animate(
        next,
        [
          { opacity: 0, transform: `translateX(${direction * 8}px)` },
          { opacity: 1, transform: "none" },
        ],
        180,
        "ease-enter",
      );
      if (transition !== onboardingTransition) return;
      next.inert = false;
      if (title) {
        title.tabIndex = -1;
        title.focus({ preventScroll: true });
      }
    } finally {
      if (transition === onboardingTransition) {
        onboardingBusy = false;
        controls.forEach((button) => (button.disabled = false));
        syncOnboarding();
      }
    }
  }
  // Footer height follows wrapped controls, zoom, storage notices and validation errors.
  const onboardingFooter = q(".onboarding-footer");
  new ResizeObserver(() => {
    q(".onboarding-screen").style.setProperty(
      "--onboard-footer-height",
      `${Math.ceil(onboardingFooter.getBoundingClientRect().height)}px`,
    );
  }).observe(onboardingFooter);
  function readBusinessOfferChoices() {
    const choices = {};
    for (const key of ["services", "productCategories"]) {
      const input = q("#businessCustom-" + key);
      const pending = (input?.value || "")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      choices[key] = [...new Set([...selectedBusinessValues("business-" + key), ...pending])];
      if (choices[key].length > 30) {
        q("#obValidation").textContent =
          "Você pode escolher até 30 opções por grupo. Remova uma escolha para adicionar outra.";
        input?.setAttribute("aria-invalid", "true");
        input?.focus();
        input?.scrollIntoView({ block: "center", behavior: "instant" });
        return null;
      }
      input?.removeAttribute("aria-invalid");
    }
    return choices;
  }
  function addBusinessSuggestion(key) {
    if (onboardingBusy || !["services", "productCategories"].includes(key)) return;
    const input = q("#businessCustom-" + key);
    if (!input.value.trim()) {
      input.focus();
      return;
    }
    const choices = readBusinessOfferChoices();
    if (!choices) return;
    Object.assign(businessDraft, choices);
    businessDraft = businessModel.normalize(businessDraft);
    q("#obValidation").textContent = "";
    renderBusinessFields();
    q("#businessCustom-" + key).focus();
  }
  experienceRoot.addEventListener("click", (event) => {
    const add = event.target.closest("[data-business-add]");
    if (add) addBusinessSuggestion(add.dataset.businessAdd);
  });
  experienceRoot.addEventListener("keydown", (event) => {
    if (
      event.key !== "Enter" ||
      event.isComposing ||
      !event.target.closest(".onboarding-panel.is-active")
    )
      return;
    if (event.target.id.startsWith("businessCustom-")) {
      event.preventDefault();
      addBusinessSuggestion(event.target.id.replace("businessCustom-", ""));
    } else if (event.target.matches("input:not([type=checkbox]):not([type=radio])")) {
      event.preventDefault();
      q("[data-onboard-next]").click();
    }
  });
  experienceRoot.addEventListener("change", (event) => {
    const input = event.target;
    if (input.name?.startsWith("business-")) {
      const key = input.name.replace("business-", "");
      if (input.checked && selectedBusinessValues(input.name).length > 30) {
        input.checked = false;
        q("#obValidation").textContent = "Você pode escolher até 30 opções por grupo.";
      }
      const count = q(`[data-business-count="${key}"]`);
      const length = selectedBusinessValues(input.name).length;
      if (count) count.textContent = `${length} ${length === 1 ? "selecionado" : "selecionados"}`;
    }
    if (input.name === "businessModule") updateOnboardingPreview();
  });
  window.addEventListener("pagehide", () => clearTimeout(previewTimer));

  /* AUTOMAÇÕES — JAVASCRIPT
  Rotinas editáveis são rascunhos locais; não executam fluxos externos. */
  const RULE_KEY = "socialmei-automation-drafts-v1";
  const triggerOptions = [
    "Uma cobrança estiver a 1 dia do vencimento",
    "Uma conversa aguardar resposta por 2 horas",
    "Uma venda for concluída",
    "Um cliente concluir uma nova compra",
  ];
  const actionOptions = [
    "Preparar lembrete de cobrança",
    "Sinalizar atendimento pendente",
    "Preparar tarefa de entrega",
    "Preparar contato de pós-venda",
  ];
  triggerOptions.push("Uma venda aguardar Pix por 2 dias");
  triggerOptions.push("Um cliente ficar 30 dias sem comprar");
  triggerOptions.push("Um pedido estiver pronto");
  triggerOptions.push("Uma entrega for registrada");
  actionOptions.push("Preparar agradecimento");
  actionOptions.push("Preparar pedido de avaliação");
  const defaultRules = triggerOptions.slice(0, 4).map((when, i) => ({
    id: "rule-" + i,
    name: [
      "Lembrete de cobrança",
      "Conversa sem resposta",
      "Próxima etapa da venda",
      "Retorno ao cliente",
    ][i],
    when,
    then: actionOptions[i],
    enabled: i < 2,
  }));
  let rules = defaultRules;
  let editingRule = null;
  let assistantIntent = "summary";
  let focusedRule = null;
  let ruleFilter = "all";
  try {
    const saved = JSON.parse(localStorage.getItem(RULE_KEY));
    if (
      Array.isArray(saved) &&
      saved.every(
        (r) =>
          r &&
          typeof r.id === "string" &&
          typeof r.name === "string" &&
          triggerOptions.includes(r.when) &&
          actionOptions.includes(r.then),
      )
    ) {
      rules = saved;
    }
  } catch (_) {}
  let savedRules = cloneData(rules);
  function saveRules() {
    if (!socialmeiStorageSet(RULE_KEY, JSON.stringify(rules), "os rascunhos de automação")) {
      rules = cloneData(savedRules);
      toast("Rotina não salva", "O armazenamento do navegador não permitiu a alteração.");
      return false;
    }
    savedRules = cloneData(rules);
    return true;
  }
  // Modelos usam a mesma coleção e chave; os metadados adicionais permanecem compatíveis.
  const ruleModels = [
    {
      name: "Cobrar Pix pendente após 2 dias",
      when: "Uma venda aguardar Pix por 2 dias",
      then: "Preparar lembrete de cobrança",
      after: "Conferir recebimento antes de cobrar",
      area: "Financeiro",
    },
    {
      name: "Agradecer depois de venda paga",
      when: "Uma venda for concluída",
      then: "Preparar agradecimento",
      after: "Revisar o agradecimento com o cliente",
      area: "Vendas",
    },
    {
      name: "Retomar cliente após 30 dias sem comprar",
      when: "Um cliente ficar 30 dias sem comprar",
      then: "Preparar contato de pós-venda",
      after: "Revisar o histórico e escolher o momento do contato",
      area: "Clientes",
    },
    {
      name: "Avisar pedido pronto",
      when: "Um pedido estiver pronto",
      then: "Preparar tarefa de entrega",
      after: "Confirmar disponibilidade e combinar a retirada",
      area: "Vendas",
    },
    {
      name: "Lembrar de responder conversa parada",
      when: "Uma conversa aguardar resposta por 2 horas",
      then: "Sinalizar atendimento pendente",
      after: "Ler a conversa e responder a dúvida em aberto",
      area: "Atendimento",
    },
    {
      name: "Pedir avaliação após entrega",
      when: "Uma entrega for registrada",
      then: "Preparar pedido de avaliação",
      after: "Confirmar a entrega e revisar o pedido de avaliação",
      area: "Clientes",
    },
  ];
  let ruleArea = "Todas";
  let assistantTone = "Curto";
  let assistantDrafts = [];
  let ruleTests = readStoredJson("socialmei-automation-tests-v1", []);
  let assistantHistory = readStoredJson("socialmei-ai-drafts-v1", []);
  if (!Array.isArray(ruleTests)) {
    ruleTests = [];
  }
  ruleTests = ruleTests
    .filter(
      (t) =>
        t &&
        typeof t.ruleId === "string" &&
        typeof t.text === "string" &&
        !Number.isNaN(Date.parse(t.at)),
    )
    .slice(0, 100);
  if (!Array.isArray(assistantHistory)) {
    assistantHistory = [];
  }
  assistantHistory = assistantHistory
    .filter(
      (t) =>
        t &&
        typeof t.text === "string" &&
        typeof t.name === "string" &&
        !Number.isNaN(Date.parse(t.at)),
    )
    .slice(0, 10);
  const ruleAreaOf = (r) =>
    r.area ||
    (/cobrança|cobran|Pix/i.test(r.when + " " + r.then)
      ? "Financeiro"
      : /conversa|atendimento/i.test(r.when + " " + r.then)
        ? "Atendimento"
        : /cliente|pós-venda/i.test(r.when + " " + r.then)
          ? "Clientes"
          : "Vendas");
  const ruleAfter = (r) =>
    r.after ||
    {
      "Preparar lembrete de cobrança": "Conferir vencimento e recebimento antes de cobrar",
      "Sinalizar atendimento pendente": "Ler a conversa e revisar a resposta",
      "Preparar tarefa de entrega": "Confirmar o item e combinar a entrega",
      "Preparar contato de pós-venda": "Revisar o histórico e escolher o próximo contato",
      "Preparar agradecimento": "Revisar o agradecimento",
      "Preparar pedido de avaliação": "Confirmar a entrega antes de pedir avaliação",
    }[r.then] ||
    "Revisar a tarefa preparada";
  function ruleIcon(rule) {
    switch (ruleAreaOf(rule)) {
      case "Financeiro":
        return "wallet";
      case "Atendimento":
        return "inbox";
      case "Clientes":
        return "users";
      default:
        return "bag";
    }
  }
  const localTime = (iso) =>
    new Date(iso).toLocaleString("pt-BR", {
      timeZone: APP_TIMEZONE,
      dateStyle: "short",
      timeStyle: "short",
    });
  /**
   * Reinicia a revelação curta do fluxo. Sem efeito com movimento reduzido (o CSS não anima).
   * @param {"enter"|"switch"} mode Entrada na tela ou troca de rotina.
   */
  function revealRuleFlow(mode) {
    const flow = q("#automationFeature .management-rule-flow");
    if (!flow || motion.reduced) {
      return;
    }
    flow.removeAttribute("data-reveal");
    void flow.offsetWidth;
    flow.dataset.reveal = mode;
  }
  function renderRules() {
    const featured =
      rules.find((rule) => rule.id === focusedRule) ||
      rules.find((rule) => rule.enabled) ||
      rules[0];
    focusedRule = featured?.id || null;
    const last7 = ruleTests.filter((t) => Date.parse(t.at) >= Date.now() - 7 * 864e5).length;
    q("#nvRuleKpis").innerHTML = [
      [
        "Rotinas ativas",
        rules.filter((rule) => rule.enabled).length,
        "Configuração salva · sem execução automática",
      ],
      [
        "Rotinas pausadas",
        rules.filter((rule) => !rule.enabled).length,
        "Só mudam quando você decidir",
      ],
      ["Testes simulados · 7 dias", last7, "Apenas testes feitos por você · nenhum envio"],
    ]
      .map(
        ([
          label,
          value,
          note,
        ]) => /* HTML */ `<article class="management-kpi" title="${escapeHtml(note)}">
                  <b>${value}</b><span>${escapeHtml(label)}</span
                  ><small class="sr-only">${escapeHtml(note)}</small>
                </article>`,
      )
      .join("");
    q("#nvRuleModels").innerHTML = ruleModels
      .map(
        (m, i) => /* HTML */ `<article class="management-model">
                  <h4>${escapeHtml(m.name)}</h4>
                  <p class="management-note">${escapeHtml(m.after)}.</p>
                  <span class="pill draft">${m.area}</span>
                  <button class="management-button sm" data-rule-model="${i}">Usar modelo</button>
                </article>`,
      )
      .join("");
    q("#automationFeature").innerHTML = featured
      ? /* HTML */ `<div class="rule-feature-head">
                  <div class="rule-feature-title">
                    <h3>${escapeHtml(featured.name)}</h3>
                    <span class="pill ${featured.enabled ? "info" : "draft"}"
                      >${featured.enabled ? "Ativa" : "Pausada"}</span
                    >
                  </div>
                  <div class="management-inline-actions rule-feature-actions">
                    <button class="management-button" data-rule-test="${escapeHtml(featured.id)}">
                      Testar com um exemplo</button
                    ><button class="management-button" data-rule-edit="${escapeHtml(featured.id)}">
                      Editar</button
                    ><button class="management-button" data-rule-history="${escapeHtml(featured.id)}">
                      Histórico
                    </button>
                  </div>
                </div>
                <div class="management-rule-flow">
                  <section class="management-rule-step">
                    ${renderIcon(ruleIcon(featured))}<small>Quando</small
                    ><b>${escapeHtml(featured.when)}</b>
                  </section>
                  <i class="management-rule-link" aria-hidden="true"></i>
                  <section class="management-rule-step">
                    ${renderIcon(/lembrete|cobrança/.test(featured.then) ? "wallet" : /entrega/.test(featured.then) ? "box" : "note")}<small
                      >Faça</small
                    ><b>${escapeHtml(featured.then)}</b>
                  </section>
                  <i class="management-rule-link" aria-hidden="true"></i>
                  <section class="management-rule-step">
                    ${renderIcon("check")}<small>Depois</small
                    ><b>${escapeHtml(ruleAfter(featured))}</b>
                  </section>
                </div>`
      : emptyMarkup(
          "Nenhuma rotina cadastrada",
          "Escolha um modelo ou crie sua primeira rotina.",
          '<button class="management-button" data-rule-create>Nova rotina</button>',
        );
    q("#nvRuleStates").innerHTML = [
      ["all", "Todas", rules.length],
      ["active", "Habilitadas", rules.filter((rule) => rule.enabled).length],
      ["paused", "Pausadas", rules.filter((rule) => !rule.enabled).length],
    ]
      .map(
        ([v, l, n]) => /* HTML */ `<button
                  class="management-chip"
                  data-rule-filter="${v}"
                  aria-pressed="${ruleFilter === v}"
                >
                  ${l}<b>${n}</b>
                </button>`,
      )
      .join("");
    q("#nvRuleAreas").innerHTML = ["Todas", "Vendas", "Atendimento", "Financeiro", "Clientes"]
      .map(
        (area) => /* HTML */ `<button
                  class="management-chip"
                  data-rule-area="${area}"
                  aria-pressed="${ruleArea === area}"
                >
                  ${area === "Todas" ? "Todas as áreas" : area}<b
                    >${area === "Todas" ? rules.length : rules.filter((rule) => ruleAreaOf(rule) === area).length}</b
                  >
                </button>`,
      )
      .join("");
    const query = normalizedText(q("#nvRuleSearch").value);
    const shown = rules.filter(
      (rule) =>
        (ruleFilter === "all" ||
          (ruleFilter === "active" && rule.enabled) ||
          (ruleFilter === "paused" && !rule.enabled)) &&
        (ruleArea === "Todas" || ruleAreaOf(rule) === ruleArea) &&
        normalizedText(rule.name).includes(query),
    );
    q("#automationList").innerHTML = shown.length
      ? renderManagementTable(
          "Biblioteca de rotinas",
          ["Rotina", "Área", "Último teste", "Situação", "Ações"],
          shown.map((r) => {
            const last = ruleTests.find((t) => t.ruleId === r.id);
            return [
              /* HTML */ `<button
                        class="row-action"
                        data-rule-focus="${escapeHtml(r.id)}"
                        aria-pressed="${r.id === focusedRule}"
                      >
                        ${escapeHtml(r.name)}
                      </button>
                      <p class="management-note">${escapeHtml(r.when)}</p>`,
              /* HTML */ `<span class="pill draft">${escapeHtml(ruleAreaOf(r))}</span>`,
              last
                ? /* HTML */ `${escapeHtml(localTime(last.at))}
                          <p class="management-note">Simulado · sem envio</p>`
                : "Não testada",
              /* HTML */ `<div class="management-inline-actions">
                      <button
                        class="management-switch"
                        data-rule-toggle="${escapeHtml(r.id)}"
                        role="switch"
                        aria-checked="${!!r.enabled}"
                        aria-label="${r.enabled ? "Pausar" : "Ativar"} ${escapeHtml(r.name)}"
                      ></button
                      ><span class="pill ${r.enabled ? "info" : "draft"}"
                        >${r.enabled ? "Ativa" : "Pausada"}</span
                      >
                    </div>`,
              /* HTML */ `<button
                      class="management-button sm"
                      data-rule-edit="${escapeHtml(r.id)}"
                    >
                      Editar
                    </button>`,
            ];
          }),
        )
      : emptyMarkup(
          "Nenhuma rotina nesta seleção",
          "Tente outro nome ou limpe os filtros.",
          '<button class="management-button" data-rule-clear>Limpar filtros</button>',
        );
  }
  function editRule(id) {
    editingRule = id || null;
    const r = rules.find((rule) => rule.id === id);
    q("#automationModalTitle").textContent = r ? "Editar rotina" : "Nova rotina";
    q("#ruleWhen").innerHTML = triggerOptions
      .map((x) => /* HTML */ `<option>${escapeHtml(x)}</option>`)
      .join("");
    q("#ruleThen").innerHTML = actionOptions
      .map((x) => /* HTML */ `<option>${escapeHtml(x)}</option>`)
      .join("");
    q("#ruleName").value = r?.name || "";
    q("#ruleWhen").value = r?.when || triggerOptions[0];
    q("#ruleThen").value = r?.then || actionOptions[0];
    q("#nvRuleAfter").value = r
      ? ruleAfter(r)
      : "Conferir vencimento e recebimento antes de cobrar";
    q("#nvRuleArea").value = r ? ruleAreaOf(r) : "Financeiro";
    q("#deleteRule").hidden = !r;
    updateRulePreview();
    openModal("automationModal");
    requestAnimationFrame(() => q("#ruleName").focus());
  }
  q("#automationDraftForm").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.target.reportValidity()) {
      return;
    }
    const name = q("#ruleName").value.trim();
    const after = q("#nvRuleAfter").value.trim();
    if (!name || !after) {
      return;
    }
    const i = rules.findIndex((rule) => rule.id === editingRule);
    const old = rules[i];
    const draft = {
      ...old,
      id: old?.id || "rule-" + SocialMEIClients.newId(),
      name,
      when: q("#ruleWhen").value,
      then: q("#ruleThen").value,
      after,
      area: q("#nvRuleArea").value,
      enabled: old?.enabled ?? false,
    };
    if (i < 0) {
      rules.push(draft);
    } else {
      rules[i] = draft;
    }
    focusedRule = draft.id;
    if (!saveRules()) {
      return;
    }
    renderRules();
    closeModal("automationModal");
    toast("Rotina salva", "Configuração local; nenhuma execução agendada.");
  });
  function updateRulePreview() {
    q("#ruleLivePreview").innerHTML = /* HTML */ `<h3>Confira o caminho</h3>
            <p class="management-drawer-note">
              Quando ${escapeHtml(q("#ruleWhen").value.toLowerCase())},
              ${escapeHtml(q("#ruleThen").value.toLowerCase())}. Depois:
              ${escapeHtml(q("#nvRuleAfter").value || "defina o próximo cuidado")}.
            </p>
            <p class="management-note">Salvar não agenda nem envia mensagens.</p>`;
  }
  q("#automationDraftForm").addEventListener("input", updateRulePreview);
  q("#automationDraftForm").addEventListener("change", updateRulePreview);
  function testRule(id) {
    const r = rules.find((rule) => rule.id === id);
    if (!r) {
      return;
    }
    let sale = null;
    let client = null;
    let conversation = null;
    let eligible = false;
    let evidence = "";
    const sorted = [...appData.vendas].sort((a, b) => b.data.localeCompare(a.data));
    if (r.when.includes("Pix")) {
      sale = sorted.find(
        (v) =>
          v.status === "Pendente" && v.pagamento === "Pix" && v.data <= dateShift(todayISO(), -2),
      );
      eligible = !!sale;
      sale ||= sorted.find((v) => v.pagamento === "Pix") || sorted[0];
      evidence = eligible
        ? "Pedido pendente de Pix há pelo menos 2 dias."
        : "O pedido de exemplo não confirma Pix pendente há 2 dias.";
    } else if (r.when.includes("conversa")) {
      conversation =
        businessViewConversations().find(
          (c) =>
            ["aberto", "andamento"].includes(c.status) &&
            [...c.mensagens].reverse().find((m) => m.de !== "nota")?.de === "cliente",
        ) || businessViewConversations()[0];
      evidence =
        "Sem data e hora completas do último evento, não é possível confirmar as 2 horas de espera.";
    } else if (r.when.includes("30 dias")) {
      client = appData.clientes.find((c) => {
        const last = sorted.find((v) => v.status === "Pago" && SocialMEISales.matchesClient(v, c));
        return last && last.data < dateShift(todayISO(), -30);
      });
      eligible = !!client;
      client ||= appData.clientes[0];
      evidence = eligible
        ? "Última venda paga registrada há mais de 30 dias."
        : "Sem histórico que confirme 30 dias sem comprar para este exemplo.";
    } else if (r.when.includes("concluída") || r.when.includes("nova compra")) {
      sale = sorted.find((v) => v.status === "Pago");
      eligible = !!sale;
      sale ||= sorted[0];
      evidence = eligible
        ? "Venda paga registrada. Não há execução automática ligada a esse evento."
        : "Sem venda paga que confirme o gatilho.";
    } else if (r.when.includes("vencimento")) {
      const due = appData.financeiro.find(
        (entry) =>
          entry.tipo === "receita" &&
          entry.status !== "pago" &&
          entry.vencimento === dateShift(todayISO(), 1),
      );
      eligible = !!due;
      evidence = due
        ? `Cobrança “${due.descricao}” vence ${formatDate(due.vencimento)}.`
        : "Sem cobrança a 1 dia do vencimento; apenas exemplo do conteúdo.";
      sale = sorted.find((v) => v.status === "Pendente") || sorted[0];
    } else {
      sale = sorted[0];
      evidence =
        "Prontidão e entrega não têm evento registrado nesta base. Este teste não confirma o gatilho.";
    }
    client ||= sale
      ? appData.clientes.find((c) => SocialMEISales.matchesClient(sale, c))
      : conversation
        ? clientContext(conversation).client
        : null;
    if (!sale && !client && !conversation) {
      openManagementDrawer(
        "Sem exemplo disponível",
        emptyMarkup(
          "Cadastre uma venda ou cliente",
          "Um teste precisa de um registro real para preparar o conteúdo.",
          '<button class="management-button" data-go="Vendas">Abrir vendas</button>',
        ),
      );
      return;
    }
    const name =
      client?.nome || sale?.cliente || (conversation ? displayName(conversation) : "Cliente");
    const amount = sale ? money(sale.valor) : null;
    const prepared =
      r.then === "Preparar lembrete de cobrança"
        ? `Olá, ${name.split(" ")[0]}. Podemos conferir o pagamento${sale ? ` do pedido #${sale.id} (${amount})` : ""}? Se já pagou, avise para eu verificar.`
        : r.then === "Preparar agradecimento"
          ? `Obrigado pela compra, ${name.split(" ")[0]}!${sale ? ` Seu pedido #${sale.id} está registrado.` : ""}`
          : r.then === "Preparar pedido de avaliação"
            ? `Olá, ${name.split(" ")[0]}. Depois de confirmar a entrega, podemos saber como foi sua experiência?`
            : r.then === "Preparar tarefa de entrega"
              ? `Conferir o item${sale?.item ? " " + sale.item : ""}${sale ? " do pedido #" + sale.id : ""} e combinar a entrega com ${name}.`
              : r.then === "Sinalizar atendimento pendente"
                ? `Revisar a conversa de ${name}: “${conversation ? lastMessage(conversation) : "conversa não vinculada"}”.`
                : `Olá, ${name.split(" ")[0]}. Podemos continuar de onde paramos?`;
    const text = `${evidence}\n\nO que seria preparado:\n${prepared}\n\nDepois: ${ruleAfter(r)}\nRascunho simulado · nenhuma ação enviada.`;
    const log = {
      ruleId: r.id,
      name: r.name,
      at: new Date().toISOString(),
      text,
      record: sale
        ? {
            type: "sales",
            id: sale.id,
          }
        : client
          ? {
              type: "clients",
              id: client.id,
            }
          : {
              type: "conversation",
              id: conversation.id,
            },
      triggerConfirmed: eligible,
    };
    ruleTests.unshift(log);
    ruleTests = ruleTests.slice(0, 100);
    socialmeiStorageSet(
      "socialmei-automation-tests-v1",
      JSON.stringify(ruleTests),
      "o histórico de testes",
    );
    renderRules();
    openManagementDrawer(
      "Teste simulado · " + r.name,
      /* HTML */ `${renderLocalDemoNotice()}<span class="pill ${eligible ? "info" : "draft"}"
                >${eligible ? "Gatilho compatível com os registros" : "Gatilho não confirmado"}</span
              >
              <p class="management-drawer-note">${escapeHtml(evidence)}</p>
              <div class="management-draft">
                <b>${escapeHtml(name)}${sale ? " · #" + sale.id : ""}</b>
                <p>${escapeHtml(prepared)}</p>
              </div>
              <p class="management-note">Depois: ${escapeHtml(ruleAfter(r))}</p>
              <button class="management-button" data-rule-history="${escapeHtml(r.id)}">
                Ver histórico de testes
              </button>`,
    );
  }
  function showRuleHistory(id) {
    const logs = ruleTests.filter((t) => !id || t.ruleId === id);
    openManagementDrawer(
      "Histórico de execuções",
      /* HTML */ `${renderLocalDemoNotice()}
              <h3>Execuções automáticas</h3>
              ${emptyMarkup("Nenhuma execução automática", "O serviço de rotinas ainda não está conectado.")}
              <h3>Testes manuais simulados</h3>
              ${
                logs.length
                  ? logs
                      .map(
                        (t) => /* HTML */ `<article class="management-draft">
                            <b>${escapeHtml(t.name)}</b>
                            <p class="management-note">${escapeHtml(localTime(t.at))} · simulado</p>
                            <p>${escapeHtml(t.text)}</p>
                          </article>`,
                      )
                      .join("")
                  : emptyMarkup(
                      "Nenhum teste feito",
                      "Use “Testar com um exemplo” para conferir o conteúdo sem enviar nada.",
                    )
              }`,
    );
  }
  q("#nvRuleSearch").addEventListener("input", renderRules);

  /* ASSISTENTE — JAVASCRIPT
  Estado visual do workspace; a geração de rascunhos continua local. */
  const assistantRoot = q("#aiToolsView");
  const assistantDesktopQuery = matchMedia("(min-width:1360px)");
  const assistantMobileQuery = matchMedia("(max-width:720px)");
  const assistantIconPaths = {
    spark: "M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2ZM20 3v4M18 5h4",
    chat: "M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2ZM7 9h10M7 13h6",
    search: "M21 21l-5.2-5.2M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
    reply: "M9 4 3 10l6 6M3 10h10a7 7 0 0 1 7 7v3",
    summary: "M5 6h14M5 12h14M5 18h9",
    sales: "M7 17 17 7M7 7h10v10",
    collect: "M5 5h14v16l-3-2-4 2-4-2-3 2V5ZM8 10h8M8 14h5",
    follow: "M4 10a8 8 0 1 1 1 8M4 4v6h6",
    check: "M5 12l4 4 10-10",
    close: "M6 6l12 12M6 18 18 6",
    back: "M20 12H4m6-6-6 6 6 6",
    arrow: "M4 12h16m-6-6 6 6-6 6",
    context: "M3 4h18v16H3V4Zm12 0v16M6 8h5M6 12h5",
    chevron: "m6 9 6 6 6-6",
    plus: "M12 5v14M5 12h14",
    copy: "M9 9h12v12H9V9ZM15 9V3H3v12h6",
    history: "M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v6l4 2",
    sliders: "M4 7h16M4 17h16M9 4v6M15 14v6",
  };
  function renderAssistantIcon(name) {
    return (
      '<svg class="assistant-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="' +
      (assistantIconPaths[name] || assistantIconPaths.spark) +
      '"></path></svg>'
    );
  }
  qa("[data-as-icon]", assistantRoot).forEach(
    (element) => (element.innerHTML = renderAssistantIcon(element.dataset.asIcon)),
  );
  if (/Mac|iPhone|iPad/.test(navigator.platform)) {
    q("#asShortcut").textContent = "⌘ ↵";
  }
  let activeAssistantDraftIndex = 0;
  let isAssistantHistoryExpanded = false;
  let isAssistantMainVisibleOnMobile = false;
  let isAssistantContextCollapsed = false;
  let hasAssistantArrived = false;
  let assistantSelectionRequest = 0;
  let isAssistantSelecting = false;
  let assistantCopyFeedbackTimer = 0;
  let isAssistantContextClosing = false;
  let assistantPreviousBodyOverflow = "";
  let assistantContextTrigger = null;
  const assistantContextDialog = q("#asContextDialog");
  const assistantContextPanel = q("#asContextRail");
  const assistantWorkspace = q("#asWorkbench");
  const assistantIntentLabels = {
    summary: "Resumir conversa",
    reply: "Responder dúvida",
    sales: "Propor venda/orçamento",
    collect: "Cobrar pendência",
    follow: "Retomar cliente",
  };
  const assistantIntentDescriptions = {
    summary: "Reúne a última mensagem e notas registradas.",
    reply: "Texto inicial para revisar; não confirma estoque ou prazo.",
    sales: "Roteiro de orçamento com os pedidos registrados.",
    collect: "Confere pendências antes de preparar uma cobrança.",
    follow: "Retoma o contexto sem agendar contatos.",
  };
  function getAssistantConversation() {
    return businessViewConversations().find(
      (conversation) => String(conversation.id) === q("#aiContextSelect").value,
    );
  }
  function isAssistantViewActive() {
    return (
      assistantRoot.classList.contains("active") &&
      document.body.classList.contains("experience-app")
    );
  }
  function syncAssistantTone() {
    const index = ["Curto", "Amigável", "Formal"].indexOf(assistantTone);
    q("#nvAiTones").style.setProperty("--tone-index", Math.max(0, index));
    qa("[data-ai-tone]", assistantRoot).forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.aiTone === assistantTone)),
    );
    q("#asConfigSummary").textContent =
      (assistantIntentLabels[assistantIntent] || "Configuração") + " · " + assistantTone;
  }
  function syncAssistantUi() {
    const conversation = getAssistantConversation();
    const hasDraft = assistantDrafts.length > 0;
    const hasContext = !!conversation && !isAssistantContextCollapsed;
    assistantRoot.classList.toggle("has-conversation", !!conversation);
    assistantRoot.classList.toggle("has-draft", hasDraft);
    assistantRoot.classList.toggle("context-hidden", !assistantDesktopQuery.matches || !hasContext);
    assistantRoot.classList.toggle(
      "mobile-canvas",
      isAssistantMainVisibleOnMobile && (!!conversation || hasDraft),
    );
    q("#asNoConversation").hidden = !!conversation || hasDraft;
    q("#asSelectedHead").hidden = !conversation && !hasDraft;
    q("#asMessageBlock").hidden = !conversation;
    q("#asConfiguration").hidden = !conversation;
    q("#aiReviewSection").hidden = !conversation && !hasDraft;
    qa("[data-ai-prepare]", assistantRoot).forEach(
      (b) => (b.disabled = !conversation || isAssistantSelecting),
    );
    if (conversation) {
      q("#asCanvasName").textContent = displayName(conversation);
      q("#asCanvasAvatar").textContent = getContactInitials(displayName(conversation));
      q("#asCanvasMeta").textContent =
        channelLabel(conversation.canal) + " · " + statusLabel(conversation.status);
      q("#asCanvasMessage").textContent = lastMessage(conversation);
    } else if (hasDraft) {
      q("#asCanvasName").textContent = assistantDrafts[0].name;
      q("#asCanvasAvatar").textContent = getContactInitials(assistantDrafts[0].name);
      q("#asCanvasMeta").textContent = "Conversa indisponível · somente revisão";
    }
    assistantContextPanel.hidden = assistantContextDialog.open
      ? false
      : !conversation || (assistantDesktopQuery.matches && isAssistantContextCollapsed);
    q("#asContextToggle").disabled = !conversation;
    q("#asContextToggle").setAttribute(
      "aria-expanded",
      String(assistantContextDialog.open || (assistantDesktopQuery.matches && hasContext)),
    );
    q("#asContextToggle").setAttribute(
      "aria-label",
      (assistantDesktopQuery.matches && hasContext ? "Recolher" : "Abrir") +
        " contexto da conversa",
    );
    if (!conversation && assistantContextDialog.open) {
      closeAssistantContext(true);
    }
    syncAssistantTone();
  }
  function renderAssistantConversations() {
    const query = normalizedText(q("#nvAiSearch").value);
    const selected = q("#aiContextSelect").value;
    const rows = businessViewConversations().filter((conversation) =>
      normalizedText(displayName(conversation) + " " + lastMessage(conversation)).includes(query),
    );
    q("#asConversationCount").textContent = businessViewConversations().length;
    q("#asSearchStatus").textContent = plural(
      rows.length,
      "conversa encontrada",
      "conversas encontradas",
    );
    q("#nvAiConversations").innerHTML = rows.length
      ? rows
          .map(
            (c) =>
              '<button type="button" class="assistant-conversation" data-ai-conversation="' +
              escapeHtml(String(c.id)) +
              '" aria-pressed="' +
              (String(c.id) === selected) +
              '"><span class="assistant-avatar" aria-hidden="true">' +
              escapeHtml(getContactInitials(displayName(c))) +
              '</span><span class="assistant-conversation-copy"><b>' +
              escapeHtml(displayName(c)) +
              '</b><small class="assistant-conversation-meta">' +
              escapeHtml(channelLabel(c.canal)) +
              '<i class="assistant-status-dot" aria-hidden="true"></i>' +
              escapeHtml(statusLabel(c.status)) +
              '</small><small class="assistant-preview">' +
              escapeHtml(lastMessage(c)) +
              "</small></span></button>",
          )
          .join("")
      : '<div class="assistant-list-empty"><p>Nenhuma conversa encontrada.</p><p>Tente outro nome ou mensagem.</p><button type="button" data-go="Caixa Unificada">Abrir Caixa Unificada →</button></div>';
  }
  function renderAssistantHistory() {
    q("#asHistoryCount").textContent = assistantHistory.length
      ? Math.min(assistantHistory.length, 10)
      : "";
    const items = assistantHistory.slice(0, isAssistantHistoryExpanded ? 10 : 5);
    q("#nvAiHistory").innerHTML = items.length
      ? items
          .map(
            (d, i) =>
              '<div class="assistant-history-item"><div><b>' +
              escapeHtml(d.name) +
              "</b><p>" +
              escapeHtml(d.intentLabel || assistantIntentLabels[d.intent] || "Rascunho") +
              " · " +
              escapeHtml(d.tone || "Curto") +
              '</p><time datetime="' +
              escapeHtml(d.at) +
              '">' +
              escapeHtml(localTime(d.at)) +
              '</time></div><button type="button" data-ai-history="' +
              i +
              '" aria-label="Abrir rascunho de ' +
              escapeHtml(d.name) +
              " em tom " +
              escapeHtml(d.tone || "Curto") +
              '">Abrir ' +
              renderAssistantIcon("arrow") +
              "</button></div>",
          )
          .join("") +
        (assistantHistory.length > 5
          ? '<button type="button" class="assistant-history-more" data-as-history-more>' +
            (isAssistantHistoryExpanded
              ? "Mostrar menos"
              : "Ver todos os " + assistantHistory.length) +
            " →</button>"
          : "")
      : '<p class="assistant-history-empty">Nenhum rascunho recente.</p>';
  }
  function getAssistantSources(c, intent = assistantIntent) {
    if (!c) {
      return [];
    }
    const ctx = clientContext(c);
    const sources = ["Última conversa"];
    if (intent === "summary") {
      if (ctx.client?.observacao) {
        sources.push("Nota do perfil");
      }
      if (c.mensagens.some((message) => message.de === "nota")) {
        sources.push("Nota interna");
      }
    }
    if (["sales", "collect", "follow"].includes(intent)) {
      ctx.purchases.forEach((sale) => sources.push("Pedido #" + sale.id));
    }
    return sources;
  }
  function renderAssistantSources(sources) {
    return (
      (Array.isArray(sources) ? sources : [])
        .map((s) => "<span>" + renderAssistantIcon("check") + escapeHtml(s) + "</span>")
        .join("") || "<span>Nenhuma fonte disponível</span>"
    );
  }
  function refreshAssistantContext() {
    const select = q("#aiContextSelect");
    const selected = select.value;
    select.innerHTML =
      '<option value="">Selecione uma conversa</option>' +
      businessViewConversations()
        .map(
          (c) =>
            '<option value="' +
            escapeHtml(String(c.id)) +
            '">' +
            escapeHtml(displayName(c)) +
            " · " +
            escapeHtml(channelLabel(c.canal)) +
            "</option>",
        )
        .join("");
    select.value = [...select.options].some((o) => o.value === selected) ? selected : "";
    const conversation = getAssistantConversation();
    const ctx = conversation ? clientContext(conversation) : null;
    q("#aiContextName").textContent = conversation ? displayName(conversation) : "Sem conversa";
    q("#aiContextMessage").textContent = conversation
      ? lastMessage(conversation)
      : "Escolha uma conversa para ver seu contexto.";
    q("#aiContextStatus").textContent = conversation
      ? statusLabel(conversation.status)
      : "Sem contexto";
    q("#aiContextCount").textContent = conversation
      ? plural(conversation.mensagens.length, "mensagem no histórico", "mensagens no histórico")
      : "";
    q("#asContextChannel").textContent = conversation ? channelLabel(conversation.canal) : "—";
    q("#aiCustomerContext").innerHTML = ctx?.client
      ? "<h4>Cliente</h4><p>" +
        escapeHtml(ctx.client.status) +
        " · " +
        plural(ctx.purchases.length, "venda vinculada", "vendas vinculadas") +
        "</p><p>" +
        escapeHtml(ctx.client.observacao || "Sem observação no perfil.") +
        "</p>" +
        (ctx.purchases.length
          ? "<div>" +
            ctx.purchases
              .slice(0, 4)
              .map(
                (sale) =>
                  '<button type="button" class="assistant-record-link" data-record-open="sales" data-record-id="' +
                  escapeHtml(String(sale.id)) +
                  '">#' +
                  escapeHtml(String(sale.id)) +
                  " · " +
                  escapeHtml(sale.status) +
                  " · " +
                  money(sale.valor) +
                  "</button>",
              )
              .join("") +
            "</div>"
          : "")
      : "<h4>Cliente</h4><p>Sem perfil de cliente vinculado. A conversa continua disponível.</p>";
    q("#nvAiSources").innerHTML = renderAssistantSources(getAssistantSources(conversation));
    renderAssistantConversations();
    renderAssistantHistory();
    syncAssistantUi();
  }
  function renderAssistantEmptyDraft() {
    q("#aiOutput").innerHTML =
      '<div class="assistant-draft-empty">' +
      renderAssistantIcon("spark") +
      "<div><b>Seu rascunho aparece aqui.</b><p>Escolha a intenção e prepare o próximo passo.</p></div></div>";
    q("#aiReviewContext").textContent = "Para revisar, antes de usar.";
    q("#asDraftHeading").textContent = "Rascunho";
    activeAssistantDraftIndex = 0;
    syncAssistantUi();
  }
  function selectAssistantIntent(intent) {
    if (!assistantIntentLabels[intent]) {
      return;
    }
    assistantIntent = intent;
    qa("[data-ai-intent]", assistantRoot).forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.aiIntent === intent)),
    );
    q("#aiTaskBrief").textContent = assistantIntentDescriptions[intent];
    assistantDrafts = [];
    q("#asConfiguration").open = true;
    renderAssistantEmptyDraft();
    refreshAssistantContext();
    const selected = q('[data-ai-intent="' + intent + '"]', assistantRoot);
    if (isAssistantViewActive()) {
      motion.animate(
        selected?.querySelector(".assistant-icon"),
        [
          {
            transform: "scale(.85)",
          },
          {
            transform: "scale(1)",
          },
        ],
        180,
      );
    }
  }
  function renderAssistantDrafts(options = {}) {
    if (!assistantDrafts.length) {
      renderAssistantEmptyDraft();
      return;
    }
    activeAssistantDraftIndex = Math.max(
      0,
      Math.min(activeAssistantDraftIndex, assistantDrafts.length - 1),
    );
    const d = assistantDrafts[activeAssistantDraftIndex];
    const tabs =
      assistantDrafts.length > 1
        ? '<div class="assistant-draft-tabs" role="tablist" aria-label="Alternativas de tom">' +
          assistantDrafts
            .map(
              (draft, i) =>
                '<button type="button" role="tab" id="asDraftTab' +
                i +
                '" aria-controls="asDraftPanel" data-ai-variant="' +
                i +
                '" aria-selected="' +
                (i === activeAssistantDraftIndex) +
                '" tabindex="' +
                (i === activeAssistantDraftIndex ? "0" : "-1") +
                '">' +
                escapeHtml(draft.tone) +
                "</button>",
            )
            .join("") +
          "</div>"
        : "";
    const actions =
      '<div class="assistant-draft-actions"><button type="button" data-ai-insert="' +
      activeAssistantDraftIndex +
      '" title="Insere no campo de mensagem. Não envia.">' +
      renderAssistantIcon("arrow") +
      'Usar na conversa</button><button type="button" data-ai-copy="' +
      activeAssistantDraftIndex +
      '">' +
      renderAssistantIcon("copy") +
      '<span>Copiar</span></button><button type="button" data-as-adjust-tone>' +
      renderAssistantIcon("sliders") +
      'Ajustar tom</button><button type="button" data-ai-prepare>' +
      renderAssistantIcon("follow") +
      "Refazer</button></div>";
    q("#aiOutput").innerHTML =
      tabs +
      '<article class="management-draft assistant-draft" id="asDraftPanel" ' +
      (assistantDrafts.length > 1
        ? 'role="tabpanel" aria-labelledby="asDraftTab' + activeAssistantDraftIndex + '"'
        : 'aria-label="Rascunho em tom ' + escapeHtml(d.tone) + '"') +
      '><p class="assistant-draft-text">' +
      escapeHtml(d.text) +
      "</p>" +
      (d.instruction
        ? '<p class="assistant-draft-instruction">Orientação para sua revisão: ' +
          escapeHtml(d.instruction) +
          "</p>"
        : "") +
      actions +
      '<div class="assistant-draft-sources"><p>Preparado usando</p><div class="assistant-source-items">' +
      renderAssistantSources(d.sources || []) +
      '</div></div><p class="assistant-insert-note">Insere na conversa como rascunho, sem enviar.</p></article>';
    q("#asDraftHeading").textContent = "Rascunho pronto";
    q("#aiReviewContext").textContent = (d.tone || "Curto") + " · preparação local";
    q("#nvAiSources").innerHTML = renderAssistantSources([
      ...new Set(assistantDrafts.flatMap((d) => d.sources || [])),
    ]);
    if (options.collapse !== false) {
      q("#asConfiguration").open = false;
    }
    isAssistantMainVisibleOnMobile = true;
    syncAssistantUi();
    if (isAssistantViewActive()) {
      if (options.type === "tone") {
        motion.animate(
          q(".assistant-draft-text", assistantRoot),
          [{ opacity: 0.6 }, { opacity: 1 }],
          180,
        );
      } else {
        motion.animate(
          q("#aiReviewSection"),
          [
            { opacity: 0, transform: "translateY(4px)" },
            { opacity: 1, transform: "none" },
          ],
          240,
        );
        q("#asAnnounce").textContent =
          "Rascunho pronto para revisar, em tom " + d.tone + ". Nenhuma mensagem enviada.";
      }
      if (options.focus !== false) {
        const heading = q("#asDraftHeading");
        heading.focus({
          preventScroll: true,
        });
        const box = heading.getBoundingClientRect();
        if (box.top < 80 || box.bottom > innerHeight) {
          heading.scrollIntoView({
            behavior: motion.reduced ? "instant" : "smooth",
            block: "center",
          });
        }
      }
    }
  }
  /**
   * Atualiza o workspace do Assistente e seu contexto. Não envia mensagens nem inicia uma chamada externa.
   * @param {number|string} id Identificador da conversa.
   * @returns {Promise<void>}
   */
  async function selectAssistantConversation(id) {
    if (
      !businessViewConversations().some((conversation) => String(conversation.id) === String(id))
    ) {
      return;
    }
    if (q("#aiContextSelect").value === String(id)) {
      isAssistantMainVisibleOnMobile = true;
      syncAssistantUi();
      if (assistantMobileQuery.matches) {
        q("#asCanvasName").focus({
          preventScroll: true,
        });
      }
      return;
    }
    const request = ++assistantSelectionRequest;
    const old = getAssistantConversation();
    const targets = [q("#asSelectedHead"), q("#asMessageBlock"), q("#asContextBody")];
    isAssistantSelecting = true;
    syncAssistantUi();
    if (old && isAssistantViewActive()) {
      targets.forEach((element) => element.getAnimations().forEach((a) => a.cancel()));
      await Promise.all(
        targets.map((element) =>
          motion.animate(
            element,
            [
              {
                opacity: 1,
                transform: "none",
              },
              {
                opacity: 0.3,
                transform: "translateY(-5px)",
              },
            ],
            80,
            "ease-exit",
          ),
        ),
      );
    }
    if (request !== assistantSelectionRequest) {
      return;
    }
    q("#aiContextSelect").value = String(id);
    isAssistantSelecting = false;
    activeAssistantDraftIndex = 0;
    isAssistantMainVisibleOnMobile = true;
    selectAssistantIntent(assistantIntent);
    targets.forEach((element) =>
      motion.animate(
        element,
        [
          {
            opacity: 0,
            filter: "blur(3px)",
            transform: "translateY(7px)",
          },
          {
            opacity: 1,
            filter: "blur(0)",
            transform: "none",
          },
        ],
        180,
      ),
    );
    q("#asAnnounce").textContent =
      "Conversa de " + displayName(getAssistantConversation()) + " selecionada.";
    const focus = assistantMobileQuery.matches
      ? q("#asCanvasName")
      : q('[data-ai-conversation="' + id + '"]', assistantRoot);
    focus?.focus({
      preventScroll: true,
    });
    if (assistantMobileQuery.matches) {
      assistantRoot.scrollIntoView({
        behavior: "instant",
        block: "start",
      });
    }
  }
  async function closeAssistantContext(immediate = false) {
    if (isAssistantContextClosing) {
      return;
    }
    isAssistantContextClosing = true;
    if (assistantContextDialog.open) {
      if (!immediate) {
        await motion.animate(
          assistantContextDialog,
          [
            {
              opacity: 1,
              transform: "none",
            },
            {
              opacity: 0,
              transform: assistantMobileQuery.matches ? "translateY(24px)" : "translateX(20px)",
            },
          ],
          160,
          "ease-exit",
        );
      }
      assistantContextDialog.close();
      assistantWorkspace.append(assistantContextPanel);
      document.body.style.overflow = assistantPreviousBodyOverflow;
      assistantContextTrigger?.focus({
        preventScroll: true,
      });
    } else if (assistantDesktopQuery.matches) {
      if (!immediate) {
        await motion.animate(
          assistantContextPanel,
          [
            {
              opacity: 1,
              transform: "none",
            },
            {
              opacity: 0,
              transform: "translateX(8px)",
            },
          ],
          160,
          "ease-exit",
        );
      }
      isAssistantContextCollapsed = true;
      q("#asContextToggle").focus({
        preventScroll: true,
      });
    }
    isAssistantContextClosing = false;
    syncAssistantUi();
  }
  function openAssistantContext(trigger) {
    if (!getAssistantConversation()) {
      return;
    }
    if (assistantDesktopQuery.matches) {
      if (!isAssistantContextCollapsed) {
        closeAssistantContext();
        return;
      }
      isAssistantContextCollapsed = false;
      syncAssistantUi();
      motion.animate(
        assistantContextPanel,
        [
          {
            opacity: 0,
            transform: "translateX(8px)",
          },
          {
            opacity: 1,
            transform: "none",
          },
        ],
        260,
      );
    } else {
      if (assistantContextDialog.open) {
        return;
      }
      assistantContextTrigger = trigger;
      assistantPreviousBodyOverflow = document.body.style.overflow;
      assistantContextDialog.append(assistantContextPanel);
      assistantContextPanel.hidden = false;
      assistantContextDialog.showModal();
      document.body.style.overflow = "hidden";
      syncAssistantUi();
      motion.animate(
        assistantContextDialog,
        [
          {
            opacity: 0,
            transform: assistantMobileQuery.matches ? "translateY(28px)" : "translateX(24px)",
          },
          {
            opacity: 1,
            transform: "none",
          },
        ],
        260,
      );
      q("[data-as-close-context]", assistantContextPanel).focus({
        preventScroll: true,
      });
    }
  }
  assistantContextDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeAssistantContext();
  });
  assistantContextDialog.addEventListener("click", (event) => {
    if (event.target !== assistantContextDialog) {
      return;
    }
    const box = assistantContextDialog.getBoundingClientRect();
    if (
      event.clientX < box.left ||
      event.clientX > box.right ||
      event.clientY < box.top ||
      event.clientY > box.bottom
    ) {
      closeAssistantContext();
    }
  });
  q("#asGuidance").addEventListener("toggle", () => {
    if (q("#asGuidance").open) {
      motion.animate(
        q(".assistant-guidance-inner", assistantRoot),
        [
          {
            opacity: 0,
            transform: "translateY(-4px)",
          },
          {
            opacity: 1,
            transform: "none",
          },
        ],
        220,
      );
    }
  });
  q("#asConfiguration").addEventListener("toggle", () => {
    if (q("#asConfiguration").open && assistantRoot.classList.contains("has-draft")) {
      motion.animate(
        q(".assistant-configuration-content", assistantRoot),
        [
          {
            opacity: 0,
            transform: "translateY(-4px)",
          },
          {
            opacity: 1,
            transform: "none",
          },
        ],
        220,
      );
    }
  });
  function showAssistantCopyFeedback(button) {
    clearTimeout(assistantCopyFeedbackTimer);
    const original = button.innerHTML;
    button.classList.add("is-copied");
    button.innerHTML = renderAssistantIcon("check") + "<span>Copiado</span>";
    q("#asAnnounce").textContent = "Rascunho copiado.";
    motion.animate(
      button.querySelector(".assistant-icon"),
      [
        {
          opacity: 0,
          transform: "scale(.8)",
        },
        {
          opacity: 1,
          transform: "none",
        },
      ],
      250,
    );
    assistantCopyFeedbackTimer = setTimeout(() => {
      button.classList.remove("is-copied");
      button.innerHTML = original;
      assistantCopyFeedbackTimer = 0;
    }, 1400);
  }
  function animateAssistantArrival() {
    if (!isAssistantViewActive()) {
      return;
    }
    if (hasAssistantArrived) {
      motion.animate(
        q("#asCanvas"),
        [
          {
            opacity: 0.8,
          },
          {
            opacity: 1,
          },
        ],
        150,
      );
      return;
    }
    hasAssistantArrived = true;
    motion.animate(
      q("#asPageTitle"),
      [
        {
          opacity: 0,
          filter: "blur(5px)",
          transform: "translateY(8px)",
        },
        {
          opacity: 1,
          filter: "blur(0)",
          transform: "none",
        },
      ],
      280,
      "ease-enter",
      80,
    );
    qa(".assistant-conversation", assistantRoot)
      .slice(0, 5)
      .forEach((element, i) =>
        motion.animate(
          element,
          [
            {
              opacity: 0,
              transform: "translateY(5px)",
            },
            {
              opacity: 1,
              transform: "none",
            },
          ],
          130,
          "ease-enter",
          130 + i * 35,
        ),
      );
    motion.animate(
      q("#asCanvas"),
      [
        {
          opacity: 0,
          transform: "translateY(7px)",
        },
        {
          opacity: 1,
          transform: "none",
        },
      ],
      200,
      "ease-enter",
      180,
    );
    if (!assistantContextPanel.hidden && assistantDesktopQuery.matches) {
      motion.animate(
        assistantContextPanel,
        [
          {
            opacity: 0,
            transform: "translateX(5px)",
          },
          {
            opacity: 1,
            transform: "none",
          },
        ],
        150,
        "ease-enter",
        230,
      );
    }
  }
  window.SocialMEIAssistantUI = {
    arrival: animateAssistantArrival,
  };
  function syncAssistantPage() {
    document.body.classList.toggle("assistant-active", isAssistantViewActive());
    if (isAssistantViewActive()) {
      q(".hd-title h1").textContent = getBusinessLabel() + " / Assistente";
      syncAssistantUi();
    } else {
      ++assistantSelectionRequest;
      isAssistantSelecting = false;
      if (assistantContextDialog.open) {
        closeAssistantContext(true);
      }
    }
  }
  const baseUpdateHeaderContext = updateHeaderContext;
  updateHeaderContext = function (...args) {
    baseUpdateHeaderContext(...args);
    document.body.classList.toggle("assistant-active", isAssistantViewActive());
    if (isAssistantViewActive()) {
      q(".hd-title h1").textContent = getBusinessLabel() + " / Assistente";
    }
  };
  document.addEventListener("socialmei-view-change", () => queueMicrotask(syncAssistantPage));
  assistantDesktopQuery.addEventListener("change", () => {
    if (assistantContextDialog.open) {
      closeAssistantContext(true);
    }
    syncAssistantUi();
  });
  assistantMobileQuery.addEventListener("change", () => {
    if (assistantMobileQuery.matches && getAssistantConversation()) {
      isAssistantMainVisibleOnMobile = true;
    }
    syncAssistantUi();
  });
  window.addEventListener("pagehide", () => {
    clearTimeout(assistantCopyFeedbackTimer);
    if (assistantContextDialog.open) {
      closeAssistantContext(true);
    }
  });
  assistantRoot.addEventListener("click", (event) => {
    const b = event.target.closest("button");
    if (!b) {
      return;
    }
    if (b.hasAttribute("data-as-back")) {
      isAssistantMainVisibleOnMobile = false;
      syncAssistantUi();
      q("#nvAiSearch").focus({
        preventScroll: true,
      });
      assistantRoot.scrollIntoView({
        behavior: "instant",
        block: "start",
      });
    }
    if (b.hasAttribute("data-as-context")) {
      openAssistantContext(b);
    }
    if (b.hasAttribute("data-as-close-context")) {
      closeAssistantContext();
    }
    if (b.hasAttribute("data-as-history-more")) {
      isAssistantHistoryExpanded = !isAssistantHistoryExpanded;
      renderAssistantHistory();
      q("[data-as-history-more]", assistantRoot)?.focus({
        preventScroll: true,
      });
    }
    if (b.hasAttribute("data-as-adjust-tone")) {
      q("#asConfiguration").open = true;
      const focus =
        assistantDrafts.length > 1
          ? q('[data-ai-variant="' + activeAssistantDraftIndex + '"]', assistantRoot)
          : q('[data-ai-tone="' + assistantTone + '"]', assistantRoot);
      focus?.focus({
        preventScroll: true,
      });
      if (focus) {
        focus.scrollIntoView({
          behavior: motion.reduced ? "instant" : "smooth",
          block: "nearest",
        });
      }
    }
    if (b.hasAttribute("data-ai-variant")) {
      activeAssistantDraftIndex = Number(b.dataset.aiVariant);
      assistantTone = assistantDrafts[activeAssistantDraftIndex]?.tone || assistantTone;
      syncAssistantTone();
      renderAssistantDrafts({
        type: "tone",
        collapse: false,
        focus: false,
      });
      q('[data-ai-variant="' + activeAssistantDraftIndex + '"]', assistantRoot)?.focus({
        preventScroll: true,
      });
    }
  });
  assistantRoot.addEventListener("keydown", (event) => {
    if (
      (event.ctrlKey || event.metaKey) &&
      event.key === "Enter" &&
      !event.isComposing &&
      !event.repeat
    ) {
      event.preventDefault();
      if (getAssistantConversation() && !isAssistantSelecting) {
        activeAssistantDraftIndex = 0;
        prepareAssistantDraft();
      }
    }
    const tab = event.target.closest("[data-ai-variant]");
    if (!tab || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    const tabs = qa("[data-ai-variant]", assistantRoot);
    const index = tabs.indexOf(tab);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].click();
  });
  function buildAssistantDraftText(
    { conversation, context, name, first, pending, last, note },
    tone,
    intent,
  ) {
    const hello =
      tone === "Formal"
        ? `Olá, ${name}.`
        : tone === "Amigável"
          ? `Oi, ${first}! Tudo bem?`
          : `Olá, ${first}.`;
    let text = "";
    if (intent === "summary") {
      text = `${name} · ${channelLabel(conversation.canal)} · ${statusLabel(conversation.status)}\nÚltima mensagem: “${last}”${context.client?.observacao ? "\nNota do perfil: " + context.client.observacao : ""}${note ? "\nNota interna: " + (note.texto || note.text || "Nota sem texto") : ""}`;
      text +=
        "\n" +
        (tone === "Curto"
          ? "Próximo passo: conferir a dúvida e responder."
          : tone === "Amigável"
            ? "Vale ler a conversa completa com calma antes de preparar o próximo contato."
            : "Recomendação: revisar o histórico integral e verificar os dados antes de tomar qualquer ação.");
    } else if (intent === "reply") {
      text =
        hello +
        " " +
        (tone === "Curto"
          ? "Recebi sua mensagem. Vou conferir os detalhes e retorno por aqui."
          : tone === "Amigável"
            ? "Obrigado por conversar com a gente. Vou olhar sua dúvida com cuidado e te retorno por aqui."
            : "Agradeço o contato. Vou verificar as informações da sua solicitação antes de retornar.");
    } else if (intent === "sales") {
      text =
        hello +
        " " +
        (pending.length
          ? `Podemos revisar seu pedido #${pending[0].id} (${money(pending[0].valor)}) antes de preparar um novo orçamento?`
          : tone === "Curto"
            ? "Qual produto ou serviço você procura? Posso preparar um orçamento para revisar com você."
            : tone === "Amigável"
              ? "Me conta qual produto ou serviço você precisa? Assim preparo um orçamento com os detalhes para você conferir."
              : "Para preparar uma proposta, poderia informar o produto ou serviço e a quantidade desejados?");
    } else if (intent === "collect") {
      text = pending.length
        ? hello +
          " " +
          (tone === "Curto"
            ? `Podemos conferir o pagamento do pedido #${pending[0].id}, de ${money(pending[0].valor)}?`
            : tone === "Amigável"
              ? `Queria conferir com você o pagamento do pedido #${pending[0].id}, de ${money(pending[0].valor)}. Se já pagou, me avise para eu verificar.`
              : `O pedido #${pending[0].id}, no valor de ${money(pending[0].valor)}, consta como pendente nos registros. Poderia confirmar o pagamento para conferência?`)
        : "Não há pedido pendente vinculado a esta pessoa. Confira os registros antes de preparar uma cobrança.";
    } else {
      text =
        hello +
        " " +
        (tone === "Curto"
          ? "Podemos continuar nossa conversa?"
          : tone === "Amigável"
            ? "Passando para saber se ainda posso ajudar com o que conversamos. Quer continuar por aqui?"
            : "Gostaria de saber se deseja dar continuidade à nossa conversa. Fico à disposição para revisar sua solicitação.");
    }
    return text;
  }

  // Gera rascunhos locais; inserir na Caixa ainda depende da revisão do usuário.
  function prepareAssistantDraft() {
    const conversation = getAssistantConversation();
    if (!conversation) {
      q("#aiOutput").innerHTML = emptyMarkup(
        "Escolha uma conversa",
        "Abra a Caixa Unificada para começar.",
        '<button class="management-button" data-go="Caixa Unificada">Abrir caixa</button>',
      );
      return;
    }
    const ctx = clientContext(conversation);
    const name = displayName(conversation);
    const first = name.split(" ")[0];
    const sales = ctx.purchases;
    const pending = sales.filter((sale) => sale.status === "Pendente");
    const last = lastMessage(conversation);
    const note = [...conversation.mensagens].reverse().find((m) => m.de === "nota");
    const instruction = q("#aiPromptInput").value.trim();
    const tones = [
      assistantTone,
      ...["Curto", "Amigável", "Formal"].filter((t) => t !== assistantTone),
    ];
    const draftContext = { conversation, context: ctx, name, first, pending, last, note };
    assistantDrafts = tones.map((tone) => {
      const text = buildAssistantDraftText(draftContext, tone, assistantIntent);
      return {
        text,
        tone,
        name,
        conversationId: conversation.id,
        intent: assistantIntent,
        intentLabel: assistantIntentLabels[assistantIntent],
        at: new Date().toISOString(),
        sources: getAssistantSources(conversation),
        instruction,
      };
    });
    assistantHistory = [...assistantDrafts, ...assistantHistory].slice(0, 10);
    socialmeiStorageSet(
      "socialmei-ai-drafts-v1",
      JSON.stringify(assistantHistory),
      "os rascunhos recentes",
    );
    renderAssistantDrafts();
    renderAssistantHistory();
  }
  q("#nvAiSearch").addEventListener("input", renderAssistantConversations);
  q("#aiContextSelect").addEventListener("change", () => {
    isAssistantMainVisibleOnMobile = !!getAssistantConversation();
    refreshAssistantContext();
    selectAssistantIntent(assistantIntent);
  });
  q("#aiPromptInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.isComposing && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      activeAssistantDraftIndex = 0;
      prepareAssistantDraft();
    }
  });
  window.SocialMEIExperience.openAssistant = function (id) {
    ++assistantSelectionRequest;
    isAssistantSelecting = false;
    setView("Assistente");
    if (
      businessViewConversations().some((conversation) => String(conversation.id) === String(id))
    ) {
      q("#aiContextSelect").value = String(id);
    }
    isAssistantMainVisibleOnMobile = true;
    selectAssistantIntent("summary");
    q("#asGuidance").open = true;
    q("#asConfiguration").open = true;
    q("#aiPromptInput").focus();
  };
  window.SocialMEIExperience.refreshTools = function () {
    if (currentView === "Automações") {
      renderRules();
      revealRuleFlow("enter");
    }
    if (currentView === "Assistente") {
      refreshAssistantContext();
    }
  };
  document.addEventListener("socialmei-data-change", () => {
    if (currentView === "Assistente") {
      refreshAssistantContext();
    }
  });
  document.addEventListener("click", async (event) => {
    const b = event.target.closest("button");
    if (!b) {
      return;
    }
    if (b.hasAttribute("data-rule-create")) {
      editRule();
      return;
    }
    if (b.dataset.ruleEdit) {
      editRule(b.dataset.ruleEdit);
      return;
    }
    if (b.dataset.ruleToggle) {
      const r = rules.find((rule) => rule.id === b.dataset.ruleToggle);
      if (r) {
        r.enabled = !r.enabled;
        saveRules();
        renderRules();
        q(`[data-rule-toggle="${r.id}"]`)?.focus();
      }
      return;
    }
    if (b.hasAttribute("data-rule-delete") && editingRule) {
      rules = rules.filter((rule) => rule.id !== editingRule);
      if (!saveRules()) {
        renderRules();
        return;
      }
      renderRules();
      closeModal("automationModal");
      toast("Rotina excluída");
      return;
    }
    if (b.dataset.ruleFocus) {
      const changed = focusedRule !== b.dataset.ruleFocus;
      focusedRule = b.dataset.ruleFocus;
      renderRules();
      if (changed) {
        revealRuleFlow("switch");
      }
      q(`[data-rule-focus="${focusedRule}"]`)?.focus();
      return;
    }
    if (b.dataset.ruleFilter) {
      ruleFilter = b.dataset.ruleFilter;
      renderRules();
      q(`[data-rule-filter="${ruleFilter}"]`)?.focus();
      return;
    }
    if (b.dataset.ruleArea) {
      ruleArea = b.dataset.ruleArea;
      renderRules();
      q(`[data-rule-area="${ruleArea}"]`)?.focus();
      return;
    }
    if (b.hasAttribute("data-rule-clear")) {
      ruleFilter = "all";
      ruleArea = "Todas";
      q("#nvRuleSearch").value = "";
      renderRules();
      q("#nvRuleSearch").focus();
      return;
    }
    if (b.hasAttribute("data-rule-model")) {
      const model = ruleModels[Number(b.dataset.ruleModel)];
      const r = {
        ...model,
        id: "rule-" + SocialMEIClients.newId(),
        enabled: false,
      };
      rules.push(r);
      focusedRule = r.id;
      if (!saveRules()) {
        renderRules();
        return;
      }
      renderRules();
      editRule(r.id);
      return;
    }
    if (b.dataset.ruleTest) {
      testRule(b.dataset.ruleTest);
      return;
    }
    if (b.hasAttribute("data-rule-history")) {
      showRuleHistory(b.dataset.ruleHistory);
      return;
    }
    if (b.hasAttribute("data-ai-intent")) {
      selectAssistantIntent(b.dataset.aiIntent);
      return;
    }
    if (b.hasAttribute("data-ai-prepare")) {
      activeAssistantDraftIndex = 0;
      prepareAssistantDraft();
      return;
    }
    if (b.dataset.aiTone) {
      assistantTone = b.dataset.aiTone;
      syncAssistantTone();
      const variant = assistantDrafts.findIndex((d) => d.tone === assistantTone);
      if (variant >= 0) {
        activeAssistantDraftIndex = variant;
        renderAssistantDrafts({
          type: "tone",
          collapse: false,
          focus: false,
        });
      }
      return;
    }
    if (b.dataset.aiConversation) {
      await selectAssistantConversation(b.dataset.aiConversation);
      return;
    }
    if (b.hasAttribute("data-ai-copy")) {
      const d = assistantDrafts[Number(b.dataset.aiCopy)];
      if (d) {
        const copied = await copyTextToClipboard(d.text);
        if (copied && assistantRoot.contains(b)) {
          showAssistantCopyFeedback(b);
        }
      }
      return;
    }
    if (b.hasAttribute("data-ai-history")) {
      const d = assistantHistory[Number(b.dataset.aiHistory)];
      if (!d) {
        return;
      }
      q("#aiContextSelect").value = businessViewConversations().some(
        (conversation) => String(conversation.id) === String(d.conversationId),
      )
        ? String(d.conversationId)
        : "";
      selectAssistantIntent(assistantIntentLabels[d.intent] ? d.intent : assistantIntent);
      if (["Curto", "Amigável", "Formal"].includes(d.tone)) {
        assistantTone = d.tone;
      }
      assistantDrafts = [d];
      activeAssistantDraftIndex = 0;
      isAssistantMainVisibleOnMobile = true;
      refreshAssistantContext();
      renderAssistantDrafts();
      return;
    }
    if (b.hasAttribute("data-ai-insert")) {
      const d = assistantDrafts[Number(b.dataset.aiInsert)];
      if (
        !d ||
        !businessViewConversations().some((conversation) => conversation.id === d.conversationId)
      ) {
        toast("Conversa não disponível", "O rascunho continua disponível para copiar.");
        return;
      }
      setView("Caixa Unificada");
      const old = conversationDrafts.get(d.conversationId)?.text || "";
      conversationDrafts.set(d.conversationId, {
        text: old && old !== d.text ? old + "\n\n" + d.text : d.text,
        note: false,
      });
      await selectConversation(d.conversationId);
      if (currentView === "Caixa Unificada" && activeConversationId === d.conversationId) {
        loadCurrentDraft();
        saveCurrentDraft();
        q("#messageInput").focus();
        toast("Rascunho inserido", "Revise antes de enviar. Nenhuma mensagem foi enviada.");
      }
      return;
    }
  });
  q("#nvRuleModelsDisclosure").open = false;
  renderRules();
  refreshAssistantContext();
  selectAssistantIntent("summary");
  syncAssistantPage();
  if (isAssistantViewActive()) {
    animateAssistantArrival();
  }

  /* HOME — JAVASCRIPT
  Prioridades, sugestões de comandos e visão contextual do dia. */
  window.renderClientHome = function () {
    q("#clientHomeGreeting").textContent = humanGreeting();
    const unread = conversationCounts().unreadMessages;
    const overdue = businessViewData().financeiro.filter(
      (entry) => ledgerStatus(entry) === "atrasado",
    ).length;
    const balance = operationalMetrics({
      from: "0000-01-01",
      to: todayISO(),
    }).balance;
    const context = q("#homeContext");
    const ledger = businessViewData().financeiro.filter((entry) => !entry.excluida);
    const pendingLedger = ledger.filter((entry) => entry.status !== "pago");
    const hasBusinessRecords =
      businessViewData().clientes.length ||
      businessViewData().produtos.length ||
      businessViewData().vendas.length ||
      ledger.length;
    context.textContent = unread
      ? `${plural(unread, "mensagem espera", "mensagens esperam")} por você →`
      : overdue
        ? `${plural(overdue, "compromisso pede", "compromissos pedem")} atenção →`
        : hasBusinessRecords
          ? "Veja o que acontece no seu negócio →"
          : "Comece pelo seu primeiro cliente →";
    context.dataset.homeGo = unread
      ? "Caixa Unificada"
      : overdue
        ? "Financeiro"
        : hasBusinessRecords
          ? "Visão Geral"
          : "Clientes";
    q("#homePulseConversations").textContent = unread
      ? `${plural(unread, "mensagem não lida", "mensagens não lidas")}`
      : businessViewConversations().length
        ? "Sem mensagens não lidas"
        : "Nenhum atendimento ainda";
    q("#homePulseFinance").textContent = ledger.length ? money(balance) : "Ainda sem lançamentos";
    q("#homePulsePending").textContent = overdue
      ? `${plural(overdue, "atrasado", "atrasados")}`
      : pendingLedger.length
        ? plural(pendingLedger.length, "compromisso previsto", "compromissos previstos")
        : ledger.length
          ? "Sem compromissos pendentes"
          : "Nenhum compromisso cadastrado";
    q("#homeActionInbox").textContent = unread || "→";
    q("#homeActionFinance").textContent = overdue
      ? `${overdue} contas atrasadas`
      : "Ver compromissos";
    q("#homeActionRules").textContent = rules.length;
    const c =
      businessViewConversations().find((conversation) => conversation.naoLidas) ||
      businessViewConversations()[0];
    q("#homeNow").innerHTML = c
      ? /* HTML */ `<div class="desk-conversation-person">
                  <span class="av">${escapeHtml(initialsFromName(displayName(c)))}</span>
                  <div>
                    <span class="chapter-label">Uma conversa para continuar</span
                    ><b>${escapeHtml(displayName(c))}</b
                    ><small>${channelLabel(c.canal)} · ${statusLabel(c.status)}</small>
                  </div>
                </div>
                <blockquote>“${escapeHtml(lastMessage(c))}”</blockquote>
                <button class="btn" data-home-conversation="${c.id}">${SocialMEIDemoData.enabled() ? "Ver análise de exemplo →" : "Continuar conversa →"}</button>`
      : /* HTML */ `
          <span class="chapter-label">UM NOVO COMEÇO</span>
          <h3>O próximo capítulo começa com seus clientes.</h3>
          <p class="home-empty-note">Cadastre seus contatos e reúna o contexto de cada relacionamento.</p>
          <button class="btn" data-home-go="Clientes">Ver clientes →</button>
        `;
    renderHomeOperations();
    SocialMEIPersonalization.renderHome();
    q("#homeLiveIcon").innerHTML = renderIcon(homeIcons?.[iconCycle] || "inbox");
    nextHomeIcon();
  };

  function renderHomeOperations() {
    const routes = {
      overdue: "Financeiro",
      reply: SocialMEIDemoData.enabled() ? "Oportunidades" : "Caixa Unificada",
      stock: "Produtos e Serviços",
      today: "Financeiro",
    };
    const priorities = priorityItems();
    q("#homeAttentionList").innerHTML = priorities.length
      ? priorities
          .map(
            (item) => /* HTML */ `<li>
                <button class="home-priority-row" type="button" data-home-go="${routes[item.kind]}">
                  <span class="home-priority-dot ${item.tone}" aria-hidden="true"></span>
                  <span><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.desc)}</small></span>
                  <span class="home-row-arrow" aria-hidden="true">→</span>
                </button>
              </li>`,
          )
          .join("")
      : /* HTML */ `<li class="home-list-empty">
          <b>Nenhuma prioridade pendente</b>
          <p>Atrasos, respostas e estoque baixo aparecem aqui quando houver registros.</p>
        </li>`;
    const recent = businessViewData()
      .vendas.filter((sale) => !sale.excluida)
      .toSorted((first, second) => second.data.localeCompare(first.data))
      .slice(0, 3);
    q("#homeRecentSales").innerHTML = recent.length
      ? recent
          .map(
            (sale) => /* HTML */ `<li>
                <button class="home-sale-row" type="button" data-home-go="Vendas">
                  <span>
                    <b>${escapeHtml(sale.cliente)}</b>
                    <small>#${escapeHtml(String(sale.id))} · ${formatDate(sale.data)} · ${escapeHtml(sale.status)}</small>
                  </span>
                  <strong>${money(sale.valor)}</strong>
                </button>
              </li>`,
          )
          .join("")
      : /* HTML */ `<li class="home-list-empty">
          <b>Sua primeira venda aparece aqui</b>
          <p>Registre uma venda para acompanhar os pedidos mais recentes.</p>
          <button class="lk" type="button" data-home-go="Vendas">Abrir vendas →</button>
        </li>`;
  }
  document.addEventListener("click", (event) => {
    const go = event.target.closest("[data-home-go]");
    if (go && typeof window.setView === "function") {
      window.setView(go.dataset.homeGo);
      if (go.dataset.homeCreate) {
        openCreate(go.dataset.homeCreate);
      }
      return;
    }
    const send = event.target.closest("#clientCommandSend");
    if (send) {
      runHomeCommand();
      return;
    }
  });
  document.addEventListener("click", (event) => {
    const b = event.target.closest("[data-home-conversation]");
    if (b) {
      setView("Caixa Unificada");
      selectConversation(Number(b.dataset.homeConversation));
    }
  });
  const commandInput = q("#clientCommandInput");
  const suggestions = q("#homeSuggestions");
  const homeIcons = ["inbox", "bag", "users", "wallet", "bolt"];
  let iconCycle = 0;
  let homeIconTimer = null;
  function nextHomeIcon() {
    const visible =
      !document.hidden &&
      !motion.reduced &&
      currentView === "Início" &&
      document.body.classList.contains("experience-app");
    if (!visible) {
      clearTimeout(homeIconTimer);
      homeIconTimer = null;
      return;
    }
    if (homeIconTimer) {
      return;
    }
    homeIconTimer = setTimeout(async () => {
      homeIconTimer = null;
      if (document.hidden || motion.reduced || currentView !== "Início") {
        return;
      }
      const element = q("#homeLiveIcon");
      if (!element) {
        return;
      }
      await motion.animate(
        element,
        [
          {
            opacity: 1,
            transform: "translate3d(0,0,0) scale(1)",
            filter: "blur(0)",
          },
          {
            opacity: 0,
            transform: "translate3d(0,-2px,0) scale(.94)",
            filter: "blur(2px)",
          },
        ],
        135,
        "ease-exit",
      );
      if (document.hidden || motion.reduced || currentView !== "Início") {
        return;
      }
      iconCycle = (iconCycle + 1) % homeIcons.length;
      element.innerHTML = renderIcon(homeIcons[iconCycle]);
      await motion.animate(
        element,
        [
          {
            opacity: 0,
            transform: "translate3d(0,3px,0) scale(.95)",
            filter: "blur(2px)",
          },
          {
            opacity: 1,
            transform: "translate3d(0,0,0) scale(1)",
            filter: "blur(0)",
          },
        ],
        220,
        "ease-enter",
      );
      nextHomeIcon();
    }, 4700);
  }
  document.addEventListener("socialmei-motion-change", nextHomeIcon);
  document.addEventListener("socialmei-view-change", () => {
    if (currentView !== "Início") {
      closeSuggestions();
    }
    nextHomeIcon();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && currentView === "Início") {
      renderClientHome();
    }
    nextHomeIcon();
  });
  window.addEventListener("pagehide", () => clearTimeout(homeIconTimer));
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      nextHomeIcon();
    }
  });
  const homeOptions = [
    {
      label: "Responder clientes",
      view: "Caixa Unificada",
      icon: "inbox",
      hint: () => `${conversationCounts().unreadMessages} mensagens não lidas`,
    },
    {
      label: "Registrar venda",
      view: "Vendas",
      create: "venda",
      icon: "bag",
      hint: () => "Criar um novo pedido",
    },
    {
      label: "Ver financeiro",
      keywords: "cobranças pagamentos recebimentos",
      view: "Financeiro",
      icon: "wallet",
      hint: () =>
        `${businessViewData().financeiro.filter((entry) => ledgerStatus(entry) === "atrasado").length} em atraso`,
    },
    {
      label: "Adicionar cliente",
      view: "Clientes",
      create: "cliente",
      icon: "users",
      hint: () => "Salvar um novo relacionamento",
    },
    {
      label: "Abrir Caixa Unificada",
      view: "Caixa Unificada",
      icon: "inbox",
      hint: () => "Continuar atendimentos",
    },
    {
      label: "Produtos e estoque",
      view: "Produtos e Serviços",
      icon: "box",
      hint: () => "Conferir catálogo e reposição",
    },
    {
      label: "Preparar rotina",
      keywords: "automações automacao automatizar",
      view: "Automações",
      icon: "bolt",
      hint: () => `${rules.length} rotinas salvas`,
    },
  ];
  let filteredOptions = [];
  let activeOption = -1;
  function closeSuggestions() {
    suggestions.hidden = true;
    commandInput.setAttribute("aria-expanded", "false");
    commandInput.removeAttribute("aria-activedescendant");
    activeOption = -1;
  }
  function renderSuggestions() {
    const query = foldText(commandInput.value.trim());
    filteredOptions = homeOptions.filter(
      (o) =>
        foldText(o.label + " " + o.view + " " + (o.keywords || "")).includes(query) ||
        (typeof o.hint === "function" && foldText(o.hint()).includes(query)),
    );
    activeOption = filteredOptions.length ? 0 : -1;
    suggestions.replaceChildren();
    filteredOptions.forEach((o, i) => {
      const li = document.createElement("li");
      li.id = "homeOption-" + i;
      li.setAttribute("role", "option");
      li.dataset.homeOption = i;
      li.style.setProperty("--suggestion-index", i);
      const hint = typeof o.hint === "function" ? o.hint() : "";
      li.innerHTML = /* HTML */ `<span class="suggestion-icon"
                >${renderIcon(o.icon || "search")}</span
              ><span class="suggestion-copy"
                ><b>${escapeHtml(o.label)}</b><small>${escapeHtml(hint)}</small></span
              ><span class="suggestion-enter" aria-hidden="true">↵</span>`;
      suggestions.appendChild(li);
    });
    if (!filteredOptions.length) {
      const li = document.createElement("li");
      li.className = "suggestion-empty";
      li.innerHTML = /* HTML */ `<span class="suggestion-icon">${renderIcon("search")}</span
              ><span class="suggestion-copy"
                ><b>Nenhuma ação encontrada</b
                ><small>Tente “venda”, “cliente”, “mensagens” ou “cobranças”.</small></span
              >`;
      suggestions.appendChild(li);
    }
    suggestions.hidden = false;
    commandInput.setAttribute("aria-expanded", "true");
    selectSuggestion();
  }
  function selectSuggestion() {
    [...suggestions.querySelectorAll('[role="option"]')].forEach((element, i) =>
      element.setAttribute("aria-selected", String(i === activeOption)),
    );
    if (activeOption >= 0) {
      commandInput.setAttribute("aria-activedescendant", "homeOption-" + activeOption);
      suggestions.querySelector(`#homeOption-${activeOption}`)?.scrollIntoView({
        block: "nearest",
      });
    } else {
      commandInput.removeAttribute("aria-activedescendant");
    }
  }
  function runHomeCommand(index = activeOption) {
    const option = filteredOptions[index];
    if (!option) {
      renderSuggestions();
      return;
    }
    closeSuggestions();
    commandInput.value = "";
    setView(option.view);
    if (option.create) {
      openCreate(option.create);
    } else {
      const title = document.querySelector(".page-view.active h2");
      if (title) {
        title.tabIndex = -1;
        title.focus({
          preventScroll: true,
        });
      }
    }
  }
  q("#clientCommandIcon").innerHTML = renderIcon("search");
  q(".client-command").addEventListener("focusout", (event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      closeSuggestions();
    }
  });
  commandInput.addEventListener("focus", renderSuggestions);
  commandInput.addEventListener("input", renderSuggestions);
  commandInput.addEventListener("keydown", (event) => {
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      if (suggestions.hidden) {
        renderSuggestions();
      }
      activeOption = filteredOptions.length
        ? (activeOption + (event.key === "ArrowDown" ? 1 : -1) + filteredOptions.length) %
          filteredOptions.length
        : -1;
      selectSuggestion();
    }
    if (event.key === "Enter" && !event.isComposing) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (suggestions.hidden) {
        renderSuggestions();
      }
      runHomeCommand();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
      closeSuggestions();
    }
    if (event.key === "Tab") {
      closeSuggestions();
    }
  });
  suggestions.addEventListener("pointerdown", (event) => event.preventDefault());
  suggestions.addEventListener("click", (event) => {
    const item = event.target.closest("[data-home-option]");
    if (item) {
      runHomeCommand(Number(item.dataset.homeOption));
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".client-command-wrap")) {
      closeSuggestions();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (
      !event.defaultPrevented &&
      !activeModalDialog() &&
      event.key === "/" &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey &&
      !event.target.closest("input,textarea,select,[contenteditable]") &&
      document.body.classList.contains("experience-app")
    ) {
      event.preventDefault();
      setView("Início");
      commandInput.focus();
    }
  });
  document.addEventListener("socialmei-data-change", () => {
    if (currentView === "Início") {
      renderClientHome();
    }
  });

  /* Tema da experiência pública, independente do tema do app. */
  const PUBLIC_THEME_KEY = "socialmei_public_theme";
  const publicThemeBtn = () => document.getElementById("xpThemeToggle");
  function applyPublicTheme(theme) {
    const effective = theme === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-public-theme", effective);
    try {
      socialmeiStorageSet(PUBLIC_THEME_KEY, effective, "o tema da apresentação");
    } catch (_) {}
    qa("#xpThemeToggle,[data-public-theme-toggle]").forEach((button) => {
      button.setAttribute("aria-pressed", String(effective === "dark"));
      button.setAttribute(
        "aria-label",
        effective === "dark" ? "Ativar tema claro" : "Ativar tema escuro",
      );
      const label = button.querySelector(".landing-theme-label");
      if (label) {
        label.textContent = effective === "dark" ? "Tema claro" : "Tema escuro";
      }
      button.title = effective === "dark" ? "Ativar tema claro" : "Ativar tema escuro";
    });
    if (!document.body.classList.contains("experience-app") && window.SocialMEIThemes) {
      SocialMEIThemes.applyTokens(document.documentElement, SocialMEIThemes.official[effective]);
      document.documentElement.dataset.theme = effective;
    }
  }
  function initPublicTheme() {
    let stored = "light";
    try {
      stored = localStorage.getItem(PUBLIC_THEME_KEY) || "light";
    } catch (_) {}
    applyPublicTheme(stored);
  }
  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("#xpThemeToggle,[data-public-theme-toggle]");
    if (!toggle) {
      return;
    }
    event.preventDefault();
    const current =
      document.documentElement.getAttribute("data-public-theme") === "dark" ? "dark" : "light";
    applyPublicTheme(current === "dark" ? "light" : "dark");
  });
  initPublicTheme();

  /* Encaminha a saída para a experiência pública. */
  document.addEventListener(
    "click",
    (event) => {
      const p = event.target.closest('[data-profile-action="sair"],[data-account-logout]');
      if (p) {
        event.preventDefault();
        event.stopImmediatePropagation();
        logout();
      }
    },
    true,
  );
  let restore = false;
  let restored = "Início";
  try {
    restore = sessionStorage.getItem("socialmei-experience-screen") === "app";
    restored = sessionStorage.getItem("socialmei-current-view") || "Início";
  } catch (_) {}
  async function loadRegistrationPolicy() {
    const retry = q("#registrationRetry");
    if (retry.disabled) return;
    retry.disabled = true;
    q("#xpRegisterForm .experience-form-hint").textContent =
      "Consultando a disponibilidade do cadastro…";
    try {
      const policy = await SocialMEIAuth.request("/auth/registration");
      if (!["open", "invite"].includes(policy?.mode)) {
        throw new Error("Política de cadastro indisponível.");
      }
      const inviteRequired = policy.mode === "invite";
      const invite = q("#registerInvite");
      invite.parentElement.hidden = !inviteRequired;
      invite.disabled = !inviteRequired;
      invite.required = inviteRequired;
      q("#xpRegisterForm .experience-form-hint").textContent = inviteRequired
        ? "Cadastro por convite. Use o e-mail que recebeu o código para criar seu negócio."
        : "Crie sua conta para começar. Não é necessário código de convite.";
      registrationAvailable = true;
      q("#xpRegisterForm [type=submit]").disabled = false;
      retry.hidden = true;
    } catch (error) {
      q("#xpRegisterForm .experience-form-hint").textContent =
        error.status === 401
          ? "O acesso inicial foi recusado. Reabra o site e confira o acesso compartilhado."
          : "Não foi possível consultar o cadastro. Tente novamente. Se já possui conta, use Entrar.";
      retry.hidden = false;
    } finally {
      retry.disabled = false;
    }
  }
  if (SocialMEIAuth.remote) {
    SocialMEIAuth.ready.then(async (identity) => {
      if (identity) {
        refreshExperienceProfile();
        const requested = sessionStorage.getItem(registrationOnboardingKey);
        sessionStorage.removeItem(registrationOnboardingKey);
        if (requested === identity.usuario.email.toLowerCase()) startBusinessOnboarding();
        else enterApp(restored);
      } else {
        authMode = "login";
        showScreen("auth");
        q("#authConfirmation").textContent = SocialMEIAuth.problem;
        await loadRegistrationPolicy();
      }
    });
  } else if (restore) {
    enterApp(restored);
  } else {
    showScreen("landing");
  }
})();
