const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { execFileSync } = require("node:child_process");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");
const app = read("frontend/socialmei-app.html");

test("tracked paths do not collide on case-insensitive Windows filesystems", () => {
  const paths = execFileSync("git", ["ls-files", "-z"], { cwd: root, encoding: "utf8" })
    .split("\0")
    .filter(Boolean);
  const names = paths.map((file) => file.toLowerCase());
  assert.equal(new Set(names).size, names.length);
});

function filesUnder(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? filesUnder(file) : [file];
  });
}

test("all scripts parse, including their shared global declarations", () => {
  const scriptPaths = [...app.matchAll(/<script\b[^>]*src="([^"]+)"[^>]*><\/script>/g)].map(
    ([, source]) => source,
  );
  const sources = scriptPaths.map((source) => read("frontend/" + source));
  for (const source of sources) new vm.Script(source);
  new vm.Script(sources.join("\n"));
  new vm.Script(read("tools/devhub.js"));
  assert.equal(sources.length, 53);
  assert.equal(
    scriptPaths.indexOf("scripts/content-preparation-store.js"),
    scriptPaths.indexOf("scripts/instagram-simulation.js") + 1,
  );
  assert.equal(
    scriptPaths.indexOf("scripts/message-enrichment-store.js") + 1,
    scriptPaths.indexOf("scripts/message-enrichment.js"),
  );
  assert(
    scriptPaths.indexOf("scripts/message-enrichment-store.js") >
      scriptPaths.indexOf("scripts/auth-store.js"),
  );
  assert.equal(
    scriptPaths.indexOf("scripts/business-profile.js") + 1,
    scriptPaths.indexOf("scripts/profile-sync.js"),
  );
  assert.equal(
    scriptPaths.indexOf("scripts/profile-sync.js") + 1,
    scriptPaths.indexOf("scripts/personalization.js"),
  );
  assert.equal(
    scriptPaths.indexOf("scripts/content-studio.js") + 1,
    scriptPaths.indexOf("scripts/instagram-publisher.js"),
  );
  assert.equal(
    scriptPaths.indexOf("scripts/instagram-publisher.js") + 1,
    scriptPaths.indexOf("scripts/instagram-simulation.js"),
  );
  assert.equal(
    scriptPaths.indexOf("scripts/client-analysis.js") + 1,
    scriptPaths.indexOf("scripts/opportunities.js"),
  );
  assert.equal(
    scriptPaths.indexOf("scripts/report-motion.js") + 1,
    scriptPaths.indexOf("scripts/report-ui.js"),
  );
  assert.deepEqual(scriptPaths.slice(-4), [
    "scripts/password-strength.js",
    "scripts/spotlight.js",
    "scripts/premium-experience.js",
    "scripts/context-help.js",
  ]);
  assert(
    scriptPaths.indexOf("scripts/password-strength.js") >
      scriptPaths.indexOf("scripts/experience.js"),
  );
});

test("published entries preserve paths and query/hash navigation", () => {
  for (const [entry, destination] of [
    ["index.html", "frontend/socialmei-app.html"],
    ["frontend/socialmei-dashboard.html", "socialmei-app.html"],
  ]) {
    let redirected;
    const script = read(entry).match(/<script>([\s\S]*?)<\/script>/)[1];
    vm.runInNewContext(script, {
      URL,
      location: {
        href: "https://example.test/SocialMEI-IA/" + entry,
        search: "?demo=1",
        hash: "#smAI",
        replace: (url) => (redirected = url),
      },
    });
    assert.equal(
      redirected,
      new URL(destination + "?demo=1#smAI", "https://example.test/SocialMEI-IA/" + entry).href,
    );
  }
});

test("static DOM IDs stay unique and every module remains present", () => {
  const ids = [...app.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => id);
  assert.equal(new Set(ids).size, ids.length);
  for (const id of [
    "experienceRoot",
    "clientHomeView",
    "dashboardView",
    "salesView",
    "clientsView",
    "productsView",
    "financeView",
    "inboxView",
    "automationsView",
    "aiToolsView",
    "reportsView",
    "settingsView",
    "xpLoginForm",
    "xpRegisterForm",
    "sb",
    "nav",
    "backupImportInput",
    "clearInboxFilters",
  ])
    assert(ids.includes(id), id);
  assert(app.includes("https://socialmei-ia.github.io/SocialMEI-IA/frontend/socialmei-app.html"));
  assert(!app.includes("seu-dominio.example"));
});

test("relative HTML and CSS resources exist without a build step", () => {
  for (const file of ["frontend/socialmei-app.html", "tools/mike-devhub.html"]) {
    for (const [, reference] of read(file).matchAll(/(?:src|href)="([^"]+)"/g)) {
      if (/^(?:[a-z]+:|#|\$\{)/i.test(reference)) continue;
      assert(fs.existsSync(path.resolve(root, path.dirname(file), reference)), reference);
    }
  }
  const css = read("frontend/styles/socialmei.css");
  for (const [, reference] of css.matchAll(/url\(["']?([^)'"\s]+)["']?\)/g)) {
    if (/^(?:data:|https?:)/.test(reference)) continue;
    assert(fs.existsSync(path.resolve(root, "frontend/styles", reference)), reference);
  }
});

test("workflow exports are valid, inactive and contain no literal authorization headers", () => {
  const files = filesUnder(path.join(root, "n8n-workflows")).filter((file) =>
    file.endsWith(".json"),
  );
  const structural = files.filter((file) =>
    file.startsWith(path.join(root, "n8n-workflows", "structure") + path.sep),
  );
  assert.equal(files.length - structural.length, 8);
  if (structural.length) assert.equal(structural.length, 8);
  for (const file of files) {
    const workflow = JSON.parse(fs.readFileSync(file, "utf8"));
    assert.equal(workflow.active, false, file);
    if (structural.includes(file)) {
      assert(workflow.name.startsWith("[STRUCTURE] "), file);
      assert(
        workflow.nodes.every((node) => node.disabled === true),
        file,
      );
    }
    for (const node of workflow.nodes) {
      assert(!node.credentials, file);
      const headers = node.parameters.headerParameters?.parameters || [];
      assert(!headers.some((header) => header.name.toLowerCase() === "authorization"), file);
    }
  }
});
