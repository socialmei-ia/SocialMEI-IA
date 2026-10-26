const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const load = () => import("../tools/preview.mjs");

test("preview refuses remote Docker targets and injected compose settings", async () => {
  const { validateEnvironment, validateDockerEndpoint } = await load();
  for (const key of [
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "COMPOSE_FILE",
    "COMPOSE_PROJECT_NAME",
    "DATABASE_URL",
  ]) {
    assert.throws(() => validateEnvironment({ [key]: "external" }), /ambiente/i);
  }
  for (const endpoint of ["ssh://server", "tcp://localhost:2375", "tcp://10.0.0.1:2376", ""]) {
    assert.throws(() => validateDockerEndpoint(endpoint), /local/i);
  }
  validateDockerEndpoint("unix:///var/run/docker.sock");
  validateDockerEndpoint("npipe:////./pipe/dockerDesktopLinuxEngine");
});

test("preview secrets are generated once and existing malformed files are refused", async () => {
  const { ensurePreviewEnv } = await load();
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "socialmei-preview-test-"));
  try {
    const file = ensurePreviewEnv(directory);
    const first = fs.readFileSync(file, "utf8");
    assert.match(
      first,
      /^PREVIEW_POSTGRES_PASSWORD=[a-f0-9]{64}\nPREVIEW_TEST_KEY=[a-f0-9]{64}\n$/,
    );
    assert.equal(ensurePreviewEnv(directory), file);
    assert.equal(fs.readFileSync(file, "utf8"), first);
    fs.appendFileSync(file, "DATABASE_URL=external\n");
    assert.throws(() => ensurePreviewEnv(directory), /configuração/i);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("preview fixes compose target and never removes volumes", async () => {
  const { composeArguments } = await load();
  assert.deepEqual(composeArguments("down", "local.env"), [
    "compose",
    "--project-name",
    "socialmei-preview",
    "--env-file",
    "local.env",
    "-f",
    "compose.preview.yaml",
    "down",
  ]);
  assert.deepEqual(composeArguments("up", "local.env").slice(-6), [
    "up",
    "-d",
    "--build",
    "--wait",
    "--wait-timeout",
    "180",
  ]);
  assert.deepEqual(composeArguments("check", "local.env").slice(-2), ["config", "--quiet"]);
  assert.throws(() => composeArguments("reset", "local.env"), /comando/i);
});
