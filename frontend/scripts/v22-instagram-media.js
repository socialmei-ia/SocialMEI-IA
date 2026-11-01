/* Read the connected account only on request; never publish or send from this view. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInstagramMedia) return;
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const observed = new WeakSet();
  let dialog = null,
    epoch = 0;
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function safeURL(value, image = false) {
    if (typeof value !== "string" || value.length > 8192) return null;
    try {
      const url = new URL(value),
        name = url.hostname.toLowerCase();
      if (
        url.protocol !== "https:" ||
        url.username ||
        url.password ||
        url.hash ||
        (url.port && url.port !== "443") ||
        [...url.searchParams.keys()].some((key) => /^(access_token|token|code)$/i.test(key))
      )
        return null;
      return image
        ? ["cdninstagram.com", "fbcdn.net"].some(
            (domain) => name === domain || name.endsWith("." + domain),
          )
          ? url.href
          : null
        : ["instagram.com", "www.instagram.com"].includes(name)
          ? url.href
          : null;
    } catch {
      return null;
    }
  }
  function open() {
    dialog?.close();
    const box = element("dialog"),
      owner = scope();
    box.dataset.owner = owner;
    box.dataset.igMediaDialog = "true";
    box.className = "ig-account-media";
    box.setAttribute("aria-label", "Publicações da conta Instagram conectada");
    dialog = box;
    const generation = ++epoch;
    const current = () => dialog === box && box.open && generation === epoch && owner === scope();
    const heading = element("h2", "Publicações do Instagram");
    const feedback = element("p", "Consultando a conta conectada…");
    feedback.setAttribute("role", "status");
    feedback.setAttribute("aria-live", "polite");
    const list = element("div");
    list.dataset.igMediaItems = "true";
    const close = element("button", "Fechar"),
      more = element("button", "Carregar mais"),
      retry = element("button", "Consultar novamente");
    for (const button of [close, more, retry]) button.type = "button";
    let cursor = null,
      busy = false;
    const seen = new Set();
    const valid = (item) =>
      item &&
      typeof item.id === "string" &&
      /^\d{1,40}$/.test(item.id) &&
      ["IMAGE", "VIDEO", "CAROUSEL_ALBUM"].includes(item.media_type) &&
      (item.caption === null || typeof item.caption === "string") &&
      (item.timestamp === null ||
        (typeof item.timestamp === "string" && Number.isFinite(Date.parse(item.timestamp))));
    async function load(reset = false) {
      if (busy || !current()) return;
      busy = true;
      retry.disabled = more.disabled = true;
      box.setAttribute("aria-busy", "true");
      if (reset) {
        cursor = null;
        seen.clear();
        list.replaceChildren();
      }
      feedback.textContent = "Consultando a conta conectada…";
      try {
        const response = await host.request(
          "/instagram/media" + (cursor ? "?after=" + encodeURIComponent(cursor) : ""),
        );
        if (!current()) return;
        if (
          !Array.isArray(response.items) ||
          response.items.length > 25 ||
          !response.items.every(valid) ||
          !(
            response.next_cursor === null ||
            (typeof response.next_cursor === "string" &&
              /^[A-Za-z0-9_+/=-]{1,2048}$/.test(response.next_cursor))
          )
        )
          throw Error("Resposta das publicações não reconhecida.");
        for (const item of response.items) {
          if (seen.has(item.id)) continue;
          seen.add(item.id);
          const card = element("article");
          card.dataset.mediaId = item.id;
          const image = safeURL(
            item.media_type === "VIDEO" ? item.thumbnail_url : item.media_url,
            true,
          );
          if (image) {
            const picture = element("img");
            picture.alt = item.caption ? item.caption.slice(0, 120) : "Publicação do Instagram";
            picture.loading = "lazy";
            picture.referrerPolicy = "no-referrer";
            picture.src = image;
            picture.onerror = () => {
              picture.remove();
              card.prepend(
                element("p", "Imagem indisponível. Consulte a publicação no Instagram."),
              );
            };
            card.append(picture);
          }
          card.append(element("p", item.caption || "Legenda não informada pela Meta."));
          if (item.timestamp) {
            const time = element("time", new Date(item.timestamp).toLocaleString("pt-BR"));
            time.dateTime = item.timestamp;
            card.append(time);
          }
          const link = safeURL(item.permalink);
          if (link) {
            const anchor = element("a", "Abrir publicação no Instagram");
            anchor.href = link;
            anchor.target = "_blank";
            anchor.rel = "noopener noreferrer";
            card.append(anchor);
          }
          list.append(card);
        }
        cursor = response.next_cursor;
        feedback.textContent = seen.size
          ? `${seen.size} publicações carregadas da conta conectada.`
          : "Nenhuma publicação retornada pela Meta.";
        retry.hidden = true;
        more.hidden = !cursor;
      } catch (error) {
        if (current()) {
          cursor = null;
          list.replaceChildren();
          seen.clear();
          more.hidden = true;
          retry.hidden = false;
          feedback.textContent =
            error.message ||
            "Não foi possível consultar as publicações. Verifique a conexão e as permissões da conta.";
        }
      } finally {
        busy = false;
        if (current()) {
          retry.disabled = more.disabled = false;
          box.setAttribute("aria-busy", "false");
        }
      }
    }
    close.onclick = () => box.close();
    retry.onclick = () => load(true);
    more.onclick = () => load();
    box.addEventListener("close", () => {
      if (dialog === box) {
        dialog = null;
        epoch++;
      }
      box.remove();
    });
    more.hidden = retry.hidden = true;
    box.append(heading, feedback, list, more, retry, close);
    document.body.append(box);
    box.showModal();
    close.focus();
    load(true);
  }
  function paint(doc) {
    for (const row of doc.querySelectorAll(".sw, #cg .cn")) {
      if (
        row.querySelector("b")?.textContent.trim() !== "Instagram" ||
        row.querySelector("[data-ig-media-open]")
      )
        continue;
      const button = doc.createElement("button");
      button.type = "button";
      button.dataset.igMediaOpen = "true";
      button.textContent = "Ver publicações";
      button.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        open();
      };
      if (row.matches(".sw")) {
        const actions = doc.createElement("div"),
          existing = row.querySelector("button");
        actions.className = "ig-account-actions";
        if (existing) actions.append(existing);
        actions.append(button);
        row.append(actions);
      } else row.append(button);
    }
    if (!observed.has(doc) && doc.body) {
      observed.add(doc);
      new MutationObserver(() => paint(doc)).observe(doc.body, { childList: true, subtree: true });
    }
  }
  function mount() {
    paint(document);
    for (const frame of document.querySelectorAll("iframe")) {
      try {
        if (frame.contentDocument) paint(frame.contentDocument);
        if (!observed.has(frame)) {
          observed.add(frame);
          frame.addEventListener("load", mount);
        }
      } catch {
        /* Other origins cannot share account controls. */
      }
    }
  }
  const style = element("style");
  style.textContent =
    ".ig-account-media{margin:auto;width:760px;max-width:calc(100vw - 24px);max-height:calc(100dvh - 24px);overflow:auto;background:var(--w);color:var(--t);border:1px solid var(--b);border-radius:14px;padding:20px}.ig-account-media::backdrop{background:#0008}.ig-account-media [data-ig-media-items]{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:16px}.ig-account-media article{min-width:0;padding:12px;border:1px solid var(--b);border-radius:10px;overflow-wrap:anywhere}.ig-account-media img{width:100%;max-height:320px;object-fit:contain}.ig-account-media time,.ig-account-media a{display:block;margin-top:8px}.ig-account-media button,[data-ig-media-open]{min-height:44px;max-width:100%;padding:9px 12px;border:1px solid var(--b);border-radius:8px;color:var(--t);background:var(--w);font:inherit}.ig-account-media button{margin:12px 8px 0 0}";
  document.head.append(style);
  style.textContent +=
    ".ig-account-actions{display:flex;flex-direction:column;gap:8px;max-width:100%}";
  const render = window.render;
  if (typeof render === "function")
    window.render = function (...args) {
      if (dialog?.open && dialog.dataset.owner !== scope()) dialog.close();
      const result = render.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => dialog?.close());
  window.SocialMEIInstagramMedia = { open };
  queueMicrotask(mount);
})();
