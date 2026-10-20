// Real text measurements catch narrow labels even when the page has no overflow.
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
module.exports = async (browser, origin) => {
  const page = await browser.newPage({ reducedMotion: "reduce", locale: "pt-BR" });
  await page.route("**/*", (r) =>
    new URL(r.request().url()).origin === origin ? r.continue() : r.abort(),
  );
  const out = path.resolve(__dirname, "../test-results/functional-audit");
  fs.mkdirSync(out, { recursive: true });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Automações"));
    for (const width of [320, 360, 390])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 960 });
        await page.evaluate((theme) => SocialMEIThemes.select(theme), theme);
        const sizes = await page.locator("#automationList td").evaluateAll((cells) =>
          cells
            .filter((c) => ["Área", "Último teste", "Situação"].includes(c.dataset.l))
            .map((c) => {
              const label = getComputedStyle(c, "::before"),
                canvas = document.createElement("canvas"),
                ctx = canvas.getContext("2d");
              ctx.font = `${label.fontWeight} ${label.fontSize} ${label.fontFamily}`;
              const child = c.querySelector(".management-inline-actions,.pill");
              const text = c.textContent.trim();
              const labelWidth = ctx.measureText(c.dataset.l + ": ").width;
              const valueStyle = getComputedStyle(c);
              ctx.font = `${valueStyle.fontWeight} ${valueStyle.fontSize} ${valueStyle.fontFamily}`;
              const value = child
                ? child.getBoundingClientRect().width
                : ctx.measureText(text).width;
              return {
                label: c.dataset.l,
                width: c.getBoundingClientRect().width,
                needed: labelWidth + value + 8,
              };
            }),
        );
        assert(sizes.length >= 3);
        assert(
          sizes.every((s) => s.width >= s.needed),
          `Unreadable routine labels: ${JSON.stringify({ width, theme, sizes })}`,
        );
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: path.join(out, `automation-labels-${width}-${theme}.png`) });
      }
    return "Automações: rótulos e valores legíveis em320/360/390 claro/escuro, sem overflow";
  } finally {
    await page.close();
  }
};
