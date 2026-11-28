/* Authenticated image publishing. Provider credentials never enter this UI. */
(() => {
  const host = window.SocialMEIV22;
  if (!host?.remote || window.SocialMEIInstagramPublisher) return;
  let available = false,
    connected = false,
    scheduleAvailable = false,
    busy = false,
    dialog,
    previewURL,
    timer,
    account;
  const observed = new WeakSet(),
    frames = new WeakSet();
  const scope = () => `${host.identity?.usuario.id}:${host.identity?.negocio.id}`;
  const key = () => `socialmei-instagram-publication:${scope()}`;
  const owner = () => ["owner", "admin"].includes(host.identity?.papel);
  let attempt = null,
    accountEpoch = 0;
  try {
    attempt = JSON.parse(sessionStorage.getItem(key()) || "null");
  } catch {}
  function remember(value) {
    attempt = value;
    if (value) sessionStorage.setItem(key(), JSON.stringify(value));
    else sessionStorage.removeItem(key());
  }
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
      let calendar = card.querySelector("[data-instagram-calendar]");
      if (scheduleAvailable && !calendar) {
        calendar = doc.createElement("button");
        calendar.type = "button";
        calendar.className = "btn o";
        calendar.dataset.instagramCalendar = "1";
        calendar.textContent = "Calendário editorial";
        card.appendChild(calendar);
      }
      if (calendar) calendar.hidden = !(scheduleAvailable && owner());
      button.disabled = !(available && connected && owner()) || busy;
      button.title = !connected
        ? "Conecte o Instagram profissional"
        : !available
          ? "Publicação ainda não habilitada"
          : "Selecionar foto e confirmar publicação";
    }
  }
  function bind(doc) {
    if (!doc || observed.has(doc)) return;
    observed.add(doc);
    doc.addEventListener(
      "click",
      (e) => {
        const button = e.target.closest?.("[data-instagram-publish], [data-instagram-calendar]");
        if (!button || button.disabled) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        if (button.hasAttribute("data-instagram-calendar")) openCalendar();
        else open();
      },
      true,
    );
    const cards = doc.getElementById("cg");
    if (cards)
      new MutationObserver(() => inject(doc)).observe(cards, { childList: true, subtree: true });
    inject(doc);
  }
  function paint() {
    bind(document);
    inject(document);
    for (const frame of document.querySelectorAll("iframe")) {
      if (!frames.has(frame)) {
        frames.add(frame);
        frame.addEventListener("load", paint);
      }
      try {
        if (frame.contentDocument?.getElementById("cg")) {
          bind(frame.contentDocument);
          inject(frame.contentDocument);
        }
      } catch {}
    }
  }
  const status = (value) => {
    dialog.querySelector('[role="status"]').textContent = value;
  };
  function controls() {
    const form = dialog.querySelector("form");
    form.elements.image.disabled = busy || !!attempt;
    form.elements.caption.disabled = busy || !!attempt;
    form.querySelector('[type="submit"]').disabled = busy || !!attempt || !account;
    form.querySelector("[data-check]").hidden = !attempt;
    form.querySelector("[data-check]").disabled = busy;
    form.querySelector("[data-new]").hidden = !attempt;
    form.querySelector("[data-new]").disabled = busy;
    paint();
  }
  function result(row) {
    remember({ ...attempt, id: row.id, status: row.status });
    if (row.status === "published" && row.media_id) {
      status("Publicado no Instagram! ID: " + row.media_id);
    } else if (row.status === "created") {
      status("A Meta está processando a foto. Acompanharemos sem criar outra publicação.");
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (dialog.open && !document.hidden) check(true);
      }, 61000);
    } else if (row.status === "uncertain") {
      status(
        row.error_code === "media_processing_failed"
          ? "A Meta não concluiu o processamento da foto. Nenhuma repetição automática será feita."
          : "Resultado incerto. Confira o perfil antes de preparar outra foto; não repetiremos o envio.",
      );
    } else {
      status("Operação registrada. Aguarde e consulte o resultado. Não repetiremos o envio.");
    }
  }
  async function check(continueProcessing = false) {
    if (!attempt || busy) return;
    busy = true;
    controls();
    const identity = scope();
    try {
      const recent = await host.request("/instagram/publishing/recent");
      if (identity !== scope()) return;
      let row = recent.items.find((item) => item.request_id === attempt.request_id);
      if (row && row.status === "created" && continueProcessing) {
        row = await host.request(`/instagram/publishing/${row.id}/continue`, "POST", {});
      }
      if (identity !== scope()) return;
      if (row) result(row);
      else status("Nenhuma confirmação recebida. Confira o perfil antes de preparar outra foto.");
    } catch {
      status("Não foi possível consultar o resultado. O envio não será repetido automaticamente.");
    } finally {
      busy = false;
      controls();
    }
  }
  function build() {
    const style = document.createElement("style");
    style.textContent =
      ".ig-publish{margin:auto;color-scheme:dark;border:1px solid #49607f;border-radius:18px;width:min(520px,calc(100vw - 32px));max-height:calc(100dvh - 32px);overflow:auto;padding:22px;background:#142134;color:#eef3fa;box-shadow:0 20px 80px #0009}.ig-publish::backdrop{background:#09111bcc}.ig-publish form,.ig-publish label{display:grid;gap:10px}.ig-publish form{gap:16px}.ig-publish input,.ig-publish textarea{min-width:0;max-width:100%;padding:12px;border-radius:10px;border:1px solid #52637d;background:transparent;color:inherit;font:inherit}.ig-publish .ig-file{display:block;cursor:pointer;padding:12px;border:1px solid #52637d;border-radius:10px;min-height:44px}.ig-publish input[type=file]{position:absolute;width:1px;height:1px;padding:0;clip-path:inset(50%);overflow:hidden}.ig-publish textarea{min-height:100px;resize:vertical}.ig-publish button{min-height:44px;border:1px solid #52637d;border-radius:10px;padding:10px 15px;background:transparent;color:inherit;font:inherit;cursor:pointer}.ig-publish button:disabled{opacity:.55;cursor:default}.ig-publish .primary{background:#2975d6;border-color:#2975d6;color:white}.ig-publish .actions{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap}.ig-publish h2{font-size:20px;margin:0}.ig-publish p{font-size:14px;line-height:1.5;margin:0}.ig-publish img{width:100%;max-height:240px;object-fit:contain;border-radius:10px}.ig-publish.light{color-scheme:light;background:#fff;color:#162133}";
    document.head.appendChild(style);
    dialog = document.createElement("dialog");
    dialog.className = "ig-publish";
    dialog.setAttribute("aria-label", "Publicar foto no Instagram");
    dialog.innerHTML =
      '<form><h2>Publicar no Instagram</h2><p data-account>Confirmando o perfil…</p><p>Foto para o feed: JPEG, PNG ou WebP de até 2 MiB, entre 4:5 e 1,91:1. A cópia temporária expira em uma hora. A publicação real só ocorre ao confirmar.</p><label class="ig-file" for="ig-photo-input">Selecionar foto<span data-filename></span></label><input id="ig-photo-input" aria-label="Selecionar foto" type="file" name="image" accept="image/jpeg,image/png,image/webp" required><img alt="Prévia da foto selecionada" hidden><label>Legenda<textarea name="caption" maxlength="2200" required placeholder="Escreva sua legenda"></textarea></label><p role="status" aria-live="polite"></p><div class="actions"><button type="button" data-cancel>Fechar</button><button type="button" data-check hidden>Consultar resultado</button><button type="button" data-new hidden>Preparar outra foto</button><button class="primary" type="submit">Confirmar publicação</button></div></form>';
    document.body.appendChild(dialog);
    const form = dialog.querySelector("form");
    dialog.addEventListener("cancel", (e) => {
      if (busy) e.preventDefault();
    });
    dialog.addEventListener("close", () => {
      clearTimeout(timer);
      accountEpoch++;
    });
    dialog.querySelector("[data-cancel]").onclick = () => {
      if (!busy) dialog.close();
    };
    dialog.querySelector("[data-check]").onclick = () => check(true);
    dialog.querySelector("[data-new]").onclick = () => {
      if (busy) return;
      if (
        attempt?.status !== "published" &&
        !confirm(
          "O resultado anterior não foi confirmado. Confira no Instagram para evitar duplicação. Deseja preparar outra foto?",
        )
      )
        return;
      clearTimeout(timer);
      remember(null);
      form.reset();
      status("");
      if (previewURL) URL.revokeObjectURL(previewURL);
      dialog.querySelector("img").hidden = true;
      controls();
    };
    form.elements.image.onchange = () => {
      if (previewURL) URL.revokeObjectURL(previewURL);
      const file = form.elements.image.files[0],
        image = dialog.querySelector("img");
      image.hidden = true;
      dialog.querySelector("[data-filename]").textContent = file ? file.name : "";
      if (!file) return;
      if (
        file.size > 2 * 1024 * 1024 ||
        !["image/jpeg", "image/png", "image/webp"].includes(file.type)
      ) {
        status("Selecione uma foto JPEG, PNG ou WebP de até 2 MiB.");
        form.elements.image.value = "";
        return;
      }
      previewURL = URL.createObjectURL(file);
      image.src = previewURL;
      image.hidden = false;
      status("");
    };
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (busy || attempt || !account || !owner()) return;
      const file = form.elements.image.files[0];
      if (!file || file.size > 2 * 1024 * 1024) return;
      busy = true;
      remember({ request_id: crypto.randomUUID(), status: "uploading" });
      controls();
      const identity = scope();
      const selectedAccount = { ...account };
      status("Enviando a foto e solicitando a publicação. Não feche esta janela.");
      try {
        const encoded = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = reject;
          reader.onload = () => resolve(String(reader.result).split(",")[1]);
          reader.readAsDataURL(file);
        });
        const media = await host.request("/instagram/publishing/upload", "POST", {
          request_id: attempt.request_id,
          image_base64: encoded,
        });
        if (identity !== scope()) return;
        // Persist the request id before the only publication call; preserve it across reloads.
        remember({ ...attempt, status: "submitting" });
        const row = await host.request("/instagram/publishing/image", "POST", {
          request_id: attempt.request_id,
          media_id: media.media_id,
          connection_id: selectedAccount.connection_id,
          caption: form.elements.caption.value,
        });
        if (identity === scope()) result(row);
      } catch (error) {
        if (identity !== scope()) return;
        if (attempt.status === "uploading") {
          remember(null);
          status(
            error.message || "Não foi possível enviar a foto. Nenhuma publicação foi solicitada.",
          );
        } else
          status(
            "Resultado não confirmado. Consulte o resultado; não repetiremos o envio automaticamente.",
          );
      } finally {
        busy = false;
        controls();
      }
    });
  }
  async function open() {
    if (!dialog) build();
    dialog.classList.toggle(
      "light",
      document.documentElement.getAttribute("data-theme") === "light" ||
        document.body.classList.contains("light"),
    );
    const epoch = ++accountEpoch;
    account = null;
    dialog.querySelector("[data-account]").textContent = "Confirmando o perfil…";
    dialog.showModal();
    controls();
    try {
      const confirmed = await host.request("/instagram/publishing/account");
      if (epoch !== accountEpoch || !dialog.open) return;
      account = confirmed;
      dialog.querySelector("[data-account]").textContent =
        "Publicar no perfil @" + account.username;
    } catch {
      if (epoch !== accountEpoch || !dialog.open) return;
      account = null;
      dialog.querySelector("[data-account]").textContent =
        "Perfil não confirmado. Reabra esta janela para conferir a conexão.";
    }
    controls();
    if (attempt) check(true);
  }

  function datePayload(value, timezone) {
    const local = new Date(value);
    if (!Number.isFinite(local.getTime()))
      throw new Error("Informe uma data e um horário válidos.");
    const pad = (number) => String(number).padStart(2, "0");
    const entered = Date.UTC(
      ...value.split(/[-T:]/).map((part, index) => Number(part) - (index === 1 ? 1 : 0)),
    );
    const offset = -local.getTimezoneOffset();
    if (entered !== local.getTime() + offset * 60000)
      throw new Error("Este horário não existe no fuso informado.");
    return {
      scheduled_at:
        value +
        (offset < 0 ? "-" : "+") +
        pad(Math.floor(Math.abs(offset) / 60)) +
        ":" +
        pad(Math.abs(offset) % 60),
      timezone,
    };
  }

  async function openCalendar() {
    if (!scheduleAvailable || !owner() || document.querySelector("#sm-instagram-calendar")) return;
    const originalScope = scope();
    const calendar = document.createElement("dialog");
    calendar.id = "sm-instagram-calendar";
    calendar.style.cssText =
      "color:CanvasText;background:Canvas;max-width:min(40rem,95vw);max-height:90vh";
    calendar.setAttribute("aria-labelledby", "sm-instagram-calendar-title");
    calendar.innerHTML =
      '<form method="dialog"><button type="submit">Fechar</button></form>' +
      '<h2 id="sm-instagram-calendar-title">Calendário editorial</h2><p role="status"></p>' +
      "<form data-schedule hidden><p data-profile></p>" +
      '<label>URL HTTPS da foto JPEG <input name="image" type="url" required maxlength="2048"></label>' +
      '<label>Legenda <textarea name="caption" required maxlength="2200"></textarea></label>' +
      '<label>Data e horário <input name="when" type="datetime-local" required></label>' +
      '<p data-timezone></p><button type="submit">Agendar foto</button></form><ul></ul>';
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const valid = () => calendar.open && originalScope === scope();
    const request = (suffix = "", options) =>
      host.request("/instagram/publishing/scheduled" + suffix, options?.method, options?.body);
    const status = calendar.querySelector('[role="status"]');
    const form = calendar.querySelector("[data-schedule]");
    const list = calendar.querySelector("ul");
    const submission = form.querySelector('button[type="submit"]');
    const requestKey = "socialmei-instagram-schedule:" + originalScope;
    const states = {
      scheduled: "Agendada",
      creating: "Preparando",
      created: "Processando",
      publishing: "Publicando",
      published: "Publicada",
      failed: "Falhou",
      cancelled: "Cancelada",
      uncertain: "Resultado incerto. Confira no Instagram antes de criar outra publicação.",
    };
    let pending = false;
    let confirmedAccount;
    let approval;
    try {
      approval = JSON.parse(sessionStorage.getItem(requestKey));
    } catch {}
    const showError = (error) => {
      if (valid()) status.textContent = error.message || "Não foi poss?vel concluir.";
    };
    const run = async (action) => {
      if (pending || !valid()) return;
      pending = true;
      calendar.querySelectorAll("fieldset, button:not([type=submit])").forEach((node) => {
        node.disabled = true;
      });
      submission.disabled = true;
      try {
        await action();
      } catch (error) {
        showError(error);
      } finally {
        pending = false;
        calendar.querySelectorAll("fieldset, button:not([type=submit])").forEach((node) => {
          node.disabled = false;
        });
        submission.disabled = false;
      }
    };
    const history = document.createElement("details");
    const historyTitle = document.createElement("summary");
    historyTitle.textContent = "Histórico de publicações";
    const historyRows = document.createElement("ul");
    const historyStatus = document.createElement("p");
    historyStatus.setAttribute("role", "status");
    history.append(historyTitle, historyStatus, historyRows);
    calendar.append(history);
    history.addEventListener("toggle", () => {
      if (!history.open || historyRows.children.length) return;
      run(async () => {
        const { items } = await host.request("/instagram/publishing/recent");
        if (!valid()) return;
        historyStatus.textContent = items.length ? "" : "Nenhuma publicação registrada.";
        for (const row of items) {
          const li = document.createElement("li");
          li.textContent = new Date(row.scheduled_at || row.created_at).toLocaleString("pt-BR") +
            " · " + (states[row.status] || row.status);
          if (row.status === "published") {
            const button = document.createElement("button");
            const metrics = document.createElement("span");
            metrics.setAttribute("role", "status");
            button.type = "button";
            button.textContent = "Consultar engajamento";
            button.addEventListener("click", () => run(async () => {
              const result = await host.request("/instagram/publishing/" + row.id + "/engagement", "POST", {});
              if (valid()) metrics.textContent = " Curtidas: " + (result.like_count ?? "indisponível") +
                " · Comentários: " + (result.comments_count ?? "indisponível");
            }));
            li.append(button, metrics);
          }
          historyRows.append(li);
        }
      });
    });
    async function load() {
      const rows = await request();
      if (!valid()) return;
      const items = rows.items;
      if (approval && items.some((row) => row.request_id === approval.request_id)) {
        sessionStorage.removeItem(requestKey);
        approval = null;
      }
      list.replaceChildren();
      status.textContent = items.length ? "" : "Nenhuma publicação agendada.";
      for (const row of items) {
        const li = document.createElement("li");
        const time = new Date(row.scheduled_at).toLocaleString("pt-BR", { timeZone: row.timezone });
        li.textContent =
          time +
          " (" +
          row.timezone +
          ") ? " +
          (states[row.status] || row.status) +
          " — " +
          row.caption;
        if (row.status === "scheduled") {
          const edit = document.createElement("form");
          const fieldset = document.createElement("fieldset");
          const date = document.createElement("input");
          date.type = "datetime-local";
          date.required = true;
          date.setAttribute("aria-label", "Nova data e horário (" + timezone + ")");
          const move = document.createElement("button");
          move.textContent = "Reagendar";
          const cancel = document.createElement("button");
          cancel.type = "button";
          cancel.textContent = "Cancelar publicação";
          edit.addEventListener("submit", (event) => {
            event.preventDefault();
            run(async () => {
              await request("/" + row.id, {
                method: "PATCH",
                body: { ...datePayload(date.value, timezone), revision: row.revision },
              });
              await load();
            });
          });
          cancel.addEventListener("click", () => {
            if (!window.confirm("Cancelar esta publicação agendada?")) return;
            run(async () => {
              await request("/" + row.id + "/cancel", {
                method: "POST",
                body: { revision: row.revision },
              });
              await load();
            });
          });
          fieldset.append(date, move, cancel);
          edit.append(fieldset);
          li.append(edit);
        }
        list.append(li);
      }
    }
    calendar.addEventListener(
      "close",
      () => {
        clearInterval(scopeTimer);
        calendar.remove();
      },
      { once: true },
    );
    document.body.append(calendar);
    calendar.showModal();
    const scopeTimer = setInterval(() => {
      if (!valid()) calendar.close();
    }, 250);
    calendar.querySelector("[data-timezone]").textContent = "Fuso deste dispositivo: " + timezone;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      run(async () => {
        if (!confirmedAccount) return;
        const values = new FormData(form);
        const body = {
          ...datePayload(values.get("when"), timezone),
          connection_id: confirmedAccount.connection_id,
          image_url: values.get("image").trim(),
          caption: values.get("caption"),
        };
        const digest = await crypto.subtle.digest(
          "SHA-256",
          new TextEncoder().encode(JSON.stringify(body)),
        );
        if (!valid()) return;
        const fingerprint = Array.from(new Uint8Array(digest), (byte) =>
          byte.toString(16).padStart(2, "0"),
        ).join("");
        if (approval && approval.fingerprint !== fingerprint) {
          throw new Error(
            "Há uma tentativa sem confirmação. Reabra o calendário e confira a lista antes de agendar.",
          );
        }
        const id = approval?.request_id || crypto.randomUUID();
        approval = { request_id: id, fingerprint };
        sessionStorage.setItem(requestKey, JSON.stringify(approval));
        try {
          await request("", { method: "POST", body: { ...body, request_id: id } });
        } catch (error) {
          if (valid() && [400, 403, 409, 422].includes(error.status)) {
            sessionStorage.removeItem(requestKey);
            approval = null;
          }
          throw error;
        }
        if (!valid()) return;
        sessionStorage.removeItem(requestKey);
        approval = null;
        form.reset();
        await load();
      });
    });
    await run(load);
    if (!valid()) return;
    try {
      confirmedAccount = await host.request("/instagram/publishing/account");
      if (!valid()) return;
      calendar.querySelector("[data-profile]").textContent =
        "Instagram: @" + confirmedAccount.username;
      form.hidden = false;
    } catch {
      if (valid()) status.textContent = "Confirme a conexão do Instagram para agendar uma foto.";
    }
  }

  async function refresh() {
    const activeScope = scope();
    try {
      const [pub, ig] = await Promise.all([
        host.request("/instagram/publishing/status"),
        host.request("/instagram/meta/status"),
      ]);
      if (activeScope !== scope()) return;
      scheduleAvailable = pub.schedule_available === true;
      connected = ig.status === "connected" && ig.credential_available === true;
      available = pub.available === true && pub.connected === true && pub.upload_available === true;
    } catch {
      if (activeScope !== scope()) return;
      available = connected = scheduleAvailable = false;
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
