const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const markup = fs.readFileSync(path.join(root, "frontend/socialmei-app.html"), "utf8");

const nativeCSS = [...markup.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)]
  .map((match) => match[1])
  .join("\n");

test("V22 Home keeps sales, Inbox and content shortcuts in the native hero", () => {
  assert.match(markup, /class="hc" href="#\/negocio\/vendas"/);
  assert.match(markup, /class="hc" href="#\/caixa"/);
  assert.match(markup, /class="hc y" href="#\/divul"/);
  assert.match(markup, /Registrar uma venda/);
  assert.match(markup, /id="cmd" role="combobox"/);
  assert.match(markup, /const paraHoje=/);
  assert.match(nativeCSS, /\.hc:hover\{transform:translateX\(-6px\)/);
});

test("V22 Home actions preserve focus and reduced-motion feedback", () => {
  assert.match(nativeCSS, /:focus-visible\{outline:2px solid var\(--p\)/);
  assert.match(nativeCSS, /\.hc:focus-visible\{animation-play-state:paused/);
  assert.match(nativeCSS, /prefers-reduced-motion:reduce/);
  assert.match(markup, /aria-label="\$\{HP\}"/);
});

test("V22 Home headings and shortcuts retain responsive layout rules", () => {
  assert.match(nativeCSS, /\.hero h1\{font-size:clamp\(34px,3\.7vw,50px\)/);
  assert.match(nativeCSS, /@media\(max-width:900px\)/);
  assert.match(nativeCSS, /#v>\.hero \.cs>\.hc:nth-child\(n\+2\)/);
  assert.match(nativeCSS, /padding:10px 14px;gap:12px;font-size:16px/);
});
