const test = require("node:test"),
  assert = require("node:assert/strict");
const fixture = require("./opportunities-v8-fixture.cjs");

test("opportunity fixture accepts partial planning PATCH without erasing business fields", async () => {
  const api = fixture();
  let handler;
  await api.install(
    {
      route: async (pattern, callback) => {
        handler = callback;
      },
    },
    "https://fixture.test",
  );
  const row = api.rows[0],
    title = row.title,
    interest = row.interest_level;
  let result;
  const request = (body) =>
    handler({
      request: () => ({
        url: () => `https://fixture.test/api/v1/opportunities/${row.id}`,
        method: () => "PATCH",
        headers: () => ({ "x-socialmei-csrf": api.identity.csrf_token }),
        postDataJSON: () => body,
      }),
      fulfill: async (value) => {
        result = value;
      },
      abort() {
        throw Error("unexpected abort");
      },
      continue() {
        throw Error("unexpected continue");
      },
    });
  await request({
    operation_id: "fixture-planning",
    expected_revision: 1,
    planning_note: "shared",
    estimated_amount: 1.23,
  });
  assert.equal(result.status, 200);
  assert.equal(row.title, title);
  assert.equal(row.interest_level, interest);
  assert.equal(row.planning_note, "shared");
  assert.equal(row.estimated_amount, 1.23);
  assert.equal(row.planning_initialized, true);
  assert.equal(row.revision, 2);
  const before = JSON.stringify(row);
  await request({
    operation_id: "fixture-invalid",
    expected_revision: 2,
    interest_level: "invented",
  });
  assert.equal(result.status, 422);
  assert.equal(JSON.stringify(row), before);
  assert.equal(api.events.get(row.id).length, 2);
});
