/* Content preparation only. No channel transport or remote publication. */
const SocialMEIContentStudio = (() => {
  const byId = (id) => document.getElementById(id),
    model = SocialMEIContentDrafts;
  const profile = SocialMEIBusinessProfile.browserRepository();
  const repo = model.repository(localStorage, () => profile.scope());
  let scope,
    format = "story",
    draftId = null,
    media = null,
    file = null,
    objectUrl = null,
    uploadEpoch = 0,
    baseline = "",
    pending = null,
    opened = false;
  const fields = {
    title: "contentTitle",
    caption: "contentCaption",
    cta: "contentCta",
    hashtags: "contentHashtags",
  };
  const node = (tag, text) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const message = (text) => {
    byId("contentActionStatus").textContent = text;
  };
  const value = () => ({
    id: draftId,
    format,
    ...Object.fromEntries(Object.entries(fields).map(([key, id]) => [key, byId(id).value])),
    media,
    presentation: {
      topic: byId("dv4Topic").value,
      offering: byId("dv4Offering").value,
      objective: byId("dv4Objective").value,
      tone: byId("dv4Tone").value,
      alt: byId("dv4Alt").value,
      zoom: Number(byId("dv4Zoom").value || 1),
      x: Number(byId("contentPreviewStage").dataset.dv4X || 50),
      y: Number(byId("contentPreviewStage").dataset.dv4Y || 50),
      ...(byId("contentPreviewStage").dataset.thumbnail
        ? { thumbnail: byId("contentPreviewStage").dataset.thumbnail }
        : {}),
    },
  });
  const dirty = () => JSON.stringify(value()) !== baseline;
  function release() {
    const video = byId("contentPreviewStage").querySelector("video");
    if (video) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
  }
  function removeMedia() {
    uploadEpoch++;
    release();
    file = null;
    media = null;
    byId("contentMedia").value = "";
  }
  function load(item) {
    removeMedia();
    draftId = item?.id || null;
    format = item?.format || "story";
    media = item?.media || null;
    for (const [key, id] of Object.entries(fields)) byId(id).value = item?.[key] || "";
    const presentation = item?.presentation || {};
    for (const [key, id] of [
      ["topic", "dv4Topic"],
      ["offering", "dv4Offering"],
      ["objective", "dv4Objective"],
      ["tone", "dv4Tone"],
      ["alt", "dv4Alt"],
      ["zoom", "dv4Zoom"],
    ]) {
      const field = byId(id);
      field.value =
        presentation[key] ??
        (field.tagName === "SELECT" ? field.options[0].value : key === "zoom" ? 1 : "");
    }
    byId("contentPreviewStage").dataset.dv4X = String(presentation.x ?? 50);
    byId("contentPreviewStage").dataset.dv4Y = String(presentation.y ?? 50);
    byId("contentPreviewStage").dataset.thumbnail = presentation.thumbnail || "";
    baseline = JSON.stringify(value());
    message(item ? "Rascunho aberto neste navegador." : "");
    preview();
    if (item) document.dispatchEvent(new Event("socialmei-content-editor-open"));
  }
  function synchronize() {
    const next = profile.scope();
    if (scope !== next) {
      scope = next;
      pending = null;
      if (byId("contentConfirmModal").classList.contains("open")) closeModal("contentConfirmModal");
      const editor = repo.read().editor;
      load(editor);
      return true;
    }
    return false;
  }
  function preview() {
    const current = value(),
      video = file?.type.startsWith("video/");
    byId("contentPreviewFormat").textContent = model.FORMATS[format];
    const device = document.querySelector("[data-content-preview]");
    device.dataset.contentPreview = format;
    device.dataset.f = format;
    device.classList.toggle("empty", !file && !current.title && !current.caption && !current.cta);
    const tabs = [...document.querySelectorAll("[data-content-format]")];
    tabs.forEach((tab) => {
      const active = tab.dataset.contentFormat === format;
      tab.setAttribute("aria-selected", String(active));
      tab.setAttribute("aria-checked", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    document
      .querySelector(".content-formats")
      .style.setProperty("--content-format", ["story", "feed", "reel"].indexOf(format));
    byId("contentEditorPanel").setAttribute("aria-labelledby", "contentFormat-" + format);
    if (document.activeElement !== byId("contentPreviewTitle"))
      byId("contentPreviewTitle").textContent = current.title;
    if (document.activeElement !== byId("contentPreviewCaption"))
      byId("contentPreviewCaption").textContent = current.caption;
    byId("exactV4-ptg").textContent = current.hashtags;
    if (document.activeElement !== byId("exactV4-pcta"))
      byId("exactV4-pcta").textContent = current.cta;
    byId("contentCaptionCount").textContent = current.caption.length + " / 2200";
    byId("contentMedia").accept =
      format === "reel"
        ? "video/mp4,video/webm"
        : format === "feed"
          ? "image/jpeg,image/png,image/webp"
          : "image/jpeg,image/png,image/webp,video/mp4,video/webm";
    byId("contentMediaHelp").textContent =
      format === "feed"
        ? "Feed: imagem JPG, PNG ou WebP, até 10 MB. Sugestão de composição: 4:5."
        : format === "reel"
          ? "Reel: vídeo MP4 ou WebM, até 50 MB. Sugestão de composição: 9:16."
          : "Story: imagem até 10 MB ou vídeo até 50 MB. Sugestão de composição: 9:16.";
    byId("contentRemoveMedia").hidden = !media;
    byId("contentMediaStatus").textContent = file
      ? file.name + " · prévia local; arquivo não será salvo."
      : media
        ? "Referência: " + media.name + ". Selecione novamente o arquivo para visualizar."
        : "Nenhuma mídia selecionada. O texto pode ser salvo sem mídia.";
    if (file && !objectUrl) {
      const stage = byId("contentPreviewStage");
      stage.replaceChildren();
      objectUrl = URL.createObjectURL(file);
      const element = node(video ? "video" : "img");
      if (video) {
        element.controls = true;
        element.preload = "metadata";
        element.playsInline = true;
        element.setAttribute("aria-label", "Prévia do vídeo local");
      } else element.alt = "Prévia da mídia selecionada para " + model.FORMATS[format];
      element.addEventListener("error", () => {
        byId("contentMediaStatus").textContent =
          "O navegador não conseguiu exibir este arquivo. Confira o formato e o codec; não houve envio.";
      });
      element.src = objectUrl;
      stage.append(element);
    } else if (!file) {
      const placeholder = node("div");
      placeholder.className = "ph";
      placeholder.append(
        (() => {
          const icon = node("span");
          icon.setAttribute("aria-hidden", "true");
          icon.innerHTML = '<svg aria-hidden="true"><use href="#exactV4-img"></use></svg>';
          return icon.firstElementChild;
        })(),
        node("b", media ? "Selecione a mídia novamente" : "Seu conteúdo começa aqui"),
        node("p", media ? media.name : "Escolha um formato e escreva direto na tela."),
      );
      byId("contentPreviewStage").replaceChildren(placeholder);
    }
    document.dispatchEvent(new Event("socialmei-content-preview-change"));
  }
  function library() {
    const state = repo.read(),
      list = byId("contentDraftList");
    list.replaceChildren();
    const usable = state.status === "ready";
    byId("contentStorageStatus").textContent =
      state.status === "error"
        ? "Não foi possível ler os rascunhos. Nenhum conteúdo foi substituído."
        : !scope
          ? "Entre em uma sessão válida para usar rascunhos neste negócio."
          : "";
    for (const id of ["contentSave", "contentNew", "contentMedia"]) byId(id).disabled = !usable;
    byId("contentDraftCount").textContent =
      state.items.length + " de " + model.LIMIT + " rascunhos";
    if (!state.items.length) {
      const empty = node(
        "p",
        usable
          ? "Ainda não há rascunhos. Prepare seu primeiro conteúdo na aba Criar conteúdo."
          : "Rascunhos indisponíveis nesta sessão.",
      );
      empty.className = "content-library-empty";
      list.append(empty);
    }
    state.items.forEach((item) => {
      const row = node("article");
      row.className = "dc content-draft-row";
      row.dataset.contentDraft = item.id;
      const thumb = node("div");
      thumb.className = "th";
      thumb.innerHTML =
        '<svg aria-hidden="true"><use href="#exactV4-' + item.format + '"></use></svg>';
      if (item.presentation?.thumbnail) {
        const image = node("img");
        image.src = item.presentation.thumbnail;
        image.alt = "";
        thumb.append(image);
      }
      const info = node("div");
      info.className = "b";
      info.append(
        node("b", item.title),
        node(
          "small",
          model.FORMATS[item.format] +
            " · " +
            new Date(item.updatedAt).toLocaleString("pt-BR", { timeZone: APP_TIMEZONE }),
        ),
      );
      const actions = node("div");
      actions.className = "r content-draft-actions";
      for (const [action, label] of [
        ["edit", "Editar"],
        ["duplicate", "Duplicar"],
        ["delete", "Excluir"],
      ]) {
        const button = node("button", label);
        button.type = "button";
        button.dataset.contentAction = action;
        button.dataset.contentId = item.id;
        button.setAttribute("aria-label", label + " " + item.title);
        actions.append(button);
      }
      row.append(thumb, info, actions);
      list.append(row);
    });
    document.dispatchEvent(new Event("socialmei-content-drafts-change"));
  }
  function render() {
    synchronize();
    opened = true;
    let business = "Seu negócio";
    try {
      business =
        profile.read().profile?.businessName ||
        SocialMEIAuth.current?.negocio?.nome ||
        "Seu negócio";
    } catch {}
    byId("contentBusinessContext").textContent =
      business === "Seu negócio"
        ? "Use as informações reais do seu negócio. Nenhuma oferta ou preço é criado automaticamente."
        : business + " · prepare conteúdo com a sua voz.";
    byId("contentPreviewBusiness").textContent = business;
    byId("exactV4-bh").textContent = business;
    byId("contentPublicBusinessName").value = business;
    byId("contentPublicBusinessBio").value = profile.read().profile?.description || "";
    byId("contentBrandInitial").textContent = business[0].toUpperCase();
    preview();
    library();
  }
  function confirmation(title, text, action, label = "Continuar") {
    pending = { scope, action };
    byId("contentConfirmTitle").textContent = title;
    byId("contentConfirmMessage").textContent = text;
    byId("contentConfirmAction").textContent = label;
    openModal("contentConfirmModal");
  }
  function replaceEditor(action) {
    if (dirty())
      confirmation(
        "Descartar alterações não salvas?",
        "Seu texto atual não será salvo. Os rascunhos já salvos continuam disponíveis.",
        action,
        "Descartar e continuar",
      );
    else action();
  }
  byId("contentNew").addEventListener("click", () => {
    synchronize();
    replaceEditor(() => {
      load(null);
      try {
        repo.saveEditor(value(), scope);
      } catch (error) {
        message(error.message);
      }
      document.dispatchEvent(new Event("socialmei-content-editor-new"));
    });
  });
  byId("contentDraftForm").addEventListener("input", () => {
    synchronize();
    preview();
    message(
      dirty()
        ? "Alterações ainda não salvas como rascunho. Editor preservado somente neste navegador."
        : "",
    );
    try {
      repo.saveEditor(value(), scope);
    } catch (error) {
      message(error.message);
    }
  });
  byId("contentDraftForm").addEventListener("submit", (event) => {
    event.preventDefault();
    if (synchronize()) {
      library();
      return;
    }
    try {
      const title = byId("contentTitle");
      if (!title.value.trim()) {
        document.getElementById("exactV4-d3").open = true;
        title.classList.add("bad");
        title.focus();
      }
      const saved = repo.save(value(), scope);
      draftId = saved.id;
      baseline = JSON.stringify(value());
      repo.saveEditor(value(), scope);
      library();
      message("Rascunho salvo neste navegador. Nenhuma publicação foi feita.");
    } catch (error) {
      message(error.message);
    }
  });
  byId("contentMedia").addEventListener("change", async () => {
    if (synchronize()) {
      library();
      return;
    }
    const selected = byId("contentMedia").files[0];
    if (!selected) return;
    const request = ++uploadEpoch,
      expected = scope,
      expectedFormat = format;
    byId("contentMediaStatus").textContent = "Conferindo o arquivo local…";
    try {
      const metadata = await model.validateMedia(selected, format);
      if (request !== uploadEpoch || expected !== profile.scope() || expectedFormat !== format)
        return;
      release();
      file = selected;
      media = metadata;
      byId("contentPreviewStage").dataset.dv4X = "50";
      byId("contentPreviewStage").dataset.dv4Y = "50";
      byId("dv4Zoom").value = "1";
      preview();
      message("Mídia pronta para prévia local. Salve o texto se quiser continuar depois.");
    } catch (error) {
      if (request !== uploadEpoch) return;
      byId("contentMedia").value = "";
      byId("contentMediaStatus").textContent = error.message;
      message("Arquivo recusado. A mídia anterior foi preservada, se havia uma.");
    }
  });
  byId("contentRemoveMedia").addEventListener("click", () => {
    if (synchronize()) return;
    removeMedia();
    preview();
    message("Mídia removida apenas deste rascunho. Salve para confirmar.");
  });
  document.querySelector(".content-formats").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-content-format]");
    if (!tab) return;
    if (synchronize()) {
      library();
      return;
    }
    format = tab.dataset.contentFormat;
    if (
      media &&
      ((format === "reel" && !media.type.startsWith("video/")) ||
        (format === "feed" && !media.type.startsWith("image/")))
    ) {
      removeMedia();
      message("Selecione uma mídia compatível com o novo formato. Seu texto foi preservado.");
    }
    preview();
    try {
      repo.saveEditor(value(), scope);
    } catch (error) {
      message(error.message);
    }
  });
  document.querySelector(".content-formats").addEventListener("keydown", (event) => {
    const tabs = [...document.querySelectorAll("[data-content-format]")],
      index = tabs.indexOf(event.target);
    if (index < 0) return;
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % 3
        : event.key === "ArrowLeft"
          ? (index + 2) % 3
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? 2
              : null;
    if (next !== null) {
      event.preventDefault();
      tabs[next].click();
      tabs[next].focus();
    }
  });
  byId("contentDraftList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-content-action]");
    if (!button) return;
    if (synchronize()) {
      render();
      return;
    }
    const state = repo.read(),
      item = state.items.find((i) => i.id === button.dataset.contentId);
    if (!item) return;
    const execute = () => {
      try {
        if (button.dataset.contentAction === "edit") {
          load(item);
          byId("contentTitle").focus();
        } else if (button.dataset.contentAction === "duplicate") {
          const copy = repo.duplicate(item.id, scope);
          load(copy);
          library();
          message("Cópia criada somente neste navegador.");
        } else {
          repo.remove(item.id, scope);
          if (draftId === item.id) load(null);
          library();
          message("Rascunho local excluído.");
        }
      } catch (error) {
        message(error.message);
      }
    };
    if (button.dataset.contentAction === "delete")
      confirmation(
        "Excluir rascunho?",
        "Isso remove o texto salvo neste navegador. Nenhuma publicação externa será afetada.",
        execute,
        "Excluir rascunho",
      );
    else replaceEditor(execute);
  });
  byId("contentConfirmAction").addEventListener("click", async () => {
    const task = pending;
    pending = null;
    await closeModal("contentConfirmModal");
    if (task && task.scope === profile.scope()) task.action();
    else if (task) {
      render();
      message("A sessão mudou. A ação foi cancelada.");
    }
  });
  byId("contentCopy").addEventListener("click", async () => {
    if (synchronize()) return;
    const text = model.caption(value());
    if (!text) {
      message("Escreva uma legenda ou chamada antes de copiar.");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      message("Legenda copiada. Nenhuma mensagem ou postagem foi enviada.");
    } catch {
      message("Não foi possível copiar. Selecione o texto manualmente.");
    }
  });
  byId("contentExport").addEventListener("click", () => {
    if (synchronize()) return;
    try {
      const current = model.draft(value());
      const text = `${current.title}\nFormato: ${model.FORMATS[format]}\n\n${model.caption(current)}\n\nMídia: ${media?.name || "não selecionada"}\nUse o arquivo original separadamente. Preparação local; nenhuma publicação foi realizada.\n`;
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" }),
        url = URL.createObjectURL(blob),
        link = node("a");
      link.href = url;
      link.download = "socialmei-conteudo.txt";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      message("Texto de preparação gerado localmente. O arquivo de mídia não está incluído.");
    } catch (error) {
      message(error.message);
    }
  });
  document.addEventListener("socialmei-view-change", () => {
    if (currentView === "Divulgação") render();
    else {
      uploadEpoch++;
      release();
    }
  });
  document.addEventListener("socialmei-data-change", () => {
    if (opened && scope !== profile.scope()) {
      synchronize();
      if (currentView === "Divulgação") render();
    }
  });
  window.addEventListener("pagehide", () => {
    uploadEpoch++;
    removeMedia();
  });
  function simulationSnapshot() {
    synchronize();
    if (!scope || !file || !media) return null;
    return {
      scope,
      format,
      caption: model.caption(value()),
      media: { name: media.name, mime: media.type, size: media.size },
    };
  }
  function preparationSnapshot() {
    synchronize();
    if (!scope) return null;
    return {
      scope,
      title: byId("contentTitle").value,
      format,
      caption: model.caption(value()),
      media: media ? { name: media.name, mime: media.type, size: media.size } : null,
    };
  }
  function loadPreparation(item, onLoaded = () => {}) {
    synchronize();
    replaceEditor(() => {
      load({
        id: null,
        title: item.title,
        format: item.format,
        caption: item.caption,
        media: item.media?.[0]
          ? { name: item.media[0].name, type: item.media[0].mime, size: item.media[0].size }
          : null,
      });
      message(
        "Preparação compartilhada aberta. Texto não salvo localmente; mídia somente como referência.",
      );
      onLoaded();
    });
  }
  function openDraft(id, onLoaded = () => {}) {
    synchronize();
    const item = repo.read().items.find((item) => item.id === id);
    if (!item) return message("Rascunho indisponível neste negócio.");
    replaceEditor(() => {
      load(item);
      onLoaded();
    });
  }
  return Object.freeze({
    render,
    simulationSnapshot,
    preparationSnapshot,
    loadPreparation,
    openDraft,
  });
})();
