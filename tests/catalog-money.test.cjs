const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const context = vm.createContext({});
vm.runInContext(
  fs.readFileSync(path.join(__dirname, "../frontend/scripts/products.js"), "utf8"),
  context,
);

test("catalog accepts cent amounts and trailing zeros without rounding", () => {
  for (const value of [
    0,
    "0.01",
    ".5",
    "12.34",
    "12.340",
    "1.234e1",
    "1234e-2",
    "9999999999999.99",
  ])
    assert.equal(context.isCatalogAmount(value), true, String(value));
});
test("catalog rejects precision lost by Number conversion and out-of-range amounts", () => {
  for (const value of [
    "",
    "12.345",
    "12.3400000000000000001",
    "9999999999999.991",
    "10000000000000",
    "1e20",
    "1e-999",
    -1,
    "NaN",
    "Infinity",
    "not a price",
  ])
    assert.equal(context.isCatalogAmount(value), false, String(value));
});
