/* Original Divulgação V4 interactions, connected to the official scoped draft editor. */
(() => {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    const host = document.getElementById("contentStudioView"),
      root = host?.querySelector(".exact-v4-root");
    if (!root) return;
    const $ = (id) => root.querySelector("#" + id) || document.getElementById(id),
      $$ = (selector) => [...root.querySelectorAll(selector)],
      scope = () => SocialMEIBusinessProfile.browserRepository().scope(),
      repo = SocialMEIContentDrafts.repository(localStorage, scope),
      form = $("contentDraftForm"),
      stage = root.querySelector(".stage"),
      media = $("contentPreviewStage"),
      device = $("contentPreviewDevice"),
      reduced = () => matchMedia("(prefers-reduced-motion:reduce)").matches;
    let toastTimer = 0,
      stepTimer = 0,
      pendingEditorFocus = false,
      fullscreenFocus = null,
      priorOverflow = "",
      drag = null,
      moved = false;
    const toast = (text, error = false, action = null) => {
      const node = $("exactV4-toast");
      node.replaceChildren(document.createTextNode(text));
      if (action) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "tb";
        button.textContent = action[0];
        button.addEventListener("click", () => {
          action[1]();
          node.className = "";
        });
        node.append(" ", button);
      }
      node.className = "on" + (error ? " e" : "") + (action ? " a" : "");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => (node.className = ""), action ? 6000 : 3200);
    };
    const buttonState = (button, state) => {
      button.dataset.s = state;
      if (state !== "load") setTimeout(() => delete button.dataset.s, 1200);
    };
    const input = (id, value) => {
      const element = $(id);
      element.value = value;
      element.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const get = (id) => $(id).value.trim();
    const openStep = (number) =>
      $$("details.st").forEach((details, index) => (details.open = index === number - 1));
    function layoutWidth() {
      const width = root.getBoundingClientRect().width;
      if (!width) return;
      root.style.setProperty("--v4-vw", width / 100 + "px");
      for (const [name, max] of [
        ["compact", 900],
        ["mobile", 560],
        ["tiny", 340],
      ])
        root.toggleAttribute("data-v4-" + name, width <= max);
    }
    new ResizeObserver(layoutWidth).observe(root);
    window.addEventListener("resize", layoutWidth);
    layoutWidth();
    const originalHeader = root.querySelector(":scope > .v4-header"),
      officialHeader = document.querySelector("#mainContent > header.hd"),
      portal = document.createElement("div");
    portal.id = "exactV4-headerControls";
    const headerControls = [
      originalHeader.querySelector(".pill"),
      $("exactV4-th"),
      $("exactV4-prog"),
    ];
    function syncPortal() {
      const active = currentView === "Divulgação";
      document.body.classList.toggle("exact-content-v4", active);
      originalHeader.hidden = true;
      if (active && officialHeader) {
        headerControls.forEach((node) => portal.append(node));
        officialHeader.append(portal);
      } else {
        headerControls.forEach((node) => originalHeader.append(node));
        portal.remove();
      }
    }
    const theme = () => {
      root.dataset.t = document.documentElement.dataset.theme === "light" ? "light" : "dark";
      const styles = getComputedStyle(root);
      for (const key of [
        "--bg",
        "--s1",
        "--s2",
        "--ln",
        "--tx",
        "--mu",
        "--ac",
        "--ac2",
        "--wa",
        "--ez",
      ])
        portal.style.setProperty(key, styles.getPropertyValue(key));
    };
    syncPortal();
    theme();
    new MutationObserver(theme).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    $("exactV4-th").addEventListener("click", () =>
      SocialMEIThemes.select(root.dataset.t === "dark" ? "light" : "dark"),
    );
    const title = $("contentStudioTitle");
    title.replaceChildren(
      ...title.textContent.split(" ").flatMap((word, index) => {
        const wrap = document.createElement("span"),
          inside = document.createElement("i");
        wrap.className = "w";
        inside.style.setProperty("--i", index);
        inside.textContent = word;
        wrap.append(inside);
        return [wrap, document.createTextNode(" ")];
      }),
    );
    const ideas = [
        "Mostre o que seu cliente leva para casa",
        "Mostre os bastidores de hoje",
        "Conte a história de um cliente satisfeito",
        "Responda a pergunta que mais te fazem",
        "Apresente o produto mais pedido",
        "Mostre um antes e depois",
        "Agradeça seus clientes da semana",
      ],
      idea = ideas[new Date().getDay()];
    $("exactV4-ti").textContent = idea;
    function useIdea() {
      input("dv4Topic", idea.slice(0, 60));
      input("contentTitle", idea.slice(0, 50));
      openStep(2);
      toast("Ideia aplicada. Agora é só completar.");
    }
    $("exactV4-today").addEventListener("click", () => {
      if (get("dv4Topic") || get("contentTitle"))
        toast("Você já começou um texto. Substituir pela ideia de hoje?", false, [
          "Substituir",
          useIdea,
        ]);
      else useIdea();
    });
    const scrollProgress = () => {
      if (currentView !== "Divulgação") return;
      const scroller = document.scrollingElement;
      $("exactV4-prog").style.transform =
        "scaleX(" + scroller.scrollTop / Math.max(1, scroller.scrollHeight - innerHeight) + ")";
    };
    addEventListener("scroll", scrollProgress, { passive: true });
    function presentation() {
      const x = Number(media.dataset.dv4X || 50),
        y = Number(media.dataset.dv4Y || 50),
        element = media.querySelector("img,video");
      media.style.setProperty("--px", x + "%");
      media.style.setProperty("--py", y + "%");
      media.style.setProperty("--z", $("dv4Zoom").value || 1);
      media.classList.toggle("has", !!element);
      if (element) {
        if (element.tagName === "IMG") element.alt = get("dv4Alt") || "Mídia escolhida";
        else element.setAttribute("aria-label", get("dv4Alt") || "Mídia escolhida");
      }
      $("dv4FeedLight").hidden = device.dataset.f !== "feed";
      $("exactV4-sfl").hidden = device.dataset.f === "feed";
    }
    function update() {
      const fields = [
          ["Escolheu o formato", true],
          ["Definiu tema e serviço", get("dv4Topic") && get("dv4Offering")],
          ["Escreveu um título", get("contentTitle")],
          ["Escreveu a legenda", get("contentCaption")],
          ["Adicionou foto ou vídeo", !!media.querySelector("img,video")],
          ["Incluiu chamada para ação", get("contentCta")],
        ],
        done = fields.filter(([, value]) => value).length,
        progress = done / fields.length;
      $("exactV4-chk").replaceChildren(
        ...fields.map(([label, value]) => {
          const li = document.createElement("li");
          li.textContent = label;
          if (value) li.className = "on";
          return li;
        }),
      );
      $("dv4ProgressRing").style.strokeDashoffset = 150.8 * (1 - progress);
      $("dv4ProgressRing").style.stroke = progress === 1 ? "var(--ok)" : "";
      $("dv4Percent").textContent = Math.round(progress * 100) + "%";
      $("dv4ProgressTitle").textContent =
        progress === 1
          ? "Pronto para revisar"
          : progress > 0.4
            ? "Está ficando bom"
            : "Vamos começar";
      const missing = fields.find(([, value]) => !value);
      $("dv4ProgressNext").textContent = missing
        ? "Falta: " +
          missing[0]
            .replace(/^(Escolheu|Definiu|Escreveu|Adicionou|Incluiu)\s/, "")
            .replace(/^um /, "") +
          "."
        : "Tudo preenchido. Salve ou revise a preparação da semana.";
      const complete = [
        true,
        get("dv4Topic") && get("dv4Offering"),
        get("contentTitle") && get("contentCaption"),
        progress === 1,
      ];
      $$("details.st").forEach((node, index) => node.classList.toggle("done", !!complete[index]));
      const warning = [];
      if ((get("contentHashtags").match(/#/g) || []).length > 5)
        warning.push("Muitas hashtags deixam o texto poluído. Tente até 5.");
      if (device.dataset.f !== "feed" && get("contentCaption").length > 150)
        warning.push(
          (device.dataset.f === "story" ? "Story" : "Reel") +
            " com texto longo é difícil de ler. Tente até 150 caracteres.",
        );
      if (get("contentTitle").length > 40)
        warning.push("Título longo pode ficar cortado na prévia.");
      $("exactV4-warn").textContent = warning.join(" ");
      presentation();
    }
    document.addEventListener("socialmei-content-preview-change", update);
    for (const [source, target, max] of [
      ["contentPreviewTitle", "contentTitle", 50],
      ["contentPreviewCaption", "contentCaption", 2200],
      ["exactV4-pcta", "contentCta", 30],
    ]) {
      $(source).addEventListener("input", () => {
        const value = $(source).textContent.slice(0, max);
        if ($(source).textContent.length > max) $(source).textContent = value;
        input(target, value);
      });
      if (source !== "contentPreviewCaption")
        $(source).addEventListener("keydown", (event) => {
          if (event.key === "Enter") event.preventDefault();
        });
    }
    for (const name of ["input", "change"])
      form.addEventListener(name, (event) => {
        event.target.classList?.remove("bad");
        update();
      });
    $$(".fmt").forEach((button) =>
      button.addEventListener("click", (event) => {
        clearTimeout(stepTimer);
        // Arrow/Home/End radio navigation keeps the group visible and focused.
        if (event.detail > 0) stepTimer = setTimeout(() => openStep(2), reduced() ? 0 : 350);
      }),
    );
    document.addEventListener("socialmei-content-editor-open", () => {
      pendingEditorFocus = true;
      $("contentWorkspace-create").click();
      openStep(3);
      if (!$("contentCreatePanel").hidden) {
        $("contentTitle").focus();
        pendingEditorFocus = false;
      }
    });
    document.addEventListener("socialmei-content-tab-change", (event) => {
      if (event.detail.tab === "create" && pendingEditorFocus) {
        openStep(3);
        $("contentTitle").focus();
        pendingEditorFocus = false;
      }
    });
    document.addEventListener("socialmei-content-editor-new", () => {
      $("contentWorkspace-create").click();
      openStep(1);
      toast("Tudo limpo. Pode começar de novo.");
    });
    let lastSuggestion = "";
    const alternatives = () =>
      SocialMEIContentPreparation.captionAlternatives({
        style: "v4",
        topic: get("dv4Topic"),
        offering: get("dv4Offering"),
        objective: $("dv4Objective").value,
        tone: $("dv4Tone").value,
      });
    function suggestions() {
      const result = alternatives();
      $("exactV4-sugs").replaceChildren(
        ...result.alternatives.map((caption, index) => {
          const button = document.createElement("button");
          button.type = "button";
          button.style.setProperty("--i", index);
          button.textContent = caption;
          button.addEventListener("click", () => {
            if (
              get("contentCaption") &&
              $("contentCaption").value !== lastSuggestion &&
              !confirm("Substituir a legenda que você já escreveu?")
            )
              return;
            lastSuggestion = caption;
            input("contentCaption", caption);
            if (!get("contentTitle")) input("contentTitle", get("dv4Topic").slice(0, 50));
            openStep(3);
            toast("Sugestão aplicada. Edite como quiser. Confirme as informações antes de usar.");
          });
          return button;
        }),
      );
      return result;
    }
    $("exactV4-sug").addEventListener("click", () => {
      const invalid = ["dv4Topic", "dv4Offering"].filter((id) => !get(id));
      if (invalid.length) {
        invalid.forEach((id) => {
          $(id).classList.add("bad", "shake");
        });
        $(invalid[0]).focus();
        toast("Preencha o tema e o serviço primeiro.", true);
        return;
      }
      buttonState($("exactV4-sug"), "load");
      try {
        suggestions();
        buttonState($("exactV4-sug"), "ok");
      } catch (error) {
        delete $("exactV4-sug").dataset.s;
        toast(error.message, true);
      }
    });
    for (const id of ["dv4Tone", "dv4Objective"])
      $(id).addEventListener("change", () => {
        if (!$("exactV4-sugs").children.length || !get("dv4Topic") || !get("dv4Offering")) return;
        const prior = lastSuggestion,
          result = suggestions();
        if (prior && $("contentCaption").value === prior) {
          lastSuggestion = result.alternatives[0];
          input("contentCaption", lastSuggestion);
          toast("Legenda atualizada para o novo tom. Revise as informações.");
        }
      });
    async function copyAll() {
      const text = [
        get("contentTitle"),
        get("contentCaption"),
        get("contentCta"),
        get("contentHashtags"),
      ]
        .filter(Boolean)
        .join("\n\n");
      if (!text) return toast("Ainda não há nada para copiar.", true);
      try {
        await navigator.clipboard.writeText(text);
        buttonState($("exactV4-copyall"), "ok");
        toast("Publicação completa copiada. Nenhum envio foi realizado.");
      } catch {
        toast("Não foi possível copiar. Selecione o texto manualmente.", true);
      }
    }
    $("exactV4-copyall").addEventListener("click", copyAll);
    media.addEventListener("click", () => {
      if (moved) {
        moved = false;
        return;
      }
      $("contentMedia").click();
    });
    media.addEventListener("pointerdown", (event) => {
      if (event.target.closest("video") || !media.querySelector("img,video")) return;
      drag = {
        x: event.clientX,
        y: event.clientY,
        px: Number(media.dataset.dv4X || 50),
        py: Number(media.dataset.dv4Y || 50),
      };
      moved = false;
      media.setPointerCapture(event.pointerId);
    });
    media.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const box = media.getBoundingClientRect(),
        dx = event.clientX - drag.x,
        dy = event.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
      media.dataset.dv4X = String(Math.max(0, Math.min(100, drag.px - (dx / box.width) * 100)));
      media.dataset.dv4Y = String(Math.max(0, Math.min(100, drag.py - (dy / box.height) * 100)));
      presentation();
    });
    for (const name of ["pointerup", "pointercancel"])
      media.addEventListener(name, () => {
        if (drag && moved) form.dispatchEvent(new Event("input", { bubbles: true }));
        drag = null;
        setTimeout(() => (moved = false), 50);
      });
    media.addEventListener("keydown", (event) => {
      const shift = { ArrowLeft: [5, 0], ArrowRight: [-5, 0], ArrowUp: [0, 5], ArrowDown: [0, -5] }[
        event.key
      ];
      if (shift && media.querySelector("img,video")) {
        event.preventDefault();
        media.dataset.dv4X = String(
          Math.max(0, Math.min(100, Number(media.dataset.dv4X || 50) + shift[0])),
        );
        media.dataset.dv4Y = String(
          Math.max(0, Math.min(100, Number(media.dataset.dv4Y || 50) + shift[1])),
        );
        form.dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        $("contentMedia").click();
      }
    });
    const phone = root.querySelector(".phone");
    phone.addEventListener("dragover", (event) => event.preventDefault());
    phone.addEventListener("drop", (event) => {
      event.preventDefault();
      const file = event.dataTransfer.files[0];
      if (!file) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      $("contentMedia").files = transfer.files;
      $("contentMedia").dispatchEvent(new Event("change", { bubbles: true }));
    });
    function thumbnail(element) {
      if (element.tagName !== "IMG" || !element.naturalWidth) return;
      try {
        const scale = Math.min(1, 200 / Math.max(element.naturalWidth, element.naturalHeight)),
          canvas = document.createElement("canvas");
        canvas.width = Math.round(element.naturalWidth * scale);
        canvas.height = Math.round(element.naturalHeight * scale);
        canvas.getContext("2d").drawImage(element, 0, 0, canvas.width, canvas.height);
        const data = canvas.toDataURL("image/jpeg", 0.6);
        if (data.length <= 40000) media.dataset.thumbnail = data;
      } catch {
        /* A tainted or unsupported image is never persisted. */
      }
    }
    new MutationObserver(() => {
      presentation();
      const image = media.querySelector("img");
      if (image) {
        image.addEventListener("load", () => thumbnail(image), { once: true });
        thumbnail(image);
      }
      update();
    }).observe(media, { childList: true });
    $("dv4SafeArea").addEventListener("change", () =>
      device.classList.toggle("sf", $("dv4SafeArea").checked),
    );
    $("dv4FeedLight").addEventListener("click", () => {
      const on = device.classList.toggle("lt");
      $("dv4FeedLight").setAttribute("aria-pressed", String(on));
      toast(on ? "Prévia clara aplicada ao Feed." : "Prévia escura.");
    });
    function fullscreen(force) {
      const on = force ?? !stage.classList.contains("fs");
      stage.classList.toggle("fs", on);
      $("dv4Fullscreen").textContent = on ? "Fechar" : "Tela cheia";
      if (on) {
        fullscreenFocus = document.activeElement;
        priorOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        stage.setAttribute("role", "dialog");
        stage.setAttribute("aria-modal", "true");
        stage.setAttribute("aria-label", "Prévia em tela cheia");
        $("dv4Fullscreen").focus();
      } else {
        stage.removeAttribute("role");
        stage.removeAttribute("aria-modal");
        document.body.style.overflow = priorOverflow;
        if (fullscreenFocus?.isConnected) fullscreenFocus.focus();
      }
    }
    $("dv4Fullscreen").addEventListener("click", () => fullscreen());
    document.addEventListener("keydown", (event) => {
      if (currentView !== "Divulgação" || !host.getClientRects().length) return;
      if (event.key === "Escape" && stage.classList.contains("fs")) {
        event.preventDefault();
        fullscreen(false);
        return;
      }
      if (event.key === "Tab" && stage.classList.contains("fs")) {
        const nodes = [
            ...stage.querySelectorAll(
              'button:not([disabled]),[contenteditable],[tabindex="0"],input',
            ),
          ].filter((el) => el.getClientRects().length),
          first = nodes[0],
          last = nodes.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
      if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "s" &&
        !$("contentCreatePanel").hidden
      ) {
        event.preventDefault();
        openStep(4);
        $("contentSave").click();
      }
    });
    document.addEventListener("socialmei-view-change", () => {
      syncPortal();
      if (currentView !== "Divulgação" && stage.classList.contains("fs")) fullscreen(false);
      if (currentView === "Divulgação") {
        layoutWidth();
        theme();
        update();
      }
    });
    const filter = () => {
      const items = repo.read().items,
        query = $("dv4DraftQuery").value.toLocaleLowerCase("pt-BR"),
        format = $("dv4DraftFormat").value,
        order = $("dv4DraftOrder").value;
      const allowed = items.filter(
        (item) =>
          (!format || item.format === format) &&
          (item.title + " " + item.caption + " " + (item.presentation?.offering || ""))
            .toLocaleLowerCase("pt-BR")
            .includes(query),
      );
      allowed.sort((a, b) =>
        order === "az"
          ? a.title.localeCompare(b.title, "pt-BR")
          : order === "old"
            ? Date.parse(a.updatedAt) - Date.parse(b.updatedAt)
            : Date.parse(b.updatedAt) - Date.parse(a.updatedAt),
      );
      const positions = new Map(allowed.map((item, index) => [item.id, index])),
        list = $("contentDraftList");
      const cards = [...list.querySelectorAll("[data-content-draft]")];
      cards.sort(
        (a, b) =>
          (positions.get(a.dataset.contentDraft) ?? 1000) -
          (positions.get(b.dataset.contentDraft) ?? 1000),
      );
      cards.forEach((card) => {
        card.hidden = !positions.has(card.dataset.contentDraft);
        list.append(card);
      });
      let empty = list.querySelector(".v4-filter-empty");
      if (!empty) {
        empty = document.createElement("p");
        empty.className = "empty-s v4-filter-empty";
        list.append(empty);
      }
      empty.textContent = "Nada encontrado com esses filtros.";
      empty.hidden = !!allowed.length || !items.length;
    };
    for (const id of ["dv4DraftQuery", "dv4DraftFormat", "dv4DraftOrder"])
      $(id).addEventListener(id === "dv4DraftQuery" ? "input" : "change", filter);
    document.addEventListener("socialmei-content-drafts-change", filter);
    $("dv4Export").addEventListener("click", () => {
      const state = repo.read();
      if (state.status !== "ready" || !state.items.length)
        return toast("Não há rascunhos para exportar.", true);
      const drafts = state.items.map((item) => ({
        ...item,
        presentation: item.presentation
          ? Object.fromEntries(
              Object.entries(item.presentation).filter(([key]) => key !== "thumbnail"),
            )
          : undefined,
      }));
      const blob = new Blob(
          [JSON.stringify({ app: "socialmei-native-drafts", version: 1, drafts }, null, 2)],
          { type: "application/json" },
        ),
        url = URL.createObjectURL(blob),
        link = document.createElement("a");
      link.href = url;
      link.download = "rascunhos-socialmei-" + new Date().toLocaleDateString("sv-SE") + ".json";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast("Backup gerado sem imagens. Guarde o arquivo em local seguro.");
    });
    $("dv4Import").addEventListener("click", () => $("dv4ImportFile").click());
    $("dv4ImportFile").addEventListener("change", async () => {
      const file = $("dv4ImportFile").files?.[0],
        expected = scope();
      $("dv4ImportFile").value = "";
      if (!file) return;
      try {
        if (file.size > 256 * 1024) throw Error("O backup deve ter até 256 KB.");
        const payload = JSON.parse(await file.text()),
          native = payload?.app === "socialmei-native-drafts" && payload.version === 1,
          original = payload?.app === "socialmei-divulgacao" && payload.v === 4;
        if ((!native && !original) || !Array.isArray(payload.drafts))
          throw Error("Esse arquivo não é um backup válido.");
        const entries = payload.drafts.map((item) =>
          original
            ? {
                format: item.f,
                title: item.titulo,
                caption: item.leg,
                cta: item.cta,
                hashtags: item.tags,
                media: null,
                presentation: {
                  topic: item.tema || "",
                  offering: item.prod || "",
                  objective: item.obj || "Apresentar",
                  tone: item.tom || "Profissional",
                  alt: item.alt || "",
                  zoom: Number(item.zoom || 1),
                  x: 50,
                  y: 50,
                },
              }
            : {
                ...item,
                presentation: item.presentation
                  ? Object.fromEntries(
                      Object.entries(item.presentation).filter(([key]) => key !== "thumbnail"),
                    )
                  : undefined,
              },
        );
        entries.forEach((entry) => SocialMEIContentDrafts.draft(entry));
        if (expected !== scope()) throw Error("A sessão mudou. Nenhum rascunho foi importado.");
        if (
          !confirm("Importar " + entries.length + " rascunho(s) para este negócio neste navegador?")
        )
          return;
        repo.importMany(entries, expected);
        SocialMEIContentStudio.render();
        toast(
          "Rascunhos importados para este negócio neste navegador. Selecione as mídias novamente.",
        );
      } catch (error) {
        toast(error.message || "Não foi possível importar o backup.", true);
      }
    });
    function connections() {
      const specs = [
        [
          "Instagram",
          "Preparação pendente",
          "Nenhuma conta é conectada. Prepare apenas dados públicos do seu negócio.",
          "Preparar Instagram",
        ],
        [
          "WhatsApp",
          "Não conectado",
          "Integração ainda não iniciada. Número e permissões exigem homologação.",
          "Preparação indisponível",
        ],
        [
          "Facebook",
          "Integração indisponível",
          "Esta integração ainda não está disponível.",
          "Indisponível",
        ],
      ];
      $("exactV4-cg").replaceChildren(
        ...specs.map(([name, state, description, label], index) => {
          const card = document.createElement("div");
          card.className = "cn";
          const head = document.createElement("div");
          head.style.cssText = "display:flex;justify-content:space-between;align-items:center";
          const title = document.createElement("b"),
            badge = document.createElement("span");
          title.textContent = name;
          badge.className = "chip " + (index === 0 ? "c-wa" : index === 1 ? "c-mu" : "c-er");
          badge.textContent = state;
          head.append(title, badge);
          const text = document.createElement("p"),
            button = document.createElement("button");
          text.textContent = description;
          button.type = "button";
          button.className = "btn sec";
          button.textContent = label;
          button.disabled = index > 0;
          button.addEventListener("click", () => {
            const details = $("integrationSetupPanel").closest("details");
            details.open = true;
            $("integrationSetupRefresh").click();
            $("integrationSetupPanel").scrollIntoView({
              block: "center",
              behavior: reduced() ? "auto" : "smooth",
            });
          });
          card.append(head, text, button);
          return card;
        }),
      );
    }
    $("exactV4-bs").addEventListener("click", () => {
      setView("Configurações");
      document.querySelector('[data-settings-tab="perfil"]')?.click();
    });
    document.addEventListener("socialmei-content-tab-change", (event) => {
      if (event.detail.tab === "connections") connections();
    });
    const status = $("contentActionStatus");
    new MutationObserver(() => {
      const text = status.textContent;
      if (!text || text.startsWith("Alterações")) return;
      toast(text, /Não foi|recusad|inválid|Falta|excede/.test(text));
      if (text.startsWith("Rascunho salvo")) buttonState($("contentSave"), "ok");
    }).observe(status, { childList: true, characterData: true, subtree: true });
    update();
    filter();
    connections();
  });
})();
