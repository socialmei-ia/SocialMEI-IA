/* Manual CRM association. Never changes the sender label, messages, channel or bot. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInboxCustomer) return;
  const element = (tag, text) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const writer = () => ["owner", "admin", "member"].includes(host.identity?.papel);
  const selected = () => {
    const match = /^#\/caixa\/(me-\d+)$/.exec(location.hash);
    return match && host.conversation(match[1]);
  };
  let state;
  const current = (s) => state === s && s.identity === host.identity && selected()?.id === s.id;
  function valid(data, s) {
    if (
      !data ||
      data.conversation_id !== s.id ||
      !Number.isSafeInteger(data.revision) ||
      data.revision < 0 ||
      !(
        data.cliente_id === null ||
        (Number.isSafeInteger(data.cliente_id) &&
          data.cliente_id > 0 &&
          data.customer?.id === data.cliente_id &&
          typeof data.customer.nome === "string")
      ) ||
      (data.cliente_id === null && data.customer !== null)
    )
      throw Error("Resposta de vínculo inválida. Atualize antes de alterar.");
    return data;
  }
  function paint(s) {
    if (!current(s) || !s.panel) return;
    s.feedback.textContent =
      s.error ||
      (!s.data
        ? "Consultando vínculo com o CRM…"
        : s.data.customer
          ? "Cliente: " + s.data.customer.nome
          : "Esta conversa ainda não está associada a um cliente do CRM.");
    s.edit.textContent = s.data?.customer ? "Alterar cliente do CRM" : "Associar cliente do CRM";
    s.edit.disabled = s.busy || !s.data || !writer();
    s.refresh.disabled = s.busy;
    s.panel.setAttribute("aria-busy", String(s.busy));
  }
  async function load(s) {
    if (!current(s) || s.busy) return;
    s.busy = true;
    s.lastRead = Date.now();
    paint(s);
    try {
      const data = await host.request(`/message-enrichment/conversations/${s.id}/customer`);
      if (current(s)) {
        s.data = valid(data, s);
        s.error = "";
      }
    } catch (error) {
      if (current(s)) {
        s.data = null;
        s.error = error.message || "Vínculo indisponível. Atualize para tentar novamente.";
      }
    } finally {
      s.busy = false;
      paint(s);
    }
  }
  async function edit(s) {
    if (!current(s) || s.busy || !s.data || !writer()) return;
    const original = s.data;
    s.busy = true;
    paint(s);
    let clients;
    try {
      clients = await host.request("/clientes");
      if (!Array.isArray(clients)) throw Error("Clientes indisponíveis.");
    } catch (error) {
      if (current(s)) s.error = error.message;
      return;
    } finally {
      s.busy = false;
      paint(s);
    }
    if (!current(s) || !writer()) return;
    openForm(
      "Associar conversa ao cliente",
      "Somente clientes deste negócio. Desvincular não apaga a conversa nem o cliente.",
      [{ id: "inbox_customer", label: "Cliente do CRM", type: "select", options: [] }],
      () => "",
      "Salvar vínculo",
    );
    const box = dlg(),
      form = box.querySelector("form"),
      select = form.querySelector("#f_inbox_customer");
    const owns = () => box.querySelector("form") === form;
    const none = element("option", "Sem vínculo");
    none.value = "";
    select.replaceChildren(none);
    for (const client of clients) {
      if (!Number.isSafeInteger(client.id) || typeof client.nome !== "string") continue;
      const detail = client.email || client.telefone || "ID " + client.id;
      const option = element("option", `${client.nome} · ${detail}`);
      option.value = String(client.id);
      select.append(option);
    }
    select.value = original.cliente_id === null ? "" : String(original.cliente_id);
    const feedback = element("p");
    feedback.setAttribute("role", "status");
    form.append(feedback);
    let submitting = false;
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (submitting) return;
      if (!current(s) || !writer()) {
        if (owns()) box.close();
        return;
      }
      const customerId = select.value ? Number(select.value) : null;
      if (customerId !== null && !clients.some((c) => c.id === customerId)) {
        feedback.textContent = "Cliente inválido. Reabra o formulário.";
        return;
      }
      submitting = true;
      s.busy = true;
      form.querySelectorAll("button").forEach((b) => (b.disabled = true));
      paint(s);
      try {
        const data = await host.request(
          `/message-enrichment/conversations/${s.id}/customer`,
          "PATCH",
          { expected_revision: original.revision, cliente_id: customerId },
        );
        if (!current(s)) return;
        valid(data, s);
        const revision = original.revision + (original.cliente_id === customerId ? 0 : 1);
        if (data.cliente_id !== customerId || data.revision !== revision)
          throw Error("Confirmação inválida. Atualize o vínculo antes de repetir.");
        s.data = data;
        s.error = "";
        if (owns()) box.close();
      } catch (error) {
        if (current(s) && owns()) {
          s.data = null;
          s.error = "Vínculo sem confirmação. Atualize antes de alterar.";
          feedback.textContent =
            error.status === 409
              ? "A conversa ou o cliente mudou. Feche e atualize o vínculo antes de salvar novamente."
              : "Resultado não confirmado. Feche e atualize o vínculo antes de repetir.";
        }
      } finally {
        submitting = false;
        s.busy = false;
        if (owns()) form.querySelectorAll("button").forEach((b) => (b.disabled = false));
        paint(s);
      }
    };
    const cancel = (event) => {
      if (submitting && owns()) event.preventDefault();
    };
    box.addEventListener("cancel", cancel);
    box.addEventListener("close", () => box.removeEventListener("cancel", cancel), { once: true });
  }
  function mount() {
    const row = selected();
    if (!row) {
      state?.panel?.remove();
      state = null;
      return;
    }
    const thread = document.querySelector(".ct");
    if (!thread) return;
    if (!state || state.identity !== host.identity || state.id !== row.id) {
      state?.panel?.remove();
      state = {
        identity: host.identity,
        id: row.id,
        data: null,
        busy: false,
        lastRead: 0,
        inboxRevision: row.revision,
      };
    }
    const s = state;
    if (!s.panel?.isConnected) {
      s.panel = element("section");
      s.panel.className = "inbox-customer";
      s.panel.dataset.inboxCustomer = "true";
      s.panel.setAttribute("aria-label", "Cliente do CRM desta conversa");
      s.feedback = element("p");
      s.feedback.setAttribute("role", "status");
      s.feedback.setAttribute("aria-live", "polite");
      s.edit = element("button", "Associar cliente do CRM");
      s.refresh = element("button", "Atualizar vínculo CRM");
      for (const b of [s.edit, s.refresh]) {
        b.type = "button";
        b.className = "btn o";
      }
      s.edit.onclick = () => edit(s);
      s.refresh.onclick = () => load(s);
      s.panel.append(s.feedback, s.edit, s.refresh);
      const messages = thread.querySelector(".ms");
      if (messages) messages.before(s.panel);
      else thread.append(s.panel);
    }
    paint(s);
    if (!s.lastRead || s.inboxRevision !== row.revision) {
      s.inboxRevision = row.revision;
      load(s);
    }
  }
  const style = element("style");
  style.textContent =
    ".inbox-customer{padding:10px 16px;display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--b);background:var(--w);color:var(--t)}.inbox-customer p{width:100%;overflow-wrap:anywhere;margin:0}.inbox-customer button{min-height:44px}";
  document.head.append(style);
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      const result = render.apply(this, args);
      mount();
      return result;
    };
  window.SocialMEIInboxCustomer = { refresh: () => state && load(state) };
  mount();
})();
