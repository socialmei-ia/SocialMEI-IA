const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  const page = await browser.newPage({ reducedMotion: "reduce" });
  await page.route("**/*", (r) =>
    new URL(r.request().url()).origin === origin ? r.continue() : r.abort(),
  );
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Clientes"));
    const focus = await page.evaluate(() => {
      const raf = requestAnimationFrame,
        queued = [];
      window.requestAnimationFrame = (cb) => {
        queued.push(cb);
        return queued.length;
      };
      openCreate("cliente");
      document.getElementById("f_nome").focus();
      window.requestAnimationFrame = raf;
      for (const cb of queued) cb(performance.now());
      return document.activeElement.id;
    });
    assert.equal(
      focus,
      "f_nome",
      "Deferred autofocus must not overwrite focus already chosen inside the dialog",
    );
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    assert.equal(await page.evaluate(() => document.activeElement.id), "f_nome");
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.getElementById("createModal").classList.contains("open"),
    );
    return "Modal: autofocus tardio preserva foco já escolhido, Tab/Shift+Tab e Escape";
  } finally {
    await page.close();
  }
};
