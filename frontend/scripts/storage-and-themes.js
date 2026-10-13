/* STORAGE AND THEMES */

const SOCIALMEI_APP_SCHEMA_VERSION = 1;
function socialmeiIsQuotaExceeded(error) {
  return (
    !!error &&
    (error.name === "QuotaExceededError" ||
      error.name === "NS_ERROR_DOM_QUOTA_REACHED" ||
      error.code === 22 ||
      error.code === 1014)
  );
}
function socialmeiNotifyStorageError(context, error) {
  const quota = socialmeiIsQuotaExceeded(error);
  const title = quota ? "Armazenamento do navegador cheio" : "Não foi possível salvar";
  const detail = quota
    ? `Não foi possível salvar ${context}. Exporte um backup em Preferências > Dados e libere espaço antes de fechar a página.`
    : `O navegador não permitiu salvar ${context}. Os dados desta sessão continuam abertos.`;
  console.warn(title + ": " + context, error || "");
  const notify = () => {
    if (typeof window.toast === "function") {
      window.toast(title, detail);
      return true;
    }
    return false;
  };
  if (!notify()) {
    setTimeout(notify, 0);
  }
}
/**
 * Grava uma chave existente sem mudar seu formato. Retorna false e informa a falha ao usuário se o navegador recusar a gravação.
 * @param {string} key Chave de armazenamento.
 * @param {string} value Conteúdo serializado.
 * @param {string} context Descrição apresentada em caso de erro.
 * @returns {boolean}
 */
function socialmeiStorageSet(key, value, context = "os dados") {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch (error) {
    socialmeiNotifyStorageError(context, error);
    return false;
  }
}

/* Motor de temas: cores, contraste e preferências persistentes. */
(function () {
  "use strict";

  const HEX_COLOR_PATTERN = /^#[\da-f]{6}$/i;
  const themeColorTokenNames = [
    "background",
    "surface",
    "surface-secondary",
    "border",
    "text-primary",
    "text-secondary",
    "brand-primary",
    "brand-accent",
    "hover",
    "selected",
    "success",
    "warning",
    "danger",
    "info",
  ];
  const baseThemePalettes = {
    light: {
      background: "#F7F7F2",
      surface: "#FFFFFF",
      "surface-secondary": "#EEEFEA",
      border: "#DFE3E7",
      "border-strong": "#77869B",
      "text-primary": "#1C2B3A",
      "text-secondary": "#526171",
      "text-muted": "#657282",
      success: "#167347",
      warning: "#985009",
      danger: "#B42318",
      info: "#1962B7",
    },
    dark: {
      background: "#0C1624",
      surface: "#142134",
      "surface-secondary": "#1B2B42",
      border: "#304057",
      "border-strong": "#647997",
      "text-primary": "#EEF3FA",
      "text-secondary": "#B6C4D5",
      "text-muted": "#A4B3C6",
      success: "#70D5A4",
      warning: "#F3B56E",
      danger: "#FF9A92",
      info: "#8ABFFF",
    },
  };
  const officialThemes = {
    light: {
      name: "SocialMEI Claro",
      base: "light",
      primary: "#1E73D8",
      accent: "#F2B11B",
      intensity: 35,
      recommendedStatus: true,
      overrides: {},
    },
    dark: {
      name: "SocialMEI Escuro",
      base: "dark",
      primary: "#579BEF",
      accent: "#F5C451",
      intensity: 35,
      recommendedStatus: true,
      overrides: {},
    },
  };
  const hexToRgb = (hexColor) =>
    hexColor
      .slice(1)
      .match(/../g)
      .map((x) => parseInt(x, 16));
  const rgbToHex = (channels) =>
    "#" +
    channels
      .map((v) =>
        Math.round(Math.max(0, Math.min(255, v)))
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
      .toUpperCase();
  const mixColors = (a, b, p) =>
    rgbToHex(hexToRgb(a).map((v, i) => v * (1 - p) + hexToRgb(b)[i] * p));
  const relativeLuminance = (hexColor) =>
    hexToRgb(hexColor)
      .map((v) => {
        v /= 255;
        return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
      })
      .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
  const getContrastRatio = (firstColor, secondColor) => {
    const x = relativeLuminance(firstColor);
    const y = relativeLuminance(secondColor);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  };
  const getReadableForeground = (background) => {
    const w = getContrastRatio("#FFFFFF", background);
    const d = getContrastRatio("#111827", background);
    return w >= d && w >= 4.5 ? "#FFFFFF" : d >= 4.5 ? "#111827" : "#000000";
  };
  function getAccessibleColor(color, backgrounds, minimum = 4.5) {
    if (backgrounds.every((background) => getContrastRatio(color, background) >= minimum)) {
      return color;
    }
    let best = color;
    let score = 0;
    for (const target of ["#FFFFFF", "#111827", "#000000"]) {
      for (let i = 0; i <= 100; i++) {
        const c = mixColors(color, target, i / 100);
        const s = Math.min(...backgrounds.map((background) => getContrastRatio(c, background)));
        if (s >= minimum) {
          return c;
        }
        if (s > score) {
          best = c;
          score = s;
        }
      }
    }
    return best;
  }
  function validateTheme(value, { stored = false } = {}) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw Error("O JSON deve conter um objeto de tema.");
    }
    const allowed = [
      "version",
      "id",
      "name",
      "base",
      "primary",
      "accent",
      "intensity",
      "recommendedStatus",
      "overrides",
    ];
    if (Object.keys(value).some((k) => !allowed.includes(k))) {
      throw Error("O arquivo contém campos de tema desconhecidos.");
    }
    if (value.version !== undefined && value.version !== 1) {
      throw Error("Versão de tema não suportada.");
    }
    if (
      typeof value.name !== "string" ||
      !value.name.trim() ||
      value.name.length > 60 ||
      /[\x00-\x1F]/.test(value.name)
    ) {
      throw Error("Use um nome entre 1 e 60 caracteres.");
    }
    if (!["light", "dark"].includes(value.base)) {
      throw Error("A base deve ser light ou dark.");
    }
    if (
      typeof value.primary !== "string" ||
      typeof value.accent !== "string" ||
      !HEX_COLOR_PATTERN.test(value.primary) ||
      !HEX_COLOR_PATTERN.test(value.accent)
    ) {
      throw Error("Use cores HEX no formato #RRGGBB.");
    }
    if (
      typeof value.intensity !== "number" ||
      !Number.isFinite(value.intensity) ||
      value.intensity < 0 ||
      value.intensity > 100
    ) {
      throw Error("A intensidade deve ser um número de 0 a 100.");
    }
    if (value.recommendedStatus !== undefined && typeof value.recommendedStatus !== "boolean") {
      throw Error("O campo recommendedStatus deve ser booleano.");
    }
    const o = value.overrides ?? {};
    if (
      !o ||
      typeof o !== "object" ||
      Array.isArray(o) ||
      Object.keys(o).some(
        (k) =>
          !themeColorTokenNames.includes(k) ||
          typeof o[k] !== "string" ||
          !HEX_COLOR_PATTERN.test(o[k]),
      )
    ) {
      throw Error("As configurações avançadas contêm campos ou cores inválidos.");
    }
    const overrides = {};
    for (const k of themeColorTokenNames) {
      if (o[k]) {
        overrides[k] = o[k].toUpperCase();
      }
    }
    const result = {
      version: 1,
      name: value.name.trim(),
      base: value.base,
      primary: value.primary.toUpperCase(),
      accent: value.accent.toUpperCase(),
      intensity: value.intensity,
      recommendedStatus: value.recommendedStatus !== false,
      overrides,
    };
    if (stored && typeof value.id === "string" && /^custom-[a-z0-9-]{1,80}$/i.test(value.id)) {
      result.id = value.id;
    }
    return result;
  }
  function buildTheme(theme) {
    const dark = theme.base === "dark";
    const o = theme.overrides || {};
    const t = {
      ...baseThemePalettes[theme.base],
    };
    for (const k of themeColorTokenNames) {
      if (
        o[k] &&
        HEX_COLOR_PATTERN.test(o[k]) &&
        ![
          "brand-primary",
          "brand-accent",
          "hover",
          "selected",
          "success",
          "warning",
          "danger",
          "info",
        ].includes(k)
      ) {
        t[k] = o[k];
      }
    }
    const p = theme.primary;
    const a = theme.accent;
    const colorIntensityRatio = theme.intensity / 100;
    t["surface-elevated"] = t.surface;
    t["brand-primary"] = p;
    t["brand-accent"] = a;
    // Mantém as cores escolhidas; deriva tons e cores de texto com contraste acessível.
    t["brand-primary-hover"] = mixColors(p, dark ? "#FFFFFF" : "#000000", dark ? 0.1 : 0.13);
    t["brand-primary-active"] = mixColors(p, dark ? "#FFFFFF" : "#000000", dark ? 0.18 : 0.24);
    t["brand-primary-soft"] = mixColors(
      t.surface,
      p,
      (dark ? 0.14 : 0.06) + colorIntensityRatio * 0.14,
    );
    t["brand-primary-subtle"] = mixColors(t.surface, p, 0.02 + colorIntensityRatio * 0.055);
    t["brand-accent-hover"] = mixColors(a, dark ? "#FFFFFF" : "#000000", 0.12);
    t["brand-accent-soft"] = mixColors(t.surface, a, 0.08 + colorIntensityRatio * 0.1);
    t.hover = o.hover || mixColors(t.surface, p, 0.025 + colorIntensityRatio * 0.07);
    t.selected = o.selected || t["brand-primary-soft"];
    const neutrals = [
      t.background,
      t.surface,
      t["surface-secondary"],
      t.hover,
      t.selected,
      t["brand-primary-soft"],
      t["brand-accent-soft"],
    ];
    t["text-muted"] = getAccessibleColor(baseThemePalettes[theme.base]["text-muted"], neutrals);
    t["brand-primary-text"] = getAccessibleColor(p, neutrals);
    t["on-primary"] = getReadableForeground(p);
    t["on-primary-hover"] = getReadableForeground(t["brand-primary-hover"]);
    t["on-primary-active"] = getReadableForeground(t["brand-primary-active"]);
    t["on-accent"] = getReadableForeground(a);
    t["focus-ring"] = getAccessibleColor(p, [t.background, t.surface], 3);
    for (const k of ["success", "warning", "danger", "info"]) {
      const status =
        theme.recommendedStatus === false && o[k] ? o[k] : baseThemePalettes[theme.base][k];
      t[k + "-soft"] = mixColors(t.surface, status, dark ? 0.13 : 0.07);
      t[k] = getAccessibleColor(status, [t.background, t.surface, t[k + "-soft"]]);
    }
    t["message-out"] = t["brand-primary-soft"];
    t["message-out-text"] = getAccessibleColor(t["text-primary"], [t["message-out"]]);
    t["chart-1"] = p;
    t["chart-2"] = mixColors(p, dark ? "#FFFFFF" : "#1962B7", 0.4);
    t["chart-3"] = a;
    t["chart-4"] = t.success;
    t["chart-5"] = dark ? "#7388A4" : "#9BAAC0";
    t["tooltip-background"] = dark ? "#EAF1FA" : "#19263B";
    t["tooltip-text"] = getReadableForeground(t["tooltip-background"]);
    t["overlay"] = "rgba(4,12,25,.46)";
    t.shadow = dark ? "0 7px 22px rgba(0,0,0,.16)" : "0 5px 18px rgba(15,35,65,.06)";
    return t;
  }
  const themeTokenAliases = {
    bg: "background",
    sf: "surface",
    ln: "border",
    tx: "text-primary",
    mt: "text-muted",
    br: "brand-primary",
    bs: "brand-primary-soft",
    bi: "brand-primary-text",
    ng: "danger",
    ngs: "danger-soft",
    gy: "chart-5",
    hv: "hover",
    on: "on-primary",
    amber: "warning",
    ambg: "warning-soft",
    blue: "info",
    "blue-soft": "info-soft",
    purple: "chart-2",
    "purple-soft": "brand-primary-subtle",
  };
  function applyTokens(element, theme) {
    const tokens = buildTheme(theme);
    for (const [k, v] of Object.entries(tokens)) {
      element.style.setProperty("--" + k, v);
    }
    for (const [k, v] of Object.entries(themeTokenAliases)) {
      element.style.setProperty("--" + k, tokens[v]);
    }
    element.style.colorScheme = theme.base;
    return tokens;
  }
  function checkThemeContrast(theme) {
    const t = buildTheme(theme);
    const list = [
      ["Texto / fundo", t["text-primary"], t.background],
      ["Texto / superfície", t["text-primary"], t.surface],
      ["Texto secundário / fundo", t["text-secondary"], t.background],
      ["Texto secundário / superfície", t["text-secondary"], t.surface],
      ["Texto discreto / fundo", t["text-muted"], t.background],
      ["Texto discreto / superfície", t["text-muted"], t.surface],
      ["Texto / superfície secundária", t["text-primary"], t["surface-secondary"]],
      ["Texto / hover", t["text-primary"], t.hover],
      ["Texto / seleção", t["text-primary"], t.selected],
      ["Texto / destaque suave", t["text-primary"], t["brand-accent-soft"]],
      ["Texto / botão principal", t["on-primary"], t["brand-primary"]],
      ["Texto / botão hover", t["on-primary-hover"], t["brand-primary-hover"]],
      ["Texto / botão ativo", t["on-primary-active"], t["brand-primary-active"]],
      ["Texto / destaque", t["on-accent"], t["brand-accent"]],
      ["Link / superfície", t["brand-primary-text"], t.surface],
      ["Mensagem enviada", t["message-out-text"], t["message-out"]],
    ];
    for (const k of ["success", "warning", "danger", "info"]) {
      list.push([
        {
          success: "Sucesso",
          warning: "Aviso",
          danger: "Erro",
          info: "Informação",
        }[k],
        t[k],
        t[k + "-soft"],
      ]);
    }
    return list.map(([label, fg, background]) => ({
      label,
      fg,
      bg: background,
      ratio: getContrastRatio(fg, background),
      pass: getContrastRatio(fg, background) >= 4.5,
    }));
  }
  let themes = [];
  let active = "light";
  let storageError = false;
  function loadThemePreferences() {
    try {
      const raw = localStorage.getItem("socialmei-custom-themes");
      const parsed = raw && raw.length <= 102400 ? JSON.parse(raw) : [];
      themes = Array.isArray(parsed)
        ? parsed.slice(0, 40).flatMap((x) => {
            try {
              const t = validateTheme(x, {
                stored: true,
              });
              return t.id ? [t] : [];
            } catch (error) {
              return [];
            }
          })
        : [];
      const stored = localStorage.getItem("socialmei-active-theme");
      const legacy = localStorage.getItem("socialmei-theme");
      const fallback = ["light", "dark", "auto"].includes(legacy) ? legacy : "auto";
      active =
        ["light", "dark", "auto"].includes(stored) || themes.some((t) => t.id === stored)
          ? stored
          : fallback;
    } catch (error) {
      themes = [];
      active = "auto";
    }
  }
  const scheme = matchMedia("(prefers-color-scheme: dark)");
  function getCurrentTheme() {
    return (
      themes.find((t) => t.id === active) ||
      officialThemes[active === "auto" ? (scheme.matches ? "dark" : "light") : active] ||
      officialThemes.light
    );
  }
  function applyTheme() {
    document.documentElement.dataset.theme = getCurrentTheme().base;
    document.documentElement.dataset.activeTheme = active;
    applyTokens(document.documentElement, getCurrentTheme());
  }
  function persistThemePreferences() {
    const okCustom = socialmeiStorageSet(
      "socialmei-custom-themes",
      JSON.stringify(themes),
      "os temas personalizados",
    );
    const okActive = socialmeiStorageSet("socialmei-active-theme", active, "o tema ativo");
    const okLegacy = socialmeiStorageSet(
      "socialmei-theme",
      active.startsWith("custom-") ? getCurrentTheme().base : active,
      "a preferência de tema",
    );
    storageError = !(okCustom && okActive && okLegacy);
    return !storageError;
  }
  function selectTheme(id) {
    if (!["light", "dark", "auto"].includes(id) && !themes.some((t) => t.id === id)) {
      return false;
    }
    active = id;
    applyTheme();
    return persistThemePreferences();
  }
  function saveCustomTheme(theme) {
    const clean = validateTheme(theme, {
      stored: true,
    });
    clean.id =
      clean.id ||
      "custom-" +
        (globalThis.crypto?.randomUUID?.() ||
          Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8));
    const i = themes.findIndex((t) => t.id === clean.id);
    if (i < 0 && themes.length >= 40) {
      throw Error("Você pode salvar até 40 temas.");
    }
    const previous = themes.slice();
    if (i >= 0) {
      themes[i] = clean;
    } else {
      themes.push(clean);
    }
    if (!persistThemePreferences()) {
      themes = previous;
      throw Error("Não foi possível salvar. Verifique o armazenamento do navegador.");
    }
    if (active === clean.id) {
      applyTheme();
    }
    return clean;
  }
  function removeCustomTheme(id) {
    if (!themes.some((t) => t.id === id)) {
      return false;
    }
    const removed = themes.find((t) => t.id === id);
    themes = themes.filter((t) => t.id !== id);
    if (active === id) {
      active = removed.base === "dark" ? "dark" : "light";
    }
    applyTheme();
    return persistThemePreferences();
  }
  function fixThemeContrast(theme) {
    const next = JSON.parse(JSON.stringify(theme));
    const t = buildTheme(next);
    const o = next.overrides || {};
    const backgrounds = ["background", "surface", "surface-secondary", "hover", "selected"].map(
      (k) => t[k],
    );
    for (const key of ["text-primary", "text-secondary"]) {
      o[key] = getAccessibleColor(t[key], backgrounds);
    }
    next.overrides = o;
    if (checkThemeContrast(next).some((x) => !x.pass)) {
      for (const k of ["background", "surface", "surface-secondary", "hover", "selected"]) {
        delete o[k];
      }
      const normal = buildTheme(next);
      const b = [
        normal.background,
        normal.surface,
        normal["surface-secondary"],
        normal.hover,
        normal.selected,
        normal["brand-accent-soft"],
      ];
      for (const k of ["text-primary", "text-secondary"]) {
        o[k] = getAccessibleColor(normal[k], b);
      }
    }
    return next;
  }
  loadThemePreferences();
  applyTheme();
  scheme.addEventListener?.("change", () => {
    if (active === "auto") {
      applyTheme();
      window.dispatchEvent(new CustomEvent("socialmei-theme-change"));
    }
  });
  window.addEventListener("storage", (event) => {
    if (
      ["socialmei-active-theme", "socialmei-custom-themes", "socialmei-theme"].includes(event.key)
    ) {
      loadThemePreferences();
      applyTheme();
      window.dispatchEvent(new CustomEvent("socialmei-theme-change"));
    }
  });
  window.SocialMEIThemes = {
    official: officialThemes,
    bases: baseThemePalettes,
    keys: themeColorTokenNames,
    aliases: themeTokenAliases,
    HEX: HEX_COLOR_PATTERN,
    build: buildTheme,
    applyTokens,
    checks: checkThemeContrast,
    contrast: getContrastRatio,
    fix: fixThemeContrast,
    validate: validateTheme,
    save: saveCustomTheme,
    select: selectTheme,
    remove: removeCustomTheme,
    current: getCurrentTheme,
    get themes() {
      return themes;
    },
    get active() {
      return active;
    },
    get storageError() {
      return storageError;
    },
  };
})();
