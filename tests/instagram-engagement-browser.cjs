const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ channel: "chrome" });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 800 } });
    await page.route("**/*", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: '<div id="cg"><div class="cn"><b>Instagram</b></div></div>',
      }),
    );
    await page.goto("http://localhost:8724/");
    await page.evaluate(() => {
      window.render = () => {};
      window.providerReads = [];
      window.SocialMEIV22 = {
        remote: true,
        ready: Promise.resolve(),
        identity: { usuario: { id: 1 }, negocio: { id: 2 }, papel: "owner" },
        request: async (url, method) => {
          if (url.endsWith("/publishing/status")) return { schedule_available: true };
          if (url.endsWith("/meta/status"))
            return { status: "connected", credential_available: true };
          if (url.endsWith("/scheduled")) return { items: [] };
          if (url.endsWith("/account")) return { username: "fixture", connection_id: "1" };
          if (url.endsWith("/recent"))
            return {
              items: [
                { id: "published", status: "published", created_at: "2026-11-28T00:00:00Z" },
                { id: "uncertain", status: "uncertain", created_at: "2026-11-28T00:00:00Z" },
              ],
            };
          if (url.endsWith("/published/engagement") && method === "POST") {
            window.providerReads.push(url);
            return { like_count: 0, comments_count: null };
          }
          throw Error("Unapproved request " + url);
        },
      };
    });
    await page.addScriptTag({
      path: path.join(__dirname, "../frontend/scripts/v22-instagram-publisher.js"),
    });
    await page.getByRole("button", { name: "Calendário editorial" }).click();
    await page.getByText("Instagram: @fixture", { exact: true }).waitFor();
    await page.getByText("Histórico de publicações", { exact: true }).click();
    await page.getByText(/Resultado incerto/).waitFor();
    assert.deepEqual(await page.evaluate(() => window.providerReads), []);
    await page.getByRole("button", { name: "Consultar engajamento" }).click();
    await page.getByText("Curtidas: 0 · Comentários: indisponível", { exact: true }).waitFor();
    assert.equal((await page.evaluate(() => window.providerReads)).length, 1);
    console.log(
      "Publication history: uncertain retained and optional metrics loaded only on demand",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
