const assert = require("node:assert/strict");
const { test } = require("node:test");
const { evaluatePassword } = require("../frontend/scripts/password-strength.js");

test("empty passwords have no active strength cells", () => {
  const state = evaluatePassword("");
  assert.equal(state.score, 0);
  assert.equal(state.max, 4);
  assert(state.rules.every((rule) => !rule.met));
});

test("guessable patterns stay weak even when every suggestion is met", () => {
  for (const password of ["Password123456!", "OtheraaaaAB12!", "OtherAbcd78#!"]) {
    const state = evaluatePassword(password);
    assert.equal(state.guessable, true);
    assert.equal(state.score, 1);
  }
});

test("an invalid short password is not presented as good or strong", () => {
  const state = evaluatePassword("Aa9!");
  assert.equal(state.score, 1);
  assert.equal(state.label, "Muito curta");
  assert.equal(state.rules[0].met, false);
});

test("the length suggestion follows the existing local or remote form policy", () => {
  const password = "Local9!X";
  assert.equal(evaluatePassword(password, 8).rules[0].met, true);
  assert.equal(evaluatePassword(password, 12).rules[0].met, false);
});

test("uppercase, lowercase and symbols include Portuguese and Unicode input", () => {
  const state = evaluatePassword("Árvore-Céu9∞Sol");
  assert.equal(state.score, 4);
  assert.equal(state.guessable, false);
  assert(state.rules.every((rule) => rule.met));
});

test("evaluation returns suggestions and scores without returning the password", () => {
  const password = "Private-Synthetic-9!";
  const state = evaluatePassword(password);
  assert.equal(JSON.stringify(state).includes(password), false);
  assert.deepEqual(Object.keys(state).sort(), ["guessable", "label", "max", "rules", "score"]);
});
