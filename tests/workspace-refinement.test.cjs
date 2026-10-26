const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend/socialmei-app.html"), "utf8");

const css = [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)]
  .map((match) => match[1])
  .join("\n");

test("V22 workspace preserves native shell, tabs and identity-gated bootstrap", () => {
  assert.match(html, /<div id="app"><\/div>/);
  assert.match(html, /id="v22-native-source"/);
  assert.match(html, /function nhead\(tab\)/);
  assert.match(html, /Resumo','Vendas','Clientes','Produtos','Financeiro/);
  const scripts = [...html.matchAll(/<script[^>]*src="([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(scripts, ["config.js", "scripts/auth-store.js", "scripts/v22-bootstrap.js"]);
  const bootstrap = fs.readFileSync(path.join(root, "frontend/scripts/v22-bootstrap.js"), "utf8");
  assert.match(bootstrap, /await auth.ready/);
  assert.match(bootstrap, /scripts\/v22-backend\.js/);
});

test("V22 workspace keeps each operational view and searchable record actions", () => {
  for (const name of ["vendas", "clientes", "produtos", "financeiro"])
    assert.match(html, new RegExp("function " + name + "\\(\\)"));
  assert(html.includes('data-a="novo:${a[0]}"'));
  for (const kind of ["venda", "cliente", "produto", "lanc"])
    assert(html.includes("if(k==='" + kind + "')"), kind);
  for (const action of ["edit:cli", "edit:prod"])
    assert(html.includes('data-a="' + action + '"'), action);
  for (const placeholder of [
    "Buscar por nome ou e-mail",
    "Buscar por nome ou código",
    "Buscar lançamento",
  ])
    assert(html.includes(placeholder), placeholder);
  assert.match(html, /const search=\(q,ph\)=>/);
  assert.match(html, /data-q="\$\{q\}"/);
  assert.match(html, /function filt\(inp\)/);
});

test("V22 workspace retains keyboard, mobile and reduced-motion rules", () => {
  assert.match(css, /:focus-visible/);
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /prefers-reduced-motion:reduce/);
  assert.match(css, /\.tb/);
  assert.match(html, /data-a="edit:cli"/);
  assert.match(html, /data-a="edit:prod"/);
});
