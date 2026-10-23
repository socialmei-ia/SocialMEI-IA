import { readFile, readdir, lstat } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";
export const PACKAGE_FILES = [
  "index.html",
  "reference/Oportunidades-V8-original.html",
  "reference/Divulgacao-V4-original.html",
  "manifest.json",
  "_headers",
  "README.txt",
  "404.html",
  "robots.txt",
].sort();
export function parseHeaders(text) {
  assert.equal(text.split("\n")[0], "/*");
  const result = {};
  for (const line of text.split("\n").slice(1).filter(Boolean)) {
    const match = /^  ([A-Za-z-]+): (.+)$/.exec(line);
    assert(match, "Invalid static header rule");
    assert(!result[match[1].toLowerCase()], "Duplicate header");
    result[match[1].toLowerCase()] = match[2];
  }
  assert.match(result["content-security-policy"], /connect-src 'none'/);
  assert.match(result["content-security-policy"], /frame-ancestors 'none'/);
  assert.match(result["content-security-policy"], /script-src 'sha256-/);
  assert(!result["content-security-policy"].includes("script-src 'unsafe-inline'"));
  assert.equal(result["cache-control"], "no-store");
  assert.equal(result["referrer-policy"], "no-referrer");
  assert.equal(result["x-content-type-options"], "nosniff");
  assert.equal(result["cross-origin-opener-policy"], "same-origin");
  assert.equal(result["cross-origin-resource-policy"], "same-origin");
  assert.equal(
    result["permissions-policy"],
    "camera=(), microphone=(), geolocation=(), payment=()",
  );
  return result;
}
export async function verifyPackage(directory, expectedSha) {
  const root = resolve(directory),
    found = [];
  async function walk(relative = "") {
    for (const item of await readdir(resolve(root, relative))) {
      const name = relative ? relative + "/" + item : item;
      const info = await lstat(resolve(root, name));
      assert(!info.isSymbolicLink(), "Symlinks are forbidden");
      if (info.isDirectory()) {
        assert.equal(name, "reference");
        await walk(name);
      } else {
        assert(info.isFile());
        found.push(name);
      }
    }
  }
  await walk();
  assert.deepEqual(found.sort(), PACKAGE_FILES, "Unexpected or missing public package files");
  const manifest = JSON.parse(await readFile(resolve(root, "manifest.json"), "utf8"));
  assert.match(manifest.sha, /^[0-9a-f]{40}$/);
  if (expectedSha) assert.equal(manifest.sha, expectedSha, "Candidate SHA mismatch");
  assert.equal(manifest.published, false);
  const entries = [...manifest.files, ...manifest.assets];
  assert.deepEqual(
    entries.map((f) => f.target).sort(),
    PACKAGE_FILES.filter((f) => f !== "manifest.json"),
  );
  for (const item of entries) {
    const bytes = await readFile(resolve(root, item.target));
    assert.equal(
      createHash("sha256").update(bytes).digest("hex"),
      item.sha256,
      "Integrity failure: " + item.target,
    );
  }
  const headers = parseHeaders(await readFile(resolve(root, "_headers"), "utf8"));
  return { manifest, headers, root, files: found };
}
export async function checkPublished(
  origin,
  expectedSha,
  fetcher = fetch,
  { allowDirtyLocal = false, trustedManifest, expectedHeaders } = {},
) {
  const url = new URL(origin);
  assert.equal(url.pathname, "/");
  assert(
    !url.username && !url.password && !url.search && !url.hash,
    "Only a clean origin is allowed",
  );
  assert(
    (url.protocol === "https:" &&
      /^(?:[a-z0-9-]+\.)?socialmei-lab\.pages\.dev$/.test(url.hostname)) ||
      (url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname)),
    "Only the proposed Pages project or loopback may be tested",
  );
  assert.match(expectedSha, /^[0-9a-f]{40}$/);
  assert(
    trustedManifest && expectedHeaders,
    "Use the verified local candidate manifest and headers",
  );
  const request = async (path) => {
    let next = new URL(path, url);
    for (let i = 0; i < 4; i++) {
      assert.equal(next.origin, url.origin, "Redirect must remain on the approved demo origin");
      assert(!next.username && !next.password && !next.search && !next.hash);
      const response = await fetcher(next, {
        method: "GET",
        credentials: "omit",
        redirect: "manual",
        signal: AbortSignal.timeout(15000),
      });
      assert(!response.headers.has("set-cookie"), "Demonstration must not establish a session");
      if (![301, 302, 307, 308].includes(response.status)) return response;
      const location = response.headers.get("location");
      assert(location, "Redirect without a destination");
      next = new URL(location, next);
    }
    throw Error("Too many redirects");
  };
  const res = await request("manifest.json");
  assert.equal(res.status, 200);
  const manifest = await res.json();
  assert.equal(manifest.sha, expectedSha, "Published SHA is not the approved candidate");
  assert.equal(
    manifest.workingTreeDirty &&
      !(
        allowDirtyLocal &&
        url.protocol === "http:" &&
        ["127.0.0.1", "localhost"].includes(url.hostname)
      ),
    false,
  );
  assert.equal(manifest.published, false);
  assert.deepEqual(
    manifest,
    trustedManifest,
    "Published manifest differs from the approved artifact",
  );
  for (const entry of [...manifest.files, ...manifest.assets]) {
    assert(PACKAGE_FILES.includes(entry.target), "Invalid asset path");
    if (["_headers", "404.html"].includes(entry.target)) continue;
    const response = await request(entry.target);
    assert.equal(response.status, 200, entry.target);
    for (const [key, value] of Object.entries(expectedHeaders))
      assert.equal(response.headers.get(key), value, "Missing/changed header: " + key);
    const bytes = Buffer.from(await response.arrayBuffer());
    assert.equal(
      createHash("sha256").update(bytes).digest("hex"),
      entry.sha256,
      "Published content mismatch: " + entry.target,
    );
  }
  for (const absent of [
    "/api/v1/auth/session",
    "/frontend/config.js",
    "/.env",
    "/missing-page",
    "/_headers",
  ]) {
    const response = await request(absent);
    assert.equal(response.status, 404, "No SPA fallback or connected API: " + absent);
    assert.equal(
      createHash("sha256")
        .update(Buffer.from(await response.arrayBuffer()))
        .digest("hex"),
      manifest.assets.find((a) => a.target === "404.html").sha256,
    );
  }
  return {
    sha: manifest.sha,
    origin: url.origin,
    securityHeaders: true,
    integrity: true,
    backend: false,
  };
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const directory = process.argv[2] || "test-results/public-demo";
  console.log(
    JSON.stringify({
      verified: true,
      sha: (await verifyPackage(directory, process.argv[3])).manifest.sha,
    }),
  );
}
