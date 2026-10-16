"use strict";
const $ = (selector) => document.querySelector(selector);
const profiles = {
  perfume: {
    label: "Perfumaria e cosméticos",
    description: "Produtos, variações e reposição",
    products: true,
    services: false,
    stock: true,
    appointments: false,
    term: "Produtos",
    example: "Perfume de 100 ml; kits de presente",
    channel: ["physical", "whatsapp"],
  },
  grocery: {
    label: "Mercadinho",
    description: "Catálogo, estoque e vendas do dia",
    products: true,
    services: false,
    stock: true,
    appointments: false,
    term: "Produtos",
    example: "Itens de mercearia e produtos de limpeza",
    channel: ["physical", "whatsapp"],
  },
  barber: {
    label: "Barbearia",
    description: "Serviços, horários e relacionamento",
    products: false,
    services: true,
    stock: false,
    appointments: true,
    term: "Serviços",
    example: "Corte de cabelo; barba; pacote de cuidados",
    channel: ["whatsapp", "instagram"],
  },
  tailor: {
    label: "Costureira",
    description: "Serviços sob medida e encomendas",
    products: true,
    services: true,
    stock: false,
    appointments: true,
    term: "Produtos e serviços",
    example: "Ajuste de roupa; peça sob encomenda",
    channel: ["whatsapp", "physical"],
  },
  repair: {
    label: "Assistência de celulares",
    description: "Reparos, peças e acompanhamento",
    products: true,
    services: true,
    stock: true,
    appointments: false,
    term: "Produtos e serviços",
    example: "Troca de tela; acessórios; diagnóstico",
    channel: ["physical", "whatsapp"],
  },
  other: {
    label: "Outro tipo de negócio",
    description: "Ajuste produtos, serviços e recursos na próxima etapa",
    products: true,
    services: true,
    stock: false,
    appointments: false,
    term: "Produtos e serviços",
    example: "Um produto ou serviço escolhido por você",
    channel: ["physical", "whatsapp"],
  },
};
const channels = {
  physical: "Loja ou atendimento presencial",
  whatsapp: "WhatsApp",
  instagram: "Instagram",
  website: "Site ou loja virtual",
};
let step = 0,
  selectedProfile = null,
  answers = {};
const escapeHTML = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );
function choice(id, label, description, checked, type = "checkbox", name = id) {
  return `<label class="choice"><input type="${type}" id="${id}" name="${name}" value="${id}" ${checked ? "checked" : ""} /><span>${label}${description ? `<small>${description}</small>` : ""}</span></label>`;
}
function capabilities() {
  return [
    answers.products && "Produtos",
    answers.services && "Serviços",
    answers.stock && "Estoque",
    answers.appointments && "Agendamentos (planejado)",
  ].filter(Boolean);
}
function profileConfig() {
  return {
    demo: true,
    version: 1,
    businessProfile: selectedProfile,
    core: ["Clientes", "Vendas", "Financeiro", "Relatórios"],
    capabilities: {
      products: answers.products,
      services: answers.services,
      inventory: answers.stock,
      appointments: answers.appointments,
    },
    defaults: {
      catalogLabel:
        answers.products && answers.services
          ? "Produtos e serviços"
          : answers.products
            ? "Produtos"
            : "Serviços",
      channels: answers.channels,
      team: answers.team,
      serviceArea: answers.area,
    },
    integrationsEnabled: false,
  };
}
function render() {
  const profile = profiles[selectedProfile];
  $("#validation").textContent = "";
  $("#result-status").textContent = "";
  document.querySelectorAll("[data-step]").forEach((item) => {
    if (Number(item.dataset.step) === step) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  });
  $("#back").hidden = step === 0;
  $("#next").hidden = step === 2;
  $("#download").hidden = step !== 2;
  $("#restart").hidden = step !== 2;
  $("#step-title").textContent = [
    "O que descreve melhor seu negócio?",
    "Como funciona sua rotina?",
    "Esta pode ser sua organização inicial.",
  ][step];
  $("#step-copy").textContent = [
    "Escolha o exemplo mais próximo. As sugestões podem ser alteradas na próxima etapa.",
    "Ajuste as sugestões ao seu jeito de trabalhar. Nenhum canal será conectado.",
    "Confira o núcleo comum e as capacidades sugeridas. Isto ainda não configura o aplicativo real.",
  ][step];
  if (step === 0) {
    $("#step-content").innerHTML =
      `<fieldset><legend class="eyebrow">Tipo de negócio</legend><div class="choices">${Object.entries(
        profiles,
      )
        .map(([id, item]) =>
          choice(id, item.label, item.description, id === selectedProfile, "radio", "segment"),
        )
        .join("")}</div></fieldset>`;
  }
  if (step === 1) {
    $("#step-content").innerHTML =
      `<p class="badge">Sugestões para ${profile.label}</p><fieldset><legend>O que você oferece?</legend><div class="choices">${choice("products", "Produtos", "Itens vendidos pelo seu negócio", answers.products)}${choice("services", "Serviços", "Trabalhos e atendimentos", answers.services)}</div></fieldset><fieldset><legend>O que ajuda sua rotina?</legend><div class="choices">${choice("stock", "Controle de estoque", "Sugestão para produtos e materiais", answers.stock)}${choice("appointments", "Horários e agendamentos", "Capacidade futura, ainda não conectada", answers.appointments)}</div></fieldset><fieldset><legend>Por onde você atende?</legend><div class="choices">${Object.entries(
        channels,
      )
        .map(([id, label]) =>
          choice(id, label, "Seleção não conecta o canal", answers.channels.includes(id)),
        )
        .join(
          "",
        )}</div></fieldset><div class="toolbar"><label class="field"><span>Quem trabalha no negócio?</span><select id="team"><option value="solo">Só eu</option><option value="small">Equipe de 2 a 5 pessoas</option><option value="larger">Mais de 5 pessoas</option></select></label><label class="field search"><span>Área de atendimento (opcional)</span><input id="area" type="text" maxlength="100" placeholder="Ex.: meu bairro ou atendimento online" value="${escapeHTML(answers.area)}" /></label></div>`;
    $("#team").value = answers.team;
  }
  if (step === 2) {
    const config = profileConfig();
    $("#step-content").innerHTML =
      `<dl class="review-list"><dt>Perfil</dt><dd>${profile.label}</dd><dt>Catálogo</dt><dd>${config.defaults.catalogLabel}</dd><dt>Canais sugeridos</dt><dd>${answers.channels.map((id) => channels[id]).join(", ")}</dd><dt>Equipe</dt><dd>${{ solo: "Só eu", small: "2 a 5 pessoas", larger: "Mais de 5 pessoas" }[answers.team]}</dd><dt>Área</dt><dd>${escapeHTML(answers.area) || "Não informada"}</dd></dl><h3>Núcleo comum</h3><div class="preview-modules">${config.core.map((label) => `<span class="badge">${label}</span>`).join("")}</div><h3>Capacidades sugeridas</h3><div class="preview-modules">${capabilities()
        .map((label) => `<span class="badge">${label}</span>`)
        .join(
          "",
        )}</div><div class="notice"><strong>Exemplo de catálogo, sem cadastro:</strong> ${profile.example}.<br>Integrações continuam desligadas. A seleção de agendamentos é apenas planejamento.</div><details><summary>Ver configuração demonstrativa</summary><pre id="config-preview"></pre></details>`;
    $("#config-preview").textContent = JSON.stringify(config, null, 2);
    $("#config-preview").style.whiteSpace = "pre-wrap";
    $("#config-preview").style.overflowWrap = "anywhere";
  }
}
function readRoutine() {
  ["products", "services", "stock", "appointments"].forEach(
    (key) => (answers[key] = $("#" + key).checked),
  );
  answers.channels = Object.keys(channels).filter((key) => $("#" + key).checked);
  answers.team = $("#team").value;
  answers.area = $("#area").value.trim();
}
$("#wizard").addEventListener("submit", (event) => {
  event.preventDefault();
  if (step === 0) {
    if (!selectedProfile) {
      $("#validation").textContent = "Escolha um tipo de negócio para continuar.";
      document.querySelector('[name="segment"]').focus();
      return;
    }
    step = 1;
  } else if (step === 1) {
    readRoutine();
    if (!answers.products && !answers.services) {
      $("#validation").textContent = "Selecione produtos, serviços ou ambos.";
      $("#products").focus();
      return;
    }
    if (!answers.channels.length) {
      $("#validation").textContent = "Selecione pelo menos um canal de atendimento.";
      $("#physical").focus();
      return;
    }
    step = 2;
  }
  render();
  $("#step-title").focus();
});
$("#step-content").addEventListener("change", (event) => {
  if (event.target.name !== "segment") return;
  const next = event.target.value;
  if (next === selectedProfile) return;
  selectedProfile = next;
  const profile = profiles[next];
  answers = {
    products: profile.products,
    services: profile.services,
    stock: profile.stock,
    appointments: profile.appointments,
    channels: [...profile.channel],
    team: "solo",
    area: "",
  };
});
$("#back").addEventListener("click", () => {
  if (step === 1) readRoutine();
  step = Math.max(0, step - 1);
  render();
  $("#step-title").focus();
});
$("#restart").addEventListener("click", () => {
  step = 0;
  selectedProfile = null;
  answers = {};
  render();
  $("#step-title").focus();
});
$("#download").addEventListener("click", () => {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(profileConfig(), null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "socialmei-perfil-demonstrativo.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  $("#result-status").textContent =
    "Perfil demonstrativo baixado. O cadastro e o aplicativo real não foram alterados.";
});
$("#theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("#theme").setAttribute("aria-pressed", String(dark));
  $("#theme").textContent = dark ? "Tema claro" : "Tema escuro";
});
render();
