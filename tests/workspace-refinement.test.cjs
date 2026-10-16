const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend/socialmei-app.html"), "utf8");
const cssPath = path.join(root, "frontend/styles/workspace-refinement.css");

test("business workspace uses its own design layer without changing script order", () => {
  assert.match(html, /href="styles\/workspace-refinement\.css"/);
  assert.match(html, /class="management-shell workspace-shell" id="nvShell"/);
  assert.match(html, /class="workspace-eyebrow"/);
  assert.match(html, /class="management-tabs workspace-tabs"/);
  assert.equal((html.match(/class="management-card management-flush workspace-list-panel"/g) || []).length, 4);
  assert.equal((html.match(/class="management-tools workspace-list-toolbar"/g) || []).length, 4);
  assert(fs.existsSync(cssPath), "workspace stylesheet must exist");
});

test("workspace redesign preserves native actions and searchable records", () => {
  for (const id of [
    "nvTitle",
    "nvTabs",
    "nvActs",
    "privacyBtn",
    "salesSearch",
    "clientsSearch",
    "productsSearch",
    "financeSearch",
    "salesTable",
    "clientsTable",
    "productsGrid",
    "financeTable",
  ]) {
    assert.match(html, new RegExp('id="' + id + '"'));
  }
  assert.match(html, /role="tablist"/);
});

test("workspace styles expose focus, small-screen and reduced-motion states", () => {
  const css = fs.readFileSync(cssPath, "utf8");
  assert.match(css, /\.workspace-tabs button\[aria-selected="true"\]/);
  assert.match(css, /\.workspace-tabs button:focus-visible/);
  assert.match(css, /\.workspace-list-panel \.management-table tbody tr:focus-within/);
  assert.match(css, /@media \(max-width: 760px\)/);
  assert.match(css, /@media \(max-width: 480px\)/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(css, /!important/);
});
