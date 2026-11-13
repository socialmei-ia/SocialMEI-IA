/* Visitor booking: opaque references stay in memory and never enter browser storage. */
(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("booking-form"),
    content = $("step-content"),
    next = $("next"),
    back = $("back");
  const steps = ["service", "resource", "date", "slot", "contact", "code", "review"];
  const labels = {
    service: ["Escolha o serviço", "Consulte os serviços publicados pelo negócio."],
    resource: ["Escolha quem vai atender", "Selecione o profissional ou a equipe."],
    date: ["Escolha uma data", "Os horários seguem o fuso do negócio."],
    slot: ["Escolha um horário", "A disponibilidade será conferida novamente ao confirmar."],
    contact: ["Como podemos encontrar você?", "Enviaremos um código para verificar seu e-mail."],
    code: [
      "Confira seu e-mail",
      "Informe o código de seis dígitos recebido. Confira também o spam.",
    ],
    review: [
      "Confira seu agendamento",
      "Seu e-mail foi verificado. Confirme os detalhes antes de reservar.",
    ],
    done: ["Agendamento confirmado", "Sua reserva foi registrada pelo negócio."],
    completed: ["Atendimento concluído", "O negócio marcou este atendimento como concluído."],
    cancelled: [
      "Agendamento cancelado",
      "Esta reserva foi cancelada. Entre em contato com o negócio para consultar um novo horário.",
    ],
    unavailable: [
      "Agendamento indisponível",
      "Entre em contato com o negócio para consultar o atendimento.",
    ],
  };
  let state,
    generation = 0,
    controller;
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  const reference = (value) =>
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 16384 &&
    !/[\u0000-\u001f]/.test(value);
  const text = (value) => typeof value === "string" && value.length > 0 && value.length <= 160;
  function money(value) {
    if (!/^\d{1,12}(?:\.\d{1,2})?$/.test(String(value))) throw Error("invalid_response");
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
      Number(value),
    );
  }
  function validDay(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const day = new Date(value + "T12:00:00Z");
    return Number.isFinite(day.getTime()) && day.toISOString().slice(0, 10) === value;
  }
  function at(value) {
    if (
      typeof value !== "string" ||
      !/(Z|[+-]\d\d:\d\d)$/.test(value) ||
      !Number.isFinite(Date.parse(value))
    )
      throw Error("invalid_response");
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: state.business.timezone,
    }).format(new Date(value));
  }
  function message(value) {
    $("feedback").textContent = value || "";
    $("feedback").hidden = !value;
  }
  function busy(value) {
    state.busy = value;
    form.setAttribute("aria-busy", String(value));
    form.querySelectorAll("button,input").forEach((node) => {
      node.disabled = value;
    });
    if (!value)
      next.disabled =
        !steps.includes(state.step) ||
        (state.step === "slot" && !state.slots.length) ||
        (state.step === "resource" && !state.resources.length);
  }
  async function request(path, body) {
    const mine = generation;
    controller?.abort();
    controller = new AbortController();
    let result;
    try {
      result = await fetch(state.base + path, {
        method: body === undefined ? "GET" : "POST",
        credentials: "omit",
        cache: "no-store",
        headers:
          body === undefined
            ? { Accept: "application/json" }
            : { Accept: "application/json", "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (error) {
      if (mine !== generation) throw Object.assign(Error("stale"), { stale: true });
      throw Object.assign(Error("network"), { status: 0 });
    }
    if (mine !== generation) throw Object.assign(Error("stale"), { stale: true });
    if (!result.ok) throw Object.assign(Error("request_failed"), { status: result.status });
    let data;
    try {
      data = await result.json();
    } catch {
      throw Error("invalid_response");
    }
    if (mine !== generation) throw Object.assign(Error("stale"), { stale: true });
    return data;
  }
  function summary() {
    const list = $("summary");
    list.replaceChildren();
    const add = (label, value) => {
      if (value) list.append(element("dt", label), element("dd", value));
    };
    add("Serviço", state.service?.name);
    if (state.service)
      add(
        "Duração e valor",
        `${state.service.duration_minutes} min · ${money(state.service.price)}`,
      );
    add("Profissional ou equipe", state.resource?.name);
    if (state.slot) add("Dia e horário", at(state.slot.scheduled_for));
  }
  function field(label, id, type, value = "") {
    const wrapper = element("label", label),
      input = element("input");
    input.id = id;
    input.type = type;
    input.required = true;
    input.value = value;
    wrapper.append(input);
    content.append(wrapper);
    return input;
  }
  function choices(items, selected, caption, detail) {
    const group = element("fieldset");
    group.append(element("legend", caption));
    items.forEach((item, index) => {
      const label = element("label"),
        input = element("input"),
        words = element("span");
      label.className = "choice";
      input.type = "radio";
      input.name = "selection";
      input.value = String(index);
      input.required = true;
      input.checked = item === selected;
      words.append(element("strong", item.name || at(item.scheduled_for)));
      if (detail) words.append(element("small", detail(item)));
      label.append(input, words);
      group.append(label);
    });
    content.append(group);
  }
  function render(focus = true) {
    content.replaceChildren();
    message("");
    const [title, description] = labels[state.step] || labels.unavailable;
    $("step-title").textContent = title;
    $("step-description").textContent = description;
    $("progress").textContent = steps.includes(state.step)
      ? `Etapa ${steps.indexOf(state.step) + 1} de ${steps.length}`
      : "";
    next.hidden = !steps.includes(state.step);
    back.hidden = !steps.includes(state.step) || state.step === "service" || state.uncertain;
    next.textContent =
      {
        date: "Consultar horários",
        contact: "Enviar código",
        code: "Verificar e-mail",
        review: state.uncertain ? "Verificar confirmação" : "Confirmar agendamento",
      }[state.step] || "Continuar";
    if (state.step === "service")
      choices(
        state.business.services,
        state.service,
        "Serviços disponíveis",
        (item) => `${item.duration_minutes} min · ${money(item.price)}`,
      );
    if (state.step === "resource")
      choices(state.resources, state.resource, "Profissionais e equipes disponíveis");
    if (state.step === "date") {
      const input = field("Data do atendimento", "booking-date", "date", state.day);
      input.min = state.business.server_date;
      const end = new Date(state.business.server_date + "T12:00:00Z");
      end.setUTCDate(end.getUTCDate() + state.business.horizon_days);
      input.max = end.toISOString().slice(0, 10);
    }
    if (state.step === "slot") {
      if (state.slots.length) choices(state.slots, state.slot, "Horários disponíveis");
      else {
        const empty = element(
          "p",
          "Não há horários livres nessa data. Volte para escolher outro dia.",
        );
        empty.className = "empty-state";
        content.append(empty);
      }
      if (state.hasMore) {
        const more = element("button", "Mais horários");
        more.id = "more";
        more.type = "button";
        more.className = "secondary";
        more.addEventListener("click", () => act(() => loadSlots(state.page + 1)));
        content.append(more);
      }
    }
    if (state.step === "contact") {
      const name = field("Seu nome", "booking-name", "text", state.name);
      name.maxLength = 160;
      name.autocomplete = "name";
      name.addEventListener("input", () => {
        state.name = name.value;
      });
      const email = field("Seu e-mail", "booking-email", "email", state.email);
      email.maxLength = 255;
      email.autocomplete = "email";
      email.addEventListener("input", () => {
        state.email = email.value;
      });
    }
    if (state.step === "code") {
      const input = field("Código recebido por e-mail", "booking-code", "text");
      input.inputMode = "numeric";
      input.autocomplete = "one-time-code";
      input.minLength = input.maxLength = 6;
      input.pattern = "[0-9]{6}";
    }
    if (state.step === "review") {
      const note = element("p", "A reserva só será concluída após a verificação final do negócio.");
      note.className = "review-note";
      content.append(note);
      content.append(element("p", "E-mail verificado: " + state.email));
      if (state.uncertain)
        message(
          "Não foi possível confirmar o resultado. Verifique a mesma solicitação antes de escolher outro horário.",
        );
    }
    if (["done", "completed", "cancelled"].includes(state.step)) {
      if (state.step !== "done") content.append(element("p", labels[state.step][1]));
      $("step-description").textContent =
        `${state.receipt.service_name} · ${at(state.receipt.scheduled_for)}`;
      content.append(
        element("p", `${state.receipt.duration_minutes} min · ${money(state.receipt.price)}`),
      );
      state.challenge = state.proof = "";
      state.name = state.email = "";
    }
    summary();
    busy(false);
    if (focus) $("step-title").focus();
  }
  function chosen(items) {
    const selected = content.querySelector('input[name="selection"]:checked');
    if (!selected || !items[Number(selected.value)]) throw Error("selection");
    return items[Number(selected.value)];
  }
  function validateSlot(item) {
    if (
      !reference(item.offer) ||
      !text(item.service_name) ||
      !text(item.resource_name) ||
      !Number.isInteger(item.duration_minutes) ||
      item.duration_minutes < 1 ||
      item.duration_minutes > 1440
    )
      throw Error("invalid_response");
    at(item.scheduled_for);
    at(item.ends_at);
    money(item.price);
    return item;
  }
  async function loadSlots(page = 0) {
    const data = await request("/slots", {
      service: state.service.reference,
      resource: state.resource.reference,
      day: state.day,
      page,
    });
    if (
      !Array.isArray(data.items) ||
      data.items.length > 100 ||
      typeof data.has_more !== "boolean" ||
      data.timezone !== state.business.timezone
    )
      throw Error("invalid_response");
    const items = data.items.map(validateSlot);
    state.slots = page ? [...state.slots, ...items] : items;
    state.page = page;
    state.hasMore = data.has_more;
    state.step = "slot";
    render();
  }
  async function submit() {
    if (state.step === "service") {
      state.service = chosen(state.business.services);
      state.slot = state.resource = null;
      const data = await request("/resources", { service: state.service.reference });
      if (
        !Array.isArray(data.items) ||
        data.items.length > 100 ||
        data.items.some((item) => !reference(item.reference) || !text(item.name))
      )
        throw Error("invalid_response");
      state.resources = data.items;
      state.step = "resource";
      if (!state.resources.length) {
        render();
        message(
          "Não há profissionais disponíveis para esse serviço. Entre em contato com o negócio.",
        );
        return;
      }
    } else if (state.step === "resource") {
      state.resource = chosen(state.resources);
      state.step = "date";
    } else if (state.step === "date") {
      state.day = $("booking-date").value;
      state.slot = null;
      state.challenge = state.proof = "";
      await loadSlots();
      return;
    } else if (state.step === "slot") {
      state.slot = chosen(state.slots);
      state.challenge = state.proof = "";
      state.step = "contact";
    } else if (state.step === "contact") {
      const data = await request("/verification/request", {
        offer: state.slot.offer,
        name: state.name.trim(),
        email: state.email.trim(),
      });
      if (!reference(data.challenge)) throw Error("invalid_response");
      state.challenge = data.challenge;
      state.step = "code";
    } else if (state.step === "code") {
      const data = await request("/verification/confirm", {
        challenge: state.challenge,
        code: $("booking-code").value,
      });
      if (!reference(data.proof)) throw Error("invalid_response");
      state.proof = data.proof;
      state.step = "review";
    } else if (state.step === "review") {
      const data = await request("/confirm", {
        offer: state.slot.offer,
        proof: state.proof,
        confirmed: true,
      });
      if (
        !["scheduled", "completed", "cancelled"].includes(data.status) ||
        !reference(data.reference) ||
        !text(data.service_name) ||
        !Number.isInteger(data.duration_minutes) ||
        data.duration_minutes < 1 ||
        data.duration_minutes > 1440
      )
        throw Error("invalid_receipt");
      at(data.scheduled_for);
      money(data.price);
      state.receipt = data;
      state.uncertain = false;
      state.step = data.status === "scheduled" ? "done" : data.status;
    }
    render();
  }
  async function act(action) {
    if (!state || state.busy) return;
    const mine = generation,
      confirming = state.step === "review";
    busy(true);
    message("");
    try {
      await action();
    } catch (error) {
      if (mine !== generation || error.stale) return;
      if (confirming && (error.status === 0 || error.status >= 500 || !error.status)) {
        state.uncertain = true;
        render();
      } else if (error.status === 409) {
        await boot("O horário ou as condições mudaram. Consulte as opções novamente.");
      } else {
        const value =
          error.status === 429
            ? "Muitas tentativas. Aguarde alguns minutos antes de tentar novamente."
            : error.status === 403
              ? "Não foi possível validar esta solicitação. Reabra o link do negócio."
              : [404, 503].includes(error.status)
                ? "O agendamento está indisponível. Entre em contato com o negócio."
                : error.status === 422 || error.status === 400
                  ? "Confira os dados informados e tente novamente."
                  : "Não foi possível concluir a consulta. Tente novamente.";
        message(value);
      }
    } finally {
      if (mine === generation) busy(false);
    }
  }
  async function boot(notice = "") {
    controller?.abort();
    const mine = ++generation;
    const slug = new URLSearchParams(location.search).get("negocio") || "";
    state = {
      base: "/api/v1/public/booking/" + encodeURIComponent(slug),
      business: null,
      step: "unavailable",
      busy: false,
      resources: [],
      slots: [],
      service: null,
      resource: null,
      slot: null,
      day: "",
      page: 0,
      hasMore: false,
      name: "",
      email: "",
      challenge: "",
      proof: "",
      uncertain: false,
    };
    $("business-name").textContent = "Seu próximo atendimento.";
    content.replaceChildren();
    $("summary").replaceChildren();
    message("");
    next.hidden = back.hidden = true;
    $("progress").textContent = "";
    $("step-title").textContent = "Consultando o negócio…";
    $("step-description").textContent = "";
    if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(slug)) {
      render(false);
      return;
    }
    busy(true);
    try {
      const data = await request("");
      if (
        !text(data.name) ||
        !text(data.timezone) ||
        !validDay(data.server_date) ||
        !Number.isInteger(data.horizon_days) ||
        data.horizon_days < 1 ||
        data.horizon_days > 60 ||
        !Array.isArray(data.services) ||
        data.services.length > 100
      )
        throw Error("invalid_response");
      new Intl.DateTimeFormat("pt-BR", { timeZone: data.timezone }).format(new Date());
      data.services.forEach((item) => {
        if (
          !reference(item.reference) ||
          !text(item.name) ||
          !Number.isInteger(item.duration_minutes) ||
          item.duration_minutes < 1 ||
          item.duration_minutes > 1440
        )
          throw Error("invalid_response");
        money(item.price);
      });
      state.business = data;
      state.step = data.services.length ? "service" : "unavailable";
      $("business-name").textContent = data.name;
      document.title = `Agendamento — ${data.name}`;
      render(false);
      if (notice) message(notice);
      else if (!data.services.length)
        message("Não há serviços publicados para agendamento. Entre em contato com o negócio.");
    } catch (error) {
      if (mine === generation && !error.stale) {
        state.step = "unavailable";
        render(false);
      }
    } finally {
      if (mine === generation) busy(false);
    }
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (form.reportValidity()) act(submit);
  });
  back.addEventListener("click", () => {
    if (state.busy || state.uncertain) return;
    state.step =
      {
        resource: "service",
        date: "resource",
        slot: "date",
        contact: "slot",
        code: "contact",
        review: "contact",
      }[state.step] || "service";
    state.challenge = state.proof = "";
    render();
  });
  const theme = $("theme");
  function setTheme(dark) {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    theme.setAttribute("aria-pressed", String(dark));
    theme.textContent = dark ? "Tema claro" : "Tema escuro";
  }
  setTheme(matchMedia("(prefers-color-scheme: dark)").matches);
  theme.addEventListener("click", () =>
    setTheme(document.documentElement.dataset.theme !== "dark"),
  );
  addEventListener("popstate", () => boot());
  boot();
})();
