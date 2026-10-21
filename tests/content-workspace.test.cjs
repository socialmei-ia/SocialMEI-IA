const test = require("node:test");
const assert = require("node:assert/strict");
const model = require("../frontend/scripts/content-workspace.js");
test("agenda filters by status and local day in each job timezone", () => {
  const jobs = [
    {
      id: "a",
      status: "scheduled",
      scheduled_for: "2026-11-02T01:00:00Z",
      timezone: "America/Fortaleza",
    },
    {
      id: "b",
      status: "cancelled",
      scheduled_for: "2026-11-01T15:00:00Z",
      timezone: "America/Fortaleza",
    },
    { id: "c", status: "draft", scheduled_for: null, timezone: "America/Fortaleza" },
  ];
  assert.deepEqual(
    model.filterJobs(jobs, { status: "scheduled", day: "2026-11-01" }).map((j) => j.id),
    ["a"],
  );
  assert.deepEqual(
    model.filterJobs(jobs, { status: "all", day: "2026-11-01" }).map((j) => j.id),
    ["a", "b"],
  );
  assert.equal(model.filterJobs(jobs, { status: "draft", day: "" })[0].id, "c");
});
