/* Setup guidance reuses existing forms and counts only persisted business records. */
(() => {
  const host = window.SocialMEIV22,
    auth = window.SocialMEIAuth;
  if (!host?.remote || !auth?.remote || window.SocialMEIBusinessStart) return;
  const el = (tag, text) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = String(text);
    return n;
  };
  const scope = () => auth.current && `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  const route = () => ["", "#/inicio", "#/bemvindo", "#/config/negocio"].includes(location.hash);
  function mount() {
    const view = document.getElementById("v");
    if (
      !view ||
      !scope() ||
      !route() ||
      !["owner", "admin"].includes(auth.current.papel) ||
      view.querySelector("[data-business-start]")
    )
      return;
    const owner = scope(),
      section = el("section");
    section.dataset.businessStart = "true";
    section.style.cssText =
      "margin:20px 0;padding:20px;border:1px solid var(--b);border-radius:16px;background:var(--w);color:var(--t);overflow-wrap:anywhere";
    section.append(el("h2", "Primeiros passos · " + auth.current.negocio.nome));
    const message = el("p"),
      content = el("div"),
      refresh = el("button", "Atualizar primeiros passos");
    refresh.type = "button";
    refresh.className = "btn o";
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    section.append(message, content, refresh);
    if (location.hash === "#/config/negocio") view.append(section);
    else view.prepend(section);
    let revision = 0,
      catalogRevision = 0;
    const alive = (id) => section.isConnected && scope() === owner && route() && id === revision;
    async function catalog(id, target, offers) {
      const ticket = ++catalogRevision;
      const catalogAlive = () => alive(id) && ticket === catalogRevision;
      const key = "socialmei-initial-catalog-pending-v1:" + owner;
      const feedback = el("p", "Consultando suas ofertas escolhidas…");
      feedback.setAttribute("role", "status");
      target.replaceChildren(feedback);
      try {
        const data = await host.request("/onboarding/catalog");
        if (!catalogAlive()) return;
        if (
          data.workspace_id !== auth.current.negocio.id ||
          !Number.isSafeInteger(data.revision) ||
          !Array.isArray(data.items) ||
          !Array.isArray(data.suggestions)
        )
          throw Error("Não foi possível confirmar a configuração deste negócio.");
        if (data.receipt) {
          sessionStorage.removeItem(key);
          feedback.textContent =
            "O cadastro inicial já foi confirmado. Consulte Produtos ou Agenda para conferir o estado atual, editar ou adicionar itens.";
          return;
        }
        const form = el("form"),
          rows = el("div"),
          actions = el("div");
        let expected = data.revision,
          pending = null;
        try {
          pending = JSON.parse(sessionStorage.getItem(key));
        } catch {
          /* Invalid local receipt is never sent. */
        }
        if (
          pending &&
          (typeof pending.operation_id !== "string" ||
            !Array.isArray(pending.items) ||
            pending.confirmed !== true)
        )
          throw Error(
            "A tentativa anterior precisa de revisão. Entre novamente antes de continuar.",
          );
        const controls = [];
        const input = (label, type, value = "") => {
          const wrap = el("label", label),
            field = el("input");
          field.type = type;
          field.value = value ?? "";
          field.style.cssText =
            "display:block;width:100%;min-width:0;box-sizing:border-box;margin:4px 0 12px";
          wrap.append(field);
          return [wrap, field];
        };
        function add(value = {}) {
          if (controls.length >= 30) return;
          const box = el("fieldset"),
            legend = el("legend", "Oferta " + (controls.length + 1));
          box.style.cssText = "margin:12px 0;padding:12px;min-width:0;border:1px solid var(--b)";
          const [nameLabel, name] = input("Nome", "text", value.nome),
            [priceLabel, price] = input("Preço (R$)", "number", value.preco),
            [durationLabel, duration] = input("Duração (minutos)", "number", value.duracao_minutos),
            typeLabel = el("label", "Tipo"),
            type = el("select"),
            remove = el("button", "Remover oferta");
          name.required = price.required = true;
          name.maxLength = 160;
          price.min = "0";
          price.step = "0.01";
          duration.min = "1";
          duration.max = "1440";
          duration.step = "1";
          for (const kind of ["Serviço", "Produto"]) {
            const option = el("option", kind);
            option.value = kind;
            type.append(option);
          }
          type.value =
            value.tipo || (offers.length === 1 && offers[0] === "products" ? "Produto" : "Serviço");
          type.style.cssText = "display:block;width:100%;margin:4px 0 12px";
          typeLabel.append(type);
          remove.type = "button";
          remove.className = "btn o";
          const row = { box, name, price, type, duration };
          remove.onclick = () => {
            controls.splice(controls.indexOf(row), 1);
            box.remove();
          };
          type.onchange = () => {
            durationLabel.hidden = type.value !== "Serviço";
            duration.required = !durationLabel.hidden;
          };
          type.onchange();
          controls.push(row);
          box.append(legend, nameLabel, typeLabel, priceLabel, durationLabel, remove);
          rows.append(box);
        }
        const initial =
          pending?.items ||
          (data.items.length
            ? data.items
            : data.suggestions.map((nome) => ({ nome, tipo: "Serviço" })));
        initial.forEach(add);
        if (!initial.length) add();
        const values = (draft) =>
          controls
            .filter((row) => !draft || row.name.value.trim())
            .map((row) => ({
              nome: row.name.value.trim(),
              tipo: row.type.value,
              preco: row.price.value === "" ? null : Number(row.price.value),
              duracao_minutos:
                row.type.value === "Serviço" && row.duration.value !== ""
                  ? Number(row.duration.value)
                  : null,
            }));
        const addButton = el("button", "Adicionar oferta"),
          save = el("button", "Salvar e continuar depois"),
          submit = el(
            "button",
            pending ? "Conferir tentativa anterior" : "Cadastrar ofertas confirmadas",
          ),
          [confirmLabel, confirm] = input(
            "Conferi nomes, preços e duração destas ofertas.",
            "checkbox",
          );
        confirm.checked = !!pending;
        confirm.required = true;
        addButton.type = save.type = "button";
        submit.type = "submit";
        for (const button of [addButton, save, submit]) button.className = "btn o";
        actions.style.cssText = "display:flex;flex-wrap:wrap;gap:8px";
        actions.append(addButton, save, submit);
        feedback.textContent = pending
          ? "Uma tentativa anterior aguarda confirmação. Consulte o resultado antes de cadastrar novamente."
          : "Escolher serviços no perfil não os cadastra. Confirme somente ofertas reais; nenhum preço ou duração será preenchido por nós.";
        form.append(rows, confirmLabel, actions);
        target.append(form);
        addButton.onclick = () => add();
        function busy(active) {
          for (const control of form.querySelectorAll("input,select,button"))
            control.disabled = active || !!pending;
          if (pending && !active) submit.disabled = false;
        }
        busy(false);
        save.onclick = async () => {
          busy(true);
          try {
            const result = await host.request("/onboarding/catalog", "PUT", {
              expected_revision: expected,
              items: values(true),
            });
            if (!catalogAlive()) return;
            if (
              result.workspace_id !== auth.current.negocio.id ||
              !Number.isSafeInteger(result.revision)
            )
              throw Error("Não foi possível confirmar o salvamento.");
            expected = result.revision;
            feedback.textContent =
              "Configuração salva. Você pode retomar neste negócio; nenhuma oferta foi cadastrada ainda.";
          } catch (error) {
            if (catalogAlive()) feedback.textContent = error.message || "Não foi possível salvar.";
          } finally {
            if (catalogAlive()) busy(false);
          }
        };
        form.onsubmit = async (event) => {
          event.preventDefault();
          if (!pending && !form.reportValidity()) return;
          if (!pending) {
            if (!controls.length) {
              feedback.textContent = "Inclua ao menos uma oferta real.";
              return;
            }
            pending = {
              operation_id: crypto.randomUUID(),
              expected_revision: expected,
              confirmed: true,
              items: values(false),
            };
            try {
              sessionStorage.setItem(key, JSON.stringify(pending));
            } catch {
              pending = null;
              feedback.textContent =
                "Não foi possível preservar sua tentativa neste navegador. Tente novamente.";
              return;
            }
          }
          busy(true);
          try {
            const result = await host.request("/onboarding/catalog", "POST", pending);
            if (!catalogAlive()) return;
            if (
              result.workspace_id !== auth.current.negocio.id ||
              result.registered !== true ||
              !Array.isArray(result.items)
            )
              throw Error("Não foi possível confirmar o cadastro.");
            sessionStorage.removeItem(key);
            pending = null;
            await load();
          } catch (error) {
            if (!catalogAlive()) return;
            if ([409, 422].includes(error.status)) {
              sessionStorage.removeItem(key);
              pending = null;
            }
            feedback.textContent =
              error.message ||
              "Resultado ainda não confirmado. Confira a tentativa anterior antes de repetir.";
          } finally {
            if (catalogAlive()) {
              submit.textContent = pending
                ? "Conferir tentativa anterior"
                : "Cadastrar ofertas confirmadas";
              busy(false);
            }
          }
        };
      } catch (error) {
        if (catalogAlive())
          feedback.textContent = error.message || "Não foi possível consultar suas ofertas.";
      }
    }
    async function load() {
      const id = ++revision;
      refresh.disabled = true;
      section.setAttribute("aria-busy", "true");
      content.replaceChildren();
      message.textContent = "Consultando o que já foi salvo neste negócio…";
      try {
        const data = await host.request("/onboarding/status");
        if (!alive(id)) return;
        if (
          data.workspace_id !== auth.current.negocio.id ||
          typeof data.profile_complete !== "boolean" ||
          typeof data.profile_problem !== "boolean" ||
          !Array.isArray(data.offers) ||
          data.offers.length > 2 ||
          new Set(data.offers).size !== data.offers.length ||
          !data.offers.every((v) => ["products", "services"].includes(v)) ||
          data.profile_complete !== !!data.offers.length ||
          (data.profile_complete && data.profile_problem) ||
          ![
            "customers",
            "products",
            "services",
            "resources",
            "appointments_created",
            "valid_sales",
          ].every((k) => Number.isSafeInteger(data.counts?.[k]) && data.counts[k] >= 0)
        )
          throw Error("Não foi possível confirmar seus primeiros passos.");
        const c = data.counts,
          services = !data.profile_complete || data.offers.includes("services"),
          products = !data.profile_complete || data.offers.includes("products");
        const steps = [
          {
            title: "Perfil do negócio salvo",
            done: data.profile_complete,
            action: data.profile_complete ? "Rever configuração" : "Configurar negócio",
            href: "/frontend/entrada.html?setup=1#/comecar",
          },
          {
            title: services ? "Cliente cadastrado para agendar" : "Cliente cadastrado (opcional)",
            done: c.customers > 0,
            optional: !services,
            action: "Abrir clientes",
            href: "#/negocio/clientes",
          },
        ];
        if (services)
          steps.push(
            {
              title: "Serviço ativo com duração",
              done: c.services > 0,
              action: "Gerenciar serviços",
              href: "#/agenda",
            },
            {
              title: "Profissional ou recurso ativo",
              done: c.resources > 0,
              action: "Gerenciar recursos",
              href: "#/agenda",
            },
            {
              title: "Primeiro agendamento cadastrado",
              done: c.appointments_created > 0,
              action: "Abrir agenda",
              href: "#/agenda",
            },
          );
        if (products)
          steps.push(
            {
              title: "Produto ativo e estoque cadastrados",
              done: c.products > 0,
              action: "Abrir produtos e estoque",
              href: "#/negocio/produtos",
            },
            {
              title: "Primeira venda válida registrada",
              done: c.valid_sales > 0,
              action: "Abrir vendas",
              href: "#/negocio/vendas",
            },
          );
        if (data.profile_problem)
          content.append(
            el(
              "p",
              "O perfil salvo precisa de revisão. Use Configurar negócio para conferir suas informações.",
            ),
          );
        if (!data.profile_complete)
          content.append(
            el(
              "p",
              "Na configuração, escolha produtos, serviços ou ambos para mostrar somente os passos relevantes. Clientes são necessários para agendar e opcionais nas vendas.",
            ),
          );
        const list = el("ol");
        list.style.cssText = "padding-left:22px";
        for (const step of steps) {
          const row = el("li");
          row.dataset.state = step.done ? "complete" : "pending";
          row.style.cssText = "margin:12px 0;overflow-wrap:anywhere";
          const line = el("div");
          line.style.cssText =
            "display:flex;gap:12px;flex-wrap:wrap;align-items:center;justify-content:space-between";
          const link = el("a", step.action);
          link.href = step.href;
          link.className = "btn o";
          line.append(
            el(
              "span",
              step.title +
                " — " +
                (step.done ? "Registrado" : step.optional ? "Opcional" : "Pendente"),
            ),
            link,
          );
          row.append(line);
          list.append(row);
        }
        content.append(list, el("p", data.description));
        const setupTarget = el("div"),
          setup = el("button", "Conferir ofertas iniciais");
        setup.type = "button";
        setup.className = "btn o";
        setup.onclick = () => catalog(id, setupTarget, data.offers);
        content.append(setup, setupTarget);
        if (data.setup && typeof data.setup.hours_configured === "boolean") {
          const hours = el(
              "p",
              "Horários de funcionamento — " +
                (data.setup.hours_configured ? "Registrados" : "Pendentes"),
            ),
            link = el("a", "Configurar horários e profissionais na Agenda");
          link.href = "#/agenda";
          link.className = "btn o";
          content.append(hours, link);
        }
        const channels = el("a", "Configurar canais depois (opcional)");
        channels.href = "#/config/integracoes";
        channels.className = "btn o";
        content.append(channels);
        const required = steps.filter((s) => !s.optional);
        message.textContent = data.profile_complete
          ? `${required.filter((s) => s.done).length} de ${required.length} passos essenciais registrados neste negócio.`
          : "Seus dados estão separados por negócio. Comece pela configuração e siga os passos que usar.";
      } catch (error) {
        if (alive(id)) {
          content.replaceChildren();
          message.textContent = error.message || "Não foi possível consultar os primeiros passos.";
        }
      } finally {
        if (alive(id)) {
          refresh.disabled = false;
          section.setAttribute("aria-busy", "false");
        }
      }
    }
    refresh.onclick = load;
    load();
  }
  window.SocialMEIBusinessStart = { refresh: mount };
  const previous = window.render;
  if (typeof previous === "function")
    window.render = function (...args) {
      const result = previous.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  queueMicrotask(mount);
})();
