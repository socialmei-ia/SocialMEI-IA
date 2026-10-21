(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIContentDrafts = api;
})(globalThis, function () {
  "use strict";
  const FORMATS = Object.freeze({ story: "Story", feed: "Feed", reel: "Reel" });
  const LIMIT = 40;
  function text(value, max) {
    if (typeof value !== "string" || value.length > max)
      throw new Error("O conteúdo excede os limites do rascunho.");
    return value;
  }
  function schedule(value) {
    if (value === undefined || value === null || value === "") return "";
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value))
      throw new Error("Informe data e horário válidos para o planejamento.");
    const [year, month, day, hour, minute] = value.match(/\d+/g).map(Number);
    const date = new Date(year, month - 1, day, hour, minute);
    if (year < 2024 || year > 2100 ||
        date.getFullYear() !== year || date.getMonth() !== month - 1 ||
        date.getDate() !== day || date.getHours() !== hour ||
        date.getMinutes() !== minute)
      throw new Error("Informe data e horário válidos para o planejamento.");
    return value;
  }
  function draft(value) {
    if (!value || !Object.hasOwn(FORMATS, value.format))
      throw new Error("Escolha Story, Feed ou Reel.");
    const title = text(value.title, 80).trim();
    if (!title) throw new Error("Dê um título ao rascunho.");
    let media = null;
    if (value.media) {
      const m = value.media;
      if (
        typeof m.name !== "string" ||
        m.name.length > 180 ||
        !["image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm"].includes(m.type) ||
        !Number.isSafeInteger(m.size) ||
        m.size <= 0 ||
        m.size > (m.type.startsWith("image/") ? 10 : 50) * 1024 * 1024 ||
        (value.format === "reel" && !m.type.startsWith("video/")) ||
        (value.format === "feed" && !m.type.startsWith("image/"))
      )
        throw new Error("Referência de mídia inválida.");
      media = { name: m.name, type: m.type, size: m.size };
    }
    return {
      format: value.format,
      title,
      caption: text(value.caption || "", 2200),
      cta: text(value.cta || "", 140),
      hashtags: text(value.hashtags || "", 300),
      scheduledAt: schedule(value.scheduledAt),
      media,
    };
  }
  function caption(value) {
    return [value.caption, value.cta, value.hashtags]
      .filter((s) => s && s.trim())
      .map((s) => s.trim())
      .join("\n\n");
  }
  function repository(
    storage,
    getScope,
    { id = () => crypto.randomUUID(), now = () => new Date().toISOString() } = {},
  ) {
    const key = (scope) => "socialmei-content-drafts-v1:" + encodeURIComponent(scope);
    function read() {
      const scope = getScope();
      if (!scope) return { scope: null, items: [], status: "unavailable" };
      try {
        const raw = storage.getItem(key(scope));
        if (!raw) return { scope, items: [], status: "ready" };
        const data = JSON.parse(raw);
        if (
          data.version !== 1 ||
          data.scope !== scope ||
          !Array.isArray(data.items) ||
          data.items.length > LIMIT
        )
          throw Error();
        const ids = new Set();
        const items = data.items.map((item) => {
          if (
            !/^[\w-]{1,80}$/.test(item.id) ||
            ids.has(item.id) ||
            !Number.isFinite(Date.parse(item.createdAt)) ||
            !Number.isFinite(Date.parse(item.updatedAt))
          )
            throw Error();
          ids.add(item.id);
          return {
            ...draft(item),
            id: item.id,
            createdAt: item.createdAt,
            updatedAt: item.updatedAt,
          };
        });
        return { scope, items, status: "ready" };
      } catch {
        return { scope, items: [], status: "error" };
      }
    }
    function change(expected, update) {
      if (!expected || getScope() !== expected)
        throw new Error("A sessão mudou. Reabra Divulgação antes de salvar.");
      const state = read();
      if (state.status !== "ready" || state.scope !== expected)
        throw new Error("Não foi possível ler os rascunhos. Nada foi substituído.");
      const items = update(state.items);
      if (items.length > LIMIT)
        throw new Error("Limite de 40 rascunhos neste navegador. Exclua um antes de continuar.");
      if (getScope() !== expected) throw new Error("A sessão mudou. Nenhum rascunho foi salvo.");
      try {
        storage.setItem(key(expected), JSON.stringify({ version: 1, scope: expected, items }));
      } catch {
        throw new Error("Não foi possível salvar no navegador. Confira o espaço e as permissões.");
      }
      return items;
    }
    function save(value, expected) {
      const valid = draft(value);
      let saved;
      change(expected, (items) => {
        const prior = value.id && items.find((i) => i.id === value.id);
        if (value.id && !prior) throw new Error("Rascunho não encontrado neste negócio.");
        saved = {
          ...valid,
          id: prior?.id || id(),
          createdAt: prior?.createdAt || now(),
          updatedAt: now(),
        };
        return [saved, ...items.filter((i) => i.id !== saved.id)];
      });
      return saved;
    }
    function remove(target, expected) {
      return change(expected, (items) => {
        if (!items.some((i) => i.id === target)) throw new Error("Rascunho não encontrado.");
        return items.filter((i) => i.id !== target);
      });
    }
    function duplicate(target, expected) {
      const state = read();
      if (state.scope !== expected) throw new Error("A sessão mudou.");
      const item = state.items.find((i) => i.id === target);
      if (!item) throw new Error("Rascunho não encontrado.");
      return save(
        { ...item, id: undefined, title: item.title.slice(0, 72) + " · cópia" },
        expected,
      );
    }
    return Object.freeze({ read, save, remove, duplicate });
  }
  async function validateMedia(file, format) {
    if (!file || !Object.hasOwn(FORMATS, format))
      throw new Error("Escolha um arquivo e um formato.");
    const video = ["video/mp4", "video/webm"].includes(file.type),
      image = ["image/png", "image/jpeg", "image/webp"].includes(file.type);
    if ((format === "reel" && !video) || (format === "feed" && !image) || (!video && !image))
      throw new Error(
        format === "reel"
          ? "Reel aceita vídeo MP4 ou WebM."
          : format === "feed"
            ? "Feed aceita imagem JPG, PNG ou WebP."
            : "Story aceita imagem JPG, PNG, WebP ou vídeo MP4/WebM.",
      );
    if (
      !Number.isFinite(file.size) ||
      file.size <= 0 ||
      file.size > (video ? 50 : 10) * 1024 * 1024
    )
      throw new Error(video ? "Use um vídeo de até 50 MB." : "Use uma imagem de até 10 MB.");
    const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer()),
      ascii = (a, b) => String.fromCharCode(...bytes.slice(a, b));
    const valid =
      file.type === "image/png"
        ? bytes[0] === 137 &&
          ascii(1, 4) === "PNG" &&
          bytes[4] === 13 &&
          bytes[5] === 10 &&
          bytes[6] === 26 &&
          bytes[7] === 10
        : file.type === "image/jpeg"
          ? bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255
          : file.type === "image/webp"
            ? ascii(0, 4) === "RIFF" && ascii(8, 12) === "WEBP"
            : file.type === "video/mp4"
              ? ascii(4, 8) === "ftyp"
              : bytes[0] === 26 && bytes[1] === 69 && bytes[2] === 223 && bytes[3] === 163;
    if (!valid) throw new Error("O conteúdo do arquivo não corresponde ao tipo informado.");
    return { name: String(file.name).slice(0, 180), type: file.type, size: file.size };
  }
  return Object.freeze({ FORMATS, LIMIT, draft, caption, repository, validateMedia });
});
