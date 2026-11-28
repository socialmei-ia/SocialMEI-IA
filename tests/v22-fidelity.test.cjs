const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { test } = require("node:test");
const root = path.resolve(__dirname, "..");
const bytes = (name) => fs.readFileSync(path.join(root, name));
const sha = (value) => crypto.createHash("sha256").update(value).digest("hex");
const styles = (value) =>
  [...value.toString().matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/g)].map((match) => match[1]);
const approved = JSON.parse(bytes("deploy/premium-v7911/schema046-manifest.json")).files;

test("V22 native CSS and original reference retain the owner supplied composition and animations", () => {
  const original = bytes("frontend/reference/Frontend-V22-original.html");
  assert.equal(
    sha(original),
    "14bd96c4be2750e6db9de2733d81bcd685eb41acc38d363cd92c38b1b86ce562",
    "Reference must be the supplied original, not an edited baseline",
  );
  const originalStyles = styles(original);
  const app = bytes("frontend/socialmei-app.html");
  const integratedStyles = bytes("frontend/styles/app-base.css");
  assert(originalStyles.length > 0);
  assert.deepEqual(styles(app), [], "Premium uses the external stylesheet");
  assert.match(app.toString(), /<link rel="stylesheet" href="styles\/app-base\.css"/);
  assert.equal(sha(integratedStyles), approved["styles/app-base.css"]);
  for (const declaration of ["@keyframes", "prefers-reduced-motion", "transition:"])
    assert(integratedStyles.includes(declaration), declaration);
});

test("Premium entry and the original reference assets retain exact approved bytes", () => {
  const manifest = {
    "frontend/styles/entrada.css": approved["styles/entrada.css"],
    "frontend/scripts/hero-wall.js": approved["scripts/hero-wall.js"],
    "frontend/scripts/sections-anim.js": approved["scripts/sections-anim.js"],
    "frontend/assets/inter-variable.woff2":
      "3100e775e8616cd2611beecfa23a4263d7037586789b43f035236a2e6fbd4c62",
    "frontend/assets/logo-socialmei.png":
      "813aac0cd14fc012d3c879afc63dadaae7f77953b6bf32b143c6383d484b5342",
    "frontend/assets/workspace-hero.png":
      "51504c3863e193e9696604563d06f2abac4ac7a46c6404c2d296e85f71154865",
    "frontend/assets/brand-icon.png":
      "d046ce2c613f92e85412d7ab7e405ae91c6425231d2adafed92e66650ed25b2c",
  };
  for (const [name, expected] of Object.entries(manifest))
    assert.equal(sha(bytes(name)), expected, name);
});
