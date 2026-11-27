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
  const dismissed = new Set();
  const prefKey = (owner) => "socialmei:business-start:dismissed:v1:" + owner;
  const isDismissed = (owner) => {
    if (dismissed.has(owner)) return true;
    try { return localStorage.getItem(prefKey(owner)) === "1"; }
    catch (_) { return false; }
  };
  const dismiss = (owner) => {
    dismissed.add(owner);
    try { localStorage.setItem(prefKey(owner), "1"); } catch (_) {}
  };
  function mount() {
    const view = document.getElementById("v");
    if (
      !view ||
      !scope() ||
      !route() ||
      (location.hash !== "#/bemvindo" && isDismissed(scope())) ||
      !["owner", "admin"].includes(auth.current.papel) ||
      view.querySelector("[data-business-start]")
    )
      return;
    const owner = scope(),
      section = el("section");
    section.dataset.businessStart = "true";
    section.className = "bs-card";
    const bsHead = el("header");
    bsHead.className = "bs-head";
    const bsT = el("div"),
      bsEy = el("span", auth.current.negocio.nome),
      bsH = el("h2", "Primeiros passos");
    bsEy.className = "bs-eyebrow";
    bsT.append(bsEy, bsH);
    const bsProg = el("div");
    bsProg.className = "bs-prog";
    bsProg.hidden = true;
    bsHead.append(bsT, bsProg);
    section.append(bsHead);
    const message = el("p"),
      content = el("div"),
      refresh = el("button", "Atualizar primeiros passos");
    refresh.type = "button";
    refresh.className = "btn o bs-refresh";
    message.className = "bs-msg";
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    section.append(message, content, refresh);
    if (location.hash === "#/config/negocio") view.append(section);
    else view.prepend(section);
    let revision = 0;
    const alive = (id) => section.isConnected && scope() === owner && route() && id === revision;
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
        if (services)
          steps.splice(steps.findIndex((x) => x.title.startsWith("Serviço ativo")) + 1, 0, {
            title: "Horário de funcionamento definido",
            done: !!String(auth.current.negocio.configuracao?.horario || "").trim(),
            action: "Definir horário",
            href: "#/agenda",
          });
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
            Object.assign(
              el(
                "p",
                "O perfil salvo precisa de revisão. Use Configurar negócio para conferir suas informações.",
              ),
              { className: "bs-alert" },
            ),
          );
        if (!data.profile_complete)
          content.append(
            Object.assign(
              el(
                "p",
                "Na configuração, escolha produtos, serviços ou ambos para mostrar somente os passos relevantes. Clientes são necessários para agendar e opcionais nas vendas.",
              ),
              { className: "bs-hint" },
            ),
          );
        const HELP = [
          ["Perfil do negócio", "Nome, segmento e o que você oferece."],
          ["Cliente cadastrado", "Necessário para agendar; opcional nas vendas."],
          ["Serviço ativo", "O que você oferece e quanto tempo leva."],
          ["Horário de funcionamento", "Dias e horários em que você atende."],
          ["Profissional ou recurso", "Quem ou o que atende os agendamentos."],
          ["Primeiro agendamento", "Teste o fluxo completo da agenda."],
          ["Produto ativo", "Itens à venda e a quantidade em estoque."],
          ["Primeira venda", "Registre uma venda e acompanhe o Financeiro."],
        ];
        const help = (t) => (HELP.find((h) => t.startsWith(h[0])) || [])[1] || "";
        const nextIdx = steps.findIndex((x) => !x.done && !x.optional);
        const list = el("ol");
        list.className = "bs-steps";
        steps.forEach((step, i) => {
          const row = el("li");
          row.dataset.state = step.done ? "complete" : "pending";
          if (i === nextIdx) row.dataset.next = "true";
          row.className = "bs-step";
          const mark = el("span", step.done ? "✓" : String(i + 1));
          mark.className = "bs-n";
          mark.setAttribute("aria-hidden", "true");
          const body = el("div");
          body.className = "bs-t";
          const stateText = step.done ? "Registrado" : step.optional ? "Opcional" : "Pendente";
          const title = el("strong", step.title);
          const chip = el("span", stateText);
          chip.className = "bs-chip";
          chip.dataset.s = step.done ? "ok" : step.optional ? "opt" : i === nextIdx ? "next" : "pend";
          const head = el("div");
          head.className = "bs-th";
          head.append(title, chip);
          const hp = el("span", help(step.title));
          hp.className = "bs-d";
          body.append(head, hp);
          const link = el("a", step.action);
          link.href = step.href;
          link.className = i === nextIdx ? "btn" : "btn o";
          if (i === nextIdx) link.setAttribute("aria-label", step.action + " — próximo passo");
          row.append(mark, body, link);
          list.append(row);
        });
        content.append(list);
        if (data.description) {
          const det = el("details");
          det.className = "bs-note";
          det.append(el("summary", "Como estas etapas são contadas"), el("p", data.description));
          content.append(det);
        }
        const channels = el("button", "Configurar depois");
        channels.type = "button";
        channels.className = "btn o bs-chan";
        channels.onclick = () => {
          if (scope() !== owner || !section.isConnected) return;
          dismiss(owner);
          ++revision;
          section.remove();
          if (location.hash && location.hash !== "#/inicio") location.hash = "#/inicio";
        };
        content.append(channels);
        const required = steps.filter((s) => !s.optional);
        {
          const req = steps.filter((x) => !x.optional),
            n = req.filter((x) => x.done).length,
            pct = req.length ? Math.round((n / req.length) * 100) : 0;
          bsProg.hidden = !data.profile_complete;
          bsProg.replaceChildren();
          const bar = el("div"),
            fill = el("i");
          bar.className = "bs-bar";
          bar.setAttribute("role", "progressbar");
          bar.setAttribute("aria-valuemin", "0");
          bar.setAttribute("aria-valuemax", String(req.length));
          bar.setAttribute("aria-valuenow", String(n));
          bar.setAttribute("aria-label", "Passos essenciais registrados");
          fill.style.width = pct + "%";
          bar.append(fill);
          bsProg.append(el("b", n + " de " + req.length), el("span", "passos essenciais"), bar);
        }
        {
          // v7.6: próximo passo em destaque e cartão compacto quando os essenciais terminam.
          const all = required.length > 0 && required.every((x) => x.done) && data.profile_complete;
          section.classList.toggle("bs-done", all);
          section.querySelector(".bs-nextline")?.remove();
          section.querySelector(".bs-toggle")?.remove();
          const nx = steps[nextIdx];
          if (nx && data.profile_complete) {
            const line = el("p", "Próximo passo: " + nx.title.toLowerCase() + ". Cada etapa leva poucos minutos.");
            line.className = "bs-nextline";
            content.prepend(line);
          }
          if (all) {
            section.classList.remove("bs-open");
            const tg = el("button", "Ver detalhes");
            tg.type = "button"; tg.className = "bs-toggle"; tg.setAttribute("aria-expanded", "false");
            tg.onclick = () => { const o = section.classList.toggle("bs-open"); tg.textContent = o ? "Ocultar detalhes" : "Ver detalhes"; tg.setAttribute("aria-expanded", String(o)); };
            section.append(tg);
          }
        }
        message.classList.toggle("bs-sr", data.profile_complete);
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
