const test = require("node:test");
const assert = require("node:assert/strict");
const workflow = require("../n8n-workflows/experimental/provider-sentiment-worker.json");

test("workflow sentiment stays inactive, needs operator enablement", () => {
  assert.equal(workflow.active, false);
  const gate = workflow.nodes.find((n) => n.name === "Piloto protegido");
  assert.match(gate.parameters.jsCode, /ENABLED = false/);
  assert.equal(gate.type, "n8n-nodes-base.code");
});

test("sentiment workflow only calls the internal API; never sends messages", () => {
  const requests = workflow.nodes.filter((node) => node.type === "n8n-nodes-base.httpRequest");
  assert.equal(requests.length, 2);
  const paths = requests.map((node) => new URL(node.parameters.url).pathname).sort();
  assert(requests.every((node) => node.parameters.method === "POST"));
  assert.deepEqual(paths, [
    "/internal/message-enrichment/provider/claims",
    "/internal/message-enrichment/provider/results",
  ]);
  for (const node of requests) {
    assert.equal(node.parameters.authentication, "genericCredentialType");
    assert.equal(node.parameters.genericAuthType, "httpHeaderAuth");
    assert.equal(node.retryOnFail, false);
    assert.equal(node.credentials, undefined);
  }
});

test("the AI output is validated and claim identity is taken from the task", () => {
  const validate = workflow.nodes.find((node) => node.name === "Validar classificacao");
  assert.equal(validate.parameters.mode, "runOnceForEachItem");
  assert.match(validate.parameters.jsCode, /Individualizar classificacoes/);
  assert.match(validate.parameters.jsCode, /JSON\.parse\(raw\)/);
  assert.match(validate.parameters.jsCode, /claim_id:task\.claim_id/);
  for (const node of workflow.nodes) {
    if (node.type === "n8n-nodes-base.code")
      assert.doesNotThrow(() => new Function(node.parameters.jsCode));
  }
});

test("team API only receives opt-in sentiment configuration from its private environment", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const compose = fs.readFileSync(path.join(__dirname, "..", "compose.team.yaml"), "utf8");
  assert.match(
    compose,
    /SOCIALMEI_PROVIDER_SENTIMENT_ENABLED: \$\{SOCIALMEI_PROVIDER_SENTIMENT_ENABLED:-false\}/,
  );
  assert.match(
    compose,
    /SOCIALMEI_PROVIDER_SENTIMENT_KEY: \$\{SOCIALMEI_PROVIDER_SENTIMENT_KEY:-\}/,
  );
  assert.match(
    compose,
    /SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS: \$\{SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS:-\}/,
  );
});

test("n8n bridge uses a private team automation network only, never team PostgreSQL", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const root = path.join(__dirname, "..");
  const team = fs.readFileSync(path.join(root, "compose.team.yaml"), "utf8");
  const bridge = fs.readFileSync(path.join(root, "compose.team-n8n-bridge.yaml"), "utf8");
  assert.match(team, /automation:\n    internal: true\n    name: socialmei_team_automation/);
  assert.match(team, /networks: \[database, api, automation\]/);
  assert.match(bridge, /external: true/);
  assert.match(bridge, /name: socialmei_team_automation/);
  assert.match(bridge, /networks:\n      - default\n      - team_automation/);
  assert.doesNotMatch(bridge, /team-postgres|POSTGRES_PASSWORD|ports:/);
});

test("team WAHA bot config remains opt-in and registry is read-only", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const team = fs.readFileSync(path.join(__dirname, "..", "compose.team.yaml"), "utf8");
  assert.match(team, /SOCIALMEI_WAHA_INGRESS_MODE: \$\{SOCIALMEI_WAHA_INGRESS_MODE:-disabled\}/);
  assert.match(
    team,
    /SOCIALMEI_WAHA_LAB_ENVIRONMENT: \$\{SOCIALMEI_WAHA_LAB_ENVIRONMENT:-disabled\}/,
  );
  assert.match(team, /SOCIALMEI_WHATSAPP_BOT_ENABLED: \$\{SOCIALMEI_WHATSAPP_BOT_ENABLED:-false\}/);
  assert.match(team, /SOCIALMEI_WAHA_REGISTRY_FILE: \/run\/socialmei\/private\/waha-registry.json/);
  assert.match(team, /\.\/deploy\/team\/private:\/run\/socialmei\/private:ro/);
});
