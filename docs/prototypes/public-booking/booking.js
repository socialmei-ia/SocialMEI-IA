"use strict";

(() => {
  const businesses = {
    bella: {
      name: "Bella Store",
      services: [
        { id: "style", name: "Consultoria de estilo", duration: 30, price: 80 },
        { id: "fitting", name: "Atendimento de provador", duration: 45, price: 60 },
      ],
      resources: ["Consultora Ana", "Consultora Marina"],
    },
    brilho: {
      name: "Brilho Limpeza",
      services: [
        { id: "assessment", name: "Avaliação de limpeza", duration: 30, price: 50 },
        { id: "cleaning", name: "Limpeza de estofado", duration: 90, price: 180 },
      ],
      resources: ["Equipe Manhã", "Equipe Tarde"],
    },
  };
  const titles = [
    "Escolha o serviço",
    "Quem vai atender você?",
    "Escolha o dia e o horário",
    "Como podemos chamar você?",
    "Confira sua solicitação",
    "Simulação concluída",
  ];
  const descriptions = [
    "Valores e duração deste exemplo.",
    "Escolha um profissional ou uma equipe.",
    "Horários no fuso de Fortaleza (UTC−3).",
    "Use dados fictícios nesta demonstração.",
    "Confira os detalhes antes de continuar.",
    "Nenhuma reserva foi criada e nenhum dado foi enviado.",
  ];
  const $ = (id) => document.getElementById(id);
  let state;
  let loadingTimer;
  const money = (value) => value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const service = () =>
    businesses[state.business].services.find((item) => item.id === state.service);
  const dateLabel = () =>
    state.date
      ? new Date(state.date + "T12:00:00-03:00").toLocaleDateString("pt-BR")
      : "A escolher";
  function element(tag, value, className) {
    const node = document.createElement(tag);
    if (value) node.textContent = value;
    if (className) node.className = className;
    return node;
  }
  function reset() {
    clearTimeout(loadingTimer);
    state = {
      business: $("business").value,
      scenario: $("scenario").value,
      step: 0,
      service: "",
      resource: "",
      date: "",
      time: "",
      name: "",
      contact: "",
      conflictHandled: false,
      unavailable: "",
    };
    render();
  }
  function summary(target) {
    target.replaceChildren();
    const chosen = service();
    for (const [label, value] of [
      ["Serviço", chosen?.name || "A escolher"],
      [
        "Duração e valor",
        chosen ? `${chosen.duration} min · ${money(chosen.price)}` : "A escolher",
      ],
      ["Profissional ou equipe", state.resource || "A escolher"],
      ["Dia e horário", state.time ? `${dateLabel()} às ${state.time}` : "A escolher"],
    ]) {
      target.append(element("dt", label), element("dd", value));
    }
  }
  function choices(values, selected, name) {
    const fieldset = element("fieldset");
    fieldset.append(element("legend", name));
    values.forEach(({ value, title, description }) => {
      const label = element("label", "", "choice");
      const input = document.createElement("input");
      Object.assign(input, {
        type: "radio",
        name: "selection",
        value,
        checked: value === selected,
        required: true,
      });
      const copy = element("span");
      copy.append(element("strong", title));
      if (description) copy.append(element("small", description));
      label.append(input, copy);
      fieldset.append(label);
    });
    return fieldset;
  }
  function inputField(title, id, type, value, autocomplete) {
    const label = element("label", title);
    const input = document.createElement("input");
    Object.assign(input, { id, type, value, required: true, autocomplete });
    label.append(input);
    return label;
  }
  function availability(content) {
    const scenario = state.scenario;
    if (scenario === "empty" || scenario === "error") {
      const box = element("div", "", "empty-state");
      box.append(
        element(
          "strong",
          scenario === "empty"
            ? "Sem horários neste período"
            : "Não foi possível consultar os horários",
        ),
        element(
          "p",
          scenario === "empty"
            ? "Tente outro período ou fale com o negócio para combinar um horário."
            : "Sua escolha está preservada. Tente consultar novamente.",
        ),
      );
      const retry = element(
        "button",
        scenario === "empty" ? "Explorar outro período" : "Tentar novamente",
        "secondary",
      );
      retry.type = "button";
      retry.addEventListener("click", () => {
        box.replaceChildren(element("p", "Consultando horários de exemplo…"));
        $("next").disabled = true;
        loadingTimer = setTimeout(() => {
          state.scenario = "normal";
          $("scenario").value = "normal";
          render();
        }, 250);
      });
      box.append(retry);
      content.append(box);
      $("next").disabled = true;
      return;
    }
    const day = inputField("Dia", "booking-date", "date", state.date, "off");
    const dayInput = day.querySelector("input");
    const tomorrow = new Date();
    tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
    dayInput.min = tomorrow.toISOString().slice(0, 10);
    if (!state.date) {
      state.date = dayInput.min;
      dayInput.value = state.date;
    }
    const latest = new Date(tomorrow);
    latest.setUTCDate(latest.getUTCDate() + 29);
    dayInput.max = latest.toISOString().slice(0, 10);
    dayInput.addEventListener("change", () => {
      state.date = dayInput.value;
      state.time = "";
      render(false);
    });
    content.append(
      day,
      choices(
        ["09:00", "10:30", "14:00"]
          .filter((time) => time !== state.unavailable)
          .map((time) => ({ value: time, title: time })),
        state.time,
        "Horários de exemplo",
      ),
    );
  }
  function render(focus = true) {
    const content = $("step-content");
    content.replaceChildren();
    $("feedback").hidden = true;
    $("progress").textContent =
      state.step < 5 ? `Etapa ${state.step + 1} de 5` : "Fim da demonstração";
    $("step-title").textContent = titles[state.step];
    $("step-description").textContent = descriptions[state.step];
    $("business-name").textContent = businesses[state.business].name;
    $("back").hidden = state.step === 0 || state.step === 5;
    $("next").disabled = false;
    $("next").textContent =
      state.step === 4 ? "Simular solicitação" : state.step === 5 ? "Recomeçar" : "Continuar";
    if (state.step === 0)
      content.append(
        choices(
          businesses[state.business].services.map((item) => ({
            value: item.id,
            title: item.name,
            description: `${item.duration} minutos · ${money(item.price)}`,
          })),
          state.service,
          "Serviços",
        ),
      );
    if (state.step === 1)
      content.append(
        choices(
          businesses[state.business].resources.map((name) => ({ value: name, title: name })),
          state.resource,
          "Profissionais ou equipes",
        ),
      );
    if (state.step === 2) availability(content);
    if (state.step === 3) {
      const name = inputField("Seu nome de exemplo", "booking-name", "text", state.name, "off");
      name.querySelector("input").maxLength = 80;
      const contact = inputField(
        "E-mail de exemplo",
        "booking-contact",
        "email",
        state.contact,
        "off",
      );
      contact.querySelector("input").maxLength = 120;
      content.append(
        name,
        contact,
        element(
          "p",
          "Exemplo: Pessoa Teste e pessoa@example.test. Não informe dados reais.",
          "privacy-note",
        ),
      );
    }
    if (state.step === 4) {
      const details = element("dl");
      summary(details);
      details.append(
        element("dt", "Solicitante de exemplo"),
        element("dd", state.name),
        element("dt", "Contato de exemplo"),
        element("dd", state.contact),
      );
      content.append(
        details,
        element(
          "p",
          "Em uma versão publicada, o horário precisará ser verificado novamente antes da confirmação. Nesta prévia, você apenas simula a solicitação.",
          "review-note",
        ),
      );
    }
    if (state.step === 5)
      content.append(
        element(
          "p",
          "Você percorreu o fluxo de agendamento. Para um atendimento real, entre em contato com o negócio.",
          "empty-state",
        ),
      );
    summary($("summary"));
    if (focus) $("step-title").focus({ preventScroll: true });
  }
  $("booking-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const chosen = document.querySelector('input[name="selection"]:checked');
    if (state.step === 0) {
      state.service = chosen.value;
      state.resource = "";
      state.time = "";
    }
    if (state.step === 1) {
      state.resource = chosen.value;
      state.time = "";
    }
    if (state.step === 2) {
      state.date = $("booking-date").value;
      state.time = chosen.value;
    }
    if (state.step === 3) {
      state.name = $("booking-name").value.trim();
      state.contact = $("booking-contact").value.trim();
      if (!state.name) {
        $("feedback").textContent = "Informe um nome de exemplo.";
        $("feedback").hidden = false;
        return;
      }
    }
    if (state.step === 4 && state.scenario === "occupied" && !state.conflictHandled) {
      state.conflictHandled = true;
      state.unavailable = state.time;
      state.time = "";
      state.step = 2;
      render();
      $("feedback").textContent =
        "Este horário acabou de ficar indisponível no exemplo. Escolha outro horário; nenhuma reserva foi criada.";
      $("feedback").hidden = false;
      return;
    }
    if (state.step === 5) {
      reset();
      return;
    }
    state.step += 1;
    render();
  });
  $("back").addEventListener("click", () => {
    state.step -= 1;
    render();
  });
  $("business").addEventListener("change", reset);
  $("scenario").addEventListener("change", reset);
  $("theme").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme !== "dark";
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    $("theme").setAttribute("aria-pressed", String(dark));
    $("theme").textContent = dark ? "Tema claro" : "Tema escuro";
  });
  reset();
})();
