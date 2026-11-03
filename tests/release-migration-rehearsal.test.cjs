const assert = require("node:assert/strict");
const { test, after } = require("node:test");
const {
  mkdtempSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
  rmSync,
} = require("node:fs");
const { tmpdir } = require("node:os");
const { dirname, join, resolve } = require("node:path");
const modulePromise = import("../tools/release-migration-rehearsal.mjs");
const repository = resolve(__dirname, ".."),
  legacyRoot = mkdtempSync(join(tmpdir(), "socialmei-reviewed035-"));
mkdirSync(join(legacyRoot, "database/migrations"), { recursive: true });
for (const name of readdirSync(join(repository, "database/migrations")).filter(
  (n) => /^\d{3}_.*\.sql$/.test(n) && Number(n.slice(0, 3)) <= 35,
))
  writeFileSync(
    join(legacyRoot, "database/migrations", name),
    readFileSync(join(repository, "database/migrations", name)),
  );
after(() => rmSync(legacyRoot, { recursive: true }));

test("rehearsal is a non-mutating plan by default and exposes exact reviewed profile", async () => {
  const { parseOptions, rehearse } = await modulePromise;
  const plan = await rehearse(parseOptions([]), legacyRoot);
  assert.equal(plan.mode, "plan");
  assert.equal(plan.profile, "035");
  assert.equal(Object.keys(plan.source_migrations).length, 35);
  assert.equal(Object.keys(plan.baseline_migrations).length, 33);
  assert.equal(plan.production_data_used, false);
  assert.equal(plan.production_runtime_changed, false);
});

test("execution requires an exact commit and content-addressed API image", async () => {
  const { parseOptions } = await modulePromise;
  for (const values of [
    ["--run"],
    ["--run", "--source-sha", "0054a04"],
    ["--run", "--source-sha", "a".repeat(40), "--api-image", "latest"],
    ["--database-url", "postgresql://production"],
  ])
    assert.throws(() => parseOptions(values));
  assert.equal(
    parseOptions([
      "--run",
      "--source-sha",
      "a".repeat(40),
      "--api-image",
      "sha256:" + "b".repeat(64),
    ]).run,
    true,
  );
});

test("artifact paths and Docker endpoints cannot target other machines or directories", async () => {
  const { workspacePath, localDocker, ROOT } = await modulePromise;
  assert.equal(
    workspacePath(ROOT, ".preview/receipt.json"),
    resolve(ROOT, ".preview/receipt.json"),
  );
  assert.throws(() => workspacePath(ROOT, "../outside.json"));
  assert.throws(() => workspacePath(ROOT, ROOT));
  for (const endpoint of [
    "ssh://production",
    "tcp://localhost:2375",
    "tcp://54.94.213.7:2375",
    undefined,
  ])
    assert.equal(localDocker(endpoint), false);
  assert.equal(localDocker("unix:///var/run/docker.sock"), true);
  assert.equal(localDocker("npipe:////./pipe/dockerDesktopLinuxEngine"), true);
});

test("SQL identity normalizes only CRLF and refuses missing migrations", async () => {
  const { migrationManifest, ROOT } = await modulePromise;
  const original = migrationManifest(legacyRoot),
    temp = mkdtempSync(join(tmpdir(), "socialmei-migration35-"));
  try {
    const directory = join(temp, "database/migrations");
    mkdirSync(directory, { recursive: true });
    for (const name of original.names)
      writeFileSync(
        join(directory, name),
        readFileSync(join(ROOT, "database/migrations", name), "utf8").replace(/\r?\n/g, "\r\n"),
      );
    assert.deepEqual(migrationManifest(temp).source_migrations, original.source_migrations);
    writeFileSync(join(directory, original.names[34]), "SELECT 1;\n");
    assert.notEqual(
      migrationManifest(temp).source_migrations[original.names[34]],
      original.source_migrations[original.names[34]],
    );
    rmSync(join(directory, original.names[34]));
    assert.throws(() => migrationManifest(temp), /migration_profile_not_035/);
  } finally {
    assert.equal(dirname(resolve(temp)), resolve(tmpdir()));
    rmSync(temp, { recursive: true });
  }
});

test("live constraint rehearsal covers tenant boundaries and uncertain send state", async () => {
  const { CONTRACT } = await modulePromise;
  for (const expected of [
    "channel_id=5002",
    "conversation_id=6002",
    "source_message_id=7002",
    "created_by=2002",
    "revision=9007199254740992",
    "23505",
    "member_delete_contract_invalid",
    "ROLLBACK;",
  ])
    assert(CONTRACT.includes(expected));
});

test("schema comparison accepts only the known lossless PostgreSQL dump rewrites", async () => {
  const { canonicalExpression } = await modulePromise;
  const before =
    "CHECK ((status)::text = ANY ((ARRAY['pending'::character varying, 'done'::character varying])::text[]))";
  const after =
    "CHECK ((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('done'::character varying)::text]))";
  assert.equal(canonicalExpression(before), after);
  assert.equal(canonicalExpression(after), after);
  for (const expression of [
    "(ARRAY['a'::character varying(1)])::text[]",
    "(ARRAY[status::character varying])::text[]",
    "(ARRAY[1::integer])::text[]",
    "CHECK (status='done')",
  ])
    assert.equal(canonicalExpression(expression), expression);
  assert.notEqual(canonicalExpression(before.replace("'done'", "'sent'")), after);
  const nested =
    "CHECK ((((octet_length(text) >= 1) AND (octet_length(text) <= 1000)) AND (length(btrim(text)) > 0)))";
  const flat =
    "CHECK (((octet_length(text) >= 1) AND (octet_length(text) <= 1000) AND (length(btrim(text)) > 0)))";
  assert.equal(canonicalExpression(nested), flat);
  assert.notEqual(canonicalExpression(nested.replace("1000", "2000")), flat);
});
