const { test } = require("node:test");
const fs = require("node:fs");
const { execFileSync } = require("node:child_process");
test("temporary formatting diagnostics", async () => {
  for (const path of [
    "frontend/scripts/sales-calculator.js",
    "frontend/socialmei-app.html",
    "tests/sales-calculator.test.cjs",
  ]) {
    const raw = fs.readFileSync(path, "utf8");
    const formatted = execFileSync(process.execPath, ["node_modules/prettier/bin/prettier.cjs", path], { encoding: "utf8", maxBuffer: 4000000 });
    const base64 = Buffer.from(formatted, "utf8").toString("base64");
    const tag = path.replaceAll("/", "_");
    for (let i = 0; i < base64.length; i += 7000) {
      console.log("FORMAT-EXPORT:" + tag + ":" + String(i / 7000) + ":" + base64.slice(i, i + 7000));
    }
    console.log("FORMAT-END:" + tag);
  }
});
