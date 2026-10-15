const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs
  .readFileSync(path.join(__dirname, "../tools/db-migrate.mjs"), "utf8")
  .replace(/^import .*;\n/gm, "");

function runCommand(command, { initialized = false, applied = [] } = {}) {
  const queries = [];
  const output = [];
  const migrations = ["001_first.sql", "002_second.sql"];
  vm.runInNewContext(source, {
    process: {
      argv: ["node", "db-migrate.mjs", command],
      exit(code) {
        throw new Error(`Unexpected exit: ${code}`);
      },
      stderr: { write: assert.fail },
    },
    console: { log: (value) => output.push(value), error: assert.fail },
    existsSync: () => true,
    readdirSync: () => migrations,
    readFileSync: (file) =>
      file === ".env.development"
        ? "POSTGRES_USER=test\nPOSTGRES_DB=disposable\n"
        : "SELECT 'test migration';",
    basename: path.basename,
    join: path.join,
    spawnSync(executable, args, options) {
      assert.equal(executable, "docker");
      assert(args.includes("compose.dev.yaml"));
      const sql = options.input;
      queries.push(sql);
      const stdout = sql.includes("to_regclass")
        ? initialized
          ? "t"
          : "f"
        : sql.includes("SELECT version")
          ? applied.join("\n")
          : "";
      return { status: 0, stdout };
    },
  });
  return { queries, output };
}

test("migration status on an empty database never creates a schema or table", () => {
  const { queries, output } = runCommand("status");
  assert.equal(queries.length, 1);
  assert(queries.every((sql) => /^SELECT /.test(sql)));
  assert(output.some((line) => line.includes("001_first.sql") && line.includes("pendente")));
});

test("migration status reads existing history without changing records", () => {
  const { queries, output } = runCommand("status", {
    initialized: true,
    applied: ["001_first.sql"],
  });
  assert.equal(queries.length, 2);
  assert(queries.every((sql) => /^SELECT /.test(sql)));
  assert(output.some((line) => line.includes("001_first.sql") && line.includes("aplicada")));
  assert(output.some((line) => line.includes("002_second.sql") && line.includes("pendente")));
});

test("explicit migrate still initializes history and applies pending files transactionally", () => {
  const { queries } = runCommand("migrate", { applied: ["001_first.sql"] });
  assert(queries[0].includes("CREATE SCHEMA IF NOT EXISTS"));
  assert.equal(queries.filter((sql) => sql.includes("INSERT INTO")).length, 1);
  assert(queries[2].includes("BEGIN;"));
  assert(queries[2].includes("002_second.sql"));
  assert(queries[2].includes("COMMIT;"));
});

test("explicit migrate does not replay an already installed file", () => {
  const { queries, output } = runCommand("migrate", {
    applied: ["001_first.sql", "002_second.sql"],
  });
  assert.equal(queries.length, 2);
  assert(!queries.some((sql) => sql.includes("INSERT INTO")));
  assert(output.some((line) => line.includes("já está atualizado")));
});
