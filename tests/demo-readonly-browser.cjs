const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  const page = await browser.newPage({ reducedMotion: "reduce" });
  await page.route("**/*", (r) =>
    new URL(r.request().url()).origin === origin ? r.continue() : r.abort(),
  );
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => {
      SocialMEIExperience.enterApp("Vendas");
      SocialMEIDemoData.set(true);
      document.dispatchEvent(new CustomEvent("socialmei-demo-change"));
      window.qaDemoRAF = requestAnimationFrame;
      window.qaDemoFrames = [];
      window.requestAnimationFrame = (callback) => {
        qaDemoFrames.push(callback);
        return qaDemoFrames.length;
      };
      document.getElementById("salesSearch").value = "nenhum cliente corresponde";
      renderSales();
    });
    const controls = await page.evaluate(() =>
      [...document.querySelectorAll('[data-create="venda"]')].map((e) => ({
        disabled: e.disabled,
        description: e.getAttribute("aria-describedby"),
      })),
    );
    assert(controls.length > 0);
    assert(
      controls.every((e) => e.disabled && e.description?.includes("viewDemoDescription")),
      "New demo controls must be read-only before the next paint",
    );
    return "Amostra: novos controles de venda bloqueados antes do próximo frame";
  } finally {
    await page
      .evaluate(() => {
        if (window.qaDemoRAF) {
          window.requestAnimationFrame = qaDemoRAF;
          for (const callback of qaDemoFrames) qaDemoRAF(callback);
        }
      })
      .catch(() => {});
    await page.close();
  }
};
