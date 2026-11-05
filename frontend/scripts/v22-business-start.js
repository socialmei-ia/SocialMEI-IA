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
