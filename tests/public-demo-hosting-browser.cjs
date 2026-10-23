const { execFileSync } = require("node:child_process");
const path = require("node:path");
module.exports = async (browser) => {
  execFileSync(process.execPath, [path.resolve(__dirname, "../tools/package-public-demo.mjs")]);
  const { servePublicDemo } = await import("../tools/public-demo-local-server.mjs");
  const { checkPublished, verifyPackage } = await import("../tools/verify-public-demo.mjs");
  const directory = path.resolve(__dirname, "../test-results/public-demo");
  const { manifest, headers } = await verifyPackage(directory);
  const host = await servePublicDemo(directory);
  try {
    // An uncommitted local run still tests bytes; clean candidates are enforced for actual publishing.
    const result = await checkPublished(host.origin, manifest.sha, fetch, {
      allowDirtyLocal: true,
      trustedManifest: manifest,
      expectedHeaders: headers,
    });
    await require("./public-demo-browser.cjs")(browser, host.origin, {
      build: false,
      basePath: "/",
    });
    return { publicHosting: result, transport: "none" };
  } finally {
    await host.close();
  }
};
