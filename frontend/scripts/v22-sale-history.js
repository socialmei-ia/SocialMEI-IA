/* Read-only sale snapshots. Stock-applied flags are not stock movement quantities. */
(() => {
  const host = window.SocialMEIV22;
  const auth = window.SocialMEIAuth;
  if (!host?.remote || !auth?.remote || window.SocialMEISaleHistory) return;
  const scope = () => auth.current && `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  let currentDialog = null;
  function close() {
    if (currentDialog) {
      const dialog = currentDialog;
      currentDialog = null;
      dialog.remove();
      if (dialog.historyOpener?.isConnected) dialog.historyOpener.focus();
    }
  }
  async function open(saleId) {
    close();
    const owner = scope();
    const dialog = element("dialog");
    dialog.historyOpener = document.activeElement;
    currentDialog = dialog;
    dialog.setAttribute("aria-label", "Histórico da venda " + saleId);
    dialog.style.cssText =
      "width:min(680px,calc(100vw - 32px));max-height:80vh;box-sizing:border-box;overflow:auto;border:1px solid var(--b);border-radius:16px;padding:20px;background:var(--w);color:var(--t)";
    const title = element("h2", "Histórico da venda #" + saleId);
    const caveat = element(
      "p",
      "Autor não registrado neste histórico. O estado de estoque de cada versão não informa a quantidade movimentada.",
    );
    const status = element("p", "Consultando histórico salvo…");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const list = element("ol");
    list.style.cssText = "padding-left:24px;overflow-wrap:anywhere";
    const more = element("button", "Carregar registros anteriores");
    more.type = "button";
    more.className = "btn o";
    more.hidden = true;
    const done = element("button", "Fechar histórico");
    done.type = "button";
    done.className = "btn o";
    done.onclick = close;
    dialog.append(title, caveat, status, list, more, done);
    document.body.append(dialog);
    dialog.addEventListener("close", () => {
      if (currentDialog === dialog) close();
      else dialog.remove();
    });
    dialog.showModal();
    let cursor = null,
      busy = false;
    const active = () => dialog.isConnected && dialog.open && scope() === owner;
    async function load() {
      if (busy || !active()) return;
      busy = true;
      more.disabled = true;
      status.textContent = "Consultando histórico salvo…";
      try {
        const result = await host.request(
          "/vendas/" +
            saleId +
            "/history?limit=20" +
            (cursor ? "&before=" + encodeURIComponent(cursor) : ""),
        );
        if (!active()) return;
        if (
          result.workspace_id !== auth.current.negocio.id ||
          result.sale_id !== saleId ||
          result.actor_recorded !== false ||
          typeof result.timezone !== "string" ||
          !Array.isArray(result.items) ||
          result.items.length > 50 ||
          (result.next_cursor !== null && !/^[a-f0-9-]{36}$/.test(result.next_cursor))
        )
          throw Error("Histórico não confirmado pelo servidor.");
        const fragment = document.createDocumentFragment();
        for (const item of result.items) {
          if (
            !Number.isSafeInteger(item.revision) ||
            item.revision < 1 ||
            !Number.isSafeInteger(item.quantity) ||
            item.quantity < 1 ||
            !["Rascunho", "Pendente", "Pago", "Cancelado"].includes(item.status) ||
            !/^\d{1,13}\.\d{2}$/.test(item.total) ||
            typeof item.stock_applied !== "boolean" ||
            typeof item.deleted !== "boolean" ||
            !Number.isFinite(Date.parse(item.recorded_at))
          )
            throw Error("Histórico não confirmado pelo servidor.");
          const row = element("li");
          row.style.cssText = "padding:12px 0;border-bottom:1px solid var(--b)";
          row.append(element("strong", "Versão " + item.revision + " · " + item.status));
          row.append(
            element(
              "p",
              new Date(item.recorded_at).toLocaleString("pt-BR", { timeZone: result.timezone }) +
                " · " +
                result.timezone,
            ),
          );
          row.append(
            element(
              "p",
              "Quantidade: " +
                item.quantity +
                " · Total: " +
                Number(item.total).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }),
            ),
          );
          row.append(
            element("p", "Estoque aplicado nesta versão: " + (item.stock_applied ? "Sim" : "Não")),
          );
          if (item.deleted) row.append(element("p", "Venda excluída; registro preservado."));
          fragment.append(row);
        }
        list.append(fragment);
        cursor = result.next_cursor;
        more.hidden = cursor === null;
        status.textContent = result.items.length
          ? "Registros salvos, do mais recente para o mais antigo."
          : "Nenhuma operação registrada neste histórico. Importações e registros antigos podem não ter histórico de operações.";
      } catch (error) {
        if (active()) {
          status.textContent = error.message || "Não foi possível consultar o histórico.";
          more.hidden = false;
          more.textContent = "Tentar consultar novamente";
        }
      } finally {
        busy = false;
        if (active()) more.disabled = false;
      }
    }
    more.onclick = load;
    load();
  }
  function mount() {
    if (location.hash !== "#/negocio/vendas" || !auth.current) return;
    for (const row of document.querySelectorAll("#v table tr:has(td)")) {
      if (row.querySelector("[data-sale-history]")) continue;
      const action = row.querySelector('[data-a^="vt:"]');
      const index = action && Number(action.dataset.a.slice(3));
      const saleId = Number(V[index]?.[0]);
      if (!Number.isSafeInteger(saleId) || saleId < 1) continue;
      const button = element("button", "Histórico da venda " + saleId);
      button.type = "button";
      button.className = "lk sm";
      button.dataset.saleHistory = String(saleId);
      const owner = scope();
      button.onclick = (event) => {
        event.preventDefault();
        if (row.isConnected && scope() === owner && Number(V[index]?.[0]) === saleId) open(saleId);
      };
      (row.querySelector(".acr") || row.lastElementChild).append(button);
    }
  }
  window.SocialMEISaleHistory = { refresh: mount };
  const previous = window.render;
  if (typeof previous === "function")
    window.render = function (...args) {
      const result = previous.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => {
    close();
    queueMicrotask(mount);
  });
  queueMicrotask(mount);
})();
