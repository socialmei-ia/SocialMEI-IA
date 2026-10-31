/* Human takeover for persisted WhatsApp conversations. No provider sending. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIWhatsAppBot) return;
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const owner = () => ["owner", "admin"].includes(host.identity?.papel);
  const selected = () => {
    const match = /^#\/caixa\/(me-\d+)$/.exec(location.hash);
    const row = match && host.conversation(match[1]);
    return row?.origin === "waha" && owner() ? row : null;
  };
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  let state;
  const current = (s) => state === s && s.scope === scope() && selected()?.id === s.id;
  function paint(s) {
    if (!current(s)) return;
    const data = s.data;
    let text = s.message || "Consultando o atendimento…";
    if (!s.message && data) {
      text =
        data.state === "human"
          ? "Atendimento humano ativo. Novas respostas do bot estão suspensas."
          : data.enabled
            ? "Bot disponível para esta conversa. Assuma o atendimento para suspender novas respostas."
            : "Bot desativado no servidor. Você pode assumir o atendimento preventivamente.";
      if (data.claimed_in_flight)
        text +=
          " Existe envio já reservado: ele pode estar em andamento e precisa ser conciliado. Não repita o envio.";
    }
    s.feedback.textContent = text;
    s.pause.disabled = s.busy || !data || data.state === "human";
    s.resume.disabled = s.busy || !data || data.state !== "human";
    s.refresh.disabled = s.busy;
    s.panel.setAttribute("aria-busy", String(s.busy));
  }
  async function read(s) {
    const data = await host.request(`/whatsapp/bot/conversations/${s.id}/status`);
    if (!current(s)) return;
    if (
      !Number.isSafeInteger(data.channel_id) ||
      data.channel_id < 1 ||
      !["menu", "ask_product", "human"].includes(data.state) ||
      typeof data.enabled !== "boolean" ||
      !(
        typeof data.claimed_in_flight === "boolean" ||
        (Number.isSafeInteger(data.claimed_in_flight) && data.claimed_in_flight >= 0)
      )
    )
      throw Error("Estado do atendimento não reconhecido.");
    s.data = data;
    s.message = "";
  }
  async function load(s) {
    if (!current(s) || s.busy) return;
    s.busy = true;
    s.lastRead = Date.now();
    paint(s);
    try {
      await read(s);
    } catch {
      if (current(s)) {
        s.data = null;
        s.message = "Não foi possível consultar o atendimento. Atualize para tentar novamente.";
      }
    } finally {
      s.busy = false;
      paint(s);
    }
  }
  async function change(s, action) {
    if (!current(s) || s.busy || !s.data) return;
    const channel = s.data.channel_id;
    s.busy = true;
    s.message = "Confirmando no servidor…";
    paint(s);
    try {
      await host.request(`/whatsapp/bot/conversations/${s.id}/${action}`, "POST", {
        channel_id: channel,
      });
      if (current(s)) await read(s);
    } catch {
      if (current(s)) {
        s.data = null;
        s.message =
          "Resultado não confirmado. Atualize o atendimento antes de tentar outra alteração.";
      }
    } finally {
      s.busy = false;
      paint(s);
    }
  }
  function mount() {
    const row = selected();
    if (!row) {
      state?.panel.remove();
      state = null;
      return;
    }
    const thread = document.querySelector(".ct");
    if (!thread) return;
    if (!state || state.scope !== scope() || state.id !== row.id) {
      state?.panel.remove();
      state = { id: row.id, scope: scope(), busy: false, lastRead: 0, data: null };
    }
    const s = state;
    if (!s.panel?.isConnected) {
      s.panel = element("section");
      s.panel.className = "wa-human";
      s.panel.dataset.waBot = "true";
      s.panel.setAttribute("aria-label", "Atendimento humano do WhatsApp");
      s.feedback = element("p");
      s.feedback.setAttribute("role", "status");
      s.feedback.setAttribute("aria-live", "polite");
      s.pause = element("button", "Assumir atendimento");
      s.resume = element("button", "Retomar bot");
      s.refresh = element("button", "Atualizar atendimento");
      for (const button of [s.pause, s.resume, s.refresh]) button.type = "button";
      s.pause.onclick = () => change(s, "pause");
      s.resume.onclick = () => change(s, "resume");
      s.refresh.onclick = () => load(s);
      s.panel.append(
        element("strong", "Atendimento WhatsApp"),
        s.feedback,
        s.pause,
        s.resume,
        s.refresh,
      );
      thread.append(s.panel);
    }
    paint(s);
    if (Date.now() - s.lastRead > 5000) load(s);
  }
  const style = element("style");
  style.textContent =
    ".wa-human{padding:12px 16px;border:1px solid var(--b);border-radius:12px;margin:12px 0;display:flex;gap:8px;flex-wrap:wrap;color:var(--t);background:var(--w)}.wa-human strong,.wa-human p{width:100%}.wa-human p{font-size:14px;overflow-wrap:anywhere}.wa-human button{min-height:44px;padding:8px 12px;font:inherit;color:var(--t);background:var(--w);border:1px solid var(--b);border-radius:9px;cursor:pointer}.wa-human button:disabled{opacity:.55;cursor:default}";
  document.head.append(style);
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      const result = render.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  window.setInterval(() => {
    if (!document.hidden) mount();
  }, 6000);
  window.SocialMEIWhatsAppBot = { refresh: () => state && load(state) };
  queueMicrotask(mount);
})();
