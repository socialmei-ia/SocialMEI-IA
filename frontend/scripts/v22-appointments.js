/* Service bookings supplement manual reminders; every record belongs to the server session. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIAppointments) return;
  const node = (tag, text) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const writer = () => ["owner", "admin", "member"].includes(host.identity?.papel);
  let state;
  function current() {
    if (!state || state.identity !== host.identity) {
      const from = new Date(),
        to = new Date();
      from.setDate(from.getDate() - 7);
      to.setDate(to.getDate() + 90);
      state = {
        identity: host.identity,
        scope: scope(),
        items: [],
        phase: "initial",
        busy: false,
        from: dateTime(from).slice(0, 10),
        to: dateTime(to).slice(0, 10),
      };
    }
    return state;
  }
  const live = (s) => s.identity === host.identity && s.scope === scope();
  const storageKey = (s) => "socialmei-booking-pending-v1:" + s.scope;
  async function sendPending(s, packet, raw) {
    try {
      return await host.request("/agenda/appointments", "POST", packet);
    } catch (error) {
      // A definitive validation/conflict rejection rolls back the server transaction.
      // Preserve uncertain transport failures and UUID conflicts for reconciliation.
      if (
        live(s) &&
        (error.status === 422 ||
          (error.status === 409 &&
            error.message === "Horário ocupado para este recurso. Escolha outro horário.")) &&
        localStorage.getItem(storageKey(s)) === raw
      )
        localStorage.removeItem(storageKey(s));
      throw error;
    }
  }
  const valid = (r) =>
    r &&
    typeof r.id === "string" &&
    Number.isSafeInteger(r.revision) &&
    Number.isFinite(Date.parse(r.scheduled_for)) &&
    Number.isFinite(Date.parse(r.ends_at)) &&
    ["pending", "done", "cancelled"].includes(r.status);
  function button(text, action, disabled = false) {
    const b = node("button", text);
    b.type = "button";
    b.className = "btn o";
    b.disabled = disabled;
    b.onclick = action;
    return b;
  }
  async function load(s = current()) {
    if (!live(s) || s.busy) return;
    s.phase = "loading";
    s.error = "";
    const ticket = (s.ticket = (s.ticket || 0) + 1);
    paint();
    try {
      const result = await host.request(
        `/agenda/appointments?include_cancelled=true&from_date=${encodeURIComponent(s.from)}&to_date=${encodeURIComponent(s.to)}`,
      );
      if (!live(s) || ticket !== s.ticket) return;
      if (!Array.isArray(result.items) || !result.items.every(valid))
        throw Error("Resposta de agendamentos inválida.");
      s.items = result.items;
      s.truncated = result.truncated;
      s.phase = "ready";
    } catch (e) {
      if (live(s) && ticket === s.ticket) {
        s.phase = "error";
        s.error = e.message;
      }
    }
    if (live(s)) paint();
  }
  function dateTime(value) {
    const d = new Date(value);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function instant(value) {
    const d = new Date(value);
    if (!Number.isFinite(d.getTime()) || dateTime(d) !== value)
      throw Error("Data ou horário inválido no fuso do dispositivo.");
    return d.toISOString();
  }
  function form(s, title, fields, submit, label = "Salvar") {
    if (!live(s) || !writer()) return;
    openForm(
      title,
      "Dados salvos neste negócio. Horário do dispositivo: " +
        Intl.DateTimeFormat().resolvedOptions().timeZone +
        ". Nenhuma mensagem será enviada.",
      fields,
      () => "",
      label,
    );
    const box = dlg(),
      f = box.querySelector("form"),
      feedback = node("p");
    feedback.setAttribute("role", "status");
    f.append(feedback);
    const owns = () => box.querySelector("form") === f;
    const input = (id) => f.querySelector("#f_" + id);
    let busy = false;
    f.onsubmit = async (event) => {
      event.preventDefault();
      if (busy) return;
      if (!live(s) || !writer()) {
        if (owns()) box.close();
        return;
      }
      if (!f.reportValidity()) return;
      busy = true;
      s.busy = true;
      f.querySelectorAll("button").forEach((b) => (b.disabled = true));
      try {
        await submit(input, feedback);
        if (!live(s)) return;
        if (owns()) box.close();
        s.busy = false;
        await load(s);
      } catch (e) {
        if (live(s) && owns())
          feedback.textContent = e.message || "Sem confirmação. Consulte antes de repetir.";
      } finally {
        busy = false;
        s.busy = false;
        if (owns()) f.querySelectorAll("button").forEach((b) => (b.disabled = false));
        if (live(s)) paint();
      }
    };
    const cancel = (e) => {
      if (busy && owns()) e.preventDefault();
    };
    box.addEventListener("cancel", cancel);
    box.addEventListener("close", () => box.removeEventListener("cancel", cancel), { once: true });
    return input;
  }
  async function prepare(s, task) {
    if (!live(s) || s.busy || !writer()) return;
    s.busy = true;
    paint();
    try {
      await task();
    } catch (e) {
      if (live(s)) s.error = e.message;
    } finally {
      s.busy = false;
      if (live(s)) paint();
    }
  }
  function resource(s) {
    const operationId = crypto.randomUUID();
    form(
      s,
      "Cadastrar profissional ou recurso",
      [{ id: "booking_resource", label: "Nome", req: 1 }],
      async (input) => {
        const nome = input("booking_resource").value.trim();
        if (!nome) throw Error("Informe o nome.");
        await host.request("/agenda/resources", "POST", {
          operation_id: operationId,
          nome,
        });
      },
    );
  }
  function service(s) {
    const input = form(
      s,
      "Cadastrar serviço para agendamento",
      [
        { id: "booking_service", label: "Nome do serviço", req: 1 },
        { id: "booking_duration", label: "Duração em minutos", value: "30", req: 1 },
        { id: "booking_price", label: "Preço em reais", value: "0", req: 1 },
      ],
      async (get) => {
        const duration = Number(get("booking_duration").value),
          price = Number(get("booking_price").value.replace(",", "."));
        if (
          !Number.isInteger(duration) ||
          duration < 1 ||
          duration > 1440 ||
          !Number.isFinite(price) ||
          price < 0
        )
          throw Error("Confira duração e preço.");
        await host.request("/produtos", "POST", {
          nome: get("booking_service").value.trim(),
          tipo: "Serviço",
          preco: price,
          custo: 0,
          estoque: null,
          minimo: null,
          status: "Ativo",
          duracao_minutos: duration,
        });
      },
    );
    if (input) {
      input("booking_duration").type = "number";
      input("booking_duration").min = "1";
      input("booking_duration").max = "1440";
    }
  }
  function manageResources(s) {
    prepare(s, async () => {
      const result = await host.request("/agenda/resources");
      if (!live(s)) return;
      if (!result.items?.length) throw Error("Cadastre um profissional ou recurso primeiro.");
      const input = form(
        s,
        "Configurar profissional ou recurso",
        [
          { id: "booking_resource", label: "Profissional ou recurso", type: "select", options: [] },
          { id: "booking_name", label: "Nome", req: 1 },
          {
            id: "booking_active",
            label: "Ativo para novos agendamentos",
            type: "check",
            value: true,
          },
        ],
        async (get) => {
          const item = result.items.find((row) => row.id === get("booking_resource").value);
          if (!item) throw Error("Recurso inválido. Reabra a janela.");
          await host.request("/agenda/resources/" + item.id, "PATCH", {
            expected_revision: item.revision,
            nome: get("booking_name").value.trim(),
            ativo: get("booking_active").checked,
          });
        },
      );
      if (!input) return;
      const select = input("booking_resource");
      select.replaceChildren();
      for (const row of result.items) {
        const option = node("option", row.nome + (row.ativo ? "" : " · Inativo"));
        option.value = row.id;
        select.append(option);
      }
      const fill = () => {
        const row = result.items.find((item) => item.id === select.value);
        input("booking_name").value = row.nome;
        input("booking_active").checked = row.ativo;
      };
      select.onchange = fill;
      input("booking_name").maxLength = 160;
      fill();
    });
  }
  function book(s) {
    prepare(s, async () => {
      const raw = localStorage.getItem(storageKey(s));
      if (raw) {
        const packet = JSON.parse(raw);
        if (!packet.operation_id || !packet.resource_id || !packet.servico_id || !packet.cliente_id)
          throw Error("Pedido pendente inválido. Preserve-o e solicite suporte.");
        if (!live(s)) return;
        const input = form(
          s,
          "Retomar agendamento sem confirmação",
          [],
          async () => {
            if (localStorage.getItem(storageKey(s)) !== raw)
              throw Error("O pedido pendente mudou. Reabra a janela.");
            const result = await sendPending(s, packet, raw);
            if (!valid(result) || result.id !== packet.operation_id)
              throw Error("Resposta inválida. Preserve o pedido original.");
            if (live(s) && localStorage.getItem(storageKey(s)) === raw)
              localStorage.removeItem(storageKey(s));
          },
          "Conferir pedido original",
        );
        if (input)
          dlg()
            .querySelector("form")
            .prepend(
              node(
                "p",
                "O mesmo pedido será consultado com sua identidade original; nenhum novo agendamento será duplicado.",
              ),
            );
        return;
      }
      const [clients, products, resources] = await Promise.all([
        host.request("/clientes"),
        host.request("/produtos"),
        host.request("/agenda/resources"),
      ]);
      if (!live(s)) return;
      const services = products.filter(
          (p) => p.tipo === "Serviço" && p.status === "Ativo" && p.duracao_minutos > 0,
        ),
        available = resources.items.filter((r) => r.ativo);
      if (!clients.length || !services.length || !available.length)
        throw Error(
          "Cadastre cliente, serviço com duração e profissional/recurso ativo antes de agendar.",
        );
      const input = form(
        s,
        "Novo agendamento",
        [
          { id: "booking_client", label: "Cliente", type: "select", options: [] },
          { id: "booking_service", label: "Serviço", type: "select", options: [] },
          { id: "booking_resource", label: "Profissional ou recurso", type: "select", options: [] },
          { id: "booking_start", label: "Data e horário", req: 1 },
          { id: "booking_notes", label: "Observações", type: "textarea" },
        ],
        async (get) => {
          if (localStorage.getItem(storageKey(s)))
            throw Error("Retome primeiro o pedido pendente.");
          const packet = {
            operation_id: crypto.randomUUID(),
            cliente_id: Number(get("booking_client").value),
            servico_id: Number(get("booking_service").value),
            resource_id: get("booking_resource").value,
            scheduled_for: instant(get("booking_start").value),
            notes: get("booking_notes").value.trim(),
          };
          const availability = await host.request(
            `/agenda/availability?resource_id=${encodeURIComponent(packet.resource_id)}&servico_id=${packet.servico_id}&scheduled_for=${encodeURIComponent(packet.scheduled_for)}`,
          );
          if (!live(s) || !writer()) throw Error("A sessão mudou. Reabra o formulário.");
          if (!availability.available)
            throw Error("Horário indisponível para este recurso. Escolha outro horário.");
          const pending = JSON.stringify(packet);
          localStorage.setItem(storageKey(s), pending);
          const result = await sendPending(s, packet, pending);
          if (!valid(result) || result.id !== packet.operation_id)
            throw Error("Sem confirmação. Retome o pedido original.");
          if (live(s) && localStorage.getItem(storageKey(s)) === pending)
            localStorage.removeItem(storageKey(s));
        },
        "Confirmar agendamento",
      );
      if (!input) return;
      for (const [id, items, label] of [
        ["client", clients, (r) => r.nome],
        ["service", services, (r) => `${r.nome} · ${r.duracao_minutos} min`],
        ["resource", available, (r) => r.nome],
      ]) {
        const select = input("booking_" + id);
        select.replaceChildren();
        for (const row of items) {
          const option = node("option", label(row));
          option.value = String(row.id);
          select.append(option);
        }
      }
      input("booking_start").type = "datetime-local";
      input("booking_notes").maxLength = 1000;
    });
  }
  const bookingDays = [
    "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo",
  ];
  function parseBookingHours(value, weekday) {
    const windows = [];
    for (const entry of value.split(";").map((part) => part.trim()).filter(Boolean)) {
      const match = /^(\\d{2}:\\d{2})\\s*-\\s*(\\d{2}:\\d{2})$/.exec(entry);
      if (!match || match[1] >= match[2] ||
          ![match[1], match[2]].every((clock) =>
            /^(?:[01]\\d|2[0-3]):[0-5]\\d$/.test(clock)))
        throw Error(bookingDays[weekday] + ": use 09:00-12:00;13:00-18:00.");
      windows.push({ weekday, opens: match[1], closes: match[2] });
    }
    return windows;
  }
  function configureChannelBooking(s) {
    prepare(s, async () => {
      if (!["owner", "admin"].includes(host.identity?.papel))
        throw Error("Somente a administração pode definir horários dos canais.");
      const existing = await host.request("/agenda/channel-booking");
      if (!live(s)) return;
      if (!Number.isSafeInteger(existing.revision) || !existing.policy ||
          !Array.isArray(existing.policy.hours))
        throw Error("Configuração de horários inválida. Nenhuma alteração foi feita.");
      const fields = [
        { id: "channel_booking_enabled", label: "Agendamento pelo WhatsApp e Instagram", type: "select", options: [] },
        { id: "channel_booking_timezone", label: "Fuso horário", req: 1 },
        { id: "channel_booking_step", label: "Intervalo dos horários (minutos)", req: 1 },
        { id: "channel_booking_lead", label: "Antecedência mínima (minutos)", req: 1 },
        { id: "channel_booking_horizon", label: "Dias disponíveis para marcar", req: 1 },
        ...bookingDays.map((day, i) => ({
          id: "channel_booking_day_" + i,
          label: day + " (ex.: 09:00-12:00;13:00-18:00)",
        })),
      ];
      const input = form(
        s,
        "Horários para agendamento por WhatsApp e Instagram",
        fields,
        async (get) => {
          const hours = bookingDays.flatMap((_, weekday) =>
            parseBookingHours(get("channel_booking_day_" + weekday).value, weekday));
          const policy = {
            ...existing.policy,
            enabled: get("channel_booking_enabled").value === "true",
            timezone: get("channel_booking_timezone").value.trim(),
            step_minutes: Number(get("channel_booking_step").value),
            lead_minutes: Number(get("channel_booking_lead").value),
            horizon_days: Number(get("channel_booking_horizon").value),
            hours,
          };
          if (!policy.timezone || ![policy.step_minutes, policy.lead_minutes,
                policy.horizon_days].every(Number.isInteger))
            throw Error("Confira o fuso horário e os intervalos.");
          if (policy.enabled && !hours.length)
            throw Error("Defina pelo menos um dia de atendimento antes de ativar.");
          await host.request("/agenda/channel-booking", "PUT", {
            expected_revision: existing.revision,
            policy,
          });
        },
        "Salvar horários",
      );
      if (!input) return;
      const active = input("channel_booking_enabled");
      active.replaceChildren();
      for (const [value, title] of [["false", "Desativado"], ["true", "Ativado"]]) {
        const option = node("option", title);
        option.value = value;
        active.append(option);
      }
      active.value = String(existing.policy.enabled);
      for (const [field, value] of [
        ["timezone", existing.policy.timezone],
        ["step", existing.policy.step_minutes],
        ["lead", existing.policy.lead_minutes],
        ["horizon", existing.policy.horizon_days],
      ]) input("channel_booking_" + field).value = String(value);
      for (const [field, min, max] of [
        ["step", 5, 120], ["lead", 0, 10080], ["horizon", 1, 60],
      ]) {
        const element = input("channel_booking_" + field);
        element.type = "number";
        element.min = String(min);
        element.max = String(max);
        element.step = "1";
      }
      for (let day = 0; day < bookingDays.length; day++)
        input("channel_booking_day_" + day).value = existing.policy.hours
          .filter((item) => item.weekday === day)
          .map((item) => item.opens + "-" + item.closes).join(";");
      const details = node("p",
        "Estes horários valem para os dois canais, em cada negócio separadamente. " +
        "Os clientes só confirmam reservas depois de escolher serviço, profissional e horário. " +
        "A agenda interna permanece disponível mesmo com o menu dos canais desativado.");
      details.className = "mut";
      dlg().querySelector("form")?.prepend(details);
    });
  }
  function duration(s) {
    prepare(s, async () => {
      const products = await host.request("/produtos");
      if (!live(s)) return;
      const services = products.filter((p) => p.tipo === "Serviço");
      if (!services.length) throw Error("Cadastre um serviço primeiro.");
      const input = form(
        s,
        "Configurar duração de serviço",
        [
          { id: "booking_service", label: "Serviço", type: "select", options: [] },
          { id: "booking_duration", label: "Duração em minutos", req: 1 },
        ],
        async (get) => {
          const item = services.find((p) => String(p.id) === get("booking_service").value);
          const minutes = Number(get("booking_duration").value);
          if (!item || !Number.isInteger(minutes) || minutes < 1 || minutes > 1440)
            throw Error("Informe duração entre 1 e 1440 minutos.");
          await host.request("/produtos/" + item.id, "PATCH", {
            expected_version: item.versao,
            duracao_minutos: minutes,
          });
        },
      );
      if (!input) return;
      const select = input("booking_service");
      select.replaceChildren();
      for (const service of services) {
        const option = node("option", service.nome);
        option.value = String(service.id);
        select.append(option);
      }
      const fill = () => {
        input("booking_duration").value =
          services.find((p) => String(p.id) === select.value)?.duracao_minutos || "";
      };
      select.onchange = fill;
      input("booking_duration").type = "number";
      input("booking_duration").min = "1";
      input("booking_duration").max = "1440";
      fill();
    });
  }
  function update(s, row, status) {
    const fields = status
      ? []
      : [
          {
            id: "booking_start",
            label: "Nova data e horário",
            value: dateTime(row.scheduled_for),
            req: 1,
          },
        ];
    const input = form(
      s,
      status === "cancelled"
        ? "Cancelar agendamento"
        : status === "done"
          ? "Concluir agendamento"
          : "Reagendar",
      fields,
      async (get) => {
        const payload = { expected_revision: row.revision };
        if (status) payload.status = status;
        else payload.scheduled_for = instant(get("booking_start").value);
        const saved = await host.request("/agenda/appointments/" + row.id, "PATCH", payload);
        if (!valid(saved) || saved.id !== row.id)
          throw Error("Confirmação inválida. Consulte a agenda antes de repetir.");
      },
      status === "cancelled" ? "Confirmar cancelamento" : "Confirmar",
    );
    if (input && !status) input("booking_start").type = "datetime-local";
  }
  async function history(s, row) {
    try {
      const result = await host.request("/agenda/appointments/" + row.id + "/history");
      if (!live(s)) return;
      const labels = { pending: "Agendado", done: "Concluído", cancelled: "Cancelado" };
      const lines = result.items.map(
        (r) =>
          `${new Date(r.recorded_at).toLocaleString("pt-BR")} · revisão ${r.revision}: ${labels[r.status] || r.status} · ${new Date(r.scheduled_for).toLocaleString("pt-BR")}`,
      );
      openForm(
        "Histórico do agendamento",
        "Eventos registrados neste negócio.",
        [],
        () => "",
        "Fechar",
      );
      const f = dlg().querySelector("form");
      for (const text of lines) f.append(node("p", text));
      f.onsubmit = (e) => {
        e.preventDefault();
        dlg().close();
      };
    } catch (e) {
      if (live(s)) {
        s.error = e.message;
        paint();
      }
    }
  }
  function paint() {
    const parent = document.querySelector(".sm-agenda");
    if (!parent || location.hash !== "#/agenda") return;
    const s = current(),
      section = node("section");
    section.dataset.appointments = "true";
    section.append(
      node("h2", "Agendamentos de serviços"),
      node(
        "p",
        "Escolha um recurso/profissional. Conflitos de horário são conferidos no servidor; horários de funcionamento não são presumidos.",
      ),
    );
    const actions = node("div");
    actions.className = "row wr";
    const disabled = s.busy || !writer();
    actions.append(
      button("Cadastrar serviço", () => service(s), disabled),
      button("Configurar duração", () => duration(s), disabled),
      button("Cadastrar profissional/recurso", () => resource(s), disabled),
      button("Configurar profissional/recurso", () => manageResources(s), disabled),
      button("Novo agendamento", () => book(s), disabled || s.phase !== "ready"),
      button("Configurar horários dos canais", () => configureChannelBooking(s),
        disabled || !["owner", "admin"].includes(host.identity?.papel)),
      button("Atualizar agendamentos", () => load(s), s.busy),
    );
    section.append(actions);
    const filters = node("form");
    filters.className = "row wr";
    filters.setAttribute("aria-label", "Período dos agendamentos");
    for (const [key, label] of [
      ["from", "Agendamentos de"],
      ["to", "Agendamentos até"],
    ]) {
      const wrapper = node("label", label),
        input = node("input");
      input.type = "date";
      input.required = true;
      input.value = s[key];
      input.disabled = s.busy;
      input.onchange = () => {
        s[key] = input.value;
      };
      wrapper.append(input);
      filters.append(wrapper);
    }
    const consult = button("Consultar agendamentos", null, s.busy);
    consult.type = "submit";
    filters.append(consult);
    filters.onsubmit = (e) => {
      e.preventDefault();
      if (filters.reportValidity()) load(s);
    };
    section.append(filters);
    const feedback = node(
      "p",
      s.error || (s.phase === "loading" ? "Consultando agendamentos…" : ""),
    );
    feedback.setAttribute("role", "status");
    section.append(feedback);
    for (const row of s.items) {
      const card = node("article");
      card.className = "crd";
      card.append(
        node("h3", row.service_name),
        node("p", `${row.client_name} · ${row.resource_name}`),
        node(
          "p",
          `${new Date(row.scheduled_for).toLocaleString("pt-BR")} – ${new Date(row.ends_at).toLocaleTimeString("pt-BR")} · ${row.status === "pending" ? "Agendado" : row.status === "done" ? "Concluído" : "Cancelado"}`,
        ),
      );
      if (row.notes) card.append(node("p", row.notes));
      const controls = node("div");
      controls.className = "row wr";
      if (row.status === "pending")
        controls.append(
          button("Reagendar", () => update(s, row), disabled || s.phase !== "ready"),
          button("Concluir", () => update(s, row, "done"), disabled || s.phase !== "ready"),
          button(
            "Cancelar agendamento",
            () => update(s, row, "cancelled"),
            disabled || s.phase !== "ready",
          ),
        );
      controls.append(button("Histórico", () => history(s, row), s.busy));
      card.append(controls);
      section.append(card);
    }
    if (s.phase === "ready" && !s.items.length)
      section.append(node("p", "Nenhum agendamento neste período."));
    if (s.truncated)
      section.append(
        node("p", "Lista limitada. Reduza o período para consultar os demais registros."),
      );
    parent.querySelector("[data-appointments]")?.remove();
    parent.append(section);
  }
  function mount() {
    paint();
    const s = current();
    if (s.phase === "initial" && location.hash === "#/agenda") load(s);
  }
  document.addEventListener("socialmei-agenda-painted", mount);
  window.SocialMEIAppointments = { refresh: () => load(current()) };
  mount();
})();
