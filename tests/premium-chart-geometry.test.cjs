const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const context = vm.createContext({ document: { addEventListener() {} } });
vm.runInContext(
  fs.readFileSync("frontend/scripts/report-motion.js", "utf8") +
    "\nglobalThis.curve = SocialMEIReportMotion.draw;",
  context,
);

function verify(points) {
  const path = context.curve(points);
  assert(!/NaN|Infinity/.test(path));
  const commands = path.match(/[MC][^MC]+/g);
  assert.equal(commands.length, points.length);
  for (let i = 1; i < commands.length; i++) {
    const [ax, ay, bx, by, x, y] = commands[i]
      .slice(1)
      .match(/-?\d+(?:\.\d+)?/g)
      .map(Number);
    const [px, py] = points[i - 1];
    assert(
      Math.abs(x - points[i][0]) <= 0.001 && Math.abs(y - points[i][1]) <= 0.001,
      "The curve passes through each exact data point",
    );
    for (let step = 0; step <= 100; step++) {
      const t = step / 100,
        u = 1 - t;
      const cy = u ** 3 * py + 3 * u ** 2 * t * ay + 3 * u * t ** 2 * by + t ** 3 * y;
      const cx = u ** 3 * px + 3 * u ** 2 * t * ax + 3 * u * t ** 2 * bx + t ** 3 * x;
      assert(
        cy >= Math.min(py, y) - 0.002 && cy <= Math.max(py, y) + 0.002,
        "No invented financial peaks or troughs",
      );
      assert(cx >= px - 0.002 && cx <= x + 0.002);
    }
  }
}
test("Monotone curves preserve zeros, plateaus, extrema and unequal bucket spacing", () => {
  for (const values of [
    [0, 0],
    [0, 100, 0],
    [100, 0, 0, 80],
    [5, 6, 1000, 1001],
    [100, 10, 11, 0],
    [0, 100, 0, 100, 0],
  ])
    verify(values.map((value, i) => [i * i * 10, value]));
  assert.equal(context.curve([]), "");
  assert.equal(context.curve([[12, 18]]), "M12,18");
});
test("Seeded financial series remain bounded, including interpolated morph frames", () => {
  let seed = 19;
  const random = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32;
  for (let run = 0; run < 80; run++) {
    const a = Array.from({ length: 12 }, (_, i) => [i * 50, Math.round(random() * 10000)]);
    const b = a.map(([x]) => [x, Math.round(random() * 10000)]);
    for (const t of [0, 0.25, 0.5, 0.75, 1])
      verify(a.map(([x, y], i) => [x, y + (b[i][1] - y) * t]));
  }
});
