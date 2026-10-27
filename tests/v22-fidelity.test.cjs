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

test("V22 native CSS and original reference retain the owner supplied composition and animations", () => {
  const original = bytes("frontend/reference/Frontend-V22-original.html");
  assert.equal(
    sha(original),
    "14bd96c4be2750e6db9de2733d81bcd685eb41acc38d363cd92c38b1b86ce562",
    "Reference must be the supplied original, not an edited baseline",
  );
  const originalStyles = styles(original),
    integratedStyles = styles(bytes("frontend/socialmei-app.html"));
  assert(originalStyles.length > 0);
  assert.deepEqual(
    integratedStyles,
    originalStyles,
    "Backend wiring cannot modify the original CSS or animation declarations",
  );
  for (const declaration of ["@keyframes", "prefers-reduced-motion", "transition:"])
    assert(originalStyles.join("\n").includes(declaration), declaration);
});

test("V25 entry styles and V22-preserved assets match the owner supplied ZIP bytes", () => {
  const manifest = {
    "frontend/styles/entrada.css":
      "6daf78e04befe978450658c9dff38fd925658589c05b9b48687cbdaffa76a86a",
    "frontend/scripts/hero-wall.js":
      "9032905fe937c6a5a7c20b368306333eab10a4c1bb5426bfa306c5fc9a28f087",
    "frontend/scripts/sections-anim.js":
      "a381dbcac34aa9e5a260237b1aa3feb38eb25af40568651ef3204c3dde6dfead",
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
