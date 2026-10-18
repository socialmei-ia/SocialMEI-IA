/* Bundle the approved native sources plus preview adapters for offline review. */
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../..");
const frontend = path.join(root, "frontend");
const output = path.resolve(
  process.argv[2] || path.join(root, "work/reports-v21/SocialMEI-Relatorios-V2.1.html"),
);
function inlineScript(source, attributes = "") {
  return (
    "<script" + attributes + ">\n" + source.replace(/<\/script/gi, "<\\/script") + "\n</script>"
  );
}
function css(file) {
  return fs.readFileSync(file, "utf8").replace(/url\(["']?([^)'"\s]+)["']?\)/g, (match, source) => {
    if (source.startsWith("data:") || source.startsWith("#")) return match;
    const asset = path.resolve(path.dirname(file), source);
    if (!asset.startsWith(frontend + path.sep) || !fs.existsSync(asset))
      throw Error("Asset não local: " + source);
    const type = asset.endsWith(".woff2") ? "font/woff2" : "image/png";
    return `url("data:${type};base64,${fs.readFileSync(asset).toString("base64")}")`;
  });
}
let html = fs.readFileSync(path.join(frontend, "socialmei-app.html"), "utf8");
html = html.replace(
  "<head>",
  "<head>" + inlineScript(fs.readFileSync(path.join(__dirname, "sandbox.js"), "utf8")),
);
html = html.replace(
  /<link rel="stylesheet" href="([^"]+)"\s*\/>/g,
  (_, file) => "<style>\n" + css(path.join(frontend, file)) + "\n</style>",
);
html = html.replace(
  /<script\b([^>]*?)\bsrc="([^"]+)"([^>]*)>\s*<\/script>/g,
  (_, before, file, after) =>
    inlineScript(
      fs.readFileSync(
        file === "config.js" ? path.join(__dirname, "config.js") : path.join(frontend, file),
        "utf8",
      ),
      before + after,
    ),
);
html = html.replace(
  'href="assets/brand-icon.png"',
  'href="data:image/png;base64,' +
    fs.readFileSync(path.join(frontend, "assets/brand-icon.png")).toString("base64") +
    '"',
);
html = html.replace(
  "</head>",
  "<style>\n" + css(path.join(__dirname, "preview.css")) + "\n</style></head>",
);
html = html.replace(
  "</body>",
  inlineScript(fs.readFileSync(path.join(__dirname, "experience.js"), "utf8")) + "</body>",
);
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, html);
console.log(output);
