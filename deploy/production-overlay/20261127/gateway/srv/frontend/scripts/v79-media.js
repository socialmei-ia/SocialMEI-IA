/* SocialMEI-IA · v7.9 · Componentes de mídia da Caixa Unificada (imagem, áudio, vídeo, documento/PDF).
   SOMENTE INTERFACE. Não existe contrato de backend confirmado para anexos: nenhum formato de payload nem rota de
   arquivo é presumido aqui. Nada é exibido em conversas reais enquanto um adaptador não for registrado.

   Para ligar (quando o backend publicar o contrato):
     SocialMEIMedia.register({ resolve(message, conversation) { return [descriptor] | null; } })
   descriptor: { kind: "image"|"audio"|"video"|"document", src, name?, mime?, size?, duration?, poster?, state? }
     state: "ready" (padrão) | "loading" | "unavailable" | "error"   (src pode faltar quando state != "ready")
   Segurança: src só é aceito se for blob:, data: de mídia segura ou do mesmo domínio do app. */
(() => {
  "use strict";
  if (window.SocialMEIMedia) return;
  const adapters = [];
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const IC = {
    image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
    audio: '<path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM19 11a7 7 0 0 1-14 0M12 18v3"/>',
    video: '<rect x="2" y="5" width="14" height="14" rx="2"/><path d="m16 10 6-3v10l-6-3"/>',
    document: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6"/>',
    play: '<path d="M7 4v16l13-8z"/>',
    pause: '<path d="M8 4v16M16 4v16"/>',
    warn: '<path d="M12 3 2 21h20L12 3zM12 10v5M12 18v.01"/>',
    dl: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5"/>',
  };
  const icon = (n, s = 18) => {
    const w = el("span", "v79m-ic");
    w.innerHTML = `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[n] || ""}</svg>`;
    return w;
  };
  const SAFE_DATA = /^data:(?:image\/(?:jpeg|png|webp|gif)|audio\/(?:mpeg|ogg|mp4|webm|wav)|video\/(?:mp4|webm));base64,/;
  function safeSrc(src) {
    if (typeof src !== "string" || !src || src.length > 4e6) return "";
    if (src.startsWith("blob:") || SAFE_DATA.test(src)) return src;
    try {
      const u = new URL(src, location.href);
      return u.origin === location.origin && /^https?:$/.test(u.protocol) ? u.href : "";
    } catch {
      return "";
    }
  }
  const fmtSize = (n) =>
    !Number.isFinite(n) || n < 0 ? "" : n < 1024 ? n + " B" : n < 1048576 ? Math.round(n / 1024) + " KB" : (n / 1048576).toFixed(1).replace(".", ",") + " MB";
  const fmtDur = (s) => {
    if (!Number.isFinite(s) || s < 0) return "0:00";
    const m = Math.floor(s / 60);
    return m + ":" + String(Math.floor(s % 60)).padStart(2, "0");
  };
  const LABEL = { image: "Imagem", audio: "Áudio", video: "Vídeo", document: "Documento" };

  function status(kind, tone, text, retry) {
    const b = el("div", "v79m v79m-st");
    b.dataset.tone = tone;
    b.setAttribute("role", tone === "error" ? "alert" : "status");
    if (tone === "loading") b.append(el("span", "v79m-spin"));
    else b.append(icon(tone === "error" ? "warn" : kind));
    b.append(el("span", "", text));
    if (retry && tone === "error") {
      const r = el("button", "v79m-btn", "Tentar de novo");
      r.type = "button";
      r.addEventListener("click", retry);
      b.append(r);
    }
    return b;
  }
  function lightbox(kind, src, name) {
    const d = el("dialog", "v79m-lb");
    d.setAttribute("aria-label", name || LABEL[kind]);
    const close = el("button", "v79m-x");
    close.type = "button";
    close.setAttribute("aria-label", "Fechar");
    close.append(icon("x", 20));
    const m = kind === "video" ? el("video") : el("img");
    if (kind === "video") {
      m.controls = true;
      m.preload = "metadata";
    } else m.alt = name || "Imagem recebida";
    m.src = src;
    close.addEventListener("click", () => d.close());
    d.addEventListener("click", (e) => e.target === d && d.close());
    d.addEventListener("close", () => {
      if (kind === "video") m.pause();
      d.remove();
    });
    d.append(close, m);
    document.body.append(d);
    d.showModal();
  }

  function image(d, src) {
    const b = el("button", "v79m v79m-img");
    b.type = "button";
    b.setAttribute("aria-label", "Abrir imagem" + (d.name ? ": " + d.name : ""));
    const img = el("img");
    img.alt = d.name || "Imagem recebida";
    img.loading = "lazy";
    img.decoding = "async";
    const sk = el("span", "v79m-sk");
    b.append(sk, img);
    img.addEventListener("load", () => sk.remove());
    img.addEventListener("error", () => {
      const s = status("image", "error", "Não foi possível carregar a imagem.", () => s.replaceWith(api.mount(d)));
      b.replaceWith(s);
    });
    img.src = src;
    b.addEventListener("click", () => lightbox("image", src, d.name));
    return b;
  }
  function audio(d, src) {
    const w = el("div", "v79m v79m-au");
    const a = el("audio");
    a.preload = "none";
    a.src = src;
    const btn = el("button", "v79m-play");
    btn.type = "button";
    btn.setAttribute("aria-label", "Reproduzir áudio");
    btn.append(icon("play", 18));
    const bar = el("input", "v79m-rng");
    bar.type = "range";
    bar.min = "0";
    bar.max = "1000";
    bar.value = "0";
    bar.setAttribute("aria-label", "Posição do áudio");
    const t = el("span", "v79m-t", fmtDur(d.duration));
    const swap = (n, label) => {
      btn.replaceChildren(icon(n, 18));
      btn.setAttribute("aria-label", label);
    };
    btn.addEventListener("click", () => (a.paused ? a.play().catch(() => fail()) : a.pause()));
    a.addEventListener("play", () => swap("pause", "Pausar áudio"));
    a.addEventListener("pause", () => swap("play", "Reproduzir áudio"));
    a.addEventListener("loadedmetadata", () => (t.textContent = fmtDur(a.duration)));
    a.addEventListener("timeupdate", () => {
      if (a.duration) bar.value = String(Math.round((a.currentTime / a.duration) * 1000));
      t.textContent = fmtDur(a.currentTime);
    });
    a.addEventListener("ended", () => {
      bar.value = "0";
      t.textContent = fmtDur(a.duration);
    });
    bar.addEventListener("input", () => {
      if (a.duration) a.currentTime = (Number(bar.value) / 1000) * a.duration;
    });
    const fail = () => w.replaceWith(status("audio", "error", "Não foi possível reproduzir o áudio."));
    a.addEventListener("error", fail);
    w.append(btn, bar, t, a);
    return w;
  }
  function video(d, src) {
    const b = el("button", "v79m v79m-vid");
    b.type = "button";
    b.setAttribute("aria-label", "Abrir vídeo" + (d.name ? ": " + d.name : ""));
    const poster = safeSrc(d.poster);
    if (poster) {
      const img = el("img");
      img.alt = "";
      img.loading = "lazy";
      img.src = poster;
      b.append(img);
    }
    const p = el("span", "v79m-pl");
    p.append(icon("play", 22));
    b.append(p);
    b.addEventListener("click", () => lightbox("video", src, d.name));
    return b;
  }
  function documentCard(d, src) {
    const a = el("a", "v79m v79m-doc");
    a.href = src;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    if (d.name) a.download = d.name;
    const pdf = /pdf/i.test(d.mime || "") || /\.pdf$/i.test(d.name || "");
    const tag = el("span", "v79m-ext", pdf ? "PDF" : ((d.name || "").split(".").pop() || "DOC").slice(0, 4).toUpperCase());
    const body = el("span", "v79m-db");
    body.append(el("b", "", d.name || "Documento"), el("span", "", [pdf ? "PDF" : "Arquivo", fmtSize(d.size)].filter(Boolean).join(" · ")));
    a.append(tag, body, icon("dl", 18));
    a.setAttribute("aria-label", `${pdf ? "Abrir PDF" : "Abrir documento"} ${d.name || ""}`.trim());
    return a;
  }
  const api = {
    /* Cria o nó de mídia para um descriptor. Nunca lança: descriptor inválido vira estado de falha. */
    mount(d, onRetry) {
      try {
        if (!d || !LABEL[d.kind]) return status("document", "error", "Anexo em formato não reconhecido.");
        const s = d.state || "ready";
        if (s === "loading") return status(d.kind, "loading", `Carregando ${LABEL[d.kind].toLowerCase()}…`);
        if (s === "unavailable") return status(d.kind, "unavail", `${LABEL[d.kind]} indisponível no momento.`);
        if (s === "error") return status(d.kind, "error", `Não foi possível carregar ${d.kind === "image" ? "a" : "o"} ${LABEL[d.kind].toLowerCase()}.`, onRetry);
        const src = safeSrc(d.src);
        if (!src) return status(d.kind, "unavail", `${LABEL[d.kind]} indisponível: endereço do arquivo não confiável.`);
        return { image, audio, video, document: documentCard }[d.kind](d, src);
      } catch {
        return status("document", "error", "Não foi possível exibir o anexo.");
      }
    },
    register(adapter) {
      if (!adapter || typeof adapter.resolve !== "function") throw Error("Adaptador de mídia inválido.");
      adapters.push(adapter);
    },
    get active() {
      return adapters.length > 0;
    },
    /* Descriptors de uma mensagem real, vindos somente de adaptadores registrados. */
    describe(message, conversation) {
      const out = [];
      for (const a of adapters) {
        try {
          const r = a.resolve(message, conversation);
          if (Array.isArray(r)) out.push(...r.filter(Boolean));
        } catch {}
      }
      return out;
    },
  };
  window.SocialMEIMedia = Object.freeze(api);
})();
