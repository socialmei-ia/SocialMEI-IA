const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const directory = path.resolve(__dirname, "../test-results/public-demo");
test("allowlisted package, Pages security headers/404, integrity and deployment target guards", async () => {
  execFileSync(process.execPath, [path.resolve(__dirname, "../tools/package-public-demo.mjs")]);
  const { verifyPackage, checkPublished } = await import("../tools/verify-public-demo.mjs");
  const { servePublicDemo } = await import("../tools/public-demo-local-server.mjs");
  const candidate = await verifyPackage(directory);
  const server = await servePublicDemo(directory);
  const options = {
    allowDirtyLocal: true,
    trustedManifest: candidate.manifest,
    expectedHeaders: candidate.headers,
  };
  try {
    assert(
      (await checkPublished(server.origin, candidate.manifest.sha, fetch, options)).securityHeaders,
    );
    for (const invalid of [
      "https://socialmei-ia.54-94-213-7.sslip.io",
      "https://example.com",
      "https://socialmei-lab.pages.dev.evil.test",
      "https://user:pass@socialmei-lab.pages.dev",
      "http://socialmei-lab.pages.dev",
    ])
      await assert.rejects(
        checkPublished(
          invalid,
          candidate.manifest.sha,
          () => {
            throw Error("Must not request network");
          },
          options,
        ),
      );
    await assert.rejects(checkPublished(server.origin, "0".repeat(40), fetch, options));
    const forged = async (...args) => {
      const response = await fetch(...args);
      if (new URL(args[0]).pathname === "/manifest.json")
        return new Response(JSON.stringify({ ...candidate.manifest, files: [] }), {
          status: 200,
          headers: response.headers,
        });
      return response;
    };
    await assert.rejects(
      checkPublished(server.origin, candidate.manifest.sha, forged, options),
      /manifest differs/,
    );
    const redirect = async () =>
      new Response(null, { status: 302, headers: { location: "https://example.com" } });
    await assert.rejects(
      checkPublished(server.origin, candidate.manifest.sha, redirect, options),
      /approved demo origin/,
    );
  } finally {
    await server.close();
  }
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "socialmei-static-"));
  try {
    await fs.cp(directory, temp, { recursive: true });
    await fs.appendFile(path.join(temp, "index.html"), "tampered");
    await assert.rejects(verifyPackage(temp), /Integrity failure/);
    await fs.cp(directory, temp, { recursive: true });
    await fs.writeFile(path.join(temp, ".env"), "fixture-only");
    await assert.rejects(verifyPackage(temp), /Unexpected/);
    await fs.rm(path.join(temp, ".env"));
    await fs.rm(path.join(temp, "index.html"));
    await fs.symlink(path.join(directory, "index.html"), path.join(temp, "index.html"));
    await assert.rejects(verifyPackage(temp), /Symlinks/);
  } finally {
    await fs.rm(temp, { recursive: true, force: true });
  }
});
