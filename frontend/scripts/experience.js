/* EXPERIENCE */
(function () {
  const experienceRoot = document.getElementById("experienceRoot");
  if (!experienceRoot) {
    return;
  }
  const screens = [...experienceRoot.querySelectorAll("[data-xp-screen]")];
  let onboardingStep = 1;
  let authMode = "register";
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
    const initials =
      String(profile.name || "")
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((x) => x[0]?.toUpperCase() || "")
        .join("") || "SM";
    if (typeof sessionData !== "undefined" && sessionData.usuario) {
      sessionData.usuario.nome = String(profile.name || "").trim();
      sessionData.usuario.primeiro = first;
      sessionData.usuario.iniciais = initials;
    }
  }
  persistExperienceProfile();

  const q = (s, base = document) => base.querySelector(s);

  const qa = (s, base = document) => [...base.querySelectorAll(s)];
  if (SocialMEIAuth.remote) {
    const field = document.createElement("div");
    field.className = "experience-field";
    field.innerHTML =
      '<label for="registerInvite">Código do convite</label><input id="registerInvite" required minlength="64" maxlength="64" pattern="[A-Za-z0-9_-]{64}" autocomplete="off" aria-describedby="registerInviteStatus"><small class="experience-field-status" id="registerInviteStatus">Use o convite recebido do administrador.</small>';
    q("#xpRegisterForm [type=submit]").before(field);
    q("#registerPassword").minLength = 12;
    q("#registerPassword").maxLength = 128;
    q("#registerPassword").placeholder = "12 caracteres ou mais";
    q("#registerPasswordStatus").textContent = "Use 12 ou mais caracteres.";
    q("#xpRegisterForm .experience-form-hint").textContent =
      "Cadastro por convite. Use o e-mail que recebeu o código para criar seu negócio.";
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
    if (q('[data-xp-screen="onboarding"].is-active') && onboardingStep === 4) {
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
    const initials =
      String(profile.name || "")
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((x) => x[0]?.toUpperCase() || "")
        .join("") || "SM";
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
    const bar = q("#xpOnboardingProgress span");
    if (bar) {
      bar.style.transform = `scaleX(${Math.min(1, onboardingStep / 4)})`;
    }
    q("#xpOnboardingProgress").setAttribute("role", "progressbar");
    q("#xpOnboardingProgress").setAttribute("aria-label", "Configuração do espaço");
    q("#xpOnboardingProgress").setAttribute("aria-valuemin", "0");
    q("#xpOnboardingProgress").setAttribute("aria-valuemax", "4");
    q("#xpOnboardingProgress").setAttribute("aria-valuenow", onboardingStep);
    qa("[data-onboard-panel]").forEach((p) =>
      p.classList.toggle("is-active", Number(p.dataset.onboardPanel) === onboardingStep),
    );
    qa("[data-onboard-step]").forEach((s) => {
      const n = Number(s.dataset.onboardStep);
      s.classList.toggle("is-current", n === onboardingStep);
      s.classList.toggle("is-done", n < onboardingStep);
      s.setAttribute("aria-current", n === onboardingStep ? "step" : "false");
      const mark = s.querySelector("span");
      if (mark) {
        mark.textContent = n < onboardingStep ? "✓" : n;
      }
      if (n === onboardingStep && previousStep !== onboardingStep) {
        motion.animate(
          mark,
          [
            {
              transform: "scale(.96)",
            },
            {
              transform: "scale(1.02)",
            },
            {
              transform: "none",
            },
          ],
          "motion-medium",
          "ease-spring",
        );
      }
    });
    previousStep = onboardingStep;
    q("[data-onboard-back]").classList.toggle("show", onboardingStep > 1);
    q("[data-onboard-next]").textContent =
      onboardingStep === 3
        ? "Preparar meu espaço"
        : onboardingStep === 4
          ? "Entrar no SocialMEI"
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
    if (onboardingStep === 3) {
      profile.channels = qa('.experience-choice.is-selected[data-choice-group="channel"]').map(
        (x) => x.dataset.choice,
      );
      profile.focus =
        qa('.experience-choice.is-selected[data-choice-group="focus"]').map(
          (x) => x.dataset.choice,
        )[0] || "Atendimento";
      const title = q("#xpReadyTitle");
      if (title) {
        title.textContent = profile.name.trim()
          ? `Seu espaço está pronto, ${profile.name.trim().split(/\s+/)[0]}.`
          : "Seu espaço está pronto.";
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
    }
    persistExperienceProfile();
  }
  experienceRoot.addEventListener("click", (event) => {
    const go = event.target.closest("[data-xp-go]");
    if (go) {
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
    const next = event.target.closest("[data-onboard-next]");
    if (next) {
      if (!validateOnboard()) {
        return;
      }
      collectStep();
      if (onboardingStep < 4) {
        stepTransition(onboardingStep + 1);
      } else {
        enterApp();
      }
      return;
    }
    const back = event.target.closest("[data-onboard-back]");
    if (back && onboardingStep > 1) {
      collectStep();
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
      if (SocialMEIAuth.remote) {
        if (event.target.id === "xpLoginForm") {
          await SocialMEIAuth.login({
            email: q("#loginEmail").value.trim(),
            senha: q("#loginPassword").value,
            lembrar: q("#loginRemember").checked,
          });
        } else {
          await SocialMEIAuth.register({
            nome: q("#registerName").value.trim(),
            email: q("#registerEmail").value.trim(),
            telefone: q("#registerPhone").value.trim(),
            senha: q("#registerPassword").value,
            convite: q("#registerInvite").value.trim(),
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
        persistExperienceProfile();
        enterApp();
      } else {
        profile.name = q("#registerName").value.trim() || profile.name;
        profile.email = q("#registerEmail").value.trim();
        profile.phone = q("#registerPhone").value.trim();
        persistExperienceProfile();
        onboardingStep = 1;
        // Reutiliza os dados do cadastro no preenchimento inicial do onboarding.
        q("#obName").value = profile.name;
        q("#obEmail").value = profile.email;
        q("#obPhone").value = profile.phone;
        showScreen("onboarding");
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
      q("#authConfirmation").textContent =
        error.message || "Não foi possível entrar. Tente novamente.";
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
  let previousStep = 1;
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
    q("#previewPhone").textContent =
      digits.length >= 10
        ? `(${digits.slice(0, 2)}) •••••-${digits.slice(-4)}`
        : "Um canal para conversar";
    for (const [id, built] of [
      [
        "previewProfile",
        !!name && q("#registerEmail").validity.valid && !!q("#registerEmail").value,
      ],
      ["previewChannel", digits.length >= 10],
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
      [10, 11].includes(digits.length),
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
    const d = element.value.replace(/\D/g, "").slice(0, 11);
    const n = d.length > 10 ? 5 : 4;
    element.value =
      d.length < 3
        ? d
        : `(${d.slice(0, 2)}) ${d.slice(2, 2 + n)}${d.length > 2 + n ? "-" + d.slice(2 + n) : ""}`;
  }
  function validateAuth(input) {
    if (input.id === "registerName") {
      input.setCustomValidity(input.value.trim() ? "" : "Informe seu nome.");
    }
    if (input.id === "registerPhone") {
      input.setCustomValidity(
        [10, 11].includes(input.value.replace(/\D/g, "").length)
          ? ""
          : "Informe o WhatsApp com DDD e 10 ou 11 dígitos.",
      );
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
        if (element.id === "registerPhone") {
          maskPhone(element);
        }
        element.closest(".experience-field").classList.toggle("is-filled", !!element.value);
        if (element.dataset.visited) {
          validateAuth(element);
        }
        clearTimeout(previewTimer);
        previewTimer = setTimeout(updatePreview, motion.ms("motion-fast"));
      });
    });
  q("#obPhone").addEventListener("input", (event) => maskPhone(event.target));
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
    const name = q("#obName").value.trim() || profile.name;
    const business = q("#obBusiness").value.trim() || profile.business;
    q("#obPreviewBusiness").textContent = business;
    q("#obPreviewPerson").textContent = name;
    q("#obPreviewAvatar").textContent = business
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((x) => x[0] || "")
      .join("")
      .toUpperCase();
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
    const fields = qa(".onboarding-panel.is-active input,.onboarding-panel.is-active select");
    fields.forEach((element) => {
      let message = "";
      const value = element.value.trim();
      if (element.required && !value) {
        message = "Preencha este campo antes de continuar.";
      }
      if (element.id === "obPhone" && value && !/^\d{10,11}$/.test(value.replace(/\D/g, ""))) {
        message = "Use um telefone com DDD e 10 ou 11 dígitos.";
      }
      if (element.id === "obCnpj" && value && !isValidCnpj(value)) {
        message = "Confira os 14 dígitos do CNPJ ou deixe em branco.";
      }
      element.setCustomValidity(message);
    });
    const invalid = fields.find((element) => !element.checkValidity());
    fields.forEach((element) =>
      element.setAttribute("aria-invalid", String(!element.validity.valid)),
    );
    if (invalid) {
      q("#obValidation").textContent = "Confira o campo indicado antes de continuar.";
      invalid.focus();
      invalid.reportValidity();
      return false;
    }
    return true;
  }
  qa(".onboarding-screen input,.onboarding-screen select").forEach((element) => {
    element.addEventListener("input", () => {
      element.setCustomValidity("");
      element.removeAttribute("aria-invalid");
      q("#obValidation").textContent = "";
      updateOnboardingPreview();
    });
    element.addEventListener("change", updateOnboardingPreview);
  });
  async function stepTransition(nextStep) {
    if (onboardingBusy) {
      return;
    }
    onboardingBusy = true;
    const direction = nextStep > onboardingStep ? 1 : -1;
    const old = q(".onboarding-panel.is-active");
    await motion.animate(
      old,
      [
        {
          opacity: 1,
          transform: "none",
        },
        {
          opacity: 0,
          transform: `translateX(${-direction * 12}px)`,
        },
      ],
      150,
      "ease-exit",
    );
    onboardingStep = nextStep;
    syncOnboarding();
    updateOnboardingPreview();
    q("#obValidation").textContent = "";
    const next = q(".onboarding-panel.is-active");
    const title = next.querySelector("h1,h2");
    if (title) {
      title.tabIndex = -1;
      title.focus({
        preventScroll: true,
      });
    }
    await motion.animate(
      next,
      [
        {
          opacity: 0,
          transform: `translateX(${direction * 12}px)`,
        },
        {
          opacity: 1,
          transform: "none",
        },
      ],
      150,
      "ease-enter",
    );
    if (nextStep === 4) {
      motion.animate(
        q("#readyCheck"),
        [
          {
            strokeDasharray: "1",
            strokeDashoffset: "1",
          },
          {
            strokeDasharray: "1",
            strokeDashoffset: "0",
          },
        ],
        "motion-slow",
      );
      qa(".experience-complete-list>div").forEach((element, i) =>
        motion.animate(
          element,
          [
            {
              opacity: 0,
              transform: "translateY(8px)",
            },
            {
              opacity: 1,
              transform: "none",
            },
          ],
          "motion-medium",
          "ease-enter",
          i * motion.ms("stagger"),
        ),
      );
    }
    onboardingBusy = false;
  }
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
  const ruleIcon = (r) =>
    ruleAreaOf(r) === "Financeiro"
      ? "wallet"
      : ruleAreaOf(r) === "Atendimento"
        ? "inbox"
        : ruleAreaOf(r) === "Clientes"
          ? "users"
          : "bag";
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
                  ${area}<b
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
        sessionData.conversas.find(
          (c) =>
            ["aberto", "andamento"].includes(c.status) &&
            [...c.mensagens].reverse().find((m) => m.de !== "nota")?.de === "cliente",
        ) || sessionData.conversas[0];
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
    return sessionData.conversas.find(
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
    const rows = sessionData.conversas.filter((conversation) =>
      normalizedText(displayName(conversation) + " " + lastMessage(conversation)).includes(query),
    );
    q("#asConversationCount").textContent = sessionData.conversas.length;
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
      sessionData.conversas
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
          [
            {
              opacity: 0.65,
              filter: "blur(2px)",
            },
            {
              opacity: 1,
              filter: "blur(0)",
            },
          ],
          220,
        );
      } else {
        motion.animate(
          q("#aiReviewSection"),
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
          420,
        );
        motion.animate(
          q(".assistant-draft-text", assistantRoot),
          [
            {
              opacity: 0,
              filter: "blur(2px)",
              transform: "translateY(5px)",
            },
            {
              opacity: 1,
              filter: "blur(0)",
              transform: "none",
            },
          ],
          480,
          "ease-out",
          40,
        );
        qa(".assistant-draft-actions button", assistantRoot).forEach((b, i) =>
          motion.animate(
            b,
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
            190,
            "ease-out",
            140 + i * 25,
          ),
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
    if (!sessionData.conversas.some((conversation) => String(conversation.id) === String(id))) {
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
  /**
   * Produz sugestões locais a partir dos registros existentes. O usuário revisa o resultado antes de inserir qualquer texto na Caixa.
   */
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
    assistantDrafts = tones.map((tone) => {
      const hello =
        tone === "Formal"
          ? `Olá, ${name}.`
          : tone === "Amigável"
            ? `Oi, ${first}! Tudo bem?`
            : `Olá, ${first}.`;
      let text = "";
      if (assistantIntent === "summary") {
        text = `${name} · ${channelLabel(conversation.canal)} · ${statusLabel(conversation.status)}\nÚltima mensagem: “${last}”${ctx.client?.observacao ? "\nNota do perfil: " + ctx.client.observacao : ""}${note ? "\nNota interna: " + (note.texto || note.text || "Nota sem texto") : ""}`;
        text +=
          "\n" +
          (tone === "Curto"
            ? "Próximo passo: conferir a dúvida e responder."
            : tone === "Amigável"
              ? "Vale ler a conversa completa com calma antes de preparar o próximo contato."
              : "Recomendação: revisar o histórico integral e verificar os dados antes de tomar qualquer ação.");
      } else if (assistantIntent === "reply") {
        text =
          hello +
          " " +
          (tone === "Curto"
            ? "Recebi sua mensagem. Vou conferir os detalhes e retorno por aqui."
            : tone === "Amigável"
              ? "Obrigado por conversar com a gente. Vou olhar sua dúvida com cuidado e te retorno por aqui."
              : "Agradeço o contato. Vou verificar as informações da sua solicitação antes de retornar.");
      } else if (assistantIntent === "sales") {
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
      } else if (assistantIntent === "collect") {
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
    if (sessionData.conversas.some((conversation) => String(conversation.id) === String(id))) {
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
      q("#aiContextSelect").value = sessionData.conversas.some(
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
        !sessionData.conversas.some((conversation) => conversation.id === d.conversationId)
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
  q("#nvRuleModelsDisclosure").open = innerWidth > 720;
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
    const unread = sessionData.conversas.reduce(
      (conversation, c) => conversation + (c.naoLidas || 0),
      0,
    );
    const overdue = appData.financeiro.filter((entry) => ledgerStatus(entry) === "atrasado").length;
    const balance = operationalMetrics({
      from: "0000-01-01",
      to: todayISO(),
    }).balance;
    const context = q("#homeContext");
    const ledger = appData.financeiro.filter((entry) => !entry.excluida);
    const pendingLedger = ledger.filter((entry) => entry.status !== "pago");
    const hasBusinessRecords =
      appData.clientes.length || appData.produtos.length || appData.vendas.length || ledger.length;
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
      ? `${plural(unread, "não lida", "não lidas")}`
      : sessionData.conversas.length
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
      sessionData.conversas.find((conversation) => conversation.naoLidas) ||
      sessionData.conversas[0];
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
                <button class="btn" data-home-conversation="${c.id}">Continuar conversa →</button>`
      : /* HTML */ `
          <span class="chapter-label">UM NOVO COMEÇO</span>
          <h3>O próximo capítulo começa com seus clientes.</h3>
          <p class="home-empty-note">Cadastre seus contatos e reúna o contexto de cada relacionamento.</p>
          <button class="btn" data-home-go="Clientes">Ver clientes →</button>
        `;
    renderHomeOperations();
    q("#homeLiveIcon").innerHTML = renderIcon(homeIcons?.[iconCycle] || "inbox");
    nextHomeIcon();
  };

  function renderHomeOperations() {
    const routes = {
      overdue: "Financeiro",
      reply: "Caixa Unificada",
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
    const recent = appData.vendas
      .filter((sale) => !sale.excluida)
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
      hint: () =>
        `${sessionData.conversas.reduce((conversation, c) => conversation + c.naoLidas, 0)} mensagens não lidas`,
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
        `${appData.financeiro.filter((entry) => ledgerStatus(entry) === "atrasado").length} em atraso`,
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
  if (SocialMEIAuth.remote) {
    SocialMEIAuth.ready.then((identity) => {
      if (identity) {
        refreshExperienceProfile();
        enterApp(restored);
      } else {
        authMode = "login";
        showScreen("auth");
        q("#authConfirmation").textContent = SocialMEIAuth.problem;
      }
    });
  } else if (restore) {
    enterApp(restored);
  } else {
    showScreen("landing");
  }
})();
