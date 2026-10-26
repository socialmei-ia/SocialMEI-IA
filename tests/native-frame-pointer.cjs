/* Chromium/CDP omits ancestor CSS zoom when translating iframe locator clicks.
   Use actual viewport pixels; retain both frame and target hit-test assertions. */
const assert = require("node:assert/strict");
module.exports = async function clickFrame(page, locator) {
  await locator.waitFor({ state: "visible" });
  await locator.scrollIntoViewIfNeeded();
  await locator.evaluate(
    (el) =>
      new Promise((resolve, reject) => {
        let tries = 0;
        function ready() {
          const r = el.getBoundingClientRect(),
            h = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
          if (el === h || el.contains(h)) return resolve();
          if (++tries > 100) return reject(Error("Embedded control is covered"));
          setTimeout(ready, 50);
        }
        ready();
      }),
  );
  const point = await locator.evaluate((el) => {
    const r = el.getBoundingClientRect(),
      f = window.frameElement,
      b = f.getBoundingClientRect();
    const x = r.x + r.width / 2,
      y = r.y + r.height / 2;
    return {
      x: b.x + (x * b.width) / f.clientWidth,
      y: b.y + (y * b.height) / f.clientHeight,
      target:
        el === document.elementFromPoint(x, y) || el.contains(document.elementFromPoint(x, y)),
    };
  });
  assert(point.target, "The original embedded control must receive pointer events");
  assert(
    await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.tagName === "IFRAME", point),
    "The official frame must be visible at the click position",
  );
  await page.mouse.click(point.x, point.y);
};
