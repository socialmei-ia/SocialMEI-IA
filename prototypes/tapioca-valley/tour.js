(function () {
  "use strict";
  const scenario = window.SocialMEITapiocaScenario;
  const params = new URLSearchParams(location.search);
  const base = new URL("../", document.currentScript.src);
  let selected =
    scenario.customers.find((customer) => customer.id === params.get("client")) ||
    scenario.customers[0];
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const theme = () => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  const destinations = [
    "onboarding/index.html",
    "tapioca-valley/inbox.html",
    "opportunities/index.html#intent-form",
    "opportunities/index.html#customer-priorities",
  ];
  function href(path) {
    const url = new URL(path, base);
    url.searchParams.set("tour", "tapioca-valley");
    url.searchParams.set("theme", theme());
    url.searchParams.set("client", selected.id);
    return url.href;
  }
  window.SocialMEITapiocaLink = href;
  document
    .querySelectorAll("[data-tour-business]")
    .forEach((node) => (node.textContent = scenario.business));
  function applyTheme() {
    document
      .querySelectorAll("[data-tour-link]")
      .forEach((node) => (node.href = href(node.dataset.tourLink)));
    document
      .querySelectorAll("a[data-tour-hub]")
      .forEach((node) => (node.href = new URL("index.html?theme=" + theme(), base).href));
    const button = document.getElementById("theme");
    if (button) {
      button.textContent = theme() === "dark" ? "Tema claro" : "Tema escuro";
      button.setAttribute("aria-pressed", String(theme() === "dark"));
    }
  }
  if (["light", "dark"].includes(params.get("theme")))
    document.documentElement.dataset.theme = params.get("theme");
  document.querySelector("[data-tour-theme]")?.addEventListener("click", () => {
    document.documentElement.dataset.theme = theme() === "dark" ? "light" : "dark";
  });
  new MutationObserver(applyTheme).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  if (scenario.active) {
    const main = document.querySelector("main");
    const banner = element("section", undefined, "tour-banner");
    banner.append(element("p", "Tapioca Valley · " + scenario.business, "eyebrow"));
    const nav = element("nav", undefined, "tour-steps");
    nav.setAttribute("aria-label", "Roteiro de demonstração");
    destinations.forEach((path, index) => {
      const link = element(
        "a",
        [
          "1. Seu negócio",
          "2. Conversas ilustrativas",
          "3. Analisar intenção",
          "4. Fila e revisão",
        ][index],
      );
      link.dataset.tourLink = path;
      nav.append(link);
    });
    banner.append(
      nav,
      element(
        "p",
        "Cenário fixo · 16/10/2026, 09h (Fortaleza). Alterações e revisões ficam apenas na página atual; sair ou recarregar reinicia o estado.",
        "tour-note",
      ),
    );
    main.prepend(banner);
    document
      .querySelectorAll('a[href="../index.html"]')
      .forEach((link) => (link.dataset.tourHub = ""));
    const updateCurrent = () => {
      const step = location.pathname.includes("/onboarding/")
        ? 0
        : location.pathname.endsWith("/inbox.html")
          ? 1
          : location.hash === "#intent-form"
            ? 2
            : 3;
      [...nav.children].forEach((link, index) => {
        if (index === step) link.setAttribute("aria-current", "step");
        else link.removeAttribute("aria-current");
      });
    };
    addEventListener("hashchange", updateCurrent);
    updateCurrent();
    if (location.pathname.includes("/onboarding/")) {
      const note = element(
        "p",
        "Roteiro fixo de perfumaria. Ajustar capacidades nesta prévia não altera as conversas do cenário nem configura o aplicativo real.",
        "tour-note",
      );
      document.querySelector(".wizard-panel").prepend(note);
      const next = element("a", "Continuar para as conversas ilustrativas", "tour-next");
      next.dataset.tourLink = destinations[1];
      next.id = "tour-next";
      document.querySelector(".wizard-panel").append(next);
      const configure = () => {
        document.querySelectorAll('[name="segment"]').forEach((radio) => {
          radio.closest("label").hidden = radio.value !== "perfume";
        });
        const perfume = document.getElementById("perfume");
        if (perfume && !perfume.checked) perfume.click();
        const area = document.getElementById("area");
        if (area && !area.value) area.value = "Fortaleza · cenário fictício";
        next.hidden = document.getElementById("download").hidden;
      };
      new MutationObserver(configure).observe(document.getElementById("step-content"), {
        childList: true,
      });
      configure();
    }
    if (location.pathname.includes("/opportunities/")) {
      document.getElementById("priority-scenario-note").textContent =
        "Três clientes sintéticos da Perfumaria Aurora · recomendação revisável";
      document.getElementById("manual-library").hidden = true;
      document.querySelector("#customer-priorities > .priority-reference").textContent =
        "Referência fictícia fixa: 16/10/2026, 09h · Fortaleza.";
      const form = document.getElementById("intent-form");
      form.prepend(
        element(
          "p",
          "Os exemplos abaixo são as mensagens deste cenário. Editar a análise avulsa não altera as conversas ou a fila.",
          "tour-note",
        ),
      );
      const picker = document.getElementById("intent-example");
      picker.addEventListener("change", () => {
        selected = scenario.customers[Number(picker.value)] || selected;
        applyTheme();
      });
      picker.value = String(
        scenario.customers.findIndex((customer) => customer.id === selected.id),
      );
      picker.dispatchEvent(new Event("change", { bubbles: true }));
      const next = element("a", "Continuar para a fila e a revisão humana", "tour-next");
      next.dataset.tourLink = destinations[3];
      document.querySelector(".intent-workspace").after(next);
      // Same-page links keep in-memory reviews; no message text is placed in URLs.
      if (location.hash === "#intent-form") requestAnimationFrame(() => form.scrollIntoView());
    }
  }
  applyTheme();
})();
