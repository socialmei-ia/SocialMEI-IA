/* SPOTLIGHT — um único card acompanha o ponteiro; nunca captura o scroll touch. */
(() => {
  "use strict";
  const surfaces = [...document.querySelectorAll("[data-spotlight]")];
  if (!surfaces.length) return;
  const finePointer = matchMedia("(hover: hover) and (pointer: fine)");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  let activeSurface = null;
  let pointer = null;
  let frame = null;

  function stop() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    activeSurface?.removeAttribute("data-spotlight-active");
    activeSurface = null;
    pointer = null;
  }

  function available(surface) {
    return (
      finePointer.matches &&
      !reducedMotion.matches &&
      !document.hidden &&
      !!surface.closest(".landing-page.is-active")
    );
  }

  function paint() {
    frame = null;
    if (!activeSurface || !pointer || !available(activeSurface)) {
      stop();
      return;
    }
    const bounds = activeSurface.getBoundingClientRect();
    activeSurface.style.setProperty("--spotlight-x", `${pointer.x - bounds.left}px`);
    activeSurface.style.setProperty("--spotlight-y", `${pointer.y - bounds.top}px`);
  }

  for (const surface of surfaces) {
    surface.classList.add("spotlight-surface");
    const layer = document.createElement("span");
    layer.className = "spotlight-layer";
    layer.setAttribute("aria-hidden", "true");
    surface.append(layer);
    surface.addEventListener(
      "pointermove",
      (event) => {
        if (event.pointerType === "touch" || !available(surface)) return;
        if (activeSurface !== surface) {
          stop();
          activeSurface = surface;
          surface.setAttribute("data-spotlight-active", "");
        }
        pointer = { x: event.clientX, y: event.clientY };
        if (frame === null) frame = requestAnimationFrame(paint);
      },
      { passive: true },
    );
    surface.addEventListener("pointerleave", () => {
      if (activeSurface === surface) stop();
    });
  }
  finePointer.addEventListener("change", stop);
  reducedMotion.addEventListener("change", stop);
  document.addEventListener("visibilitychange", stop);
  window.addEventListener("pagehide", stop);
  window.addEventListener(
    "scroll",
    () => {
      if (activeSurface && frame === null) frame = requestAnimationFrame(paint);
    },
    { passive: true },
  );
  const landing = surfaces[0].closest(".landing-page");
  if (landing)
    new MutationObserver(stop).observe(landing, { attributes: true, attributeFilter: ["class"] });
})();
