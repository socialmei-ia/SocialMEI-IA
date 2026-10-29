/* Wait for V22's native fit() resize listener, without calling it or hiding content. */
async function waitForViewportFit(page) {
  await page.waitForFunction(() => {
    const width = Number.parseFloat(document.body.style.width);
    const zoom = Number.parseFloat(document.body.style.zoom) || 1;
    return Number.isFinite(width) && Math.abs(width * zoom - innerWidth) <= 1;
  });
}

async function layoutSnapshot(page) {
  return page.evaluate(() => ({
    route: location.hash,
    width: innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.getBoundingClientRect().width,
    zoom: document.body.style.zoom,
    overflowing: [...document.querySelectorAll("body *")]
      .filter((element) => element.getBoundingClientRect().right > innerWidth + 1)
      .slice(0, 12)
      .map((element) => ({
        tag: element.tagName,
        id: element.id,
        class: element.getAttribute("class"),
        right: element.getBoundingClientRect().right,
      })),
  }));
}

module.exports = { waitForViewportFit, layoutSnapshot };
