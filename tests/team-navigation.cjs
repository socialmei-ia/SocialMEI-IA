const { setTimeout: delay } = require("node:timers/promises");

// Only the initial document GET may retry; never wrap app actions or writes.
async function navigateInitialPage(page, url) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await page.goto(url);
    } catch (error) {
      if (
        attempt === 3 ||
        !/^page\.goto: net::ERR_NETWORK_CHANGED(?: at |\r?\n|$)/.test(error.message)
      ) {
        throw error;
      }
      console.warn(`Initial HTTPS navigation: ERR_NETWORK_CHANGED; retry ${attempt}/2`);
      await delay(200);
    }
  }
}

module.exports = { navigateInitialPage };
