const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const frontend = path.resolve(__dirname, "../frontend");
const source = fs.readFileSync(path.join(frontend, "testes-publicos.html"), "utf8");
const references = [
  "reference/Oportunidades-V8-original.html",
  "reference/Divulgacao-V4-original.html",
];

test("public prototype landing links to the two immutable local HTML references", () => {
  for (const href of references) {
    assert(source.includes('href="' + href + '"'), "Missing original reference: " + href);
    const file = path.resolve(frontend, href);
    assert(file.startsWith(frontend + path.sep), "Reference escapes frontend directory");
    assert(fs.existsSync(file), "Missing reference: " + href);
    assert(fs.readFileSync(file, "utf8").startsWith("<!DOCTYPE html>"));
  }
});

test("public test landing never calls production services or embeds connected app", () => {
  assert.match(source, /Laborat[oó]rio p[uú]blico/);
  assert.match(source, /somente simula[cç][aã]o/i);
  assert.match(source, /n[aã]o o CRM conectado/i);
  assert.match(source, /N[aã]o insira nomes/i);
  assert.doesNotMatch(source, /<(iframe|form|script)\b/i);
  assert.doesNotMatch(source, /https?:\/\//i);
  assert.doesNotMatch(source, /\b(api\/v1|webhook|token|client_secret|password)\b/i);
});

test("both reference prototypes remain standalone; never expose fake persistence as CRM", () => {
  for (const href of references) {
    const html = fs.readFileSync(path.resolve(frontend, href), "utf8");
    assert.match(html, /localStorage/);
    assert.doesNotMatch(html, /\bfetch\s*\(/);
  }
});
