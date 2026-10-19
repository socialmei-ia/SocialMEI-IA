const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawnSync } = require("node:child_process");
const prettier = require("prettier");

test("temporary format diagnostic", async () => {
  for (const file of ["frontend/scripts/instagram-publisher.js", "frontend/socialmei-app.html"]) {
    const source = path.resolve(__dirname, "..", file);
    const original = fs.readFileSync(source, "utf8");
    const formatted = await prettier.format(original, { filepath: source });
    if (original === formatted) continue;
    const output = path.join(os.tmpdir(), "socialmei-format-diagnostic");
    fs.writeFileSync(output, formatted);
    const diff = spawnSync("diff", ["-u", source, output], { encoding: "utf8" });
    console.log("FORMAT DIFF START " + file + "\n" + diff.stdout + "\nFORMAT DIFF END " + file);
  }
});
