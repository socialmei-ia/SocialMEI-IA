const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const script = fs.readFileSync(path.join(__dirname, "../frontend/scripts/entrada.js"), "utf8");
const start = script.indexOf("  // Read the one-use recovery token");
const end = script.indexOf("  var account =", start);
const formStart = script.indexOf("  if (remote && recoveryLinkToken) {");
const formEnd = script.indexOf("  async function requestRecovery()", formStart);
assert(start > 0 && end > start && formStart > end && formEnd > formStart);
const parse = script.slice(start, end);
const fill = script.slice(formStart, formEnd);

function open(fragment, remote = true) {
  let replaced = null;
  const location = {
    pathname: "/frontend/entrada.html",
    search: "",
    hash: fragment,
  };
  const fields = {
    "#rToken": { value: "" },
    "#rStatus": { textContent: "" },
  };
  const stages = [];
  const ctx = {
    location,
    history: {
      state: { keep: "state" },
      replaceState(state, unused, value) {
        replaced = value;
        location.hash = value.slice(value.indexOf("#"));
        assert.equal(state.keep, "state");
      },
    },
    remote,
    $(selector) { return fields[selector]; },
    rSet(stage, focus) { stages.push([stage, focus]); },
  };
  vm.createContext(ctx);
  vm.runInContext(parse + "\n" + fill, ctx);
  return { ctx, location, fields, stages, replaced };
}

test("one-use URL fragment is erased while reset form receives the token", () => {
  const token = "X".repeat(43);
  const result = open("#/recuperar/" + token);
  assert.equal(result.replaced, "/frontend/entrada.html#/recuperar");
  assert.equal(result.location.hash, "#/recuperar");
  assert.equal(result.fields["#rToken"].value, token);
  assert.equal(result.fields["#rStatus"].textContent.includes("nova senha"), true);
  assert.deepEqual(result.stages, [[3, false]]);
  assert.equal(result.ctx.recoveryLinkToken, null);
});

test("malformed token fragment is erased without prefill", () => {
  const result = open("#/recuperar/not-a-real-token");
  assert.equal(result.location.hash, "#/recuperar");
  assert.equal(result.fields["#rToken"].value, "");
  assert.equal(result.stages.length, 0);
});

test("local demonstration does not use remote recovery links", () => {
  const result = open("#/recuperar/" + "T".repeat(43), false);
  assert.equal(result.location.hash, "#/recuperar");
  assert.equal(result.fields["#rToken"].value, "");
  assert.equal(result.stages.length, 0);
});
