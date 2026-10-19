/* MOTION */
/* Centraliza durações e preferência de movimento; limpa os efeitos ao terminar. */
window.SocialMEIMotion = (() => {
  const preference = matchMedia("(prefers-reduced-motion: reduce)");
  const running = new Set();
  const activeByElement = new WeakMap();

  // Mantém em cache os tokens de duração e curva.
  // Esses tokens não dependem do tema; o cache evita recalcular estilos a cada interação.
  let rootStyle = null;
  const tokenCache = new Map();
  const readStyle = () => rootStyle || (rootStyle = getComputedStyle(document.documentElement));
  const token = (name) => {
    if (tokenCache.has(name)) {
      return tokenCache.get(name);
    }
    const value = readStyle()
      .getPropertyValue("--" + name)
      .trim();
    if (name.startsWith("motion-") || name.startsWith("ease-") || name === "stagger") {
      tokenCache.set(name, value);
    }
    return value;
  };
  const milliseconds = (name) => {
    const v = token(name);
    return parseFloat(v) * (v.endsWith("ms") ? 1 : 1000);
  };
  const animate = (element, frames, duration = "motion-base", easing = "ease-out", delay = 0) => {
    if (!element || preference.matches || document.hidden || !element.animate) {
      return Promise.resolve();
    }
    const previous = activeByElement.get(element);
    previous?.animation.cancel();
    const props = new Set();
    (frames || []).forEach((frame) =>
      Object.keys(frame || {}).forEach((key) => {
        if (key === "transform" || key === "opacity" || key === "filter") {
          props.add(key);
        }
      }),
    );
    const previousWillChange = previous?.willChange ?? element.style.willChange;
    if (props.size) {
      element.style.willChange = [...props].join(", ");
    }
    const a = element.animate(frames, {
      duration: typeof duration === "number" ? duration : milliseconds(duration),
      easing: token(easing),
      delay,
      fill: "both",
    });
    activeByElement.set(element, { animation: a, willChange: previousWillChange });
    running.add(a);
    return a.finished
      .catch(() => {})
      .finally(() => {
        running.delete(a);
        a.cancel();
        if (activeByElement.get(element)?.animation === a) {
          activeByElement.delete(element);
          element.style.willChange = previousWillChange;
        }
      });
  };
  function sync() {
    document.documentElement.classList.toggle("motion-reduced", preference.matches);
    if (preference.matches) {
      running.forEach((a) => a.cancel());
      document.getAnimations().forEach((a) => a.cancel());
    }
    document.dispatchEvent(new CustomEvent("socialmei-motion-change"));
  }
  preference.addEventListener("change", sync);
  sync();
  document.addEventListener("visibilitychange", () => {
    document.documentElement.classList.toggle("tab-hidden", document.hidden);
    if (document.hidden) {
      running.forEach((a) => a.cancel());
    }
  });
  window.addEventListener("pagehide", () => running.forEach((a) => a.cancel()));
  const seenViews = new WeakSet();
  const seenCharts = new Set();
  function drawCharts(view) {
    if (!view) {
      return;
    }
    view.querySelectorAll(".report-trend").forEach((chart, i) => {
      const key = view.id + ":" + i;
      const box = chart.getBoundingClientRect();
      if (!box.width || !box.height || seenCharts.has(key)) {
        return;
      }
      seenCharts.add(key);
      chart.querySelectorAll("rect").forEach((bar, i) => {
        bar.style.transformBox = "fill-box";
        bar.style.transformOrigin = "center bottom";
        animate(
          bar,
          [
            {
              opacity: 0.65,
              transform: "scaleY(.9)",
            },
            {
              opacity: 1,
              transform: "none",
            },
          ],
          "motion-medium",
          "ease-out",
          Math.min(i, 5) * 20,
        );
      });
    });
  }
  document.addEventListener(
    "toggle",
    () => {
      if (document.body.classList.contains("experience-app")) {
        drawCharts(document.querySelector(".page-view.active"));
      }
    },
    true,
  );
  const highlight = (element) =>
    animate(
      element,
      [
        {
          backgroundColor: token("success-soft"),
        },
        {
          backgroundColor: token("sf"),
        },
      ],
      "motion-slow",
    );
  function enterView(view) {
    if (preference.matches) {
      running.forEach((a) => a.cancel());
      document.getAnimations().forEach((a) => a.cancel());
      return;
    }
    if (!view || !document.body.classList.contains("experience-app")) {
      return;
    }
    if (view.id === "aiToolsView") {
      window.SocialMEIAssistantUI?.arrival();
      return;
    }
    const first = !seenViews.has(view);
    seenViews.add(view);
    drawCharts(view);
    if (view.id !== "settingsView") {
      animate(
        view,
        [
          {
            opacity: 0.84,
            transform: "translate3d(0,6px,0)",
          },
          {
            opacity: 1,
            transform: "translate3d(0,0,0)",
          },
        ],
        260,
        "ease-enter",
      );
    }
    if (view.id !== "settingsView") {
      if (first && view.id === "clientHomeView") {
        animate(
          view.querySelector("h2"),
          [
            {
              opacity: 0,
              transform: "translate3d(0,8px,0)",
            },
            {
              opacity: 1,
              transform: "none",
            },
          ],
          340,
          "ease-enter",
        );
      }
      let groups =
        view.id === "inboxView"
          ? view.querySelectorAll(".conv-item")
          : view.querySelectorAll(
              ".journal-entry,.order-entry,.relationship-entry,.inventory-entry,.routine-row,.home-operation-panel,.desk-conversation,.content-editor,.content-preview-panel",
            );
      [...(first ? groups : [])].slice(0, 6).forEach((element, i) =>
        animate(
          element,
          [
            {
              opacity: 0,
              transform: "translate3d(0,8px,0)",
            },
            {
              opacity: 1,
              transform: "translate3d(0,0,0)",
            },
          ],
          "motion-page",
          "ease-enter",
          i * 38,
        ),
      );
      if (view.id === "automationsView") {
        view.querySelectorAll(".automation-wire path").forEach((element) =>
          animate(
            element,
            [
              {
                strokeDasharray: "26",
                strokeDashoffset: 26,
              },
              {
                strokeDasharray: "26",
                strokeDashoffset: 0,
              },
            ],
            "motion-medium",
          ),
        );
      }
    }
  }
  return {
    token,
    ms: milliseconds,
    animate,
    enterView,
    highlight,
    get reduced() {
      const reduced = preference.matches;
      document.documentElement.classList.toggle("motion-reduced", reduced);
      return reduced;
    },
  };
})();
document.documentElement.classList.add("js", "js-motion-ready");
try {
  document.documentElement.setAttribute(
    "data-public-theme",
    localStorage.getItem("socialmei_public_theme") === "dark" ? "dark" : "light",
  );
} catch (_) {}
setTimeout(() => {
  if (!window.SocialMEIPublicMotion) {
    document.documentElement.classList.remove("js-motion-ready");
  }
}, 2200);
requestAnimationFrame(() =>
  requestAnimationFrame(() => document.documentElement.classList.add("theme-ready")),
);
