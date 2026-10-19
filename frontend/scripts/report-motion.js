/* Presentation geometry only; source values and report snapshots remain untouched. */
const SocialMEIReportMotion = (() => {
  const geometries = new Map();
  const bars = new Map();
  let frame = 0;
  let focused = null;
  const chartKey = (chart) => (chart.closest("[id]")?.id || "reports") + "|" + chart.dataset.source;
  const quiet = () => SocialMEIMotion.reduced || document.hidden;

  // Monotone Hermite tangents: every segment stays inside its two data values.
  function draw(values) {
    if (!values.length) return "";
    const number = (value) => Number(value.toFixed(3));
    const point = ([x, y]) => `${number(x)},${number(y)}`;
    if (values.length === 1) return "M" + point(values[0]);
    const slopes = values.slice(1).map(([x, y], i) => (y - values[i][1]) / (x - values[i][0] || 1));
    const tangents = values.map((_, i) => {
      if (!i) return slopes[0];
      if (i === values.length - 1) return slopes[i - 1];
      const a = slopes[i - 1],
        b = slopes[i];
      return a * b <= 0 ? 0 : (2 * a * b) / (a + b);
    });
    slopes.forEach((slope, i) => {
      if (!slope) {
        tangents[i] = tangents[i + 1] = 0;
        return;
      }
      const norm = Math.hypot(tangents[i] / slope, tangents[i + 1] / slope);
      if (norm > 3) {
        tangents[i] *= 3 / norm;
        tangents[i + 1] *= 3 / norm;
      }
    });
    return (
      "M" +
      point(values[0]) +
      values
        .slice(1)
        .map(([x, y], i) => {
          const [px, py] = values[i],
            third = (x - px) / 3;
          return ` C${point([px + third, py + third * tangents[i]])} ${point([x - third, y - third * tangents[i + 1]])} ${point([x, y])}`;
        })
        .join("")
    );
  }
  function sample(values, index, length) {
    const position = length === 1 ? 0 : (index / (length - 1)) * (values.length - 1);
    const low = Math.floor(position),
      high = Math.min(values.length - 1, low + 1);
    return values[low].map(
      (value, axis) => value + (values[high][axis] - value) * (position - low),
    );
  }
  function paint(entry) {
    entry.path.setAttribute("d", draw(entry.points));
    if (entry.index === 0) {
      entry.chart.querySelectorAll(".rv2-point").forEach((point, i) => {
        const position = entry.points[i];
        if (!position) return;
        point.querySelectorAll("circle, ellipse").forEach((circle) => {
          circle.setAttribute("cx", position[0]);
          circle.setAttribute("cy", position[1]);
        });
      });
    } else {
      entry.chart.querySelectorAll(".rv2-secondary-point").forEach((point, i) => {
        if (entry.points[i]) {
          point.setAttribute("cx", entry.points[i][0]);
          point.setAttribute("cy", entry.points[i][1]);
        }
      });
    }
    const active = entry.chart.querySelector('.rv2-point[data-active="true"] circle');
    if (active) {
      const guide = entry.chart.querySelector(".rv2-guide");
      guide.setAttribute("x1", active.getAttribute("cx"));
      guide.setAttribute("x2", active.getAttribute("cx"));
    }
  }
  function finishBar(entry) {
    entry.node.style.width = entry.width;
    entry.node.style.removeProperty("transform");
    entry.node.style.removeProperty("opacity");
    entry.active = false;
  }
  function tick(now) {
    frame = 0;
    let running = false;
    geometries.forEach((entry) => {
      if (!entry.active) return;
      const t =
        quiet() || !entry.path.isConnected
          ? 1
          : Math.min(1, (now - entry.started) / entry.duration);
      const ease = 1 - (1 - t) ** 3;
      entry.points = entry.end.map((point, i) =>
        point.map((value, axis) => entry.start[i][axis] + (value - entry.start[i][axis]) * ease),
      );
      paint(entry);
      entry.active = t < 1;
      running ||= entry.active;
    });
    document.querySelectorAll("#reportsView .rv2-trend").forEach((chart) => {
      chart.dataset.motionState = [...geometries.values()].some(
        (entry) => entry.chart === chart && entry.active,
      )
        ? "updating"
        : "settled";
    });
    bars.forEach((entry) => {
      if (!entry.active) return;
      const t = quiet() || !entry.node.isConnected ? 1 : Math.min(1, (now - entry.started) / 400);
      entry.current = entry.start + (entry.end - entry.start) * (1 - (1 - t) ** 3);
      entry.node.style.transform = `scaleX(${entry.current / entry.base})`;
      entry.node.style.opacity = String(0.78 + 0.22 * t);
      if (t === 1) finishBar(entry);
      else running = true;
    });
    if (running) frame = requestAnimationFrame(tick);
  }
  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(tick);
  };
  function reset() {
    cancelAnimationFrame(frame);
    frame = 0;
    focused = null;
    geometries.forEach((entry) =>
      entry.path.getAnimations().forEach((animation) => animation.cancel()),
    );
    bars.forEach(finishBar);
    geometries.clear();
    bars.clear();
  }
  function update() {
    document.querySelectorAll("#reportsView .rv2-trend").forEach((chart) => {
      if (!chart.getClientRects().length) return;
      const key = chartKey(chart);
      chart.querySelectorAll(".rv2-line").forEach((path, index) => {
        const end = JSON.parse(path.dataset.points);
        const signature = chart.dataset.series + chart.querySelector("svg").getAttribute("viewBox");
        const previous = geometries.get(key + index);
        if (previous?.path === path) {
          if (quiet() && previous.active) {
            previous.points = end;
            previous.active = false;
            paint(previous);
          }
          return;
        }
        previous?.path.getAnimations().forEach((animation) => animation.cancel());
        const entry = { points: end, end, signature, path, chart, index, active: false };
        geometries.set(key + index, entry);
        if (
          end.length &&
          previous?.points.length &&
          !quiet() &&
          (previous.signature !== signature || previous.active)
        ) {
          const resized =
            previous.chart.querySelector("svg").getAttribute("viewBox") !==
            chart.querySelector("svg").getAttribute("viewBox");
          const oldHeight = previous.chart.querySelector("svg").viewBox.baseVal.height;
          const newHeight = chart.querySelector("svg").viewBox.baseVal.height;
          entry.start = end.map((target, i) => {
            const current = sample(previous.points, i, end.length);
            return resized ? [target[0], (current[1] * newHeight) / oldHeight] : current;
          });
          entry.points = entry.start;
          entry.duration =
            previous.signature === signature
              ? Math.max(1, previous.started + previous.duration - performance.now())
              : 460;
          entry.started = performance.now();
          entry.active = true;
          paint(entry);
          schedule();
        } else if (!previous && !quiet() && end.length > 1) {
          const length = path.getTotalLength();
          SocialMEIMotion.animate(
            path,
            [
              { strokeDasharray: String(length), strokeDashoffset: length },
              { strokeDasharray: String(length), strokeDashoffset: 0 },
            ],
            640,
          );
        }
      });
      chart.dataset.motionState = [...geometries.values()].some(
        (entry) => entry.chart === chart && entry.active,
      )
        ? "updating"
        : "settled";
      if (
        focused?.key === key &&
        !focused.node.isConnected &&
        document.activeElement === document.body
      ) {
        chart.querySelectorAll(".rv2-point")[focused.index]?.focus({ preventScroll: true });
      }
    });
  }
  function updateBars() {
    document.querySelectorAll("#reportsView [data-report-bar]").forEach((node) => {
      const key = node.dataset.reportBar,
        previous = bars.get(key);
      if (previous?.node === node) return;
      const width = node.style.width,
        end = node.getBoundingClientRect().width;
      const start = previous?.current ?? 0;
      const entry = { node, width, end, current: end, active: false };
      bars.set(key, entry);
      if (quiet() || (previous?.width === width && !previous.active) || start === end) return;
      entry.start = start;
      entry.current = start;
      entry.base = Math.max(start, end, 1);
      entry.started = performance.now();
      entry.active = true;
      node.style.width = entry.base + "px";
      node.style.transform = `scaleX(${start / entry.base})`;
      schedule();
    });
  }
  document.addEventListener("pointerdown", (event) => {
    document.querySelectorAll("#reportsView .rv2-trend").forEach((chart) => {
      if (!chart.contains(event.target)) chart.dispatchEvent(new Event("socialmei-chart-dismiss"));
    });
  });
  document.addEventListener("focusin", (event) => {
    const point = event.target.closest?.(".rv2-point");
    focused = point
      ? {
          node: point,
          key: chartKey(point.closest(".rv2-trend")),
          index: Number(point.dataset.index),
        }
      : null;
  });
  document.addEventListener("socialmei-motion-change", () => {
    update();
    updateBars();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) tick(performance.now());
  });
  return { update, updateBars, reset, draw };
})();
