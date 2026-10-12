import { existsSync, readFileSync, readdirSync } from "node:fs";
import { basename, join } from "node:path";
import { spawnSync } from "node:child_process";

const action = process.argv[2] || "status";
const envFile = ".env.development";
const composeFile = "compose.dev.yaml";
const migrationsDir = "database/migrations";

function fail(message) {
  console.error(message);
  process.exit(1);
}

function readEnv(path) {
  if (!existsSync(path)) {
    fail(`${path} não existe. Rode "npm run setup" primeiro.`);
  }

  const values = {};
  for (const rawLine of readFileSync(path, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const separator = line.indexOf("=");
    if (separator < 1) continue;

    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();
    value = value.replace(/^["']|["']$/g, "");
    values[key] = value;
  }

  return values;
}

const env = readEnv(envFile);
const user = env.POSTGRES_USER || "socialmei_dev";
const database = env.POSTGRES_DB || "socialmei_dev";

function psql(sql, { tuplesOnly = false } = {}) {
  const args = [
    "compose",
    "--env-file",
    envFile,
    "-f",
    composeFile,
    "exec",
    "-T",
    "postgres",
    "psql",
    "-v",
    "ON_ERROR_STOP=1",
  ];

  if (tuplesOnly) args.push("-A", "-t");
  args.push("-U", user, "-d", database);

  const result = spawnSync("docker", args, {
    input: sql,
    encoding: "utf8",
  });

  if (result.error) {
    fail('Não foi possível executar Docker. Confirme se o ambiente está ativo com "npm run dev".');
  }

  if (result.status !== 0) {
    process.stderr.write(result.stderr || "");
    fail("Falha ao executar migration no PostgreSQL local.");
  }

  return (result.stdout || "").trim();
}

function ensureMigrationTable() {
  psql(`
CREATE SCHEMA IF NOT EXISTS socialmei;
CREATE TABLE IF NOT EXISTS socialmei.schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
`);
}

function migrationFiles() {
  if (!existsSync(migrationsDir)) return [];

  return readdirSync(migrationsDir)
    .filter((name) => /^\d{3}_[a-z0-9_]+\.sql$/.test(name))
    .sort();
}

function appliedVersions() {
  ensureMigrationTable();
  const output = psql("SELECT version FROM socialmei.schema_migrations ORDER BY version;", {
    tuplesOnly: true,
  });

  return new Set(
    output
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

function quoteSql(value) {
  return value.replaceAll("'", "''");
}

function showStatus() {
  const applied = appliedVersions();
  const files = migrationFiles();

  if (!files.length) {
    console.log("Nenhuma migration encontrada.");
    return;
  }

  console.log("Migrations do SocialMEI:");
  for (const file of files) {
    const state = applied.has(file) ? "aplicada" : "pendente";
    console.log(`  [${state === "aplicada" ? "x" : " "}] ${file} — ${state}`);
  }
}

function migrate() {
  const applied = appliedVersions();
  const pending = migrationFiles().filter((file) => !applied.has(file));

  if (!pending.length) {
    console.log("Banco local já está atualizado.");
    return;
  }

  for (const file of pending) {
    const path = join(migrationsDir, file);
    const sql = readFileSync(path, "utf8");

    console.log(`Aplicando ${basename(path)}...`);
    psql(`
BEGIN;
${sql}
INSERT INTO socialmei.schema_migrations (version)
VALUES ('${quoteSql(file)}')
ON CONFLICT (version) DO NOTHING;
COMMIT;
`);
  }

  console.log(`\n${pending.length} migration(s) aplicada(s) com sucesso.`);
}

switch (action) {
  case "migrate":
    migrate();
    break;
  case "status":
    showStatus();
    break;
  default:
    fail('Uso: node tools/db-migrate.mjs "migrate" ou "status".');
}
