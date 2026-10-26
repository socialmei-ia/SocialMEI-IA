// prettier-ignore-file
/* V22 authenticated Instagram publication (one public JPEG URL per post). */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInstagramPublisher) return;
  let available = false,
    connected = false,
    busy = false,
    dialog;
  let attemptId = null;
  const owners = () => ["owner", "admin"].includes(host.identity?.papel);
  const canPublish = () => available && connected && owners() && !busy;
  const observed = new WeakSet();
  function inject(doc) {
    for (const card of doc.querySelectorAll("#cg .cn")) {
      if (card.querySelector("b")?.textContent.trim() !== "Instagram") continue;
      let button = card.querySelector("[data-instagram-publish]");
      if (!button) {
        button = doc.createElement("button");
        button.type = "button";
        button.className = "btn o";
        button.dataset.instagramPublish = "1";
        button.textContent = "Publicar foto";
        card.appendChild(button);
      }
      button.disabled = !canPublish();
      button.title = !connected
        ? "Conecte o Instagram profissional"
        : !available
          ? "Publicação ainda não habilitada"
          : "Publicar uma imagem JPEG pública";
    }
  }
  function bind(doc) {
    if (!doc || observed.has(doc)) return;
    observed.add(doc);
    doc.addEventListener(
      "click",
      (e) => {
        const button = e.target.closest?.("[data-instagram-publish]");
        if (!button || button.disabled) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        open();
      },
      true,
    );
    const cards = doc.getElementById("cg");
    if (cards)
      new MutationObserver(() => inject(doc)).observe(cards, {
        childList: true,
        subtree: true,
      });
    inject(doc);
  }
  function paint() {
    bind(document);
    for (const frame of document.querySelectorAll("iframe")) {
      try {
        if (frame.contentDocument?.getElementById("cg")) bind(frame.contentDocument);
      } catch {}
    }
    inject(document);
  }
  function open() {
    if (!dialog) {
      const style = document.createElement("style");
      style.textContent =
        ".ig-publish{border:1px solid #49607f;border-radius:18px;width:min(520px,calc(100vw - 32px));max-width:100%;padding:22px;background:#142134;color:#eef3fa;box-shadow:0 20px 80px #0009}.ig-publish::backdrop{background:#09111bcc}.ig-publish form,.ig-publish label{display:grid;gap:10px}.ig-publish form{gap:16px}.ig-publish label{font-weight:600}.ig-publish input,.ig-publish textarea{padding:12px;border-radius:10px;border:1px solid #52637d;background:#0c1624;color:#eef3fa;font:inherit}.ig-publish textarea{min-height:115px;resize:vertical}.ig-publish button{border:1px solid #52637d;border-radius:10px;padding:10px 15px;background:#253c58;color:#eef3fa;font:inherit;cursor:pointer}.ig-publish button:disabled{opacity:.55;cursor:default}.ig-publish .primary{background:#2975d6;border-color:#2975d6}.ig-publish .actions{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap}.ig-publish h2{font-size:20px}.ig-publish p{font-size:13px;line-height:1.5}";
      document.head.appendChild(style);
      dialog = document.createElement("dialog");
      dialog.className = "ig-publish";
      dialog.innerHTML = [
        '<form id="ig-photo-form">',
        "<h2>Publicar no Instagram</h2>",
        "<p>Primeira etapa: envie uma foto JPEG já disponível numa URL HTTPS pública. A publicação só é feita ao confirmar.</p>",
        '<label>Link público da foto <input type="url" name="image" required maxlength="2048" autocomplete="off" placeholder="https://exemplo.com/foto.jpg"></label>',
        '<label>Legenda <textarea name="caption" required maxlength="2200" placeholder="Escreva sua legenda"></textarea></label>',
        '<p role="status" aria-live="polite"></p>',
        '<div class="actions"><button type="button" data-cancel>Cancelar</button><button class="primary" type="submit">Publicar foto</button></div>',
        "</form>",
      ].join("");
      document.body.appendChild(dialog);
      const form = dialog.querySelector("form");
      dialog.querySelector("[data-cancel]").addEventListener("click", () => {
        if (!busy) dialog.close();
      });
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!canPublish()) return;
        busy = true;
        paint();
        const status = form.querySelector('[role="status"]');
        const submit = form.querySelector('[type="submit"]');
        submit.disabled = true;
        status.textContent = "Solicitando publicação à Meta. Não feche esta janela.";
        try {
          attemptId ||= crypto.randomUUID();
          const result = await host.request("/instagram/publishing/image", "POST", {
            request_id: attemptId,
            image_url: form.elements.image.value.trim(),
            caption: form.elements.caption.value,
          });
          if (result.status === "published") {
            status.textContent = "Publicado no Instagram! ID: " + result.media_id;
            attemptId = null;
          } else {
            status.textContent =
              "Resultado não confirmado (" +
              result.status +
              "). Confira no Instagram antes de fazer outra tentativa.";
          }
        } catch {
          status.textContent =
            "Não foi possível confirmar a publicação. Confira o Instagram antes de tentar novamente.";
        } finally {
          busy = false;
          submit.disabled = false;
          paint();
        }
      });
    }
    attemptId = null;
    dialog.querySelector("form").reset();
    dialog.querySelector('[role="status"]').textContent = "";
    dialog.showModal();
  }
  async function refresh() {
    try {
      const [pub, ig] = await Promise.all([
        host.request("/instagram/publishing/status"),
        host.request("/instagram/meta/status"),
      ]);
      connected = ig.status === "connected" && ig.credential_available === true;
      available = pub.available === true && pub.connected === true;
    } catch {
      available = connected = false;
    }
    paint();
    return { available, connected };
  }
  const previousRender = render;
  render = function (...args) {
    const value = previousRender(...args);
    paint();
    return value;
  };
  window.SocialMEIInstagramPublisher = { refresh };
  host.ready.then(refresh);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
  paint();
})();
