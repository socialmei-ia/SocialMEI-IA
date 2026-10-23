// Run only after approval/publication. It cannot deploy and never uses CRM credentials.
const { chromium } = require("playwright");
(async () => {
  const [url, sha] = process.argv.slice(2);
  if (!url || !/^[0-9a-f]{40}$/.test(sha || ""))
    throw Error("Use: npm run demo:smoke -- https://socialmei-lab.pages.dev/ APPROVED_SHA");
  const { checkPublished, verifyPackage } = await import("../tools/verify-public-demo.mjs");
  const { manifest, headers } = await verifyPackage("test-results/public-demo", sha);
  const result = await checkPublished(url, sha, fetch, {
    trustedManifest: manifest,
    expectedHeaders: headers,
  });
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  try {
    await require("./public-demo-browser.cjs")(browser, new URL(url).origin, {
      build: false,
      basePath: "/",
    });
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(result));
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
