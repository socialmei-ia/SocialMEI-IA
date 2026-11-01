const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

const load = () => import("../tools/prepare-instagram-persistence.mjs");
const options = {
  sourceSha: "a".repeat(64),
  publishedVersion: "published-fixture",
  apiOrigin: "https://app.example.com",
};
function fixture() {
  return {
    id: "LHlqroY2xzvpYAmD",
    name: "PRIVATE_NAME",
    versionId: options.publishedVersion,
    active: true,
    settings: { executionOrder: "v1" },
    nodes: [
      {
        id: "hook-id",
        webhookId: "keep-webhook-id",
        name: "Original webhook",
        type: "n8n-nodes-base.webhook",
        parameters: {
          path: "PRIVATE_PATH",
          httpMethod: "POST",
          responseMode: "onReceived",
          options: {},
        },
      },
      { id: "switch", name: "Branch", type: "n8n-nodes-base.switch", parameters: {} },
      {
        id: "ai",
        name: "AI",
        type: "@n8n/n8n-nodes-langchain.agent",
        parameters: {},
        credentials: { groqApi: { id: "PRIVATE_REFERENCE" } },
      },
      {
        id: "send",
        name: "Send",
        type: "n8n-nodes-base.httpRequest",
        parameters: { method: "POST", url: "PRIVATE_URL" },
      },
      {
        id: "orphan",
        name: "Unused response",
        type: "n8n-nodes-base.respondToWebhook",
        parameters: {},
      },
    ],
    connections: {
      "Original webhook": { main: [[{ node: "Branch", type: "main", index: 0 }]] },
      Branch: { main: [[{ node: "AI", type: "main", index: 0 }]] },
      AI: { main: [[{ node: "Send", type: "main", index: 0 }]] },
    },
  };
}

test("patches same published workflow, preserves old graph and credentials", async () => {
  const { prepare, NAMES } = await load();
  const input = fixture(),
    copy = structuredClone(input);
  const result = prepare(input, options),
    graph = result.candidate;
  assert.deepEqual(input, copy);
  assert.equal(result.target_workflow_id, input.id);
  assert.equal(result.automatically_publish, false);
  assert.equal(graph.nodes[0].parameters.responseMode, "responseNode");
  assert.equal(graph.nodes[0].parameters.options.rawBody, true);
  assert.equal(graph.nodes[0].webhookId, input.nodes[0].webhookId);
  assert.deepEqual(graph.nodes.slice(1, input.nodes.length), input.nodes.slice(1));
  assert.deepEqual(graph.connections[NAMES.resume], input.connections["Original webhook"]);
  assert.deepEqual(graph.connections.AI, input.connections.AI);
  assert.equal(graph.nodes.filter((n) => n.type === "n8n-nodes-base.webhook").length, 1);
  assert.equal(graph.nodes.filter((n) => n.name === "Send").length, 1);
});

test("no acknowledgement or AI path bypasses persistence or failure handling", async () => {
  const { prepare, NAMES } = await load();
  const graph = prepare(fixture(), options).candidate;
  const route = [
    "Original webhook",
    NAMES.prepare,
    NAMES.sign,
    NAMES.persist,
    NAMES.validate,
    NAMES.ack,
    NAMES.resume,
    "Branch",
    "AI",
    "Send",
  ];
  for (let i = 0; i < route.length - 1; i++)
    assert.equal(graph.connections[route[i]].main[0][0].node, route[i + 1]);
  for (const key of ["prepare", "sign", "persist", "validate"]) {
    assert.equal(graph.connections[NAMES[key]].main[1][0].node, NAMES.fail);
    assert.equal(graph.nodes.find((n) => n.name === NAMES[key]).onError, "continueErrorOutput");
  }
  assert.equal(graph.connections[NAMES.fail], undefined);
  assert.equal(graph.nodes.find((n) => n.name === NAMES.fail).parameters.options.responseCode, 503);
  const http = graph.nodes.find((n) => n.name === NAMES.persist).parameters;
  assert.equal(http.options.redirect.redirect.followRedirects, false);
  assert.equal(http.options.response.response.neverError, false);
  assert.equal(http.contentType, "raw");
  assert.equal(http.headerParameters.parameters.at(-1).name, "X-Hub-Signature-256");
});

test("original bytes and original signature survive signing, including Unicode and whitespace", async () => {
  const { PREPARE } = await load();
  const body = Buffer.from('{ "object":"instagram", "entry": [], "text":"Olá ☕" }\n');
  const signature = "sha256=" + "b".repeat(64);
  const input = [{ json: { headers: { "x-hub-signature-256": signature } } }];
  const execute = new (Object.getPrototypeOf(async function () {}).constructor)(
    "$input",
    "Buffer",
    PREPARE,
  );
  const result = await execute.call(
    { helpers: { getBinaryDataBuffer: async () => body } },
    { all: () => input },
    Buffer,
  );
  assert.equal(result[0].json.body_text, body.toString());
  assert.equal(result[0].json.meta_signature, signature);
  const key = "isolated-key-".repeat(4);
  const actual = crypto
    .createHmac("sha256", key)
    .update(result[0].json.signing_input)
    .digest("hex");
  const expected = crypto
    .createHmac("sha256", key)
    .update(result[0].json.timestamp + "\n")
    .update(body)
    .digest("hex");
  assert.equal(actual, expected);
  assert.ok(!PREPARE.includes("JSON.stringify"));
  await assert.rejects(
    execute.call(
      { helpers: { getBinaryDataBuffer: async () => Buffer.alloc(65537) } },
      { all: () => input },
      Buffer,
    ),
  );
  await assert.rejects(execute.call({}, { all: () => [{ json: { headers: {} } }] }, Buffer));
});

test("valid receipt is required before ack; exact/mixed retries cannot rerun AI", async () => {
  const { prepare, NAMES } = await load();
  const graph = prepare(fixture(), options).candidate;
  const code = (key) => graph.nodes.find((n) => n.name === NAMES[key]).parameters.jsCode;
  const validate = new Function("$input", code("validate"));
  const resume = new Function("$", code("resume"));
  for (const receipt of [
    { received: true, continue_automation: true, processed: 1, duplicates: 0, ignored: 0 },
    { received: true, continue_automation: false, processed: 0, duplicates: 1, ignored: 0 },
    { received: true, continue_automation: false, processed: 1, duplicates: 1, ignored: 0 },
  ]) {
    const items = [{ json: receipt }];
    assert.deepEqual(validate({ first: () => items[0], all: () => items }), items);
    const original = [{ json: { body: { original: true } } }];
    assert.deepEqual(
      resume((name) => ({
        first: () => items[0],
        all: () => (name === "Original webhook" ? original : items),
      })),
      receipt.continue_automation ? original : [],
    );
  }
  assert.throws(() => validate({ first: () => ({ json: { received: false } }) }));
  assert.throws(() =>
    validate({
      first: () => ({
        json: {
          received: true,
          processed: 1,
          duplicates: 1,
          ignored: 0,
          continue_automation: true,
        },
      }),
    }),
  );
});

test("refuses drift, duplicate transform, unsafe origin, and reachable old ACK", async () => {
  const { prepare } = await load();
  for (const change of [
    (w) => (w.id = "other"),
    (w) => (w.versionId = "saved-not-published"),
    (w) => (w.connections.AI.main[0][0].node = "Unused response"),
    (w) => (w.connections.AI.main[0][0].node = "Original webhook"),
  ]) {
    const w = fixture();
    change(w);
    assert.throws(() => prepare(w, options));
  }
  for (const apiOrigin of [
    "http://app.example.com",
    "https://user:pass@app.example.com",
    "https://app.example.com/path",
  ])
    assert.throws(() => prepare(fixture(), { ...options, apiOrigin }));
  const w = fixture(),
    once = prepare(w, options);
  assert.throws(() => prepare({ ...w, ...once.candidate }, options));
});

test("offline CLI pins export bytes, refuses overwrite, prints no private workflow", async () => {
  const { main } = await load();
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "ig-persist-"));
  try {
    const input = path.join(directory, "source.json"),
      output = path.join(directory, "candidate.json");
    const bytes = JSON.stringify(fixture());
    await fs.writeFile(input, bytes);
    const args = [
      "--input",
      input,
      "--output",
      output,
      "--expected-sha256",
      crypto.createHash("sha256").update(bytes).digest("hex"),
      "--published-version",
      options.publishedVersion,
      "--api-origin",
      options.apiOrigin,
    ];
    const result = await main(args);
    assert.ok(!JSON.stringify(result).includes("PRIVATE"));
    assert.equal(result.production_changed, false);
    await assert.rejects(main(args));
    assert.equal(JSON.parse(await fs.readFile(output)).target_workflow_id, fixture().id);
    args[5] = "b".repeat(64);
    await assert.rejects(main(args));
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});
