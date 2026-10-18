/* Isolated presentation only. No auth, API, storage or official onboarding hooks. */
(() => {
  "use strict";
  const model = window.SocialMEIBusinessProfile;
  const names = ["Você", "Negócio", "Ofertas", "Rotina", "Ferramentas", "Revisão"];
  const $ = (id) => document.getElementById(id);
  const escape = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
    );
  const paths = {
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    moon: '<path d="M20.5 13A8.5 8.5 0 0 1 11 3.5a8.5 8.5 0 1 0 9.5 9.5Z"/>',
    beauty:
      '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="m8 8 12 12M8 16 20 4M14 12l-3-3"/>',
    fashion: '<path d="M9 5a3 3 0 0 1 6 0c0 2-3 2-3 4v2l9 6v2H3v-2l9-6"/>',
    food: '<path d="M4 9h13v6a6 6 0 0 1-12 0V9m13 0h1a3 3 0 0 1 0 6h-1M3 22h17M7 2v3m5-3v3"/>',
    commerce:
      '<path d="M3 10v11h18V10M2 5l2-3h16l2 3v5H2V5m6 16v-7h8v7M2 10c2 3 5 3 7 0 2 3 5 3 7 0 2 3 5 3 6 0"/>',
    technology:
      '<rect x="5" y="2" width="14" height="20" rx="3"/><path d="M10 18h4m-6-9 3 3 5-5"/>',
    services: '<path d="M14 3a6 6 0 0 0-7 8L2 16l6 6 5-5a6 6 0 0 0 8-7l-4 4-7-7 4-4Z"/>',
    product: '<path d="m3 7 9-5 9 5-9 5-9-5Zm0 0v11l9 4 9-4V7M12 12v10M7 4l10 5"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    space: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 9h18M9 9v12"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  };
  const icon = (name) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.space}</svg>`;
  const families = [
    {
      id: "beauty",
      title: "Beleza e cuidados",
      hint: "Cabelo, unhas e beleza",
      groups: ["Beleza e cuidados"],
    },
    {
      id: "fashion",
      title: "Moda e confecção",
      hint: "Peças, costura e ajustes",
      groups: ["Moda e confecção"],
    },
    {
      id: "food",
      title: "Alimentação",
      hint: "Doces, lanches e refeições",
      groups: ["Alimentação"],
    },
    {
      id: "commerce",
      title: "Comércio e varejo",
      hint: "Lojas, mercadorias e vendas",
      groups: ["Comércio e varejo"],
    },
    {
      id: "technology",
      title: "Tecnologia e reparos",
      hint: "Aparelhos e consertos",
      groups: ["Tecnologia e reparos"],
    },
    {
      id: "services",
      title: "Serviços e outros",
      hint: "Seu trabalho, sua especialidade",
      groups: ["Serviços profissionais", "Outras atividades"],
    },
  ];
  const priorities = {
    service: "Responder clientes melhor",
    sales: "Organizar minhas vendas",
    finance: "Acompanhar meu dinheiro",
    time: "Economizar tempo na rotina",
  };
  const initial = () => ({
    step: 1,
    maxVisited: 1,
    busy: false,
    dirty: false,
    done: false,
    returnTo: null,
    family: null,
    segmentChosen: false,
    offersTouched: false,
    search: "",
    toolsTouched: false,
    contact: { name: "", email: "", phone: "", city: "", instagram: "", cnpj: "" },
    draft: model.normalize(),
    channels: [],
    priority: "service",
    errors: {},
  });
  let state = initial();
  let lastResetTrigger = null;
  let specialtyAnimation = null;
  const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const announce = (text) => {
    $("announcement").textContent = text;
  };
  const profile = () => model.normalize(state.draft);
  const selection = (name, value) => {
    const values = name === "offers" ? state.draft.offers : state.draft[name];
    return values.includes(value) ? " checked" : "";
  };
  function field(id, label, value, type = "text", extra = "", placeholder = "") {
    return `<label class="ob3-field" for="${id}"><span>${label}</span><input id="${id}" name="${id}" type="${type}" value="${escape(value)}" placeholder="${escape(placeholder)}" ${extra} aria-describedby="${id}Feedback"/><small id="${id}Feedback" class="ob3-feedback" aria-live="polite"></small></label>`;
  }
  const intro = (title, description, extra = "") =>
    `<header class="ob3-intro"><h1 id="stageTitle" tabindex="-1">${title}</h1><p class="ob3-lead">${description}</p>${extra}</header>`;
  const optional = () =>
    '<button type="button" class="ob3-text-button" data-action="skip">Decidir depois →</button>';
  function contactView() {
    return `<div class="ob3-split"><section class="ob3-welcome"><p class="ob3-eyebrow">Um começo leve</p>${intro("Vamos começar por você.", "Seu negócio tem um jeito próprio. Vamos preparar um espaço que combine com ele.")}<p class="ob3-note">Explore com <strong>dados fictícios</strong>. Nada é enviado ou salvo.</p></section><section class="ob3-contact-form" aria-label="Seus dados demonstrativos">${field("personName", "Como podemos chamar você?", state.contact.name, "text", 'required maxlength="80" autocomplete="name"', "Seu nome")}${field("email", "E-mail demonstrativo", state.contact.email, "email", 'required maxlength="254" autocomplete="email"', "ana@example.com")}${field("phone", "WhatsApp <small>(opcional)</small>", state.contact.phone, "tel", 'maxlength="32" autocomplete="tel" inputmode="tel"', "(81) 99999-0000")}<div class="ob3-example"><span>Prefere explorar sem preencher?</span><button class="ob3-text-button" type="button" data-action="example">Usar exemplo</button></div></section></div>`;
  }
  function businessView() {
    return `<div class="ob3-business-top">${intro("Seu negócio, do seu jeito.", "Escolha sua área. Depois, a especialidade que combina com você.")}${field("businessName", "Nome do seu negócio", state.draft.businessName, "text", 'required maxlength="120" autocomplete="organization"', "Ex.: Barbearia da Ana")}</div>
      <div class="ob3-discovery">
        <section aria-labelledby="familyTitle">
          <div class="ob3-area-heading"><h2 id="familyTitle">Em qual área você trabalha?</h2><div class="ob3-search">${field("activitySearch", "Ou busque sua atividade", state.search, "search", 'maxlength="90" autocomplete="off" aria-controls="specialties"', "Ex.: barbeiro, costura, celular")}</div></div>
          <div id="familyGrid" class="ob3-families">${families.map((f) => `<button type="button" class="ob3-family" data-family="${f.id}" aria-pressed="${state.family === f.id}" aria-controls="specialties">${icon(f.id)}<span><b>${f.title}</b><small>${f.hint}</small></span><span class="ob3-family-mark" aria-hidden="true">✓</span></button>`).join("")}</div>
        </section>
        <section class="ob3-picker" aria-label="Escolha da especialidade">
          <div id="specialties"></div><p class="ob3-error" id="segmentFeedback" role="status"></p>
          <div id="currentSelection" role="status"></div>
          <details class="ob3-all-activities"><summary>Prefiro ver a lista completa</summary><label class="ob3-field" for="allActivities"><span>Todas as atividades</span><select id="allActivities"><option value="" disabled${!state.segmentChosen ? " selected" : ""}>Escolha uma atividade</option>${Object.entries(
            model.segments,
          )
            .map(
              ([id, item]) =>
                `<option value="${id}"${state.segmentChosen && state.draft.segment === id ? " selected" : ""}>${escape(item.label)}</option>`,
            )
            .join("")}</select></label></details>
          <div id="manualActivity"${state.draft.segment === "other" && state.segmentChosen ? "" : " hidden"}>${field("activity", "Sua atividade, com suas palavras", state.draft.activity, "text", 'maxlength="120"', "Ex.: restauração de móveis")}</div>
        </section>
      </div>
      <section class="ob3-section ob3-business-offers" aria-labelledby="offeringTitle"><div><h2 id="offeringTitle">E o que você oferece?</h2><p class="ob3-note">Pode escolher as duas opções.</p></div><div class="ob3-offer-switch" role="group" aria-labelledby="offeringTitle" aria-describedby="offersFeedback"><label><input type="checkbox" name="offers" value="products"${selection("offers", "products")}/>Produtos</label><label><input type="checkbox" name="offers" value="services"${selection("offers", "services")}/>Serviços</label></div><p id="offersFeedback" class="ob3-error" role="status"></p></section>
      <details class="ob3-optional"><summary>Adicionar informações do negócio <span>(opcional)</span></summary><div class="ob3-fields-row">${field("city", "Cidade", state.contact.city, "text", 'maxlength="100" autocomplete="address-level2"', "Ex.: Belo Jardim – PE")}${field("instagram", "Instagram", state.contact.instagram, "text", 'maxlength="40"', "@seunegocio")}${field("cnpj", "CNPJ", state.contact.cnpj, "text", 'maxlength="18" inputmode="numeric"', "00.000.000/0001-00")}</div><p class="ob3-note">Informações demonstrativas; não há consulta nem cadastro de empresa.</p></details>`;
  }

  const searchAliases = {
    barber: "barbeiro",
    hairdresser: "cabeleireira cabeleireiro",
    tailoring: "costureira costureiro",
    bakery: "boleira bolos confeiteira",
    phoneRepair: "conserto celular manutenção telefone",
    laboratory: "química químico",
    manicure: "nail designer",
  };
  function picker() {
    const needle = state.search
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();
    const family = families.find((f) => f.id === state.family);
    const entries = Object.entries(model.segments).filter(([id, segment]) => {
      const haystack = [
        id,
        segment.label,
        segment.family,
        segment.description,
        searchAliases[id] || "",
      ]
        .join(" ")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase();
      return needle ? haystack.includes(needle) : family?.groups.includes(segment.family);
    });
    if (needle)
      announce(
        entries.length
          ? `${entries.length} atividades encontradas.`
          : "Nenhuma atividade encontrada. Tente outro termo ou use a lista completa.",
      );
    $("familyGrid").hidden = !!needle;
    document.querySelector(".ob3-discovery").classList.toggle("is-searching", !!needle);
    $("familyGrid")
      .querySelectorAll("button")
      .forEach((button) =>
        button.setAttribute("aria-pressed", String(button.dataset.family === state.family)),
      );
    $("specialties").innerHTML =
      !needle && !family
        ? '<p class="ob3-note">Escolha uma área acima para ver suas especialidades. Você também pode descrever outra atividade.</p><button class="ob3-text-button" type="button" data-action="other">Descrever outra atividade →</button>'
        : !entries.length
          ? '<p class="ob3-note">Não encontramos essa atividade. Tente outra palavra ou descreva seu trabalho.</p><button class="ob3-text-button" type="button" data-action="other">Descrever outra atividade →</button>'
          : `<fieldset class="ob3-specialties" aria-describedby="segmentFeedback"><legend>${needle ? "Resultados da busca" : "Agora, sua especialidade"}<small>${entries.length} ${entries.length === 1 ? "opção" : "opções"}${needle ? " encontradas" : " em " + escape(family.title)}</small></legend><div class="ob3-specialty-grid">${entries.map(([id, item]) => `<label class="ob3-radio-row"><input type="radio" name="segment" value="${id}"${state.segmentChosen && id === state.draft.segment ? " checked" : ""}/><span><b>${escape(item.label)}</b><small>${escape(item.description)}</small></span></label>`).join("")}</div></fieldset>`;
    $("currentSelection").innerHTML = state.segmentChosen
      ? `<p class="ob3-selection">Sua escolha: <b>${escape(model.segments[state.draft.segment].label)}</b></p>`
      : "";
    $("allActivities").value = state.segmentChosen ? state.draft.segment : "";
    $("manualActivity").hidden = !(state.segmentChosen && state.draft.segment === "other");
  }
  function choiceGroup(kind, title, description, glyph) {
    const segment = model.segments[state.draft.segment];
    const suggestions = kind === "services" ? segment.services : segment.products;
    const all = [...new Set([...suggestions, ...state.draft[kind]])];
    return `<section aria-labelledby="${kind}Title"><div class="ob3-group-title">${icon(glyph)}<h2 id="${kind}Title">${title}</h2></div><p class="ob3-note">${description}</p><div id="${kind}Choices" class="ob3-chips">${chips(kind, all)}</div><p class="ob3-choice-count" id="${kind}Count">${state.draft[kind].length} ${state.draft[kind].length === 1 ? "selecionado" : "selecionados"}</p><div class="ob3-custom-add">${field(`${kind}Custom`, `Adicionar ${kind === "services" ? "outro serviço" : "outra categoria"}`, "", "text", 'maxlength="80"', kind === "services" ? "Ex.: atendimento em domicílio" : "Ex.: perfumes artesanais")}<button type="button" class="ob3-button ob3-secondary" data-add="${kind}" aria-label="Adicionar ${kind === "services" ? "serviço" : "categoria"}">+</button></div></section>`;
  }
  function chips(kind, values) {
    return values
      .map(
        (value) =>
          `<label class="ob3-chip"><input type="checkbox" name="${kind}" value="${escape(value)}"${selection(kind, value)}/><span>${escape(value)}</span></label>`,
      )
      .join("");
  }
  function offeringsView() {
    return `${intro("O que você faz bem?", "Escolha o que seus clientes encontram no seu negócio. São sugestões para o perfil, não cadastros de catálogo.", optional())}<div class="ob3-offerings">${state.draft.offers.includes("services") ? choiceGroup("services", "Seus serviços", "Marque quantos fizerem sentido para você.", "beauty") : ""}${state.draft.offers.includes("products") ? choiceGroup("productCategories", "Seus produtos", "Escolha categorias. Os itens e preços vêm depois.", "product") : ""}</div><p class="ob3-note ob3-section">Quer combinar produtos e serviços? <button class="ob3-text-button" type="button" data-action="editOffers">Ajustar tipo de oferta</button></p>`;
  }
  function routineView() {
    const options = model.routineOptions(state.draft);
    const groups = [
      ["Atendimentos", ["appointments", "walkIns", "recurring"]],
      ["Pedidos e entregas", ["orders", "quotes", "onlineOrders", "deliveries"]],
      ["Estrutura do negócio", ["inventory", "team"]],
    ];
    return `${intro("Como seu dia acontece?", "Marque o que faz parte da sua rotina. Você pode combinar formas diferentes de trabalhar.", optional())}<div class="ob3-routine">${groups
      .map(([title, ids]) => {
        const group = options.filter(([id]) => ids.includes(id));
        return group.length
          ? `<fieldset class="ob3-routine-group"><legend>${title}</legend>${group.map(([id, label]) => `<label class="ob3-check-row"><input type="checkbox" name="capabilities" value="${id}"${state.draft.capabilities[id] ? " checked" : ""}/><span>${label}</span></label>`).join("")}</fieldset>`
          : "";
      })
      .join(
        "",
      )}</div><p class="ob3-note ob3-routine-note">Não precisa decidir tudo agora. Uma opção desmarcada significa apenas que você não a selecionou.</p>`;
  }
  function moduleChoice(id, future = false) {
    return `<label class="ob3-check-row"><input type="checkbox" name="modules" value="${id}"${state.draft.modules.includes(id) ? " checked" : ""}/><span>${escape(model.modules[id])}${future ? '<small class="ob3-future-badge">Interesse futuro · em desenvolvimento</small>' : ""}</span></label>`;
  }
  function toolsView() {
    const available = model.availableModules(profile());
    const active = available.filter((id) => !model.futureFeatures[id]);
    const future = available.filter((id) => model.futureFeatures[id]);
    return `${intro("Seu espaço começa a ganhar forma.", "Escolha o que quer ter à mão. Estas preferências não ativam módulos nem conectam canais no protótipo.", optional())}<div class="ob3-tools"><section class="ob3-tools-options" aria-labelledby="availableToolsTitle"><h2 id="availableToolsTitle">Disponíveis no aplicativo</h2><div class="ob3-module-list">${active.map((id) => moduleChoice(id)).join("")}</div><details class="ob3-future"><summary>Para o futuro · ainda em desenvolvimento</summary><p class="ob3-note">Marque apenas seu interesse. Isso não libera uma funcionalidade.</p>${future.length ? future.map((id) => moduleChoice(id, true)).join("") : '<p class="ob3-note">Agenda, encomendas, entregas e gestão de equipe ainda dependem de desenvolvimento. As opções de interesse acompanham a rotina informada.</p>'}</details></section><section class="ob3-space-preview" aria-labelledby="spacePreviewTitle"><p class="ob3-note">Organização sugerida</p><h2 id="spacePreviewTitle">${escape(state.draft.businessName)}</h2><p class="ob3-note">${escape(state.draft.segment === "other" ? state.draft.activity || "Seu negócio" : model.segments[state.draft.segment].label)}</p><div id="spacePreview"></div><p class="ob3-note">Prévia dos atalhos escolhidos. Sem números, registros ou integrações inventados.</p></section></div><div class="ob3-preferences"><section aria-labelledby="channelsTitle"><h3 id="channelsTitle">Por onde seus clientes falam com você?</h3><p class="ob3-note">Só uma preferência. Nenhum canal será conectado.</p><div class="ob3-offer-switch" role="group" aria-labelledby="channelsTitle">${["WhatsApp", "Instagram"].map((value) => `<label><input type="checkbox" name="channels" value="${value}"${state.channels.includes(value) ? " checked" : ""}/>${value}</label>`).join("")}</div></section><fieldset class="ob3-priorities"><legend>O que merece atenção primeiro?</legend>${Object.entries(
      priorities,
    )
      .map(
        ([id, text]) =>
          `<label class="ob3-radio-row"><input type="radio" name="priority" value="${id}"${state.priority === id ? " checked" : ""}/><span>${text}</span></label>`,
      )
      .join("")}</fieldset></div>`;
  }
  function updateSpace() {
    if (!$("spacePreview")) return;
    const active = state.draft.modules.filter((id) => !model.futureFeatures[id]);
    $("spacePreview").innerHTML = active.length
      ? `<ul>${active.map((id) => `<li>${icon("space")}<span>${escape(model.modules[id])}</span></li>`).join("")}</ul>`
      : '<p class="ob3-note ob3-section">Nenhum atalho escolhido. Você poderá decidir depois.</p>';
  }
  function reviewBlock(title, step, rows) {
    return `<section class="ob3-review-block"><header><h2>${title}</h2><button class="ob3-text-button" type="button" data-edit="${step}">Editar <span class="ob3-sr">${title}</span></button></header><dl>${rows.map(([label, value]) => `<dt>${label}</dt><dd>${escape(value || "Não informado")}</dd>`).join("")}</dl></section>`;
  }
  function reviewView() {
    const p = profile();
    const active = p.modules.filter((id) => !model.futureFeatures[id]);
    const future = p.modules.filter((id) => model.futureFeatures[id]);
    return `<div class="ob3-review"><div class="ob3-review-heading">${icon("space")}${intro("Um perfil com a sua cara.", "Confira suas escolhas. Você pode editar qualquer parte antes de concluir a demonstração.")}</div>${reviewBlock(
      "Você",
      1,
      [
        ["Nome", state.contact.name],
        ["E-mail demonstrativo", state.contact.email],
        ["WhatsApp", state.contact.phone],
      ],
    )}${reviewBlock("Seu negócio", 2, [["Negócio", p.businessName], ["Atividade", p.segment === "other" ? p.activity || "Outra atividade" : model.segments[p.segment].label], ["Ofertas", p.offers.map((id) => (id === "services" ? "Serviços" : "Produtos")).join(" e ")], ...["city", "instagram", "cnpj"].filter((id) => state.contact[id]).map((id) => [{ city: "Cidade", instagram: "Instagram", cnpj: "CNPJ" }[id], state.contact[id]])])}${reviewBlock(
      "Produtos e serviços",
      3,
      [
        ["Serviços sugeridos", p.services.join(" · ") || "Escolher depois"],
        ["Categorias sugeridas", p.productCategories.join(" · ") || "Escolher depois"],
      ],
    )}${reviewBlock("Sua rotina", 4, [
      [
        "Preferências",
        Object.entries(p.capabilities)
          .filter(([, chosen]) => chosen)
          .map(([id]) => model.capabilities[id])
          .join(" · ") || "Decidir depois",
      ],
    ])}${reviewBlock("Seu espaço", 5, [
      [
        "Atalhos disponíveis",
        active.map((id) => model.modules[id]).join(" · ") || "Escolher depois",
      ],
      [
        "Interesses futuros",
        future.map((id) => `${model.modules[id]} (em desenvolvimento)`).join(" · ") ||
          "Nenhum selecionado",
      ],
      ["Canais de interesse", state.channels.join(" · ") || "Escolher depois"],
      ["Primeiro foco", priorities[state.priority]],
    ])}<p class="ob3-review-note">Ao concluir, você verá o resultado apenas nesta página. Nada será salvo na conta, no catálogo ou no navegador.</p></div>`;
  }
  function doneView() {
    return `<section class="ob3-done">${icon("check")}${intro("Sua demonstração está pronta.", `${escape(state.contact.name.split(/\s+/)[0])}, este é um exemplo de como o SocialMEI pode conhecer ${escape(state.draft.businessName)}.`)}<p class="ob3-note ob3-section">Nenhuma conta foi criada. Produtos, serviços, agenda e canais não foram cadastrados nem conectados. Suas escolhas continuam só na memória desta página.</p><button type="button" class="ob3-button ob3-secondary" data-action="review">Conferir configuração</button></section>`;
  }
  function prepareModules() {
    state.draft = profile();
    if (!state.toolsTouched) {
      const eligible = model.availableModules(state.draft);
      const suggested = [
        ...(state.draft.offers.includes("services") ? ["services"] : []),
        ...(state.draft.offers.includes("products") ? ["products"] : []),
        "clients",
        "sales",
        "finance",
      ];
      state.draft.modules = suggested.filter((id) => eligible.includes(id));
    }
  }
  function render() {
    document.body.classList.toggle("ob3-business-step", state.step === 2 && !state.done);
    if (state.step === 5) prepareModules();
    $("stepList").innerHTML = names
      .map((name, i) => {
        const n = i + 1,
          complete = n < state.maxVisited || state.done;
        return `<li><button type="button" data-step="${n}" class="${complete && n !== state.step ? "is-complete" : ""}"${n === state.step ? ' aria-current="step"' : ""}${n > state.maxVisited || n === state.step ? " disabled" : ""} aria-label="${n < state.maxVisited ? "Rever" : "Etapa"} ${n}: ${name}"><span aria-hidden="true">${complete && n !== state.step ? "✓" : n}</span><span class="ob3-step-label">${name}</span></button></li>`;
      })
      .join("");
    $("progressFill").style.transform = `scaleX(${(state.step - 1) / 5})`;
    $("stepStatus").textContent =
      `${state.step} de 6 · ${names[state.step - 1]}${state.done ? " · demonstração concluída" : ""}`;
    $("stage").innerHTML = state.done
      ? doneView()
      : [contactView, businessView, offeringsView, routineView, toolsView, reviewView][
          state.step - 1
        ]();
    if (state.step === 2 && !state.done) picker();
    if (state.step === 5 && !state.done) updateSpace();
    $("backButton").hidden = state.step === 1 || state.done;
    $("nextButton").hidden = state.done;
    $("nextButton").textContent =
      state.returnTo && state.step !== 6
        ? state.returnTo === 6
          ? "Aplicar e voltar à revisão"
          : "Voltar às ofertas"
        : state.step === 6
          ? "Concluir demonstração"
          : "Continuar →";
    $("footerNote").textContent = state.done
      ? "Demonstração concluída nesta página. Nada foi salvo."
      : state.step === 6
        ? "Demonstração em memória. Sem criar conta ou registros."
        : state.step === 2
          ? "Prévia em memória. No aplicativo, o perfil é local neste navegador, sem sincronização."
          : "Dados fictícios · respostas só nesta página.";
    state.errors = {};
  }
  function setError(id, message) {
    state.errors[id] = message;
    const feedback = $(id + "Feedback");
    if (feedback) {
      feedback.textContent = message;
      feedback.classList.add("is-error");
    }
    $(id)?.setAttribute("aria-invalid", "true");
  }
  function clearError(id) {
    delete state.errors[id];
    const feedback = $(id + "Feedback");
    if (feedback) {
      feedback.textContent = "";
      feedback.classList.remove("is-error", "is-valid");
    }
    $(id)?.removeAttribute("aria-invalid");
  }
  function errorsFor(step) {
    const errors = {};
    if (step === 1) {
      const email = document.createElement("input");
      email.type = "email";
      email.required = true;
      email.value = state.contact.email;
      if (!state.contact.name.trim()) errors.personName = "Conte como podemos chamar você.";
      if (!email.validity.valid) errors.email = "Use um e-mail no formato ana@example.com.";
      if (state.contact.phone.trim() && !SocialMEIContacts.phone(state.contact.phone, true).valid)
        errors.phone = "Confira o DDD e o número informado.";
    }
    if (step === 2) {
      if (!state.draft.businessName.trim())
        errors.businessName = "Dê um nome ao seu negócio demonstrativo.";
      if (!state.segmentChosen)
        errors.segment = "Escolha uma especialidade ou descreva outra atividade.";
      if (!state.draft.offers.length)
        errors.offers = "Escolha produtos, serviços ou as duas opções.";
    }
    return errors;
  }
  function validate(step = state.step, focus = true) {
    Object.keys(state.errors).forEach(clearError);
    state.errors = {};
    Object.entries(errorsFor(step)).forEach(([id, message]) => setError(id, message));
    if (state.errors.segment && $("activitySearch")) {
      $("activitySearch").setAttribute("aria-invalid", "true");
      $("activitySearch").setAttribute("aria-describedby", "segmentFeedback");
    }
    const error = Object.keys(state.errors)[0];
    if (error && focus) {
      const target =
        error === "segment"
          ? $("activitySearch")
          : error === "offers"
            ? document.querySelector('input[name="offers"]')
            : $(error);
      target?.focus();
      target?.scrollIntoView({ block: "center", behavior: "instant" });
    }
    return !error;
  }
  async function requestStep(step) {
    if (state.busy) return;
    if (step > state.step || step === 6) {
      const invalid = [1, 2].find(
        (required) => required < step && Object.keys(errorsFor(required)).length,
      );
      if (invalid) {
        state.done = false;
        state.draft.completed = false;
        state.returnTo = step === 6 ? 6 : null;
        if (invalid !== state.step) await go(invalid);
        validate(invalid);
        return;
      }
    }
    if (state.done) {
      state.done = false;
      state.draft.completed = false;
    }
    await go(step);
  }
  async function go(step) {
    if (state.busy || step === state.step) return;
    state.busy = true;
    $("nextButton").disabled = true;
    $("resetPreview").disabled = true;
    $("stage").inert = true;
    const direction = step > state.step ? 1 : -1;
    if (!reduced())
      await $("stage").animate(
        [
          { opacity: 1, transform: "none" },
          { opacity: 0, transform: `translateX(${-direction * 8}px)` },
        ],
        { duration: 160, easing: "ease-in" },
      ).finished;
    state.step = step;
    state.maxVisited = Math.max(state.maxVisited, step);
    render();
    $("stage").inert = false;
    window.scrollTo({ top: 0, behavior: "instant" });
    $("stageTitle").focus({ preventScroll: true });
    if (!reduced())
      await $("stage").animate(
        [
          { opacity: 0, transform: `translateX(${direction * 8}px)` },
          { opacity: 1, transform: "none" },
        ],
        { duration: 180, easing: "ease-out" },
      ).finished;
    state.busy = false;
    $("nextButton").disabled = false;
    $("resetPreview").disabled = false;
  }
  function next() {
    if (state.busy || state.done || !validate()) return;
    for (const [id, key] of [
      ["personName", "name"],
      ["email", "email"],
      ["phone", "phone"],
      ["instagram", "instagram"],
    ]) {
      if ($(id)) state.contact[key] = $(id).value.trim();
    }
    state.draft = profile();
    Object.keys(state.contact).forEach((key) => {
      state.contact[key] = state.contact[key].trim();
    });
    if (state.step === 6) {
      const invalid = [1, 2].find((required) => Object.keys(errorsFor(required)).length);
      if (invalid) {
        requestStep(6);
        return;
      }
      state.done = true;
      state.draft.completed = true;
      render();
      $("stageTitle").focus();
      announce("Demonstração concluída. Nenhuma informação foi salva.");
      return;
    }
    const target = state.returnTo || state.step + 1;
    state.returnTo = null;
    requestStep(target);
  }
  function chooseSegment(id) {
    const firstChoice = !state.segmentChosen;
    const changed = state.draft.segment !== id;
    state.segmentChosen = true;
    state.draft.segment = id;
    state.family = families.find((f) => f.groups.includes(model.segments[id].family))?.id || null;
    if ((firstChoice || changed) && !state.offersTouched && state.maxVisited < 3)
      state.draft.offers = [...model.segments[id].offers];
    state.draft = profile();
    state.dirty = true;
    document.querySelectorAll('input[name="offers"]').forEach((input) => {
      input.checked = state.draft.offers.includes(input.value);
    });
    clearError("segment");
    clearError("activitySearch");
    clearError("offers");
    picker();
    announce(
      `${model.segments[id].label} selecionado. Confira suas opções de produtos e serviços.`,
    );
  }
  function addCustom(kind) {
    const input = $(kind + "Custom"),
      value = input.value.trim();
    if (!value) {
      setError(kind + "Custom", "Escreva uma opção antes de adicionar.");
      input.focus();
      return;
    }
    if (
      state.draft[kind].some(
        (item) => item.toLocaleLowerCase("pt-BR") === value.toLocaleLowerCase("pt-BR"),
      )
    ) {
      setError(kind + "Custom", "Essa opção já está selecionada.");
      input.focus();
      return;
    }
    if (state.draft[kind].length >= 30) {
      setError(kind + "Custom", "Use até 30 opções neste exemplo.");
      input.focus();
      return;
    }
    state.draft[kind].push(value);
    const segment = model.segments[state.draft.segment];
    $(kind + "Choices").innerHTML = chips(kind, [
      ...new Set([
        ...(kind === "services" ? segment.services : segment.products),
        ...state.draft[kind],
      ]),
    ]);
    $(kind + "Count").textContent =
      `${state.draft[kind].length} ${state.draft[kind].length === 1 ? "selecionado" : "selecionados"}`;
    input.value = "";
    clearError(kind + "Custom");
    input.focus();
    state.dirty = true;
    announce(`${value} adicionado às sugestões deste exemplo.`);
  }
  $("stepForm").addEventListener("submit", (event) => {
    event.preventDefault();
    next();
  });
  $("backButton").addEventListener("click", () => {
    state.returnTo = null;
    go(state.step - 1);
  });
  $("stepList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-step]");
    if (!button || button.disabled || state.busy) return;
    const step = Number(button.dataset.step);
    if (step > state.step && !validate()) return;
    state.returnTo = null;
    requestStep(step);
  });
  $("stage").addEventListener("click", (event) => {
    if (state.busy) return;
    const family = event.target.closest("[data-family]");
    if (family) {
      state.family = family.dataset.family;
      state.search = "";
      $("activitySearch").value = "";
      picker();
      specialtyAnimation?.cancel();
      if (!reduced()) {
        specialtyAnimation = $("specialties").animate(
          [
            { opacity: 0.65, transform: "translateY(4px)" },
            { opacity: 1, transform: "none" },
          ],
          { duration: 180, easing: "ease-out" },
        );
      }
      announce("Especialidades de " + families.find((f) => f.id === state.family).title);
      return;
    }
    const edit = event.target.closest("[data-edit]");
    if (edit) {
      state.returnTo = 6;
      go(Number(edit.dataset.edit));
      return;
    }
    const add = event.target.closest("[data-add]");
    if (add) {
      addCustom(add.dataset.add);
      return;
    }
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (action === "example") {
      Object.assign(state.contact, { name: "Ana de teste", email: "ana@example.com", phone: "" });
      state.dirty = true;
      render();
      $("personName").focus();
      announce("Exemplo fictício preenchido. Nenhuma conta criada.");
    }
    if (action === "other") {
      state.search = "";
      $("activitySearch").value = "";
      chooseSegment("other");
      $("activity").focus();
    }
    if (action === "editOffers") {
      state.returnTo = 3;
      go(2);
    }
    if (action === "skip") {
      const target = state.returnTo || state.step + 1;
      state.returnTo = null;
      requestStep(target);
    }
    if (action === "review") {
      state.done = false;
      state.draft.completed = false;
      render();
      $("stageTitle").focus();
    }
  });
  $("stage").addEventListener("input", (event) => {
    const input = event.target;
    const map = {
      personName: "name",
      email: "email",
      phone: "phone",
      city: "city",
      instagram: "instagram",
      cnpj: "cnpj",
    };
    if (map[input.id]) state.contact[map[input.id]] = input.value;
    if (input.id === "businessName") state.draft.businessName = input.value;
    if (input.id === "activity") state.draft.activity = input.value;
    if (input.id === "activitySearch") {
      state.search = input.value;
      picker();
      clearError("segment");
    }
    clearError(input.id);
    state.dirty = true;
  });
  $("stage").addEventListener("change", (event) => {
    const input = event.target;
    if (input.id === "allActivities") {
      state.search = "";
      $("activitySearch").value = "";
      chooseSegment(input.value);
      if (input.value === "other") $("activity").focus();
    }
    if (input.name === "segment") {
      chooseSegment(input.value);
      document
        .querySelector(`input[name="segment"][value="${input.value}"]`)
        ?.focus({ preventScroll: true });
    }
    if (["offers", "services", "productCategories", "modules", "channels"].includes(input.name)) {
      const values = [...document.querySelectorAll(`input[name="${input.name}"]:checked`)].map(
        (node) => node.value,
      );
      if (["services", "productCategories"].includes(input.name) && values.length > 30) {
        input.checked = false;
        announce("Use até 30 opções neste exemplo. Nenhuma seleção anterior foi removida.");
        return;
      }
      if (input.name === "channels") state.channels = values;
      else state.draft[input.name] = values;
      if (input.name === "offers") {
        state.offersTouched = true;
        state.draft = profile();
        clearError("offers");
      }
      if (input.name === "modules") {
        state.toolsTouched = true;
        updateSpace();
      }
      if (["services", "productCategories"].includes(input.name))
        $(input.name + "Count").textContent =
          `${values.length} ${values.length === 1 ? "selecionado" : "selecionados"}`;
    }
    if (input.name === "capabilities") state.draft.capabilities[input.value] = input.checked;
    if (input.name === "priority") state.priority = input.value;
    state.dirty = true;
  });
  $("stage").addEventListener("keydown", (event) => {
    if (
      event.key === "Enter" &&
      ["servicesCustom", "productCategoriesCustom"].includes(event.target.id)
    ) {
      event.preventDefault();
      addCustom(event.target.id.replace("Custom", ""));
    }
  });
  $("stage").addEventListener("focusout", (event) => {
    const id = event.target.id;
    if (id === "phone" || id === "instagram") state.contact[id] = event.target.value;
    if (!["personName", "email", "phone", "businessName"].includes(id)) return;
    const value = event.target.value.trim();
    if (!value) return;
    const feedback = $(id + "Feedback");
    if (!feedback) return;
    const invalid =
      id === "email"
        ? !event.target.validity.valid
        : id === "phone"
          ? !SocialMEIContacts.phone(value, true).valid
          : false;
    if (invalid)
      setError(id, id === "email" ? "Confira o formato do e-mail." : "Confira o DDD e o número.");
    else {
      clearError(id);
      feedback.textContent = "Tudo certo para este exemplo.";
      feedback.classList.add("is-valid");
    }
  });
  const setTheme = (theme) => {
    document.documentElement.dataset.previewTheme = theme;
    $("themeToggle").setAttribute(
      "aria-label",
      theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro",
    );
    $("themeToggle").innerHTML = icon(theme === "dark" ? "sun" : "moon");
  };
  setTheme(matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  $("themeToggle").addEventListener("click", () =>
    setTheme(document.documentElement.dataset.previewTheme === "dark" ? "light" : "dark"),
  );
  $("resetPreview").addEventListener("click", (event) => {
    lastResetTrigger = event.currentTarget;
    $("resetDialog").showModal();
  });
  $("cancelReset").addEventListener("click", () => $("resetDialog").close());
  $("confirmReset").addEventListener("click", () => {
    $("resetDialog").close();
    state = initial();
    render();
    window.scrollTo(0, 0);
    $("stageTitle").focus();
    announce("Demonstração reiniciada. As respostas anteriores foram apagadas.");
  });
  $("resetDialog").addEventListener("close", () => {
    if (state.dirty) lastResetTrigger?.focus();
  });
  addEventListener("beforeunload", (event) => {
    if (state.dirty && !state.done) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  window.SocialMEIOnboardingPreview = Object.freeze({
    snapshot: () =>
      structuredClone({
        profile: profile(),
        contact: state.contact,
        channels: state.channels,
        priority: state.priority,
        step: state.step,
        done: state.done,
      }),
  });
  render();
})();
