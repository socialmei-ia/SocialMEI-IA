/* Native charts keep final layout; only displayed transform geometry is animated. */
const SocialMEIChartRefinement = (() => {
  const plots = new Map(),
    sparks = new Map();
  const seen = new WeakSet();
  let scope = null,
    pending = false,
    frame = 0,
    focused = null;
  const identity = () =>
    JSON.stringify([
      SocialMEIBusinessProfile.browserRepository().scope(),
      SocialMEIDemoData.enabled(),
      ["clientes", "produtos", "vendas", "financeiro"].map((key) => {
        const source = SOCIALMEI_CONFIG[key] || {};
        return [source.mode, source.apiBaseUrl, source.workspaceKey];
      }),
    ]);
  const quiet = () => SocialMEIMotion.reduced || document.hidden;
  const plotKey = (plot) => {
    const host = plot.closest("[id]") || plot.parentElement;
    return (
      (host.id || "chart") + "|" + [...host.querySelectorAll(".management-plot")].indexOf(plot)
    );
  };
  function settle(entry) {
    entry.current = entry.end;
    entry.bar.style.height = entry.height;
    entry.bar.style.removeProperty("transform");
    entry.bar.style.removeProperty("opacity");
    entry.active = false;
  }
  function tick(now) {
    frame = 0;
    let active = false;
    plots.forEach(({ entries }) =>
      entries.forEach((entry) => {
        if (!entry.active) return;
        const t =
          quiet() || !entry.bar.isConnected
            ? 1
            : Math.min(1, (now - entry.started) / entry.duration);
        entry.current = entry.start + (entry.end - entry.start) * (1 - (1 - t) ** 3);
        entry.bar.style.transform = `scaleY(${entry.current / entry.base})`;
        entry.bar.style.opacity = String(0.7 + 0.3 * t);
        if (t === 1) settle(entry);
        else active = true;
      }),
    );
    if (active) frame = requestAnimationFrame(tick);
  }
  function reset() {
    cancelAnimationFrame(frame);
    frame = 0;
    plots.forEach(({ entries }) => entries.forEach(settle));
    plots.clear();
    sparks.clear();
    focused = null;
  }
  function update() {
    pending = false;
    const nextScope = identity();
    if (scope !== nextScope) {
      reset();
      scope = nextScope;
    }
    document.querySelectorAll(".management-sparkline polyline").forEach((line, index) => {
      if (!line.getClientRects().length || seen.has(line)) return;
      seen.add(line);
      const key = (line.closest("[id]")?.id || "spark") + index;
      const signature = line.getAttribute("points");
      const coordinates = signature
        .trim()
        .split(/\s+/)
        .map((point) => point.split(",").map(Number));
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("class", "chart-spark-curve");
      path.setAttribute("d", SocialMEIReportMotion.draw(coordinates));
      line.after(path);
      line.style.display = "none";
      if (sparks.get(key) !== signature) {
        path.setAttribute("pathLength", "100");
        SocialMEIMotion.animate(
          path,
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
      if (!plot.getClientRects().length) return;
      const key = plotKey(plot),
        previous = plots.get(key);
      if (previous?.plot === plot) return;
      const signature =
        [...plot.querySelectorAll(".management-chart-column")]
          .map((column) => column.getAttribute("aria-label"))
          .join("|") +
        "|" +
        [...plot.querySelectorAll(".management-bars i")]
          .map((bar) => bar.style.height + bar.className)
          .join("|");
      const entries = [...plot.querySelectorAll(".management-bars i")].map((bar, index) => {
        const old = previous?.entries[index],
          end = bar.getBoundingClientRect().height,
          start = old?.current ?? 0;
        const entry = { bar, height: bar.style.height, current: end, end, active: false };
        if (quiet() || (previous?.signature === signature && !old?.active) || start === end)
          return entry;
        entry.start = start;
        entry.current = start;
        entry.base = Math.max(start, end, 1);
        entry.started = performance.now();
        entry.duration =
          previous?.signature === signature
            ? Math.max(1, old.started + old.duration - entry.started)
            : 420;
        entry.active = true;
        bar.style.height = entry.base + "px";
        bar.style.transform = `scaleY(${start / entry.base})`;
        return entry;
      });
      plots.set(key, { plot, entries, signature });
      if (entries.some((entry) => entry.active) && !frame) frame = requestAnimationFrame(tick);
      if (
        focused?.key === key &&
        !focused.node.isConnected &&
        document.activeElement === document.body
      )
        plot
          .querySelectorAll(".management-chart-column")
          [focused.index]?.focus({ preventScroll: true });
      plot.querySelectorAll(".management-chart-column").forEach((column) => {
        column.addEventListener("click", () => {
          const active = column.dataset.chartActive !== "true";
          plot.querySelectorAll(".management-chart-column").forEach((other) => {
            other.dataset.chartActive = String(active && other === column);
          });
        });
        column.addEventListener("keydown", (event) => {
          if (event.key === "Escape") {
            column.dataset.chartActive = "false";
            column.dataset.chartDismissed = "true";
          }
        });
        column.addEventListener("blur", () => {
          column.dataset.chartActive = "false";
          column.dataset.chartDismissed = "false";
        });
        column.addEventListener("pointerenter", () => {
          column.dataset.chartDismissed = "false";
        });
      });
    });
  }
  const queue = () => {
    if (!pending) {
      pending = true;
      requestAnimationFrame(update);
    }
  };
  document.addEventListener("focusin", (event) => {
    const column = event.target.closest?.(".management-plot .management-chart-column");
    const plot = column?.closest(".management-plot");
    focused = column
      ? {
          node: column,
          key: plotKey(plot),
          index: [...plot.querySelectorAll(".management-chart-column")].indexOf(column),
        }
      : null;
  });
  document.addEventListener("DOMContentLoaded", () => {
    new MutationObserver((records) => {
      if (records.some((record) => [...record.addedNodes].some((node) => node.nodeType === 1)))
        queue();
    }).observe(document.getElementById("mainContent") || document.body, {
      childList: true,
      subtree: true,
    });
    ["socialmei-view-change", "socialmei-demo-change", "socialmei-business-profile-change"].forEach(
      (event) => document.addEventListener(event, queue),
    );
    document.addEventListener("socialmei-motion-change", () => {
      if (quiet()) tick(performance.now());
      queue();
    });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) tick(performance.now());
    });
    queue();
  });
  return { update };
})();
