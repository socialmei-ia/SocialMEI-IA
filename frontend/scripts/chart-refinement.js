/* Animate only changed bar geometry; keep native buttons, labels and tooltips. */
const SocialMEIChartRefinement = (() => {
  let values = new Map(),
    scope = null,
    sparks = new Map(),
    pending = false;
  function update() {
    pending = false;
    const nextScope =
      SocialMEIBusinessProfile.browserRepository().scope() + "|" + SocialMEIDemoData.enabled();
    if (scope !== nextScope) {
      values.clear();
      sparks.clear();
      scope = nextScope;
    }
    document.querySelectorAll(".management-sparkline polyline").forEach((line, index) => {
      if (!line.getClientRects().length || line.dataset.chartRefined) return;
      line.dataset.chartRefined = "true";
      const key = (line.closest("[id]")?.id || "spark") + index;
      const signature = line.getAttribute("points");
      if (sparks.get(key) !== signature) {
        line.setAttribute("pathLength", "100");
        SocialMEIMotion.animate(
          line,
          [
            { strokeDasharray: "100", strokeDashoffset: 100 },
            { strokeDasharray: "100", strokeDashoffset: 0 },
          ],
          560,
        );
        sparks.set(key, signature);
      }
    });
    document.querySelectorAll(".management-plot").forEach((plot) => {
      const host = plot.closest("[id]");
      if (!host || !plot.getClientRects().length || plot.dataset.chartRefined) return;
      plot.dataset.chartRefined = "true";
      const key = host.id,
        previous = values.get(key) || [];
      const bars = [...plot.querySelectorAll(".management-bars i")];
      const next = bars.map((bar) => parseFloat(bar.style.height) || 0);
      bars.forEach((bar, index) => {
        const from = previous[index] ?? 0,
          to = next[index];
        if (from !== to)
          SocialMEIMotion.animate(bar, [{ height: from + "%" }, { height: to + "%" }], 480);
      });
      values.set(key, next);
    });
  }
  const queue = () => {
    if (!pending) {
      pending = true;
      requestAnimationFrame(update);
    }
  };
  document.addEventListener("DOMContentLoaded", () => {
    new MutationObserver((records) => {
      if (records.some((record) => [...record.addedNodes].some((node) => node.nodeType === 1)))
        queue();
    }).observe(document.getElementById("mainContent") || document.body, {
      childList: true,
      subtree: true,
    });
    document.addEventListener("socialmei-view-change", queue);
    document.addEventListener("socialmei-demo-change", queue);
    queue();
  });
  return { update };
})();
