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

test("V22 inline and external scripts parse with their shared globals in load order", () => {
  const sources = [];
  const scripts = [...app.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
  const external = [];
  for (const [, attributes, body] of scripts) {
    const source = attributes.match(/src="([^"]+)"/);
    if (source) {
      external.push(source[1]);
      sources.push(read("frontend/" + source[1]));
    } else {
      assert(body.trim(), "Inline application source must not be empty");
      sources.push(body);
    }
  }
  for (const source of sources) new vm.Script(source);
  new vm.Script(sources.join("\n"));
  for (const file of filesUnder(path.join(root, "frontend/scripts")).filter((file) =>
    file.endsWith(".js"),
  ))
    new vm.Script(fs.readFileSync(file, "utf8"), { filename: file });
  new vm.Script(read("tools/devhub.js"));
  assert.deepEqual(external, ["config.js", "scripts/auth-store.js", "scripts/v22-bootstrap.js"]);
  assert.equal(new Set(external).size, external.length, "Each bootstrap controller is loaded once");
  assert.match(app, /<script type="text\/plain" id="v22-native-source">/);
  const bootstrap = read("frontend/scripts/v22-bootstrap.js");
  assert.match(bootstrap, /await auth.ready/);
  assert.match(bootstrap, /original.textContent/);
  assert.match(bootstrap, /scripts\/v22-backend\.js/);
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

test("V22 static DOM IDs are unique and native modules remain present", () => {
  // IDs inside JS template strings belong to alternative rendered routes, not the static document.
  const staticHTML = app
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, "")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/g, "");
  const ids = [...staticHTML.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => id);
  assert.equal(new Set(ids).size, ids.length, "Static document IDs cannot collide");
  assert(ids.includes("app"));
  for (const fn of [
    "inicio",
    "caixaList",
    "vendas",
    "clientes",
    "produtos",
    "financeiro",
    "automacoes",
    "relatorios",
    "config",
  ])
    assert(new RegExp("(?:function " + fn + "\\(|const " + fn + "=)").test(app), fn);
  for (const route of [
    "inicio",
    "caixa",
    "oport",
    "divul",
    "negocio",
    "automacoes",
    "relatorios",
    "config",
  ])
    assert(new RegExp("(?:['\"]" + route + "['\"]|" + route + ":)").test(app), route);
  assert.match(app, /telas\/oportunidades\.html/);
  assert.match(app, /telas\/divulgacao\.html/);
  const entry = read("frontend/entrada.html");
  for (const id of ["fC", "fE", "cNome", "cMail", "cPass", "eMailL", "ePassL", "obCard", "stepper"])
    assert(entry.includes('id="' + id + '"'), id);
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
