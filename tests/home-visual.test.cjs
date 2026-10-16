const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const markup = fs.readFileSync(path.join(root, "frontend/socialmei-app.html"), "utf8");
const css = fs.readFileSync(path.join(root, "frontend/styles/socialmei.css"), "utf8");

test("Home highlights the real sales action without hiding other shortcuts", () => {
  assert.match(markup, /data-home-go="Vendas" data-home-create="venda"/);
  assert.match(markup, /data-home-go="Caixa Unificada"/);
  assert.match(markup, /data-home-go="Automações"/);
  assert.match(css, /\.command-starters button\[data-home-create="venda"\] \{/);
  assert.match(
    css,
    /\.command-starters button\[data-home-create="venda"\]:is\(:hover, :focus-visible\)/,
  );
});

test("Home actions have keyboard focus feedback and mobile-friendly sales totals", () => {
  assert.match(css, /\.home-priority-row:focus-visible,/);
  assert.match(css, /\.home-sale-row:focus-visible/);
  assert.match(css, /\.command-starters button:focus-visible/);
  assert.match(css, /\.home-sale-row > strong \{[\s\S]*?overflow-wrap: anywhere;/);
});
