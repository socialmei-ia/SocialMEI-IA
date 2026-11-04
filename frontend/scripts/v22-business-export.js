/* Explicit owner export through the authenticated API; never browser demo arrays. */
(() => {
  const auth = window.SocialMEIAuth;
  if (!auth?.remote || window.SocialMEIBusinessExport) return;
  const kinds = {
    "#/negocio/clientes": ["clientes", "data do cadastro"],
    "#/negocio/produtos": ["produtos", "data do cadastro"],
    "#/negocio/vendas": ["vendas", "data da venda"],
    "#/negocio/financeiro": ["financeiro", "vencimento"],
    "#/agenda": ["agendamentos", "início do agendamento"],
  };
  function element(tag, text) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    return node;
  }
  function mount() {
    const identity = auth.current;
    if (!identity || !["owner", "admin"].includes(identity.papel)) return;
    const match = kinds[location.hash.split("?")[0]];
    const view = document.getElementById("v");
    if (!match || !view || view.querySelector("[data-business-export]")) return;
    const [kind, field] = match;
    const scope = `${identity.usuario.id}:${identity.negocio.id}`;
    const panel = element("section");
    panel.dataset.businessExport = "true";
    panel.setAttribute("aria-label", "Exportação dos dados do negócio");
    panel.style.cssText =
      "margin:16px 0;padding:16px;border:1px solid var(--b);border-radius:12px;background:var(--w);color:var(--t)";
    panel.append(element("h3", "Exportar dados deste negócio"));
    panel.append(
      element(
        "p",
        "CSV para Excel, sem mensagens privadas nem notas livres. Filtro por " +
          field +
          ". Vazio exporta todos os registros, até 10 mil, sem cortes.",
      ),
    );
    const form = element("form");
    form.style.cssText = "display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin-top:12px";
    const inputs = [];
    for (const title of ["Exportar desde", "Exportar até"]) {
      const label = element("label", title);
      label.style.cssText = "display:grid;gap:6px;max-width:100%";
      const input = element("input");
      input.type = "date";
      input.style.cssText =
        "padding:10px;max-width:100%;box-sizing:border-box;background:var(--w);color:var(--t);border:1px solid var(--b);border-radius:8px";
      label.append(input);
      inputs.push(input);
      form.append(label);
    }
    const button = element("button", "Exportar CSV");
    button.type = "submit";
    button.className = "btn o";
    form.append(button);
    const message = element("p");
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    panel.append(form, message);
    view.append(panel);
    const active = () =>
      panel.isConnected &&
      auth.current &&
      `${auth.current.usuario.id}:${auth.current.negocio.id}` === scope;
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (button.disabled || !active()) return;
      if (
        !!inputs[0].value !== !!inputs[1].value ||
        (inputs[0].value && inputs[0].value > inputs[1].value)
      ) {
        message.textContent = "Informe início e fim em ordem, ou deixe os dois vazios.";
        return;
      }
      button.disabled = true;
      message.textContent = "Preparando arquivo com os dados salvos…";
      try {
        const result = await auth.request(
          "/exports/" + kind,
          "POST",
          inputs[0].value ? { start: inputs[0].value, end: inputs[1].value } : {},
        );
        if (!active()) return;
        if (
          typeof result.csv !== "string" ||
          !/^socialmei-[a-z]+-[0-9_a-z-]+\.csv$/.test(result.filename) ||
          !Number.isSafeInteger(result.row_count)
        )
          throw new Error("O arquivo não foi confirmado pelo servidor.");
        const url = URL.createObjectURL(new Blob([result.csv], { type: "text/csv;charset=utf-8" }));
        const link = element("a");
        link.href = url;
        link.download = result.filename;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        message.textContent =
          result.row_count + " registro(s) exportado(s) deste negócio. Confira o arquivo baixado.";
      } catch (error) {
        if (active())
          message.textContent = error.message || "Não foi possível exportar. Tente novamente.";
      } finally {
        if (active()) button.disabled = false;
      }
    };
  }
  window.SocialMEIBusinessExport = { refresh: mount };
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
