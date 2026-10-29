/* Resize readiness must not hide genuine content overflow. Native shell, no API. */
const assert = require("node:assert/strict");
const { waitForViewportFit, layoutSnapshot } = require("./v22-layout-ready.cjs");
module.exports = async function (browser, origin) {
  const page = await browser.newPage();
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(() => !!window.SocialMEIV22);
    for (let cycle = 0; cycle < 10; cycle++)
      for (const width of [1440, 768, 390]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate(() => go("/inicio"));
        await waitForViewportFit(page);
        const layout = await layoutSnapshot(page);
        assert.equal(layout.scrollWidth <= width + 1, true, JSON.stringify(layout));
      }
    // The readiness condition concerns the shell's resize event, never whether
    // content happens to fit. A real overflowing child must still fail QA.
    await page.evaluate(() => {
      const child = document.createElement("div");
      child.style.cssText = "position:absolute;left:0;top:0;width:4000px;height:4px";
      child.id = "overflow-canary";
      document.body.appendChild(child);
    });
    await waitForViewportFit(page);
    const broken = await layoutSnapshot(page);
    assert(broken.scrollWidth > broken.width + 1);
    assert(broken.overflowing.some((row) => row.id === "overflow-canary"));
  } finally {
    await page.close();
  }
};
