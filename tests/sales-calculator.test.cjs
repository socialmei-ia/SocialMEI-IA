const { test } = require("node:test");
const assert = require("node:assert/strict");
const calc = require("../frontend/scripts/sales-calculator.js");

test("calculates three manual scenario hypotheses", () => {
  const result = calc.calculate({ count: 10, ticket: 150, rates: [20, 40, 60], closed: 2 });
  assert.deepEqual(result.scenarios.map((s) => s.expectedSales), [2, 4, 6]);
  assert.deepEqual(result.scenarios.map((s) => s.grossRevenue), [300, 600, 900]);
  assert.deepEqual(result.scenarios.map((s) => s.difference), [-300, 0, 300]);
  assert.equal(result.closedRevenue, 300);
});

test("does not invent revenue from zero inputs", () => {
  const result = calc.calculate({ count: 0, ticket: 0, rates: [0, 40, 100] });
  assert.deepEqual(result.scenarios.map((s) => s.grossRevenue), [0, 0, 0]);
  assert.equal(result.closedRevenue, null);
});

test("retains fractional expected sales and cents", () => {
  const result = calc.calculate({ count: 3, ticket: 19.9, rates: [20, 40, 60] });
  assert.equal(result.scenarios[0].expectedSales, 0.6);
  assert.equal(result.scenarios[0].grossRevenue, 11.94);
});

test("rejects invalid manual inputs", () => {
  const valid = { count: 8, ticket: 150, rates: [20, 40, 60] };
  for (const broken of [
    { count: -1 }, { count: 1.5 }, { count: Infinity }, { ticket: NaN },
    { ticket: -1 }, { rates: [20, 40] }, { rates: [101, 40, 60] },
    { closed: -1 }, { closed: 9 }, { count: 1000001 },
  ]) assert.throws(() => calc.calculate({ ...valid, ...broken }));
});
