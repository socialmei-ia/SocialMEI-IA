/* Synthetic account responses; the native entry consumes real one-use-link UI. */
const assert = require("node:assert/strict");

module.exports = async function (browser, origin) {
  const token = "R".repeat(43);
  for (const mode of ["confirmed", "expired"])
    for (const width of [390, 1440]) {
      const page = await browser.newPage({
        viewport: { width, height: 1000 },
        reducedMotion: "reduce",
      });
      const errors = [],
        confirmations = [];
      let sessionReads = 0;
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript(() => {
        localStorage.setItem("socialmei-auth-browser-scope", "91:17");
        localStorage.setItem("socialmei-private-draft", "previous-account-work");
      });
      await page.route("**/*", async (route) => {
        const request = route.request(),
          url = new URL(request.url());
        if (url.origin !== origin) return route.abort();
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        if (url.pathname === "/api/v1/auth/session") {
          sessionReads++;
          // The link fragment must already be erased before session completion.
          await page.waitForFunction(() => location.hash === "#/recuperar");
          return route.fulfill({ json: null });
        }
        if (url.pathname === "/api/v1/auth/registration")
          return route.fulfill({ json: { mode: "open" } });
        if (url.pathname === "/api/v1/auth/recovery/confirm") {
          confirmations.push(request.postDataJSON());
          return mode === "confirmed"
            ? route.fulfill({ status: 204 })
            : route.fulfill({ status: 410, json: { detail: "Código inválido ou expirado." } });
        }
        throw Error("Unexpected account request " + url.pathname);
      });
      try {
        await page.goto(origin + "/frontend/entrada.html#/recuperar/" + token);
        await page.locator("#rToken").waitFor({ state: "visible" });
        await page.waitForFunction(
          () => localStorage.getItem("socialmei-auth-browser-scope") === "",
        );
        assert.equal(await page.locator("#rToken").inputValue(), token);
        assert.equal(sessionReads, 1, "An expired session must not reload away the recovery link");
        assert.equal(new URL(page.url()).hash, "#/recuperar");
        await page.locator("#nPass").fill("FlorSol!");
        await page.locator("#nPass2").fill("FlorSol!");
        await page.locator('#fN [type="submit"]').click();
        if (mode === "confirmed") {
          await page.locator("#rS4").waitFor({ state: "visible" });
          assert.equal(await page.locator("#rToken").inputValue(), "");
        } else {
          await page.locator("#rStatus").getByText("Código inválido ou expirado.").waitFor();
          assert.equal(await page.locator("#rToken").inputValue(), token);
          assert.equal(await page.locator('#fN [type="submit"]').isEnabled(), true);
        }
        assert.deepEqual(confirmations, [{ token, nova: "FlorSol!" }]);
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        const state = await page.evaluate(() => JSON.stringify({ ...localStorage }));
        assert(!state.includes(token));
        assert(!state.includes("FlorSol!"));
        assert.deepEqual(errors, []);
      } finally {
        await page.close();
      }
    }
  return "Recovery links survive expired sessions at mobile/desktop widths; 410 retains fields without persisting secrets";
};
