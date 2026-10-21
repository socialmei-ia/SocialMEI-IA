const { setTimeout: delay } = require("node:timers/promises");

// Only the initial document GET may retry; never wrap app actions or writes.
async function navigateInitialPage(page, url, { onStartupRetry = () => {} } = {}) {
  for (let attempt = 1; ; attempt++) {
    const failures = [];
    const failed = (request) => {
      if (
        ["script", "stylesheet"].includes(request.resourceType()) &&
        new URL(request.url()).origin === new URL(url).origin
      )
        failures.push({
          path: new URL(request.url()).pathname,
          error: request.failure()?.errorText,
        });
    };
    const httpFailed = (response) => {
      if (
        !response.ok() &&
        ["script", "stylesheet"].includes(response.request().resourceType()) &&
        new URL(response.url()).origin === new URL(url).origin
      )
        failures.push({ path: new URL(response.url()).pathname, status: response.status() });
    };
    page.on("requestfailed", failed);
    page.on("response", httpFailed);
    try {
      const response = await page.goto(url);
      // A Docker startup network event can cancel assets after the HTML already
      // returned 200. Recover only this exact transport error, before app actions.
      if (
        response?.status() === 200 &&
        failures.length &&
        failures.every((failure) => failure.error === "net::ERR_NETWORK_CHANGED")
      )
        throw new Error("page.goto: net::ERR_NETWORK_CHANGED at " + url);
      return response;
    } catch (error) {
      if (
        attempt === 3 ||
        failures.some((failure) => failure.error !== "net::ERR_NETWORK_CHANGED") ||
        !/^page\.goto: net::ERR_NETWORK_CHANGED(?: at |\r?\n|$)/.test(error.message)
      ) {
        throw error;
      }
      console.warn(`Initial HTTPS navigation: ERR_NETWORK_CHANGED; retry ${attempt}/2`);
      onStartupRetry({ attempt, failures });
      await delay(200);
    } finally {
      page.off("requestfailed", failed);
      page.off("response", httpFailed);
    }
  }
}

module.exports = { navigateInitialPage };
