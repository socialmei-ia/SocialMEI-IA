const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

// SHA-256 computed from the two exact HTML files supplied for this iteration.
// Golden references must not be reformatted, minified or modified in-place.
const originals = [
  ["Oportunidades-V8-original.html", "01947470141d0b18d19aade38680537f8ccac9319342b226b457f0f1d9ff2499"],
  ["Divulgacao-V4-original.html", "922905cf26b4892867ee4682480d8ce54137b90b8b494ceab89cb5a864556659"],
];
for (const [name, expected] of originals) {
  test("exact user-supplied prototype reference remains intact: " + name, () => {
    const file = path.join(__dirname, "..", "frontend", "reference", name);
    const actual = crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
    assert.equal(actual, expected, "Do not modify the golden HTML source; work in the app instead");
  });
}
