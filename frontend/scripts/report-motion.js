/* Reports presentation only. Geometry is interpolated; commercial values are never changed. */
const SocialMEIReportMotion = (() => {
  const geometries = new Map();
  let frame = 0;
  const points = (path) => {
    const values = (path.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
    return Array.from({ length: values.length / 2 }, (_, i) => values.slice(i * 2, i * 2 + 2));
  };
  const draw = (values) =>
    values.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  function sample(values, index, length) {
    const position = length === 1 ? 0 : (index / (length - 1)) * (values.length - 1);
    const low = Math.floor(position),
      high = Math.min(values.length - 1, low + 1);
    return values[low].map(
      (value, axis) => value + (values[high][axis] - value) * (position - low),
    );
  }
  function reset() {
    cancelAnimationFrame(frame);
    geometries.forEach(({ path }) =>
      path.getAnimations().forEach((animation) => animation.cancel()),
    );
    geometries.clear();
  }
  function update() {
    cancelAnimationFrame(frame);
    const jobs = [];
    document.querySelectorAll("#reportsView .rv2-trend").forEach((chart) => {
      chart.dataset.motionState = "settled";
      if (!chart.getClientRects().length) return;
      chart.querySelectorAll(".rv2-line").forEach((path, index) => {
        const end = points(path.getAttribute("d"));
        const key = chart.dataset.source + index;
        const signature = chart.dataset.series + chart.querySelector("svg").getAttribute("viewBox");
        const previous = geometries.get(key);
        const entry = { points: end, signature, path };
        geometries.set(key, entry);
        if (SocialMEIMotion.reduced || document.hidden || previous?.signature === signature) return;
        if (!previous) {
          const length = path.getTotalLength();
          SocialMEIMotion.animate(
            path,
            [
              { strokeDasharray: String(length), strokeDashoffset: length },
              { strokeDasharray: String(length), strokeDashoffset: 0 },
            ],
            740,
          );
          return;
        }
        path.getAnimations().forEach((animation) => animation.cancel());
        const start = end.map((_, i) => sample(previous.points, i, end.length));
        entry.points = start;
        path.setAttribute("d", draw(start));
        chart.dataset.motionState = "updating";
        jobs.push({ chart, path, start, end, entry, index });
      });
    });
    if (!jobs.length) return;
    const started = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - started) / 460),
        ease = 1 - (1 - t) ** 3;
      jobs.forEach(({ chart, path, start, end, entry, index }) => {
        entry.points = end.map((point, i) =>
          point.map((value, axis) => start[i][axis] + (value - start[i][axis]) * ease),
        );
        path.setAttribute("d", draw(entry.points));
        if (index === 0)
          chart.querySelectorAll(".rv2-point").forEach((point, i) => {
            point.querySelectorAll("circle").forEach((circle) => {
              circle.setAttribute("cx", entry.points[i][0]);
              circle.setAttribute("cy", entry.points[i][1]);
            });
          });
        if (t === 1) chart.dataset.motionState = "settled";
      });
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
  }
  return { update, reset };
})();
