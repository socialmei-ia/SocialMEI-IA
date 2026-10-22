/* V4 parity on official stores: drafting, suggestion tools and preview controls. */
(() => {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("contentStudioView");
    const form = document.getElementById("contentDraftForm");
    if (!root || !form) return;
    const $ = (id) => root.querySelector("#" + id);
    const status = $("contentActionStatus");
    const draftModel = SocialMEIContentDrafts;
    const scope = () => SocialMEIBusinessProfile.browserRepository().scope();
    const repository = draftModel.repository(localStorage, scope);
    const activeFormat = () =>
      root.querySelector('[data-content-format][aria-selected="true"]')?.dataset.contentFormat ||
      "feed";
    const node = (tag, text, klass) => {
      const el = document.createElement(tag);
      if (text !== undefined) el.textContent = text;
      if (klass) el.className = klass;
      return el;
    };
    const action = (title, onClick) => {
      const b = node("button", title, "management-button");
      b.type = "button";
      b.addEventListener("click", onClick);
      return b;
    };
    const formLine = (label, control) => {
      const wrap = node("label", label);
      wrap.append(control);
      return wrap;
    };
    const text = (id, placeholder) => {
      const el = node("input");
      el.id = id;
      el.type = "text";
      el.placeholder = placeholder;
      el.maxLength = 160;
      return el;
    };
    const options = (id, items) => {
      const select = node("select");
      select.id = id;
      for (const [value, title] of items) {
        const option = node("option", title);
        option.value = value;
        select.append(option);
      }
      return select;
    };
    const creator = node("section", undefined, "dv4-original-tools");
    creator.innerHTML =
      '<div class="dv4-section-head"><h3>Sugestões para sua divulgação</h3>' +
      '<p>Mesmo fluxo do HTML V4: tema, serviço, objetivo e tom. Modelo local, não IA.</p></div>';
    const fields = node("div", undefined, "dv4-original-fields");
    fields.append(
      formLine("Tema", text("dv4Topic", "Ex.: Meu trabalho")),
      formLine("Produto ou serviço", text("dv4Offering", "Ex.: corte de cabelo")),
      formLine("Objetivo", options("dv4Objective", [
        ["informar", "Informar"],
        ["apresentar", "Apresentar serviço"],
        ["convidar", "Convidar para conversar"],
      ])),
      formLine("Tom", options("dv4Tone", [
        ["simples", "Simples"],
        ["acolhedor", "Acolhedor"],
        ["profissional", "Profissional"],
      ])),
    );
    const suggestions = node("div", undefined, "dv4-original-suggestions");
    suggestions.id = "dv4OriginalSuggestions";
    creator.append(fields);
    creator.append(action("Sugerir três legendas", () => {
      const topic = $("dv4Topic").value.trim();
      if (!topic) {
        status.textContent = "Escreva um tema para receber sugestões locais.";
        $("dv4Topic").focus();
        return;
      }
      try {
        const res = SocialMEIContentPreparation.captionAlternatives({
          topic,
          offering: $("dv4Offering").value,
          objective: $("dv4Objective").value,
          tone: $("dv4Tone").value,
          business: $("contentPreviewBusiness").textContent,
        });
        suggestions.replaceChildren();
        res.alternatives.forEach((caption, index) => {
          const card = node("article", undefined, "dv4-suggestion");
          card.append(node("p", caption));
          card.append(action("Usar legenda " + (index + 1), () => {
            const existing = $("contentCaption").value.trim();
            if (existing && !window.confirm("Substituir a legenda que você já escreveu?"))
              return;
            $("contentCaption").value = caption;
            $("contentCaption").dispatchEvent(new Event("input", { bubbles: true }));
            $("contentCaption").focus();
            status.textContent = "Legenda aplicada. Revise e salve; nada foi publicado.";
          }));
          suggestions.append(card);
        });
        status.textContent =
          "Três sugestões criadas por regras locais. Confirme informações antes de publicar.";
      } catch (error) {
        status.textContent = error.message;
      }
    }));
    creator.append(suggestions);
    root.querySelector("#contentCreatePanel .dv4-progress").after(creator);

    const previews = node("div", undefined, "dv4-original-preview-controls");
    const fullscreen = action("Tela cheia", () => {
      const on = !root.classList.contains("dv4-fullscreen");
      root.classList.toggle("dv4-fullscreen", on);
      fullscreen.textContent = on ? "Fechar tela cheia" : "Tela cheia";
      if (on) fullscreen.focus();
    });
    const light = action("Feed claro", () => {
      root.classList.toggle("dv4-feed-light");
      light.setAttribute("aria-pressed", String(root.classList.contains("dv4-feed-light")));
    });
    light.setAttribute("aria-pressed", "false");
    const safe = node("input");
    safe.type = "checkbox";
    safe.id = "dv4SafeArea";
    const zoom = node("input");
    zoom.type = "range";
    zoom.id = "dv4Zoom";
    zoom.min = "1";
    zoom.max = "2";
    zoom.step = "0.05";
    zoom.value = "1";
    const alt = text("dv4Alt", "Descrição da imagem para acessibilidade");
    alt.maxLength = 180;
    const thumb = $("contentPreviewStage");
    const updateMedia = () => {
      const media = thumb.querySelector("img,video");
      if (media) {
        media.style.transform = "scale(" + zoom.value + ")";
        if (media.tagName === "IMG") media.alt = alt.value.trim() || "Prévia da imagem local";
      }
      thumb.style.setProperty("--dv4-zoom", zoom.value);
    };
    for (const t of ["input", "change"]) zoom.addEventListener(t, updateMedia);
    alt.addEventListener("input", updateMedia);
    safe.addEventListener("change", () =>
      root.classList.toggle("dv4-safe-area", safe.checked),
    );
    previews.append(
      fullscreen,
      light,
      formLine("Mostrar área segura", safe),
      formLine("Zoom da mídia", zoom),
      formLine("Texto alternativo da prévia", alt),
    );
    root.querySelector(".content-preview-heading").after(previews);
    thumb.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      if (!thumb.querySelector("img,video")) return;
      event.preventDefault();
      const x = Number(thumb.dataset.dv4X || "50");
      const y = Number(thumb.dataset.dv4Y || "50");
      const dx = event.key === "ArrowRight" ? -5 : event.key === "ArrowLeft" ? 5 : 0;
      const dy = event.key === "ArrowDown" ? -5 : event.key === "ArrowUp" ? 5 : 0;
      thumb.dataset.dv4X = String(Math.max(0, Math.min(100, x + dx)));
      thumb.dataset.dv4Y = String(Math.max(0, Math.min(100, y + dy)));
      thumb.style.setProperty("--dv4-x", thumb.dataset.dv4X + "%");
      thumb.style.setProperty("--dv4-y", thumb.dataset.dv4Y + "%");
    });
    thumb.tabIndex = 0;
    thumb.setAttribute("aria-label", "Prévia da mídia; use setas para ajustar a posição");
    new MutationObserver(updateMedia).observe(thumb, { childList: true });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && root.classList.contains("dv4-fullscreen")) {
        fullscreen.click();
        return;
      }
      if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "s" &&
        !root.hidden &&
        root.offsetParent !== null
      ) {
        event.preventDefault();
        $("contentSave").click();
      }
    });

    root.querySelector(".content-editor-actions").append(
      action("Copiar publicação completa", async () => {
        const body = [
          $("contentTitle").value.trim(),
          draftModel.FORMATS[activeFormat()],
          $("contentCaption").value.trim(),
          $("contentCta").value.trim(),
          $("contentHashtags").value.trim(),
        ].filter(Boolean).join("\n\n");
        if (!body) return;
        try {
          await navigator.clipboard.writeText(body);
          status.textContent = "Publicação completa copiada. Nenhum envio foi realizado.";
        } catch {
          status.textContent = "Não foi possível copiar. Selecione o texto manualmente.";
        }
      }),
    );
    const filterBar = node("section", undefined, "dv4-draft-filter");
    const search = text("dv4DraftQuery", "Buscar rascunho");
    search.type = "search";
    const format = options("dv4DraftFormat", [
      ["", "Todos os formatos"],
      ["story", "Story"],
      ["feed", "Feed"],
      ["reel", "Reel"],
    ]);
    const order = options("dv4DraftOrder", [
      ["recent", "Mais recentes"],
      ["old", "Mais antigos"],
      ["az", "A–Z"],
    ]);
    filterBar.append(
      formLine("Buscar", search),
      formLine("Formato", format),
      formLine("Ordenar", order),
    );
    $("contentDraftList").before(filterBar);
    let updating = false;
    const applyDraftFilters = () => {
      const state = repository.read();
      if (state.status !== "ready") return;
      const items = state.items.filter((item) =>
        (!format.value || item.format === format.value) &&
        (item.title + " " + item.caption + " " + item.cta)
          .toLocaleLowerCase("pt-BR")
          .includes(search.value.toLocaleLowerCase("pt-BR")),
      );
      items.sort((a, b) =>
        order.value === "az"
          ? a.title.localeCompare(b.title, "pt-BR")
          : order.value === "old"
            ? Date.parse(a.updatedAt) - Date.parse(b.updatedAt)
            : Date.parse(b.updatedAt) - Date.parse(a.updatedAt),
      );
      const allowed = new Set(items.map((item) => item.id));
      const pos = new Map(items.map((item, index) => [item.id, index]));
      const list = $("contentDraftList");
      updating = true;
      const cards = [...list.querySelectorAll("[data-content-draft]")];
      cards.sort((a, b) => (pos.get(a.dataset.contentDraft) ?? 1000) - (pos.get(b.dataset.contentDraft) ?? 1000));
      cards.forEach((card) => {
        card.hidden = !allowed.has(card.dataset.contentDraft);
        list.append(card);
      });
      updating = false;
    };
    for (const input of [search, format, order])
      input.addEventListener(input === search ? "input" : "change", applyDraftFilters);
    const list = $("contentDraftList");
    new MutationObserver(() => {
      if (!updating) applyDraftFilters();
    }).observe(list, { childList: true });
    root.querySelector("#contentDraftsPanel").append(
      action("Exportar backup JSON dos rascunhos", () => {
        const state = repository.read();
        if (state.status !== "ready" || !state.items.length) {
          status.textContent = "Nenhum rascunho disponível para exportar.";
          return;
        }
        const blob = new Blob(
          [JSON.stringify({ app: "socialmei-native-drafts", version: 1, drafts: state.items }, null, 2)],
          { type: "application/json" },
        );
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "rascunhos-socialmei.json";
        link.click();
        URL.revokeObjectURL(url);
        status.textContent = "Backup exportado. Guarde-o em local seguro.";
      }),
    );
  });
})();
