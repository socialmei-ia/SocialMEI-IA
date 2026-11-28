const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ channel: "chrome" });
  try {
    for (const width of [390, 1280]) {
      const page = await browser.newPage({ viewport: { width, height: 800 } });
      await page.route("**/*", (route) =>
        route.fulfill({
          contentType: "text/html",
          body: '<main id="v"><div class="cx4-th"></div></main>',
        }),
      );
      await page.goto("http://localhost:8724/#/caixa");
      await page.evaluate(() => {
        window.tones = 0;
        window.fixtureTime = 5000;
        Date.now = () => window.fixtureTime;
        window.AudioContext = class {
          async resume() {
            this.state = "running";
          }
          createOscillator() {
            return {
              frequency: {},
              connect() {},
              start() {
                window.tones++;
              },
              stop() {},
            };
          }
          createGain() {
            return {
              connect() {},
              gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} },
            };
          }
        };
        window.publish = (scope, id, origin = "instagram", overrides = {}) =>
          window.SocialMEIInboxSound.observe(scope, [
            { origin, last_inbound_id: id, unread_count: 1, ...overrides },
          ]);
      });
      await page.addScriptTag({
        path: path.join(__dirname, "../frontend/scripts/inbox-notification-sound.js"),
      });
      await page.evaluate(() => {
        window.SocialMEIInboxSound.mount("4:60");
        window.publish("4:60", 100);
        window.publish("4:60", 101);
      });
      assert.equal(await page.evaluate(() => window.tones), 0);
      await page.getByRole("button", { name: "Ativar som" }).click();
      await page.getByRole("button", { name: "Desativar som" }).waitFor();
      await page.evaluate(() => {
        window.publish("4:60", 102);
        window.fixtureTime += 3000;
        window.publish("4:60", 102);
        window.publish("4:60", 103, "synthetic");
        window.publish("4:60", 104, "waha", { snoozed_until: "2027-04-10" });
        window.publish("4:60", 105, "waha", { unread_count: 0 });
      });
      assert.equal(await page.evaluate(() => window.tones), 1);
      await page.evaluate(() => {
        window.SocialMEIInboxSound.mount("4:61");
        window.publish("4:61", 901);
        window.publish("4:61", 902);
        window.SocialMEIInboxSound.mount("4:60");
        window.publish("4:60", 106);
      });
      assert.equal(await page.evaluate(() => window.tones), 1);
      await page.getByRole("button", { name: "Desativar som" }).click();
      await page.evaluate(() => window.publish("4:60", 107));
      assert.equal(await page.evaluate(() => window.tones), 1);
      await page.close();
    }
    console.log(
      "Inbox sound: opt-in, no replay, snoozed suppression and tenant switch at 390px and 1280px",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
