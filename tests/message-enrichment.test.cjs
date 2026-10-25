const test = require("node:test"),
  assert = require("node:assert/strict");
const { create, identityKey } = require("../frontend/scripts/message-enrichment-store.js");
const identity = (workspace = 1, role = "owner") => ({
  usuario: { id: 11 },
  negocio: { id: workspace },
  papel: role,
});
const row = (id = 1) => ({
  id,
  channel: "whatsapp",
  account_ref: "synthetic:a",
  contact_ref: "synthetic:a",
  contact_name: "Mesmo nome",
  revision: 1,
  messages: [{ id, text: "Mensagem fictícia", revision: 1 }],
});
function fixture() {
  const requests = [],
    auth = {
      remote: true,
      current: identity(),
      async request(path, method = "GET", body) {
        requests.push({ path, method, body });
        if (method !== "GET") return { id: 1 };
        if (path.endsWith("capabilities"))
          return {
            schema_version: 1,
            mode: "stub",
            transport: "none",
            workspace_id: auth.current.negocio.id,
          };
        return path.endsWith("conversations")
          ? { workspace_id: auth.current.negocio.id, items: [row()] }
          : { workspace_id: auth.current.negocio.id, items: [] };
      },
    };
  return { auth, requests, store: create({ auth }) };
}
test("local mode never contacts the API or changes legacy persistence", async () => {
  const { auth, requests, store } = fixture();
  auth.remote = false;
  await store.refresh();
  assert.equal(requests.length, 0);
  assert.equal(store.state().status, "unavailable");
});
test("workspace and session are required, with no browser-selected tenant", async () => {
  const { auth, requests, store } = fixture();
  auth.current = null;
  await store.refresh();
  assert.equal(identityKey(null), null);
  assert.equal(requests.length, 0);
  assert.deepEqual(store.state().rows, []);
});
test("capability disabled prevents data reads and writes", async () => {
  const { auth, requests, store } = fixture();
  auth.request = async () => ({
    schema_version: 1,
    mode: "disabled",
    transport: "none",
    workspace_id: 1,
  });
  await store.refresh();
  assert.equal(store.state().status, "disabled");
  await assert.rejects(
    store.write("x", "/synthetic-messages", "POST", {}, identityKey(auth.current)),
  );
  assert.equal(requests.length, 0);
});
test("validated conversations keep same-name contacts distinct and return snapshots", async () => {
  const { auth, store } = fixture(),
    request = auth.request;
  auth.request = async (p) =>
    p.endsWith("conversations")
      ? {
          workspace_id: auth.current.negocio.id,
          items: [row(1), { ...row(2), contact_ref: "synthetic:b" }],
        }
      : request(p);
  await store.refresh();
  let s = store.state();
  assert.equal(s.rows.length, 2);
  s.rows[0].contact_name = "changed";
  assert.equal(store.state().rows[0].contact_name, "Mesmo nome");
});
test("invalid source data cannot silently become local conversations", async () => {
  const { auth, store } = fixture(),
    request = auth.request;
  auth.request = async (p) =>
    p.endsWith("conversations")
      ? {
          workspace_id: auth.current.negocio.id,
          items: [{ ...row(), account_ref: "real-account" }],
        }
      : request(p);
  await store.refresh();
  assert.equal(store.state().status, "error");
  assert.deepEqual(store.state().rows, []);
});
test("scope switch discards previous results and rejects an old form", async () => {
  const { auth, store } = fixture();
  await store.refresh();
  const old = store.state().scope;
  auth.current = identity(2);
  assert.deepEqual(store.state().rows, []);
  await assert.rejects(store.write("x", "/synthetic-messages", "POST", {}, old), /sessão mudou/);
});
test("viewer cannot write; member cannot manage RAG documents", async () => {
  const { auth, store } = fixture();
  await store.refresh();
  const scope = store.state().scope;
  auth.current.papel = "viewer";
  await assert.rejects(
    store.write("x", "/synthetic-messages", "POST", {}, scope),
    /somente leitura/,
  );
  auth.current.papel = "member";
  await assert.rejects(store.write("x", "/documents", "POST", {}, scope), /somente leitura/);
});
test("offline retries keep the same operation ID and payload", async () => {
  const { auth, requests, store } = fixture();
  await store.refresh();
  const request = auth.request;
  let fail = true;
  auth.request = async (p, m, b) => {
    if (m === "POST") {
      requests.push({ path: p, method: m, body: b });
      if (fail) throw new Error("offline");
      return { id: 1 };
    }
    return request(p, m, b);
  };
  const args = ["m", "/synthetic-messages", "POST", { text: "Fictícia" }, store.state().scope];
  await assert.rejects(store.write(...args));
  fail = false;
  await store.write(...args);
  const writes = requests.filter((r) => r.method === "POST");
  assert.equal(writes.length, 2);
  assert.deepEqual(writes[0].body, writes[1].body);
  assert(writes[0].body.operation_id);
});
test("human-review conflict preserves submitted revision and never blindly retries", async () => {
  const { auth, store } = fixture();
  await store.refresh();
  let writes = 0;
  auth.request = async () => {
    writes++;
    throw Object.assign(new Error("conflict"), { status: 409 });
  };
  await assert.rejects(
    store.write(
      "review",
      "/jobs/test/review",
      "PATCH",
      { expected_revision: 1, suggested_reply: "Rascunho" },
      store.state().scope,
    ),
  );
  assert.equal(writes, 1);
  assert.match(store.state().problem, /rascunho foi preservado/);
});
test("out-of-order reads cannot overwrite the latest workspace snapshot", async () => {
  const { auth, store } = fixture(),
    request = auth.request;
  let release;
  auth.request = async (p, ...a) =>
    p.endsWith("conversations") ? new Promise((r) => (release = r)) : request(p, ...a);
  const old = store.refresh();
  while (!release) await new Promise((r) => setImmediate(r));
  auth.current = identity(2);
  auth.request = request;
  await store.refresh();
  release({ items: [row(99)] });
  await old;
  assert.equal(store.state().rows[0].id, 1);
  assert.equal(store.state().scope, identityKey(auth.current));
});
test("verified browser identity mismatch blocks reads before a shared-cookie account switch", async () => {
  const { auth, requests } = fixture();
  const store = create({ auth, verifiedScope: () => null });
  await store.refresh();
  assert.equal(requests.length, 0);
  assert.deepEqual(store.state().rows, []);
});
test("server workspace metadata must match the captured account identity", async () => {
  const { auth, store } = fixture(),
    request = auth.request;
  auth.request = async (...args) => ({ ...(await request(...args)), workspace_id: 999 });
  await store.refresh();
  assert.equal(store.state().status, "error");
  assert.deepEqual(store.state().rows, []);
});
test("lost refresh after confirmed POST keeps its idempotency key for retry", async () => {
  const { auth, store } = fixture();
  await store.refresh();
  const base = auth.request,
    operations = [];
  let unavailable = true;
  auth.request = async (p, method, body) => {
    if (method === "POST") {
      operations.push(body.operation_id);
      return { id: 1 };
    }
    if (p.endsWith("conversations") && unavailable) throw new Error("offline");
    return base(p, method, body);
  };
  const args = [
    "document",
    "/documents",
    "POST",
    { title: "Fictício", content: "Texto fictício" },
    store.state().scope,
  ];
  await store.write(...args);
  assert.equal(store.state().status, "error");
  unavailable = false;
  await store.write(...args);
  assert.equal(operations.length, 2);
  assert.equal(operations[0], operations[1]);
});
test("Instagram rows require explicit provenance and capability without synthetic masking", async () => {
  const { auth, store } = fixture();
  const providerRow = {
    ...row(),
    origin: "instagram",
    channel: "instagram",
    account_ref: "instagram:987654321",
    contact_ref: "instagram:123456789",
    messages: [
      {
        id: 1,
        text: "  Original\n",
        external_message_id: "m".repeat(300),
        occurred_at: "2026-10-23T15:40:00.123Z",
        revision: 1,
        enrichment: null,
      },
    ],
  };
  auth.request = async (p) =>
    p.endsWith("capabilities")
      ? {
          schema_version: 1,
          mode: "disabled",
          transport: "none",
          workspace_id: 1,
          instagram_inbox: true,
        }
      : { workspace_id: 1, items: [providerRow] };
  await store.refresh();
  assert.equal(store.state().status, "ready");
  assert.equal(store.state().rows[0].origin, "instagram");
  assert.equal(store.state().rows[0].messages[0].text, "  Original\n");
  await assert.rejects(store.write("x", "/synthetic-messages", "POST", {}, store.state().scope));
  for (const change of [
    { origin: "unknown" },
    { origin: "synthetic" },
    { account_ref: "synthetic:fake" },
    { channel: "whatsapp" },
  ]) {
    auth.request = async (p) =>
      p.endsWith("capabilities")
        ? {
            schema_version: 1,
            mode: "disabled",
            transport: "none",
            workspace_id: 1,
            instagram_inbox: true,
          }
        : { workspace_id: 1, items: [{ ...providerRow, ...change }] };
    await store.refresh();
    assert.equal(store.state().status, "error");
  }
});

test("WAHA provider provenance supports opaque LIDs without enabling synthetic writes", async () => {
  const { auth, store } = fixture();
  const provider = {
    ...row(),
    origin: "waha",
    channel: "whatsapp",
    account_ref: "waha:111@c.us",
    contact_ref: "waha:opaque-22@lid",
    messages: [
      {
        id: 1,
        text: " WAHA original\n",
        external_message_id: "mid-long-" + "x".repeat(300),
        occurred_at: "2026-10-25T12:00:00.123Z",
        revision: 1,
        enrichment: null,
      },
    ],
  };
  let candidate = provider;
  auth.request = async (p) =>
    p.endsWith("capabilities")
      ? {
          schema_version: 1,
          mode: "disabled",
          transport: "none",
          workspace_id: 1,
          waha_inbox: true,
        }
      : { workspace_id: 1, items: [candidate] };
  await store.refresh();
  assert.equal(store.state().status, "ready");
  assert.equal(store.state().rows[0].origin, "waha");
  await assert.rejects(store.write("x", "/synthetic-messages", "POST", {}, store.state().scope));
  for (const change of [
    { origin: "synthetic" },
    { account_ref: "synthetic:fake" },
    { contact_ref: "waha:123@g.us" },
    { channel: "instagram" },
  ]) {
    candidate = { ...provider, ...change };
    await store.refresh();
    assert.equal(store.state().status, "error");
  }
});
